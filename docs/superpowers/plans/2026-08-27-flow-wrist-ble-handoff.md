# Flow Wrist BLE Connection and RK3588 Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让手环清楚显示 BLE 连接、加密、目录同步和现场状态同步进度，并交付 RK3588 可直接实现的协议文档与 Mac 端模拟器。

**Architecture:** `flow_ble` 输出强类型链路状态，`app_main` 通过队列交给 UI，不允许 NimBLE 回调直接操作 LVGL。协议继续使用固定 UUID 和 CBOR，命令由手环发出，Hub 以 catalog/state 写入并用 ack_id 闭环确认。

**Tech Stack:** ESP-IDF NimBLE、TinyCBOR、LVGL 9.5、Python Bleak、cbor2、BlueZ GATT

---

### Task 1: 将布尔连接回调升级为可测试的链路状态

**Files:**
- Modify: `firmware/flow-wrist/components/flow_ble/include/flow_ble.h`
- Modify: `firmware/flow-wrist/components/flow_ble/flow_ble.c`
- Create: `firmware/flow-wrist/tests/host/test_link_state.c`
- Modify: `firmware/flow-wrist/tests/host/run.sh`

- [ ] **Step 1: 写失败测试**

覆盖 `ADVERTISING → SECURING → SYNCING_CATALOG → SYNCING_STATE → READY`，以及 ready 后断开返回 advertising、协议版本不兼容进入 `VERSION_MISMATCH`。

- [ ] **Step 2: 验证失败**

Run: `cd firmware/flow-wrist && tests/host/run.sh`

Expected: 编译失败，提示 `flow_link_state_t` 不存在。

- [ ] **Step 3: 实现状态接口**

定义 `FLOW_LINK_ADVERTISING`、`FLOW_LINK_SECURING`、`FLOW_LINK_SYNCING_CATALOG`、`FLOW_LINK_SYNCING_STATE`、`FLOW_LINK_READY`、`FLOW_LINK_VERSION_MISMATCH`；回调携带状态和是否保留缓存，不再只传 bool。

- [ ] **Step 4: 运行测试并 Commit**

```bash
cd firmware/flow-wrist
tests/host/run.sh
git add components/flow_ble tests/host
git commit -m "feat: expose BLE synchronization states"
```

Expected: 所有 host tests PASS。

### Task 2: 实现连接与重连 UI

**Files:**
- Create: `firmware/flow-wrist/components/flow_ui/flow_ui_connection.c`
- Modify: `firmware/flow-wrist/components/flow_ui/include/flow_ui.h`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui.c`
- Modify: `firmware/flow-wrist/components/flow_ui/flow_ui_home.c`
- Modify: `firmware/flow-wrist/components/flow_ui/CMakeLists.txt`
- Modify: `firmware/flow-wrist/main/app_main.c`

- [ ] **Step 1: 建立状态映射**

UI 文案固定为：`FINDING THE HUB.`、`SECURING THE LINK.`、`SYNCING THE ROOM.`、`READING THE FLOOR.`；ready 时显示绿色 `● HUB`，版本不匹配时显示 `UPDATE REQUIRED.`。

- [ ] **Step 2: 实现非阻塞动效**

等待页只使用三个点的透明度循环和一条 900 ms 进度扫线；全部由 LVGL 动画驱动，不创建额外 UI task，不持续重绘全屏。

- [ ] **Step 3: 实现重连规则**

首次连接前显示全屏连接页；ready 后断开保留上次曲目、能量和风格，在首页覆盖离线提示并禁用发送；重新 ready 后自动恢复操作。

- [ ] **Step 4: 双配置构建并 Commit**

```bash
cd firmware/flow-wrist
idf.py -B build-sim build
idf.py -B build-ble -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.ble.defaults" build
git add components/flow_ui main/app_main.c
git commit -m "feat: add staged BLE connection UI"
```

Expected: 两个构建均成功。

### Task 3: 固化 RK3588 协议交付物

**Files:**
- Create: `firmware/flow-wrist/docs/ble-protocol-v1.md`
- Modify: `firmware/flow-wrist/docs/ble-test.md`
- Modify: `firmware/flow-wrist/README.md`

- [ ] **Step 1: 写协议文档**

文档必须列出 service/command/state/catalog UUID、特征权限与方向、Little Endian/CBOR 约定、`{v,kind,id,op,value}` 命令、catalog/state 完整字段、phase 枚举、错误码、配对流程、ack_id 去重、10–20 秒 ETA 更新、断线重连和版本不兼容行为，并附能量 4→5 与风格 hiphop→breaking 的十六进制 CBOR 示例。

- [ ] **Step 2: 写 Hub 侧顺序**

BlueZ Central 的固定顺序为：扫描 `FLOW-WRIST` → connect → pair/encrypt → subscribe Command indications → write Catalog → write initial State → wait READY → receive command → immediately indicate receipt through State → update phase/eta → final State。

- [ ] **Step 3: 文档校验并 Commit**

Run: `rg -n "0001|0002|0003|0004|ack_id|eta_ms|VERSION_MISMATCH" firmware/flow-wrist/docs/ble-protocol-v1.md`

Expected: 所有关键词均命中。

```bash
git add firmware/flow-wrist/docs firmware/flow-wrist/README.md
git commit -m "docs: hand off Flow Wrist BLE protocol v1"
```

### Task 4: 提供 Mac/RK3588 通用 Hub 模拟器

**Files:**
- Create: `firmware/flow-wrist/tools/flow_hub_mock.py`
- Create: `firmware/flow-wrist/tools/requirements-hub-mock.txt`
- Create: `firmware/flow-wrist/tests/host/test_hub_mock.py`

- [ ] **Step 1: 写失败测试**

测试构造 command CBOR，断言模拟器能去重 id、立即产生 ack、按 `accepted → preparing → switching → complete` 生成单调递减 eta_ms，并拒绝 v != 1。

- [ ] **Step 2: 验证失败**

Run: `python3 -m unittest firmware/flow-wrist/tests/host/test_hub_mock.py -v`

Expected: 因 `flow_hub_mock` 不存在而 FAIL。

- [ ] **Step 3: 实现模拟器**

Bleak 只负责扫描、连接、订阅和写特征；CBOR 状态机写成无 BLE 依赖的类，测试直接调用。CLI 支持 `--device FLOW-WRIST`、`--transition-seconds 12`、`--verbose`。

- [ ] **Step 4: 运行测试并 Commit**

```bash
python3 -m unittest firmware/flow-wrist/tests/host/test_hub_mock.py -v
git add firmware/flow-wrist/tools firmware/flow-wrist/tests/host/test_hub_mock.py
git commit -m "feat: add Flow Wrist Hub BLE simulator"
```

Expected: tests PASS。

### Task 5: 实机 BLE 验收

**Files:**
- Modify: `firmware/flow-wrist/docs/ble-test.md`

- [ ] **Step 1: 烧录 BLE 固件**

```bash
cd firmware/flow-wrist
idf.py -B build-ble -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.ble.defaults" -p /dev/cu.usbmodem1101 flash monitor
```

Expected: 启动日志显示 advertising，屏幕显示 `FINDING THE HUB.`。

- [ ] **Step 2: 完成端到端场景**

模拟器连接后验证四段连接文案依次出现；发送能量和风格命令；验证 transition 页面收到 phase、目标风格和剩余时间；切换完成后回首页。

- [ ] **Step 3: 验证断线恢复**

停止模拟器，确认手环保留缓存并禁用操作；重新启动后 10 秒内恢复 ready，命令 id 不重复执行。

- [ ] **Step 4: 记录结果并 Commit**

在 `ble-test.md` 记录日期、固件 commit、Mac 地址/系统版本、扫描/加密/同步/断线结果。

```bash
git add firmware/flow-wrist/docs/ble-test.md
git commit -m "test: record Flow Wrist BLE handoff verification"
```
