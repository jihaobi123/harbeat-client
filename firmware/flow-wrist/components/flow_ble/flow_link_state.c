#include "flow_link_state.h"

flow_link_state_t flow_link_resolve(const flow_link_inputs_t *inputs)
{
    if (inputs == 0 || !inputs->connected) {
        return FLOW_LINK_ADVERTISING;
    }
    if (inputs->version_mismatch) {
        return FLOW_LINK_VERSION_MISMATCH;
    }
    if (!inputs->encrypted || !inputs->command_subscribed) {
        return FLOW_LINK_SECURING;
    }
    if (!inputs->catalog_received) {
        return FLOW_LINK_SYNCING_CATALOG;
    }
    if (!inputs->state_received) {
        return FLOW_LINK_SYNCING_STATE;
    }
    return FLOW_LINK_READY;
}
