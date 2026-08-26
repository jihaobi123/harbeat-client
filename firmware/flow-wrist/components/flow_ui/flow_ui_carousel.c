#include "flow_ui_internal.h"

#include <stdbool.h>
#include <stddef.h>
#include <string.h>

static const char *const s_energy_labels[] = {
    "01 / WARM",
    "02 / LOW",
    "03 / FLOW",
    "04 / HIGH",
    "05 / PEAK",
};

static const char *const s_style_ids[] = {
    "hiphop",
    "breaking",
    "funk",
    "locking",
};

static const char *const s_style_labels[] = {
    "HIPHOP",
    "BREAKING",
    "FUNK",
    "LOCKING",
};

typedef struct {
    bool energy_mode;
    bool pointer_tracking;
    uint8_t current_index;
    uint8_t preview_index;
    int32_t press_x;
    int32_t press_y;
    int32_t pointer_x;
    int32_t pointer_y;
    lv_obj_t *poster;
    lv_obj_t *feedback;
    lv_timer_t *feedback_timer;
} carousel_context_t;

static carousel_context_t s_carousel;

static uint8_t style_index(const char *style)
{
    for (uint8_t index = 0; index < 4; ++index) {
        if (strcmp(style, s_style_ids[index]) == 0) {
            return index;
        }
    }
    return 0;
}

static void hide_feedback_cb(lv_timer_t *timer)
{
    (void)timer;
    s_carousel.feedback_timer = NULL;
    if (s_carousel.feedback != NULL) {
        lv_obj_add_flag(s_carousel.feedback, LV_OBJ_FLAG_HIDDEN);
    }
}

static void carousel_root_delete_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) != LV_EVENT_DELETE) {
        return;
    }
    if (s_carousel.feedback_timer != NULL) {
        lv_timer_delete(s_carousel.feedback_timer);
        s_carousel.feedback_timer = NULL;
    }
    s_carousel.poster = NULL;
    s_carousel.feedback = NULL;
}

static void show_feedback(const char *text)
{
    lv_label_set_text(s_carousel.feedback, text);
    lv_obj_clear_flag(s_carousel.feedback, LV_OBJ_FLAG_HIDDEN);
    if (s_carousel.feedback_timer != NULL) {
        lv_timer_delete(s_carousel.feedback_timer);
    }
    s_carousel.feedback_timer = lv_timer_create(hide_feedback_cb, 900, NULL);
    lv_timer_set_repeat_count(s_carousel.feedback_timer, 1);
}

static void render_poster(void)
{
    lv_obj_clean(s_carousel.poster);
    const lv_color_t accent = s_carousel.energy_mode
        ? flow_color_yellow()
        : flow_color_blue();
    lv_obj_set_style_bg_color(s_carousel.poster, accent, 0);

    lv_obj_t *kicker = lv_label_create(s_carousel.poster);
    lv_label_set_text(kicker, s_carousel.energy_mode ? "ENERGY LEVEL" : "DANCE STYLE");
    lv_obj_align(kicker, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_text_font(kicker, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(kicker, flow_color_ink(), 0);

    lv_obj_t *art = lv_obj_create(s_carousel.poster);
    lv_obj_remove_style_all(art);
    lv_obj_align(art, LV_ALIGN_CENTER, 0, -18);
    if (s_carousel.energy_mode) {
        flow_ui_art_energy(art, (uint8_t)(s_carousel.preview_index + 1));
    } else {
        flow_ui_art_style(art, s_style_ids[s_carousel.preview_index]);
    }

    lv_obj_t *label = lv_label_create(s_carousel.poster);
    lv_label_set_text(label,
                      s_carousel.energy_mode
                          ? s_energy_labels[s_carousel.preview_index]
                          : s_style_labels[s_carousel.preview_index]);
    lv_obj_align(label, LV_ALIGN_BOTTOM_LEFT, 0, -24);
    lv_obj_set_width(label, LV_PCT(100));
    lv_obj_set_style_text_font(label, &lv_font_montserrat_26, 0);
    lv_obj_set_style_text_color(label, flow_color_ink(), 0);

    lv_obj_t *instruction = lv_label_create(s_carousel.poster);
    lv_label_set_text(instruction, "SWIPE TO PREVIEW  /  TAP TO SEND");
    lv_obj_align(instruction, LV_ALIGN_BOTTOM_LEFT, 0, 0);
    lv_obj_set_style_text_font(instruction, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(instruction, flow_color_ink(), 0);
}

static void set_poster_x(void *object, int32_t x)
{
    lv_obj_set_x((lv_obj_t *)object, x);
}

static void animate_poster(int32_t from_x)
{
    lv_anim_t animation;
    lv_anim_init(&animation);
    lv_anim_set_var(&animation, s_carousel.poster);
    lv_anim_set_exec_cb(&animation, set_poster_x);
    lv_anim_set_values(&animation, from_x, lv_obj_get_x(s_carousel.poster));
    lv_anim_set_duration(&animation, 250);
    lv_anim_set_path_cb(&animation, lv_anim_path_ease_out);
    lv_anim_start(&animation);
}

static void move_preview(lv_dir_t direction)
{
    const uint8_t count = s_carousel.energy_mode ? 5 : 4;
    uint8_t next = s_carousel.preview_index;
    if (direction == LV_DIR_LEFT) {
        if (s_carousel.energy_mode) {
            if (next + 1 < count) {
                ++next;
            }
        } else {
            next = (uint8_t)((next + 1) % count);
        }
    } else if (direction == LV_DIR_RIGHT) {
        if (s_carousel.energy_mode) {
            if (next > 0) {
                --next;
            }
        } else {
            next = (uint8_t)((next + count - 1) % count);
        }
    }

    if (next != s_carousel.preview_index) {
        s_carousel.preview_index = next;
        render_poster();
        animate_poster(direction == LV_DIR_LEFT ? 20 : -20);
    }
}

static void emit_selection(void)
{
    flow_ui_action_t action = {0};
    if (s_carousel.energy_mode) {
        action.type = FLOW_UI_ACTION_SET_ENERGY;
        action.energy = (uint8_t)(s_carousel.preview_index + 1);
    } else {
        action.type = FLOW_UI_ACTION_SET_STYLE;
        strcpy(action.style, s_style_ids[s_carousel.preview_index]);
    }
    flow_ui_emit(&action);
}

static void poster_event_cb(lv_event_t *event)
{
    const lv_event_code_t code = lv_event_get_code(event);
    if (code == LV_EVENT_PRESSED) {
        lv_indev_t *input = lv_indev_active();
        if (input != NULL) {
            lv_point_t point;
            lv_indev_get_point(input, &point);
            s_carousel.press_x = point.x;
            s_carousel.press_y = point.y;
            s_carousel.pointer_x = point.x;
            s_carousel.pointer_y = point.y;
            s_carousel.pointer_tracking = true;
        }
        return;
    }
    if (code == LV_EVENT_PRESSING && s_carousel.pointer_tracking) {
        lv_indev_t *input = lv_indev_active();
        if (input != NULL) {
            lv_point_t point;
            lv_indev_get_point(input, &point);
            s_carousel.pointer_x = point.x;
            s_carousel.pointer_y = point.y;
        }
        return;
    }
    if (code != LV_EVENT_RELEASED) {
        return;
    }

    const int32_t delta_x = s_carousel.pointer_x - s_carousel.press_x;
    const int32_t delta_y = s_carousel.pointer_y - s_carousel.press_y;
    const int32_t horizontal_distance = delta_x < 0 ? -delta_x : delta_x;
    const int32_t vertical_distance = delta_y < 0 ? -delta_y : delta_y;
    s_carousel.pointer_tracking = false;

    if (horizontal_distance >= 35 && horizontal_distance > vertical_distance) {
        move_preview(delta_x < 0 ? LV_DIR_LEFT : LV_DIR_RIGHT);
        return;
    }
    if (s_carousel.preview_index == s_carousel.current_index) {
        show_feedback("CURRENT / ALREADY LIVE");
    } else {
        emit_selection();
    }
}

static void back_event_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) == LV_EVENT_CLICKED) {
        const flow_ui_action_t action = {.type = FLOW_UI_ACTION_BACK};
        flow_ui_emit(&action);
    }
}

void flow_ui_carousel_create(lv_obj_t *root, const flow_app_state_t *state)
{
    memset(&s_carousel, 0, sizeof(s_carousel));
    lv_obj_add_event_cb(root, carousel_root_delete_cb, LV_EVENT_DELETE, NULL);
    s_carousel.energy_mode = state->screen == FLOW_SCREEN_ENERGY;
    s_carousel.current_index = s_carousel.energy_mode
        ? (uint8_t)(state->snapshot.current.energy - 1)
        : style_index(state->snapshot.current.style);
    s_carousel.preview_index = s_carousel.current_index;

    lv_obj_t *back = lv_button_create(root);
    lv_obj_set_pos(back, 0, 0);
    lv_obj_set_size(back, 50, 42);
    lv_obj_set_style_radius(back, 12, 0);
    lv_obj_set_style_bg_color(back, flow_color_paper(), 0);
    lv_obj_set_style_border_color(back, flow_color_ink(), 0);
    lv_obj_set_style_border_width(back, 2, 0);
    lv_obj_add_event_cb(back, back_event_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *back_label = lv_label_create(back);
    lv_label_set_text(back_label, "<");
    lv_obj_center(back_label);
    lv_obj_set_style_text_color(back_label, flow_color_ink(), 0);

    lv_obj_t *title = lv_label_create(root);
    lv_label_set_text(title, s_carousel.energy_mode ? "CHOOSE ENERGY" : "CHOOSE STYLE");
    lv_obj_align(title, LV_ALIGN_TOP_RIGHT, 0, 8);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_18, 0);
    lv_obj_set_style_text_color(title, flow_color_ink(), 0);

    s_carousel.poster = lv_obj_create(root);
    lv_obj_set_pos(s_carousel.poster, 10, 70);
    lv_obj_set_size(s_carousel.poster, 342, 330);
    lv_obj_set_style_radius(s_carousel.poster, 24, 0);
    lv_obj_set_style_border_color(s_carousel.poster, flow_color_ink(), 0);
    lv_obj_set_style_border_width(s_carousel.poster, 3, 0);
    lv_obj_set_style_pad_all(s_carousel.poster, 18, 0);
    lv_obj_clear_flag(s_carousel.poster, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(s_carousel.poster, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(s_carousel.poster, poster_event_cb, LV_EVENT_ALL, NULL);
    render_poster();

    s_carousel.feedback = lv_label_create(root);
    lv_label_set_text(s_carousel.feedback, "CURRENT / ALREADY LIVE");
    lv_obj_align(s_carousel.feedback, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_text_font(s_carousel.feedback, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(s_carousel.feedback, flow_color_green(), 0);
    lv_obj_add_flag(s_carousel.feedback, LV_OBJ_FLAG_HIDDEN);
}
