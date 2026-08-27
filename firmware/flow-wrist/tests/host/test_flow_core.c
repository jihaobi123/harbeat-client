#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "flow_core.h"

static flow_snapshot_t make_snapshot(uint32_t revision,
                                     flow_phase_t phase,
                                     bool locked)
{
    flow_snapshot_t value = {0};
    strcpy(value.session_id, "8f3a19d04b7c221e");
    value.revision = revision;
    value.phase = phase;
    value.locked = locked;
    value.current.energy = 3;
    strcpy(value.current.style, "hiphop");
    value.current.bpm = 96;
    value.target.energy = 5;
    strcpy(value.target.style, "breaking");
    value.target.bpm = 108;
    value.eta_ms = 14000;
    return value;
}

static void test_connecting_to_home_and_navigation(void)
{
    flow_app_state_t state;
    flow_state_init(&state);
    assert(state.screen == FLOW_SCREEN_CONNECTING);
    assert(!flow_state_open_control(&state, FLOW_SCREEN_STYLE));

    flow_snapshot_t first = make_snapshot(7, FLOW_PHASE_IDLE, false);
    assert(flow_state_apply_snapshot(&state, &first) == FLOW_APPLY_OK);
    assert(state.screen == FLOW_SCREEN_HOME);

    assert(flow_state_open_control(&state, FLOW_SCREEN_STYLE));
    assert(state.screen == FLOW_SCREEN_STYLE);
    flow_state_return_home(&state);
    assert(state.screen == FLOW_SCREEN_HOME);
    assert(!flow_state_open_control(&state, FLOW_SCREEN_COMPLETE));
}

static void test_offline_home_can_browse_controls_but_not_send(void)
{
    flow_app_state_t state;
    flow_state_init(&state);
    assert(flow_state_view_home(&state));
    assert(state.screen == FLOW_SCREEN_HOME);
    assert(!state.has_snapshot);
    assert(flow_state_open_control(&state, FLOW_SCREEN_ENERGY));
    assert(state.screen == FLOW_SCREEN_ENERGY);
    flow_state_return_home(&state);
    assert(state.screen == FLOW_SCREEN_HOME);
    assert(flow_state_open_control(&state, FLOW_SCREEN_STYLE));
    assert(state.screen == FLOW_SCREEN_STYLE);
    assert(flow_state_begin_command(&state, 42) == FLOW_COMMAND_BLOCKED);

    state.screen = FLOW_SCREEN_TRANSITION;
    state.snapshot.locked = true;
    assert(!flow_state_view_home(&state));
    assert(state.screen == FLOW_SCREEN_TRANSITION);
}

static void test_offline_home_uses_full_preview_music(void)
{
    flow_app_state_t state;
    flow_state_init(&state);

    bool preview = false;
    flow_music_state_t music = flow_state_home_music(&state, &preview);
    assert(preview);
    assert(music.energy == 3);
    assert(strcmp(music.style, "hiphop") == 0);
    assert(music.bpm == 96);

    state.has_snapshot = true;
    state.snapshot.current.energy = 5;
    strcpy(state.snapshot.current.style, "locking");
    state.snapshot.current.bpm = 112;
    music = flow_state_home_music(&state, &preview);
    assert(!preview);
    assert(music.energy == 5);
    assert(strcmp(music.style, "locking") == 0);
    assert(music.bpm == 112);
}

static void test_global_lock_and_transition(void)
{
    flow_app_state_t state;
    flow_state_init(&state);
    flow_snapshot_t first = make_snapshot(7, FLOW_PHASE_IDLE, false);
    assert(flow_state_apply_snapshot(&state, &first) == FLOW_APPLY_OK);

    assert(flow_state_begin_command(&state, 42) == FLOW_COMMAND_STARTED);
    assert(state.screen == FLOW_SCREEN_SENDING);
    assert(flow_state_begin_command(&state, 43) == FLOW_COMMAND_BLOCKED);
    flow_state_return_home(&state);
    assert(state.screen == FLOW_SCREEN_SENDING);

    flow_snapshot_t busy = make_snapshot(8, FLOW_PHASE_PREPARING, true);
    busy.ack_id = 42;
    assert(flow_state_apply_snapshot(&state, &busy) == FLOW_APPLY_OK);
    assert(state.screen == FLOW_SCREEN_TRANSITION);
    assert(!flow_state_open_control(&state, FLOW_SCREEN_ENERGY));
    flow_state_return_home(&state);
    assert(state.screen == FLOW_SCREEN_TRANSITION);

    flow_snapshot_t rejected_busy = make_snapshot(9, FLOW_PHASE_REJECTED, true);
    rejected_busy.ack_id = 43;
    strcpy(rejected_busy.error, "busy");
    assert(flow_state_apply_snapshot(&state, &rejected_busy) == FLOW_APPLY_OK);
    assert(state.screen == FLOW_SCREEN_TRANSITION);
}

static void test_revisions_completion_and_new_session(void)
{
    flow_app_state_t state;
    flow_state_init(&state);
    flow_snapshot_t busy = make_snapshot(8, FLOW_PHASE_TRANSITIONING, true);
    assert(flow_state_apply_snapshot(&state, &busy) == FLOW_APPLY_OK);

    flow_snapshot_t stale = make_snapshot(7, FLOW_PHASE_COMPLETED, false);
    assert(flow_state_apply_snapshot(&state, &stale) == FLOW_APPLY_STALE);
    assert(state.screen == FLOW_SCREEN_TRANSITION);

    flow_snapshot_t done = make_snapshot(9, FLOW_PHASE_COMPLETED, false);
    done.eta_ms = 0;
    done.current = done.target;
    assert(flow_state_apply_snapshot(&state, &done) == FLOW_APPLY_OK);
    assert(state.screen == FLOW_SCREEN_COMPLETE);

    flow_state_return_home(&state);
    assert(state.screen == FLOW_SCREEN_HOME);

    flow_snapshot_t restarted = make_snapshot(1, FLOW_PHASE_IDLE, false);
    strcpy(restarted.session_id, "0123456789abcdef");
    assert(flow_state_apply_snapshot(&state, &restarted) == FLOW_APPLY_OK);
    assert(state.snapshot.revision == 1);
}

static void test_invalid_snapshots_are_ignored(void)
{
    flow_app_state_t state;
    flow_state_init(&state);

    flow_snapshot_t invalid = make_snapshot(1, FLOW_PHASE_IDLE, false);
    invalid.current.energy = 0;
    assert(flow_state_apply_snapshot(&state, &invalid) == FLOW_APPLY_INVALID);
    assert(!state.has_snapshot);

    invalid = make_snapshot(1, FLOW_PHASE_IDLE, false);
    invalid.target.energy = 6;
    assert(flow_state_apply_snapshot(&state, &invalid) == FLOW_APPLY_INVALID);

    invalid = make_snapshot(1, FLOW_PHASE_IDLE, false);
    invalid.current.style[0] = '\0';
    assert(flow_state_apply_snapshot(&state, &invalid) == FLOW_APPLY_INVALID);

    invalid = make_snapshot(1, FLOW_PHASE_IDLE, false);
    strcpy(invalid.session_id, "too-short");
    assert(flow_state_apply_snapshot(&state, &invalid) == FLOW_APPLY_INVALID);
}

int main(void)
{
    test_connecting_to_home_and_navigation();
    test_offline_home_can_browse_controls_but_not_send();
    test_offline_home_uses_full_preview_music();
    test_global_lock_and_transition();
    test_revisions_completion_and_new_session();
    test_invalid_snapshots_are_ignored();
    puts("flow_core tests passed");
    return 0;
}
