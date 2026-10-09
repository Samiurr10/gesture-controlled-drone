// SPDX-License-Identifier: MIT
#include "hand_link.h"

#include <stdio.h>
#include <string.h>

#include "console.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "link.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "packet.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

static const ble_uuid128_t s_service_uuid = LINK_SERVICE_UUID;
static const ble_uuid128_t s_packet_uuid = LINK_PACKET_UUID;
static const ble_uuid128_t s_command_uuid = LINK_COMMAND_UUID;

static const char *s_name;
static hand_link_command_fn s_on_command;
static uint8_t s_own_addr_type;
static uint16_t s_packet_handle;

// Written by the host task, read by the control task: word-sized fields only.
static volatile uint16_t s_conn = BLE_HS_CONN_HANDLE_NONE;
static volatile bool s_subscribed;
static volatile uint16_t s_mtu;
static volatile uint32_t s_sent, s_skipped, s_connects;

// The last published packet, served to a GATT read.
static uint8_t s_latest[HAND_PACKET_SIZE];
static portMUX_TYPE s_latest_lock = portMUX_INITIALIZER_UNLOCKED;

static void advertise(void);

static int access_packet(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt,
                         void *arg)
{
    (void)conn; (void)attr; (void)arg;
    if (ctxt->op != BLE_GATT_ACCESS_OP_READ_CHR) return BLE_ATT_ERR_UNLIKELY;
    uint8_t copy[HAND_PACKET_SIZE];
    portENTER_CRITICAL(&s_latest_lock);
    memcpy(copy, s_latest, sizeof(copy));
    portEXIT_CRITICAL(&s_latest_lock);
    return os_mbuf_append(ctxt->om, copy, sizeof(copy)) == 0 ? 0
                                                             : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int access_command(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt,
                          void *arg)
{
    (void)conn; (void)attr; (void)arg;
    if (ctxt->op != BLE_GATT_ACCESS_OP_WRITE_CHR) return BLE_ATT_ERR_UNLIKELY;
    if (OS_MBUF_PKTLEN(ctxt->om) != 1) return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
    uint8_t opcode = 0;
    os_mbuf_copydata(ctxt->om, 0, 1, &opcode);
    if (s_on_command) s_on_command(opcode);
    return 0;
}

static const struct ble_gatt_svc_def s_services[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &s_service_uuid.u,
        .characteristics = (struct ble_gatt_chr_def[]){
            {
                .uuid = &s_packet_uuid.u,
                .access_cb = access_packet,
                .val_handle = &s_packet_handle,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
            },
            {
                .uuid = &s_command_uuid.u,
                .access_cb = access_command,
                .flags = BLE_GATT_CHR_F_WRITE,
            },
            {0},
        },
    },
    {0},
};

static void emit_link(const char *event, int status)
{
    uint8_t addr[6] = {0};
    ble_hs_id_copy_addr(s_own_addr_type, addr, NULL);
    console_printf("{\"type\":\"link\",\"event\":\"%s\",\"status\":%d,\"mtu\":%u,"
           "\"addr\":\"%02x:%02x:%02x:%02x:%02x:%02x\"}\n", event, status, (unsigned)s_mtu,
           addr[5], addr[4], addr[3], addr[2], addr[1], addr[0]);
}

static int on_gap_event(struct ble_gap_event *event, void *arg)
{
    (void)arg;
    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (event->connect.status == 0) {
            s_conn = event->connect.conn_handle;
            s_mtu = BLE_ATT_MTU_DFLT;
            ++s_connects;
            emit_link("connected", 0);
        } else {
            emit_link("connect_failed", event->connect.status);
            advertise();
        }
        return 0;
    case BLE_GAP_EVENT_DISCONNECT:
        s_conn = BLE_HS_CONN_HANDLE_NONE;
        s_subscribed = false;
        emit_link("disconnected", event->disconnect.reason);
        advertise();
        return 0;
    case BLE_GAP_EVENT_MTU:
        s_mtu = event->mtu.value;
        emit_link("mtu", 0);
        return 0;
    case BLE_GAP_EVENT_SUBSCRIBE:
        if (event->subscribe.attr_handle == s_packet_handle) {
            s_subscribed = event->subscribe.cur_notify;
            emit_link(s_subscribed ? "subscribed" : "unsubscribed", 0);
        }
        return 0;
    case BLE_GAP_EVENT_ADV_COMPLETE:
        advertise();
        return 0;
    default:
        return 0;
    }
}

static void advertise(void)
{
    // Name and 128-bit UUID don't both fit in 31 bytes: the name (which the
    // hub filters on) is advertised, the UUID goes in the scan response.
    struct ble_hs_adv_fields fields = {0};
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name = (const uint8_t *)s_name;
    fields.name_len = strlen(s_name);
    fields.name_is_complete = 1;
    int status = ble_gap_adv_set_fields(&fields);
    if (status == 0) {
        struct ble_hs_adv_fields response = {0};
        response.uuids128 = &s_service_uuid;
        response.num_uuids128 = 1;
        response.uuids128_is_complete = 1;
        status = ble_gap_adv_rsp_set_fields(&response);
    }
    if (status == 0) {
        struct ble_gap_adv_params params = {
            .conn_mode = BLE_GAP_CONN_MODE_UND,
            .disc_mode = BLE_GAP_DISC_MODE_GEN,
        };
        status = ble_gap_adv_start(s_own_addr_type, NULL, BLE_HS_FOREVER, &params,
                                   on_gap_event, NULL);
    }
    emit_link("advertising", status);
}

static void on_sync(void)
{
    ble_hs_util_ensure_addr(0);
    ble_hs_id_infer_auto(0, &s_own_addr_type);
    advertise();
}

static void on_reset(int reason)
{
    emit_link("host_reset", reason);
}

static void host_task(void *param)
{
    (void)param;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

esp_err_t hand_link_start(enum hand_side side, hand_link_command_fn on_command)
{
    s_name = side == HAND_SIDE_RIGHT ? LINK_NAME_RIGHT : LINK_NAME_LEFT;
    s_on_command = on_command;
    esp_err_t status = nimble_port_init();
    if (status != ESP_OK) return status;

    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.reset_cb = on_reset;
    ble_svc_gap_init();
    ble_svc_gatt_init();
    if (ble_gatts_count_cfg(s_services) != 0 || ble_gatts_add_svcs(s_services) != 0
            || ble_svc_gap_device_name_set(s_name) != 0) {
        return ESP_FAIL;
    }
    nimble_port_freertos_init(host_task);
    return ESP_OK;
}

void hand_link_publish(const uint8_t *packet, size_t length)
{
    if (length != HAND_PACKET_SIZE) return;
    portENTER_CRITICAL(&s_latest_lock);
    memcpy(s_latest, packet, HAND_PACKET_SIZE);
    portEXIT_CRITICAL(&s_latest_lock);

    const uint16_t conn = s_conn;
    if (conn == BLE_HS_CONN_HANDLE_NONE || !s_subscribed
            || s_mtu < HAND_PACKET_SIZE + 3) {
        ++s_skipped;
        return;
    }
    struct os_mbuf *om = ble_hs_mbuf_from_flat(packet, HAND_PACKET_SIZE);
    if (om && ble_gatts_notify_custom(conn, s_packet_handle, om) == 0) {
        ++s_sent;
    } else {
        ++s_skipped;      // notify_custom frees the mbuf on failure
    }
}

void hand_link_get_status(struct hand_link_status *out)
{
    out->connected = s_conn != BLE_HS_CONN_HANDLE_NONE;
    out->subscribed = s_subscribed;
    out->mtu = s_mtu;
    out->sent = s_sent;
    out->skipped = s_skipped;
    out->connects = s_connects;
}
