#include "flow_protocol.h"

#include <ctype.h>
#include <limits.h>
#include <string.h>

#include "cbor.h"

static bool bounded_text_equals(const char *text,
                                size_t capacity,
                                const char *expected)
{
    const char *terminator = memchr(text, '\0', capacity);
    return terminator != NULL && strcmp(text, expected) == 0;
}

static bool known_style(const char *style)
{
    static const char *const styles[] = {
        "hiphop",
        "breaking",
        "funk",
        "locking",
    };

    for (size_t index = 0; index < sizeof(styles) / sizeof(styles[0]); ++index) {
        if (bounded_text_equals(style, FLOW_STYLE_ID_MAX, styles[index])) {
            return true;
        }
    }
    return false;
}

bool flow_protocol_validate_command(const flow_command_t *command)
{
    if (command == NULL || command->version != 1 || command->id == 0) {
        return false;
    }
    if (command->operation == FLOW_OPERATION_SET_ENERGY) {
        return command->energy >= 1 && command->energy <= 5;
    }
    if (command->operation == FLOW_OPERATION_SET_STYLE) {
        return known_style(command->style);
    }
    return false;
}

static CborError encode_key(CborEncoder *map, const char *key)
{
    return cbor_encode_text_stringz(map, key);
}

int flow_protocol_encode_command(const flow_command_t *command,
                                 uint8_t *buffer,
                                 size_t capacity,
                                 size_t *encoded_size)
{
    if (!flow_protocol_validate_command(command) || buffer == NULL ||
        capacity == 0 || encoded_size == NULL) {
        return -1;
    }

    CborEncoder root;
    CborEncoder map;
    CborError error;
    cbor_encoder_init(&root, buffer, capacity, 0);

    error = cbor_encoder_create_map(&root, &map, 5);
    if (error != CborNoError ||
        encode_key(&map, "v") != CborNoError ||
        cbor_encode_uint(&map, command->version) != CborNoError ||
        encode_key(&map, "kind") != CborNoError ||
        cbor_encode_text_stringz(&map, "command") != CborNoError ||
        encode_key(&map, "id") != CborNoError ||
        cbor_encode_uint(&map, command->id) != CborNoError ||
        encode_key(&map, "op") != CborNoError ||
        cbor_encode_text_stringz(&map,
            command->operation == FLOW_OPERATION_SET_ENERGY
                ? "set_energy"
                : "set_style") != CborNoError ||
        encode_key(&map, "value") != CborNoError) {
        return -1;
    }

    if (command->operation == FLOW_OPERATION_SET_ENERGY) {
        error = cbor_encode_uint(&map, command->energy);
    } else {
        error = cbor_encode_text_stringz(&map, command->style);
    }
    if (error != CborNoError ||
        cbor_encoder_close_container(&root, &map) != CborNoError) {
        return -1;
    }

    *encoded_size = cbor_encoder_get_buffer_size(&root, buffer);
    return 0;
}

static bool find_value(const CborValue *map, const char *key, CborValue *value)
{
    return cbor_value_map_find_value(map, key, value) == CborNoError &&
           cbor_value_is_valid(value);
}

static bool decode_uint(const CborValue *map,
                        const char *key,
                        uint64_t maximum,
                        uint64_t *result)
{
    CborValue value;
    if (!find_value(map, key, &value) || !cbor_value_is_unsigned_integer(&value) ||
        cbor_value_get_uint64(&value, result) != CborNoError) {
        return false;
    }
    return *result <= maximum;
}

static bool decode_text(const CborValue *map,
                        const char *key,
                        char *destination,
                        size_t capacity,
                        bool allow_empty)
{
    CborValue value;
    size_t length = 0;
    if (!find_value(map, key, &value) || !cbor_value_is_text_string(&value) ||
        cbor_value_calculate_string_length(&value, &length) != CborNoError ||
        length >= capacity || (!allow_empty && length == 0)) {
        return false;
    }

    size_t copied = capacity;
    if (cbor_value_copy_text_string(&value, destination, &copied, NULL) != CborNoError) {
        return false;
    }
    destination[length] = '\0';
    return true;
}

static bool decode_bool(const CborValue *map, const char *key, bool *result)
{
    CborValue value;
    return find_value(map, key, &value) && cbor_value_is_boolean(&value) &&
           cbor_value_get_boolean(&value, result) == CborNoError;
}

bool flow_protocol_validate_catalog(const uint8_t *data, size_t size)
{
    if (data == NULL || size == 0) {
        return false;
    }

    CborParser parser;
    CborValue root;
    CborValue styles;
    CborValue iterator;
    uint64_t version = 0;
    uint64_t energy_min = 0;
    uint64_t energy_max = 0;
    char kind[12];
    uint8_t known_mask = 0;

    if (cbor_parser_init(data, size, 0, &parser, &root) != CborNoError ||
        !cbor_value_is_map(&root) ||
        !decode_uint(&root, "v", UINT8_MAX, &version) || version != 1 ||
        !decode_text(&root, "kind", kind, sizeof(kind), false) ||
        strcmp(kind, "catalog") != 0 ||
        !decode_uint(&root, "energy_min", UINT8_MAX, &energy_min) ||
        !decode_uint(&root, "energy_max", UINT8_MAX, &energy_max) ||
        energy_min != 1 || energy_max != 5 ||
        !find_value(&root, "styles", &styles) ||
        !cbor_value_is_array(&styles) ||
        cbor_value_enter_container(&styles, &iterator) != CborNoError) {
        return false;
    }

    while (!cbor_value_at_end(&iterator)) {
        char id[FLOW_STYLE_ID_MAX];
        if (!cbor_value_is_map(&iterator) ||
            !decode_text(&iterator, "id", id, sizeof(id), false)) {
            return false;
        }
        if (strcmp(id, "hiphop") == 0) {
            known_mask |= 1u << 0;
        } else if (strcmp(id, "breaking") == 0) {
            known_mask |= 1u << 1;
        } else if (strcmp(id, "funk") == 0) {
            known_mask |= 1u << 2;
        } else if (strcmp(id, "locking") == 0) {
            known_mask |= 1u << 3;
        }
        if (cbor_value_advance(&iterator) != CborNoError) {
            return false;
        }
    }

    return known_mask == 0x0f;
}

static bool decode_music(const CborValue *map,
                         const char *key,
                         flow_music_state_t *music)
{
    CborValue value;
    uint64_t energy = 0;
    uint64_t bpm = 0;
    if (!find_value(map, key, &value) || !cbor_value_is_map(&value) ||
        !decode_uint(&value, "energy", 5, &energy) || energy < 1 ||
        !decode_text(&value, "style", music->style, sizeof(music->style), false) ||
        !decode_uint(&value, "bpm", UINT16_MAX, &bpm)) {
        return false;
    }

    music->energy = (uint8_t)energy;
    music->bpm = (uint16_t)bpm;
    return true;
}

static bool decode_target(const CborValue *map,
                          const flow_music_state_t *current,
                          flow_music_state_t *target)
{
    CborValue value;
    if (!find_value(map, "target", &value)) {
        return false;
    }
    if (cbor_value_is_null(&value)) {
        *target = *current;
        return true;
    }
    return decode_music(map, "target", target);
}

static bool decode_error(const CborValue *map, char *error, size_t capacity)
{
    CborValue value;
    if (!find_value(map, "error", &value)) {
        return false;
    }
    if (cbor_value_is_null(&value)) {
        error[0] = '\0';
        return true;
    }
    return decode_text(map, "error", error, capacity, true);
}

static bool valid_session_id(const char *session_id)
{
    for (size_t index = 0; index < FLOW_SESSION_ID_LENGTH; ++index) {
        if (!isxdigit((unsigned char)session_id[index])) {
            return false;
        }
    }
    return session_id[FLOW_SESSION_ID_LENGTH] == '\0';
}

static bool decode_phase(const CborValue *map, flow_phase_t *phase)
{
    static const struct {
        const char *text;
        flow_phase_t phase;
    } phases[] = {
        {"idle", FLOW_PHASE_IDLE},
        {"accepted", FLOW_PHASE_ACCEPTED},
        {"preparing", FLOW_PHASE_PREPARING},
        {"transitioning", FLOW_PHASE_TRANSITIONING},
        {"completed", FLOW_PHASE_COMPLETED},
        {"rejected", FLOW_PHASE_REJECTED},
        {"error", FLOW_PHASE_ERROR},
    };

    char text[16];
    if (!decode_text(map, "phase", text, sizeof(text), false)) {
        return false;
    }
    for (size_t index = 0; index < sizeof(phases) / sizeof(phases[0]); ++index) {
        if (strcmp(text, phases[index].text) == 0) {
            *phase = phases[index].phase;
            return true;
        }
    }
    return false;
}

int flow_protocol_decode_snapshot(const uint8_t *data,
                                  size_t size,
                                  flow_snapshot_t *snapshot)
{
    if (data == NULL || size == 0 || snapshot == NULL) {
        return -1;
    }

    CborParser parser;
    CborValue root;
    flow_snapshot_t decoded = {0};
    uint64_t version = 0;
    uint64_t revision = 0;
    uint64_t ack_id = 0;
    uint64_t eta_ms = 0;
    char kind[12];

    if (cbor_parser_init(data, size, 0, &parser, &root) != CborNoError ||
        !cbor_value_is_map(&root) ||
        !decode_uint(&root, "v", UINT8_MAX, &version) || version != 1 ||
        !decode_text(&root, "kind", kind, sizeof(kind), false) ||
        strcmp(kind, "snapshot") != 0 ||
        !decode_text(&root,
                     "session_id",
                     decoded.session_id,
                     sizeof(decoded.session_id),
                     false) ||
        !valid_session_id(decoded.session_id) ||
        !decode_uint(&root, "revision", UINT32_MAX, &revision) ||
        !decode_uint(&root, "ack_id", UINT32_MAX, &ack_id) ||
        !decode_phase(&root, &decoded.phase) ||
        !decode_bool(&root, "locked", &decoded.locked) ||
        !decode_uint(&root, "eta_ms", UINT32_MAX, &eta_ms) ||
        !decode_music(&root, "current", &decoded.current) ||
        !decode_target(&root, &decoded.current, &decoded.target) ||
        !decode_error(&root, decoded.error, sizeof(decoded.error))) {
        return -1;
    }

    decoded.revision = (uint32_t)revision;
    decoded.ack_id = (uint32_t)ack_id;
    decoded.eta_ms = (uint32_t)eta_ms;
    *snapshot = decoded;
    return 0;
}
