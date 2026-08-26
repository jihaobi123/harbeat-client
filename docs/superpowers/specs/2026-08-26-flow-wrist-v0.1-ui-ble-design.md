# Flow Wrist V0.1 UI 与 BLE 设计规格

日期：2026-08-26

硬件：Waveshare ESP32-S3-Touch-AMOLED-2.06

Hub：RK3588 Linux 设备

软件：ESP-IDF 5.5+、LVGL 9.5、NimBLE、BlueZ

## 1. 目标

Flow Wrist V0.1 用来控制现场音乐的能量和风格。用户看到舞池人员或气氛变化后，唤醒手环，在 3–5 秒内发出调整指令。RK3588 Hub 接收指令，并在约 10–20 秒内完成选曲或音乐过渡。

首版只验证两项控制：

- 能量：1–5 档，与曲库中的能量标记一致。
- 风格：`hiphop`、`breaking`、`funk`、`locking` 四个 Flow 风格配置。

手环不直接处理音乐。当前曲目、目标曲目、BPM、执行阶段和剩余时间都由 Hub 决定。手环负责输入、显示和连接状态。

## 2. 首版范围

### 包含

- BOOT 短按唤醒控制界面。
- 触摸选择能量或风格。
- 点选后立即发送，不显示二次确认框。
- 显示当前和目标风格、目标能量、目标 BPM、下一首切换倒计时。
- 执行期间锁定所有新指令。
- BLE 配对、Hub 自动重连、状态同步和电量上报。
- Hub 忙碌、离线、超时和执行中断线的反馈。
- 屏幕亮度、自动熄屏和电池状态等基础功能。

### 不包含

- 在手环上修改 BPM 或调性。
- IMU 手势控制、双击屏幕唤醒和震动反馈。
- 多任务排队或覆盖正在执行的指令。
- Wi-Fi、MicroSD、麦克风、扬声器和 RTC 相关产品功能。
- 自定义 PCB、最终续航优化和量产安全方案。

## 3. 硬件使用约束

显示屏分辨率为 410×502，CO5300 使用专用 QSPI。FT3168 触摸、电源管理、IMU、RTC 和音频器件共用 GPIO14/15 的 I2C 总线。

首版把 BOOT 作为界面唤醒键。正常运行时由 GPIO0 读取短按；上电时按住 BOOT 仍然进入下载模式。PWR 保留电源功能，不分配长按操作，因为持续按压约 6 秒会关机。若某批次硬件实际带有独立 RESET 键，该键不能复用为应用按键。

AMOLED 使用暖白底，但不常亮：

- 控制首页和选择页 10 秒无操作后熄屏。
- 执行页在切换完成前保持点亮，5 秒无触摸后降低亮度。
- 完成页停留 2 秒，然后回到首页；首页继续按无操作时间熄屏。
- V0.1 不进入会关闭 BLE 或触摸控制器的深度睡眠。

## 4. 视觉语言

界面沿用 HarBeat 移动端的叙事编辑插画方向，但重新为手表设计版式。手机端的信息密度、底部导航和多卡片结构不移植到手环。

### 4.1 视觉规则

- 暖纸白作为主背景，深墨色作为结构线和正文色。
- 黄色用于能量，钴蓝用于风格，粉色用于当前操作和运动轨迹。
- 绿色只表示 Hub 在线或切换成功；橙色表示忙碌和需要等待。
- 大标题使用紧凑、粗重的编辑字体。说明文字使用高可读无衬线字体。
- 插画用黑色手绘线和平涂色块。每屏只保留一个叙事画面，不用插画填满所有空白。
- 高饱和色不承载长段文字。当前操作必须有形状、位置和文字三重提示，不能只靠颜色。

### 4.2 建议色板

| 角色 | 色值 |
|---|---|
| 暖纸白 | `#FFF8ED` |
| 深墨色 | `#11110F` |
| 操作粉 | `#F54F87` |
| 能量黄 | `#FFD21E` |
| 风格蓝 | `#2C8FE6` |
| 在线绿 | `#15933A` |
| 忙碌橙 | `#F47A27` |

### 4.3 字体与资源

大标题和数字各使用一套 LVGL 编译字体；中文状态文字使用精简字库，只打包界面实际出现的字符。能量和风格插画以局部画幅资源编译进固件，不使用视频或全屏透明动画。

## 5. 交互结构

### 5.1 唤醒

```text
屏幕关闭
→ BOOT 短按
→ 屏幕点亮
→ 显示主控制页
```

若 BLE 已连接，主控制页立即可用。若尚未连接，页面显示“正在连接 Hub”，两个控制入口暂时禁用。

### 5.2 主控制页：双入口海报

主控制页只提供两个大入口：

```text
ENERGY / 当前 03
STYLE / 当前 HIPHOP
```

两个入口都占用大面积触摸区域。顶部显示 Hub 在线状态，不设置底部导航。

### 5.3 能量选择：单档海报

进入能量页后，中央只显示一个能量档位。左右滑动浏览 1–5 档，点击中央海报立即发送。

- 初始位置是当前能量。
- 能量档位不循环，1 和 5 分别是两端。
- 滑动只改变预览，不发送。
- 点击当前已生效的档位不发送，页面提示“当前能量已生效”。
- 触摸移动超过手势阈值后，不触发点击发送。

每个能量档位有独立的数字、名称、颜色比例和动作插画。数字始终是最清楚的识别信息。

### 5.4 风格选择：海报轮播

风格页与能量页使用同一套操作：左右浏览，点击中央海报立即发送。首版顺序固定为：

```text
hiphop → breaking → funk → locking
```

风格轮播可以首尾循环。每张海报使用不同的动作插画和辅助色，但保持标题位置、点击区域和返回方式一致。点击当前已生效的风格只显示状态，不发送指令。

这四项是 Flow 风格配置，不等同于严格的音乐流派。Hub 负责把风格 ID 映射到曲库标签、BPM 范围、选曲权重和过渡策略。

### 5.5 点选与锁定

用户点击目标海报后，手环立即发送指令并进入本地 `sending` 状态。Hub 接受后，手环切换到全局锁定页。执行完成前，能量和风格都不能再次修改。

锁定期间触摸屏幕时，页面显示：

```text
正在完成上一次切换
剩余 14 秒
```

手环不排队、不覆盖，也不重复发送原指令。

### 5.6 执行页：双唱片封面

执行页采用“当前 / 下一首”两张唱片封面对照。信息优先级如下：

1. 当前风格、目标风格和下一首切换倒计时。
2. 执行阶段，例如准备中或过渡中。
3. 目标能量和目标 BPM。

能量与 BPM 是次要事实，不占据主视觉。BPM 只读。

### 5.7 完成页

只有收到 Hub 的 `completed` 快照后，手环才显示完成页，例如：

```text
BREAKING IS LIVE
✓
```

完成页停留 2 秒，然后回到主控制页。手环不能根据本地倒计时自行判断成功。

## 6. UI 状态机

```text
screen_off
  ↓ BOOT 短按
connecting / idle
  ↓ 进入能量或风格
selecting
  ↓ 点击目标海报
sending
  ├─ Hub accepted → preparing → transitioning → completed → idle
  ├─ Hub busy → rejected_busy → 显示 Hub 当前任务 → idle 或继续显示任务
  ├─ 业务确认超时 → synchronizing → idle 或 error
  ├─ BLE 断开 → reconnecting
  └─ Hub error → error → idle
```

UI 只显示来自最新 Hub 快照的业务状态。BLE 已送达不等于 Hub 已接受，倒计时归零也不等于执行完成。

## 7. BLE 架构

### 7.1 角色

```text
Flow Wrist：BLE Peripheral / GATT Server
RK3588 Hub：BLE Central / GATT Client
```

Hub 主动扫描、连接和管理可穿戴设备。Wrist 广播名称使用 `FLOW-WRIST-XXXX`，其中 `XXXX` 是设备 ID 的后四位。

V0.1 使用 BLE LE Secure Connections 的 Just Works 配对，并在 Hub 保存设备身份。Hub 只连接已登记的 Wrist。首次配对需要用户在 Hub 端明确进入配对模式。量产版本再增加屏幕配对码或更强的身份验证。

连接后的初始化顺序固定为：

```text
Hub 发现服务
→ 订阅 Command Indication
→ 写入 Catalog
→ 写入完整 Hub State
→ Wrist 启用能量和风格入口
```

在完整 Hub State 到达前，Wrist 只能显示连接进度，不能发送控制指令。

### 7.2 GATT 服务

自定义服务 UUID：

```text
464C4F57-0001-4F57-8101-000000000001
```

| Characteristic | UUID | 属性 | 作用 |
|---|---|---|---|
| Command | `464C4F57-0001-4F57-8101-000000000002` | Indicate | Wrist 向 Hub 发送控制指令 |
| Hub State | `464C4F57-0001-4F57-8101-000000000003` | Read、Write with response | Hub 写入权威状态快照 |
| Catalog | `464C4F57-0001-4F57-8101-000000000004` | Read、Write with response | Hub 同步能量范围和风格目录 |

电量使用标准 Battery Service `0x180F`，设备信息使用标准 Device Information Service `0x180A`。

### 7.3 编码和版本

V0.1 使用 CBOR。本文用 JSON 展示等价结构。所有自定义消息都带 `v: 1`。Command 保持在单个 ATT 数据包内；Hub State 和 Catalog 允许使用标准 GATT Long Write。连接后请求 ATT MTU 247，但协议不能依赖 MTU 协商一定成功。

未知字段必须忽略。协议版本不兼容时，Wrist 显示“需要更新固件”，并禁止发送控制指令。

## 8. 消息定义

### 8.1 能量指令

```json
{
  "v": 1,
  "kind": "command",
  "id": 42,
  "op": "set_energy",
  "value": 5
}
```

`value` 必须是 1–5 的整数。Hub 收到非法值后返回 `rejected`，错误码为 `invalid_energy`。

### 8.2 风格指令

```json
{
  "v": 1,
  "kind": "command",
  "id": 43,
  "op": "set_style",
  "value": "breaking"
}
```

`value` 使用 Catalog 中的稳定 ID。Hub 不接受仅靠显示文字匹配的风格名称。

### 8.3 Hub 状态快照

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
  "current": {
    "energy": 3,
    "style": "hiphop",
    "bpm": 96
  },
  "target": {
    "energy": 5,
    "style": "breaking",
    "bpm": 108
  },
  "error": null
}
```

`phase` 只允许以下值：

```text
idle
accepted
preparing
transitioning
completed
rejected
error
```

`current` 表示当前实际生效状态，`target` 表示 Hub 正在准备的目标。`target` 在 `idle` 状态可以为空。`eta_ms` 只在 `preparing` 和 `transitioning` 阶段有效。

`completed` 快照必须满足：`locked` 为 `false`、`eta_ms` 为 `0`，并且 `current` 已更新为实际生效状态。完成页使用 `current`，不再读取旧的 `target`。

### 8.4 Catalog

```json
{
  "v": 1,
  "kind": "catalog",
  "energy_min": 1,
  "energy_max": 5,
  "styles": [
    {"id": "hiphop", "label": "HIPHOP", "order": 1},
    {"id": "breaking", "label": "BREAKING", "order": 2},
    {"id": "funk", "label": "FUNK", "order": 3},
    {"id": "locking", "label": "LOCKING", "order": 4}
  ]
}
```

V0.1 固件只带这四种风格的专属插画。Hub 下发未知风格时，Wrist 可以显示通用文字海报，但不把未知风格加入可选轮播。

## 9. 顺序、幂等和超时

- `id` 是 Wrist 生成的递增 32 位无符号整数。重启后从随机种子开始，避免与 Hub 缓存中的旧命令碰撞。
- Hub 用 `ack_id` 对应最近处理的命令。重复 `id` 只能返回既有结果，不能再次触发音乐操作。
- `revision` 是 Hub 在单次 `session_id` 内生成的递增 32 位无符号整数。Wrist 丢弃小于或等于已应用版本的快照。`session_id` 变化时，Wrist 先清除旧版本号，再接受新会话快照。
- Indication 的链路确认只表示 BLE 已送达。业务接受必须等待含相同 `ack_id` 的 Hub State。
- 正常连接下，发送后 2 秒内未收到业务确认，Wrist 进入 `synchronizing` 并主动读取 Hub State，不自动重发。只有 BLE 已断开或状态读取失败时才进入 `reconnecting`。
- Hub 在准备和过渡阶段至少每秒发送一次校正后的 `eta_ms`。Wrist 可以在两次快照之间本地递减。
- 2.5 秒没有收到新快照时，Wrist 停止倒计时，显示“状态同步中”。

## 10. 连接与恢复

### 10.1 发送前离线

主控制页显示“Hub 未连接”，能量和风格入口禁用。Wrist 不保存离线指令。

### 10.2 执行中断线

Wrist 保留最后一次目标信息，停止倒计时并显示“正在重新连接”。重连后先读取 Hub State，再决定显示执行页、完成页或空闲页。Wrist 不根据断线前的时间推断结果。

### 10.3 Hub 忙碌

Hub 返回：

```json
{
  "phase": "rejected",
  "ack_id": 44,
  "locked": true,
  "error": "busy"
}
```

同一快照还要包含 Hub 正在执行的 `current`、`target` 和 `eta_ms`。Wrist 直接显示该任务，不创建新的本地任务。

V0.1 规定以下错误码：

| 错误码 | 含义 | Wrist 行为 |
|---|---|---|
| `busy` | Hub 正在执行另一项切换 | 显示现有任务和剩余时间 |
| `invalid_energy` | 能量不在 1–5 范围 | 显示指令无效，返回选择页 |
| `unknown_style` | Hub 不支持该风格 ID | 刷新 Catalog，返回风格页 |
| `version_mismatch` | 协议版本不兼容 | 禁用控制并提示更新固件 |
| `internal_error` | Hub 无法完成操作 | 显示失败，等待最新状态快照 |

### 10.4 Hub 重启

Hub 重启后使用新的会话 ID，并从持久化或音乐引擎读取当前实际状态。Wrist 发现会话变化后清除旧的命令和倒计时缓存，完全采用新快照。

`session_id` 是 Hub 每次进程启动时生成的 64 位随机值，传输时编码为 16 位十六进制字符串，避免不同语言处理 64 位整数时丢失精度。

## 11. 软件模块边界

Wrist 固件按职责拆分：

```text
app_state
├── 保存最新 Hub 快照、当前页面和本地 sending 状态
│
ui
├── 主控制页
├── 海报轮播组件
├── 执行与完成页
└── 连接、错误和电量提示
│
flow_protocol
├── CBOR 编解码
├── 字段校验
├── command_id / revision / session_id 处理
└── 超时规则
│
ble_service
├── 广播、配对和连接生命周期
├── GATT Characteristics
└── 标准 Battery / Device Info Service
│
power
├── BOOT 按键
├── 屏幕亮度和熄屏
└── AXP2101 电量与充电状态
```

UI 不直接调用 BLE API。用户操作先生成领域命令，由 `flow_protocol` 编码后交给 `ble_service`。收到数据时顺序相反：BLE 交给协议层校验，协议层更新 `app_state`，UI 只响应状态变化。

RK3588 Hub 侧至少拆分为 BlueZ 连接管理、协议编解码、命令路由和音乐引擎适配四层。BLE 回调不能直接执行耗时的选曲或音频任务。

## 12. 性能和资源原则

- LVGL 动画以 200–350 ms 的位移、缩放和颜色切换为主。
- 避免大面积实时透明、模糊和逐像素滤镜。
- 海报滑动时保持稳定帧率，滑动结束后再加载下一张非相邻插画。
- 触摸区域至少覆盖完整海报主体。返回按钮和状态入口不使用小于 44×44 逻辑像素的点击区域。
- 屏幕唤醒到主控制页可操作不超过 500 ms；BLE 正在重连时先显示缓存状态和明确的连接提示。

## 13. 测试范围

### 13.1 UI

- BOOT 短按可以稳定唤醒，长按或抖动不会连续打开页面。
- 能量 1 和 5 不发生越界滑动；风格轮播可以循环。
- 滑动不会误触发送，点击海报只发送一次。
- 当前值点击不发送。
- 暖白界面在室内、舞池低光和不同亮度下可读。
- 执行页中风格和倒计时比能量、BPM 更醒目。
- 完成页只在 Hub 返回 `completed` 后出现。

### 13.2 BLE 和协议

- 正常能量切换和正常风格切换。
- Hub 忙碌时拒绝新命令。
- 相同 `command_id` 重复到达时只执行一次。
- 乱序、重复和旧 `revision` 快照不会回滚 UI。
- 业务确认超时、倒计时更新超时和 BLE 断线分别触发正确页面。
- 执行中断线重连后，以 Hub 状态恢复。
- Hub 重启产生新的 `session_id` 后，Wrist 清除旧任务。
- 非法能量、未知风格、损坏 CBOR 和协议版本不匹配都有明确错误。
- MTU 协商失败时，Hub State 和 Catalog 仍可通过 Long Write 传输。

### 13.3 现场验证

- 用户从熄屏开始，能在 3–5 秒内完成一次能量或风格操作。
- 舞动、手汗和快速触摸下不出现明显误发。
- 在 10–20 秒切换期间，用户能说清当前风格、目标风格和剩余时间。
- Hub 离线或忙碌时，用户不会误认为指令已经执行。

## 14. 验收标准

V0.1 通过以下条件验收：

1. 五档能量和四种风格都能通过同一套海报操作发送到 RK3588。
2. 正常连接下，用户点击后 1 秒内看到 Hub 的业务确认。
3. Hub 执行期间不能发送第二条命令。
4. 执行页持续显示当前/目标风格和 Hub 提供的切换倒计时，能量与 BPM 作为次要信息显示。
5. BLE 断开、Hub 忙碌、协议错误和超时均不会产生静默失败或延迟执行。
6. Hub 是业务状态的唯一真相来源；手环不会自行宣布切换成功。
7. 真机操作从唤醒到发出指令的中位时间不超过 5 秒。

## 15. 资料

- [Waveshare ESP32-S3-Touch-AMOLED-2.06 产品文档](https://docs.waveshare.net/ESP32-S3-Touch-AMOLED-2.06)
- [Waveshare ESP-IDF 开发说明](https://docs.waveshare.net/ESP32-S3-Touch-AMOLED-2.06/ESP-IDF)
- [Waveshare 官方示例仓库](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-2.06)
