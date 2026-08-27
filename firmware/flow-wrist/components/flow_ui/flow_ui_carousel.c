#include "flow_ui_internal.h"
#include "flow_carousel_model.h"

#include <stdbool.h>
#include <stddef.h>
#include <string.h>

static const char *const s_energy_labels[] = {
    "01 / WARM", "02 / LOW", "03 / FLOW", "04 / HIGH", "05 / PEAK",
};

static const char *const s_style_ids[] = {
    "hiphop", "breaking", "funk", "locking",
};

static const char *const s_style_labels[] = {
    "HIPHOP", "BREAKING", "FUNK", "LOCKING",
};

typedef struct {
    bool energy_mode;
    bool pointer_tracking;
    bool animating;
    uint8_t current_index;
    uint8_t preview_index;
    int8_t pending_step;
    int32_t press_x;
    int32_t press_y;
    int32_t pointer_x;
    int32_t pointer_y;
    int32_t offset;
    uint32_t press_tick;
    lv_obj_t *viewport;
    lv_obj_t *pages[3];
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

static uint8_t item_count(void)
{
    return s_carousel.energy_mode ? 5 : 4;
}

static bool wraps(void)
{
    return !s_carousel.energy_mode;
}

static uint8_t page_index(int8_t relative)
{
    return flow_carousel_neighbor(s_carousel.preview_index,
                                  relative,
                                  item_count(),
                                  wraps());
}

static void hide_feedback_cb(lv_timer_t *timer)
{
    (void)timer;
    s_carousel.feedback_timer = NULL;
    if (s_carousel.feedback != NULL) {
        lv_obj_add_flag(s_carousel.feedback, LV_OBJ_FLAG_HIDDEN);
    }
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

static void render_page(lv_obj_t *page, uint8_t index)
{
    lv_obj_clean(page);
    const lv_color_t accent = s_carousel.energy_mode
        ? flow_color_yellow()
        : flow_color_blue();
    lv_obj_set_style_bg_color(page, accent, 0);

    lv_obj_t *kicker = lv_label_create(page);
    lv_label_set_text(kicker, s_carousel.energy_mode ? "ENERGY LEVEL" : "DANCE STYLE");
    lv_obj_align(kicker, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_text_font(kicker, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(kicker, flow_color_ink(), 0);

    lv_obj_t *art = lv_obj_create(page);
    lv_obj_remove_style_all(art);
    lv_obj_align(art, LV_ALIGN_CENTER, 0, -18);
    if (s_carousel.energy_mode) {
        flow_ui_art_energy(art, (uint8_t)(index + 1));
    } else {
        flow_ui_art_style(art, s_style_ids[index]);
    }

    lv_obj_t *label = lv_label_create(page);
    lv_label_set_text(label,
                      s_carousel.energy_mode
                          ? s_energy_labels[index]
                          : s_style_labels[index]);
    lv_obj_align(label, LV_ALIGN_BOTTOM_LEFT, 0, -24);
    lv_obj_set_width(label, LV_PCT(100));
    lv_obj_set_style_text_font(label, &lv_font_montserrat_26, 0);
    lv_obj_set_style_text_color(label, flow_color_ink(), 0);

    lv_obj_t *instruction = lv_label_create(page);
    lv_label_set_text(instruction, "DRAG TO PREVIEW  /  TAP TO SEND");
    lv_obj_align(instruction, LV_ALIGN_BOTTOM_LEFT, 0, 0);
    lv_obj_set_style_text_font(instruction, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(instruction, flow_color_ink(), 0);
}

static void render_all_pages(void)
{
    render_page(s_carousel.pages[0], page_index(-1));
    render_page(s_carousel.pages[1], page_index(0));
    render_page(s_carousel.pages[2], page_index(1));
}

static void layout_pages(int32_t offset)
{
    s_carousel.offset = offset;
    for (uint8_t index = 0; index < 3; ++index) {
        const int32_t page_x = ((int32_t)index - 1) * FLOW_CAROUSEL_WIDTH_PX + offset;
        lv_obj_set_x(s_carousel.pages[index], page_x);
        int32_t distance = page_x < 0 ? -page_x : page_x;
        if (distance > FLOW_CAROUSEL_WIDTH_PX) {
            distance = FLOW_CAROUSEL_WIDTH_PX;
        }
        const lv_opa_t opacity = (lv_opa_t)(255 - (distance * 75 / FLOW_CAROUSEL_WIDTH_PX));
        lv_obj_set_style_opa(s_carousel.pages[index], opacity, 0);
    }
}

static void set_track_offset(void *object, int32_t offset)
{
    (void)object;
    layout_pages(offset);
}

static void snap_complete_cb(lv_anim_t *animation)
{
    (void)animation;
    if (s_carousel.pending_step != 0) {
        s_carousel.preview_index = flow_carousel_neighbor(s_carousel.preview_index,
                                                          s_carousel.pending_step,
                                                          item_count(),
                                                          wraps());
    }
    s_carousel.pending_step = 0;
    s_carousel.animating = false;
    render_all_pages();
    layout_pages(0);
}

static void snap_to(const flow_carousel_release_t *release)
{
    s_carousel.pending_step = release->step;
    s_carousel.animating = true;
    lv_anim_t animation;
    lv_anim_init(&animation);
    lv_anim_set_var(&animation, &s_carousel);
    lv_anim_set_exec_cb(&animation, set_track_offset);
    lv_anim_set_values(&animation, s_carousel.offset, release->target_offset);
    lv_anim_set_duration(&animation, release->duration_ms);
    lv_anim_set_path_cb(&animation, lv_anim_path_ease_out);
    lv_anim_set_completed_cb(&animation, snap_complete_cb);
    lv_anim_start(&animation);
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

static void update_pointer(void)
{
    lv_indev_t *input = lv_indev_active();
    if (input != NULL) {
        lv_point_t point;
        lv_indev_get_point(input, &point);
        s_carousel.pointer_x = point.x;
        s_carousel.pointer_y = point.y;
    }
}

static void poster_event_cb(lv_event_t *event)
{
    const lv_event_code_t code = lv_event_get_code(event);
    if (code == LV_EVENT_PRESSED && !s_carousel.animating) {
        update_pointer();
        s_carousel.press_x = s_carousel.pointer_x;
        s_carousel.press_y = s_carousel.pointer_y;
        s_carousel.press_tick = lv_tick_get();
        s_carousel.pointer_tracking = true;
        return;
    }
    if (code == LV_EVENT_PRESSING && s_carousel.pointer_tracking) {
        update_pointer();
        const int32_t delta_x = s_carousel.pointer_x - s_carousel.press_x;
        const int32_t delta_y = s_carousel.pointer_y - s_carousel.press_y;
        if ((delta_x < 0 ? -delta_x : delta_x) > (delta_y < 0 ? -delta_y : delta_y)) {
            layout_pages(flow_carousel_drag_offset(delta_x, FLOW_CAROUSEL_WIDTH_PX));
        }
        return;
    }
    if (code != LV_EVENT_RELEASED || !s_carousel.pointer_tracking) {
        return;
    }

    update_pointer();
    const int32_t delta_x = s_carousel.pointer_x - s_carousel.press_x;
    const int32_t delta_y = s_carousel.pointer_y - s_carousel.press_y;
    const int32_t abs_x = delta_x < 0 ? -delta_x : delta_x;
    const int32_t abs_y = delta_y < 0 ? -delta_y : delta_y;
    s_carousel.pointer_tracking = false;

    if (abs_x < 12 && abs_y < 12) {
        layout_pages(0);
        if (s_carousel.preview_index == s_carousel.current_index) {
            show_feedback("CURRENT / ALREADY LIVE");
        } else {
            emit_selection();
        }
        return;
    }

    uint32_t elapsed = lv_tick_elaps(s_carousel.press_tick);
    if (elapsed == 0) {
        elapsed = 1;
    }
    const int32_t velocity_x = (int32_t)((int64_t)delta_x * 1000 / elapsed);
    const flow_carousel_release_t release = flow_carousel_release(delta_x,
                                                                  delta_y,
                                                                  velocity_x,
                                                                  s_carousel.preview_index,
                                                                  item_count(),
                                                                  wraps());
    snap_to(&release);
}

static void back_event_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) == LV_EVENT_CLICKED) {
        const flow_ui_action_t action = {.type = FLOW_UI_ACTION_BACK};
        flow_ui_emit(&action);
    }
}

static void carousel_root_delete_cb(lv_event_t *event)
{
    if (lv_event_get_code(event) != LV_EVENT_DELETE) {
        return;
    }
    lv_anim_delete(&s_carousel, set_track_offset);
    if (s_carousel.feedback_timer != NULL) {
        lv_timer_delete(s_carousel.feedback_timer);
    }
    memset(&s_carousel, 0, sizeof(s_carousel));
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

    const flow_back_button_layout_t back_layout = flow_carousel_back_button_layout();
    lv_obj_t *back = lv_button_create(root);
    lv_obj_set_pos(back, back_layout.x, back_layout.y);
    lv_obj_set_size(back, back_layout.width, back_layout.height);
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
    lv_obj_align(title, LV_ALIGN_TOP_RIGHT, 0, back_layout.title_y);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_18, 0);
    lv_obj_set_style_text_color(title, flow_color_ink(), 0);

    s_carousel.viewport = lv_obj_create(root);
    lv_obj_remove_style_all(s_carousel.viewport);
    lv_obj_set_pos(s_carousel.viewport, 10, 70);
    lv_obj_set_size(s_carousel.viewport, FLOW_CAROUSEL_WIDTH_PX, 330);
    lv_obj_clear_flag(s_carousel.viewport, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(s_carousel.viewport, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(s_carousel.viewport, poster_event_cb, LV_EVENT_ALL, NULL);

    for (uint8_t index = 0; index < 3; ++index) {
        lv_obj_t *page = lv_obj_create(s_carousel.viewport);
        lv_obj_set_size(page, FLOW_CAROUSEL_WIDTH_PX, 330);
        lv_obj_set_y(page, 0);
        lv_obj_set_style_radius(page, 24, 0);
        lv_obj_set_style_border_color(page, flow_color_ink(), 0);
        lv_obj_set_style_border_width(page, 3, 0);
        lv_obj_set_style_pad_all(page, 18, 0);
        lv_obj_clear_flag(page, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_clear_flag(page, LV_OBJ_FLAG_CLICKABLE);
        s_carousel.pages[index] = page;
    }
    render_all_pages();
    layout_pages(0);

    s_carousel.feedback = lv_label_create(root);
    lv_label_set_text(s_carousel.feedback, "CURRENT / ALREADY LIVE");
    lv_obj_align(s_carousel.feedback, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_text_font(s_carousel.feedback, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_color(s_carousel.feedback, flow_color_green(), 0);
    lv_obj_add_flag(s_carousel.feedback, LV_OBJ_FLAG_HIDDEN);
}

static void set_preview_index(uint8_t target)
{
    if (s_carousel.viewport == NULL || s_carousel.animating ||
        target == s_carousel.preview_index || target >= item_count()) {
        return;
    }
    const int8_t step = target > s_carousel.preview_index ? 1 : -1;
    flow_carousel_release_t release = {
        .step = step,
        .target_offset = step > 0 ? -FLOW_CAROUSEL_WIDTH_PX :
                                    FLOW_CAROUSEL_WIDTH_PX,
        .duration_ms = FLOW_CAROUSEL_SNAP_MS,
    };
    snap_to(&release);
}

void flow_ui_carousel_set_energy(uint8_t energy)
{
    if (s_carousel.energy_mode && energy >= 1 && energy <= 5) {
        set_preview_index((uint8_t)(energy - 1));
    }
}

void flow_ui_carousel_set_style(const char *style_id)
{
    if (!s_carousel.energy_mode && style_id != NULL) {
        set_preview_index(style_index(style_id));
    }
}
