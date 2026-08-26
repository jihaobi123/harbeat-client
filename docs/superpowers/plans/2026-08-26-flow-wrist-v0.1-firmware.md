# Flow Wrist V0.1 Firmware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Waveshare ESP32-S3-Touch-AMOLED-2.06 上交付可独立演示的 Flow Wrist 固件，完成已批准的 LVGL 交互、状态机、CBOR 协议、BLE Peripheral、BOOT 唤醒和电量基础功能。

**Architecture:** 固件从微雪 `02_lvgl_demo_v9` 的 BSP 初始化方式起步，UI、状态、协议、BLE 和电源分成独立组件。BLE 回调不直接调用 LVGL；协议消息先经过校验和状态归并，再由 UI 队列刷新页面。开发阶段提供本地 Hub 模拟器，因此没有 RK3588 时也能演示完整的 10–20 秒切换流程。

**Tech Stack:** ESP-IDF 5.5.5、LVGL 9.5.0、Waveshare BSP 2.0.0、ESP-IDF NimBLE、Espressif TinyCBOR 0.6.1~4、FreeRTOS、C11/C++17、macOS Apple Silicon

---

## 范围拆分

本计划只处理 Wrist。RK3588 BlueZ Central、音乐引擎适配和真实选曲倒计时另写 Hub 实施计划。Wrist 通过本地模拟器和标准 GATT 接口独立验收后，再进入 Hub 联调。

## 文件结构

```text
firmware/flow-wrist/
├── CMakeLists.txt
├── partitions.csv
├── sdkconfig.defaults
├── README.md
├── main/
│   ├── CMakeLists.txt
│   ├── idf_component.yml
│   └── app_main.c
├── components/
│   ├── flow_core/
│   │   ├── CMakeLists.txt
│   │   ├── include/flow_core.h
│   │   └── flow_core.c
│   ├── flow_protocol/
│   │   ├── CMakeLists.txt
│   │   ├── include/flow_protocol.h
│   │   └── flow_protocol.c
│   ├── flow_ui/
│   │   ├── CMakeLists.txt
│   │   ├── include/flow_ui.h
│   │   ├── flow_ui_internal.h
│   │   ├── flow_ui.c
│   │   ├── flow_ui_theme.c
│   │   ├── flow_ui_home.c
│   │   ├── flow_ui_carousel.c
│   │   ├── flow_ui_transition.c
│   │   └── flow_ui_art.c
│   ├── flow_ble/
│   │   ├── CMakeLists.txt
│   │   ├── include/flow_ble.h
│   │   └── flow_ble.c
│   ├── flow_power/
│   │   ├── CMakeLists.txt
│   │   ├── include/flow_power.h
│   │   └── flow_power.c
│   └── flow_simulator/
│       ├── CMakeLists.txt
│       ├── Kconfig
│       ├── include/flow_simulator.h
│       └── flow_simulator.c
├── tests/host/
│   ├── run.sh
│   ├── test_flow_core.c
│   └── test_protocol_schema.c
└── docs/
    ├── hardware-bringup.md
    └── ble-test.md
```

`flow_core` 和协议字段校验保持纯 C，不依赖 ESP-IDF，方便在 Mac 上用 Clang 快速测试。显示、BLE 和电源组件只负责平台接口。

### Task 1: 安装并验证 Mac ESP-IDF 工具链

**Files:**
- Create: `firmware/flow-wrist/docs/hardware-bringup.md`

- [ ] **Step 1: 安装 Espressif Installation Manager**

Run:

```bash
brew tap espressif/eim
brew install eim
```

Expected: `eim --version` 返回版本号，命令退出码为 0。

- [ ] **Step 2: 安装 ESP-IDF 5.5.5**

Run:

```bash
eim install -i v5.5.5
```

Expected: 安装器报告 `Successfully installed IDF`，工具放在用户目录的 `.espressif` 下。

- [ ] **Step 3: 激活环境并验证工具**

Run:

```bash
source "$HOME/.espressif/tools/activate_idf_v5.5.5.sh"
idf.py --version
cmake --version
ninja --version
python --version
```

Expected:

```text
ESP-IDF v5.5.5
CMake 可运行
Ninja 可运行
Python 3.10 或更高
```

- [ ] **Step 4: 记录本机和 USB 基线**

Create `firmware/flow-wrist/docs/hardware-bringup.md`:

```markdown
# Flow Wrist hardware bring-up

## Toolchain

- ESP-IDF: 5.5.5
- Target: esp32s3
- Board: Waveshare ESP32-S3-Touch-AMOLED-2.06
- BSP: waveshare/esp32_s3_touch_amoled_2_06 2.0.0
- LVGL: 9.5.0

## USB

The native USB serial port should appear as `/dev/cu.usbmodem*` on macOS.
If it does not appear, use a data-capable USB-C cable, hold BOOT while reconnecting,
then release BOOT after the port is visible.
```

- [ ] **Step 5: Commit the environment record**

```bash
git add firmware/flow-wrist/docs/hardware-bringup.md
git commit -m "docs: record Flow Wrist toolchain baseline"
```

### Task 2: 建立可编译的板级工程

**Files:**
- Create: `firmware/flow-wrist/CMakeLists.txt`
- Create: `firmware/flow-wrist/partitions.csv`
- Create: `firmware/flow-wrist/sdkconfig.defaults`
- Create: `firmware/flow-wrist/main/CMakeLists.txt`
- Create: `firmware/flow-wrist/main/idf_component.yml`
- Create: `firmware/flow-wrist/main/app_main.c`

- [ ] **Step 1: 创建顶层构建文件**

Create `firmware/flow-wrist/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(flow_wrist)
```

Create `firmware/flow-wrist/partitions.csv`:

```csv
# Name,   Type, SubType, Offset,  Size, Flags
nvs,      data, nvs,     0x9000,  0x6000,
phy_init, data, phy,     0xf000,  0x1000,
factory,  app,  factory, ,        8M,
storage,  data, spiffs,  ,        7M,
```

- [ ] **Step 2: 固定 BSP、LVGL 和 CBOR 依赖**

Create `firmware/flow-wrist/main/idf_component.yml`:

```yaml
dependencies:
  waveshare/esp32_s3_touch_amoled_2_06:
    version: "2.0.0"
  lvgl/lvgl:
    version: "9.5.0"
    public: true
  espressif/cbor:
    version: "0.6.1~4"
  espressif/esp_codec_dev:
    version: "~1.5"
  espressif/usb:
    version: "^1.4.1"
```

- [ ] **Step 3: 配置 ESP32-S3、PSRAM、LVGL 和 NimBLE**

Create `firmware/flow-wrist/sdkconfig.defaults`:

```text
CONFIG_ESPTOOLPY_FLASHMODE_QIO=y
CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"
CONFIG_COMPILER_OPTIMIZATION_PERF=y
CONFIG_SPIRAM=y
CONFIG_SPIRAM_MODE_OCT=y
CONFIG_SPIRAM_SPEED_80M=y
CONFIG_SPIRAM_FETCH_INSTRUCTIONS=y
CONFIG_SPIRAM_RODATA=y
CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y
CONFIG_FREERTOS_HZ=1000
CONFIG_LV_OS_FREERTOS=y
CONFIG_LV_DRAW_SW_DRAW_UNIT_CNT=2
CONFIG_LV_DEF_REFR_PERIOD=15
CONFIG_LV_USE_CLIB_MALLOC=y
CONFIG_LV_USE_CLIB_STRING=y
CONFIG_LV_USE_CLIB_SPRINTF=y
CONFIG_LV_USE_FONT_COMPRESSED=y
CONFIG_BT_ENABLED=y
CONFIG_BT_NIMBLE_ENABLED=y
CONFIG_BT_NIMBLE_ROLE_PERIPHERAL=y
CONFIG_BT_NIMBLE_MAX_CONNECTIONS=1
CONFIG_BT_NIMBLE_ATT_PREFERRED_MTU=247
```

- [ ] **Step 4: 写入最小显示入口**

Create `firmware/flow-wrist/main/CMakeLists.txt`:

```cmake
idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash
)
```

Create `firmware/flow-wrist/main/app_main.c`:

```c
#include "bsp/display.h"
#include "esp_err.h"
#include "nvs_flash.h"
#include "lvgl.h"

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    bsp_display_start();
    bsp_display_lock(0);

    lv_obj_t *screen = lv_screen_active();
    lv_obj_set_style_bg_color(screen, lv_color_hex(0xFFF8ED), 0);

    lv_obj_t *label = lv_label_create(screen);
    lv_label_set_text(label, "FLOW WRIST\nBRING-UP");
    lv_obj_set_style_text_color(label, lv_color_hex(0x11110F), 0);
    lv_obj_center(label);

    bsp_display_unlock();
}
```

- [ ] **Step 5: 构建工程**

Run:

```bash
cd firmware/flow-wrist
idf.py set-target esp32s3
idf.py build
```

Expected: `Project build complete`，生成 `build/flow_wrist.bin`。

- [ ] **Step 6: 连接硬件后烧录最小界面**

Run:

```bash
serial_port="$(find /dev -maxdepth 1 -name 'cu.usbmodem*' -print -quit)"
test -n "$serial_port"
idf.py -p "$serial_port" flash monitor
```

Expected: 屏幕显示暖白背景和 `FLOW WRIST / BRING-UP`；串口没有持续重启或显示驱动错误。若 `test` 失败，先检查数据线和 BOOT 下载模式，不执行烧录。

- [ ] **Step 7: Commit**

```bash
git add firmware/flow-wrist
git commit -m "feat: scaffold Flow Wrist ESP-IDF firmware"
```

### Task 3: 用纯 C 状态模型锁定业务规则

**Files:**
- Create: `firmware/flow-wrist/components/flow_core/CMakeLists.txt`
- Create: `firmware/flow-wrist/components/flow_core/include/flow_core.h`
- Create: `firmware/flow-wrist/components/flow_core/flow_core.c`
- Create: `firmware/flow-wrist/tests/host/test_flow_core.c`
- Create: `firmware/flow-wrist/tests/host/run.sh`

- [ ] **Step 1: 写状态测试**

Create `firmware/flow-wrist/tests/host/test_flow_core.c`:

```c
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "flow_core.h"

static flow_snapshot_t snapshot(uint32_t revision, flow_phase_t phase, bool locked)
{
    flow_snapshot_t value = {0};
    strcpy(value.session_id, "8f3a19d04b7c221e");
    value.revision = revision;
    value.phase = phase;
    value.locked = locked;
    value.current.energy = 3;
    strcpy(value.current.style, "hiphop");
    value.current.bpm = 96;
    value.target.energy = 5;
    strcpy(value.target.style, "breaking");
    value.target.bpm = 108;
    value.eta_ms = 14000;
    return value;
}

int main(void)
{
    flow_app_state_t state;
    flow_state_init(&state);
    assert(state.screen == FLOW_SCREEN_CONNECTING);

    flow_snapshot_t first = snapshot(7, FLOW_PHASE_IDLE, false);
    assert(flow_state_apply_snapshot(&state, &first) == FLOW_APPLY_OK);
    assert(state.screen == FLOW_SCREEN_HOME);

    assert(flow_state_open_control(&state, FLOW_SCREEN_STYLE));
    assert(state.screen == FLOW_SCREEN_STYLE);
    flow_state_return_home(&state);
    assert(state.screen == FLOW_SCREEN_HOME);

    assert(flow_state_begin_command(&state, 42) == FLOW_COMMAND_STARTED);
    assert(state.screen == FLOW_SCREEN_SENDING);
    assert(flow_state_begin_command(&state, 43) == FLOW_COMMAND_BLOCKED);

    flow_snapshot_t busy = snapshot(8, FLOW_PHASE_PREPARING, true);
    busy.ack_id = 42;
    assert(flow_state_apply_snapshot(&state, &busy) == FLOW_APPLY_OK);
    assert(state.screen == FLOW_SCREEN_TRANSITION);

    flow_snapshot_t stale = snapshot(7, FLOW_PHASE_COMPLETED, false);
    assert(flow_state_apply_snapshot(&state, &stale) == FLOW_APPLY_STALE);
    assert(state.screen == FLOW_SCREEN_TRANSITION);

    flow_snapshot_t done = snapshot(9, FLOW_PHASE_COMPLETED, false);
    done.eta_ms = 0;
    done.current = done.target;
    assert(flow_state_apply_snapshot(&state, &done) == FLOW_APPLY_OK);
    assert(state.screen == FLOW_SCREEN_COMPLETE);

    flow_state_return_home(&state);
    assert(state.screen == FLOW_SCREEN_HOME);

    puts("flow_core tests passed");
    return 0;
}
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
clang -std=c11 -Wall -Wextra -Werror \
  -Ifirmware/flow-wrist/components/flow_core/include \
  firmware/flow-wrist/tests/host/test_flow_core.c \
  firmware/flow-wrist/components/flow_core/flow_core.c \
  -o /tmp/flow_core_test
```

Expected: FAIL，因为 `flow_core.h` 和实现还不存在。

- [ ] **Step 3: 定义状态模型**

Create `firmware/flow-wrist/components/flow_core/include/flow_core.h`:

```c
#pragma once

#include <stdbool.h>
#include <stdint.h>

#define FLOW_STYLE_ID_MAX 16
#define FLOW_SESSION_ID_LENGTH 16

typedef enum {
    FLOW_PHASE_IDLE,
    FLOW_PHASE_ACCEPTED,
    FLOW_PHASE_PREPARING,
    FLOW_PHASE_TRANSITIONING,
    FLOW_PHASE_COMPLETED,
    FLOW_PHASE_REJECTED,
    FLOW_PHASE_ERROR
} flow_phase_t;

typedef enum {
    FLOW_SCREEN_OFF,
    FLOW_SCREEN_CONNECTING,
    FLOW_SCREEN_HOME,
    FLOW_SCREEN_ENERGY,
    FLOW_SCREEN_STYLE,
    FLOW_SCREEN_SENDING,
    FLOW_SCREEN_TRANSITION,
    FLOW_SCREEN_COMPLETE,
    FLOW_SCREEN_ERROR
} flow_screen_t;

typedef struct {
    uint8_t energy;
    char style[FLOW_STYLE_ID_MAX];
    uint16_t bpm;
} flow_music_state_t;

typedef struct {
    char session_id[FLOW_SESSION_ID_LENGTH + 1];
    uint32_t revision;
    uint32_t ack_id;
    flow_phase_t phase;
    bool locked;
    uint32_t eta_ms;
    flow_music_state_t current;
    flow_music_state_t target;
    char error[24];
} flow_snapshot_t;

typedef struct {
    flow_screen_t screen;
    flow_snapshot_t snapshot;
    uint32_t pending_command_id;
    bool has_snapshot;
} flow_app_state_t;

typedef enum { FLOW_APPLY_OK, FLOW_APPLY_STALE, FLOW_APPLY_INVALID } flow_apply_result_t;
typedef enum { FLOW_COMMAND_STARTED, FLOW_COMMAND_BLOCKED } flow_command_result_t;

void flow_state_init(flow_app_state_t *state);
flow_apply_result_t flow_state_apply_snapshot(flow_app_state_t *state,
                                              const flow_snapshot_t *snapshot);
flow_command_result_t flow_state_begin_command(flow_app_state_t *state,
                                               uint32_t command_id);
bool flow_state_open_control(flow_app_state_t *state, flow_screen_t screen);
void flow_state_return_home(flow_app_state_t *state);
```

- [ ] **Step 4: 实现状态归并**

Create `firmware/flow-wrist/components/flow_core/flow_core.c`:

```c
#include "flow_core.h"
#include <string.h>

static bool valid_snapshot(const flow_snapshot_t *snapshot)
{
    if (snapshot == NULL || strlen(snapshot->session_id) != FLOW_SESSION_ID_LENGTH) {
        return false;
    }
    if (snapshot->current.energy < 1 || snapshot->current.energy > 5) {
        return false;
    }
    return true;
}

void flow_state_init(flow_app_state_t *state)
{
    memset(state, 0, sizeof(*state));
    state->screen = FLOW_SCREEN_CONNECTING;
}

flow_command_result_t flow_state_begin_command(flow_app_state_t *state,
                                               uint32_t command_id)
{
    if (!state->has_snapshot || state->snapshot.locked ||
        state->screen == FLOW_SCREEN_SENDING ||
        state->screen == FLOW_SCREEN_TRANSITION) {
        return FLOW_COMMAND_BLOCKED;
    }
    state->pending_command_id = command_id;
    state->screen = FLOW_SCREEN_SENDING;
    return FLOW_COMMAND_STARTED;
}

bool flow_state_open_control(flow_app_state_t *state, flow_screen_t screen)
{
    if (!state->has_snapshot || state->snapshot.locked ||
        (screen != FLOW_SCREEN_ENERGY && screen != FLOW_SCREEN_STYLE)) {
        return false;
    }
    state->screen = screen;
    return true;
}

void flow_state_return_home(flow_app_state_t *state)
{
    if (state->has_snapshot && !state->snapshot.locked) {
        state->screen = FLOW_SCREEN_HOME;
    }
}

flow_apply_result_t flow_state_apply_snapshot(flow_app_state_t *state,
                                              const flow_snapshot_t *snapshot)
{
    if (!valid_snapshot(snapshot)) {
        return FLOW_APPLY_INVALID;
    }

    bool same_session = state->has_snapshot &&
        strcmp(state->snapshot.session_id, snapshot->session_id) == 0;
    if (same_session && snapshot->revision <= state->snapshot.revision) {
        return FLOW_APPLY_STALE;
    }

    state->snapshot = *snapshot;
    state->has_snapshot = true;

    switch (snapshot->phase) {
    case FLOW_PHASE_IDLE:
        state->screen = FLOW_SCREEN_HOME;
        break;
    case FLOW_PHASE_ACCEPTED:
    case FLOW_PHASE_PREPARING:
    case FLOW_PHASE_TRANSITIONING:
        state->screen = FLOW_SCREEN_TRANSITION;
        break;
    case FLOW_PHASE_COMPLETED:
        state->screen = FLOW_SCREEN_COMPLETE;
        break;
    case FLOW_PHASE_REJECTED:
    case FLOW_PHASE_ERROR:
        state->screen = FLOW_SCREEN_ERROR;
        break;
    }
    return FLOW_APPLY_OK;
}
```

Create `firmware/flow-wrist/components/flow_core/CMakeLists.txt`:

```cmake
idf_component_register(SRCS "flow_core.c" INCLUDE_DIRS "include")
```

- [ ] **Step 5: 创建快速测试脚本并运行**

Create `firmware/flow-wrist/tests/host/run.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
test_bin="$(mktemp /tmp/flow-core-test.XXXXXX)"
clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_core/include \
  tests/host/test_flow_core.c \
  components/flow_core/flow_core.c \
  -o "$test_bin"
"$test_bin"
```

Run from `firmware/flow-wrist`:

```bash
chmod +x tests/host/run.sh
./tests/host/run.sh
```

Expected: `flow_core tests passed`。

- [ ] **Step 6: Commit**

```bash
git add firmware/flow-wrist/components/flow_core firmware/flow-wrist/tests/host
git commit -m "feat: add Flow Wrist state reducer"
```

### Task 4: 实现 CBOR 命令和 Hub 快照

**Files:**
- Create: `firmware/flow-wrist/components/flow_protocol/CMakeLists.txt`
- Create: `firmware/flow-wrist/components/flow_protocol/include/flow_protocol.h`
- Create: `firmware/flow-wrist/components/flow_protocol/flow_protocol.c`
- Create: `firmware/flow-wrist/tests/host/test_protocol_schema.c`

- [ ] **Step 1: 写字段校验测试**

Create `firmware/flow-wrist/tests/host/test_protocol_schema.c`:

```c
#include <assert.h>
#include <string.h>
#include "flow_protocol.h"

int main(void)
{
    flow_command_t command = {
        .version = 1,
        .id = 42,
        .operation = FLOW_OPERATION_SET_ENERGY,
        .energy = 5
    };
    assert(flow_protocol_validate_command(&command));
    command.energy = 0;
    assert(!flow_protocol_validate_command(&command));

    command.operation = FLOW_OPERATION_SET_STYLE;
    strcpy(command.style, "breaking");
    assert(flow_protocol_validate_command(&command));
    strcpy(command.style, "unknown");
    assert(!flow_protocol_validate_command(&command));
    return 0;
}
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_core/include \
  -Icomponents/flow_protocol/include \
  tests/host/test_protocol_schema.c \
  components/flow_protocol/flow_protocol.c \
  -o /tmp/flow_protocol_schema_test
```

Expected: FAIL，因为协议文件尚未创建。

- [ ] **Step 3: 定义协议接口**

Create `firmware/flow-wrist/components/flow_protocol/include/flow_protocol.h`:

```c
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
```

- [ ] **Step 4: 实现纯 C 字段校验**

Add to `firmware/flow-wrist/components/flow_protocol/flow_protocol.c` before the CBOR functions:

```c
#include "flow_protocol.h"
#include <string.h>

static bool known_style(const char *style)
{
    static const char *styles[] = {"hiphop", "breaking", "funk", "locking"};
    for (size_t index = 0; index < sizeof(styles) / sizeof(styles[0]); ++index) {
        if (strcmp(style, styles[index]) == 0) {
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
```

- [ ] **Step 5: 扩展 host 测试脚本**

Append to `firmware/flow-wrist/tests/host/run.sh`:

```bash
protocol_bin="$(mktemp /tmp/flow-protocol-test.XXXXXX)"
clang -std=c11 -Wall -Wextra -Werror \
  -Icomponents/flow_core/include \
  -Icomponents/flow_protocol/include \
  tests/host/test_protocol_schema.c \
  components/flow_protocol/flow_protocol.c \
  -DFLOW_PROTOCOL_SCHEMA_ONLY \
  -o "$protocol_bin"
"$protocol_bin"
```

Wrap TinyCBOR includes and CBOR functions in `flow_protocol.c` with:

```c
#ifndef FLOW_PROTOCOL_SCHEMA_ONLY
#include "cbor.h"
#endif
```

The schema-only host build contains `flow_protocol_validate_command`; ESP-IDF builds the CBOR section.

- [ ] **Step 6: 实现 CBOR command encoder**

Implement `flow_protocol_encode_command` using a fixed map with five fields: `v`, `kind`, `id`, `op`, `value`. Use `set_energy` or `set_style` for `op`. Return `0` on success and `-1` on validation or buffer failure. After closing the map, calculate the byte count with `cbor_encoder_get_buffer_size`.

Required encoder structure:

```c
CborEncoder root;
CborEncoder map;
cbor_encoder_init(&root, buffer, capacity, 0);
cbor_encoder_create_map(&root, &map, 5);
cbor_encode_text_stringz(&map, "v");
cbor_encode_uint(&map, command->version);
cbor_encode_text_stringz(&map, "kind");
cbor_encode_text_stringz(&map, "command");
cbor_encode_text_stringz(&map, "id");
cbor_encode_uint(&map, command->id);
cbor_encode_text_stringz(&map, "op");
cbor_encode_text_stringz(&map,
    command->operation == FLOW_OPERATION_SET_ENERGY ? "set_energy" : "set_style");
cbor_encode_text_stringz(&map, "value");
if (command->operation == FLOW_OPERATION_SET_ENERGY) {
    cbor_encode_uint(&map, command->energy);
} else {
    cbor_encode_text_stringz(&map, command->style);
}
cbor_encoder_close_container(&root, &map);
*encoded_size = cbor_encoder_get_buffer_size(&root, buffer);
```

- [ ] **Step 7: 实现 snapshot decoder**

Use `cbor_value_map_find_value` for `v`, `kind`, `session_id`, `revision`, `ack_id`, `phase`, `locked`, `eta_ms`, `current`, `target`, and `error`. Decode `current` and `target` through one private helper that requires `energy`, `style`, and `bpm`. Reject:

- `v` other than 1;
- `kind` other than `snapshot`;
- session IDs not exactly 16 hexadecimal characters;
- energy outside 1–5;
- unknown phase text;
- text longer than the destination arrays.

Map phase text to the enum in this exact order:

```c
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
```

- [ ] **Step 8: 注册组件并构建**

Create `firmware/flow-wrist/components/flow_protocol/CMakeLists.txt`:

```cmake
idf_component_register(
    SRCS "flow_protocol.c"
    INCLUDE_DIRS "include"
    REQUIRES flow_core cbor
)
```

Run:

```bash
./tests/host/run.sh
idf.py build
```

Expected: host tests pass and ESP-IDF links TinyCBOR without undefined symbols.

- [ ] **Step 9: Commit**

```bash
git add firmware/flow-wrist/components/flow_protocol firmware/flow-wrist/tests/host
git commit -m "feat: add Flow Wrist CBOR protocol"
```

### Task 5: 建立 LVGL 主题、页面路由和动作队列

**Files:**
- Create: `firmware/flow-wrist/components/flow_ui/CMakeLists.txt`
- Create: `firmware/flow-wrist/components/flow_ui/include/flow_ui.h`
- Create: `firmware/flow-wrist/components/flow_ui/flow_ui_internal.h`
- Create: `firmware/flow-wrist/components/flow_ui/flow_ui.c`
- Create: `firmware/flow-wrist/components/flow_ui/flow_ui_theme.c`
- Modify: `firmware/flow-wrist/main/CMakeLists.txt`
- Modify: `firmware/flow-wrist/main/app_main.c`

- [ ] **Step 1: 定义 UI 动作和入口**

Create `firmware/flow-wrist/components/flow_ui/include/flow_ui.h`:

```c
#pragma once

#include <stdint.h>
#include "flow_core.h"

typedef enum {
    FLOW_UI_ACTION_OPEN_ENERGY,
    FLOW_UI_ACTION_OPEN_STYLE,
    FLOW_UI_ACTION_BACK,
    FLOW_UI_ACTION_SET_ENERGY,
    FLOW_UI_ACTION_SET_STYLE,
    FLOW_UI_ACTION_COMPLETE_TIMEOUT
} flow_ui_action_type_t;

typedef struct {
    flow_ui_action_type_t type;
    uint8_t energy;
    char style[FLOW_STYLE_ID_MAX];
} flow_ui_action_t;

typedef void (*flow_ui_action_handler_t)(const flow_ui_action_t *action, void *context);

void flow_ui_init(flow_ui_action_handler_t handler, void *context);
void flow_ui_render(const flow_app_state_t *state);
void flow_ui_show_offline(void);
void flow_ui_show_syncing(void);
```

Create `flow_ui_internal.h` for declarations shared only inside the UI component:

```c
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

void flow_ui_home_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_carousel_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_transition_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_transition_update(const flow_app_state_t *state);
void flow_ui_complete_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_status_create(lv_obj_t *root, const flow_app_state_t *state);
void flow_ui_emit(const flow_ui_action_t *action);
```

- [ ] **Step 2: 实现设计 tokens**

In `flow_ui_theme.c`, expose colors through functions rather than global mutable objects:

```c
#include "lvgl.h"

lv_color_t flow_color_paper(void) { return lv_color_hex(0xFFF8ED); }
lv_color_t flow_color_ink(void) { return lv_color_hex(0x11110F); }
lv_color_t flow_color_pink(void) { return lv_color_hex(0xF54F87); }
lv_color_t flow_color_yellow(void) { return lv_color_hex(0xFFD21E); }
lv_color_t flow_color_blue(void) { return lv_color_hex(0x2C8FE6); }
lv_color_t flow_color_green(void) { return lv_color_hex(0x15933A); }
lv_color_t flow_color_orange(void) { return lv_color_hex(0xF47A27); }
```

Create `flow_ui/CMakeLists.txt` initially with only the files that exist in this task:

```cmake
idf_component_register(
    SRCS "flow_ui.c" "flow_ui_theme.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "."
    REQUIRES flow_core lvgl
)
```

- [ ] **Step 3: 实现单实例页面路由**

`flow_ui.c` keeps one root object and rebuilds it only when `state->screen` changes. It must:

- assert that `bsp_display_lock` has already been taken by the caller;
- delete the old root with `lv_obj_delete`;
- create a 410×502 root using the paper color;
- dispatch to `flow_ui_home_create`, `flow_ui_carousel_create`, `flow_ui_transition_create`, `flow_ui_complete_create`, or `flow_ui_status_create`;
- store the last rendered `revision` and update countdown labels in place when the screen does not change.

Use this routing switch:

```c
switch (state->screen) {
case FLOW_SCREEN_HOME:
    flow_ui_home_create(root, state, emit_action);
    break;
case FLOW_SCREEN_ENERGY:
case FLOW_SCREEN_STYLE:
    flow_ui_carousel_create(root, state, emit_action);
    break;
case FLOW_SCREEN_TRANSITION:
    flow_ui_transition_create(root, state);
    break;
case FLOW_SCREEN_COMPLETE:
    flow_ui_complete_create(root, state);
    break;
default:
    flow_ui_status_create(root, state);
    break;
}
```

- [ ] **Step 4: 接入主程序队列**

`app_main.c` creates a FreeRTOS queue of `flow_app_state_t` snapshots. A UI timer running under the BSP LVGL task drains the latest item and calls `flow_ui_render`. BLE and simulator callbacks only enqueue data.

Use a queue length of 1 and `xQueueOverwrite`, so stale countdown frames cannot build up.

- [ ] **Step 5: 构建并检查线程边界**

Run:

```bash
idf.py build
rg -n 'lv_[a-zA-Z0-9_]+\(' components/flow_ble components/flow_simulator
```

Expected: build passes; the search prints no LVGL calls outside `flow_ui` and `app_main`'s locked rendering path.

- [ ] **Step 6: Commit**

```bash
git add firmware/flow-wrist/components/flow_ui firmware/flow-wrist/main
git commit -m "feat: add Flow Wrist LVGL application shell"
```

### Task 6: 实现双入口主页和海报轮播

**Files:**
- Create: `firmware/flow-wrist/components/flow_ui/flow_ui_home.c`
- Create: `firmware/flow-wrist/components/flow_ui/flow_ui_carousel.c`
- Create: `firmware/flow-wrist/components/flow_ui/flow_ui_art.c`
- Modify: `firmware/flow-wrist/components/flow_ui/CMakeLists.txt`

- [ ] **Step 1: 创建双入口主页**

Build two full-width cards under `WHAT SHIFTS NEXT?`:

- Energy card: yellow, shows `ENERGY` and two-digit current value.
- Style card: blue, shows `STYLE` and uppercase current style.
- Online state: green dot plus `HUB`.
- Card callbacks emit `OPEN_ENERGY` or `OPEN_STYLE`.

Cards must have at least 72 px height and use `LV_OBJ_FLAG_CLICKABLE`. The whole card, not only the label, is the hit target.

- [ ] **Step 2: 建立统一轮播数据模型**

Use these fixed data arrays in `flow_ui_carousel.c`:

```c
static const char *energy_labels[] = {
    "01 / WARM", "02 / LOW", "03 / FLOW", "04 / HIGH", "05 / PEAK"
};

static const char *style_ids[] = {
    "hiphop", "breaking", "funk", "locking"
};

static const char *style_labels[] = {
    "HIPHOP", "BREAKING", "FUNK", "LOCKING"
};
```

Energy stops at 1 and 5. Style wraps between the first and last item.

- [ ] **Step 3: 区分 swipe 和 click**

On `LV_EVENT_GESTURE`, read `lv_indev_get_gesture_dir`. Left and right change the preview index and start a 250 ms slide animation. Set `gesture_consumed = true`.

On `LV_EVENT_RELEASED`, send only when:

```c
if (!carousel->gesture_consumed && carousel->preview_index != carousel->current_index) {
    emit_selection(carousel);
}
carousel->gesture_consumed = false;
```

Clicking the current value displays `CURRENT / 已生效` for 900 ms and emits no command.

- [ ] **Step 4: 用 LVGL primitives 建立首批插画**

`flow_ui_art.c` creates small editorial doodles from lines, arcs and circles. Provide one function per category:

```c
void flow_ui_art_energy(lv_obj_t *parent, uint8_t energy);
void flow_ui_art_style(lv_obj_t *parent, const char *style_id);
void flow_ui_art_record(lv_obj_t *parent, lv_color_t accent);
```

The first firmware uses vector-like primitives so the UI can ship before final raster artwork. Each function stays inside a 160×120 art container and creates no timer.

Update `flow_ui/CMakeLists.txt` so `SRCS` also includes `flow_ui_home.c`, `flow_ui_carousel.c`, and `flow_ui_art.c`.

- [ ] **Step 5: 真机检查主页和轮播**

Run:

```bash
serial_port="$(find /dev -maxdepth 1 -name 'cu.usbmodem*' -print -quit)"
test -n "$serial_port"
idf.py -p "$serial_port" flash monitor
```

Expected:

- BOOT 后显示双入口主页；
- 能量页不能从 1 继续左移或从 5 继续右移；
- 风格页可以循环；
- 快速 swipe 不触发发送；
- 点击不同海报只发送一次 UI action。

- [ ] **Step 6: Commit**

```bash
git add firmware/flow-wrist/components/flow_ui
git commit -m "feat: add Flow Wrist poster controls"
```

### Task 7: 实现执行、完成和异常页面

**Files:**
- Create: `firmware/flow-wrist/components/flow_ui/flow_ui_transition.c`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui.c`

- [ ] **Step 1: 创建双唱片执行页**

The transition page must render:

```text
CHANGE IS IN MOTION.
NOW: <current style>
NEXT: <target style>
NEXT TRACK: <ceil(eta_ms / 1000)>s
ENERGY: <target energy>
BPM: <target bpm>
```

Style covers and countdown use the largest type. Energy and BPM use compact fact boxes below the countdown strip.

- [ ] **Step 2: 更新倒计时而不重建页面**

Keep pointers to the countdown, phase, energy and BPM labels. When the screen stays `FLOW_SCREEN_TRANSITION`, update only label text. Do not recreate the record illustrations once per second.

- [ ] **Step 3: 创建完成页**

Display `<CURRENT STYLE> IS LIVE` and a green check only for `FLOW_PHASE_COMPLETED`. Schedule a one-shot LVGL timer for 2000 ms; the timer emits `FLOW_UI_ACTION_COMPLETE_TIMEOUT`, and the state owner calls `flow_state_return_home()` using the completed `current` snapshot. A manual back action remains separate from this completion timeout.

- [ ] **Step 4: 创建错误状态**

Map errors exactly:

```text
busy             → 正在完成上一次切换
invalid_energy   → 能量指令无效
unknown_style    → 风格列表已变化
version_mismatch → 需要更新固件
internal_error   → Hub 无法完成切换
```

Offline and syncing use separate status pages. No error page may call the command callback automatically.

Update `flow_ui/CMakeLists.txt` so `SRCS` also includes `flow_ui_transition.c`.

- [ ] **Step 5: Build and visual verification**

Run:

```bash
idf.py build
serial_port="$(find /dev -maxdepth 1 -name 'cu.usbmodem*' -print -quit)"
test -n "$serial_port"
idf.py -p "$serial_port" flash monitor
```

Expected: transition labels update without flicker; success appears only after a completed snapshot; tapping while busy emits no command.

- [ ] **Step 6: Commit**

```bash
git add firmware/flow-wrist/components/flow_ui
git commit -m "feat: add Flow Wrist transition feedback"
```

### Task 8: 添加本地 Hub 模拟器

**Files:**
- Create: `firmware/flow-wrist/components/flow_simulator/CMakeLists.txt`
- Create: `firmware/flow-wrist/components/flow_simulator/Kconfig`
- Create: `firmware/flow-wrist/components/flow_simulator/include/flow_simulator.h`
- Create: `firmware/flow-wrist/components/flow_simulator/flow_simulator.c`
- Modify: `firmware/flow-wrist/main/app_main.c`

- [ ] **Step 1: 定义模拟器接口**

```c
typedef void (*flow_snapshot_handler_t)(const flow_snapshot_t *snapshot, void *context);

void flow_simulator_start(flow_snapshot_handler_t handler, void *context);
void flow_simulator_submit(const flow_command_t *command);
```

- [ ] **Step 2: 实现确定性的 12 秒流程**

On command:

1. Emit `accepted`, `locked=true`, `eta_ms=12000`.
2. Emit `preparing` once per second from 11000 to 6000.
3. Emit `transitioning` once per second from 5000 to 1000.
4. Emit `completed`, `locked=false`, `eta_ms=0`, with `current=target`.

Reject a second command during the sequence with `phase=rejected`, `error=busy`, while preserving the active target and ETA.

- [ ] **Step 3: 增加构建开关**

Create `firmware/flow-wrist/components/flow_simulator/Kconfig`:

```text
menu "Flow Wrist"
    config FLOW_SIMULATOR
        bool "Enable local Hub simulator"
        default y
        help
            Drive the UI without an RK3588 Hub. Disable for BLE integration.
endmenu
```

`app_main` routes UI commands to the simulator when enabled and to BLE when disabled.

- [ ] **Step 4: Run the complete local demo**

Expected flow:

```text
BOOT → HOME → STYLE → BREAKING → 12s transition → BREAKING IS LIVE → HOME
```

Repeat with energy 05. During the transition, tapping the screen must show busy feedback and leave the active sequence unchanged.

- [ ] **Step 5: Commit**

```bash
git add firmware/flow-wrist/components/flow_simulator firmware/flow-wrist/main
git commit -m "feat: add Flow Wrist Hub simulator"
```

### Task 9: 实现 BLE Peripheral 和 GATT 服务

**Files:**
- Create: `firmware/flow-wrist/components/flow_ble/CMakeLists.txt`
- Create: `firmware/flow-wrist/components/flow_ble/include/flow_ble.h`
- Create: `firmware/flow-wrist/components/flow_ble/flow_ble.c`
- Create: `firmware/flow-wrist/docs/ble-test.md`
- Modify: `firmware/flow-wrist/main/app_main.c`

- [ ] **Step 1: 定义 BLE 接口**

```c
typedef void (*flow_ble_snapshot_handler_t)(const flow_snapshot_t *snapshot, void *context);

esp_err_t flow_ble_init(flow_ble_snapshot_handler_t handler, void *context);
esp_err_t flow_ble_send_command(const flow_command_t *command);
bool flow_ble_is_connected(void);
```

- [ ] **Step 2: 注册 UUID 和 Characteristics**

Use the exact UUIDs from the approved design:

```text
Service:   464C4F57-0001-4F57-8101-000000000001
Command:   464C4F57-0001-4F57-8101-000000000002  Indicate
Hub State: 464C4F57-0001-4F57-8101-000000000003  Read + Write response
Catalog:   464C4F57-0001-4F57-8101-000000000004  Read + Write response
```

Also register Battery Service `0x180F` and Device Information Service `0x180A`.

- [ ] **Step 3: 实现安全写入路径**

The Hub State write callback must:

1. Reject values over 512 bytes.
2. Copy all `os_mbuf` fragments into a contiguous local buffer.
3. Decode with `flow_protocol_decode_snapshot`.
4. Enqueue the decoded snapshot.
5. Return an ATT error for invalid CBOR or schema violations.

No LVGL call is allowed in the access callback.

- [ ] **Step 4: 实现 command indication**

Encode into a 192-byte stack buffer. Copy the encoded value into an `os_mbuf`, then call `ble_gatts_indicate_custom`. Allow only one outstanding command. Clear the outstanding flag on indication acknowledgement, disconnect, or a 2-second transport timeout.

- [ ] **Step 5: 广播、连接和配对**

Advertise `FLOW-WRIST-XXXX` plus the custom service UUID. Enable bonding and LE Secure Connections with Just Works for V0.1. On disconnect, restart advertising. Keep UI controls disabled until Catalog and the first Hub State have both arrived.

- [ ] **Step 6: 写 BLE 测试说明**

Create `firmware/flow-wrist/docs/ble-test.md` with:

```markdown
# Flow Wrist BLE test

1. Disable `CONFIG_FLOW_SIMULATOR`.
2. Build and flash the firmware.
3. Confirm advertising name `FLOW-WRIST-XXXX`.
4. Connect from a BLE central and subscribe to Command indications.
5. Write Catalog, then an idle Hub State.
6. Select energy 05 and verify one CBOR command indication.
7. Write preparing snapshots with decreasing `eta_ms`.
8. Write completed with `current=target`, `locked=false`, `eta_ms=0`.
9. Repeat one snapshot revision and verify the UI does not roll back.
10. Disconnect during transition and verify the countdown stops.
```

- [ ] **Step 7: Build both modes**

Run once with simulator enabled and once disabled:

```bash
idf.py build
idf.py menuconfig
idf.py fullclean
idf.py build
```

Expected: both configurations compile; BLE mode advertises after boot.

- [ ] **Step 8: Commit**

```bash
git add firmware/flow-wrist/components/flow_ble firmware/flow-wrist/docs firmware/flow-wrist/main
git commit -m "feat: add Flow Wrist BLE GATT service"
```

### Task 10: BOOT 唤醒、屏幕超时和电量

**Files:**
- Create: `firmware/flow-wrist/components/flow_power/CMakeLists.txt`
- Create: `firmware/flow-wrist/components/flow_power/include/flow_power.h`
- Create: `firmware/flow-wrist/components/flow_power/flow_power.c`
- Modify: `firmware/flow-wrist/main/app_main.c`

- [ ] **Step 1: 定义电源接口**

```c
typedef void (*flow_wake_handler_t)(void *context);

esp_err_t flow_power_init(flow_wake_handler_t handler, void *context);
void flow_power_note_activity(void);
void flow_power_set_transition_active(bool active);
uint8_t flow_power_battery_percent(void);
bool flow_power_is_charging(void);
```

- [ ] **Step 2: 实现 BOOT 短按去抖**

Configure GPIO0 as input with pull-up. Poll every 10 ms. A valid short press requires 30 ms stable low followed by high before 800 ms. Do not emit repeated wake events while held. The application never changes GPIO0 output mode.

- [ ] **Step 3: 实现亮度和熄屏规则**

Use BSP functions:

```c
bsp_display_brightness_set(70);  /* active */
bsp_display_brightness_set(35);  /* transition dim */
bsp_display_backlight_off();     /* screen off */
```

Rules:

- Home and carousel: off after 10 seconds without touch.
- Transition: remain on; dim after 5 seconds without touch.
- Complete: 70% for 2 seconds, then home.
- BOOT short press: 70% and home/active transition page based on state.

- [ ] **Step 4: 读取 AXP2101**

Reuse the official `01_AXP2101` register access pattern, but obtain the already initialized GPIO14/15 bus only through `bsp_i2c_get_handle()`. Never call `i2c_new_master_bus()` in `flow_power`: the FT3168 touch controller already shares that BSP bus. Add the AXP2101 device with `i2c_master_bus_add_device()`, then read battery voltage and charging state every 5 seconds. Convert voltage to a smoothed UI estimate with a fixed LiPo lookup table; apply an exponential average so charger insertion does not make the icon jump immediately.

Battery Service notifications are sent only when the displayed percentage changes by at least 1 point or charging state changes.

- [ ] **Step 5: 真机检查按键和屏幕策略**

Expected:

- BOOT short press wakes once.
- Holding BOOT does not repeatedly open HOME.
- Home turns off after 10 seconds.
- Transition remains visible and dims after 5 seconds.
- PWR long press behavior is unchanged.
- Battery icon changes gradually and charging state matches USB connection.

- [ ] **Step 6: Commit**

```bash
git add firmware/flow-wrist/components/flow_power firmware/flow-wrist/main
git commit -m "feat: add Flow Wrist wake and battery handling"
```

### Task 11: 完整验证和开发交接

**Files:**
- Create: `firmware/flow-wrist/README.md`
- Modify: `firmware/flow-wrist/docs/hardware-bringup.md`
- Modify: `firmware/flow-wrist/docs/ble-test.md`

- [ ] **Step 1: 运行静态和 host 测试**

Run:

```bash
cd firmware/flow-wrist
./tests/host/run.sh
idf.py fullclean
idf.py build
```

Expected: host tests pass; firmware builds without warnings promoted to errors.

- [ ] **Step 2: 跑本地模拟器验收**

Verify five energy values, four styles, busy rejection, 12-second transition and completion. Measure from BOOT press to command emission for ten attempts; median must be 5 seconds or less.

- [ ] **Step 3: 跑 BLE 协议验收**

Verify duplicate command IDs, stale revisions, new session IDs, malformed CBOR, disconnect/reconnect, missing business ACK and unknown style catalog behavior.

- [ ] **Step 4: 记录固件体积和内存**

Run:

```bash
idf.py size
idf.py size-components
```

Record app size, free internal RAM after boot and PSRAM allocation in `hardware-bringup.md`. The factory app must stay below the 8 MB partition.

- [ ] **Step 5: 写 README**

`README.md` must include toolchain activation, build, flash, monitor, simulator switch, BLE UUIDs, directory map and recovery flashing with BOOT.

- [ ] **Step 6: Final commit**

```bash
git add firmware/flow-wrist
git commit -m "docs: complete Flow Wrist V0.1 firmware handoff"
```

## 计划自检

- 设计规格中的唤醒、双入口、五档能量、四种风格、立即发送、执行锁、双唱片反馈、倒计时、离线与断线状态均有对应任务。
- Wrist 的 CBOR、UUID、幂等字段和版本校验在本计划内实现；RK3588 业务处理不混入该固件计划。
- 所有 UI 更新经过单一 LVGL 路径。BLE、电源和模拟器不直接操作页面。
- 没有离线队列或自动重发。完成页只接受 Hub `completed` 快照。
- 首版插画用 LVGL primitives 达到可运行的编辑插画效果，最终精修位图可以在固件闭环稳定后替换，不阻塞功能验收。
