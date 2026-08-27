#include "flow_ui_internal.h"

static const char *connection_title(flow_link_state_t state)
{
    switch (state) {
    case FLOW_LINK_SECURING:
        return "SECURING THE LINK.";
    case FLOW_LINK_SYNCING_CATALOG:
        return "SYNCING THE ROOM.";
    case FLOW_LINK_SYNCING_STATE:
        return "READING THE FLOOR.";
    case FLOW_LINK_VERSION_MISMATCH:
        return "UPDATE REQUIRED.";
    default:
        return "FINDING THE HUB.";
    }
}

static const char *connection_detail(flow_link_state_t state)
{
    switch (state) {
    case FLOW_LINK_SECURING:
        return "PAIRING WITH RK3588";
    case FLOW_LINK_SYNCING_CATALOG:
        return "LOADING ENERGY + STYLES";
    case FLOW_LINK_SYNCING_STATE:
        return "GETTING CURRENT TRACK";
    case FLOW_LINK_VERSION_MISMATCH:
        return "FLOW HUB USES ANOTHER VERSION";
    default:
        return "OPEN FLOW HUB TO CONNECT";
    }
}

static void set_dot_opacity(void *object, int32_t opacity)
{
    lv_obj_set_style_opa((lv_obj_t *)object, (lv_opa_t)opacity, 0);
}

static void set_sweep_width(void *object, int32_t width)
{
    lv_obj_set_width((lv_obj_t *)object, width);
}

static void view_home_event_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) == LV_EVENT_CLICKED) {
        const flow_ui_action_t action = {.type = FLOW_UI_ACTION_VIEW_HOME};
        flow_ui_emit(&action);
    }
}

void flow_ui_connection_create(lv_obj_t *root, const flow_app_state_t *state)
{
    lv_obj_set_flex_flow(root, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(root,
                          LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);

    lv_obj_t *mark = lv_obj_create(root);
    lv_obj_remove_style_all(mark);
    lv_obj_set_size(mark, 96, 96);
    lv_obj_set_style_radius(mark, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(mark, flow_color_yellow(), 0);
    lv_obj_set_style_bg_opa(mark, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(mark, flow_color_ink(), 0);
    lv_obj_set_style_border_width(mark, 3, 0);

    for (uint8_t index = 0; index < 3; ++index) {
        lv_obj_t *dot = lv_obj_create(mark);
        lv_obj_remove_style_all(dot);
        lv_obj_set_size(dot, 12, 12);
        lv_obj_set_pos(dot, 22 + (int32_t)index * 20, 42);
        lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_bg_color(dot, flow_color_ink(), 0);
        lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
        if (state->link_state != FLOW_LINK_VERSION_MISMATCH) {
            lv_anim_t pulse;
            lv_anim_init(&pulse);
            lv_anim_set_var(&pulse, dot);
            lv_anim_set_exec_cb(&pulse, set_dot_opacity);
            lv_anim_set_values(&pulse, LV_OPA_30, LV_OPA_COVER);
            lv_anim_set_duration(&pulse, 360);
            lv_anim_set_playback_duration(&pulse, 360);
            lv_anim_set_repeat_count(&pulse, LV_ANIM_REPEAT_INFINITE);
            lv_anim_set_delay(&pulse, (uint32_t)index * 120);
            lv_anim_start(&pulse);
        }
    }

    lv_obj_t *title = lv_label_create(root);
    lv_label_set_text(title, connection_title(state->link_state));
    lv_obj_set_width(title, LV_PCT(100));
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(title, flow_color_ink(), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_26, 0);

    lv_obj_t *detail = lv_label_create(root);
    lv_label_set_text(detail, connection_detail(state->link_state));
    lv_obj_set_style_text_color(detail, flow_color_muted(), 0);
    lv_obj_set_style_text_font(detail, &lv_font_montserrat_12, 0);
    lv_obj_set_style_pad_top(detail, 10, 0);

    if (state->link_state != FLOW_LINK_VERSION_MISMATCH) {
        lv_obj_t *track = lv_obj_create(root);
        lv_obj_remove_style_all(track);
        lv_obj_set_size(track, 230, 5);
        lv_obj_set_style_radius(track, 3, 0);
        lv_obj_set_style_bg_color(track, flow_color_muted(), 0);
        lv_obj_set_style_bg_opa(track, LV_OPA_30, 0);
        lv_obj_set_style_pad_top(track, 18, 0);

        lv_obj_t *sweep = lv_obj_create(track);
        lv_obj_remove_style_all(sweep);
        lv_obj_set_height(sweep, 5);
        lv_obj_set_style_radius(sweep, 3, 0);
        lv_obj_set_style_bg_color(sweep, flow_color_pink(), 0);
        lv_obj_set_style_bg_opa(sweep, LV_OPA_COVER, 0);
        lv_anim_t scan;
        lv_anim_init(&scan);
        lv_anim_set_var(&scan, sweep);
        lv_anim_set_exec_cb(&scan, set_sweep_width);
        lv_anim_set_values(&scan, 24, 230);
        lv_anim_set_duration(&scan, 900);
        lv_anim_set_repeat_count(&scan, LV_ANIM_REPEAT_INFINITE);
        lv_anim_set_path_cb(&scan, lv_anim_path_ease_in_out);
        lv_anim_start(&scan);
    }

    lv_obj_t *view_home = lv_button_create(root);
    lv_obj_set_size(view_home, 250, 56);
    lv_obj_set_style_radius(view_home, 16, 0);
    lv_obj_set_style_bg_color(view_home, flow_color_paper(), 0);
    lv_obj_set_style_border_color(view_home, flow_color_ink(), 0);
    lv_obj_set_style_border_width(view_home, 3, 0);
    lv_obj_set_style_shadow_width(view_home, 0, 0);
    lv_obj_add_event_cb(view_home, view_home_event_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *view_home_label = lv_label_create(view_home);
    lv_label_set_text(view_home_label, "VIEW HOME");
    lv_obj_center(view_home_label);
    lv_obj_set_style_text_font(view_home_label, &lv_font_montserrat_16, 0);
    lv_obj_set_style_text_color(view_home_label, flow_color_ink(), 0);
}

void flow_ui_offline_overlay(lv_obj_t *root)
{
    lv_obj_t *blocker = lv_obj_create(root);
    lv_obj_remove_style_all(blocker);
    lv_obj_set_size(blocker, LV_PCT(100), LV_PCT(100));
    lv_obj_set_pos(blocker, 0, 0);
    lv_obj_add_flag(blocker, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_clear_flag(blocker, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *label = lv_label_create(blocker);
    lv_label_set_text(label, "HUB OFFLINE");
    lv_obj_align(label, LV_ALIGN_BOTTOM_RIGHT, 0, 0);
    lv_obj_set_style_text_color(label, flow_color_pink(), 0);
    lv_obj_set_style_text_font(label, &lv_font_montserrat_12, 0);
}
