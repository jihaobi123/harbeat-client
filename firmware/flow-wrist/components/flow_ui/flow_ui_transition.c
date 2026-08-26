#include "flow_ui_internal.h"

#include <stdint.h>
#include <string.h>

static lv_obj_t *s_countdown_label;
static lv_obj_t *s_phase_label;
static lv_obj_t *s_energy_label;
static lv_obj_t *s_bpm_label;
static lv_obj_t *s_busy_feedback;
static lv_timer_t *s_complete_timer;

static lv_obj_t *card(lv_obj_t *root,
                      int32_t x,
                      int32_t y,
                      int32_t width,
                      int32_t height,
                      lv_color_t color)
{
    lv_obj_t *object = lv_obj_create(root);
    lv_obj_set_pos(object, x, y);
    lv_obj_set_size(object, width, height);
    lv_obj_set_style_radius(object, 18, 0);
    lv_obj_set_style_bg_color(object, color, 0);
    lv_obj_set_style_bg_opa(object, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(object, flow_color_ink(), 0);
    lv_obj_set_style_border_width(object, 2, 0);
    lv_obj_set_style_pad_all(object, 12, 0);
    lv_obj_clear_flag(object, LV_OBJ_FLAG_SCROLLABLE);
    return object;
}

static const char *phase_text(flow_phase_t phase)
{
    switch (phase) {
    case FLOW_PHASE_ACCEPTED:
        return "COMMAND ACCEPTED";
    case FLOW_PHASE_PREPARING:
        return "PREPARING THE NEXT TRACK";
    case FLOW_PHASE_TRANSITIONING:
        return "MUSIC IS TRANSITIONING";
    default:
        return "CHANGE IS IN MOTION";
    }
}

static void hide_busy_cb(lv_timer_t *timer)
{
    (void)timer;
    if (s_busy_feedback != NULL) {
        lv_obj_add_flag(s_busy_feedback, LV_OBJ_FLAG_HIDDEN);
    }
}

static void transition_touch_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) != LV_EVENT_CLICKED || s_busy_feedback == NULL) {
        return;
    }
    lv_obj_clear_flag(s_busy_feedback, LV_OBJ_FLAG_HIDDEN);
    lv_timer_t *timer = lv_timer_create(hide_busy_cb, 1200, NULL);
    lv_timer_set_repeat_count(timer, 1);
}

static void create_record_card(lv_obj_t *root,
                               int32_t x,
                               const char *eyebrow,
                               const char *style,
                               lv_color_t color)
{
    lv_obj_t *cover = card(root, x, 76, 171, 194, color);
    lv_obj_t *small = lv_label_create(cover);
    lv_label_set_text(small, eyebrow);
    lv_obj_set_style_text_font(small, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(small, flow_color_ink(), 0);

    lv_obj_t *art = lv_obj_create(cover);
    lv_obj_remove_style_all(art);
    lv_obj_align(art, LV_ALIGN_CENTER, 0, -6);
    flow_ui_art_record(art, color);
    lv_obj_set_style_transform_scale(art, 190, 0);

    lv_obj_t *style_label = lv_label_create(cover);
    lv_label_set_text(style_label, style);
    lv_obj_align(style_label, LV_ALIGN_BOTTOM_LEFT, 0, 0);
    lv_obj_set_width(style_label, LV_PCT(100));
    lv_obj_set_style_text_font(style_label, &lv_font_montserrat_18, 0);
    lv_obj_set_style_text_color(style_label, flow_color_ink(), 0);
}

void flow_ui_transition_update(const flow_app_state_t *state)
{
    const uint32_t seconds = (state->snapshot.eta_ms + 999U) / 1000U;
    if (s_countdown_label != NULL) {
        lv_label_set_text_fmt(s_countdown_label, "NEXT TRACK  %lus", (unsigned long)seconds);
    }
    if (s_phase_label != NULL) {
        lv_label_set_text(s_phase_label, phase_text(state->snapshot.phase));
    }
    if (s_energy_label != NULL) {
        lv_label_set_text_fmt(s_energy_label,
                              "ENERGY\n%02u / 05",
                              state->snapshot.target.energy);
    }
    if (s_bpm_label != NULL) {
        lv_label_set_text_fmt(s_bpm_label,
                              "BPM\n%u",
                              state->snapshot.target.bpm);
    }
}

void flow_ui_transition_create(lv_obj_t *root, const flow_app_state_t *state)
{
    s_complete_timer = NULL;
    lv_obj_add_flag(root, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(root, transition_touch_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *title = lv_label_create(root);
    lv_label_set_text(title, "CHANGE IS IN MOTION.");
    lv_obj_set_style_text_font(title, &lv_font_montserrat_22, 0);
    lv_obj_set_style_text_color(title, flow_color_ink(), 0);

    s_phase_label = lv_label_create(root);
    lv_obj_align(s_phase_label, LV_ALIGN_TOP_RIGHT, 0, 32);
    lv_obj_set_style_text_font(s_phase_label, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(s_phase_label, flow_color_green(), 0);

    create_record_card(root,
                       0,
                       "NOW",
                       state->snapshot.current.style,
                       flow_color_pink());
    create_record_card(root,
                       191,
                       "NEXT",
                       state->snapshot.target.style,
                       flow_color_blue());

    lv_obj_t *countdown = card(root, 0, 286, 362, 72, flow_color_yellow());
    s_countdown_label = lv_label_create(countdown);
    lv_obj_center(s_countdown_label);
    lv_obj_set_style_text_font(s_countdown_label, &lv_font_montserrat_26, 0);
    lv_obj_set_style_text_color(s_countdown_label, flow_color_ink(), 0);

    lv_obj_t *energy = card(root, 0, 372, 171, 68, flow_color_paper());
    s_energy_label = lv_label_create(energy);
    lv_obj_center(s_energy_label);
    lv_obj_set_style_text_align(s_energy_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_font(s_energy_label, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(s_energy_label, flow_color_ink(), 0);

    lv_obj_t *bpm = card(root, 191, 372, 171, 68, flow_color_paper());
    s_bpm_label = lv_label_create(bpm);
    lv_obj_center(s_bpm_label);
    lv_obj_set_style_text_align(s_bpm_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_font(s_bpm_label, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(s_bpm_label, flow_color_ink(), 0);

    s_busy_feedback = lv_label_create(root);
    lv_label_set_text(s_busy_feedback, "PREVIOUS SHIFT IS STILL RUNNING");
    lv_obj_align(s_busy_feedback, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_text_font(s_busy_feedback, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(s_busy_feedback, flow_color_pink(), 0);
    lv_obj_add_flag(s_busy_feedback, LV_OBJ_FLAG_HIDDEN);

    flow_ui_transition_update(state);
}

static void complete_timer_cb(lv_timer_t *timer)
{
    (void)timer;
    s_complete_timer = NULL;
    const flow_ui_action_t action = {.type = FLOW_UI_ACTION_COMPLETE_TIMEOUT};
    flow_ui_emit(&action);
}

static void complete_root_delete_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) == LV_EVENT_DELETE && s_complete_timer != NULL) {
        lv_timer_delete(s_complete_timer);
        s_complete_timer = NULL;
    }
}

void flow_ui_complete_create(lv_obj_t *root, const flow_app_state_t *state)
{
    lv_obj_set_flex_flow(root, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(root,
                          LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);

    lv_obj_t *check = lv_obj_create(root);
    lv_obj_remove_style_all(check);
    lv_obj_set_size(check, 112, 112);
    lv_obj_set_style_radius(check, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(check, flow_color_green(), 0);
    lv_obj_set_style_bg_opa(check, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(check, flow_color_ink(), 0);
    lv_obj_set_style_border_width(check, 3, 0);
    lv_obj_t *check_label = lv_label_create(check);
    lv_label_set_text(check_label, "OK");
    lv_obj_center(check_label);
    lv_obj_set_style_text_font(check_label, &lv_font_montserrat_26, 0);
    lv_obj_set_style_text_color(check_label, flow_color_paper(), 0);

    lv_obj_t *title = lv_label_create(root);
    lv_label_set_text_fmt(title, "%s IS LIVE", state->snapshot.current.style);
    lv_obj_set_width(title, LV_PCT(100));
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_26, 0);
    lv_obj_set_style_text_color(title, flow_color_ink(), 0);

    lv_obj_t *detail = lv_label_create(root);
    lv_label_set_text_fmt(detail,
                          "ENERGY %02u  /  %u BPM",
                          state->snapshot.current.energy,
                          state->snapshot.current.bpm);
    lv_obj_set_style_text_font(detail, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(detail, flow_color_muted(), 0);

    lv_obj_add_event_cb(root, complete_root_delete_cb, LV_EVENT_DELETE, NULL);
    s_complete_timer = lv_timer_create(complete_timer_cb, 2000, NULL);
    lv_timer_set_repeat_count(s_complete_timer, 1);
}

static const char *error_message(const char *error)
{
    if (strcmp(error, "busy") == 0) {
        return "THE PREVIOUS SHIFT\nIS STILL RUNNING";
    }
    if (strcmp(error, "invalid_energy") == 0) {
        return "THAT ENERGY LEVEL\nIS NOT AVAILABLE";
    }
    if (strcmp(error, "unknown_style") == 0) {
        return "THE STYLE LIST\nHAS CHANGED";
    }
    if (strcmp(error, "version_mismatch") == 0) {
        return "WRIST UPDATE\nREQUIRED";
    }
    return "THE HUB COULD NOT\nFINISH THE SHIFT";
}

static void error_back_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) == LV_EVENT_CLICKED) {
        const flow_ui_action_t action = {.type = FLOW_UI_ACTION_BACK};
        flow_ui_emit(&action);
    }
}

void flow_ui_error_create(lv_obj_t *root, const flow_app_state_t *state)
{
    lv_obj_set_flex_flow(root, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(root,
                          LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);
    lv_obj_add_flag(root, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(root, error_back_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *mark = lv_label_create(root);
    lv_label_set_text(mark, "!");
    lv_obj_set_style_text_font(mark, &lv_font_montserrat_26, 0);
    lv_obj_set_style_text_color(mark, flow_color_pink(), 0);

    lv_obj_t *title = lv_label_create(root);
    lv_label_set_text(title, error_message(state->snapshot.error));
    lv_obj_set_width(title, LV_PCT(100));
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_22, 0);
    lv_obj_set_style_text_color(title, flow_color_ink(), 0);

    lv_obj_t *detail = lv_label_create(root);
    lv_label_set_text(detail, "TAP TO RETURN");
    lv_obj_set_style_text_font(detail, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(detail, flow_color_muted(), 0);
}
