#include "flow_carousel_model.h"

static int32_t absolute(int32_t value)
{
    return value < 0 ? -value : value;
}

int32_t flow_carousel_drag_offset(int32_t delta_x, int32_t width)
{
    if (delta_x > width) {
        return width;
    }
    if (delta_x < -width) {
        return -width;
    }
    return delta_x;
}

uint8_t flow_carousel_neighbor(uint8_t index,
                               int8_t step,
                               uint8_t count,
                               bool wrap)
{
    if (count == 0 || step == 0) {
        return index;
    }
    if (step > 0) {
        if ((uint8_t)(index + 1) < count) {
            return (uint8_t)(index + 1);
        }
        return wrap ? 0 : index;
    }
    if (index > 0) {
        return (uint8_t)(index - 1);
    }
    return wrap ? (uint8_t)(count - 1) : index;
}

flow_carousel_release_t flow_carousel_release(int32_t delta_x,
                                               int32_t delta_y,
                                               int32_t velocity_x,
                                               uint8_t index,
                                               uint8_t count,
                                               bool wrap)
{
    flow_carousel_release_t result = {
        .step = 0,
        .target_offset = 0,
        .duration_ms = FLOW_CAROUSEL_SNAP_MS,
    };
    if (absolute(delta_y) >= absolute(delta_x)) {
        return result;
    }

    const bool crossed_distance = absolute(delta_x) >= 52;
    const bool crossed_velocity = absolute(velocity_x) >= 720;
    if (!crossed_distance && !crossed_velocity) {
        return result;
    }

    const int8_t requested_step = delta_x < 0 || velocity_x < -720 ? 1 : -1;
    if (flow_carousel_neighbor(index, requested_step, count, wrap) == index) {
        return result;
    }
    result.step = requested_step;
    result.target_offset = requested_step > 0
        ? -FLOW_CAROUSEL_WIDTH_PX
        : FLOW_CAROUSEL_WIDTH_PX;
    return result;
}
