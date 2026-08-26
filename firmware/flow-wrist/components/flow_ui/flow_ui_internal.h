#pragma once

#include "flow_ui.h"
#include "lvgl.h"

lv_color_t flow_color_paper(void);
lv_color_t flow_color_ink(void);
lv_color_t flow_color_pink(void);
lv_color_t flow_color_yellow(void);
lv_color_t flow_color_blue(void);
lv_color_t flow_color_green(void);
lv_color_t flow_color_orange(void);
lv_color_t flow_color_muted(void);

void flow_ui_emit(const flow_ui_action_t *action);
void flow_ui_home_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_carousel_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_status_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_transition_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_transition_update(const flow_app_state_t *state);
void flow_ui_complete_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_error_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_art_energy(lv_obj_t *parent, uint8_t energy);
void flow_ui_art_style(lv_obj_t *parent, const char *style_id);
void flow_ui_art_record(lv_obj_t *parent, lv_color_t accent);
