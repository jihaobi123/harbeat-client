#pragma once

#include "esp_err.h"
#include "flow_core.h"
#include "flow_protocol.h"

typedef void (*flow_snapshot_handler_t)(const flow_snapshot_t *snapshot,
                                        void *context);

esp_err_t flow_simulator_start(flow_snapshot_handler_t handler, void *context);
esp_err_t flow_simulator_submit(const flow_command_t *command);
