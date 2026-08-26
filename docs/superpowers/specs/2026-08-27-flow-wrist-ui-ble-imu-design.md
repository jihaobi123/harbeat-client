# Flow Wrist V0.2 UI、BLE 与 IMU 首版设计规格

日期：2026-08-27

硬件：Waveshare ESP32-S3-Touch-AMOLED-2.06

Hub：RK3588 Linux 设备

软件：ESP-IDF 5.5.5、LVGL 9.5、NimBLE、QMI8658

状态：用户已授权按本规格直接实施第一版

## 1. 目标

本轮在已经可运行的 Flow Wrist V0.1 固件上完成四件事：

1. 用四个可辨认的低像素舞者姿态替换抽象 LVGL 色块人物。
2. 让能量和风格轮播在拖动过程中实时跟随手指，并用轻量动效提供即时反馈。
3. 固定 Wrist 与 RK3588 的 BLE v1 契约，补齐连接、配对、同步和重连 UI，并提供可运行的 Hub 联调样例。
4. 集成 QMI8658，提供第一版不依赖触摸屏的能量和风格控制路径。

上一版规格 `2026-08-26-flow-wrist-v0.1-ui-ble-design.md` 中的业务原则继续有效；本规格覆盖其“IMU 不在首版范围”和静态人物实现，并细化连接状态与性能预算。

## 2. 范围与非目标

### 2.1 本轮包含

- `hiphop`、`breaking`、`funk`、`locking` 四张同角色、不同姿态的 Chunky Sticker 人物资源。
- 固定外框、内部内容实时拖动的轮播。
- 140 ms 吸附、进入/发送动效、5 档能量速度线反馈。
- BLE 连接状态 UI：等待 Hub、建立安全链路、同步目录、同步状态、就绪、重连、版本不匹配。
- 可交给 RK3588 团队的 UUID、CBOR schema、状态推进、错误码和 Python 参考实现。
- QMI8658 驱动、采样、校准、手势识别、手势 UI 和统一动作队列。
- Mac 主机测试、模拟器构建、真实 BLE 构建和 ESP32-S3 实机验收。

### 2.2 本轮不包含

- 从 Wrist 修改 BPM 或调性；两者仍只读。
- 机器学习手势分类器、用户自训练模型或云端识别。
- 在屏幕关闭时仅靠任意舞动直接发送音乐命令。
- IMU 自动识别左右手佩戴；首版使用固定坐标映射和上板阈值。
- OTA、Wi-Fi、麦克风、扬声器、RTC 和 MicroSD 产品功能。

## 3. 硬件事实与资源预算

开发板实测资源为 32 MB Flash、8 MB Octal PSRAM、ESP32-S3 240 MHz、410×502 AMOLED。显示、FT3168 触摸、AXP2101 和 QMI8658 共享板级资源；QMI8658 使用 BSP 已创建的 I²C master bus。

Waveshare 官方仓库确认该板带 QMI8658，并提供 ESP-IDF `04_Immersive_block` 示例。官方示例通过 `bsp_i2c_get_handle()` 获取总线，以 `QMI8658_ADDRESS_HIGH` 初始化，证明无需另建 I²C 总线。

资源预算：

| 项目 | 预算 |
|---|---:|
| 四张人物位图 | 150–220 KB Flash |
| IMU 组件代码与状态 | 小于 40 KB Flash、8 KB RAM |
| 人物显示尺寸 | 约 112×112 px |
| 拖动刷新 | 25–30 FPS，事件驱动 |
| 触摸到首帧反馈 | 小于 50 ms |
| 吸附动画 | 140 ms |
| 空闲人物动画 | 0 FPS |

固件必须保留至少 70% 的 8 MB app partition 空间，避免首版资源失控。

## 4. 人物素材与视觉语言

### 4.1 角色设定

四张图使用同一位中性街舞角色。保持相同的脸型、帽子、头身比和主服装，只改变动作、局部配色和舞种识别细节：

- `hiphop`：bounce 重心、放松肩线、宽站姿。
- `breaking`：低重心 footwork 或 freeze，支撑手和伸展腿清晰。
- `funk`：groove 与身体曲线更明显，动作开放。
- `locking`：明确的 stop/point 姿态，肘腕转折清楚。

人物采用粗黑边、块状低像素、少色平涂。必须能辨认头颈、弯肘、膝盖、手掌和鞋底，避免用直方块拼接成抽象符号。

### 4.2 资源处理

生图输出保存为项目源素材 PNG，保留透明背景。处理步骤固定为：

```text
生成高分辨率透明 PNG
→ 裁切统一画布和重心
→ 最近邻缩放到约 112×112
→ 限制到 Flow 色板附近的少量颜色
→ 转换为 LVGL RGB565+A8 C array
→ const 存入 Flash
```

不在运行时解码 PNG。位图保持原尺寸绘制，不做连续缩放和旋转。

### 4.3 页面层级

- 暖纸白 `#FFF8ED` 为全局底色。
- 深墨 `#11110F` 用于结构线和主要文字。
- 能量黄、风格蓝、操作粉、在线绿沿用 V0.1 色板。
- 首页人物约占卡片右侧 40%，不遮挡当前值和操作文案。
- 选择页显示相邻项目露边、页码点和 `DRAG TO PREVIEW / TAP TO SEND`。

## 5. 跟手轮播和轻量动效

### 5.1 对象结构

轮播不在每次滑动时 `lv_obj_clean()` 后重建。页面创建时预建：

```text
固定 poster viewport
├── 前一项 content pane
├── 当前项 content pane
└── 后一项 content pane
```

每个 pane 只包含人物、标题和少量装饰。外框、背景和操作提示保持静止。拖动只改变三个 pane 的 X 坐标，viewport 负责裁切。

### 5.2 手势行为

- `PRESSED` 记录起点并立即进入拖动状态。
- `PRESSING` 每 33 ms 或累计位移超过 4 px 更新 pane 位置。
- 水平距离超过 35 px 且大于垂直距离时，松手切换项目。
- 未超过阈值时，松手回弹到当前项目。
- 选中目标后轻点当前 pane 立即发送。
- 能量在 1 和 5 处有 8 px 阻尼位移，不越界。
- 风格首尾循环。

### 5.3 动效预算

- 页面进入：人物 160 ms 从 6 px 下方进入。
- 吸附：140 ms ease-out。
- 能量反馈：2–4 px 阶梯弹跳，速度线数量和频率随 1–5 档增加。
- 发送：人物向前 4 px，粉色印章反馈 180 ms。
- 所有动效在操作结束 500 ms 后停止。

禁止大面积透明残影、模糊、连续缩放以及全屏动画。

## 6. BLE 连接 UI

连接状态不是一个笼统的 `connected` 布尔值。领域层使用：

```text
offline
advertising
securing
syncing_catalog
syncing_state
ready
version_mismatch
```

### 6.1 页面表现

| 状态 | 主标题 | 次要信息 | 控制入口 |
|---|---|---|---|
| advertising | `FINDING THE HUB.` | `OPEN FLOW HUB TO CONNECT` | 禁用 |
| securing | `SECURING THE LINK.` | `PAIRING WITH RK3588` | 禁用 |
| syncing_catalog | `SYNCING THE ROOM.` | `LOADING ENERGY + STYLES` | 禁用 |
| syncing_state | `READING THE FLOOR.` | `GETTING CURRENT TRACK` | 禁用 |
| ready | 首页 | 绿色 `● HUB` | 启用 |
| offline after ready | `HUB IS OFFLINE.` | 保留最后状态，显示重连 | 禁用 |
| version_mismatch | `WRIST UPDATE REQUIRED.` | 显示协议版本 | 禁用 |

连接页只使用小范围的三点步进动画，4 FPS，避免持续大面积刷新。重连时不删除最后的 `current/target`，但不得离线排队或发送。

### 6.2 BLE 状态来源

NimBLE 层在以下事件报告领域连接状态：

- 开始广播：`advertising`
- GAP connect：`securing`
- encryption change 成功：等待订阅和目录
- Command Indication 已订阅：继续同步
- Catalog 校验通过：`syncing_state`
- 首个 Snapshot 校验通过：`ready`
- disconnect：`advertising`，并标记是否属于重连

UI 不直接读取 NimBLE handle。

## 7. BLE v1 契约

### 7.1 角色和服务

```text
Wrist：BLE Peripheral / GATT Server
RK3588：BLE Central / GATT Client / 业务状态权威
```

自定义服务：

```text
464C4F57-0001-4F57-8101-000000000001
```

| Characteristic | UUID 末尾 | 属性 | 方向 |
|---|---:|---|---|
| Command | `0002` | Indicate | Wrist → Hub |
| Hub State | `0003` | Read、Write with response、加密 | Hub → Wrist |
| Catalog | `0004` | Read、Write with response、加密 | Hub → Wrist |

另提供 Battery Service `0x180F` 和 Device Information Service `0x180A`。

### 7.2 初始化顺序

```text
扫描 FLOW-WRIST-XXXX
→ 连接
→ LE Secure Connections / Just Works / Bonding
→ 订阅 Command Indication
→ 写入完整 Catalog
→ 写入完整 Snapshot
→ Wrist ready
```

建议 MTU 247；Catalog 和 Snapshot 必须支持 GATT Long Write，不能依赖 MTU 协商成功。

### 7.3 Command

链路实际使用 CBOR；JSON 只用于说明：

```json
{"v":1,"kind":"command","id":42,"op":"set_energy","value":5}
```

```json
{"v":1,"kind":"command","id":43,"op":"set_style","value":"breaking"}
```

`id` 是非零 uint32。Hub 必须按 `session_id + id` 幂等，重复命令不能重复触发音乐任务。

### 7.4 Snapshot

```json
{
  "v": 1,
  "kind": "snapshot",
  "session_id": "8f3a19d04b7c221e",
  "revision": 107,
  "ack_id": 43,
  "phase": "preparing",
  "locked": true,
  "eta_ms": 14000,
  "current": {"energy": 3, "style": "hiphop", "bpm": 96},
  "target": {"energy": 5, "style": "breaking", "bpm": 108},
  "error": null
}
```

允许 phase：`idle`、`accepted`、`preparing`、`transitioning`、`completed`、`rejected`、`error`。

业务规则：

- Indication confirm 只代表链路送达。
- Hub 接受命令后必须发布相同 `ack_id` 的 Snapshot。
- `accepted/preparing/transitioning` 必须 `locked=true`。
- `completed` 必须 `locked=false`、`eta_ms=0`，且 `current` 已更新。
- 单个 `session_id` 内 `revision` 严格递增。
- Hub 重启必须更换 16 位十六进制 `session_id`。
- Wrist 丢弃相同会话内旧或重复 revision。

### 7.5 Catalog 和错误

Catalog 固定 1–5 档能量，以及 `hiphop/breaking/funk/locking` 四个稳定 ID。错误码：

- `busy`
- `invalid_energy`
- `unknown_style`
- `version_mismatch`
- `transport_error`
- `internal_error`

BPM 首版只在 Snapshot 中回传展示，不提供 Wrist 修改命令。

## 8. IMU 无触控控制

### 8.1 安全原则

用户在舞池会持续运动。普通运动不能直接成为音乐控制命令。IMU 控制采用“唤醒/武装 → 预览 → 明确确认”的短时状态机，并复用触摸操作的动作队列、Hub 锁定和错误处理。

手势仅在以下条件启用控制：

- BLE 状态为 `ready`
- Hub `locked=false`
- 当前没有 `sending/transition`

否则 IMU 只允许点亮屏幕和查看状态。

### 8.2 第一版状态机

```text
gesture_idle
  ↓ 抬腕并稳定 500 ms
screen_wake
  ↓ 1.2 s 内完成一次明确的双向 roll
gesture_armed（5 s 超时）
  ↓ 上/下 flick
选择 ENERGY / STYLE
  ↓ 左/右 roll
预览上一项 / 下一项
  ↓ 稳定保持 800 ms
屏幕显示确认环
  ↓ 继续稳定到 1.1 s
发送当前预览
```

任何大幅移动、向下 flick、BLE 状态变化或 5 秒超时都会取消并回到首页，不发送。

该设计允许完整无触控操作，同时要求用户先进入短时手势窗口，降低舞动误触发。

### 8.3 识别器

QMI8658 配置建议：

- accelerometer：±8 g、125 Hz
- gyroscope：±512 dps、125 Hz
- 任务采样周期：8 ms；识别窗口按时间戳运行
- 启动时在静止条件下收集 1.5 秒 gyro bias

处理流程：

```text
raw accel/gyro
→ 单极低通估计 gravity
→ linear acceleration
→ gyro bias correction
→ 候选事件窗口
→ dominant-axis 与方向分类
→ cooldown / state gate
→ flow_ui_action_t
```

首版阈值从以下范围开始上板调节：

- flick peak：120–280 dps
- flick duration：80–450 ms
- dominant-axis ratio：至少 1.35
- still gyro：每轴小于 12 dps
- still acceleration magnitude：1 g ±0.10 g
- gesture cooldown：350 ms

识别逻辑放在纯 C `flow_gesture_engine`，不依赖 I²C、FreeRTOS 或 LVGL，以便使用录制样本做主机测试。`flow_imu` 只负责 QMI8658 和采样任务。

### 8.4 手势 UI

进入手势窗口后，顶部显示 `GESTURE CONTROL`，中央复用能量/风格选择页，额外显示：

- 当前识别模式 ENERGY / STYLE
- 最近识别方向
- 5 秒窗口剩余进度
- 稳定确认环
- `MOVE TO CANCEL` 提示

触摸和 IMU 可同时存在；触摸发生时立即取消手势窗口，避免两个输入源争用。

## 9. 模块边界

```text
main/app coordinator
├── 单一 action queue
├── Hub snapshot queue
├── link-state queue
└── input-source arbitration

flow_ui
├── connection status
├── home
├── carousel viewport + three panes
├── gesture overlay
└── transition / complete / error

flow_art
├── LVGL image descriptors
└── style-id → image mapping

flow_ble
├── GAP/security lifecycle
├── GATT service
└── link-state callback

flow_protocol
├── CBOR validation/encoding/decoding
└── v1 schema

flow_imu
├── QMI8658 driver adapter
├── calibration
└── 125 Hz sampling task

flow_gesture_engine
├── filtering
├── temporal state machine
└── gesture events
```

BLE callback、IMU task 和 LVGL task 之间只传值对象，不共享 LVGL 指针。

## 10. 失败处理

- QMI8658 初始化失败：记录错误，触摸 UI 和 BLE 继续工作，隐藏手势入口。
- I²C 单次读取失败：丢弃样本；连续 20 次失败后暂停 IMU 1 秒并重试。
- 触摸与 IMU 同时输入：触摸优先，取消 gesture armed 状态。
- BLE 断开：取消手势窗口、禁用发送、进入重连 UI。
- Hub locked：任何触摸或 IMU 新命令都只显示当前任务。
- 图片资源异常：构建期失败，不提供运行时占位下载路径。
- Link indication 超时：不自动重发，进入同步/错误路径。

## 11. 测试与验收

### 11.1 主机自动测试

- 能量边界、风格循环、点击与拖动区分。
- gesture engine 的左/右、上/下、稳定确认、超时、cooldown 和噪声拒绝。
- 触摸优先和 Hub locked gate。
- Command CBOR、Snapshot decode、Catalog validation。
- stale revision、新 session、busy 和错误状态。

### 11.2 构建

- simulator build 成功。
- BLE build 成功。
- 固件 app partition 剩余大于 70%。
- 人物资源总大小不超过 250 KB。

### 11.3 UI 实机

- 连续左右快速拖动 50 次无崩溃、白屏或明显误发送。
- pane 在拖动中跟随，松手 140 ms 左右吸附。
- 四个姿态在实际尺寸下可辨认。
- 两次完整能量切换和两次风格切换通过。
- 熄屏、BOOT 唤醒和完成页返回正常。

### 11.4 BLE 实机

Mac/Python Hub mock 必须验证：

- 扫描、连接、配对/加密。
- 订阅 Command Indication。
- 写 Catalog 和首次 Snapshot 后进入 ready。
- 收到 `set_energy` 和 `set_style`。
- 依次写 accepted、preparing、transitioning、completed。
- disconnect 后重新广播，重连后重新同步。
- 非法 Catalog/Snapshot 被拒绝。

### 11.5 IMU 实机

- 读取 WHO_AM_I 和连续 accel/gyro 数据。
- 静止校准成功。
- 10 次目标方向手势中至少 8 次识别。
- 30 秒普通持握/轻微移动不进入 armed。
- 未 armed、Hub locked 和 BLE offline 时不能发送。
- 完成一次完全无触控的能量切换和一次风格切换。

## 12. 交付物

- 4 张源 PNG 和 4 个 LVGL C array。
- 跟手轮播与事件动效固件。
- BLE 连接 UI。
- `docs/ble-protocol-v1.md`。
- `tools/flow_hub_mock.py` 和依赖说明。
- QMI8658/gesture 组件与测试样本。
- simulator 和 BLE 两套可复现构建命令。
- 实机烧录版本与串口验收记录。

## 13. 参考资料

- [Waveshare 产品文档](https://docs.waveshare.net/ESP32-S3-Touch-AMOLED-2.06)
- [Waveshare 官方示例仓库](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-2.06)
- [官方 ESP-IDF QMI8658 示例](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-2.06/tree/main/examples/esp-idf/04_Immersive_block)
- [QMI8658C Datasheet](https://files.waveshare.com/wiki/ESP32-S3-Touch-LCD-1.28/QMI8658C.pdf)
