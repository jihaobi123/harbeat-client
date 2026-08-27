#pragma once

#include <stdbool.h>
#include "flow_core.h"

typedef struct {
    bool connected;
    bool encrypted;
    bool command_subscribed;
    bool catalog_received;
    bool state_received;
    bool version_mismatch;
} flow_link_inputs_t;

flow_link_state_t flow_link_resolve(const flow_link_inputs_t *inputs);
