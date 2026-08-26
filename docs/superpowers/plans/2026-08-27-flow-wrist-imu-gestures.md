# Flow Wrist IMU Gesture Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不触摸屏幕时，用 QMI8658 的一套高意图手势安全完成能量或风格预览与确认发送，同时避免跳舞动作误触。

**Architecture:** QMI8658 采样层只提供统一单位的时间戳、加速度和角速度；纯 C 手势引擎负责滤波、阈值和状态机；协调层负责与触控、BLE ready/locked 状态仲裁。任何普通单次甩动都不能直接发送，必须先完成抬腕静止、双向解锁和稳定确认。

**Tech Stack:** ESP-IDF 5.5.5、Waveshare QMI8658 component、FreeRTOS、C11、LVGL 9.5

---

### Task 1: 用合成轨迹锁定手势状态机

**Files:**
- Create: `firmware/flow-wrist/components/flow_gesture/include/flow_gesture_engine.h`
- Create: `firmware/flow-wrist/components/flow_gesture/flow_gesture_engine.c`
- Create: `firmware/flow-wrist/components/flow_gesture/CMakeLists.txt`
- Create: `firmware/flow-wrist/tests/host/test_gesture_engine.c`
- Modify: `firmware/flow-wrist/tests/host/run.sh`

- [ ] **Step 1: 写失败测试**

测试轨迹必须覆盖：普通跳舞 30 秒零发送；抬腕静止 500 ms 进入 awake；1.2 秒内左右双向 roll 解锁 5 秒窗口；上下 flick 选择 ENERGY/STYLE；左右 roll 只产生 PREVIEW -1/+1；稳定 800 ms 产生确认提示；稳定 1.1 秒产生 SEND；任意移动、反向 flick、触控、BLE 断开、locked 或超时都 CANCEL；发送后 350 ms 冷却。

- [ ] **Step 2: 验证失败**

Run: `cd firmware/flow-wrist && tests/host/run.sh`

Expected: 编译失败，提示 `flow_gesture_engine.h` 不存在。

- [ ] **Step 3: 定义纯 C 输入输出**

输入包含 `timestamp_ms`、`accel_g[3]`、`gyro_dps[3]`、`touch_active`、`ble_ready`、`hub_locked`；输出事件只允许 `NONE`、`WAKE`、`ARMED`、`MODE_ENERGY`、`MODE_STYLE`、`PREVIEW_PREV`、`PREVIEW_NEXT`、`CONFIRMING`、`SEND`、`CANCEL`。

- [ ] **Step 4: 实现滤波和阈值**

使用 5 样本移动平均；静止条件为 gyro 三轴绝对值均小于 12 dps 且加速度模长在 0.90–1.10 g；flick 峰值为 120–280 dps、持续 80–450 ms、主轴/次轴比至少 1.35；每次预览后 350 ms 内忽略下一次 roll。

- [ ] **Step 5: 运行测试并 Commit**

```bash
cd firmware/flow-wrist
tests/host/run.sh
git add components/flow_gesture tests/host
git commit -m "feat: add tested IMU gesture state machine"
```

Expected: 所有 host tests PASS，普通跳舞轨迹 SEND 次数为 0。

### Task 2: 接入 QMI8658 实机采样

**Files:**
- Modify: `firmware/flow-wrist/main/idf_component.yml`
- Create: `firmware/flow-wrist/components/flow_imu/include/flow_imu.h`
- Create: `firmware/flow-wrist/components/flow_imu/flow_imu.c`
- Create: `firmware/flow-wrist/components/flow_imu/CMakeLists.txt`
- Modify: `firmware/flow-wrist/main/CMakeLists.txt`

- [ ] **Step 1: 添加官方依赖**

在 component manifest 中添加 `waveshare/qmi8658: "*"`，复用 BSP `bsp_i2c_get_handle()` 和 `QMI8658_ADDRESS_HIGH`，不创建第二条 I2C 总线。

- [ ] **Step 2: 实现采样任务**

QMI8658 配置 accel ±8g、gyro ±512 dps、125 Hz；8 ms 周期读取并转换为 g/dps，写入长度 8 的 overwrite queue。任务优先级低于 BLE host、高于纯 UI 动画。

- [ ] **Step 3: 实现非致命降级**

初始化失败时记录一次错误、返回 `FLOW_IMU_UNAVAILABLE`，不重启、不阻塞触控、BLE 或 LVGL；UI 设置中显示 `IMU OFFLINE`。

- [ ] **Step 4: 双配置构建并 Commit**

```bash
cd firmware/flow-wrist
idf.py -B build-sim build
idf.py -B build-ble -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.ble.defaults" build
git add main components/flow_imu
git commit -m "feat: sample the wrist QMI8658 IMU"
```

Expected: 两个构建均成功。

### Task 3: 实现触控优先的动作协调器

**Files:**
- Create: `firmware/flow-wrist/components/flow_core/include/flow_input_coordinator.h`
- Create: `firmware/flow-wrist/components/flow_core/flow_input_coordinator.c`
- Create: `firmware/flow-wrist/tests/host/test_input_coordinator.c`
- Modify: `firmware/flow-wrist/components/flow_core/CMakeLists.txt`
- Modify: `firmware/flow-wrist/tests/host/run.sh`

- [ ] **Step 1: 写失败测试**

断言 touch_active 立即取消 IMU session；BLE 非 ready、Hub locked、sending 或 transition 中禁止 arm/send；preview 只能在范围内改变一档；SEND 复用现有 `flow_core_request_change()` 并分配单调命令 id。

- [ ] **Step 2: 验证失败**

Run: `cd firmware/flow-wrist && tests/host/run.sh`

Expected: 编译失败，提示 `flow_input_coordinator.h` 不存在。

- [ ] **Step 3: 实现协调器**

协调器持有临时 mode/value，不直接操作 LVGL 或 NimBLE；输出统一 action queue，由 app_main 同一条路径更新 UI 并发送 CBOR，因此触控和 IMU 不会产生两套业务状态。

- [ ] **Step 4: 运行测试并 Commit**

```bash
cd firmware/flow-wrist
tests/host/run.sh
git add components/flow_core tests/host
git commit -m "feat: arbitrate touch and IMU wrist input"
```

Expected: 所有 host tests PASS。

### Task 4: 增加最小手势反馈 UI

**Files:**
- Create: `firmware/flow-wrist/components/flow_ui/flow_ui_gesture.c`
- Modify: `firmware/flow-wrist/components/flow_ui/include/flow_ui.h`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui.c`
- Modify: `firmware/flow-wrist/components/flow_ui/CMakeLists.txt`
- Modify: `firmware/flow-wrist/main/app_main.c`

- [ ] **Step 1: 实现覆盖层**

抬腕显示小型 `GESTURE READY`；解锁后显示 5 秒环；mode 选择后复用能量/风格轮播；预览只移动一格；确认阶段用 300 ms 进度描边；SEND 后立即进入现有 transition 页面。

- [ ] **Step 2: 实现取消反馈**

取消只显示 450 ms 的 `CANCELLED` 并回到原页面；触控取消不弹提示，直接把控制权交给触控；反馈期间不使用振动，因为首版硬件方案未确认马达。

- [ ] **Step 3: 集成采样与 action queue**

app_main 每次收到 IMU sample 先注入实时 BLE/locked/touch 状态，再把手势事件交给协调器；所有 LVGL 调用继续在 BSP display lock 内执行。

- [ ] **Step 4: 构建并 Commit**

```bash
cd firmware/flow-wrist
idf.py -B build-ble -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.ble.defaults" build
git add components/flow_ui main/app_main.c
git commit -m "feat: add no-touch gesture control feedback"
```

Expected: build 成功。

### Task 5: 实机校准与最终验收

**Files:**
- Create: `firmware/flow-wrist/docs/imu-gesture-test.md`

- [ ] **Step 1: 烧录并记录静止噪声**

在桌面静止、正常佩戴静止、走路和舞动四种情况下各采集 30 秒 gyro/accel 摘要；文档记录每轴峰值、95 分位值和误触事件数，不保存完整个人运动数据。

- [ ] **Step 2: 只用测试结果调整阈值**

若普通舞动出现 SEND，优先提高 arm 双向动作的主轴比和确认静止时间；若目标手势漏检，先调整 flick 持续范围，不降低“必须先 arm 再 send”的安全门槛。

- [ ] **Step 3: 无触控端到端验收**

连续完成能量 +1、能量 -1、风格 next、风格 prev 各 10 次；发送成功率至少 90%，普通舞动 10 分钟误发送为 0，触控在任意阶段都能抢占。

- [ ] **Step 4: 最终回归**

Run: `cd firmware/flow-wrist && tests/host/run.sh && idf.py -B build-ble -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.ble.defaults" build`

Expected: host tests 和 BLE 构建全部成功。

- [ ] **Step 5: 记录并 Commit**

```bash
git add firmware/flow-wrist/docs/imu-gesture-test.md
git commit -m "test: document Flow Wrist IMU gesture calibration"
```
