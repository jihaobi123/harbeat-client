#!/usr/bin/env bash
set -euo pipefail

test_bin="$(mktemp /tmp/flow-core-test.XXXXXX)"
protocol_bin="$(mktemp /tmp/flow-protocol-test.XXXXXX)"
power_bin="$(mktemp /tmp/flow-power-test.XXXXXX)"
carousel_bin="$(mktemp /tmp/flow-carousel-test.XXXXXX)"
link_bin="$(mktemp /tmp/flow-link-test.XXXXXX)"
gesture_bin="$(mktemp /tmp/flow-gesture-test.XXXXXX)"
input_bin="$(mktemp /tmp/flow-input-test.XXXXXX)"
trap 'rm -f "$test_bin" "$protocol_bin" "$power_bin" "$carousel_bin" "$link_bin" "$gesture_bin" "$input_bin"' EXIT

clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_core/include \
  tests/host/test_flow_core.c \
  components/flow_core/flow_core.c \
  -o "$test_bin"

"$test_bin"

clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_core/include \
  -Icomponents/flow_protocol/include \
  -Imanaged_components/espressif__cbor/tinycbor/src \
  tests/host/test_protocol_schema.c \
  components/flow_protocol/flow_protocol.c \
  managed_components/espressif__cbor/tinycbor/src/cborencoder.c \
  managed_components/espressif__cbor/tinycbor/src/cborparser.c \
  -o "$protocol_bin"

"$protocol_bin"

clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_power/include \
  tests/host/test_power_policy.c \
  components/flow_power/flow_power_policy.c \
  -o "$power_bin"

"$power_bin"

clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_ui/include \
  tests/host/test_carousel_model.c \
  components/flow_ui/flow_carousel_model.c \
  -o "$carousel_bin"

"$carousel_bin"

clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_ble/include \
  -Icomponents/flow_core/include \
  tests/host/test_link_state.c \
  components/flow_ble/flow_link_state.c \
  -o "$link_bin"

"$link_bin"

clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_gesture/include \
  tests/host/test_gesture_engine.c \
  components/flow_gesture/flow_gesture_engine.c \
  -o "$gesture_bin"

"$gesture_bin"

clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_core/include \
  -Icomponents/flow_gesture/include \
  tests/host/test_input_coordinator.c \
  components/flow_core/flow_input_coordinator.c \
  -o "$input_bin"

"$input_bin"
