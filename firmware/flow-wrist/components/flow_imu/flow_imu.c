#include "flow_imu.h"

#include <string.h>

#include "bsp/esp-bsp.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/task.h"
#include "qmi8658.h"

#define FLOW_IMU_SAMPLE_PERIOD_MS 8
#define FLOW_IMU_TASK_PRIORITY 4
#define FLOW_IMU_TASK_STACK 3072

static const char *const TAG = "flow_imu";
static qmi8658_dev_t s_device;
static QueueHandle_t s_output_queue;
static bool s_available;

static void publish_latest(const flow_imu_sample_t *sample)
{
    if (xQueueSend(s_output_queue, sample, 0) == pdTRUE) {
        return;
    }
    flow_imu_sample_t discarded;
    (void)xQueueReceive(s_output_queue, &discarded, 0);
    (void)xQueueSend(s_output_queue, sample, 0);
}

static void sample_task(void *context)
{
    (void)context;
    TickType_t wake_at = xTaskGetTickCount();
    unsigned consecutive_errors = 0;
    while (true) {
        qmi8658_data_t data;
        const esp_err_t error = qmi8658_read_sensor_data(&s_device, &data);
        if (error == ESP_OK) {
            flow_imu_sample_t sample = {
                .timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000),
                .accel_g = {
                    data.accelX / 1000.0f,
                    data.accelY / 1000.0f,
                    data.accelZ / 1000.0f,
                },
                .gyro_dps = {data.gyroX, data.gyroY, data.gyroZ},
            };
            publish_latest(&sample);
            consecutive_errors = 0;
        } else {
            ++consecutive_errors;
            if (consecutive_errors == 1 || consecutive_errors % 125 == 0) {
                ESP_LOGW(TAG, "QMI8658 sample failed: %s (%u consecutive)",
                         esp_err_to_name(error), consecutive_errors);
            }
        }
        xTaskDelayUntil(&wake_at, pdMS_TO_TICKS(FLOW_IMU_SAMPLE_PERIOD_MS));
    }
}

esp_err_t flow_imu_start(QueueHandle_t output_queue)
{
    if (output_queue == NULL || s_available) {
        return output_queue == NULL ? ESP_ERR_INVALID_ARG : ESP_ERR_INVALID_STATE;
    }
    memset(&s_device, 0, sizeof(s_device));
    s_output_queue = output_queue;

    i2c_master_bus_handle_t bus = bsp_i2c_get_handle();
    if (bus == NULL) {
        ESP_LOGE(TAG, "QMI8658 unavailable: shared I2C bus is not ready");
        return ESP_ERR_INVALID_STATE;
    }
    esp_err_t error = qmi8658_init(&s_device, bus, QMI8658_ADDRESS_HIGH);
    if (error == ESP_OK) {
        error = qmi8658_set_accel_range(&s_device, QMI8658_ACCEL_RANGE_8G);
    }
    if (error == ESP_OK) {
        error = qmi8658_set_accel_odr(&s_device, QMI8658_ACCEL_ODR_125HZ);
    }
    if (error == ESP_OK) {
        error = qmi8658_set_gyro_range(&s_device, QMI8658_GYRO_RANGE_512DPS);
    }
    if (error == ESP_OK) {
        error = qmi8658_set_gyro_odr(&s_device, QMI8658_GYRO_ODR_125HZ);
    }
    if (error == ESP_OK) {
        qmi8658_set_accel_unit_mg(&s_device, true);
        qmi8658_set_gyro_unit_dps(&s_device, true);
        error = qmi8658_enable_sensors(&s_device,
                                       QMI8658_ENABLE_ACCEL | QMI8658_ENABLE_GYRO);
    }
    if (error != ESP_OK) {
        ESP_LOGE(TAG, "QMI8658 unavailable: %s; touch and BLE remain active",
                 esp_err_to_name(error));
        if (s_device.dev_handle != NULL) {
            (void)i2c_master_bus_rm_device(s_device.dev_handle);
            s_device.dev_handle = NULL;
        }
        return error;
    }

    if (xTaskCreate(sample_task, "flow_imu", FLOW_IMU_TASK_STACK, NULL,
                    FLOW_IMU_TASK_PRIORITY, NULL) != pdPASS) {
        (void)i2c_master_bus_rm_device(s_device.dev_handle);
        s_device.dev_handle = NULL;
        return ESP_ERR_NO_MEM;
    }
    s_available = true;
    ESP_LOGI(TAG, "QMI8658 sampling at 125 Hz (accel +/-8g, gyro +/-512dps)");
    return ESP_OK;
}

bool flow_imu_is_available(void)
{
    return s_available;
}
