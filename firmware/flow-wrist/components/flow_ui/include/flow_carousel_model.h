#pragma once

#include <stdbool.h>
#include <stdint.h>

#define FLOW_CAROUSEL_WIDTH_PX 342
#define FLOW_CAROUSEL_SNAP_MS 140

typedef struct {
    int8_t step;
    int32_t target_offset;
    uint16_t duration_ms;
} flow_carousel_release_t;

int32_t flow_carousel_drag_offset(int32_t delta_x, int32_t width);
uint8_t flow_carousel_neighbor(uint8_t index,
                               int8_t step,
                               uint8_t count,
                               bool wrap);
flow_carousel_release_t flow_carousel_release(int32_t delta_x,
                                               int32_t delta_y,
                                               int32_t velocity_x,
                                               uint8_t index,
                                               uint8_t count,
                                               bool wrap);
