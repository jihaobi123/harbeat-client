#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "flow_gesture_engine.h"

static flow_gesture_event_t feed(flow_gesture_engine_t *engine,
                                 uint32_t *time_ms,
                                 float gx,
                                 float gy,
                                 float gz,
                                 bool touch,
                                 bool ready,
                                 bool locked)
{
    flow_gesture_input_t input = {
        .timestamp_ms = *time_ms,
        .accel_g = {0.0f, 0.0f, 1.0f},
        .gyro_dps = {gx, gy, gz},
        .touch_active = touch,
        .ble_ready = ready,
        .hub_locked = locked,
    };
    *time_ms += 8;
    return flow_gesture_update(engine, &input);
}

static bool feed_still_until(flow_gesture_engine_t *engine,
                             uint32_t *time_ms,
                             uint32_t duration_ms,
                             flow_gesture_event_t wanted)
{
    const uint32_t count = duration_ms / 8;
    for (uint32_t i = 0; i < count; ++i) {
        if (feed(engine, time_ms, 0, 0, 0, false, true, false) == wanted) {
            return true;
        }
    }
    return false;
}

static flow_gesture_event_t pulse(flow_gesture_engine_t *engine,
                                  uint32_t *time_ms,
                                  float gx,
                                  float gy)
{
    flow_gesture_event_t result = FLOW_GESTURE_NONE;
    for (int i = 0; i < 18; ++i) {
        flow_gesture_event_t event = feed(engine, time_ms, gx, gy, 5,
                                          false, true, false);
        if (event != FLOW_GESTURE_NONE) {
            result = event;
        }
    }
    for (int i = 0; i < 15; ++i) {
        flow_gesture_event_t event = feed(engine, time_ms, 0, 0, 0,
                                          false, true, false);
        if (event != FLOW_GESTURE_NONE) {
            result = event;
        }
    }
    return result;
}

static void arm(flow_gesture_engine_t *engine, uint32_t *time_ms)
{
    for (int i = 0; i < 20; ++i) {
        (void)feed(engine, time_ms, 45, 35, 20, false, true, false);
    }
    assert(feed_still_until(engine, time_ms, 560, FLOW_GESTURE_WAKE));
    assert(pulse(engine, time_ms, 170, 0) == FLOW_GESTURE_NONE);
    assert(pulse(engine, time_ms, -170, 0) == FLOW_GESTURE_ARMED);
}

static void test_energy_preview_and_send(void)
{
    flow_gesture_engine_t engine;
    flow_gesture_init(&engine);
    uint32_t time_ms = 0;
    arm(&engine, &time_ms);
    assert(pulse(&engine, &time_ms, 0, -180) == FLOW_GESTURE_MODE_ENERGY);
    assert(pulse(&engine, &time_ms, 170, 0) == FLOW_GESTURE_PREVIEW_NEXT);
    assert(feed_still_until(&engine, &time_ms, 900, FLOW_GESTURE_CONFIRMING));
    assert(feed_still_until(&engine, &time_ms, 400, FLOW_GESTURE_SEND));

    for (int i = 0; i < 40; ++i) {
        assert(feed(&engine, &time_ms, 0, 0, 0, false, true, false) ==
               FLOW_GESTURE_NONE);
    }
}

static void test_style_prev_and_cancellations(void)
{
    flow_gesture_engine_t engine;
    flow_gesture_init(&engine);
    uint32_t time_ms = 0;
    arm(&engine, &time_ms);
    assert(pulse(&engine, &time_ms, 0, 180) == FLOW_GESTURE_MODE_STYLE);
    assert(pulse(&engine, &time_ms, -170, 0) == FLOW_GESTURE_PREVIEW_PREV);
    assert(feed(&engine, &time_ms, 0, 0, 0, true, true, false) ==
           FLOW_GESTURE_CANCEL);

    flow_gesture_init(&engine);
    time_ms = 0;
    arm(&engine, &time_ms);
    assert(feed(&engine, &time_ms, 0, 0, 0, false, false, false) ==
           FLOW_GESTURE_CANCEL);

    flow_gesture_init(&engine);
    time_ms = 0;
    arm(&engine, &time_ms);
    assert(feed(&engine, &time_ms, 0, 0, 0, false, true, true) ==
           FLOW_GESTURE_CANCEL);
}

static void test_timeout_and_dance_never_send(void)
{
    flow_gesture_engine_t engine;
    flow_gesture_init(&engine);
    uint32_t time_ms = 0;
    assert(!feed_still_until(&engine, &time_ms, 2000, FLOW_GESTURE_WAKE));

    flow_gesture_init(&engine);
    time_ms = 0;
    arm(&engine, &time_ms);
    assert(feed_still_until(&engine, &time_ms, 5200, FLOW_GESTURE_CANCEL));

    flow_gesture_init(&engine);
    time_ms = 0;
    int sends = 0;
    int arms = 0;
    for (int i = 0; i < 3750; ++i) {
        const float gx = (i % 23 < 11) ? 75.0f : -92.0f;
        const float gy = (i % 31 < 15) ? -64.0f : 88.0f;
        flow_gesture_event_t event = feed(&engine, &time_ms, gx, gy, 35,
                                          false, true, false);
        sends += event == FLOW_GESTURE_SEND;
        arms += event == FLOW_GESTURE_ARMED;
    }
    assert(sends == 0);
    assert(arms == 0);
}

int main(void)
{
    test_energy_preview_and_send();
    test_style_prev_and_cancellations();
    test_timeout_and_dance_never_send();
    puts("gesture engine tests passed");
    return 0;
}
