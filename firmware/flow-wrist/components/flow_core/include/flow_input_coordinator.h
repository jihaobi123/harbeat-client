#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "flow_core.h"
#include "flow_gesture_engine.h"

typedef enum {
    FLOW_INPUT_NONE,
    FLOW_INPUT_READY,
    FLOW_INPUT_ARMED,
    FLOW_INPUT_OPEN_ENERGY,
    FLOW_INPUT_OPEN_STYLE,
    FLOW_INPUT_PREVIEW_ENERGY,
    FLOW_INPUT_PREVIEW_STYLE,
    FLOW_INPUT_CONFIRMING,
    FLOW_INPUT_SUBMIT_ENERGY,
    FLOW_INPUT_SUBMIT_STYLE,
    FLOW_INPUT_CANCEL,
} flow_input_action_type_t;

typedef struct {
    flow_input_action_type_t type;
    uint8_t energy;
    char style[FLOW_STYLE_ID_MAX];
} flow_input_action_t;

typedef struct {
    uint8_t mode;
    uint8_t preview_energy;
    uint8_t preview_style;
    bool active;
} flow_input_coordinator_t;

void flow_input_coordinator_init(flow_input_coordinator_t *coordinator);
flow_input_action_t flow_input_handle_gesture(
    flow_input_coordinator_t *coordinator,
    flow_gesture_event_t event,
    const flow_app_state_t *state);
