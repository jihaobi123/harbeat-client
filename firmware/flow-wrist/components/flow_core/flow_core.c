#include "flow_core.h"

#include <stddef.h>
#include <string.h>

static bool has_terminated_text(const char *text, size_t capacity)
{
    return text[0] != '\0' && memchr(text, '\0', capacity) != NULL;
}

static bool has_exact_session_id(const char *session_id)
{
    const char *terminator = memchr(session_id, '\0', FLOW_SESSION_ID_LENGTH + 1);
    return terminator == session_id + FLOW_SESSION_ID_LENGTH;
}

static bool error_equals(const char *error, const char *expected)
{
    return memchr(error, '\0', sizeof(((flow_snapshot_t *)0)->error)) != NULL &&
           strcmp(error, expected) == 0;
}

static bool valid_snapshot(const flow_snapshot_t *snapshot)
{
    if (snapshot == NULL || !has_exact_session_id(snapshot->session_id)) {
        return false;
    }
    if (snapshot->phase < FLOW_PHASE_IDLE || snapshot->phase > FLOW_PHASE_ERROR) {
        return false;
    }
    if (snapshot->current.energy < 1 || snapshot->current.energy > 5 ||
        snapshot->target.energy < 1 || snapshot->target.energy > 5) {
        return false;
    }
    return has_terminated_text(snapshot->current.style, FLOW_STYLE_ID_MAX) &&
           has_terminated_text(snapshot->target.style, FLOW_STYLE_ID_MAX);
}

void flow_state_init(flow_app_state_t *state)
{
    memset(state, 0, sizeof(*state));
    state->screen = FLOW_SCREEN_CONNECTING;
}

flow_command_result_t flow_state_begin_command(flow_app_state_t *state,
                                               uint32_t command_id)
{
    if (!state->has_snapshot || state->snapshot.locked ||
        state->screen == FLOW_SCREEN_SENDING ||
        state->screen == FLOW_SCREEN_TRANSITION) {
        return FLOW_COMMAND_BLOCKED;
    }

    state->pending_command_id = command_id;
    state->screen = FLOW_SCREEN_SENDING;
    return FLOW_COMMAND_STARTED;
}

bool flow_state_open_control(flow_app_state_t *state, flow_screen_t screen)
{
    if (!state->has_snapshot || state->snapshot.locked ||
        (screen != FLOW_SCREEN_ENERGY && screen != FLOW_SCREEN_STYLE)) {
        return false;
    }

    state->screen = screen;
    return true;
}

bool flow_state_view_home(flow_app_state_t *state)
{
    if (state == NULL || state->snapshot.locked ||
        state->screen == FLOW_SCREEN_SENDING ||
        state->screen == FLOW_SCREEN_TRANSITION) {
        return false;
    }
    state->screen = FLOW_SCREEN_HOME;
    return true;
}

void flow_state_return_home(flow_app_state_t *state)
{
    if (state->has_snapshot && !state->snapshot.locked &&
        state->screen != FLOW_SCREEN_SENDING &&
        state->screen != FLOW_SCREEN_TRANSITION) {
        state->screen = FLOW_SCREEN_HOME;
    }
}

flow_apply_result_t flow_state_apply_snapshot(flow_app_state_t *state,
                                              const flow_snapshot_t *snapshot)
{
    if (!valid_snapshot(snapshot)) {
        return FLOW_APPLY_INVALID;
    }

    const bool same_session = state->has_snapshot &&
        strcmp(state->snapshot.session_id, snapshot->session_id) == 0;
    if (same_session && snapshot->revision <= state->snapshot.revision) {
        return FLOW_APPLY_STALE;
    }

    state->snapshot = *snapshot;
    state->has_snapshot = true;
    if (state->pending_command_id != 0 &&
        snapshot->ack_id == state->pending_command_id) {
        state->pending_command_id = 0;
    }

    switch (snapshot->phase) {
    case FLOW_PHASE_IDLE:
        state->screen = FLOW_SCREEN_HOME;
        break;
    case FLOW_PHASE_ACCEPTED:
    case FLOW_PHASE_PREPARING:
    case FLOW_PHASE_TRANSITIONING:
        state->screen = FLOW_SCREEN_TRANSITION;
        break;
    case FLOW_PHASE_COMPLETED:
        state->screen = FLOW_SCREEN_COMPLETE;
        break;
    case FLOW_PHASE_REJECTED:
        if (snapshot->locked && error_equals(snapshot->error, "busy")) {
            state->screen = FLOW_SCREEN_TRANSITION;
            break;
        }
        state->screen = FLOW_SCREEN_ERROR;
        break;
    case FLOW_PHASE_ERROR:
        state->screen = FLOW_SCREEN_ERROR;
        break;
    }

    return FLOW_APPLY_OK;
}
