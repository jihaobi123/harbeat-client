# Flow Ring V0.1：XIAO nRF54L15 Sense 手势音效戒指设计

- 日期：2026-08-28
- 状态：设计已逐段确认，书面规格等待最终审阅
- 目标读者：Windows 固件开发 AI、nRF Connect SDK 工程师、RK3588 工程师、Flutter 工程师、测试人员
- 当前开发板：Seeed Studio XIAO nRF54L15 Sense
- 固件栈：nRF Connect SDK 3.4.0、Zephyr、C
- 主开发系统：Windows 11 x64

## 1. 给 Windows AI 的执行摘要

你要开发的是舞者佩戴的手势音效戒指，不是手环的缩小版。

戒指只负责一件事：舞者用拇指有意识地触摸戒指表面，然后完成一个手势，戒指在本地识别动作并通过 BLE 把事件发给 RK3588。RK3588 根据 App 演出前选好的音效库，把动作映射成一次性音效并立即播放。能量、舞蹈风格和切歌仍由 Flow Wrist 手环负责。

V0.1 必须完成端到端最小闭环：

1. XIAO nRF54L15 Sense 固件完成触摸门控、四手势本地识别、BLE 事件、ACK 反馈和低功耗框架。
2. RK3588 新增独立 Ring Gateway，连接戒指、去重事件、映射音效并调用现有 Audio Engine。
3. Flutter App 增加戒指状态和 `Performance / DJ` 两档音效库选择。
4. 当前没有外置电容触摸模块、DRV2605L 或 LRA。开发板阶段用 USER 按键模拟触摸、用 LED 模拟触觉反馈，但必须保留可替换的真实硬件后端。

开始修改前先阅读本文件、现有 Wrist BLE 协议和 RK3588 Audio Engine。不要把 Ring UUID、状态机或命令并入 Wrist Command 协议。

## 2. 产品目标与非目标

### 2.1 产品目标

舞者在跳舞过程中用戒指触发短音效，与动作形成明确的视听配合。体验要满足以下条件：

- 只有拇指主动触摸戒指表面后，手势才可能触发音效。
- 一次触摸最多触发一个音效。
- 戒指本地完成手势识别，不依赖手机、云端或 RK3588 处理原始 IMU 流。
- App 只在演出前选择音效库；演出时手机可以退出或断开。
- 手势识别完成到扬声器开始出声的 P95 延迟不超过 100 ms。
- 最终定制戒指单次充电至少工作 8 小时。

### 2.2 V0.1 非目标

V0.1 不包含以下工作：

- 用戒指切换能量、舞蹈风格、歌曲或手环页面。
- 开发完整的八槽 Pad 编辑器。
- 在戒指上存储或播放音频。
- 使用云端识别动作。
- 训练通用 TinyML 手势模型。
- 正式发布 BLE OTA 升级流程。
- 设计定制 PCB、戒指外壳、量产治具或认证方案。
- 在当前阶段实际连接 LRA、DRV2605L 或外置电容触摸芯片。

## 3. 已确认的交互

### 3.1 触发动作

拇指按住或触摸戒指表面，相当于“扣动扳机”。触摸稳定 40 ms 后，戒指进入 `ARMED`，开始高频采集 IMU。识别一个动作后立即锁定，直到触摸释放稳定 150 ms 才能进行下一次触发。

### 3.2 音效库

App 在演出前选择两套内置音效库之一：

| 手势 | `performance` 演出音效库 | `dj` DJ 音效库 |
|---|---|---|
| 向前出拳 `PUNCH_FORWARD` | Snare / Impact | Bass Drop |
| 向上甩动 `FLICK_UP` | Air Horn | Whoosh |
| 横向划动 `SWIPE_SIDE` | Beat Stutter | Scratch |
| 手腕旋转 `WRIST_ROLL` | Bass Drop | Spinback / Vinyl Stop |

两套音效库共有七个稳定音效键：

```text
snare_impact
air_horn
beat_stutter
bass_drop
whoosh
scratch
spinback
```

`bass_drop` 被两套音效库复用。当前 Audio Engine 已有部分素材和数字键映射，但 Ring 不应依赖数字键。Ring Gateway 使用上述稳定字符串键；Audio Engine 保留旧数字键兼容层。

### 3.3 反馈语义

| 状态 | 最终触觉反馈 | 当前开发板反馈 |
|---|---|---|
| 进入 `ARMED` | 一次很轻的提示 | LED 短闪 |
| 音效已被 Audio Engine 接受 | 一次明确短振 | LED 单次亮闪 |
| 手势不完整或无法区分 | 两次弱短振 | LED 两次短闪 |
| BLE 未连接或播放失败 | 明确的失败节奏 | LED 快速三闪 |

成功反馈不能在只收到 BLE 链路确认时出现。Ring Gateway 必须先确认 Audio Engine 已接受 one-shot，再写业务 ACK。

## 4. 系统边界与架构

```text
┌──────────────────────── Flow Ring ────────────────────────┐
│ Touch Gate → IMU Sampler → Gesture Engine → Ring BLE     │
│      ↑                                      ↓             │
│  USER button / AT42QT1010             ACK → Haptic       │
└──────────────────────────┬─────────────────────────────────┘
                           │ BLE Secure Connection
                           ▼
┌────────────────────── RK3588 Hub ─────────────────────────┐
│ Ring Gateway                                              │
│   ├─ connect / bond / reconnect                           │
│   ├─ validate and deduplicate event                       │
│   ├─ map gesture through active bank                      │
│   └─ trigger named effect through Unix socket             │
│                           ↓                               │
│ Audio Engine: preloaded one-shot PCM                      │
│                           ↑                               │
│ Edge Agent REST ← App selects performance / dj            │
└────────────────────────────────────────────────────────────┘

Flow Wrist ──独立 BLE 服务──▶ RK3588 Hub
    只负责能量、风格和已有控制，不参与 Ring 音效事件
```

关键边界：

- Ring 是 BLE Peripheral / GATT Server。
- RK3588 是 BLE Central / GATT Client。
- Ring 与 Wrist 使用不同的服务 UUID、连接状态和命令模型。
- 手机不在实时触发链路中。
- 原始 IMU 数据只存在于开发构建和采集工具中。
- Ring 断线时不缓存动作，重连后不补播旧音效。

### 4.1 当前代码基线

截至本文编写时，仓库状态与目标之间有以下明确差距：

| 当前代码 | 已有能力 | Ring V0.1 要补的内容 |
|---|---|---|
| `firmware/flow-wrist` | Wrist 独立固件和 CBOR BLE 协议 | 新建 Ring 固件，不能复制 Wrist 业务状态机 |
| `audio-engine/engine.py` | 数字键 `1..6`、启动时加载已有素材、one-shot 混音 | 增加七个命名音效键、manifest、严格就绪检查 |
| `input-daemon/audio_socket.py` | 4 字节大端长度加 JSON 的 Unix socket | Ring Gateway 复用同一 framing，并等待 Audio Engine 响应 |
| `edge-agent/main.py` | `/trigger` 接受数字键并转发 Audio Engine | 增加 Ring status 和 bank API，代理 Ring Gateway 控制 socket |
| `EdgeAgentClient` | 只实现 GET 和 POST | 增加 PUT 和 Ring 数据模型 |
| `dj_control_page.dart` | 有实时 FX Pad，直接触发 RK 数字键 | 增加 Ring 状态卡和两档 bank，不改现有 FX Pad 行为 |

`whoosh` 和 `scratch` 当前不在 Audio Engine 的正式 Ring 素材清单中；它们是 V0.1 必须补齐并在演出前检查的两个资源。现有 `air_horn_burst` 保持为旧 FX Pad 素材，不进入 Ring 两套四手势映射。

## 5. 当前开发板能力与限制

### 5.1 可直接使用的硬件

XIAO nRF54L15 Sense 提供：

- nRF54L15：128 MHz Arm Cortex-M33、最高 1.5 MB NVM、最高 256 KB RAM，并集成 BLE。
- 板载 LSM6DS3TR-C 六轴 IMU，I2C 地址 `0x6A`。
- IMU 中断接 `P0.02`。
- IMU 与 PDM 麦克风共用受控电源，电源控制为 `P0.01`。
- USER 按键接 `P0.00`。
- USB 口通过板载 SAMD11 CMSIS-DAP 完成烧录、调试和串口日志，第一阶段不需要外置 J-Link。
- 电池测量使用 `P1.15` 打开分压，`P1.14` ADC 读取后按 2 倍换算。

开发板尺寸约为 21 mm × 17.8 mm，适合验证算法和链路，不代表最终戒指体积。

### 5.2 开发板阶段固定引脚

| 功能 | XIAO 标号 | nRF54L15 引脚 | V0.1 用法 |
|---|---|---|---|
| 模拟触摸 | USER | `P0.00` | 当前默认输入 |
| 真实触摸预留 | D0 | `P1.04` | 外置触摸芯片数字输出，active high |
| LRA I2C SDA | D4 | `P1.10` | DRV2605L 预留 |
| LRA I2C SCL | D5 | `P1.11` | DRV2605L 预留 |
| IMU INT | 板内连接 | `P0.02` | 数据就绪或运动中断 |
| IMU/麦克风电源 | 板内连接 | `P0.01` | 开发板传感器电源门控 |
| 电池检测使能 | 板内连接 | `P1.15` | 测量前短时拉起 |
| 电池 ADC | 板内连接 | `P1.14` | 读取电池电压 |

D4/D5 是独立引出的 I2C 总线。DRV2605L 默认地址为 `0x5A`，与板载 IMU 的 `0x6A` 不冲突。

### 5.3 电容触摸预留

推荐最终原型使用 Microchip AT42QT1010 单键电容触摸控制器：

- 触摸检测输出为 active high，固件可按普通 GPIO 中断读取。
- `touch_gate` 只暴露稳定后的按下/释放事件，业务层不知道输入来自按键还是触摸芯片。
- 当前硬件构建使用 `touch_button_backend`；接入模块后切换为 `touch_gpio_backend`。
- 设备树负责引脚、极性和上拉配置，不在 C 文件中写死 `P1.04`。

触摸电极、采样电容和外壳厚度必须跟随 Microchip 触摸设计指南验证。V0.1 只预留数字输出接口，不对最终电极结构作量产承诺。

### 5.4 触觉反馈预留

最终触觉方案为 LRA 加 TI DRV2605L：

- DRV2605L 使用 I2C，支持 LRA 闭环、自动校准和内部波形库。
- Zephyr 已提供 `ti,drv2605` 设备树绑定和驱动接口。
- 当前构建使用 `haptic_mock_led`。
- 硬件构建使用 `haptic_drv2605l`，且必须从设备树读取 actuator mode、额定参数和 GPIO，不允许把具体 LRA 电压或谐振频率写死在业务代码中。

本阶段没有马达和驱动器，因此 `haptic_drv2605l` 只要求完成接口、设备树示例和可编译的条件构建；实际自动校准和波形强度在接入真实 LRA 后验收。

### 5.5 电池与充电限制

XIAO 板载充电电路的默认充电电流约为 200 mA。常见 30–50 mAh 微型戒指电池不应直接接到该充电口。开发阶段使用 USB，或使用能承受该充电电流且带保护的较大电池。

最终戒指需要独立的小电流充电方案。电池容量按实测平均电流计算：

```text
最小电池容量 mAh = 平均电流 mA × 8 小时 ÷ 0.8
```

其中 `0.8` 为低温、老化、转换损耗和不完全放电预留。不能在没有实测数据时先拍定电池容量。

最终定制 PCB 不需要 PDM 麦克风，并应让 IMU 拥有独立电源域，避免为了动作识别同时给无用的麦克风供电。

## 6. 固件工程结构

当前仓库使用以下路径：

```text
firmware/flow-ring/
├── CMakeLists.txt
├── prj.conf
├── VERSION
├── boards/
│   ├── xiao_nrf54l15_nrf54l15_cpuapp.overlay
│   ├── development.conf
│   └── hardware.conf
├── src/
│   ├── main.c
│   ├── app_state.c
│   ├── touch_gate.c
│   ├── touch_button_backend.c
│   ├── touch_gpio_backend.c
│   ├── imu_sampler.c
│   ├── gesture_engine.c
│   ├── ring_ble.c
│   ├── haptic_driver.c
│   ├── haptic_mock_led.c
│   ├── haptic_drv2605l.c
│   ├── battery_monitor.c
│   └── diagnostics.c
├── include/flow_ring/
│   ├── app_events.h
│   ├── touch_gate.h
│   ├── imu_sampler.h
│   ├── gesture_engine.h
│   ├── ring_ble.h
│   ├── haptic_driver.h
│   └── ring_protocol.h
├── tests/
│   ├── app_state/
│   ├── gesture_engine/
│   ├── ring_protocol/
│   └── replay/
├── tools/
│   ├── capture_imu.py
│   ├── label_session.py
│   └── replay_gestures.py
└── docs/
    ├── windows-setup.md
    ├── hardware-bringup.md
    ├── gesture-data.md
    └── ble-test.md
```

如果 Windows 工作区已经完成 `harbeat-wear` 目录迁移，并且存在 `ring/README.md` 与 `wrist/flow-wrist/`，则使用 `ring/flow-ring/`。同一个提交中只能存在一个 Ring 源码目录，禁止复制两份实现。当前工作区尚未完成该迁移，因此本文默认路径是 `firmware/flow-ring/`。

### 6.1 模块职责

| 模块 | 唯一职责 | 主要依赖 |
|---|---|---|
| `app_state` | 管理 IDLE、ARMED、EVENT_PENDING、LOCKED | 其他模块的抽象接口 |
| `touch_gate` | 去抖并产生稳定触摸事件 | button 或 GPIO backend |
| `imu_sampler` | 配置 IMU、采样、时间戳和偏置修正 | Zephyr sensor API |
| `gesture_engine` | 从样本窗口生成一个手势结果 | 纯 C，不依赖 BLE/GPIO |
| `ring_ble` | 广播、配对、GATT、事件和 ACK | Zephyr Bluetooth API、zcbor |
| `haptic_driver` | 把语义反馈映射到具体后端 | LED 或 DRV2605L |
| `battery_monitor` | 按需读取电池并上报百分比 | ADC、GPIO |
| `diagnostics` | 版本化日志和错误计数 | Zephyr logging |

### 6.2 并发规则

- GPIO、IMU 和 BLE 回调只投递事件，不在中断或回调中运行分类器和业务状态机。
- `app_state` 是状态转换的唯一写入者。
- IMU 使用静态样本缓冲，不在手势窗口中动态分配内存。
- 1.2 秒、208 Hz 对应最多约 250 帧，缓冲至少容纳 256 帧。
- 队列满、采样丢帧或时间戳倒退时，本次手势判定为失败，不用残缺数据猜测动作。
- 正式构建关闭原始 IMU GATT characteristic 和高频日志。

### 6.3 构建模式

| 模式 | 触摸 | 反馈 | Raw IMU | 日志 | 用途 |
|---|---|---|---|---|---|
| `development` | USER 按键 | LED | 开启 | 详细 | 数据采集和开发板联调 |
| `hardware` | D0 外置触摸 | DRV2605L | 默认关闭 | 普通 | 接入真实外设后的台架测试 |
| `production` | D0 外置触摸 | DRV2605L | 编译移除 | 精简 | 最终低功耗构建 |

## 7. 手势状态机

```text
IDLE
  │ touch active stable for 40 ms
  ▼
ARMED
  │ start IMU at 208 Hz; observe up to 1.2 s
  ├─ valid gesture ─────────────────────────────┐
  └─ timeout / ambiguous ── feedback failure ──┤
                                                ▼
                                         EVENT_PENDING
                                                │ send indication
                                                │ wait business ACK
                                                ▼
                                             LOCKED
                                                │ ignore movement
                                                │ touch released stable 150 ms
                                                ▼
                                               IDLE
```

状态规则：

- 每次触摸最多生成一个 `event_id`。
- 识别超时或 `UNKNOWN` 不发送 BLE 音效事件。
- ATT indication 未确认时，使用同一个 `event_id` 重发一次。
- 业务 ACK 最长等待 500 ms；仍未收到则给出失败反馈并丢弃事件。
- `LOCKED` 状态不再采集新的手势，直到触摸释放。
- BLE 未连接时，触摸后立即失败提示，不进入完整识别窗口。
- BLE 在 `EVENT_PENDING` 中断开时，立即清除待确认事件；重连后不重发。
- 断线期间不写闪存队列，不在重连后补发。

### 7.1 传感器电源时序

- development 初期允许保持开发板传感器电源开启，以先验证采样和分类器。
- 低功耗配置在原始触摸边沿到达时拉起 `P0.01`，并在 40 ms 去抖窗口内完成 IMU 初始化。
- 只有触摸仍然有效且 IMU 已 ready 才能进入 `ARMED`；60 ms 内未 ready 则失败并回到 `IDLE`。
- `LOCKED` 结束后关闭高频采样。开发板是否关闭整个共享电源域由功耗测试决定，因为该电源域同时包含麦克风。
- 最终定制 PCB 使用独立 IMU 电源域，IDLE 时关闭麦克风相关硬件。

## 8. 手势识别

### 8.1 V0.1 算法

V0.1 使用触摸门控后的规则评分分类器，不直接使用机器学习：

1. 触摸成立时记录初始重力方向和陀螺仪偏置。
2. IMU 以 208 Hz 采集三轴加速度和三轴角速度。
3. 做偏置修正、低通滤波和短时去噪。
4. 提取轴向峰值、动作持续时间、角速度积分、线性冲击和总能量。
5. 四个分类器分别给出 `0..255` 分数。
6. 最高分达到本类阈值，且与第二名的差值达到最小 margin，才输出手势；否则输出 `UNKNOWN`。

### 8.2 分类特征

| 手势 | 主要特征 | 排除条件 |
|---|---|---|
| `PUNCH_FORWARD` | 沿戒指纵轴的短促加速度峰值 | 累计滚转过大 |
| `FLICK_UP` | 相对初始重力方向向上的加速度，伴随短促俯仰角速度 | 横轴能量占优 |
| `SWIPE_SIDE` | 戒指横轴加速度峰值明显 | 纵轴冲击或滚转占优 |
| `WRIST_ROLL` | 绕戒指纵轴的累计角度明显 | 线性冲击过大 |

分类顺序先判断 `WRIST_ROLL`，再比较其他三类。戒指结构必须固定传感器纵轴、触摸面和佩戴方向；电路板不能在外壳内转动。

### 8.3 参数管理

所有滤波、阈值和 margin 使用版本化 `gesture_profile`，不能散落成无法追踪的魔法数字。每次数据文件和测试报告记录：

```text
firmware_version
gesture_profile_version
sample_rate_hz
accel_range
gyro_range
board_orientation
```

参数更新必须通过离线重放集，不允许只凭一次佩戴体验直接覆盖默认配置。

### 8.4 数据采集格式

开发固件通过 Raw IMU Debug characteristic 或 USB 串口输出记录。每帧至少包含：

```text
timestamp_us
accel_x_mg
accel_y_mg
accel_z_mg
gyro_x_mdps
gyro_y_mdps
gyro_z_mdps
touch_state
expected_gesture
performer_id
session_id
board_orientation
firmware_version
gesture_profile_version
```

第一轮数据：

- 每种手势至少 60 次，覆盖轻、中、重三种力度。
- 覆盖站立、移动、音乐节拍中和连续舞蹈状态。
- 至少记录 15 分钟正常跳舞负样本。
- 每种手势另留 30 次不参与调参的验证样本。
- 包含触摸但不动作、动作做到一半取消、连续动作和相似干扰动作。

## 9. Ring BLE v1

### 9.1 设备角色和广播

- 广播名：`FLOW-RING-XXXX`，末四位来自设备地址。
- 广播包包含完整 Ring Service UUID。
- Ring 是 Peripheral / GATT Server。
- RK3588 是 Central / GATT Client。
- 推荐协商 ATT MTU 247，但协议不能依赖单一 MTU 才能工作。

### 9.2 UUID

Ring 使用与 Wrist 不同的 `0002` 命名空间：

| 名称 | UUID | Ring 视角 | 权限 | 最大长度 |
|---|---|---|---|---:|
| Ring Service | `464C4F57-0002-4F57-8101-000000000001` | Primary service | - | - |
| Ring Event | `464C4F57-0002-4F57-8101-000000000002` | Ring → Hub | encrypted Indicate | 192 B |
| Ring ACK | `464C4F57-0002-4F57-8101-000000000003` | Hub → Ring | encrypted Write with response | 128 B |
| Ring Status | `464C4F57-0002-4F57-8101-000000000004` | Ring → Hub | encrypted Read/Notify | 256 B |
| Ring Config | `464C4F57-0002-4F57-8101-000000000005` | Hub → Ring | encrypted Read/Write with response | 256 B |
| Raw IMU Debug | `464C4F57-0002-4F57-8101-000000000006` | Ring → Tool | encrypted Notify，开发构建专用 | MTU 允许的单包上限 |
| Battery Service | `0x180F` | 标准服务 | Read/Notify | 1 B |
| Device Information | `0x180A` | 标准服务 | Read | UTF-8 |

### 9.3 编码规则

- 自定义 characteristic 使用 CBOR map。
- key 使用 UTF-8 text string，与现有 Wrist 协议一致。
- 不使用 float；置信度用 `confidence_q8` 的 `0..255` 整数。
- `v` 当前固定为 `1`。
- 未知字段由接收方忽略；缺少必填字段必须拒绝。
- `boot_id` 是每次启动生成的 16 位十六进制字符串。
- `event_id` 是非零 `uint32`，同一 `boot_id` 内递增。
- 如果 `event_id` 即将回绕，固件先生成新的 `boot_id`，再从随机非零起点继续，不能产生相同复合事件 ID。

### 9.4 Ring Event

```json
{
  "v": 1,
  "kind": "gesture_event",
  "boot_id": "8f3a19d04b7c221e",
  "event_id": 42,
  "gesture": "punch_forward",
  "confidence_q8": 231,
  "battery_pct": 76,
  "uptime_ms": 512309
}
```

`gesture` 只允许：

```text
punch_forward
flick_up
swipe_side
wrist_roll
```

### 9.5 Ring ACK

成功：

```json
{
  "v": 1,
  "kind": "gesture_ack",
  "boot_id": "8f3a19d04b7c221e",
  "event_id": 42,
  "status": "accepted",
  "audio_key": "snare_impact",
  "error": null
}
```

失败：

```json
{
  "v": 1,
  "kind": "gesture_ack",
  "boot_id": "8f3a19d04b7c221e",
  "event_id": 42,
  "status": "rejected",
  "audio_key": null,
  "error": "audio_missing"
}
```

首版错误码：

| 错误码 | 含义 |
|---|---|
| `protocol_error` | CBOR、版本或字段非法 |
| `duplicate` | 已处理事件；Ring 视为成功，不再次播放 |
| `audio_not_ready` | Audio Engine 不可用 |
| `audio_missing` | 当前映射的素材没有预加载 |
| `gateway_error` | Ring Gateway 内部错误 |
| `unpaired` | 未完成合法绑定 |

### 9.6 Ring Status 和 Config

Status 至少包含：

```json
{
  "v": 1,
  "kind": "ring_status",
  "firmware_version": "0.1.0",
  "gesture_profile_version": 1,
  "battery_pct": 76,
  "state": "idle",
  "last_error": null,
  "dropped_samples": 0
}
```

Config V0.1 只允许：

- `gesture_profile_version`：选择已编译进固件的配置。
- `sensitivity`：`1`、`2`、`3` 三档，默认 `2`。
- `raw_imu_enabled`：仅 development 构建接受，production 必须拒绝。

音效库不写入 Ring Config。Ring 永远不知道当前是 `performance` 还是 `dj`。

### 9.7 去重与重试

Hub 使用 `(device_identity, boot_id, event_id)` 去重。最近已处理事件保存在有界内存缓存中；Ring Gateway 重启后不恢复旧动作，也不从 Ring 拉取历史。相同事件再次到达时：

1. 不调用 Audio Engine。
2. 返回 `status: accepted`、`error: duplicate`，并带回首次处理时缓存的 `audio_key`。
3. Ring 把该 ACK 当成已处理，给出成功反馈并等待释放。

## 10. BLE 配对与安全

- 使用 LE Secure Connections。
- 戒指无屏幕，V0.1 使用 Just Works。
- 完成绑定后启用已绑定 Hub 白名单。
- 默认只保存一个 Hub bond。
- 首次启动开放 120 秒配对窗口。
- development 构建可在上电时长按 USER 10 秒清除 bond。
- 最终硬件使用上电时持续触摸 10 秒，或使用有线维护命令清除 bond。
- 普通运行中的长按不能清除 bond。
- Raw IMU Debug 也要求加密连接，production 构建直接移除该 characteristic。

Just Works 不提供数字比较带来的中间人确认，因此现场安全主要依赖短配对窗口、单 Hub bond 和白名单。该风险对 V0.1 可接受；若量产场景需要更高配对保证，应增加有线配网、二维码密钥或 NFC 辅助流程，并升协议版本。

## 11. RK3588 Ring Gateway

### 11.1 独立进程

新增：

```text
cypher-integration/rk3588-edge/ring-gateway/
├── main.py
├── config.py
├── ble_client.py
├── protocol.py
├── gesture_map.py
├── audio_client.py
├── state_store.py
├── requirements.txt
└── README.md
```

Ring Gateway 使用 BlueZ，作为 systemd 独立服务运行。BLE 断线、配对或解析异常不能拖垮 Edge Agent 和 Audio Engine。

### 11.2 事件路径

1. 扫描完整 Ring Service UUID；名称前缀只作为诊断信息。
2. 连接并完成配对/绑定。
3. 订阅 Ring Event indication。
4. 校验 CBOR、版本、设备身份和字段范围。
5. 以 `(device_identity, boot_id, event_id)` 去重。
6. 读取本地保存的当前音效库。
7. 把 `gesture` 映射为稳定 `audio_key`。
8. 通过现有长度前缀 JSON Unix socket 调用 Audio Engine。
9. Audio Engine 返回 `one_shot` 后，Ring Gateway 写成功 ACK。
10. 更新状态供 Edge Agent 和 App 查询。

实时事件不能绕到云端，也不能等待 App。

### 11.3 Ring Gateway 控制接口

Ring Gateway 通过仅本机可访问的 Unix socket 向 Edge Agent 提供：

```text
/run/cypher/ring-gateway.sock
```

socket 由 systemd 创建运行目录，属主为 Ring Gateway 服务账号，权限为 `0660`；Edge Agent 通过同一服务组访问。不要把 bank 修改接口暴露为可被任意本机用户写入的 `/tmp` socket。

命令：

```json
{"cmd":"status"}
{"cmd":"set_bank","bank":"performance"}
{"cmd":"clear_bond"}
```

`set_bank` 使用临时文件加原子替换持久化到：

```text
~/cypher/config/ring.json
```

文件内容：

```json
{
  "schema_version": 1,
  "bank": "performance"
}
```

文件缺失、损坏或值非法时使用 `performance`，同时在状态中报告配置错误。Ring Gateway 不因该错误退出。

### 11.4 重连

- 正常断线后使用带抖动的指数退避，1、2、4、8 秒，之后固定 10 秒。
- 已绑定设备优先按身份连接，不连接现场其他 `FLOW-RING-*`。
- 重连后重新订阅 indication，并读取 Ring Status。
- 重连不改变 App 选择的音效库。
- 重连后不请求或补播历史事件。
- Ring Gateway 启动时先断开遗留的本服务连接再重新订阅，迫使 Ring 清除任何旧的 `EVENT_PENDING`。因此进程重启不会让上一动作在新连接中重发。

## 12. Audio Engine 改造

### 12.1 稳定音效键

现有 Audio Engine 使用数字键和以下部分文件：

```text
air_horn.wav
air_horn_burst.wav
snare_crack.wav
beat_juggle_stutter.wav
bass_drop.wav
vinyl_stop.wav
```

Ring V0.1 增加命名触发，并通过 manifest 保持旧文件兼容：

```json
{
  "schema_version": 1,
  "effects": {
    "snare_impact": "snare_crack.wav",
    "air_horn": "air_horn.wav",
    "beat_stutter": "beat_juggle_stutter.wav",
    "bass_drop": "bass_drop.wav",
    "whoosh": "whoosh.wav",
    "scratch": "scratch.wav",
    "spinback": "vinyl_stop.wav"
  }
}
```

Unix socket 新命令：

```json
{"cmd":"trigger_effect","effect":"snare_impact","ts":1787880000.123}
```

成功响应：

```json
{"ok":true,"effect":"snare_impact","action":"one_shot"}
```

旧的 `{"cmd":"trigger","key":3}` 保持可用，避免破坏现有实体键盘和 App FX Pad。

### 12.2 预加载和素材缺失

- Audio Engine 启动时解码 manifest 中全部七个 Ring 音效。
- 素材缺失时，音乐播放服务可以继续运行，但 `ring_audio_ready` 必须为 false。
- Ring Gateway 在 `ring_audio_ready=false` 时不进入可演出状态，并对手势返回 `audio_missing` 或 `audio_not_ready`。
- App 必须在演出前显示缺失的具体音效键。
- 演出中不能等到第一次触发才读文件或发现文件不存在。
- 测试可以生成短脉冲音作为 fixture；正式素材必须记录来源、授权、文件 SHA-256、采样率和声道数。

## 13. Edge Agent 和 App

### 13.1 Edge Agent API

在现有 FastAPI Edge Agent 增加：

```http
GET /v1/ring/status
PUT /v1/ring/bank
Content-Type: application/json

{"bank":"performance"}
```

状态响应：

```json
{
  "connected": true,
  "paired": true,
  "device_id": "FLOW-RING-A12F",
  "firmware_version": "0.1.0",
  "gesture_profile_version": 1,
  "battery_pct": 76,
  "bank": "performance",
  "ring_audio_ready": true,
  "last_gesture": "punch_forward",
  "last_audio_key": "snare_impact",
  "last_event_at_ms": 1787880000123,
  "last_error": null
}
```

`PUT /v1/ring/bank`：

- 只接受 `performance` 或 `dj`。
- 使用现有 Edge Token 鉴权。
- 成功必须等到 Ring Gateway 已持久化配置。
- 返回最终 bank 和 `ring_audio_ready`。
- 不向 Ring 写音效库配置。

### 13.2 Flutter App

复用现有 `mobile/lib/src/edge_agent_client.dart` 和 `dj_control_page.dart`：

- `EdgeAgentClient` 增加 PUT 支持、`getRingStatus()` 和 `setRingBank()`。
- DJ Control 第 4 步顶部增加 Ring 状态卡，不开发新的八槽编辑器。
- 状态卡显示连接、配对、电量、固件、音频就绪和最近错误。
- 使用两段式选择器显示“演出音效”和“DJ 音效”。
- 点击后显示保存中、成功或明确错误；失败时恢复服务端实际值。
- App 轮询只用于显示，断开 App 不影响 Ring Gateway 继续处理手势。
- 能量和舞蹈风格入口保持原样，不放进 Ring 卡片。

## 14. Windows 开发环境

### 14.1 设备选择结论

主开发机使用 Windows 11 x64。Nordic 当前把 Windows 11 x64 列为 Tier 1；用户现有 Apple M5、macOS 26 ARM64 属于 Tier 3。Windows ARM64 不受支持。

因此：

- Windows 11 x64：主固件编译、烧录、串口、BLE 和 RK SSH 联调。
- Mac：iOS 构建、IMU 数据分析和辅助开发。
- 如果 Windows 是 ARM 机型，则改用 Mac，不尝试在 Windows ARM 上拼装非官方工具链。

### 14.2 固定版本

```text
nRF Connect SDK: 3.4.0
Board target: xiao_nrf54l15/nrf54l15/cpuapp
Application: firmware/flow-ring
```

SDK 与匹配工具链必须一起安装。不要把系统 Python、任意 Zephyr 或其他 GCC 混入构建环境。

### 14.3 Windows 安装顺序

1. 安装 Git 和 Visual Studio Code。
2. 安装 Nordic 的 nRF Connect for VS Code 扩展。
3. 在扩展欢迎页选择 `Install SDK`。
4. 下载区域选择 Mainland China 或当前网络更快的区域。
5. SDK 类型选择完整 `nRF Connect SDK`，版本选择 `v3.4.0`。
6. 使用默认 `C:\ncs` 安装位置。
7. 把项目放在短英文路径，例如 `C:\work\harbeat`。
8. 使用带数据功能的 USB-C 线连接 XIAO。
9. 先构建并烧录官方 `hello_world`，目标固定为 `xiao_nrf54l15/nrf54l15/cpuapp`。
10. 串口看到 `Hello World! xiao_nrf54l15/nrf54l15/cpuapp` 后，才开始 Ring 工程。

官方冒烟构建的命令形式：

```powershell
west build -b xiao_nrf54l15/nrf54l15/cpuapp samples/hello_world -d build/hello-ring --pristine
west flash -d build/hello-ring
```

如果命令行没有进入 Nordic 工具链环境，优先使用 VS Code 扩展的 `Generate and Build` 与 `Flash`，不要通过全局安装包猜测缺失依赖。

### 14.4 工程构建

开发构建：

```powershell
west build -b xiao_nrf54l15/nrf54l15/cpuapp firmware/flow-ring -d build/flow-ring-dev --pristine -- -DEXTRA_CONF_FILE=boards/development.conf
west flash -d build/flow-ring-dev
```

真实外设构建在没有连接外设时只要求编译通过，不烧录运行：

```powershell
west build -b xiao_nrf54l15/nrf54l15/cpuapp firmware/flow-ring -d build/flow-ring-hw --pristine -- -DEXTRA_CONF_FILE=boards/hardware.conf
```

实现时必须在 `windows-setup.md` 中记录实际验证过的命令。如果 NCS 3.4.0 对 `EXTRA_CONF_FILE` 的相对路径解析与上述形式不同，以构建日志中最终加载的文件为准并修正文档，不能保留未经验证的命令。

## 15. 开发阶段与门禁

### Gate 0：环境冒烟

交付证据：

- Windows 版本和 CPU 架构截图或文本记录。
- NCS 和工具链版本。
- `hello_world` 完整构建日志。
- 烧录成功和串口输出。

失败时不进入 Ring 工程。

### Gate 1：固件骨架

完成：

- 按键模拟触摸。
- LED 模拟反馈。
- IMU 读取和时间戳。
- 状态机。
- Ring BLE v1 编解码。
- 标准 Battery Service。
- 纯模块 ztest。

台架验收：按住 USER、完成一次模拟手势、只生成一个事件；松开后才能再次触发。

### Gate 2：数据和分类器

完成数据采集、标注、离线重放和第一版 `gesture_profile`。离线指标达到第 16 节要求后，才把阈值设为默认值。

### Gate 3：RK3588 闭环

完成 Ring Gateway、命名音效触发、去重、业务 ACK、systemd 服务和自动重连。使用测试客户端模拟 Ring Event 时，七个音效键全部能得到确定响应。

### Gate 4：App 选择

完成 Ring 状态卡和两档 bank。选择结果写入 RK3588，重启 Edge Agent、Ring Gateway 和 App 后仍保持。

### Gate 5：真实跳舞联调

戴开发板原型完成手势准确率、误触、延迟、断线和连续运行测试。当前没有触摸芯片和 LRA，因此 USER 与 LED 是本门禁允许的替代件。

### Gate 6：真实外设和定制硬件

该门禁属于下一硬件阶段：接入 AT42QT1010、DRV2605L、选定 LRA、测量真实功耗，并据此设计满足 8 小时的电池和充电电路。Gate 0–5 不等待这些器件。

## 16. 测试与验收

### 16.1 自动化测试

| 层 | 工具 | 必测内容 |
|---|---|---|
| 纯固件模块 | Zephyr ztest | 状态转换、去抖、gesture score、CBOR、事件 ID、超时 |
| 数据重放 | Python | 每条标注样本的分类、置信度和混淆矩阵 |
| Ring Gateway | pytest | 校验、映射、去重、重试、断线、配置持久化、音频错误 |
| Audio Engine | pytest | 七个命名键、旧数字键兼容、预加载、缺失素材 |
| Edge Agent | pytest | status、PUT bank、鉴权、非法值、socket 错误 |
| Flutter | flutter test | 状态卡、bank 成功/失败、服务端回滚、离线显示 |
| 全链路 | 硬件测试脚本 | BLE 事件到真实音频输出和 ACK |

### 16.2 手势指标

- 独立验证集总体准确率不低于 92%。
- 每种手势召回率不低于 88%。
- 触摸但没有完整动作时拒绝率不低于 98%。
- 不触摸状态下连续跳舞 30 分钟，音效误触发为 0。
- 手势结束到本地结果的 P95 不超过 50 ms。
- 最高分和次高分过于接近时必须拒绝，不播放猜测音效。

### 16.3 端到端指标

- 本地识别结果到扬声器开始出声 P95 不超过 100 ms。
- 每个触摸周期最多一个音效。
- ATT 重发、业务 ACK 丢失和 BLE 重连不产生双响。
- Audio Engine 失败时 Ring 得到失败反馈，不得显示成功。
- Hub 恢复后自动重连，不补播断线期间动作。
- 两套音效库逐项映射正确。
- App 退出后 Ring 仍能按最后保存的 bank 工作。

### 16.4 稳定性和功耗

- 连续运行 8 小时无崩溃、死锁、持续重连循环或计数器异常。
- 开发板阶段记录 USB 空闲、BLE 已连、ARMED、识别和 LED 反馈各状态电流。
- 真实外设阶段再记录触摸芯片、DRV2605L 和 LRA 的平均与峰值电流。
- 最终定制硬件按 8 小时公式选择电池，并进行真实 8 小时放电验证。

### 16.5 必须提交的报告

```text
docs/test-results/ring-gate-0-windows.md
docs/test-results/ring-gate-1-firmware.md
docs/test-results/ring-gate-2-gestures.md
docs/test-results/ring-gate-3-rk.md
docs/test-results/ring-gate-4-app.md
docs/test-results/ring-gate-5-field.md
docs/test-results/ring-power-template.md
```

报告必须包含命令、版本、原始结果摘要、失败项和复测结果，不能只写“已通过”。

## 17. 故障行为

| 故障 | Ring 行为 | Hub/App 行为 |
|---|---|---|
| BLE 未连接 | 触摸后立即失败提示 | App 显示断开并提供最近错误 |
| 手势模糊 | 不发送事件，两次弱反馈 | 不产生音效日志 |
| IMU 丢帧 | 取消本次动作 | 状态累计 dropped sample |
| 重复事件 | 等待 duplicate ACK 后结束 | 不重复播放 |
| ACK 超时 | 500 ms 后失败，丢弃 | 记录超时，不补播 |
| Audio Engine 离线 | 失败反馈 | `ring_audio_ready=false` |
| 素材缺失 | 失败反馈 | 演出前列出缺失键 |
| bank 配置损坏 | Ring 无感 | 回退 `performance` 并报告错误 |
| App 离线 | 正常工作 | 只失去状态显示和改 bank 能力 |
| Ring Gateway 重启 | Ring 重连，不补播 | 读取持久化 bank |

## 18. 日志和可观测性

Ring development 日志至少包含：

- firmware 和 gesture profile 版本。
- 状态转换及原因。
- 采样数、丢帧数和识别结果。
- `boot_id`、`event_id`、gesture 和 confidence。
- BLE 连接、配对、indication 和 ACK 结果。
- 电量和最近错误。

production 日志禁止连续输出原始 IMU。Ring Gateway 日志使用结构化字段：

```text
device_id
boot_id
event_id
gesture
audio_key
bank
deduplicated
recognition_to_receive_ms
receive_to_audio_ms
ack_status
```

不要记录 BLE 密钥、Edge Token 或可复用的认证材料。

## 19. 交付物

V0.1 完成时仓库必须包含：

- `flow-ring` 固件源码、设备树、配置和测试。
- Windows 安装、构建、烧录和串口说明。
- IMU 数据采集、标注和离线重放工具。
- Ring BLE v1 协议文档和编码测试向量。
- RK3588 Ring Gateway、systemd 单元和测试。
- Audio Engine 命名音效接口、manifest 和兼容测试。
- Edge Agent Ring API 和 Flutter Ring 状态卡。
- 七个音效的来源、授权、SHA-256 和格式清单。
- Gate 0–5 测试报告和功耗模板。

## 20. 给执行 AI 的停手条件

遇到以下情况不要自行扩大范围：

- Windows 不是 x64，或 NCS 3.4.0 无法完成官方 `hello_world`。
- 实际开发板不是 XIAO nRF54L15 Sense。
- 仓库同时存在两份可编辑 Ring 源码，无法判断真源。
- 现有 Audio Engine 的 Unix socket 协议与本文观察结果不同。
- 用户要求改动四手势、音效库或 Ring/Wrist 职责边界。
- 接入真实 LRA 时缺少额定电压、谐振频率或机械固定信息。
- 准备用小容量电池直接使用开发板约 200 mA 的充电电路。

这些情况必须保留现场证据并询问用户。普通编译错误、单元测试失败或 API 适配属于正常实现工作，不需要扩大产品范围。

## 21. 官方资料

- [Nordic nRF Connect for Desktop 支持的操作系统](https://docs.nordicsemi.com/r/bundle/nrf-connect-for-desktop/page/app/nrf-connect-desktop/os_support.html)
- [Nordic：首次安装 SDK 与工具链](https://docs.nordicsemi.com/r/bundle/nrf-connect-vscode/page/get_started/quick_setup.html/installing-sdk-and-toolchain-for-the-first-time)
- [Nordic nRF Connect SDK v3.4.0](https://github.com/nrfconnect/sdk-nrf/releases/tag/v3.4.0)
- [Zephyr：XIAO nRF54L15 开发板](https://docs.zephyrproject.org/latest/boards/seeed/xiao_nrf54l15/doc/index.html)
- [Seeed：XIAO nRF54L15 Sense 入门、引脚和硬件资源](https://wiki.seeedstudio.com/xiao_nrf54l15_sense_getting_started/)
- [Microchip AT42QT1010](https://www.microchip.com/en-us/product/at42qt1010)
- [TI DRV2605L](https://www.ti.com/product/DRV2605L)
- [Zephyr DRV2605 haptic driver sample](https://docs.zephyrproject.org/latest/samples/drivers/haptics/drv2605/README.html)

## 22. 现有项目参考

- `firmware/flow-wrist/docs/ble-protocol-v1.md`：Wrist 现有 CBOR、加密、bond 和业务 ACK 约定。
- `firmware/flow-wrist/docs/superpowers/plans/2026-08-27-wear-repository-contracts-baseline.md`：Wear 仓库边界和 Ring 不复用 Wrist UUID 的约定。
- `cypher-integration/rk3588-edge/audio-engine/engine.py`：当前预加载、数字音效键和 one-shot 实现。
- `cypher-integration/rk3588-edge/input-daemon/audio_socket.py`：当前长度前缀 JSON Unix socket。
- `cypher-integration/rk3588-edge/edge-agent/main.py`：当前 FastAPI 和 `/trigger` 转发。
- `mobile/lib/src/edge_agent_client.dart`：当前 App 到 Edge Agent 的客户端。
- `mobile/lib/src/dj_control_page.dart`：当前实时 FX Pad 页面。
- `docs/superpowers/specs/2026-08-18-harbeat-mobile-app-product-design.md`：完整八槽 Pad 仍属后续产品设计；Ring V0.1 不实现它。
