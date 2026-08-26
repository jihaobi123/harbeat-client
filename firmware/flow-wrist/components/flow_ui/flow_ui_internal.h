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
