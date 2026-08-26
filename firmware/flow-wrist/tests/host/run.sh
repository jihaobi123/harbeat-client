#!/usr/bin/env bash
set -euo pipefail

test_bin="$(mktemp /tmp/flow-core-test.XXXXXX)"
protocol_bin="$(mktemp /tmp/flow-protocol-test.XXXXXX)"
power_bin="$(mktemp /tmp/flow-power-test.XXXXXX)"
carousel_bin="$(mktemp /tmp/flow-carousel-test.XXXXXX)"
trap 'rm -f "$test_bin" "$protocol_bin" "$power_bin" "$carousel_bin"' EXIT

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
