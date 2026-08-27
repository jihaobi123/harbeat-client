# Flow Wrist Offline Home and Safe Area Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让真实 BLE 固件在找不到 Hub 时进入主页并浏览能量/风格选项，但离线选择只提示连接 Hub、绝不发送或缓存命令；同时扩大、内缩返回键。

**Architecture:** 状态层允许无 Snapshot 时在 HOME、ENERGY、STYLE 之间导航，但 `flow_state_begin_command` 仍要求真实 Snapshot。UI 移除覆盖主页的透明拦截层，离线轮播以默认预览数据初始化；点击选项只显示 `CONNECT HUB TO SEND`，不会产生 UI command。应用层在非 READY 状态只放行打开页面和返回动作。返回键位置由可测试的纯 C 布局函数提供，LVGL 只消费布局结果。

**Tech Stack:** ESP-IDF 5.5.5、LVGL 9.5.0、C11、FreeRTOS、现有 Mac host tests

> Task 1–5 已由 `777f237` 与 `ad3fe59` 完成。Task 6 是用户确认后的离线浏览修正，取代 Task 3 中“离线遮罩阻断卡片”和“无人物占位”的旧约束。

---

### Task 1: 离线进入主页的状态规则

**Files:**
- Modify: `firmware/flow-wrist/components/flow_core/include/flow_core.h`
- Modify: `firmware/flow-wrist/components/flow_core/flow_core.c`
- Modify: `firmware/flow-wrist/tests/host/test_flow_core.c`

- [ ] **Step 1: 写失败测试**

在 `test_flow_core.c` 增加：

```c
static void test_connecting_can_view_read_only_home(void)
{
    flow_app_state_t state;
    flow_state_init(&state);
    assert(flow_state_view_home(&state));
    assert(state.screen == FLOW_SCREEN_HOME);
    assert(!state.has_snapshot);
    assert(!flow_state_open_control(&state, FLOW_SCREEN_ENERGY));

    state.screen = FLOW_SCREEN_TRANSITION;
    state.snapshot.locked = true;
    assert(!flow_state_view_home(&state));
    assert(state.screen == FLOW_SCREEN_TRANSITION);
}
```

并在 `main()` 调用该测试。

- [ ] **Step 2: 确认测试因缺少 API 而失败**

Run:

```bash
cd "/Users/jihaobi/Documents/New project/firmware/flow-wrist"
./tests/host/run.sh
```

Expected: 编译失败，提示 `flow_state_view_home` 未声明。

- [ ] **Step 3: 添加最小状态实现**

在 `flow_core.h` 声明：

```c
bool flow_state_view_home(flow_app_state_t *state);
```

在 `flow_core.c` 实现：

```c
bool flow_state_view_home(flow_app_state_t *state)
{
    if (state == NULL || state->snapshot.locked ||
        state->screen == FLOW_SCREEN_SENDING ||
        state->screen == FLOW_SCREEN_TRANSITION) {
        return false;
    }
    state->screen = FLOW_SCREEN_HOME;
    return true;
}
```

- [ ] **Step 4: 确认测试通过**

Run: `./tests/host/run.sh`

Expected: `flow_core tests passed`，其他主机测试也通过。

### Task 2: 返回键圆角安全区模型

**Files:**
- Modify: `firmware/flow-wrist/components/flow_ui/include/flow_carousel_model.h`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_carousel_model.c`
- Modify: `firmware/flow-wrist/tests/host/test_carousel_model.c`

- [ ] **Step 1: 写失败测试**

在 `test_carousel_model.c` 增加：

```c
static void test_back_button_uses_round_screen_safe_area(void)
{
    const flow_back_button_layout_t layout = flow_carousel_back_button_layout();
    assert(layout.x == 12);
    assert(layout.y == 8);
    assert(layout.width == 64);
    assert(layout.height == 52);
    assert(layout.title_y == 16);
}
```

并在 `main()` 调用该测试。

- [ ] **Step 2: 确认测试因缺少类型和函数而失败**

Run: `./tests/host/run.sh`

Expected: 编译失败，提示 `flow_back_button_layout_t` 或 `flow_carousel_back_button_layout` 未定义。

- [ ] **Step 3: 添加布局类型和实现**

在 `flow_carousel_model.h` 增加：

```c
typedef struct {
    int16_t x;
    int16_t y;
    int16_t width;
    int16_t height;
    int16_t title_y;
} flow_back_button_layout_t;

flow_back_button_layout_t flow_carousel_back_button_layout(void);
```

在 `flow_carousel_model.c` 增加：

```c
flow_back_button_layout_t flow_carousel_back_button_layout(void)
{
    const flow_back_button_layout_t layout = {
        .x = 12,
        .y = 8,
        .width = 64,
        .height = 52,
        .title_y = 16,
    };
    return layout;
}
```

- [ ] **Step 4: 确认布局测试通过**

Run: `./tests/host/run.sh`

Expected: `carousel model tests passed`。

### Task 3: 连接页与离线主页 UI

**Files:**
- Modify: `firmware/flow-wrist/components/flow_ui/include/flow_ui.h`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui_connection.c`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui_home.c`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui.c`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui_carousel.c`

- [ ] **Step 1: 增加明确的 UI action**

在 `flow_ui_action_type_t` 中加入：

```c
FLOW_UI_ACTION_VIEW_HOME,
```

- [ ] **Step 2: 在连接页加入宽按钮**

在 `flow_ui_connection.c` 添加 click callback，发送：

```c
const flow_ui_action_t action = {.type = FLOW_UI_ACTION_VIEW_HOME};
flow_ui_emit(&action);
```

按钮文案为 `VIEW HOME`，尺寸 `250 × 56`，保持暖纸白、黑描边和 16 px 圆角。

- [ ] **Step 3: 让主页支持无 Snapshot 占位**

`flow_ui_home_create` 根据 `state->has_snapshot` 生成文本：

```c
const char *style = state->has_snapshot ? state->snapshot.current.style : "NO DATA";
```

无 Snapshot 时能量显示 `-- / 05`，底部显示 `-- BPM / OFFLINE`，不创建会暗示现场状态的人物能量图。

- [ ] **Step 4: 修正非 READY 页面选择**

在 `flow_ui_render` 中使用以下规则：

```c
if (state->link_state != FLOW_LINK_READY) {
    if (state->screen == FLOW_SCREEN_HOME) {
        flow_ui_home_create(s_root, state);
        flow_ui_offline_overlay(s_root);
    } else {
        flow_ui_connection_create(s_root, state);
    }
    return;
}
```

- [ ] **Step 5: 应用圆角安全区布局**

在 `flow_ui_carousel_create` 中取得：

```c
const flow_back_button_layout_t back_layout = flow_carousel_back_button_layout();
```

用该结果设置按钮位置、尺寸和标题 `y` 偏移。返回事件仍只发送一次 `FLOW_UI_ACTION_BACK`。

- [ ] **Step 6: 构建验证 LVGL 代码**

Run:

```bash
source /Users/jihaobi/.espressif/tools/activate_idf_v5.5.5.sh
idf.py -B build-sim build
```

Expected: `Project build complete`。

### Task 4: 应用层允许离线导航但继续阻止控制

**Files:**
- Modify: `firmware/flow-wrist/main/app_main.c`
- Modify: `firmware/flow-wrist/tests/host/test_input_coordinator.c`

- [ ] **Step 1: 保留现有离线控制测试**

确认 `test_input_coordinator.c` 的非 READY 场景继续断言 `FLOW_INPUT_CANCEL`，避免手势在离线主页发送。

- [ ] **Step 2: 在 READY 守卫之前处理 VIEW_HOME**

将 `process_ui_action` 的入口改为：

```c
if (action == NULL) {
    return;
}
if (action->type == FLOW_UI_ACTION_VIEW_HOME) {
    if (flow_state_view_home(&s_app_state)) {
        publish_state();
    }
    return;
}
if (s_app_state.link_state != FLOW_LINK_READY) {
    ESP_LOGW(TAG, "Ignored control while Hub link is not ready");
    return;
}
```

原有能量、风格和发送逻辑保持不变。

- [ ] **Step 3: 运行完整主机测试**

Run:

```bash
./tests/host/run.sh
python3 tests/host/test_hub_mock.py
python3 tests/host/test_dancer_assets.py
```

Expected: 全部通过。

### Task 5: 文档、双构建与真机烧录

**Files:**
- Modify: `firmware/flow-wrist/docs/AI-DEVELOPMENT-HANDOFF.md`

- [ ] **Step 1: 更新离线操作说明**

记录 `VIEW HOME`、首次启动占位数据、后台继续连接和离线禁止发送。同步记录返回键已扩大并进入圆角安全区。

- [ ] **Step 2: 运行格式检查和双构建**

Run:

```bash
git diff --check
source /Users/jihaobi/.espressif/tools/activate_idf_v5.5.5.sh
idf.py -B build-sim build
idf.py -B build-ble build
```

Expected: 无格式错误，两次构建都出现 `Project build complete`。

- [ ] **Step 3: 烧录真实 BLE 版**

Run:

```bash
test -c /dev/cu.usbmodem1101
idf.py -B build-ble -p /dev/cu.usbmodem1101 flash
idf.py -B build-ble -p /dev/cu.usbmodem1101 monitor
```

Expected: 烧录 hash 校验通过；启动日志包含 Display、BLE advertising 和 QMI8658 sampling。

- [ ] **Step 4: 实机验收**

不启动 Hub。点击 `VIEW HOME`，确认进入离线主页；点击离线卡片不发送；再检查能量页和风格页的返回键触摸范围。没有 RK3588 时，只把离线和按钮验收为已完成，安全链路仍保持待联调。

- [ ] **Step 5: 提交本次修改**

```bash
git add firmware/flow-wrist/components/flow_core/include/flow_core.h \
  firmware/flow-wrist/components/flow_core/flow_core.c \
  firmware/flow-wrist/components/flow_ui/include/flow_carousel_model.h \
  firmware/flow-wrist/components/flow_ui/flow_carousel_model.c \
  firmware/flow-wrist/components/flow_ui/include/flow_ui.h \
  firmware/flow-wrist/components/flow_ui/flow_ui_connection.c \
  firmware/flow-wrist/components/flow_ui/flow_ui_home.c \
  firmware/flow-wrist/components/flow_ui/flow_ui.c \
  firmware/flow-wrist/components/flow_ui/flow_ui_carousel.c \
  firmware/flow-wrist/main/app_main.c \
  firmware/flow-wrist/tests/host/test_flow_core.c \
  firmware/flow-wrist/tests/host/test_carousel_model.c \
  firmware/flow-wrist/docs/AI-DEVELOPMENT-HANDOFF.md
git commit -m "fix: allow offline wrist home navigation"
```

### Task 6: 离线浏览能量与风格轮播

**Files:**
- Modify: `firmware/flow-wrist/components/flow_core/flow_core.c`
- Modify: `firmware/flow-wrist/tests/host/test_flow_core.c`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui.c`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui_carousel.c`
- Modify: `firmware/flow-wrist/main/app_main.c`
- Modify: `firmware/flow-wrist/docs/AI-DEVELOPMENT-HANDOFF.md`

- [ ] **Step 1: 写失败测试，锁定离线导航和禁止发送边界**

把现有离线主页测试扩展为：无 Snapshot 时可打开 ENERGY、返回 HOME、打开 STYLE；但调用 `flow_state_begin_command` 仍返回 `FLOW_COMMAND_BLOCKED`。

- [ ] **Step 2: 确认测试先失败**

Run: `cd firmware/flow-wrist && ./tests/host/run.sh`

Expected: `flow_state_open_control` 的离线断言失败。

- [ ] **Step 3: 最小修改状态层**

让 `flow_state_open_control` 和 `flow_state_return_home` 不再依赖 `has_snapshot`，继续阻止锁定态、发送态、过渡态和无效目标页面。不要放宽 `flow_state_begin_command`。

- [ ] **Step 4: 确认主机测试通过**

Run: `./tests/host/run.sh`

Expected: 所有 host tests 通过。

- [ ] **Step 5: 移除透明点击拦截层并渲染离线轮播**

在 `flow_ui_render` 中，非 READY 时允许 HOME、ENERGY、STYLE 使用各自真实 UI；其他页面仍显示连接页。离线轮播通过 `flow_state_home_music` 取得安全的默认预览值，避免直接读取空 Snapshot。

- [ ] **Step 6: 离线选择只给反馈，不产生 command**

给轮播上下文记录 `hub_ready`。离线点击当前或其他选项时统一显示 `CONNECT HUB TO SEND` 并直接返回，不调用 `flow_ui_emit`，不缓存选择，也不改变默认预览。左右滑动和返回键保持可用。

- [ ] **Step 7: 应用层只放行离线导航**

在 READY 守卫之前处理 `OPEN_ENERGY`、`OPEN_STYLE` 和 `BACK`；其余离线 action 保持忽略。这样即使 UI 将来误发 SET action，状态层与应用层仍有第二道阻断。

- [ ] **Step 8: 简单验证、双构建和烧录**

Run:

```bash
git diff --check
./tests/host/run.sh
source /Users/jihaobi/.espressif/tools/activate_idf_v5.5.5.sh
idf.py -B build-sim build
idf.py -B build-ble build
test -c /dev/cu.usbmodem1101
idf.py -B build-ble -p /dev/cu.usbmodem1101 flash
```

Expected: 主机测试和两个构建通过，烧录校验成功。

- [ ] **Step 9: 更新交接文档并提交**

记录离线浏览的操作方式、安全边界和联调预期。仅提交本任务涉及的明确文件。
