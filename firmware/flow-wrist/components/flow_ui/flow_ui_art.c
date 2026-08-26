#include "flow_ui_internal.h"
#include "flow_dancer_assets.h"

#include <string.h>

static lv_obj_t *shape(lv_obj_t *parent,
                       int32_t x,
                       int32_t y,
                       int32_t width,
                       int32_t height,
                       lv_color_t color,
                       int32_t radius)
{
    lv_obj_t *object = lv_obj_create(parent);
    lv_obj_remove_style_all(object);
    lv_obj_set_pos(object, x, y);
    lv_obj_set_size(object, width, height);
    lv_obj_set_style_radius(object, radius, 0);
    lv_obj_set_style_bg_color(object, color, 0);
    lv_obj_set_style_bg_opa(object, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(object, flow_color_ink(), 0);
    lv_obj_set_style_border_width(object, 2, 0);
    lv_obj_clear_flag(object, LV_OBJ_FLAG_SCROLLABLE);
    return object;
}

static void set_art_y(void *object, int32_t y)
{
    lv_obj_set_y((lv_obj_t *)object, y);
}

void flow_ui_art_energy(lv_obj_t *parent, uint8_t energy)
{
    lv_obj_set_size(parent, 160, 120);
    lv_obj_clear_flag(parent, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *dancer = lv_image_create(parent);
    lv_image_set_src(dancer, &flow_dancer_hiphop);
    lv_obj_set_pos(dancer, 13, 4);

    const uint8_t line_count = energy > 5 ? 5 : energy;
    for (uint8_t index = 0; index < line_count; ++index) {
        lv_obj_t *line = lv_obj_create(parent);
        lv_obj_remove_style_all(line);
        lv_obj_set_pos(line, 120 + (int32_t)(index % 2) * 8, 28 + (int32_t)index * 14);
        lv_obj_set_size(line, 25 - (int32_t)(index % 2) * 7, 4);
        lv_obj_set_style_radius(line, 2, 0);
        lv_obj_set_style_bg_color(line, index % 2 == 0 ? flow_color_pink() : flow_color_blue(), 0);
        lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
    }

    lv_anim_t bob;
    lv_anim_init(&bob);
    lv_anim_set_var(&bob, dancer);
    lv_anim_set_exec_cb(&bob, set_art_y);
    lv_anim_set_values(&bob, 4, 1 - (int32_t)line_count);
    lv_anim_set_duration(&bob, 110 + (uint32_t)(5 - line_count) * 18);
    lv_anim_set_playback_duration(&bob, 140);
    lv_anim_set_repeat_count(&bob, 0);
    lv_anim_set_path_cb(&bob, lv_anim_path_ease_out);
    lv_anim_start(&bob);
}

void flow_ui_art_record(lv_obj_t *parent, lv_color_t accent)
{
    lv_obj_set_size(parent, 160, 120);
    lv_obj_clear_flag(parent, LV_OBJ_FLAG_SCROLLABLE);
    shape(parent, 29, 9, 102, 102, flow_color_ink(), LV_RADIUS_CIRCLE);
    shape(parent, 48, 28, 64, 64, flow_color_paper(), LV_RADIUS_CIRCLE);
    shape(parent, 61, 41, 38, 38, accent, LV_RADIUS_CIRCLE);
    shape(parent, 74, 54, 12, 12, flow_color_ink(), LV_RADIUS_CIRCLE);
}

void flow_ui_art_style(lv_obj_t *parent, const char *style_id)
{
    const lv_image_dsc_t *asset = &flow_dancer_hiphop;
    if (strcmp(style_id, "breaking") == 0) {
        asset = &flow_dancer_breaking;
    } else if (strcmp(style_id, "funk") == 0) {
        asset = &flow_dancer_funk;
    } else if (strcmp(style_id, "locking") == 0) {
        asset = &flow_dancer_locking;
    }

    lv_obj_set_size(parent, 160, 120);
    lv_obj_clear_flag(parent, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *dancer = lv_image_create(parent);
    lv_image_set_src(dancer, asset);
    lv_obj_align(dancer, LV_ALIGN_CENTER, 0, 0);
}
