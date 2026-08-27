#pragma once

#include <stdbool.h>
#include <stdint.h>

#define FLOW_STYLE_ID_MAX 16
#define FLOW_SESSION_ID_LENGTH 16

typedef enum {
    FLOW_PHASE_IDLE,
    FLOW_PHASE_ACCEPTED,
    FLOW_PHASE_PREPARING,
    FLOW_PHASE_TRANSITIONING,
    FLOW_PHASE_COMPLETED,
    FLOW_PHASE_REJECTED,
    FLOW_PHASE_ERROR
} flow_phase_t;

typedef enum {
    FLOW_SCREEN_OFF,
    FLOW_SCREEN_CONNECTING,
    FLOW_SCREEN_HOME,
    FLOW_SCREEN_ENERGY,
    FLOW_SCREEN_STYLE,
    FLOW_SCREEN_SENDING,
    FLOW_SCREEN_TRANSITION,
    FLOW_SCREEN_COMPLETE,
    FLOW_SCREEN_ERROR
} flow_screen_t;

typedef enum {
    FLOW_LINK_ADVERTISING,
    FLOW_LINK_SECURING,
    FLOW_LINK_SYNCING_CATALOG,
    FLOW_LINK_SYNCING_STATE,
    FLOW_LINK_READY,
    FLOW_LINK_VERSION_MISMATCH,
} flow_link_state_t;

typedef struct {
    uint8_t energy;
    char style[FLOW_STYLE_ID_MAX];
    uint16_t bpm;
} flow_music_state_t;

typedef struct {
    char session_id[FLOW_SESSION_ID_LENGTH + 1];
    uint32_t revision;
    uint32_t ack_id;
    flow_phase_t phase;
    bool locked;
    uint32_t eta_ms;
    flow_music_state_t current;
    flow_music_state_t target;
    char error[24];
} flow_snapshot_t;

typedef struct {
    flow_screen_t screen;
    flow_link_state_t link_state;
    flow_snapshot_t snapshot;
    uint32_t pending_command_id;
    bool has_snapshot;
} flow_app_state_t;

typedef enum {
    FLOW_APPLY_OK,
    FLOW_APPLY_STALE,
    FLOW_APPLY_INVALID
} flow_apply_result_t;

typedef enum {
    FLOW_COMMAND_STARTED,
    FLOW_COMMAND_BLOCKED
} flow_command_result_t;

void flow_state_init(flow_app_state_t *state);
flow_apply_result_t flow_state_apply_snapshot(flow_app_state_t *state,
                                              const flow_snapshot_t *snapshot);
flow_command_result_t flow_state_begin_command(flow_app_state_t *state,
                                               uint32_t command_id);
bool flow_state_open_control(flow_app_state_t *state, flow_screen_t screen);
bool flow_state_view_home(flow_app_state_t *state);
flow_music_state_t flow_state_home_music(const flow_app_state_t *state,
                                         bool *is_preview);
void flow_state_return_home(flow_app_state_t *state);
