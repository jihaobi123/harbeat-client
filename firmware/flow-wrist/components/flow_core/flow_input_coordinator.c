#include "flow_input_coordinator.h"

#include <stddef.h>
#include <string.h>

enum input_mode {
    INPUT_MODE_NONE,
    INPUT_MODE_ENERGY,
    INPUT_MODE_STYLE,
};

static const char *const s_styles[] = {
    "hiphop",
    "breaking",
    "funk",
    "locking",
};

static flow_input_action_t make_action(flow_input_action_type_t type)
{
    flow_input_action_t action = {0};
    action.type = type;
    return action;
}

static bool control_allowed(const flow_app_state_t *state)
{
    return state != NULL && state->link_state == FLOW_LINK_READY &&
        state->has_snapshot && !state->snapshot.locked &&
        state->screen != FLOW_SCREEN_SENDING &&
        state->screen != FLOW_SCREEN_TRANSITION;
}

static uint8_t style_index(const char *style)
{
    for (uint8_t i = 0; i < sizeof(s_styles) / sizeof(s_styles[0]); ++i) {
        if (strcmp(style, s_styles[i]) == 0) {
            return i;
        }
    }
    return 0;
}

static void set_style(flow_input_action_t *action, uint8_t index)
{
    strncpy(action->style, s_styles[index], sizeof(action->style) - 1);
    action->style[sizeof(action->style) - 1] = '\0';
}

void flow_input_coordinator_init(flow_input_coordinator_t *coordinator)
{
    if (coordinator != NULL) {
        memset(coordinator, 0, sizeof(*coordinator));
    }
}

flow_input_action_t flow_input_handle_gesture(
    flow_input_coordinator_t *coordinator,
    flow_gesture_event_t event,
    const flow_app_state_t *state)
{
    if (coordinator == NULL || event == FLOW_GESTURE_NONE) {
        return make_action(FLOW_INPUT_NONE);
    }
    if (event == FLOW_GESTURE_CANCEL) {
        flow_input_coordinator_init(coordinator);
        return make_action(FLOW_INPUT_CANCEL);
    }
    if (event == FLOW_GESTURE_WAKE) {
        return make_action(FLOW_INPUT_READY);
    }
    if (event == FLOW_GESTURE_ARMED) {
        return make_action(FLOW_INPUT_ARMED);
    }

    if (!control_allowed(state)) {
        flow_input_coordinator_init(coordinator);
        return make_action(FLOW_INPUT_CANCEL);
    }
    if (event == FLOW_GESTURE_MODE_ENERGY) {
        coordinator->active = true;
        coordinator->mode = INPUT_MODE_ENERGY;
        coordinator->preview_energy = state->snapshot.current.energy;
        flow_input_action_t action = make_action(FLOW_INPUT_OPEN_ENERGY);
        action.energy = coordinator->preview_energy;
        return action;
    }
    if (event == FLOW_GESTURE_MODE_STYLE) {
        coordinator->active = true;
        coordinator->mode = INPUT_MODE_STYLE;
        coordinator->preview_style = style_index(state->snapshot.current.style);
        flow_input_action_t action = make_action(FLOW_INPUT_OPEN_STYLE);
        set_style(&action, coordinator->preview_style);
        return action;
    }
    if (!coordinator->active) {
        return make_action(FLOW_INPUT_CANCEL);
    }
    if (event == FLOW_GESTURE_PREVIEW_PREV ||
        event == FLOW_GESTURE_PREVIEW_NEXT) {
        const int direction = event == FLOW_GESTURE_PREVIEW_NEXT ? 1 : -1;
        if (coordinator->mode == INPUT_MODE_ENERGY) {
            int energy = (int)coordinator->preview_energy + direction;
            if (energy < 1) {
                energy = 1;
            } else if (energy > 5) {
                energy = 5;
            }
            coordinator->preview_energy = (uint8_t)energy;
            flow_input_action_t action = make_action(FLOW_INPUT_PREVIEW_ENERGY);
            action.energy = coordinator->preview_energy;
            return action;
        }
        int style = (int)coordinator->preview_style + direction;
        if (style < 0) {
            style = 0;
        } else if (style >= (int)(sizeof(s_styles) / sizeof(s_styles[0]))) {
            style = (int)(sizeof(s_styles) / sizeof(s_styles[0])) - 1;
        }
        coordinator->preview_style = (uint8_t)style;
        flow_input_action_t action = make_action(FLOW_INPUT_PREVIEW_STYLE);
        set_style(&action, coordinator->preview_style);
        return action;
    }
    if (event == FLOW_GESTURE_CONFIRMING) {
        return make_action(FLOW_INPUT_CONFIRMING);
    }
    if (event == FLOW_GESTURE_SEND) {
        flow_input_action_t action;
        if (coordinator->mode == INPUT_MODE_ENERGY) {
            action = make_action(FLOW_INPUT_SUBMIT_ENERGY);
            action.energy = coordinator->preview_energy;
        } else {
            action = make_action(FLOW_INPUT_SUBMIT_STYLE);
            set_style(&action, coordinator->preview_style);
        }
        flow_input_coordinator_init(coordinator);
        return action;
    }
    return make_action(FLOW_INPUT_NONE);
}
