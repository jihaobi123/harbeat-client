#include "flow_ui_internal.h"

#include <stddef.h>

static flow_ui_action_handler_t s_action_handler;
static void *s_action_context;
static lv_obj_t *s_root;
static flow_screen_t s_last_screen = FLOW_SCREEN_OFF;
static flow_link_state_t s_last_link_state = FLOW_LINK_ADVERTISING;
static uint32_t s_last_revision;

static lv_obj_t *create_root(void)
{
    lv_obj_t *root = lv_obj_create(lv_screen_active());
    lv_obj_remove_style_all(root);
    lv_obj_set_size(root, LV_PCT(100), LV_PCT(100));
    lv_obj_set_pos(root, 0, 0);
    lv_obj_set_style_bg_color(root, flow_color_paper(), 0);
    lv_obj_set_style_bg_opa(root, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(root, 24, 0);
    lv_obj_clear_flag(root, LV_OBJ_FLAG_SCROLLABLE);
    return root;
}

static const char *status_title(const flow_app_state_t *state)
{
    switch (state->screen) {
    case FLOW_SCREEN_CONNECTING:
        return "FINDING THE HUB.";
    case FLOW_SCREEN_SENDING:
        return "SENDING THE SHIFT.";
    case FLOW_SCREEN_ERROR:
        return "THE SHIFT PAUSED.";
    case FLOW_SCREEN_OFF:
        return "";
    default:
        return "FLOW WRIST";
    }
}

static const char *status_detail(const flow_app_state_t *state)
{
    switch (state->screen) {
    case FLOW_SCREEN_CONNECTING:
        return "KEEP THE HUB CLOSE";
    case FLOW_SCREEN_SENDING:
        return "ONE MOMENT";
    case FLOW_SCREEN_ERROR:
        return state->snapshot.error[0] == '\0'
            ? "TRY AGAIN FROM HOME"
            : state->snapshot.error;
    default:
        return "READY";
    }
}

void flow_ui_status_create(lv_obj_t *root, const flow_app_state_t *state)
{
    lv_obj_set_flex_flow(root, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(root,
                          LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);

    lv_obj_t *mark = lv_obj_create(root);
    lv_obj_remove_style_all(mark);
    lv_obj_set_size(mark, 88, 88);
    lv_obj_set_style_radius(mark, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(mark, flow_color_yellow(), 0);
    lv_obj_set_style_bg_opa(mark, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(mark, flow_color_ink(), 0);
    lv_obj_set_style_border_width(mark, 3, 0);

    lv_obj_t *dot = lv_obj_create(mark);
    lv_obj_remove_style_all(dot);
    lv_obj_set_size(dot, 18, 18);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(dot, flow_color_ink(), 0);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
    lv_obj_center(dot);

    lv_obj_t *title = lv_label_create(root);
    lv_label_set_text(title, status_title(state));
    lv_obj_set_width(title, LV_PCT(100));
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(title, flow_color_ink(), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_26, 0);

    lv_obj_t *detail = lv_label_create(root);
    lv_label_set_text(detail, status_detail(state));
    lv_obj_set_style_text_color(detail, flow_color_muted(), 0);
    lv_obj_set_style_text_font(detail, &lv_font_montserrat_12, 0);
    lv_obj_set_style_pad_top(detail, 10, 0);
}

static void render_named_status(const char *title_text, const char *detail_text)
{
    flow_app_state_t state = {0};
    state.screen = FLOW_SCREEN_CONNECTING;
    if (s_root != NULL) {
        lv_obj_delete(s_root);
    }
    s_root = create_root();
    s_last_screen = FLOW_SCREEN_CONNECTING;
    flow_ui_status_create(s_root, &state);

    lv_obj_t *title = lv_obj_get_child(s_root, 1);
    lv_obj_t *detail = lv_obj_get_child(s_root, 2);
    lv_label_set_text(title, title_text);
    lv_label_set_text(detail, detail_text);
}

void flow_ui_init(flow_ui_action_handler_t handler, void *context)
{
    s_action_handler = handler;
    s_action_context = context;
}

void flow_ui_emit(const flow_ui_action_t *action)
{
    if (s_action_handler != NULL && action != NULL) {
        s_action_handler(action, s_action_context);
    }
}

void flow_ui_render(const flow_app_state_t *state)
{
    if (state == NULL) {
        return;
    }
    if (s_root != NULL && state->screen == s_last_screen &&
        state->link_state == s_last_link_state) {
        if (state->screen == FLOW_SCREEN_TRANSITION) {
            flow_ui_transition_update(state);
            s_last_revision = state->snapshot.revision;
            return;
        }
        if (state->snapshot.revision == s_last_revision) {
            return;
        }
    }
    if (s_root != NULL) {
        lv_obj_delete(s_root);
    }

    s_root = create_root();
    s_last_screen = state->screen;
    s_last_link_state = state->link_state;
    s_last_revision = state->snapshot.revision;
    if (state->link_state != FLOW_LINK_READY) {
        if (state->screen == FLOW_SCREEN_HOME) {
            flow_ui_home_create(s_root, state);
            flow_ui_offline_overlay(s_root);
        } else {
            flow_ui_connection_create(s_root, state);
        }
        return;
    }
    switch (state->screen) {
    case FLOW_SCREEN_HOME:
        flow_ui_home_create(s_root, state);
        break;
    case FLOW_SCREEN_ENERGY:
    case FLOW_SCREEN_STYLE:
        flow_ui_carousel_create(s_root, state);
        break;
    case FLOW_SCREEN_TRANSITION:
        flow_ui_transition_create(s_root, state);
        break;
    case FLOW_SCREEN_COMPLETE:
        flow_ui_complete_create(s_root, state);
        break;
    case FLOW_SCREEN_ERROR:
        flow_ui_error_create(s_root, state);
        break;
    default:
        flow_ui_status_create(s_root, state);
        break;
    }
}

void flow_ui_show_offline(void)
{
    render_named_status("HUB IS OFFLINE.", "MOVE CLOSER AND WAKE IT");
}

void flow_ui_show_syncing(void)
{
    render_named_status("SYNCING THE ROOM.", "WAIT FOR THE CURRENT TRACK");
}
