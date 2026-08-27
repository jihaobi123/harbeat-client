# Flow Wrist Field Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前可操作的 ESP32-S3 Wrist 原型加固为现场 Alpha：交互稳定、触控跟手、断连可恢复、手势默认关闭、内存有余量、日志可诊断，并能连续工作至少 4 小时。

**Architecture:** UI 只消费 `flow_core` 状态，不直接处理 BLE；BLE callback 只入队，应用任务更新状态后再渲染。正式与模拟器构建明确分离。所有计时使用单调时钟，所有 UI 修改都在 LVGL task/lock 内发生。

**Tech Stack:** ESP-IDF 5.5.5、FreeRTOS、LVGL 9.5.0、NimBLE、Waveshare BSP、Unity/host C tests

---

### Task 1: 固定正式构建配置与功能开关

**Files:**
- Create: `components/flow_core/Kconfig`
- Modify: `main/app_main.c`
- Modify: `main/CMakeLists.txt`
- Modify: `sdkconfig.defaults`
- Modify: `sdkconfig.ble.defaults`
- Create: `sdkconfig.sim.defaults`
- Test: `tests/host/test_build_profiles.py`

- [ ] **Step 1: 写构建配置测试**

断言 BLE profile：`FLOW_SIMULATOR_ENABLED=n`、`FLOW_GESTURE_ENABLED=n`、日志级别 INFO、蓝牙安全开启；SIM profile 只允许 `FLOW_SIMULATOR_ENABLED=y`，不得与真实 BLE 同时执行 Command transport。

- [ ] **Step 2: 增加 Kconfig**

```text
FLOW_GESTURE_ENABLED      default n
FLOW_DIAGNOSTICS_ENABLED  default y
FLOW_FIELD_BUILD          default y
```

`app_main.c` 用编译期分支决定是否创建 IMU queue、gesture queue/task 和 `flow_imu_start()`。正式关闭手势时完全不采样 IMU，不只是忽略事件。

- [ ] **Step 3: 验证两套 build**

```bash
idf.py -B build-sim -DSDKCONFIG_DEFAULTS='sdkconfig.defaults;sdkconfig.sim.defaults' build
idf.py -B build-ble -DSDKCONFIG_DEFAULTS='sdkconfig.defaults;sdkconfig.ble.defaults' build
python3 tests/host/test_build_profiles.py
```

### Task 2: Command 状态机故障与恢复

**Files:**
- Modify: `components/flow_core/include/flow_core.h`
- Modify: `components/flow_core/flow_core.c`
- Modify: `components/flow_ble/flow_link_state.c`
- Test: `tests/host/test_flow_core.c`
- Test: `tests/host/test_link_state.c`

- [ ] **Step 1: 写失败测试**

覆盖：未连接不能提交；连接但 Gateway not ready 不能提交；accepted 后锁定；progress 不解锁；completed/rejected/error 解锁；返回主页不取消已经发送的 Command；断连后显示错误并解锁；重复/旧 revision Snapshot 忽略；新 session 清空旧 ack 但保留当前音乐状态。

- [ ] **Step 2: 实现单一状态转换入口**

新增 `flow_core_apply_snapshot()` 和 `flow_core_on_link_change()`；UI 不直接写 `snapshot.locked`。错误文案映射固定为中文短句：

```text
busy -> 上一阶段还未切换完成
no_candidate -> 曲库里暂无合适音乐
engine_error -> Hub 音乐服务暂不可用
transport_error -> 与 Hub 的连接中断
unsupported/protocol_error -> 当前版本暂不支持
unauthorized_device -> 此手环未获授权
```

- [ ] **Step 3: 验证 host tests**

```bash
./tests/host/run.sh
```

### Task 3: 触控手势与二级页跟手性

**Files:**
- Modify: `components/flow_ui/flow_ui_carousel.c`
- Modify: `components/flow_ui/flow_ui_home.c`
- Modify: `components/flow_ui/flow_ui_connection.c`
- Modify: `components/flow_ui/flow_ui_gesture.c`
- Modify: `components/flow_core/flow_input_coordinator.c`
- Test: `tests/host/test_carousel_model.c`
- Test: `tests/host/test_input_coordinator.c`

- [ ] **Step 1: 写输入边界测试**

水平滑动门槛 28 px，水平位移必须大于垂直位移 1.25 倍；速度足够时一次最多跨 2 项，否则跨 1 项；按下期间卡片随指针位移，释放后 160 ms ease-out 吸附；点击门槛为移动小于 12 px；正在锁定时仍可返回主页但不能再发 Command。

- [ ] **Step 2: 放大返回热区**

视觉返回按钮移至距左/上安全边界至少 18 px；点击热区不小于 `64 x 56 px`，但不得覆盖标题或轮播。Finding Hub、Energy、Style、Sending、Transition、Error 页面都使用同一 helper。

- [ ] **Step 3: 限制动画成本**

只动画 `x/y/opacity/transform zoom`，不在每帧重建对象、解码 PNG 或改变大面积 shadow。动画同时最多 3 个，目标 30 FPS；人物插画在页面创建时一次绑定，切项只切换预生成 descriptor。

- [ ] **Step 4: 真机快速验证**

各完成 20 次左右滑、20 次进入/返回、10 次锁定期间返回。验收：无误触提交、无卡死、人物插画不丢失、返回热区在圆角区域内可轻松点中。

### Task 4: BLE 重连、配对和超时 UI

**Files:**
- Modify: `components/flow_ble/flow_ble.c`
- Modify: `components/flow_ble/flow_link_state.c`
- Modify: `components/flow_ui/flow_ui_connection.c`
- Modify: `main/app_main.c`
- Test: `tests/host/test_link_state.c`
- Test: `tests/host/test_hub_mock.py`

- [ ] **Step 1: 写故障场景测试**

覆盖 Gateway 未启动、启动后连接、5 秒 GATT 初始化超时、Hub 重启、Wrist 重启、Bond 存在但服务变化、未授权 Hub。Finding Hub 页面必须始终可返回主页，并显示 `重试`；不得以 modal 阻塞触控。

- [ ] **Step 2: 实现退避**

扫描/重连间隔固定 `1, 2, 4, 8, 15, 15...` 秒，成功收到有效 Snapshot 后归零。GATT 初始化失败主动断开再重试；不在 callback 中 sleep。

- [ ] **Step 3: Mock Hub 回归**

```bash
python3 tests/host/test_hub_mock.py --scenario all
```

### Task 5: 电量、灭屏和 4 小时策略

**Files:**
- Modify: `components/flow_power/flow_power.c`
- Modify: `components/flow_power/flow_power_policy.c`
- Modify: `components/flow_power/include/flow_power_policy.h`
- Modify: `main/app_main.c`
- Test: `tests/host/test_power_policy.c`

- [ ] **Step 1: 写策略测试**

正式策略冻结为：无操作 15 秒降低亮度、30 秒灭屏；Command accepted 到终态期间不自动灭屏；灭屏后首次触摸只唤醒不触发业务；BOOT 短按唤醒/回主页；RESET 只保留硬复位，不复用为业务按键。

- [ ] **Step 2: 电量采样与校准**

每 30 秒采样一次，5 点中值滤波；百分比只在变化至少 1% 时通知。用满电、约 50%、低电三点实测电压更新标定表；低于 15% 显示提示，低于 5% 禁止新 Command 并保留返回/状态查看。

- [ ] **Step 3: 关闭不需要的耗电源**

灭屏时背光/AMOLED panel 进入可恢复低功耗状态，LVGL tick 保持状态机最小运行；手势关闭时 IMU task 不存在；BLE 连接参数使用 30–50 ms interval、slave latency 4、supervision timeout 6 s，若 BSP/Hub 协商失败则记录实际参数。

- [ ] **Step 4: 验证唤醒一致性**

100 次灭屏/触摸唤醒中不得出现首次触摸误发 Command；10 次 BOOT 唤醒/回主页不得重启设备。

### Task 6: 轻量诊断与资源水位

**Files:**
- Create: `components/flow_core/include/flow_diagnostics.h`
- Create: `components/flow_core/flow_diagnostics.c`
- Modify: `components/flow_core/CMakeLists.txt`
- Modify: `main/app_main.c`
- Test: `tests/host/test_diagnostics.c`

- [ ] **Step 1: 写格式测试**

每条日志为单行，包含 `ts_ms,event,session_id,command_id,phase,error,free_heap,min_free_heap`；不包含 MAC、Bond key、歌曲名、用户标识或触摸轨迹。

- [ ] **Step 2: 实现 60 秒心跳与事件日志**

记录 boot reason、BLE state、Command queued、Snapshot phase、screen、heap、最大 UI render time。日志仅走 UART；Wrist 不保存 7 天日志，7 天留存由 Gateway journald 负责。

- [ ] **Step 3: 固定资源红线**

BLE field build 启动稳定 60 秒后：内部 free heap ≥80 KiB、largest block ≥32 KiB、PSRAM free ≥1 MiB；连续 100 次页面切换后 min-free 内部 heap 下降不得超过 8 KiB。低于红线 Gate 3 失败。

### Task 7: 真机烧录与 Gate 3

**Files:**
- Create: `docs/test-results/GATE-3-WRIST.md`
- Modify: `README.md`

- [ ] **Step 1: 全量小检查**

```bash
./tests/host/run.sh
python3 tests/host/test_hub_mock.py --scenario all
python3 tests/host/test_dancer_assets.py
idf.py -B build-ble build
```

- [ ] **Step 2: 识别串口并烧录**

```bash
ls /dev/cu.usbmodem* /dev/cu.usbserial* 2>/dev/null
idf.py -B build-ble -p /dev/cu.usbmodemXXXX flash monitor
```

必须将 `XXXX` 替换成实际唯一端口；存在多个候选时停止并人工确认，不能猜。监视 10 分钟，零 panic、watchdog、重启。

- [ ] **Step 3: 写 Gate 3 报告并提交**

报告包含 build SHA、flash 命令、版本字符串、资源水位、触控快速验证、电源策略验证。提交：

```bash
git add wrist/flow-wrist docs/test-results/GATE-3-WRIST.md
git commit -m "fix: harden wrist field interaction"
```
