#include "flow_ui_internal.h"

#include <stdint.h>

static void card_event_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) != LV_EVENT_CLICKED) {
        return;
    }
    flow_ui_action_t action = {
        .type = (flow_ui_action_type_t)(uintptr_t)lv_event_get_user_data(event),
    };
    flow_ui_emit(&action);
}

static lv_obj_t *create_card(lv_obj_t *root,
                             int32_t y,
                             lv_color_t color,
                             flow_ui_action_type_t action_type)
{
    lv_obj_t *card = lv_obj_create(root);
    lv_obj_set_pos(card, 0, y);
    lv_obj_set_size(card, LV_PCT(100), 152);
    lv_obj_set_style_radius(card, 20, 0);
    lv_obj_set_style_bg_color(card, color, 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(card, flow_color_ink(), 0);
    lv_obj_set_style_border_width(card, 3, 0);
    lv_obj_set_style_shadow_width(card, 0, 0);
    lv_obj_set_style_pad_all(card, 16, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(card, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(card,
                        card_event_cb,
                        LV_EVENT_CLICKED,
                        (void *)(uintptr_t)action_type);
    return card;
}

static void add_card_text(lv_obj_t *card,
                          const char *eyebrow,
                          const char *value,
                          const char *cta_text)
{
    lv_obj_t *small = lv_label_create(card);
    lv_label_set_text(small, eyebrow);
    lv_obj_set_style_text_font(small, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(small, flow_color_ink(), 0);

    lv_obj_t *large = lv_label_create(card);
    lv_label_set_text(large, value);
    lv_obj_set_pos(large, 0, 30);
    lv_obj_set_width(large, 174);
    lv_obj_set_style_text_font(large, &lv_font_montserrat_26, 0);
    lv_obj_set_style_text_color(large, flow_color_ink(), 0);

    lv_obj_t *cta = lv_label_create(card);
    lv_label_set_text(cta, cta_text);
    lv_obj_align(cta, LV_ALIGN_BOTTOM_LEFT, 0, 0);
    lv_obj_set_style_text_font(cta, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(cta, flow_color_ink(), 0);
}

void flow_ui_home_create(lv_obj_t *root, const flow_app_state_t *state)
{
    const bool has_snapshot = state->has_snapshot;
    const bool hub_ready = state->link_state == FLOW_LINK_READY;

    lv_obj_t *title = lv_label_create(root);
    lv_label_set_text(title, "WHAT SHIFTS\nNEXT?");
    lv_obj_set_style_text_font(title, &lv_font_montserrat_26, 0);
    lv_obj_set_style_text_color(title, flow_color_ink(), 0);

    lv_obj_t *hub = lv_label_create(root);
    lv_label_set_text(hub, hub_ready ? "\xE2\x97\x8F HUB" : "\xE2\x97\x8B HUB");
    lv_obj_align(hub, LV_ALIGN_TOP_RIGHT, 0, 8);
    lv_obj_set_style_text_font(hub, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(hub,
                                hub_ready ? flow_color_green() : flow_color_muted(),
                                0);

    lv_obj_t *energy_card = create_card(root,
                                        86,
                                        flow_color_yellow(),
                                        FLOW_UI_ACTION_OPEN_ENERGY);
    char energy_value[8];
    if (has_snapshot) {
        lv_snprintf(energy_value,
                    sizeof(energy_value),
                    "%02u / 05",
                    state->snapshot.current.energy);
    } else {
        lv_snprintf(energy_value, sizeof(energy_value), "-- / 05");
    }
    add_card_text(energy_card,
                  "ENERGY",
                  energy_value,
                  hub_ready ? "TAP TO SHIFT  >" : "WAITING FOR HUB");
    if (has_snapshot) {
        lv_obj_t *energy_art = lv_obj_create(energy_card);
        lv_obj_remove_style_all(energy_art);
        lv_obj_align(energy_art, LV_ALIGN_RIGHT_MID, 4, 0);
        flow_ui_art_energy(energy_art, state->snapshot.current.energy);
    }

    lv_obj_t *style_card = create_card(root,
                                       252,
                                       flow_color_blue(),
                                       FLOW_UI_ACTION_OPEN_STYLE);
    add_card_text(style_card,
                  "STYLE",
                  has_snapshot ? state->snapshot.current.style : "NO DATA",
                  hub_ready ? "TAP TO SHIFT  >" : "WAITING FOR HUB");
    if (has_snapshot) {
        lv_obj_t *style_art = lv_obj_create(style_card);
        lv_obj_remove_style_all(style_art);
        lv_obj_align(style_art, LV_ALIGN_RIGHT_MID, 4, 0);
        flow_ui_art_style(style_art, state->snapshot.current.style);
    }

    lv_obj_t *footer = lv_label_create(root);
    if (has_snapshot) {
        lv_label_set_text_fmt(footer,
                              "%u BPM  /  %s",
                              state->snapshot.current.bpm,
                              hub_ready ? "READY" : "LAST SYNC");
    } else {
        lv_label_set_text(footer, "-- BPM  /  OFFLINE");
    }
    lv_obj_align(footer, LV_ALIGN_BOTTOM_LEFT, 0, 0);
    lv_obj_set_style_text_font(footer, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(footer, flow_color_muted(), 0);
}
