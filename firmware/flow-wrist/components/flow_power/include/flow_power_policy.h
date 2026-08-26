#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    FLOW_DISPLAY_FULL,
    FLOW_DISPLAY_DIM,
    FLOW_DISPLAY_OFF,
} flow_display_level_t;

flow_display_level_t flow_power_policy_resolve(bool transition_active,
                                                uint32_t idle_ms);
