#include "flow_power.h"

#include "bsp/esp-bsp.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "flow_power_policy.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define FLOW_BOOT_PIN GPIO_NUM_0
#define FLOW_AXP2101_ADDRESS 0x34
#define FLOW_AXP2101_BATTERY_PERCENT_REGISTER 0xa4
#define FLOW_FULL_BRIGHTNESS 70
#define FLOW_DIM_BRIGHTNESS 18
#define FLOW_BATTERY_REFRESH_MS 60000

static const char *const TAG = "flow_power";
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static int64_t s_last_activity_us;
static bool s_transition_active;
static flow_display_level_t s_display_level = FLOW_DISPLAY_FULL;
static i2c_master_dev_handle_t s_axp2101;
static flow_power_battery_handler_t s_battery_handler;
static void *s_battery_context;

static void apply_display_level(flow_display_level_t level)
{
    if (level == s_display_level) {
        return;
    }
    int brightness = FLOW_FULL_BRIGHTNESS;
    if (level == FLOW_DISPLAY_DIM) {
        brightness = FLOW_DIM_BRIGHTNESS;
    } else if (level == FLOW_DISPLAY_OFF) {
        brightness = 0;
    }
    esp_err_t error = bsp_display_brightness_set(brightness);
    if (error == ESP_OK) {
        s_display_level = level;
    } else {
        ESP_LOGW(TAG, "Brightness update failed: %s", esp_err_to_name(error));
    }
}

static bool read_battery_percentage(uint8_t *percentage)
{
    if (s_axp2101 == NULL || percentage == NULL) {
        return false;
    }
    uint8_t reg = FLOW_AXP2101_BATTERY_PERCENT_REGISTER;
    uint8_t value = 0xff;
    if (i2c_master_transmit_receive(s_axp2101, &reg, 1, &value, 1, 100) != ESP_OK) {
        return false;
    }
    if (value > 100) {
        return false;
    }
    *percentage = value;
    return true;
}

static void power_task(void *context)
{
    (void)context;
    bool boot_was_down = false;
    uint8_t down_samples = 0;
    TickType_t last_battery_read = 0;

    while (true) {
        bool boot_down = gpio_get_level(FLOW_BOOT_PIN) == 0;
        if (boot_down) {
            if (down_samples < 3) {
                ++down_samples;
            }
            if (down_samples == 3 && !boot_was_down) {
                boot_was_down = true;
                flow_power_wake();
            }
        } else {
            down_samples = 0;
            boot_was_down = false;
        }

        int64_t last_activity;
        bool transition;
        portENTER_CRITICAL(&s_lock);
        last_activity = s_last_activity_us;
        transition = s_transition_active;
        portEXIT_CRITICAL(&s_lock);
        int64_t elapsed_us = esp_timer_get_time() - last_activity;
        uint32_t idle_ms = elapsed_us <= 0 ? 0 : (uint32_t)(elapsed_us / 1000);
        apply_display_level(flow_power_policy_resolve(transition, idle_ms));

        TickType_t now = xTaskGetTickCount();
        if (last_battery_read == 0 ||
            now - last_battery_read >= pdMS_TO_TICKS(FLOW_BATTERY_REFRESH_MS)) {
            last_battery_read = now;
            uint8_t percentage;
            if (read_battery_percentage(&percentage)) {
                if (s_battery_handler != NULL) {
                    s_battery_handler(percentage, s_battery_context);
                }
            } else {
                ESP_LOGW(TAG, "AXP2101 battery percentage unavailable");
            }
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

esp_err_t flow_power_init(flow_power_battery_handler_t battery_handler,
                          void *context)
{
    s_battery_handler = battery_handler;
    s_battery_context = context;
    s_last_activity_us = esp_timer_get_time();
    s_display_level = FLOW_DISPLAY_FULL;

    gpio_config_t button_config = {
        .pin_bit_mask = 1ULL << FLOW_BOOT_PIN,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t error = gpio_config(&button_config);
    if (error != ESP_OK) {
        return error;
    }

    i2c_master_bus_handle_t bus = bsp_i2c_get_handle();
    if (bus != NULL) {
        i2c_device_config_t device_config = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7,
            .device_address = FLOW_AXP2101_ADDRESS,
            .scl_speed_hz = 400000,
        };
        error = i2c_master_bus_add_device(bus, &device_config, &s_axp2101);
        if (error != ESP_OK) {
            ESP_LOGW(TAG, "AXP2101 setup failed: %s", esp_err_to_name(error));
            s_axp2101 = NULL;
        }
    }

    if (xTaskCreate(power_task, "flow_power", 3072, NULL, 4, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    ESP_ERROR_CHECK_WITHOUT_ABORT(bsp_display_brightness_set(FLOW_FULL_BRIGHTNESS));
    return ESP_OK;
}

void flow_power_note_activity(void)
{
    portENTER_CRITICAL(&s_lock);
    s_last_activity_us = esp_timer_get_time();
    portEXIT_CRITICAL(&s_lock);
}

void flow_power_set_transition_active(bool active)
{
    portENTER_CRITICAL(&s_lock);
    bool changed = s_transition_active != active;
    s_transition_active = active;
    if (changed) {
        s_last_activity_us = esp_timer_get_time();
    }
    portEXIT_CRITICAL(&s_lock);
}

void flow_power_wake(void)
{
    flow_power_note_activity();
}
