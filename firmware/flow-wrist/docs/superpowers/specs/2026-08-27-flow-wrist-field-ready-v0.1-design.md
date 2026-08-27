# Flow Wrist V0.1 现场可测版本总体设计

版本：1.0  
日期：2026-08-27  
状态：设计已批准，等待书面规格复核  
目标阶段：EVT / 小范围真实舞池测试

## 1. 这轮要交付什么

本轮把 Flow Wrist 从“ESP32 功能原型”推进到“可以带去真实舞池做受控测试”的版本。完成标准不是界面完整，而是手环、RK3588 和音乐引擎之间的整条控制链能够长期稳定运行。

用户闭环固定为：

```text
用户在 3–5 秒内完成能量或风格选择
        ↓
手环只发送一次命令
        ↓
RK3588 在 500 ms 内返回业务确认
        ↓
音乐引擎在 10–20 秒内完成选曲和切换
        ↓
手环持续显示目标风格、能量、BPM 和剩余时间
        ↓
完成、失败、断线或重启后回到可信状态
```

本轮包括：

- ESP32-S3 手环正式现场构建；
- RK3588 上独立运行的 `hub-gateway`；
- BlueZ 安全配对、单设备绑定和自动重连；
- Gateway 与音乐引擎之间的 Unix Domain Socket 协议；
- 触控、功耗、佩戴、故障恢复和长时间稳定性测试；
- 可验证、可回滚的 Alpha 发布包。

本轮不包括：

- BPM、调性、EQ、Pitch 或 Crossfader 手动控制；
- 多个手环共同控制；
- 戒指功能实现；
- BLE OTA 或 Wi-Fi OTA；
- 正式现场构建默认开启无触控手势；
- 深度睡眠；
- 定制 PCB；
- 手机 App；
- BLE 协议 v2。

## 2. 已确定的产品规则

| 项目 | V0.1 约定 |
|---|---|
| 正式输入方式 | 触摸屏 |
| 能量 | 1–5 五档 |
| 风格 | `hiphop`、`breaking`、`funk`、`locking` |
| 发送方式 | 点击选项立即发送，不增加二次确认 |
| 重复操作 | Hub `locked` 时禁止第二条命令 |
| 离线操作 | 可浏览，不发送、不缓存、不在重连后补发 |
| 手势 | 保留代码，正式现场构建默认关闭 |
| 主控数量 | 一个 Hub 只允许一个主控手环 |
| 固件升级 | USB 烧录，不做 OTA |
| 续航目标 | 连续使用至少 4 小时 |
| 现场前门槛 | 桌面 2 小时 + 佩戴舞动 30 分钟 |
| 日志 | Hub 保存 7 天结构化事件日志 |

## 3. 仓库和代码所有权

`harbeat-wear` 是 Wear 设备代码的唯一事实来源。完成仓库整理后，不再从 `harbeat-client` 导出 Wrist 子目录作为长期工作方式。

目标结构：

```text
harbeat-wear/
├── wrist/
│   └── flow-wrist/
│       ├── components/
│       ├── main/
│       ├── tests/
│       ├── tools/
│       └── docs/
├── hub-gateway/
│   ├── src/flow_wear_gateway/
│   ├── tests/
│   ├── packaging/
│   └── pyproject.toml
├── contracts/
│   ├── ble-v1.md
│   ├── engine-ipc-v1.md
│   └── golden-vectors/
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── releases/
│   └── test-plans/
├── ring/
│   └── README.md
├── tools/
└── .github/workflows/
```

目录责任：

- `wrist/flow-wrist` 只放 ESP32 固件、板级工具和对应测试；
- `hub-gateway` 只处理设备、BLE、协议、状态和本机 IPC；
- `contracts` 保存跨进程和跨设备协议，任何一端不能私自复制后修改；
- `ring` 本轮只记录未来边界，不创建空实现；
- 正式音乐引擎不迁入本仓库，由 Engine IPC 接入。

Git 约定：

- `main` 始终可构建；
- 功能分支使用 `codex/` 前缀；
- 禁止强制推送 `main`；
- 提交只包含一个可解释的行为变化；
- 生成文件、构建目录、Bond、密钥、设备日志和本机配置不得提交；
- Wrist 与 Gateway 独立打版本标签，例如 `wrist-v0.1.0-alpha.1`、`gateway-v0.1.0-alpha.1`。

## 4. 系统架构和责任边界

```text
ESP32-S3 Wrist
  LVGL / Touch / Power
  Wrist State Machine
  CBOR v1
  NimBLE Peripheral
          │
          │ BLE 5 LE
          │ Secure Connections + Bond
          ▼
RK3588 hub-gateway
  BlueZ D-Bus Client
  Provisioning / Allowlist
  BLE Protocol Adapter
  Command Deduplication
  Snapshot Authority
  Structured Logging
          │
          │ AF_UNIX + SOCK_STREAM
          │ NDJSON / Engine IPC v1
          ▼
Music Engine
  Track Selection
  Transition Planning
  Playback / Mixing
  Progress Events
```

责任固定如下：

- Wrist 负责表达意图和显示反馈，不负责选曲；
- Gateway 负责主控设备、连接、协议、命令生命周期和 BLE Snapshot；
- Music Engine 负责候选曲目、混音计划和真实播放状态；
- BLE 回调不得直接执行选曲或音频任务；
- Engine 卡顿不得阻塞 BlueZ 事件循环；
- Wrist 断线不得中断 Engine 正在执行的音乐切换；
- Gateway 不根据本地猜测修改 `current`，只能使用 Engine 报告的真实状态。

## 5. Hub Gateway 技术选择

Gateway 使用 Python 3.12 和 asyncio。BlueZ 连接层通过系统 D-Bus 调用标准 `org.bluez.Adapter1`、`Device1`、`Agent1` 和远程 GATT 接口。CBOR 使用 `cbor2`，本机 IPC 使用标准库 Unix Socket，服务由 systemd 管理。

选择 D-Bus 而不是自动化 `bluetoothctl` 的原因：

- 配对、扫描、连接和 GATT 操作都有可检查的返回值；
- 可以明确区分超时、认证失败、服务缺失和断线；
- systemd 服务不依赖交互式终端；
- 后续加入 Ring 时仍可复用同一设备管理层。

官方接口依据：

- BlueZ Adapter API：<https://bluez.readthedocs.io/en/latest/adapter-api/>
- BlueZ Device API：<https://bluez.readthedocs.io/en/latest/device-api/>
- BlueZ Agent API：<https://bluez.readthedocs.io/en/latest/agent-api/>
- BlueZ GATT API：<https://bluez.readthedocs.io/en/latest/gatt-api/>

## 6. 单主控手环和配对流程

一个 Hub 在 V0.1 只接受一个主控 Wrist。

首次部署：

1. 管理员运行 `flow-wearctl pair`；
2. Gateway 开启 120 秒配对窗口；
3. Adapter 只扫描 Flow Service UUID；
4. 对符合条件的设备按 RSSI 排序；
5. 选择信号最强的 `FLOW-WRIST-XXXX`；
6. 使用 LE Secure Connections、Just Works 和 Bonding；
7. 保存设备 Identity Address 与逻辑 Device ID；
8. 关闭 Pairable；
9. 后续只自动连接该设备。

其他设备可以出现在扫描结果里，但 Gateway 不订阅它们的 Command，也不写 Catalog 或 Snapshot。

更换手环必须显式执行：

```text
flow-wearctl unpair --device FLOW-WRIST-XXXX
flow-wearctl pair
```

`unpair` 同时删除 Gateway Allowlist 和 BlueZ Bond。删除前需要在终端二次确认目标 Device ID。

Just Works 不提供 MITM 保护。V0.1 用短配对窗口、物理距离、单设备 Allowlist 和配对后关闭 Pairable 降低风险。正式产品再评估数字确认、NFC 辅助配对或工厂预配置。

## 7. BLE v1 冻结项

BLE v1 的权威文件仍是 `contracts/ble-v1.md`。以下内容在 V0.1 期间冻结：

- Wrist 是 Peripheral / GATT Server；
- Gateway 是 Central / GATT Client；
- Service UUID：`464C4F57-0001-4F57-8101-000000000001`；
- Command UUID：`464C4F57-0001-4F57-8101-000000000002`；
- Hub State UUID：`464C4F57-0001-4F57-8101-000000000003`；
- Catalog UUID：`464C4F57-0001-4F57-8101-000000000004`；
- Command 使用 Indication；
- Catalog 和 Snapshot 使用加密 Write With Response；
- 所有自定义消息使用 CBOR map，`v = 1`；
- Command 最大 192 B，Catalog 和 Snapshot 最大 512 B；
- 必须支持 GATT Long Write，不把 MTU 247 当作前提；
- `session_id` 是 16 位十六进制字符串；
- 同一 Session 的 `revision` 严格递增；
- Gateway 按 `session_id + command.id` 去重；
- `ack_id` 是业务确认，Indication 确认只代表字节送达；
- `locked = true` 时禁止第二条命令；
- Catalog、首次 Snapshot 和 Command 订阅均完成后才能进入 READY；
- 能量固定 1–5；
- Style ID 固定为 `hiphop`、`breaking`、`funk`、`locking`。

任何一项需要改变时，新建 BLE v2。不得在仍声明 `v = 1` 时静默修改含义。

## 8. Gateway 连接状态机

主状态：

```text
STARTING
→ ADAPTER_READY
→ SCANNING
→ CONNECTING
→ PAIRING
→ DISCOVERING
→ SUBSCRIBING
→ SYNCING_CATALOG
→ SYNCING_STATE
→ READY
```

故障状态：

```text
DISCONNECTED
PAIRING_FAILED
PROTOCOL_ERROR
ENGINE_OFFLINE
RECOVERING
```

READY 判定：

```text
bond_valid
&& allowlisted_device
&& encrypted_link
&& command_indication_subscribed
&& catalog_written
&& initial_snapshot_written
&& engine_state_known
```

自动重连：

- 退避时间为 1、2、4、8、15 秒；
- 最大间隔 15 秒；
- 每次加入 ±20% 抖动；
- 已 Bond 的设备不重新 Pair；
- 单次 D-Bus 或 GATT 操作超时 5 秒；
- GATT 操作失败后断开并重走完整初始化；
- 不允许在只写完 Catalog 或只订阅 Command 的半同步状态下开放控制。

## 9. Engine IPC v1

Gateway 与正式音乐引擎通过 Unix Domain Socket 连接：

```text
/run/flow-wear/engine.sock
```

传输约定：

- `AF_UNIX`；
- `SOCK_STREAM`；
- UTF-8 NDJSON，一行一个 JSON 对象；
- 单条消息最大 16 KiB；
- 每行必须以 `\n` 结束；
- Socket 权限 `0660`；
- Owner 为 Music Engine 运行用户；
- Group 为 `flow-wear`；
- 不监听 TCP；
- 不允许使用相同 JSON 结构通过网络暴露服务。

连接方向：

- Music Engine 创建并监听 Socket；
- Gateway 主动连接；
- Engine 重启时 Gateway 进入 `ENGINE_OFFLINE` 并自动重连；
- Gateway 重启后先发送 `get_state`，再允许 Wrist 进入 READY。

握手：

```json
{"v":1,"kind":"hello","client":"hub-gateway","capabilities":["set_energy","set_style","transition_progress"]}
```

Engine 返回：

```json
{"v":1,"kind":"hello_ok","server":"music-engine","capabilities":["set_energy","set_style","transition_progress"]}
```

查询状态：

```json
{"v":1,"kind":"get_state","request_id":"gw-01J..."}
```

方向命令：

```json
{"v":1,"kind":"set_direction","request_id":"gw-01J...","wrist_command_id":42,"op":"set_energy","value":5,"received_at_ms":1787812345678}
```

接受：

```json
{"v":1,"kind":"accepted","request_id":"gw-01J...","target":{"energy":5,"style":"hiphop","bpm":102},"eta_ms":14000}
```

进度：

```json
{"v":1,"kind":"progress","request_id":"gw-01J...","phase":"transitioning","eta_ms":7000}
```

完成：

```json
{"v":1,"kind":"completed","request_id":"gw-01J...","current":{"energy":5,"style":"hiphop","bpm":102}}
```

拒绝：

```json
{"v":1,"kind":"rejected","request_id":"gw-01J...","error":"no_candidate"}
```

协议规则：

- Gateway 生成全局唯一的 `request_id`；
- Engine 必须回传原 `request_id`；
- Gateway 收到 Wrist Command 后，等待 Engine 的 `accepted` 或 `rejected`；
- Engine 响应预算为 400 ms，给 BLE Snapshot 留出约 100 ms；
- Gateway 不做乐观 accepted；
- Engine 没有确认时，Gateway 不向 Wrist 声称任务已接受；
- 未知 `kind`、未知版本、超长消息、缺字段或非法 UTF-8 均断开 IPC 并记录 `protocol_error`；
- `eta_ms` 在同一个任务中不得增加；
- Gateway 和 Engine 都必须按 `request_id` 去重。

Engine IPC v1 一旦用于 Alpha 发布，其字段含义冻结。破坏兼容性的修改使用 `v = 2`。

## 10. Command 和 Snapshot 责任

Gateway 是 BLE Snapshot 的唯一生成者。

命令路径：

1. 接收 Wrist Command Indication；
2. 解码 CBOR；
3. 校验版本、类型、主控设备、能量或风格值；
4. 按 `session_id + command.id` 去重；
5. 检查 Gateway 是否 READY、当前是否 locked；
6. 生成 Engine `request_id`；
7. 通过 IPC 发送 `set_direction`；
8. Engine 接受后生成 `accepted` Snapshot；
9. Progress 映射到 `preparing` 或 `transitioning`；
10. Completed 时先更新 `current`，再解除 `locked`。

重复 Wrist Command：

- 不再次调用 Engine；
- 如果原任务仍存在，重发当前 Snapshot；
- 如果原任务已经完成，返回包含最终 `current` 的最新 Snapshot；
- 日志记录 `duplicate_command`，不记为系统错误。

Engine 不可用：

- Gateway 不进入 READY；
- 已在 READY 时 Engine 断线，立即把控制入口切为不可发送；
- 未接受的 Wrist Command 返回 `rejected + engine_error`；
- 已接受并执行中的任务等待 Engine 重连后的 `get_state`；
- 不自动重新执行音乐命令。

## 11. 持久化和重启恢复

Gateway 状态文件：

```text
/var/lib/flow-wear/gateway/state.json
```

保存内容：

- Allowlist Device ID；
- Wrist Identity Address；
- 最后一次完成的 `current`；
- BLE 协议版本；
- Engine IPC 版本；
- Gateway 版本；
- 最近一次成功同步时间。

不保存：

- 待发送 Command；
- 未被 Engine 接受的请求；
- 用于重连后自动执行的选择；
- BlueZ Bond 密钥副本。

写文件使用同目录临时文件、`fsync` 和原子替换。BlueZ Bond 由 `/var/lib/bluetooth` 管理，Gateway 不复制密钥。

Gateway 重启：

- 生成新的 16 位 `session_id`；
- `revision` 从 1 开始；
- 连接 Engine 并调用 `get_state`；
- 连接已绑定 Wrist；
- 重新订阅 Command、写 Catalog 和首次 Snapshot；
- 不重放重启前的 Command。

Engine 重启：

- Gateway 保持 Wrist Bond；
- 标记 `ENGINE_OFFLINE`；
- Engine 恢复后重新握手和 `get_state`；
- 只有获得真实 `current` 或真实进行中任务后才恢复 READY。

## 12. Wrist 正式构建

正式输入：

- Touch 是 V0.1 唯一默认启用的控制输入；
- ENERGY 和 STYLE 操作应在 3–5 秒内完成；
- 左右滑动一次只改变一个选项；
- 点击非当前选项立即发送；
- 点击当前项目显示 already live，不发送；
- Hub `locked` 时不发送；
- 离线轮播可浏览，但不产生 Command。

手势：

- 保留现有代码和 host tests；
- 正式现场 `sdkconfig` 默认关闭；
- 单独提供 `sdkconfig.gesture-calibration.defaults`；
- 佩戴校准通过前，手势构建不得用于正式音乐控制。

屏幕：

- 暖纸白、低像素人物、黑色粗线和当前颜色体系保持不变；
- 普通页面无操作 10 秒熄屏；
- Transition 页面不熄灭，5 秒后降到 18%；
- 唤醒亮度为 70%；
- 动画以位移和透明度为主，目标 120–180 ms；
- 不增加全屏逐帧动画。

按键：

- BOOT 短按只作为活动/唤醒输入；
- BOOT 仍保留下载模式用途；
- PWR 不作为应用功能键；
- RST 不作为应用交互；
- 不使用会中断 BLE 的深度睡眠。

板级限制以微雪官方说明为准：GPIO14/15 是触摸、PMIC、IMU、RTC 和音频共用 I2C；GPIO0 同时连接 BOOT 和启动配置；PWR 长按约 6 秒会触发硬件关机。后续开发不得另建第二条 I2C master bus，也不得固定占用 GPIO0。官方资料：<https://docs.waveshare.net/ESP32-S3-Touch-AMOLED-2.06/>

## 13. 性能预算

| 指标 | Alpha 门槛 | 测量位置 |
|---|---:|---|
| Touch 到第一帧视觉反馈 | p95 ≤ 100 ms | Wrist 日志 + 高帧率录像 |
| 普通页面有效帧率 | ≥ 30 FPS | LVGL 统计 |
| 轮播吸附动画 | 120–180 ms | LVGL animation config |
| 已 Bond 设备从发现到 READY | p95 ≤ 10 秒 | Gateway 日志 |
| Wrist Command 到 Gateway 接收 | p95 ≤ 250 ms | 双端单调时钟事件 |
| Command 到 accepted Snapshot | p99 ≤ 500 ms | Gateway 日志 |
| 自动重连恢复 READY | p95 ≤ 15 秒 | Gateway 日志 |
| 用户完成一次触控操作 | ≤ 5 秒 | 现场录像 |
| accepted 到 completed | 10–20 秒 | Gateway + Engine 日志 |
| Wrist 内部空闲堆 | ≥ 64 KiB | ESP heap API |
| 最大内部连续内存块 | ≥ 32 KiB | ESP heap API |
| 空闲 PSRAM | ≥ 4 MiB | ESP heap API |
| 2 小时运行期间内存下降 | ≤ 5%，且无持续下降 | 周期采样 |

如果当前硬件基线达不到内存阈值，必须先记录真实空闲堆并解释占用，再调整阈值。不能通过关闭加密、错误处理或必要日志过验收。

## 14. 电源和续航

目标是使用现场准备采用的实际电池连续运行至少 4 小时。

测试流程：

1. 记录电池型号、标称容量和批次；
2. 充满后静置 10 分钟；
3. Wrist 与 Gateway 保持连接；
4. 每 2 分钟执行一次亮屏浏览；
5. 每 10 分钟发送一次能量或风格命令；
6. 每次 Transition 持续 12 秒；
7. 其余时间按正式策略熄屏；
8. 每分钟记录电量百分比、连接状态和重启计数；
9. 运行至 4 小时或设备正常关机。

通过条件：

- 连续运行至少 4 小时；
- 无 ESP32 重启；
- 无无法自动恢复的 BLE 失联；
- 电量百分比不反向跳变超过 5 个百分点；
- 显示电量与实际关机点误差不超过 10 个百分点；
- 表壳、电池和充电区域无异常发热或膨胀。

未通过时的优化顺序：

1. 降低 AMOLED 点亮时间；
2. 调整点亮亮度；
3. 正式构建关闭 IMU 高频采样；
4. 降低非执行状态的状态刷新频率；
5. 最后才评估保持 BLE 的轻睡眠。

本轮不引入深度睡眠。

## 15. 日志和诊断

Gateway 将结构化 JSONL 事件交给 journald，并额外保留 7 天轮转日志：

```text
/var/log/flow-wear/gateway.jsonl
```

记录字段：

- UTC 时间和单调时钟；
- Gateway 版本；
- Wrist Device ID；
- Connection State；
- RSSI；
- Wrist Command ID；
- `op` 和 `value`；
- Engine Request ID；
- ACK 延迟；
- Phase 和 ETA；
- Revision；
- 重连次数；
- Error Code。

不记录：

- 用户姓名或现场人员信息；
- 音频内容；
- 完整曲库；
- Bond 或密钥；
- 长期原始 BLE 抓包。

管理 CLI：

```text
flow-wearctl status
flow-wearctl devices
flow-wearctl logs --last 10m
flow-wearctl pair
flow-wearctl unpair
flow-wearctl doctor
```

`doctor` 检查：

- BlueZ 服务；
- Bluetooth Adapter Powered 状态；
- Pairable 和 Discovering 状态；
- Allowlist 与 Bond 是否一致；
- Engine Socket 和握手；
- Gateway / Wrist / 协议版本；
- GATT 服务与三个 Characteristic；
- Wrist READY 状态；
- 最近一次 Command 和错误。

## 16. 错误映射

| 来源 | 内部错误 | Wrist error | UI 行为 |
|---|---|---|---|
| Gateway locked | `busy` | `busy` | 保持当前 Transition 和倒计时 |
| Engine 无候选 | `no_candidate` | `no_candidate` | 显示无合适曲目并返回主页 |
| Engine 执行失败 | `engine_error` | `engine_error` | 显示执行失败，可重试 |
| IPC 不兼容 | `protocol_error` | `protocol_error` | 禁止控制，要求检查版本 |
| BLE v 不兼容 | `unsupported_version` | `unsupported` | 显示 UPDATE REQUIRED |
| 非主控 Wrist | `unauthorized_device` | 不写业务状态 | 不开放 READY |
| GATT 写入失败 | `transport_error` | 无 | 断线并重新同步 |

错误状态不能伪装为 completed，也不能仅靠 UI 本地计时解除 locked。

## 17. 测试层级

### 17.1 每次提交

- Wrist C host tests；
- CBOR golden vectors；
- 人物资源完整性测试；
- ESP-IDF simulator build；
- ESP-IDF BLE build；
- Gateway pytest；
- Engine IPC contract tests；
- Gateway 状态机和去重测试；
- Ruff；
- Python 类型检查；
- 文档协议示例解析测试。

### 17.2 RK3588 真机

必须覆盖：

- 首次 Pair；
- Bond 后自动连接；
- Wrist 重启；
- Gateway 重启；
- RK3588 重启；
- Engine 重启；
- Transition 中 Wrist 断线；
- 重复 Command；
- 旧 Revision；
- 无效 CBOR；
- `busy`；
- `no_candidate`；
- `engine_error`；
- MTU 247；
- MTU 小于 247；
- GATT Long Write；
- 2.4 GHz 干扰环境；
- 断电后 Bond 与 Allowlist 恢复。

### 17.3 两小时桌面稳定性

测试脚本每 60 秒安排一个完整 12 秒 Transition，每 15 分钟断开一次 Wrist，每 30 分钟重启一次 Gateway。Engine 在测试中保持运行。

通过条件：

- ESP32 零重启；
- Gateway 零未处理异常退出；
- Engine 零重复执行；
- 每个 accepted Command 最终有 completed 或明确 rejected；
- 所有计划内断线均在 15 秒目标内恢复；
- 内存无持续下降；
- 日志可以按 Command ID 还原完整时序。

### 17.4 佩戴舞动 30 分钟

- 使用正式构建，手势关闭；
- 进行步行、摆臂、跳舞、出汗和衣物摩擦；
- 每 5 分钟执行一次指定触控任务；
- 不允许出现非触摸 Command；
- 指定触控任务成功率 100%；
- 屏幕均能正常唤醒；
- 表带、接口和外壳无松动；
- 无异常发热。

### 17.5 四小时续航

按第 14 节执行。续航测试不能与高频串口日志连接同时进行，避免 USB 供电影响结果。

## 18. CI 和版本固定

CI 固定：

- ESP-IDF 5.5.5；
- LVGL 9.5.0；
- Waveshare BSP 2.0.0；
- Python 3.12；
- 锁定 Gateway Python 依赖；
- 所有构建记录依赖锁文件 Hash。

升级这些依赖时单独提交，先跑完整 HIL 验收，不与功能修改混在同一提交中。

## 19. 发布包和回滚

现场发布包：

```text
release/
├── wrist/
│   ├── bootloader.bin
│   ├── partition-table.bin
│   ├── flow_wrist.bin
│   ├── flash_args
│   ├── sdkconfig
│   ├── manifest.json
│   └── SHA256SUMS
├── gateway/
│   ├── wheel/
│   ├── requirements.lock
│   ├── systemd/
│   ├── install.sh
│   ├── uninstall.sh
│   ├── manifest.json
│   └── SHA256SUMS
└── docs/
    ├── RELEASE-NOTES.md
    ├── FIELD-CHECKLIST.md
    └── ROLLBACK.md
```

Manifest 至少包含：

- Git Commit；
- Wrist 版本；
- Gateway 版本；
- BLE 协议版本；
- Engine IPC 版本；
- ESP-IDF、BSP 和 LVGL 版本；
- 构建时间；
- 固件 SHA-256；
- Gateway Wheel SHA-256；
- 通过的测试报告 ID。

立即回滚条件：

- 重复音乐命令；
- `locked` 失效；
- 重连无法恢复；
- 现场连续两次崩溃；
- 电池异常发热、膨胀或供电不稳；
- ENERGY / STYLE 入口或返回键失效；
- 版本不一致导致状态不可解释。

现场只允许回滚到上一份完整通过验收的发布包，不允许临时修改代码后直接烧录。

## 20. 阶段门

### Gate 0：契约和仓库

- 目标目录结构完成；
- BLE v1 与 Engine IPC v1 入库；
- Golden Vectors 可由 Wrist 和 Gateway 共同读取；
- CI 基线通过。

### Gate 1：Gateway Vertical Slice

- BlueZ 配对和单设备 Allowlist；
- Command Indication；
- Catalog 和 Snapshot；
- Fake Engine Unix Socket；
- 500 ms ACK 门槛通过。

### Gate 2：正式 Engine

- 正式 Engine 支持 hello、get_state、set_direction、progress、completed、rejected；
- 能量和风格各完成一次真实切换；
- Engine 和 Gateway 任意一方重启后可恢复。

### Gate 3：Wrist Hardening

- 正式构建关闭手势；
- Touch、返回、离线和 Transition UI 验收；
- 内存和性能预算通过；
- USB 回滚包可用。

### Gate 4：稳定性与续航

- 两小时桌面测试通过；
- 30 分钟佩戴测试通过；
- 四小时续航通过；
- 所有失败都有可查询日志。

### Gate 5：Alpha 现场发布

- 发布包和 SHA-256 完整；
- Field Checklist 完成；
- Rollback 演练完成；
- 小范围舞池测试被明确批准。

前一 Gate 未通过，不进入下一 Gate，也不通过增加新功能绕开问题。

## 21. 实施顺序

1. 把 `harbeat-wear` 整理为 Wrist、Gateway、Contracts 和 Docs 四个边界；
2. 冻结 BLE v1、Engine IPC v1 和 Golden Vectors；
3. 建立 Gateway 包、systemd 服务、配置和 `flow-wearctl`；
4. 完成 BlueZ Adapter、Agent、Provisioning 和 Allowlist；
5. 完成 GATT 初始化与自动重连；
6. 完成 Command 去重、Snapshot Authority 和 Fake Engine；
7. 在 RK3588 跑通真实加密 BLE 纵向闭环；
8. 接入正式音乐引擎；
9. 修正 Wrist 真机暴露的触控、内存和错误恢复问题；
10. 执行两小时桌面测试；
11. 执行 30 分钟佩戴测试；
12. 执行四小时续航测试；
13. 生成 Alpha 发布包并演练回滚；
14. 进入小范围现场测试。

## 22. 设计决策摘要

| 决策 | 选择 | 原因 |
|---|---|---|
| 开发路线 | 契约先行的纵向闭环 | 优先消除 BlueZ 与正式 Engine 的最大未知项 |
| Hub 形态 | 独立 `hub-gateway` | 隔离 BLE 和音频故障，未来可接 Ring |
| Engine 接口 | Unix Domain Socket + NDJSON | 低延迟、本机权限清晰、跨语言 |
| 主控策略 | 单主控 Wrist | 避免权限冲突和并发命令 |
| 更新 | USB + 可回滚发布包 | V0.1 不引入 OTA 风险 |
| 手势 | 保留、正式构建关闭 | 先保证现场没有误触命令 |
| 续航 | 至少 4 小时 | 覆盖一场测试活动 |
| 稳定性 | 桌面 2 小时 + 佩戴 30 分钟 | 在开发速度和现场风险之间取可执行门槛 |
| 日志 | 结构化保存 7 天 | 能还原现场问题，不收集个人信息 |

这套决策的排序是：先保证命令唯一和状态可信，再保证断线恢复和现场可诊断，最后优化视觉细节和高级输入。V0.1 不用功能数量证明完成度，而用一条可以重复验证的真实音乐控制闭环证明完成度。
