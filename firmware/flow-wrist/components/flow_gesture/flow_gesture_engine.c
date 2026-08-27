#include "flow_gesture_engine.h"

#include <stddef.h>
#include <string.h>

enum gesture_state {
    GESTURE_IDLE,
    GESTURE_AWAKE,
    GESTURE_ARMED,
    GESTURE_MODE_ENERGY,
    GESTURE_MODE_STYLE,
    GESTURE_COOLDOWN,
};

enum pulse_axis {
    PULSE_NONE,
    PULSE_ROLL,
    PULSE_VERTICAL,
};

typedef struct {
    uint8_t axis;
    int8_t sign;
    bool valid;
} pulse_result_t;

static float absolute(float value)
{
    return value < 0.0f ? -value : value;
}

static int8_t sign_of(float value)
{
    return value < 0.0f ? -1 : 1;
}

static void reset_session(flow_gesture_engine_t *engine, uint32_t now_ms)
{
    engine->state = GESTURE_COOLDOWN;
    engine->cooldown_until_ms = now_ms + 350;
    engine->still_since_ms = 0;
    engine->first_roll_sign = 0;
    engine->confirming_reported = false;
    engine->pulse_active = false;
    engine->pulse_invalid = false;
}

void flow_gesture_init(flow_gesture_engine_t *engine)
{
    if (engine != NULL) {
        memset(engine, 0, sizeof(*engine));
    }
}

static void filter_sample(flow_gesture_engine_t *engine,
                          const flow_gesture_input_t *input,
                          float accel[3],
                          float gyro[3])
{
    const uint8_t index = engine->sample_index;
    for (int axis = 0; axis < 3; ++axis) {
        engine->accel[index][axis] = input->accel_g[axis];
        engine->gyro[index][axis] = input->gyro_dps[axis];
    }
    engine->sample_index = (uint8_t)((index + 1) % FLOW_GESTURE_FILTER_SAMPLES);
    if (engine->sample_count < FLOW_GESTURE_FILTER_SAMPLES) {
        engine->sample_count++;
    }

    for (int axis = 0; axis < 3; ++axis) {
        accel[axis] = 0.0f;
        gyro[axis] = 0.0f;
        for (uint8_t sample = 0; sample < engine->sample_count; ++sample) {
            accel[axis] += engine->accel[sample][axis];
            gyro[axis] += engine->gyro[sample][axis];
        }
        accel[axis] /= engine->sample_count;
        gyro[axis] /= engine->sample_count;
    }
}

static bool is_still(const float accel[3], const float gyro[3])
{
    if (absolute(gyro[0]) >= 12.0f || absolute(gyro[1]) >= 12.0f ||
        absolute(gyro[2]) >= 12.0f) {
        return false;
    }
    const float magnitude_squared = accel[0] * accel[0] +
        accel[1] * accel[1] + accel[2] * accel[2];
    return magnitude_squared >= 0.81f && magnitude_squared <= 1.21f;
}

static pulse_result_t detect_pulse(flow_gesture_engine_t *engine,
                                   uint32_t now_ms,
                                   const float gyro[3])
{
    pulse_result_t result = {0};
    const float roll = absolute(gyro[0]);
    const float vertical = absolute(gyro[1]);
    const float other = absolute(gyro[2]);

    if (!engine->pulse_active) {
        uint8_t axis = PULSE_NONE;
        float main = 0.0f;
        float secondary = 0.0f;
        if (roll >= vertical) {
            axis = PULSE_ROLL;
            main = roll;
            secondary = vertical > other ? vertical : other;
        } else {
            axis = PULSE_VERTICAL;
            main = vertical;
            secondary = roll > other ? roll : other;
        }
        if (main >= 120.0f && main <= 280.0f &&
            main >= (secondary + 1.0f) * 1.35f) {
            engine->pulse_active = true;
            engine->pulse_invalid = false;
            engine->pulse_axis = axis;
            engine->pulse_sign = sign_of(axis == PULSE_ROLL ? gyro[0] : gyro[1]);
            engine->pulse_started_ms = now_ms;
            engine->pulse_peak = main;
        }
        return result;
    }

    const float main = engine->pulse_axis == PULSE_ROLL ? roll : vertical;
    const float secondary = engine->pulse_axis == PULSE_ROLL ? vertical : roll;
    if (main > engine->pulse_peak) {
        engine->pulse_peak = main;
    }
    if (main > 280.0f || main < (secondary + 1.0f) * 1.10f) {
        engine->pulse_invalid = true;
    }
    if (main >= 60.0f) {
        return result;
    }

    const uint32_t duration = now_ms - engine->pulse_started_ms;
    result.axis = engine->pulse_axis;
    result.sign = engine->pulse_sign;
    result.valid = !engine->pulse_invalid && duration >= 80 && duration <= 450 &&
        engine->pulse_peak >= 120.0f && engine->pulse_peak <= 280.0f;
    engine->pulse_active = false;
    engine->pulse_invalid = false;
    return result;
}

flow_gesture_event_t flow_gesture_update(flow_gesture_engine_t *engine,
                                         const flow_gesture_input_t *input)
{
    if (engine == NULL || input == NULL) {
        return FLOW_GESTURE_NONE;
    }

    float accel[3];
    float gyro[3];
    filter_sample(engine, input, accel, gyro);
    const uint32_t now_ms = input->timestamp_ms;

    if (engine->state == GESTURE_COOLDOWN) {
        if (now_ms < engine->cooldown_until_ms) {
            return FLOW_GESTURE_NONE;
        }
        engine->state = GESTURE_IDLE;
    }

    if (engine->state != GESTURE_IDLE &&
        (input->touch_active || !input->ble_ready || input->hub_locked)) {
        reset_session(engine, now_ms);
        return FLOW_GESTURE_CANCEL;
    }
    if (engine->state == GESTURE_IDLE &&
        (input->touch_active || !input->ble_ready || input->hub_locked)) {
        engine->still_since_ms = 0;
        return FLOW_GESTURE_NONE;
    }

    const bool still = is_still(accel, gyro);
    if (engine->state == GESTURE_IDLE) {
        if (!still) {
            engine->still_since_ms = 0;
            engine->last_motion_ms = now_ms + 1;
            return FLOW_GESTURE_NONE;
        }
        if (engine->last_motion_ms == 0 ||
            now_ms + 1 - engine->last_motion_ms > 1500) {
            engine->still_since_ms = 0;
            return FLOW_GESTURE_NONE;
        }
        if (engine->still_since_ms == 0) {
            engine->still_since_ms = now_ms + 1;
        }
        if (now_ms + 1 - engine->still_since_ms >= 500) {
            engine->state = GESTURE_AWAKE;
            engine->armed_at_ms = now_ms;
            engine->still_since_ms = 0;
            return FLOW_GESTURE_WAKE;
        }
        return FLOW_GESTURE_NONE;
    }

    if ((engine->state == GESTURE_ARMED ||
         engine->state == GESTURE_MODE_ENERGY ||
         engine->state == GESTURE_MODE_STYLE) &&
        now_ms - engine->armed_at_ms > 5000) {
        reset_session(engine, now_ms);
        return FLOW_GESTURE_CANCEL;
    }

    pulse_result_t pulse = detect_pulse(engine, now_ms, gyro);
    if (engine->state == GESTURE_AWAKE) {
        if (now_ms - engine->armed_at_ms > 3000) {
            reset_session(engine, now_ms);
            return FLOW_GESTURE_CANCEL;
        }
        if (!pulse.valid) {
            if (engine->first_roll_sign != 0 &&
                now_ms - engine->first_roll_ms > 1200) {
                engine->first_roll_sign = 0;
            }
            return FLOW_GESTURE_NONE;
        }
        if (pulse.axis != PULSE_ROLL) {
            reset_session(engine, now_ms);
            return FLOW_GESTURE_CANCEL;
        }
        if (engine->first_roll_sign == 0 ||
            now_ms - engine->first_roll_ms > 1200 ||
            engine->first_roll_sign == pulse.sign) {
            engine->first_roll_sign = pulse.sign;
            engine->first_roll_ms = now_ms;
            return FLOW_GESTURE_NONE;
        }
        engine->state = GESTURE_ARMED;
        engine->armed_at_ms = now_ms;
        engine->last_motion_ms = now_ms;
        engine->first_roll_sign = 0;
        return FLOW_GESTURE_ARMED;
    }

    if (engine->state == GESTURE_ARMED) {
        if (!pulse.valid) {
            return FLOW_GESTURE_NONE;
        }
        if (pulse.axis != PULSE_VERTICAL) {
            reset_session(engine, now_ms);
            return FLOW_GESTURE_CANCEL;
        }
        engine->state = pulse.sign < 0 ? GESTURE_MODE_ENERGY : GESTURE_MODE_STYLE;
        engine->last_motion_ms = now_ms;
        engine->confirming_reported = false;
        return pulse.sign < 0 ? FLOW_GESTURE_MODE_ENERGY : FLOW_GESTURE_MODE_STYLE;
    }

    if (pulse.valid) {
        if (pulse.axis != PULSE_ROLL) {
            reset_session(engine, now_ms);
            return FLOW_GESTURE_CANCEL;
        }
        engine->last_motion_ms = now_ms;
        engine->confirming_reported = false;
        return pulse.sign < 0 ? FLOW_GESTURE_PREVIEW_PREV :
                                FLOW_GESTURE_PREVIEW_NEXT;
    }

    if (!still || engine->pulse_active) {
        return FLOW_GESTURE_NONE;
    }
    const uint32_t held_ms = now_ms - engine->last_motion_ms;
    if (!engine->confirming_reported && held_ms >= 800) {
        engine->confirming_reported = true;
        return FLOW_GESTURE_CONFIRMING;
    }
    if (held_ms >= 1100) {
        reset_session(engine, now_ms);
        return FLOW_GESTURE_SEND;
    }
    return FLOW_GESTURE_NONE;
}
