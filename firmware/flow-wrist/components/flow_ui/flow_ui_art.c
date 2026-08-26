#include "flow_ui_internal.h"

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

void flow_ui_art_energy(lv_obj_t *parent, uint8_t energy)
{
    lv_obj_set_size(parent, 160, 120);
    lv_obj_clear_flag(parent, LV_OBJ_FLAG_SCROLLABLE);

    shape(parent, 18, 16, 72, 72, flow_color_pink(), LV_RADIUS_CIRCLE);
    shape(parent, 41, 39, 26, 26, flow_color_yellow(), LV_RADIUS_CIRCLE);

    const int32_t bar_width = 12;
    for (uint8_t index = 0; index < 5; ++index) {
        const int32_t height = 18 + (int32_t)index * 12;
        const lv_color_t color = index < energy ? flow_color_ink() : flow_color_paper();
        shape(parent,
              96 + (int32_t)index * 13,
              100 - height,
              bar_width,
              height,
              color,
              3);
    }
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
    lv_color_t shirt = flow_color_blue();
    lv_color_t pants = flow_color_orange();
    if (strcmp(style_id, "breaking") == 0) {
        shirt = flow_color_green();
        pants = flow_color_orange();
    } else if (strcmp(style_id, "funk") == 0) {
        shirt = flow_color_yellow();
        pants = flow_color_pink();
    } else if (strcmp(style_id, "locking") == 0) {
        shirt = flow_color_pink();
        pants = flow_color_blue();
    }

    lv_obj_set_size(parent, 160, 120);
    lv_obj_clear_flag(parent, LV_OBJ_FLAG_SCROLLABLE);
    shape(parent, 66, 8, 30, 30, flow_color_orange(), LV_RADIUS_CIRCLE);
    shape(parent, 55, 35, 54, 42, shirt, 12);
    shape(parent, 38, 43, 28, 13, shirt, 6);
    shape(parent, 101, 34, 38, 13, shirt, 6);
    shape(parent, 59, 72, 22, 39, pants, 7);
    shape(parent, 87, 72, 22, 39, pants, 7);
    shape(parent, 42, 103, 43, 12, flow_color_paper(), 5);
    shape(parent, 88, 103, 48, 12, flow_color_paper(), 5);
}
