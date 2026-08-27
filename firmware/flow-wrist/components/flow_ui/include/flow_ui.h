#pragma once

#include <stdint.h>

#include "flow_core.h"
#include "flow_input_coordinator.h"

typedef enum {
    FLOW_UI_ACTION_OPEN_ENERGY,
    FLOW_UI_ACTION_OPEN_STYLE,
    FLOW_UI_ACTION_BACK,
    FLOW_UI_ACTION_SET_ENERGY,
    FLOW_UI_ACTION_SET_STYLE,
    FLOW_UI_ACTION_COMPLETE_TIMEOUT
} flow_ui_action_type_t;

typedef struct {
    flow_ui_action_type_t type;
    uint8_t energy;
    char style[FLOW_STYLE_ID_MAX];
} flow_ui_action_t;

typedef void (*flow_ui_action_handler_t)(const flow_ui_action_t *action,
                                         void *context);

void flow_ui_init(flow_ui_action_handler_t handler, void *context);
void flow_ui_render(const flow_app_state_t *state);
void flow_ui_show_offline(void);
void flow_ui_show_syncing(void);
void flow_ui_apply_gesture(const flow_input_action_t *action);
