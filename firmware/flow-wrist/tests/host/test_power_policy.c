#include <assert.h>
#include <stdio.h>

#include "flow_power_policy.h"

int main(void)
{
    assert(flow_power_policy_resolve(false, 0) == FLOW_DISPLAY_FULL);
    assert(flow_power_policy_resolve(false, 9999) == FLOW_DISPLAY_FULL);
    assert(flow_power_policy_resolve(false, 10000) == FLOW_DISPLAY_OFF);
    assert(flow_power_policy_resolve(false, 60000) == FLOW_DISPLAY_OFF);

    assert(flow_power_policy_resolve(true, 4999) == FLOW_DISPLAY_FULL);
    assert(flow_power_policy_resolve(true, 5000) == FLOW_DISPLAY_DIM);
    assert(flow_power_policy_resolve(true, 60000) == FLOW_DISPLAY_DIM);
    puts("flow_power policy tests passed");
    return 0;
}
