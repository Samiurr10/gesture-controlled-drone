// SPDX-License-Identifier: MIT
#include "hub_link.h"

#include <stdio.h>
#include <string.h>

#include "console.h"
#include "hand_core.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "link.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "packet.h"

static const ble_uuid128_t s_service_uuid = LINK_SERVICE_UUID;
static const ble_uuid128_t s_packet_uuid = LINK_PACKET_UUID;
static const ble_uuid128_t s_command_uuid = LINK_COMMAND_UUID;
static const ble_uuid16_t s_cccd_uuid = BLE_UUID16_INIT(BLE_GATT_DSC_CLT_CFG_UUID16);

// One slot per hand, owned by the NimBLE host task (status reads word fields).
struct slot {
    uint16_t conn;
    bool ready;
    uint16_t mtu;
    uint16_t service_end;
    uint16_t packet_handle;
    uint16_t command_handle;
    uint16_t cccd_handle;
    uint32_t notifications, connects, drops;
    uint32_t adverts;            // advertising reports seen for this side
};

static struct slot s_slot[2];
static bool s_connecting;
static uint8_t s_own_addr_type;
static hub_link_packet_fn s_on_packet;
static hub_link_ready_fn s_on_ready;

static void scan(void);

static const char *side_name(int side) { return side == HAND_SIDE_RIGHT ? "right" : "left"; }

static void emit(int side, const char *event, int status)
{
    console_printf("{\"type\":\"link\",\"side\":\"%s\",\"event\":\"%s\",\"status\":%d}\n",
           side_name(side), event, status);
    }

static int slot_of(uint16_t conn)
{
    for (int side = 0; side < 2; ++side) {
        if (s_slot[side].conn == conn) return side;
    }
    return -1;
}

static void slot_reset(int side)
{
    const uint32_t notifications = s_slot[side].notifications;
    const uint32_t connects = s_slot[side].connects, drops = s_slot[side].drops;
    const uint32_t adverts = s_slot[side].adverts;
    memset(&s_slot[side], 0, sizeof(s_slot[side]));
    s_slot[side].conn = BLE_HS_CONN_HANDLE_NONE;
    s_slot[side].notifications = notifications;
    s_slot[side].connects = connects;
    s_slot[side].drops = drops;
    s_slot[side].adverts = adverts;
}

// Any failed setup step drops the peer; the disconnect frees the slot.
static void abandon(int side, const char *step, int status)
{
    emit(side, step, status);
    ble_gap_terminate(s_slot[side].conn, BLE_ERR_REM_USER_CONN_TERM);
}

static int on_subscribed(uint16_t conn, const struct ble_gatt_error *error,
                         struct ble_gatt_attr *attr, void *arg)
{
    (void)attr; (void)arg;
    const int side = slot_of(conn);
    if (side < 0) return 0;
    if (error->status != 0) {
        abandon(side, "subscribe_failed", error->status);
        return 0;
    }
    s_slot[side].ready = true;
    emit(side, "ready", 0);
    if (s_on_ready) s_on_ready(side, true);
    return 0;
}

static int on_descriptor(uint16_t conn, const struct ble_gatt_error *error,
                         uint16_t chr_handle, const struct ble_gatt_dsc *dsc, void *arg)
{
    (void)chr_handle; (void)arg;
    const int side = slot_of(conn);
    if (side < 0) return 0;
    struct slot *slot = &s_slot[side];
    if (error->status == 0) {
        if (!slot->cccd_handle && ble_uuid_cmp(&dsc->uuid.u, &s_cccd_uuid.u) == 0) {
            slot->cccd_handle = dsc->handle;
        }
        return 0;
    }
    if (error->status != BLE_HS_EDONE || !slot->cccd_handle) {
        abandon(side, "no_cccd", error->status);
        return 0;
    }
    static const uint8_t notify_on[2] = {1, 0};
    const int status = ble_gattc_write_flat(conn, slot->cccd_handle, notify_on,
                                            sizeof(notify_on), on_subscribed, NULL);
    if (status != 0) abandon(side, "subscribe_failed", status);
    return 0;
}

static int on_characteristic(uint16_t conn, const struct ble_gatt_error *error,
                             const struct ble_gatt_chr *chr, void *arg)
{
    (void)arg;
    const int side = slot_of(conn);
    if (side < 0) return 0;
    struct slot *slot = &s_slot[side];
    if (error->status == 0) {
        if (ble_uuid_cmp(&chr->uuid.u, &s_packet_uuid.u) == 0) {
            slot->packet_handle = chr->val_handle;
        } else if (ble_uuid_cmp(&chr->uuid.u, &s_command_uuid.u) == 0) {
            slot->command_handle = chr->val_handle;
        }
        return 0;
    }
    if (error->status != BLE_HS_EDONE || !slot->packet_handle || !slot->command_handle) {
        abandon(side, "not_a_palmpilot_hand", error->status);
        return 0;
    }
    const int status = ble_gattc_disc_all_dscs(conn, slot->packet_handle, slot->service_end,
                                               on_descriptor, NULL);
    if (status != 0) abandon(side, "no_cccd", status);
    return 0;
}

static int on_service(uint16_t conn, const struct ble_gatt_error *error,
                      const struct ble_gatt_svc *service, void *arg)
{
    (void)arg;
    const int side = slot_of(conn);
    if (side < 0) return 0;
    if (error->status == 0) {
        s_slot[side].service_end = service->end_handle;
        const int status = ble_gattc_disc_all_chrs(conn, service->start_handle,
                                                   service->end_handle, on_characteristic, NULL);
        if (status != 0) abandon(side, "not_a_palmpilot_hand", status);
        return BLE_HS_EDONE;   // one service is enough; stop this procedure
    }
    if (!s_slot[side].service_end) abandon(side, "not_a_palmpilot_hand", error->status);
    return 0;
}

static int on_mtu(uint16_t conn, const struct ble_gatt_error *error, uint16_t mtu, void *arg)
{
    (void)arg;
    const int side = slot_of(conn);
    if (side < 0) return 0;
    if (error->status != 0 || mtu < HAND_PACKET_SIZE + 3) {
        abandon(side, "mtu_too_small", error->status ? error->status : mtu);
        return 0;
    }
    s_slot[side].mtu = mtu;
    const int status = ble_gattc_disc_svc_by_uuid(conn, &s_service_uuid.u, on_service, NULL);
    if (status != 0) abandon(side, "not_a_palmpilot_hand", status);
    return 0;
}

static int on_gap_event(struct ble_gap_event *event, void *arg);

// Side from the advertised complete name, or -1 for anything else.
static int side_from_advert(const struct ble_gap_disc_desc *disc)
{
    struct ble_hs_adv_fields fields;
    if (ble_hs_adv_parse_fields(&fields, disc->data, disc->length_data) != 0) return -1;
    if (!fields.name || !fields.name_is_complete) return -1;
    if (fields.name_len == strlen(LINK_NAME_LEFT)
            && !memcmp(fields.name, LINK_NAME_LEFT, fields.name_len)) {
        return HAND_SIDE_LEFT;
    }
    if (fields.name_len == strlen(LINK_NAME_RIGHT)
            && !memcmp(fields.name, LINK_NAME_RIGHT, fields.name_len)) {
        return HAND_SIDE_RIGHT;
    }
    return -1;
}

static void connect_to(int side, const ble_addr_t *address)
{
    const int cancel = ble_gap_disc_cancel();
    if (cancel != 0 && ble_gap_disc_active()) {
        emit(side, "scan_cancel_failed", cancel);
        return;
    }
    const struct ble_gap_conn_params params = {
        .scan_itvl = 0x0010,
        .scan_window = 0x0010,
        .itvl_min = LINK_INTERVAL_UNITS,
        .itvl_max = LINK_INTERVAL_UNITS,
        .latency = 0,
        .supervision_timeout = LINK_SUPERVISION_UNITS,
    };
    const int status = ble_gap_connect(s_own_addr_type, address, 2000, &params,
                                       on_gap_event, (void *)(intptr_t)side);
    if (status == 0) {
        s_connecting = true;
        const uint8_t *a = address->val;
        console_printf("{\"type\":\"link\",\"side\":\"%s\",\"event\":\"connecting\",\"status\":0,"
               "\"peer\":\"%02x:%02x:%02x:%02x:%02x:%02x\"}\n", side_name(side),
               a[5], a[4], a[3], a[2], a[1], a[0]);
    } else {
        emit(side, "connect_failed", status);
        scan();
    }
}

static int on_gap_event(struct ble_gap_event *event, void *arg)
{
    switch (event->type) {
    case BLE_GAP_EVENT_DISC: {
        const int side = side_from_advert(&event->disc);
        if (side >= 0) ++s_slot[side].adverts;
        if (side >= 0 && s_slot[side].conn == BLE_HS_CONN_HANDLE_NONE && !s_connecting) {
            connect_to(side, &event->disc.addr);
        }
        return 0;
    }
    case BLE_GAP_EVENT_DISC_COMPLETE:
        if (!s_connecting) scan();
        return 0;
    case BLE_GAP_EVENT_CONNECT: {
        const int side = (int)(intptr_t)arg;
        s_connecting = false;
        if (event->connect.status != 0) {
            emit(side, "connect_failed", event->connect.status);
            scan();
            return 0;
        }
        s_slot[side].conn = event->connect.conn_handle;
        ++s_slot[side].connects;
        emit(side, "connected", 0);
        const int status = ble_gattc_exchange_mtu(event->connect.conn_handle, on_mtu, NULL);
        if (status != 0) abandon(side, "mtu_too_small", status);
        scan();                    // look for the other hand meanwhile
        return 0;
    }
    case BLE_GAP_EVENT_DISCONNECT: {
        const int side = slot_of(event->disconnect.conn.conn_handle);
        if (side < 0) return 0;
        const bool was_ready = s_slot[side].ready;
        ++s_slot[side].drops;
        slot_reset(side);
        emit(side, "disconnected", event->disconnect.reason);
        if (was_ready && s_on_ready) s_on_ready(side, false);
        scan();
        return 0;
    }
    case BLE_GAP_EVENT_NOTIFY_RX: {
        const int side = slot_of(event->notify_rx.conn_handle);
        if (side < 0 || !s_slot[side].ready
                || event->notify_rx.attr_handle != s_slot[side].packet_handle) {
            return 0;
        }
        uint8_t data[HAND_PACKET_SIZE + 1];
        const uint16_t length = OS_MBUF_PKTLEN(event->notify_rx.om);
        // Oversized: pass one byte too many so the decoder rejects it on length.
        const uint16_t copy = length < sizeof(data) ? length : sizeof(data);
        os_mbuf_copydata(event->notify_rx.om, 0, copy, data);
        ++s_slot[side].notifications;
        if (s_on_packet) s_on_packet(side, data, copy);
        return 0;
    }
    default:
        return 0;
    }
}

static void scan(void)
{
    if (s_connecting || ble_gap_disc_active()) return;
    if (s_slot[HAND_SIDE_LEFT].conn != BLE_HS_CONN_HANDLE_NONE
            && s_slot[HAND_SIDE_RIGHT].conn != BLE_HS_CONN_HANDLE_NONE) {
        return;                    // both linked: nothing to look for
    }
    // Passive is enough: the name is in the advertisement.
    const struct ble_gap_disc_params params = {
        .passive = 1,
        .filter_duplicates = 0,
    };
    const int status = ble_gap_disc(s_own_addr_type, BLE_HS_FOREVER, &params,
                                    on_gap_event, NULL);
    if (status != 0) {
        console_printf("{\"type\":\"link\",\"event\":\"scan_failed\",\"status\":%d}\n", status);
    }
}

static void on_sync(void)
{
    ble_hs_util_ensure_addr(0);
    ble_hs_id_infer_auto(0, &s_own_addr_type);
    scan();
}

static void on_reset(int reason)
{
    console_printf("{\"type\":\"link\",\"event\":\"host_reset\",\"status\":%d}\n", reason);
}

static void host_task(void *param)
{
    (void)param;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

esp_err_t hub_link_start(hub_link_packet_fn on_packet, hub_link_ready_fn on_ready)
{
    s_on_packet = on_packet;
    s_on_ready = on_ready;
    slot_reset(HAND_SIDE_LEFT);
    slot_reset(HAND_SIDE_RIGHT);
    esp_err_t status = nimble_port_init();
    if (status != ESP_OK) return status;
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.reset_cb = on_reset;
    if (ble_att_set_preferred_mtu(LINK_MTU) != 0) return ESP_FAIL;
    nimble_port_freertos_init(host_task);
    return ESP_OK;
}

esp_err_t hub_link_send(int side, uint8_t opcode)
{
    if (side != HAND_SIDE_LEFT && side != HAND_SIDE_RIGHT) return ESP_ERR_INVALID_ARG;
    const struct slot *slot = &s_slot[side];
    if (!slot->ready) return ESP_ERR_INVALID_STATE;
    return ble_gattc_write_flat(slot->conn, slot->command_handle, &opcode, 1, NULL, NULL) == 0
               ? ESP_OK : ESP_FAIL;
}

void hub_link_get_status(int side, struct hub_link_status *out)
{
    const struct slot *slot = &s_slot[side];
    out->connected = slot->conn != BLE_HS_CONN_HANDLE_NONE;
    out->ready = slot->ready;
    out->mtu = slot->mtu;
    out->notifications = slot->notifications;
    out->connects = slot->connects;
    out->drops = slot->drops;
    out->adverts = slot->adverts;
}
