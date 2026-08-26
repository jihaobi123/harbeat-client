#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cbor.h"
#include "flow_protocol.h"

static void encode_key(CborEncoder *map, const char *key)
{
    assert(cbor_encode_text_stringz(map, key) == CborNoError);
}

static void encode_music(CborEncoder *map,
                         const char *key,
                         uint8_t energy,
                         const char *style,
                         uint16_t bpm)
{
    CborEncoder music;
    encode_key(map, key);
    assert(cbor_encoder_create_map(map, &music, 3) == CborNoError);
    encode_key(&music, "energy");
    assert(cbor_encode_uint(&music, energy) == CborNoError);
    encode_key(&music, "style");
    assert(cbor_encode_text_stringz(&music, style) == CborNoError);
    encode_key(&music, "bpm");
    assert(cbor_encode_uint(&music, bpm) == CborNoError);
    assert(cbor_encoder_close_container(map, &music) == CborNoError);
}

static size_t encode_snapshot(uint8_t *buffer,
                              size_t capacity,
                              const char *session_id,
                              const char *phase,
                              uint8_t target_energy,
                              const char *target_style)
{
    CborEncoder root;
    CborEncoder map;
    cbor_encoder_init(&root, buffer, capacity, 0);
    assert(cbor_encoder_create_map(&root, &map, 11) == CborNoError);
    encode_key(&map, "v");
    assert(cbor_encode_uint(&map, 1) == CborNoError);
    encode_key(&map, "kind");
    assert(cbor_encode_text_stringz(&map, "snapshot") == CborNoError);
    encode_key(&map, "session_id");
    assert(cbor_encode_text_stringz(&map, session_id) == CborNoError);
    encode_key(&map, "revision");
    assert(cbor_encode_uint(&map, 9) == CborNoError);
    encode_key(&map, "ack_id");
    assert(cbor_encode_uint(&map, 42) == CborNoError);
    encode_key(&map, "phase");
    assert(cbor_encode_text_stringz(&map, phase) == CborNoError);
    encode_key(&map, "locked");
    assert(cbor_encode_boolean(&map, true) == CborNoError);
    encode_key(&map, "eta_ms");
    assert(cbor_encode_uint(&map, 14000) == CborNoError);
    encode_music(&map, "current", 3, "hiphop", 96);
    encode_music(&map, "target", target_energy, target_style, 108);
    encode_key(&map, "error");
    assert(cbor_encode_text_stringz(&map, "") == CborNoError);
    assert(cbor_encoder_close_container(&root, &map) == CborNoError);
    return cbor_encoder_get_buffer_size(&root, buffer);
}

static void test_command_validation(void)
{
    flow_command_t command = {
        .version = 1,
        .id = 42,
        .operation = FLOW_OPERATION_SET_ENERGY,
        .energy = 5,
    };
    assert(flow_protocol_validate_command(&command));

    command.energy = 0;
    assert(!flow_protocol_validate_command(&command));
    command.energy = 6;
    assert(!flow_protocol_validate_command(&command));

    command.operation = FLOW_OPERATION_SET_STYLE;
    strcpy(command.style, "breaking");
    assert(flow_protocol_validate_command(&command));
    strcpy(command.style, "unknown");
    assert(!flow_protocol_validate_command(&command));
    memset(command.style, 'x', sizeof(command.style));
    assert(!flow_protocol_validate_command(&command));

    command.version = 0;
    assert(!flow_protocol_validate_command(&command));
    assert(!flow_protocol_validate_command(NULL));
}

static void test_command_encoding(void)
{
    flow_command_t command = {
        .version = 1,
        .id = 42,
        .operation = FLOW_OPERATION_SET_STYLE,
    };
    strcpy(command.style, "locking");

    uint8_t buffer[192];
    size_t encoded_size = 0;
    assert(flow_protocol_encode_command(&command, buffer, sizeof(buffer), &encoded_size) == 0);
    assert(encoded_size > 0);

    CborParser parser;
    CborValue root;
    CborValue field;
    assert(cbor_parser_init(buffer, encoded_size, 0, &parser, &root) == CborNoError);
    assert(cbor_value_is_map(&root));

    assert(cbor_value_map_find_value(&root, "id", &field) == CborNoError);
    uint64_t id = 0;
    assert(cbor_value_get_uint64(&field, &id) == CborNoError);
    assert(id == 42);

    assert(cbor_value_map_find_value(&root, "op", &field) == CborNoError);
    char operation[16];
    size_t operation_size = sizeof(operation);
    assert(cbor_value_copy_text_string(&field, operation, &operation_size, NULL) == CborNoError);
    assert(strcmp(operation, "set_style") == 0);

    assert(cbor_value_map_find_value(&root, "value", &field) == CborNoError);
    char value[FLOW_STYLE_ID_MAX];
    size_t value_size = sizeof(value);
    assert(cbor_value_copy_text_string(&field, value, &value_size, NULL) == CborNoError);
    assert(strcmp(value, "locking") == 0);

    assert(flow_protocol_encode_command(&command, buffer, 8, &encoded_size) == -1);
}

static void test_snapshot_decoding(void)
{
    uint8_t buffer[384];
    size_t size = encode_snapshot(buffer,
                                  sizeof(buffer),
                                  "8f3a19d04b7c221e",
                                  "preparing",
                                  5,
                                  "breaking");
    flow_snapshot_t snapshot;
    assert(flow_protocol_decode_snapshot(buffer, size, &snapshot) == 0);
    assert(strcmp(snapshot.session_id, "8f3a19d04b7c221e") == 0);
    assert(snapshot.revision == 9);
    assert(snapshot.ack_id == 42);
    assert(snapshot.phase == FLOW_PHASE_PREPARING);
    assert(snapshot.locked);
    assert(snapshot.eta_ms == 14000);
    assert(snapshot.current.energy == 3);
    assert(strcmp(snapshot.current.style, "hiphop") == 0);
    assert(snapshot.current.bpm == 96);
    assert(snapshot.target.energy == 5);
    assert(strcmp(snapshot.target.style, "breaking") == 0);
    assert(snapshot.target.bpm == 108);

    size = encode_snapshot(buffer, sizeof(buffer), "not-hex-12345678", "preparing", 5, "breaking");
    assert(flow_protocol_decode_snapshot(buffer, size, &snapshot) == -1);

    size = encode_snapshot(buffer, sizeof(buffer), "8f3a19d04b7c221e", "waiting", 5, "breaking");
    assert(flow_protocol_decode_snapshot(buffer, size, &snapshot) == -1);

    size = encode_snapshot(buffer, sizeof(buffer), "8f3a19d04b7c221e", "preparing", 6, "breaking");
    assert(flow_protocol_decode_snapshot(buffer, size, &snapshot) == -1);

    size = encode_snapshot(buffer,
                           sizeof(buffer),
                           "8f3a19d04b7c221e",
                           "preparing",
                           5,
                           "abcdefghijklmnop");
    assert(flow_protocol_decode_snapshot(buffer, size, &snapshot) == -1);
}

int main(void)
{
    test_command_validation();
    test_command_encoding();
    test_snapshot_decoding();
    puts("flow_protocol tests passed");
    return 0;
}
