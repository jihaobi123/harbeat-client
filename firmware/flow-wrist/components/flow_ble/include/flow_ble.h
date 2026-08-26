#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "flow_protocol.h"

typedef void (*flow_ble_snapshot_handler_t)(const flow_snapshot_t *snapshot,
                                            void *context);
typedef void (*flow_ble_connection_handler_t)(bool connected, void *context);

esp_err_t flow_ble_init(flow_ble_snapshot_handler_t snapshot_handler,
                        flow_ble_connection_handler_t connection_handler,
                        void *context);
esp_err_t flow_ble_send_command(const flow_command_t *command);
bool flow_ble_is_connected(void);
bool flow_ble_is_ready(void);
void flow_ble_set_battery(uint8_t percentage);
