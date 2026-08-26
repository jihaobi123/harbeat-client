#include "bsp/esp-bsp.h"
#include "esp_err.h"
#include "flow_core.h"
#include "flow_ui.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "lvgl.h"
#include "nvs_flash.h"

static QueueHandle_t s_render_queue;
static QueueHandle_t s_action_queue;
static flow_app_state_t s_app_state;
static uint32_t s_next_command_id = 1;

static void publish_state(void)
{
    xQueueOverwrite(s_render_queue, &s_app_state);
}

static void ui_action_handler(const flow_ui_action_t *action, void *context)
{
    (void)context;
    xQueueSend(s_action_queue, action, 0);
}

static void render_timer_cb(lv_timer_t *timer)
{
    (void)timer;
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
        if (xQueueReceive(s_action_queue, &action, portMAX_DELAY) != pdTRUE) {
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
        case FLOW_UI_ACTION_SET_STYLE:
            flow_state_begin_command(&s_app_state, s_next_command_id++);
            break;
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
    ESP_ERROR_CHECK((s_render_queue != NULL && s_action_queue != NULL)
                        ? ESP_OK
                        : ESP_ERR_NO_MEM);
    flow_state_init(&s_app_state);

    lv_display_t *display = bsp_display_start();
    ESP_ERROR_CHECK(display == NULL ? ESP_FAIL : ESP_OK);
    ESP_ERROR_CHECK(bsp_display_lock(0) ? ESP_OK : ESP_FAIL);
    flow_ui_init(ui_action_handler, NULL);
    flow_ui_render(&s_app_state);
    lv_timer_create(render_timer_cb, 30, NULL);
    bsp_display_unlock();

    xTaskCreate(app_task, "flow_app", 4096, NULL, 5, NULL);
}
