// SPDX-License-Identifier: MIT
// One BLE central holding two links at once, with two peripherals.
//
// Each peripheral (B2L-1, B2L-2) notifies {id, sequence} every 20 ms. The
// central connects B2L-1, then B2L-2 while the first link runs, and checks for
// 5 s that every notification comes from the peer its link was opened to, that
// no sequence number repeats, and that both links keep up and stay connected.
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_timer.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "nvs_flash.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

#define SERVICE_UUID 0xB2B0
#define DATA_UUID 0xB2B1
#define NOTIFY_PERIOD_US 20000
#define LINK_DEADLINE_US 15000000     // both links up within 15 s of boot
#define WINDOW_US 5000000             // then measure for 5 s
#define MIN_PER_SECOND 40             // 50 nominal

#if CONFIG_B2L_CENTRAL
#define ROLE "central"
#elif CONFIG_B2L_P1
#define ROLE "P1"
#define PERIPHERAL_ID 1
#else
#define ROLE "P2"
#define PERIPHERAL_ID 2
#endif

static uint8_t s_addr_type;

static void print_addr(const char *label, const uint8_t *a)
{
    printf("%s=%02x:%02x:%02x:%02x:%02x:%02x", label, a[5], a[4], a[3], a[2], a[1], a[0]);
}

static void on_reset(int reason) { printf("B2L: host reset %d\n", reason); }

static void host_task(void *arg)
{
    (void)arg;
    nimble_port_run();
}

#if CONFIG_B2L_CENTRAL
// ---------------------------------------------------------------- central

struct link {
    uint16_t conn;
    uint16_t data_handle;
    uint16_t end_handle;
    bool ready;
    uint32_t count, cross, repeats, drops;
    uint32_t last_seq;
    bool have_seq;
};

static struct link s_link[2] = {{.conn = BLE_HS_CONN_HANDLE_NONE}, {.conn = BLE_HS_CONN_HANDLE_NONE}};
static bool s_connecting;
static int64_t s_window_start;
static bool s_reported;

static void scan(void);

static int link_of(uint16_t conn)
{
    for (int i = 0; i < 2; ++i) if (s_link[i].conn == conn) return i;
    return -1;
}

static void report(bool linked)
{
    s_reported = true;
    int failures = 0;
    for (int i = 0; i < 2; ++i) {
        const struct link *l = &s_link[i];
        const uint32_t per_second = l->count * 1000000ULL / WINDOW_US;
        printf("B2L: link%d ready=%d notifications=%" PRIu32 " per_s=%" PRIu32
               " cross=%" PRIu32 " repeats=%" PRIu32 " drops=%" PRIu32 "\n", i + 1, l->ready,
               l->count, per_second, l->cross, l->repeats, l->drops);
        failures += !l->ready + (l->cross != 0) + (l->repeats != 0) + (l->drops != 0)
                    + (per_second < MIN_PER_SECOND);
    }
    if (!linked) failures += 1;
    printf("RESULT: %s failures=%d\n", failures ? "FAIL" : "PASS", failures);
}

static void check_done(void *arg)
{
    (void)arg;
    if (s_reported) return;
    const int64_t now = esp_timer_get_time();
    if (s_window_start == 0 && now > LINK_DEADLINE_US) {
        printf("B2L: both links not up within %d s\n", LINK_DEADLINE_US / 1000000);
        report(false);
    } else if (s_window_start && now - s_window_start >= WINDOW_US) {
        report(true);
    }
}

static int on_subscribed(uint16_t conn, const struct ble_gatt_error *e, struct ble_gatt_attr *a, void *arg)
{
    (void)a; (void)arg;
    const int i = link_of(conn);
    if (i < 0 || e->status) return 0;
    s_link[i].ready = true;
    printf("B2L: link%d subscribed\n", i + 1);
    if (s_link[0].ready && s_link[1].ready) {
        for (int k = 0; k < 2; ++k) s_link[k].count = 0;   // count only the window
        s_window_start = esp_timer_get_time();
        printf("B2L: both links up at %" PRId64 " ms\n", s_window_start / 1000);
    }
    scan();
    return 0;
}

static int on_dsc(uint16_t conn, const struct ble_gatt_error *e, uint16_t chr, const struct ble_gatt_dsc *d, void *arg)
{
    (void)chr; (void)arg;
    const int i = link_of(conn);
    if (i < 0) return 0;
    if (e->status == 0 && ble_uuid_u16(&d->uuid.u) == BLE_GATT_DSC_CLT_CFG_UUID16) {
        static const uint8_t on[2] = {1, 0};
        ble_gattc_write_flat(conn, d->handle, on, sizeof(on), on_subscribed, NULL);
        return BLE_HS_EDONE;
    }
    return 0;
}

static int on_chr(uint16_t conn, const struct ble_gatt_error *e, const struct ble_gatt_chr *c, void *arg)
{
    (void)arg;
    const int i = link_of(conn);
    if (i < 0) return 0;
    if (e->status == 0 && ble_uuid_u16(&c->uuid.u) == DATA_UUID) s_link[i].data_handle = c->val_handle;
    if (e->status == BLE_HS_EDONE && s_link[i].data_handle) {
        ble_gattc_disc_all_dscs(conn, s_link[i].data_handle, s_link[i].end_handle, on_dsc, NULL);
    }
    return 0;
}

static int on_svc(uint16_t conn, const struct ble_gatt_error *e, const struct ble_gatt_svc *s, void *arg)
{
    (void)arg;
    const int i = link_of(conn);
    if (i < 0 || e->status) return 0;
    s_link[i].end_handle = s->end_handle;
    ble_gattc_disc_all_chrs(conn, s->start_handle, s->end_handle, on_chr, NULL);
    return BLE_HS_EDONE;
}

static int on_gap(struct ble_gap_event *ev, void *arg)
{
    const int want = (int)(intptr_t)arg;
    switch (ev->type) {
    case BLE_GAP_EVENT_DISC: {
        struct ble_hs_adv_fields f;
        if (s_connecting || ble_hs_adv_parse_fields(&f, ev->disc.data, ev->disc.length_data)) return 0;
        // Connect B2L-1 first, then B2L-2 while link 1 is running.
        const int next = s_link[0].conn == BLE_HS_CONN_HANDLE_NONE ? 0
                         : (s_link[1].conn == BLE_HS_CONN_HANDLE_NONE && s_link[0].ready ? 1 : -1);
        char name[8] = "B2L-0";
        name[4] = (char)('1' + next);
        if (next < 0 || f.name_len != 5 || memcmp(f.name, name, 5)) return 0;
        ble_gap_disc_cancel();
        const struct ble_gap_conn_params p = {
            .scan_itvl = 0x10, .scan_window = 0x10, .itvl_min = 12, .itvl_max = 12,
            .supervision_timeout = 50,
        };
        printf("B2L: link%d connecting to %s ", next + 1, name);
        print_addr("addr", ev->disc.addr.val);
        printf("\n");
        s_connecting = ble_gap_connect(s_addr_type, &ev->disc.addr, 3000, &p, on_gap,
                                       (void *)(intptr_t)next) == 0;
        if (!s_connecting) scan();
        return 0;
    }
    case BLE_GAP_EVENT_CONNECT:
        s_connecting = false;
        printf("B2L: link%d connect status=%d\n", want + 1, ev->connect.status);
        if (ev->connect.status) {
            scan();
            return 0;
        }
        s_link[want].conn = ev->connect.conn_handle;
        const ble_uuid16_t svc = BLE_UUID16_INIT(SERVICE_UUID);
        ble_gattc_disc_svc_by_uuid(ev->connect.conn_handle, &svc.u, on_svc, NULL);
        return 0;
    case BLE_GAP_EVENT_DISCONNECT: {
        const int i = link_of(ev->disconnect.conn.conn_handle);
        if (i >= 0) {
            printf("B2L: link%d disconnected reason=%d\n", i + 1, ev->disconnect.reason);
            ++s_link[i].drops;
            s_link[i].conn = BLE_HS_CONN_HANDLE_NONE;
            s_link[i].ready = false;
        }
        scan();
        return 0;
    }
    case BLE_GAP_EVENT_NOTIFY_RX: {
        const int i = link_of(ev->notify_rx.conn_handle);
        uint8_t d[8] = {0};
        if (i < 0 || OS_MBUF_PKTLEN(ev->notify_rx.om) != sizeof(d)) return 0;
        os_mbuf_copydata(ev->notify_rx.om, 0, sizeof(d), d);
        uint32_t seq;
        memcpy(&seq, d + 4, 4);
        struct link *l = &s_link[i];
        ++l->count;
        if (d[0] != i + 1) ++l->cross;                     // the other peripheral's data
        if (l->have_seq && (int32_t)(seq - l->last_seq) <= 0) ++l->repeats;
        l->last_seq = seq;
        l->have_seq = true;
        return 0;
    }
    default:
        return 0;
    }
}

static void scan(void)
{
    if (s_connecting || ble_gap_disc_active()) return;
    if (s_link[0].conn != BLE_HS_CONN_HANDLE_NONE && s_link[1].conn != BLE_HS_CONN_HANDLE_NONE) return;
    const struct ble_gap_disc_params p = {.passive = 1, .filter_duplicates = 0};
    ble_gap_disc(s_addr_type, BLE_HS_FOREVER, &p, on_gap, NULL);
}

static void on_sync(void)
{
    ble_hs_util_ensure_addr(0);
    ble_hs_id_infer_auto(0, &s_addr_type);
    uint8_t a[6];
    ble_hs_id_copy_addr(s_addr_type, a, NULL);
    printf("B2L: central ");
    print_addr("addr", a);
    printf("\n");
    scan();
}

static void start_role(void)
{
    const esp_timer_create_args_t t = {.callback = check_done, .name = "b2l"};
    esp_timer_handle_t h;
    esp_timer_create(&t, &h);
    esp_timer_start_periodic(h, 100000);
}

#else
// ------------------------------------------------------------- peripheral

static uint16_t s_data_handle;
static uint16_t s_conn = BLE_HS_CONN_HANDLE_NONE;
static bool s_subscribed;
static uint32_t s_seq;

static int on_access(uint16_t c, uint16_t a, struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    (void)c; (void)a; (void)ctxt; (void)arg;
    return BLE_ATT_ERR_READ_NOT_PERMITTED;
}

static const struct ble_gatt_svc_def s_svcs[] = {
    {.type = BLE_GATT_SVC_TYPE_PRIMARY, .uuid = BLE_UUID16_DECLARE(SERVICE_UUID),
     .characteristics = (struct ble_gatt_chr_def[]){
         {.uuid = BLE_UUID16_DECLARE(DATA_UUID), .access_cb = on_access,
          .val_handle = &s_data_handle, .flags = BLE_GATT_CHR_F_NOTIFY},
         {0}}},
    {0},
};

static void advertise(void);

static int on_gap(struct ble_gap_event *ev, void *arg)
{
    (void)arg;
    switch (ev->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (ev->connect.status == 0) {
            struct ble_gap_conn_desc d;
            s_conn = ev->connect.conn_handle;
            ble_gap_conn_find(s_conn, &d);
            printf("B2L: P%d connected ", PERIPHERAL_ID);
            print_addr("peer", d.peer_id_addr.val);
            printf("\n");
        } else {
            advertise();
        }
        return 0;
    case BLE_GAP_EVENT_DISCONNECT:
        printf("B2L: P%d disconnected reason=%d\n", PERIPHERAL_ID, ev->disconnect.reason);
        s_conn = BLE_HS_CONN_HANDLE_NONE;
        s_subscribed = false;
        advertise();
        return 0;
    case BLE_GAP_EVENT_SUBSCRIBE:
        if (ev->subscribe.attr_handle == s_data_handle) s_subscribed = ev->subscribe.cur_notify;
        return 0;
    default:
        return 0;
    }
}

static void advertise(void)
{
    char name[] = "B2L-0";
    name[4] = (char)('0' + PERIPHERAL_ID);
    struct ble_hs_adv_fields f = {0};
    f.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    f.name = (const uint8_t *)name;
    f.name_len = 5;
    f.name_is_complete = 1;
    ble_gap_adv_set_fields(&f);
    const struct ble_gap_adv_params p = {.conn_mode = BLE_GAP_CONN_MODE_UND, .disc_mode = BLE_GAP_DISC_MODE_GEN};
    ble_gap_adv_start(s_addr_type, NULL, BLE_HS_FOREVER, &p, on_gap, NULL);
}

static void on_tick(void *arg)
{
    (void)arg;
    if (s_conn == BLE_HS_CONN_HANDLE_NONE || !s_subscribed) return;
    uint8_t d[8] = {PERIPHERAL_ID};
    ++s_seq;
    memcpy(d + 4, &s_seq, 4);
    struct os_mbuf *om = ble_hs_mbuf_from_flat(d, sizeof(d));
    if (om) ble_gatts_notify_custom(s_conn, s_data_handle, om);
}

static void on_sync(void)
{
    ble_hs_util_ensure_addr(0);
    ble_hs_id_infer_auto(0, &s_addr_type);
    uint8_t a[6];
    ble_hs_id_copy_addr(s_addr_type, a, NULL);
    printf("B2L: P%d ", PERIPHERAL_ID);
    print_addr("addr", a);
    printf("\n");
    advertise();
}

static void start_role(void)
{
    ble_svc_gap_init();
    ble_svc_gatt_init();
    ble_gatts_count_cfg(s_svcs);
    ble_gatts_add_svcs(s_svcs);
    const esp_timer_create_args_t t = {.callback = on_tick, .name = "notify"};
    esp_timer_handle_t h;
    esp_timer_create(&t, &h);
    esp_timer_start_periodic(h, NOTIFY_PERIOD_US);
}
#endif

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("B2L: boot role=%s\n", ROLE);
    esp_err_t status = nvs_flash_init();
    if (status != ESP_OK) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    if (nimble_port_init() != ESP_OK) {
        printf("RESULT: FAIL nimble_init\n");
        return;
    }
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.reset_cb = on_reset;
    start_role();
    nimble_port_freertos_init(host_task);
}
