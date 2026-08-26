#include "bsp/esp-bsp.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_random.h"
#include "flow_ble.h"
#include "flow_core.h"
#include "flow_power.h"
#include "flow_protocol.h"
#include "flow_simulator.h"
#include "flow_ui.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "lvgl.h"
#include "nvs_flash.h"

#include <string.h>

static QueueHandle_t s_render_queue;
static QueueHandle_t s_action_queue;
static QueueHandle_t s_snapshot_queue;
static QueueHandle_t s_connection_queue;
static flow_app_state_t s_app_state;
static uint32_t s_next_command_id;
static bool s_touch_was_pressed;
static const char *const TAG = "flow_app";

static void publish_state(void)
{
    flow_power_set_transition_active(s_app_state.screen == FLOW_SCREEN_TRANSITION);
    xQueueOverwrite(s_render_queue, &s_app_state);
}

static void ui_action_handler(const flow_ui_action_t *action, void *context)
{
    (void)context;
    ESP_LOGI(TAG, "UI action: %d", (int)action->type);
    flow_power_note_activity();
    xQueueSend(s_action_queue, action, 0);
}

static void battery_handler(uint8_t percentage, void *context)
{
    (void)context;
    flow_ble_set_battery(percentage);
}

static void snapshot_handler(const flow_snapshot_t *snapshot, void *context)
{
    (void)context;
    xQueueSend(s_snapshot_queue, snapshot, 0);
}

#if !CONFIG_FLOW_SIMULATOR
static void connection_handler(bool connected, void *context)
{
    (void)context;
    xQueueSend(s_connection_queue, &connected, 0);
}
#endif

static void render_timer_cb(lv_timer_t *timer)
{
    (void)timer;
    bool touch_pressed = false;
    for (lv_indev_t *input = lv_indev_get_next(NULL);
         input != NULL;
         input = lv_indev_get_next(input)) {
        if (lv_indev_get_state(input) == LV_INDEV_STATE_PRESSED) {
            touch_pressed = true;
            if (!s_touch_was_pressed) {
                lv_point_t point;
                lv_indev_get_point(input, &point);
                ESP_LOGI(TAG, "Touch pressed at (%ld, %ld)",
                         (long)point.x,
                         (long)point.y);
            }
            flow_power_note_activity();
            break;
        }
    }
    s_touch_was_pressed = touch_pressed;
    flow_app_state_t latest;
    if (xQueueReceive(s_render_queue, &latest, 0) == pdTRUE) {
        flow_ui_render(&latest);
    }
}

static void app_task(void *context)
{
    (void)context;
    flow_ui_action_t action;
    while (true) {
        bool connected;
        while (xQueueReceive(s_connection_queue, &connected, 0) == pdTRUE) {
            if (!connected) {
                s_app_state.screen = FLOW_SCREEN_CONNECTING;
                publish_state();
            }
        }

        flow_snapshot_t snapshot;
        while (xQueueReceive(s_snapshot_queue, &snapshot, 0) == pdTRUE) {
            if (flow_state_apply_snapshot(&s_app_state, &snapshot) == FLOW_APPLY_OK) {
                publish_state();
            }
        }

        if (xQueueReceive(s_action_queue, &action, pdMS_TO_TICKS(20)) != pdTRUE) {
            continue;
        }

        switch (action.type) {
        case FLOW_UI_ACTION_OPEN_ENERGY:
            flow_state_open_control(&s_app_state, FLOW_SCREEN_ENERGY);
            break;
        case FLOW_UI_ACTION_OPEN_STYLE:
            flow_state_open_control(&s_app_state, FLOW_SCREEN_STYLE);
            break;
        case FLOW_UI_ACTION_BACK:
        case FLOW_UI_ACTION_COMPLETE_TIMEOUT:
            flow_state_return_home(&s_app_state);
            break;
        case FLOW_UI_ACTION_SET_ENERGY:
        case FLOW_UI_ACTION_SET_STYLE: {
            flow_command_t command = {
                .version = 1,
                .id = s_next_command_id,
                .operation = action.type == FLOW_UI_ACTION_SET_ENERGY
                    ? FLOW_OPERATION_SET_ENERGY
                    : FLOW_OPERATION_SET_STYLE,
                .energy = action.energy,
            };
            memcpy(command.style, action.style, sizeof(command.style));
            if (flow_state_begin_command(&s_app_state, command.id) == FLOW_COMMAND_STARTED) {
                ++s_next_command_id;
                if (s_next_command_id == 0) {
                    s_next_command_id = 1;
                }
#if CONFIG_FLOW_SIMULATOR
                if (flow_simulator_submit(&command) != ESP_OK) {
                    s_app_state.screen = FLOW_SCREEN_ERROR;
                    strcpy(s_app_state.snapshot.error, "internal_error");
                }
#else
                if (flow_ble_send_command(&command) != ESP_OK) {
                    s_app_state.screen = FLOW_SCREEN_ERROR;
                    strcpy(s_app_state.snapshot.error, "transport_error");
                }
#endif
            }
            break;
        }
        }
        publish_state();
    }
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    s_render_queue = xQueueCreate(1, sizeof(flow_app_state_t));
    s_action_queue = xQueueCreate(8, sizeof(flow_ui_action_t));
    s_snapshot_queue = xQueueCreate(8, sizeof(flow_snapshot_t));
    s_connection_queue = xQueueCreate(2, sizeof(bool));
    ESP_ERROR_CHECK((s_render_queue != NULL && s_action_queue != NULL &&
                     s_snapshot_queue != NULL && s_connection_queue != NULL)
                        ? ESP_OK
                        : ESP_ERR_NO_MEM);
    flow_state_init(&s_app_state);
    s_next_command_id = esp_random();
    if (s_next_command_id == 0) {
        s_next_command_id = 1;
    }

    lv_display_t *display = bsp_display_start();
    ESP_ERROR_CHECK(display == NULL ? ESP_FAIL : ESP_OK);
    ESP_LOGI(TAG, "Display and touch initialized");
    ESP_ERROR_CHECK(bsp_display_lock(0) ? ESP_OK : ESP_FAIL);
    flow_ui_init(ui_action_handler, NULL);
    flow_ui_render(&s_app_state);
    lv_obj_update_layout(lv_screen_active());
    lv_obj_invalidate(lv_screen_active());
    lv_refr_now(display);
    lv_timer_create(render_timer_cb, 30, NULL);
    bsp_display_unlock();
    ESP_LOGI(TAG, "Initial UI rendered");
    ESP_ERROR_CHECK(flow_power_init(battery_handler, NULL));
    ESP_LOGI(TAG, "Power service initialized");

    ESP_ERROR_CHECK(xTaskCreate(app_task, "flow_app", 4096, NULL, 5, NULL) == pdPASS
                        ? ESP_OK
                        : ESP_ERR_NO_MEM);
#if CONFIG_FLOW_SIMULATOR
    ESP_ERROR_CHECK(flow_simulator_start(snapshot_handler, NULL));
    ESP_LOGI(TAG, "Hub simulator started");
#else
    ESP_ERROR_CHECK(flow_ble_init(snapshot_handler, connection_handler, NULL));
    ESP_LOGI(TAG, "BLE service started");
#endif
}
