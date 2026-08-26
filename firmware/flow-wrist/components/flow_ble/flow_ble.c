#include "flow_ble.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/timers.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#include "store/config/ble_store_config.h"

void ble_store_config_init(void);

#define FLOW_STATE_MAX_BYTES 512
#define FLOW_CATALOG_MAX_BYTES 512
#define FLOW_COMMAND_MAX_BYTES 192
#define FLOW_INDICATION_TIMEOUT_MS 2000

enum flow_attribute {
    FLOW_ATTR_STATE = 1,
    FLOW_ATTR_CATALOG,
    FLOW_ATTR_BATTERY,
    FLOW_ATTR_MANUFACTURER,
    FLOW_ATTR_MODEL,
    FLOW_ATTR_FIRMWARE,
};

static const char *const TAG = "flow_ble";
static const ble_uuid128_t s_service_uuid = BLE_UUID128_INIT(
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x81,
    0x57, 0x4f, 0x01, 0x00, 0x57, 0x4f, 0x4c, 0x46);
static const ble_uuid128_t s_command_uuid = BLE_UUID128_INIT(
    0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x81,
    0x57, 0x4f, 0x01, 0x00, 0x57, 0x4f, 0x4c, 0x46);
static const ble_uuid128_t s_state_uuid = BLE_UUID128_INIT(
    0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x81,
    0x57, 0x4f, 0x01, 0x00, 0x57, 0x4f, 0x4c, 0x46);
static const ble_uuid128_t s_catalog_uuid = BLE_UUID128_INIT(
    0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x81,
    0x57, 0x4f, 0x01, 0x00, 0x57, 0x4f, 0x4c, 0x46);

static uint8_t s_own_addr_type;
static uint16_t s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
static uint16_t s_command_handle;
static uint16_t s_battery_handle;
static uint8_t s_battery_percentage = 100;
static bool s_command_subscribed;
static bool s_indication_outstanding;
static bool s_catalog_received;
static bool s_state_received;
static uint8_t s_state_raw[FLOW_STATE_MAX_BYTES];
static uint16_t s_state_size;
static uint8_t s_catalog_raw[FLOW_CATALOG_MAX_BYTES];
static uint16_t s_catalog_size;
static flow_snapshot_t s_pending_snapshot;
static flow_ble_snapshot_handler_t s_snapshot_handler;
static flow_ble_connection_handler_t s_connection_handler;
static void *s_handler_context;
static TimerHandle_t s_indication_timer;
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;

static int gap_event(struct ble_gap_event *event, void *arg);

static bool ready_unlocked(void)
{
    return s_conn_handle != BLE_HS_CONN_HANDLE_NONE &&
           s_command_subscribed && s_catalog_received && s_state_received;
}

static void deliver_snapshot_if_ready(void)
{
    flow_ble_snapshot_handler_t handler = NULL;
    flow_snapshot_t snapshot;
    void *context = NULL;
    portENTER_CRITICAL(&s_lock);
    if (ready_unlocked() && s_snapshot_handler != NULL) {
        handler = s_snapshot_handler;
        snapshot = s_pending_snapshot;
        context = s_handler_context;
    }
    portEXIT_CRITICAL(&s_lock);
    if (handler != NULL) {
        handler(&snapshot, context);
    }
}

static int append_bytes(struct os_mbuf *om, const void *data, size_t size)
{
    return os_mbuf_append(om, data, size) == 0
        ? 0
        : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int access_characteristic(uint16_t conn_handle,
                                 uint16_t attr_handle,
                                 struct ble_gatt_access_ctxt *ctxt,
                                 void *arg)
{
    (void)conn_handle;
    (void)attr_handle;
    enum flow_attribute attribute = (enum flow_attribute)(intptr_t)arg;

    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        switch (attribute) {
        case FLOW_ATTR_STATE:
            return append_bytes(ctxt->om, s_state_raw, s_state_size);
        case FLOW_ATTR_CATALOG:
            return append_bytes(ctxt->om, s_catalog_raw, s_catalog_size);
        case FLOW_ATTR_BATTERY:
            return append_bytes(ctxt->om, &s_battery_percentage, 1);
        case FLOW_ATTR_MANUFACTURER:
            return append_bytes(ctxt->om, "Flow Wear", strlen("Flow Wear"));
        case FLOW_ATTR_MODEL:
            return append_bytes(ctxt->om, "Flow Wrist V0.1", strlen("Flow Wrist V0.1"));
        case FLOW_ATTR_FIRMWARE:
            return append_bytes(ctxt->om, "0.1.0", strlen("0.1.0"));
        }
    }

    if (ctxt->op != BLE_GATT_ACCESS_OP_WRITE_CHR ||
        (attribute != FLOW_ATTR_STATE && attribute != FLOW_ATTR_CATALOG)) {
        return BLE_ATT_ERR_UNLIKELY;
    }

    uint16_t length = OS_MBUF_PKTLEN(ctxt->om);
    if (length == 0 || length > FLOW_STATE_MAX_BYTES) {
        return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
    }
    uint8_t incoming[FLOW_STATE_MAX_BYTES];
    uint16_t copied = 0;
    if (ble_hs_mbuf_to_flat(ctxt->om, incoming, sizeof(incoming), &copied) != 0 ||
        copied != length) {
        return BLE_ATT_ERR_UNLIKELY;
    }

    if (attribute == FLOW_ATTR_CATALOG) {
        if (!flow_protocol_validate_catalog(incoming, copied)) {
            ESP_LOGW(TAG, "Rejected invalid Catalog (%u bytes)", copied);
            return BLE_ATT_ERR_VALUE_NOT_ALLOWED;
        }
        portENTER_CRITICAL(&s_lock);
        memcpy(s_catalog_raw, incoming, copied);
        s_catalog_size = copied;
        s_catalog_received = true;
        portEXIT_CRITICAL(&s_lock);
        ESP_LOGI(TAG, "Catalog synchronized");
    } else {
        flow_snapshot_t snapshot;
        if (flow_protocol_decode_snapshot(incoming, copied, &snapshot) != 0) {
            ESP_LOGW(TAG, "Rejected invalid Hub State (%u bytes)", copied);
            return BLE_ATT_ERR_VALUE_NOT_ALLOWED;
        }
        portENTER_CRITICAL(&s_lock);
        memcpy(s_state_raw, incoming, copied);
        s_state_size = copied;
        s_pending_snapshot = snapshot;
        s_state_received = true;
        portEXIT_CRITICAL(&s_lock);
    }
    deliver_snapshot_if_ready();
    return 0;
}

static const struct ble_gatt_svc_def s_services[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &s_service_uuid.u,
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = &s_command_uuid.u,
                .flags = BLE_GATT_CHR_F_INDICATE,
                .val_handle = &s_command_handle,
            },
            {
                .uuid = &s_state_uuid.u,
                .access_cb = access_characteristic,
                .arg = (void *)(intptr_t)FLOW_ATTR_STATE,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_WRITE |
                         BLE_GATT_CHR_F_READ_ENC | BLE_GATT_CHR_F_WRITE_ENC,
            },
            {
                .uuid = &s_catalog_uuid.u,
                .access_cb = access_characteristic,
                .arg = (void *)(intptr_t)FLOW_ATTR_CATALOG,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_WRITE |
                         BLE_GATT_CHR_F_READ_ENC | BLE_GATT_CHR_F_WRITE_ENC,
            },
            {0},
        },
    },
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(0x180f),
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = BLE_UUID16_DECLARE(0x2a19),
                .access_cb = access_characteristic,
                .arg = (void *)(intptr_t)FLOW_ATTR_BATTERY,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
                .val_handle = &s_battery_handle,
            },
            {0},
        },
    },
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(0x180a),
        .characteristics = (struct ble_gatt_chr_def[]) {
            {
                .uuid = BLE_UUID16_DECLARE(0x2a29),
                .access_cb = access_characteristic,
                .arg = (void *)(intptr_t)FLOW_ATTR_MANUFACTURER,
                .flags = BLE_GATT_CHR_F_READ,
            },
            {
                .uuid = BLE_UUID16_DECLARE(0x2a24),
                .access_cb = access_characteristic,
                .arg = (void *)(intptr_t)FLOW_ATTR_MODEL,
                .flags = BLE_GATT_CHR_F_READ,
            },
            {
                .uuid = BLE_UUID16_DECLARE(0x2a26),
                .access_cb = access_characteristic,
                .arg = (void *)(intptr_t)FLOW_ATTR_FIRMWARE,
                .flags = BLE_GATT_CHR_F_READ,
            },
            {0},
        },
    },
    {0},
};

static void advertise(void)
{
    struct ble_hs_adv_fields fields = {0};
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.uuids128 = (ble_uuid128_t *)&s_service_uuid;
    fields.num_uuids128 = 1;
    fields.uuids128_is_complete = 1;
    int rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) {
        ESP_LOGE(TAG, "Advertisement fields failed: %d", rc);
        return;
    }

    const char *name = ble_svc_gap_device_name();
    struct ble_hs_adv_fields response = {0};
    response.name = (uint8_t *)name;
    response.name_len = strlen(name);
    response.name_is_complete = 1;
    rc = ble_gap_adv_rsp_set_fields(&response);
    if (rc != 0) {
        ESP_LOGE(TAG, "Scan response failed: %d", rc);
        return;
    }

    struct ble_gap_adv_params params = {0};
    params.conn_mode = BLE_GAP_CONN_MODE_UND;
    params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    rc = ble_gap_adv_start(s_own_addr_type, NULL, BLE_HS_FOREVER,
                           &params, gap_event, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "Advertising failed: %d", rc);
    }
}

static void on_sync(void)
{
    int rc = ble_hs_util_ensure_addr(0);
    if (rc != 0 || ble_hs_id_infer_auto(0, &s_own_addr_type) != 0) {
        ESP_LOGE(TAG, "No BLE identity address");
        return;
    }

    uint8_t address[6] = {0};
    if (ble_hs_id_copy_addr(s_own_addr_type, address, NULL) != 0) {
        ESP_LOGE(TAG, "Could not read BLE address");
        return;
    }
    char name[20];
    snprintf(name, sizeof(name), "FLOW-WRIST-%02X%02X", address[1], address[0]);
    if (ble_svc_gap_device_name_set(name) != 0) {
        ESP_LOGE(TAG, "Could not set device name");
        return;
    }
    ESP_LOGI(TAG, "Advertising as %s", name);
    advertise();
}

static void on_reset(int reason)
{
    ESP_LOGE(TAG, "NimBLE reset: %d", reason);
}

static void indication_timeout(TimerHandle_t timer)
{
    (void)timer;
    portENTER_CRITICAL(&s_lock);
    s_indication_outstanding = false;
    portEXIT_CRITICAL(&s_lock);
    ESP_LOGW(TAG, "Command indication timed out; no automatic retry");
}

static void reset_connection_state(void)
{
    portENTER_CRITICAL(&s_lock);
    s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
    s_command_subscribed = false;
    s_indication_outstanding = false;
    s_catalog_received = false;
    s_state_received = false;
    s_catalog_size = 0;
    s_state_size = 0;
    portEXIT_CRITICAL(&s_lock);
    if (s_indication_timer != NULL) {
        xTimerStop(s_indication_timer, 0);
    }
}

static int gap_event(struct ble_gap_event *event, void *arg)
{
    (void)arg;
    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (event->connect.status != 0) {
            advertise();
            return 0;
        }
        portENTER_CRITICAL(&s_lock);
        s_conn_handle = event->connect.conn_handle;
        portEXIT_CRITICAL(&s_lock);
        ESP_LOGI(TAG, "Hub connected; requesting secure pairing");
        (void)ble_gap_security_initiate(event->connect.conn_handle);
        if (s_connection_handler != NULL) {
            s_connection_handler(true, s_handler_context);
        }
        return 0;

    case BLE_GAP_EVENT_DISCONNECT:
        ESP_LOGW(TAG, "Hub disconnected: %d", event->disconnect.reason);
        reset_connection_state();
        if (s_connection_handler != NULL) {
            s_connection_handler(false, s_handler_context);
        }
        advertise();
        return 0;

    case BLE_GAP_EVENT_ADV_COMPLETE:
        advertise();
        return 0;

    case BLE_GAP_EVENT_SUBSCRIBE:
        if (event->subscribe.attr_handle == s_command_handle) {
            portENTER_CRITICAL(&s_lock);
            s_command_subscribed = event->subscribe.cur_indicate;
            portEXIT_CRITICAL(&s_lock);
            ESP_LOGI(TAG, "Command indication %s",
                     event->subscribe.cur_indicate ? "subscribed" : "unsubscribed");
            deliver_snapshot_if_ready();
        }
        return 0;

    case BLE_GAP_EVENT_NOTIFY_TX:
        if (event->notify_tx.attr_handle == s_command_handle &&
            event->notify_tx.indication) {
            portENTER_CRITICAL(&s_lock);
            s_indication_outstanding = false;
            portEXIT_CRITICAL(&s_lock);
            xTimerStop(s_indication_timer, 0);
            ESP_LOGI(TAG, "Command indication link ack: %d", event->notify_tx.status);
        }
        return 0;

    case BLE_GAP_EVENT_MTU:
        ESP_LOGI(TAG, "ATT MTU %u", event->mtu.value);
        return 0;

    default:
        return 0;
    }
}

static void host_task(void *context)
{
    (void)context;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

esp_err_t flow_ble_init(flow_ble_snapshot_handler_t snapshot_handler,
                        flow_ble_connection_handler_t connection_handler,
                        void *context)
{
    if (snapshot_handler == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    s_snapshot_handler = snapshot_handler;
    s_connection_handler = connection_handler;
    s_handler_context = context;
    reset_connection_state();

    s_indication_timer = xTimerCreate("flow_indicate", pdMS_TO_TICKS(FLOW_INDICATION_TIMEOUT_MS),
                                      pdFALSE, NULL, indication_timeout);
    if (s_indication_timer == NULL) {
        return ESP_ERR_NO_MEM;
    }

    esp_err_t error = nimble_port_init();
    if (error != ESP_OK) {
        return error;
    }
    ble_hs_cfg.reset_cb = on_reset;
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;
    ble_hs_cfg.sm_io_cap = BLE_HS_IO_NO_INPUT_OUTPUT;
    ble_hs_cfg.sm_bonding = 1;
    ble_hs_cfg.sm_mitm = 0;
    ble_hs_cfg.sm_sc = 1;
    ble_hs_cfg.sm_our_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;
    ble_hs_cfg.sm_their_key_dist = BLE_SM_PAIR_KEY_DIST_ENC | BLE_SM_PAIR_KEY_DIST_ID;

    ble_svc_gap_init();
    ble_svc_gatt_init();
    int rc = ble_gatts_count_cfg(s_services);
    if (rc == 0) {
        rc = ble_gatts_add_svcs(s_services);
    }
    if (rc != 0) {
        ESP_LOGE(TAG, "GATT registration failed: %d", rc);
        return ESP_FAIL;
    }

    ble_store_config_init();
    nimble_port_freertos_init(host_task);
    return ESP_OK;
}

esp_err_t flow_ble_send_command(const flow_command_t *command)
{
    uint8_t payload[FLOW_COMMAND_MAX_BYTES];
    size_t payload_size = 0;
    if (flow_protocol_encode_command(command, payload, sizeof(payload), &payload_size) != 0) {
        return ESP_ERR_INVALID_ARG;
    }

    uint16_t conn_handle;
    portENTER_CRITICAL(&s_lock);
    if (!ready_unlocked() || s_indication_outstanding) {
        portEXIT_CRITICAL(&s_lock);
        return ESP_ERR_INVALID_STATE;
    }
    s_indication_outstanding = true;
    conn_handle = s_conn_handle;
    portEXIT_CRITICAL(&s_lock);

    struct os_mbuf *om = ble_hs_mbuf_from_flat(payload, payload_size);
    if (om == NULL) {
        portENTER_CRITICAL(&s_lock);
        s_indication_outstanding = false;
        portEXIT_CRITICAL(&s_lock);
        return ESP_ERR_NO_MEM;
    }
    int rc = ble_gatts_indicate_custom(conn_handle, s_command_handle, om);
    if (rc != 0) {
        os_mbuf_free_chain(om);
        portENTER_CRITICAL(&s_lock);
        s_indication_outstanding = false;
        portEXIT_CRITICAL(&s_lock);
        ESP_LOGW(TAG, "Command indication failed: %d", rc);
        return ESP_FAIL;
    }
    xTimerStart(s_indication_timer, 0);
    return ESP_OK;
}

bool flow_ble_is_connected(void)
{
    portENTER_CRITICAL(&s_lock);
    bool connected = s_conn_handle != BLE_HS_CONN_HANDLE_NONE;
    portEXIT_CRITICAL(&s_lock);
    return connected;
}

bool flow_ble_is_ready(void)
{
    portENTER_CRITICAL(&s_lock);
    bool ready = ready_unlocked();
    portEXIT_CRITICAL(&s_lock);
    return ready;
}

void flow_ble_set_battery(uint8_t percentage)
{
    if (percentage > 100) {
        percentage = 100;
    }
    s_battery_percentage = percentage;
    if (s_battery_handle != 0) {
        ble_gatts_chr_updated(s_battery_handle);
    }
}
