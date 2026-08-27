# Flow Wrist V0.1 开发接手手册

更新日期：2026-08-27
当前阶段：ESP32-S3 手环功能原型；RK3588 Hub 安全链路待联调

这份文档给下一位开发者或 AI 使用。先按“已验证 / 待验证”的边界工作，不要把模拟结果写成真机全链路结果。

## 1. 产品目标

Flow Wrist 用于舞池现场控制。用户发现舞者水平或现场气氛发生变化时，点亮手环，选择新的能量或风格并立即发送。手环操作应在 3–5 秒内完成，Hub 在 10–20 秒内完成选曲和音乐切换。

首版范围：

- 能量：1–5 五档；
- 风格：`hiphop`、`breaking`、`funk`、`locking`；
- 选择后立即发送，不增加二次确认弹窗；
- Hub 尚未完成上一段切歌时，禁止再次发送，并提示上一阶段仍在执行；
- BPM 和调性暂时不做手动调节。BPM 只作为 Hub 状态信息显示；
- 暖纸白底、低像素插画人物、黑色粗线和黄/蓝/粉/绿点缀是已确定的视觉方向。

## 2. 硬件与开发环境

| 项目 | 当前配置 |
|---|---|
| 开发板 | Waveshare ESP32-S3-Touch-AMOLED-2.06 |
| MCU | ESP32-S3，240 MHz，8 MB PSRAM |
| 屏幕与触控 | 使用 Waveshare BSP 2.0.0 |
| UI | LVGL 9.5.0 |
| IMU | QMI8658，I²C 地址 `0x6B` |
| 电源 | AXP2101，I²C 地址 `0x34` |
| 蓝牙 | NimBLE，手环为 Peripheral / GATT Server |
| 本机工具链 | macOS，ESP-IDF 5.5.5 |
| 当前串口 | `/dev/cu.usbmodem1101`，重新插拔后可能变化 |

工程路径：

```text
/Users/jihaobi/Documents/New project/firmware/flow-wrist
```

激活环境：

```bash
source /Users/jihaobi/.espressif/tools/activate_idf_v5.5.5.sh
cd "/Users/jihaobi/Documents/New project/firmware/flow-wrist"
```

## 3. 用户操作

### 触屏

1. 首页点 `ENERGY` 或 `STYLE` 卡片。
2. 在二级页左右拖动。左滑看下一项，右滑看上一项。
3. 松手后页面用 140 ms 动画吸附；横向位移达到 52 px 或速度达到 720 px/s 才切换一项。
4. 点当前预览卡片立即发送。点正在使用的项目不会重复发送。

能量到 1 或 5 后不循环；风格列表首尾循环。

找不到 Hub 时，连接页可以点中央的 `VIEW HOME` 进入离线预览主页，后台仍会搜索 Hub。首次启动还没有可信状态时，主页以 `03 / 05`、`HIPHOP`、`96 BPM` 渲染完整人物插画，并标成 `PREVIEW`；这些值只是 UI 示例，不代表现场状态。如果之前同步过，则显示最后一次可信状态。

离线时可以打开 `ENERGY` 和 `STYLE`，左右滑动浏览全部选项，也可以用左上角返回键回主页。点击任意选项只显示 `CONNECT HUB TO SEND`，不会生成 BLE 命令、缓存选择或在重连后自动发送。Hub 连上并写入首次 Snapshot 后，界面以 Hub 状态为准，离线预览不会覆盖现场数据。

能量页和风格页的左上返回键为 64 × 52 px，并向屏幕中心内缩，避免圆角削弱触摸范围。

### 点亮与按键

- 触摸屏幕或短按 BOOT 都会记录活动并恢复亮度；
- 普通页面无操作 10 秒后熄屏；
- 音乐切换页保持可见，5 秒后只降亮度；
- RST 只用于硬件复位，不作为应用功能键。

### 无触控手势（实验版）

手势和触控使用同一条命令路径，触控优先。当前顺序：

1. 移动手腕后稳定 500 ms，进入 READY；
2. 3 秒内做一次左右相反方向的 roll，解锁手势；
3. 向上 flick 进入能量，向下 flick 进入风格；
4. 左右 roll 每次预览一项；
5. 稳定 800 ms 显示确认，稳定到 1.1 秒才发送。

BLE 未就绪、Hub 锁定、触摸屏幕、超时或动作方向错误都会取消。该功能已经通过合成轨迹测试和 IMU 真机采样测试，但还没有完成佩戴、走路和 10 分钟舞动误触校准。详细门槛见 [imu-gesture-test.md](imu-gesture-test.md)。

## 4. 运行结构

```text
触摸 ───────────────┐
                    ├─ flow_input / app state ─ CBOR Command ─ BLE indication ─ RK3588
QMI8658 ─ 手势引擎 ─┘                                  │
                                                       │
LVGL UI ← app state ← Catalog + Snapshot ← GATT write ─┘
```

关键目录：

| 路径 | 作用 |
|---|---|
| `main/app_main.c` | 队列、UI、BLE、IMU、电源的总入口 |
| `components/flow_ui/` | 首页、轮播、连接、切换和手势反馈 UI |
| `components/flow_core/` | 页面状态、snapshot 归并、输入协调 |
| `components/flow_protocol/` | Command / Catalog / Snapshot 的 CBOR 编解码 |
| `components/flow_ble/` | NimBLE GATT Server 与连接就绪状态 |
| `components/flow_imu/` | QMI8658 125 Hz 采样任务 |
| `components/flow_gesture/` | 不依赖 ESP-IDF 的手势状态机 |
| `components/flow_power/` | BOOT 唤醒、亮度和电量 |
| `components/flow_simulator/` | 无 RK3588 时的本地 Hub 状态模拟 |
| `tools/flow_hub_mock.py` | Mac / Linux BLE Central 参考实现 |
| `tests/host/` | Mac 上可快速运行的逻辑测试 |

LVGL 只在它自己的上下文里更新。其他任务通过 FreeRTOS 队列提交状态，不要从 BLE 或 IMU 回调直接操作 LVGL 对象。

## 5. BLE 对接摘要

手环广播名为 `FLOW-WRIST-XXXX`。当前真机是 `FLOW-WRIST-F892`，设备变化后末四位也会变化。

| 接口 | UUID | 方向 |
|---|---|---|
| Flow Service | `464C4F57-0001-4F57-8101-000000000001` | 服务 |
| Command | `464C4F57-0001-4F57-8101-000000000002` | Wrist → Hub，Indicate |
| Hub State | `464C4F57-0001-4F57-8101-000000000003` | Hub → Wrist，加密读写 |
| Catalog | `464C4F57-0001-4F57-8101-000000000004` | Hub → Wrist，加密读写 |

RK3588 连接后必须依次执行：

1. Connect；
2. Pair，建立 LE Secure Connections 并保存 bond；
3. 订阅 Command indication；
4. 写完整 Catalog；
5. 写首次 Snapshot。

五步都完成后，手环才进入 READY。推荐 ATT MTU 247，同时要支持 GATT Long Write。

手环只发送两种操作：

```json
{"v":1,"kind":"command","id":42,"op":"set_energy","value":5}
{"v":1,"kind":"command","id":43,"op":"set_style","value":"breaking"}
```

Hub 必须在 500 ms 内回带相同 `ack_id` 的 `accepted` snapshot，然后按 `preparing`、`transitioning`、`completed` 更新。执行期间 `locked` 保持 `true`，`eta_ms` 单调递减。`completed` 时先把 `current` 更新为真实播放状态，再解除锁定。

完整字段、错误码、去重和重连规则见 [ble-protocol-v1.md](ble-protocol-v1.md)。不要为了绕过桌面系统的配对限制而去掉加密权限。

## 6. 构建、测试与烧录

快速测试：

```bash
./tests/host/run.sh
python3 tests/host/test_hub_mock.py
python3 tests/host/test_dancer_assets.py
```

构建本地模拟版：

```bash
idf.py -B build-sim build
```

构建真实 BLE 版：

```bash
idf.py -B build-ble build
```

确认串口并烧录：

```bash
ls /dev/cu.usbmodem*
idf.py -B build-ble -p /dev/cu.usbmodem1101 flash
idf.py -B build-ble -p /dev/cu.usbmodem1101 monitor
```

监视器用 `Ctrl+]` 退出。正常启动至少应看到：

```text
Display and touch initialized
Advertising as FLOW-WRIST-XXXX
BLE service started
QMI8658 initialized successfully
QMI8658 sampling at 125 Hz (accel +/-8g, gyro +/-512dps)
```

## 7. 当前验证结果

截至 2026-08-27：

| 项目 | 结果 |
|---|---|
| 7 组 C 主机测试 | 通过 |
| Hub 状态机与人物资源 Python 测试 | 通过 |
| 模拟版构建 | 通过，固件约 0.87 MB |
| BLE 版构建 | 通过，固件约 1.14 MB |
| 最终 BLE 版烧录 | 通过，串口 `/dev/cu.usbmodem1101` |
| 屏幕、触控、电源服务启动 | 通过 |
| BLE 广播、Mac 扫描/连接、MTU 247、订阅 indication、断线重播 | 通过 |
| QMI8658 初始化与 125 Hz 连续采样 | 通过，观察 10 秒无读取错误或重启 |
| Catalog / Snapshot / Command 加密全链路 | 待 RK3588 / BlueZ 验证 |
| 手势佩戴和舞动误触校准 | 待现场验证 |

本机 macOS 26.4 的 CoreBluetooth 在访问加密特征时返回 `Insufficient Encryption`，没有触发自动配对。因此安全业务链路必须在 RK3588 / BlueZ 上完成，固件侧不降级。

## 8. 明天 RK3588 联调清单

1. 用 BlueZ 显式 Pair，确认 bond 保存成功；
2. 按协议顺序完成 indication、Catalog、首次 Snapshot；
3. 手环首页出现绿色 `● HUB`；
4. 分别发送一次能量和风格命令，确认每次只收到一个 Command；
5. 500 ms 内回 `accepted`，10–20 秒内走完切换状态；
6. `locked: true` 时再次点击，Hub 不应收到第二条命令；
7. 测试 `busy`、断线重连和 Hub 重启后的新 `session_id`；
8. 完成后把结果补进 [ble-test.md](ble-test.md)。

可以先在 RK3588 上运行：

```bash
python3 -m venv .venv-hub
.venv-hub/bin/pip install -r tools/requirements-hub-mock.txt
.venv-hub/bin/python tools/flow_hub_mock.py --transition-seconds 12 --verbose
```

## 9. 给下一位 AI 的工作边界

- 先读本文件和 [ble-protocol-v1.md](ble-protocol-v1.md)，再改代码；
- 保留暖纸白和四个人物插画资产，不要换成重型全屏动画；
- 动效优先使用位移、透明度和 140 ms 左右的 LVGL 动画，避免大图逐帧动画；
- 触控始终高于手势，Hub `locked` 或 BLE 非 READY 时不得发送；
- 离线轮播只能浏览；不要加入待发送队列，也不要在重连后补发离线选择；
- 所有业务状态以 Hub Snapshot 为准，BLE indication 成功不等于切歌成功；
- 协议 v1 的 UUID、字段和四个 style id 已冻结；如需改动，应升协议版本；
- 不要把 macOS 配对失败解释成 ESP32 固件失败，也不要关闭加密；
- 当前仓库还有其他模块的未提交改动，修改或提交时只处理 `firmware/flow-wrist` 范围。

建议下一项任务：先完成 RK3588 / BlueZ 安全链路联调，再做 10 分钟佩戴误触测试。两项通过后，才继续 BPM 或调性控制。
