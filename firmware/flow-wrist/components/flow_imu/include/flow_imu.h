#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

typedef struct {
    uint32_t timestamp_ms;
    float accel_g[3];
    float gyro_dps[3];
} flow_imu_sample_t;

esp_err_t flow_imu_start(QueueHandle_t output_queue);
bool flow_imu_is_available(void);
