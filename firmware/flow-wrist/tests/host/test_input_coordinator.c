#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "flow_input_coordinator.h"

static flow_app_state_t ready_state(void)
{
    flow_app_state_t state;
    memset(&state, 0, sizeof(state));
    state.link_state = FLOW_LINK_READY;
    state.has_snapshot = true;
    state.screen = FLOW_SCREEN_HOME;
    state.snapshot.current.energy = 3;
    strcpy(state.snapshot.current.style, "hiphop");
    return state;
}

static void test_energy_path_and_bounds(void)
{
    flow_input_coordinator_t coordinator;
    flow_input_coordinator_init(&coordinator);
    flow_app_state_t state = ready_state();

    flow_input_action_t action = flow_input_handle_gesture(
        &coordinator, FLOW_GESTURE_MODE_ENERGY, &state);
    assert(action.type == FLOW_INPUT_OPEN_ENERGY);
    for (int i = 0; i < 5; ++i) {
        action = flow_input_handle_gesture(&coordinator,
                                           FLOW_GESTURE_PREVIEW_NEXT, &state);
    }
    assert(action.energy == 5);
    action = flow_input_handle_gesture(&coordinator, FLOW_GESTURE_SEND, &state);
    assert(action.type == FLOW_INPUT_SUBMIT_ENERGY);
    assert(action.energy == 5);
}

static void test_style_path(void)
{
    flow_input_coordinator_t coordinator;
    flow_input_coordinator_init(&coordinator);
    flow_app_state_t state = ready_state();
    flow_input_action_t action = flow_input_handle_gesture(
        &coordinator, FLOW_GESTURE_MODE_STYLE, &state);
    assert(action.type == FLOW_INPUT_OPEN_STYLE);
    action = flow_input_handle_gesture(&coordinator,
                                       FLOW_GESTURE_PREVIEW_NEXT, &state);
    assert(action.type == FLOW_INPUT_PREVIEW_STYLE);
    assert(strcmp(action.style, "breaking") == 0);
    action = flow_input_handle_gesture(&coordinator, FLOW_GESTURE_SEND, &state);
    assert(action.type == FLOW_INPUT_SUBMIT_STYLE);
    assert(strcmp(action.style, "breaking") == 0);
}

static void test_busy_and_touch_cancel(void)
{
    flow_input_coordinator_t coordinator;
    flow_input_coordinator_init(&coordinator);
    flow_app_state_t state = ready_state();
    state.snapshot.locked = true;
    assert(flow_input_handle_gesture(&coordinator, FLOW_GESTURE_MODE_ENERGY,
                                     &state).type == FLOW_INPUT_CANCEL);

    state = ready_state();
    state.screen = FLOW_SCREEN_TRANSITION;
    assert(flow_input_handle_gesture(&coordinator, FLOW_GESTURE_MODE_STYLE,
                                     &state).type == FLOW_INPUT_CANCEL);

    state = ready_state();
    assert(flow_input_handle_gesture(&coordinator, FLOW_GESTURE_MODE_STYLE,
                                     &state).type == FLOW_INPUT_OPEN_STYLE);
    assert(flow_input_handle_gesture(&coordinator, FLOW_GESTURE_CANCEL,
                                     &state).type == FLOW_INPUT_CANCEL);
}

int main(void)
{
    test_energy_path_and_bounds();
    test_style_path();
    test_busy_and_touch_cancel();
    puts("input coordinator tests passed");
    return 0;
}
