#include "flow_power_policy.h"

flow_display_level_t flow_power_policy_resolve(bool transition_active,
                                                uint32_t idle_ms)
{
    if (transition_active) {
        return idle_ms >= 5000 ? FLOW_DISPLAY_DIM : FLOW_DISPLAY_FULL;
    }
    return idle_ms >= 10000 ? FLOW_DISPLAY_OFF : FLOW_DISPLAY_FULL;
}
