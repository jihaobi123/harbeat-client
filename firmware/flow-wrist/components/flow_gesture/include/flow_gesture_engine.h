#pragma once

#include <stdbool.h>
#include <stdint.h>

#define FLOW_GESTURE_FILTER_SAMPLES 5

typedef enum {
    FLOW_GESTURE_NONE,
    FLOW_GESTURE_WAKE,
    FLOW_GESTURE_ARMED,
    FLOW_GESTURE_MODE_ENERGY,
    FLOW_GESTURE_MODE_STYLE,
    FLOW_GESTURE_PREVIEW_PREV,
    FLOW_GESTURE_PREVIEW_NEXT,
    FLOW_GESTURE_CONFIRMING,
    FLOW_GESTURE_SEND,
    FLOW_GESTURE_CANCEL,
} flow_gesture_event_t;

typedef struct {
    uint32_t timestamp_ms;
    float accel_g[3];
    float gyro_dps[3];
    bool touch_active;
    bool ble_ready;
    bool hub_locked;
} flow_gesture_input_t;

typedef struct {
    float accel[FLOW_GESTURE_FILTER_SAMPLES][3];
    float gyro[FLOW_GESTURE_FILTER_SAMPLES][3];
    uint8_t sample_index;
    uint8_t sample_count;
    uint8_t state;
    uint32_t still_since_ms;
    uint32_t armed_at_ms;
    uint32_t last_motion_ms;
    uint32_t cooldown_until_ms;
    uint32_t first_roll_ms;
    int8_t first_roll_sign;
    bool confirming_reported;
    bool pulse_active;
    bool pulse_invalid;
    uint8_t pulse_axis;
    int8_t pulse_sign;
    uint32_t pulse_started_ms;
    float pulse_peak;
} flow_gesture_engine_t;

void flow_gesture_init(flow_gesture_engine_t *engine);
flow_gesture_event_t flow_gesture_update(flow_gesture_engine_t *engine,
                                         const flow_gesture_input_t *input);
