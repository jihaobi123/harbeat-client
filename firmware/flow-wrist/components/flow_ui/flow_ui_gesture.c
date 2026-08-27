#include "flow_ui_internal.h"

#include <stddef.h>

static lv_obj_t *s_overlay;
static lv_obj_t *s_title;
static lv_obj_t *s_detail;
static lv_obj_t *s_progress;
static lv_timer_t *s_hide_timer;

static void set_progress(void *object, int32_t value)
{
    lv_bar_set_value((lv_obj_t *)object, value, LV_ANIM_OFF);
}

static void hide_overlay_cb(lv_timer_t *timer)
{
    (void)timer;
    s_hide_timer = NULL;
    if (s_overlay != NULL) {
        lv_obj_add_flag(s_overlay, LV_OBJ_FLAG_HIDDEN);
    }
}

static void hide_after(uint32_t milliseconds)
{
    if (s_hide_timer != NULL) {
        lv_timer_delete(s_hide_timer);
    }
    s_hide_timer = lv_timer_create(hide_overlay_cb, milliseconds, NULL);
    lv_timer_set_repeat_count(s_hide_timer, 1);
}

static void ensure_overlay(void)
{
    if (s_overlay != NULL) {
        return;
    }
    s_overlay = lv_obj_create(lv_screen_active());
    lv_obj_set_size(s_overlay, 300, 74);
    lv_obj_align(s_overlay, LV_ALIGN_BOTTOM_MID, 0, -20);
    lv_obj_set_style_radius(s_overlay, 18, 0);
    lv_obj_set_style_bg_color(s_overlay, flow_color_paper(), 0);
    lv_obj_set_style_bg_opa(s_overlay, LV_OPA_90, 0);
    lv_obj_set_style_border_color(s_overlay, flow_color_ink(), 0);
    lv_obj_set_style_border_width(s_overlay, 2, 0);
    lv_obj_set_style_pad_all(s_overlay, 10, 0);
    lv_obj_clear_flag(s_overlay, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(s_overlay, LV_OBJ_FLAG_HIDDEN);

    s_title = lv_label_create(s_overlay);
    lv_obj_align(s_title, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_text_font(s_title, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(s_title, flow_color_ink(), 0);

    s_detail = lv_label_create(s_overlay);
    lv_obj_align(s_detail, LV_ALIGN_TOP_RIGHT, 0, 1);
    lv_obj_set_style_text_font(s_detail, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(s_detail, flow_color_muted(), 0);

    s_progress = lv_bar_create(s_overlay);
    lv_obj_set_size(s_progress, LV_PCT(100), 8);
    lv_obj_align(s_progress, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_radius(s_progress, 4, LV_PART_MAIN);
    lv_obj_set_style_radius(s_progress, 4, LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(s_progress, flow_color_ink(), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(s_progress, LV_OPA_20, LV_PART_MAIN);
    lv_obj_set_style_bg_color(s_progress, flow_color_pink(), LV_PART_INDICATOR);
    lv_bar_set_range(s_progress, 0, 100);
}

static void show(const char *title, const char *detail, int start, int end,
                 uint32_t duration_ms, uint32_t visible_ms)
{
    ensure_overlay();
    lv_obj_move_foreground(s_overlay);
    lv_label_set_text(s_title, title);
    lv_label_set_text(s_detail, detail);
    lv_obj_clear_flag(s_overlay, LV_OBJ_FLAG_HIDDEN);
    lv_anim_delete(s_progress, set_progress);
    lv_bar_set_value(s_progress, start, LV_ANIM_OFF);
    if (duration_ms > 0) {
        lv_anim_t animation;
        lv_anim_init(&animation);
        lv_anim_set_var(&animation, s_progress);
        lv_anim_set_exec_cb(&animation, set_progress);
        lv_anim_set_values(&animation, start, end);
        lv_anim_set_duration(&animation, duration_ms);
        lv_anim_set_path_cb(&animation, lv_anim_path_ease_in_out);
        lv_anim_start(&animation);
    }
    hide_after(visible_ms);
}

void flow_ui_apply_gesture(const flow_input_action_t *action)
{
    if (action == NULL) {
        return;
    }
    switch (action->type) {
    case FLOW_INPUT_READY:
        show("GESTURE READY", "ROLL L + R", 0, 100, 500, 1000);
        break;
    case FLOW_INPUT_ARMED:
        show("ARMED", "5 SEC", 100, 0, 5000, 5000);
        break;
    case FLOW_INPUT_OPEN_ENERGY:
        show("ENERGY", "ROLL TO PREVIEW", 0, 0, 0, 1200);
        break;
    case FLOW_INPUT_OPEN_STYLE:
        show("STYLE", "ROLL TO PREVIEW", 0, 0, 0, 1200);
        break;
    case FLOW_INPUT_PREVIEW_ENERGY:
        flow_ui_carousel_set_energy(action->energy);
        show("HOLD TO CONFIRM", "ENERGY", 0, 0, 0, 1100);
        break;
    case FLOW_INPUT_PREVIEW_STYLE:
        flow_ui_carousel_set_style(action->style);
        show("HOLD TO CONFIRM", "STYLE", 0, 0, 0, 1100);
        break;
    case FLOW_INPUT_CONFIRMING:
        show("CONFIRMING", "KEEP STILL", 0, 100, 300, 450);
        break;
    case FLOW_INPUT_CANCEL:
        show("CANCELLED", "", 0, 0, 0, 450);
        break;
    case FLOW_INPUT_SUBMIT_ENERGY:
    case FLOW_INPUT_SUBMIT_STYLE:
        if (s_overlay != NULL) {
            lv_obj_add_flag(s_overlay, LV_OBJ_FLAG_HIDDEN);
        }
        break;
    case FLOW_INPUT_NONE:
        break;
    }
}
