#!/usr/bin/env bash
set -euo pipefail

test_bin="$(mktemp /tmp/flow-core-test.XXXXXX)"
trap 'rm -f "$test_bin"' EXIT

clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_core/include \
  tests/host/test_flow_core.c \
  components/flow_core/flow_core.c \
  -o "$test_bin"

"$test_bin"
