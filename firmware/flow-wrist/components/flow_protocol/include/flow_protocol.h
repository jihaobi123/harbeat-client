#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "flow_core.h"

typedef enum {
    FLOW_OPERATION_SET_ENERGY,
    FLOW_OPERATION_SET_STYLE
} flow_operation_t;

typedef struct {
    uint8_t version;
    uint32_t id;
    flow_operation_t operation;
    uint8_t energy;
    char style[FLOW_STYLE_ID_MAX];
} flow_command_t;

bool flow_protocol_validate_command(const flow_command_t *command);
int flow_protocol_encode_command(const flow_command_t *command,
                                 uint8_t *buffer,
                                 size_t capacity,
                                 size_t *encoded_size);
int flow_protocol_decode_snapshot(const uint8_t *data,
                                  size_t size,
                                  flow_snapshot_t *snapshot);
