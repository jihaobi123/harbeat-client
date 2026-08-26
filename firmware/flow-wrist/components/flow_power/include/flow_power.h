#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

typedef void (*flow_power_battery_handler_t)(uint8_t percentage, void *context);

esp_err_t flow_power_init(flow_power_battery_handler_t battery_handler,
                          void *context);
void flow_power_note_activity(void);
void flow_power_set_transition_active(bool active);
void flow_power_wake(void);
