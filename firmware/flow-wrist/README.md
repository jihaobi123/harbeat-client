# Flow Wrist V0.1 固件

这是 Flow Wear 手环端的首版 ESP-IDF 工程，面向 Waveshare ESP32-S3-Touch-AMOLED-2.06。当前包含：

- 暖纸白插画风 LVGL 界面；
- 五档能量与 HIPHOP、BREAKING、FUNK、LOCKING 风格选择；
- 发送、执行中双唱片、完成、忙碌和断线状态；
- CBOR v1 协议与 Hub 权威状态归并；
- NimBLE Peripheral / GATT Server；
- BOOT 短按唤醒、自动降亮度与熄屏；
- AXP2101 电量读取和标准 BLE Battery Service；
- 无需 RK3588 的本地 Hub 流程模拟器。
- QMI8658 无触控手势控制（实验版，需完成佩戴校准）。

## Mac 开发环境

```bash
source "$HOME/.espressif/tools/activate_idf_v5.5.5.sh"
cd "/Users/jihaobi/Documents/New project/firmware/flow-wrist"
```

运行 Mac 主机测试：

```bash
./tests/host/run.sh
```

## 构建演示版

默认开启本地 Hub 模拟器，适合先验收完整 UI 流程：

```bash
idf.py -B build build
```

## 构建真实 BLE 版

真实 BLE 版使用独立配置，避免覆盖演示版：

```bash
idf.py -B build-ble \
  -D SDKCONFIG=build-ble/sdkconfig \
  -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.ble.defaults' \
  reconfigure build
```

接入开发板后再烧录：

```bash
serial_port="$(find /dev -maxdepth 1 -name 'cu.usbmodem*' -print -quit)"
test -n "$serial_port"
idf.py -B build-ble -p "$serial_port" flash monitor
```

不要在没有找到串口时跳过 `test` 强行烧录。板级检查见 [hardware-bringup.md](docs/hardware-bringup.md)，Hub 联调步骤见 [ble-test.md](docs/ble-test.md)。

RK3588 对接先读 [BLE 协议 v1](docs/ble-protocol-v1.md)。[`tools/flow_hub_mock.py`](tools/flow_hub_mock.py) 提供相同的 Catalog、snapshot、命令 ACK 和 10–20 秒切换状态机；Linux/BlueZ 可完成全链路测试。部分 macOS 版本不会为命令行 CoreBluetooth 客户端触发自动配对，遇到这种情况按 [ble-test.md](docs/ble-test.md) 的验收边界处理。

如果要把项目交给另一位开发者或 AI，直接发送 [Flow Wrist V0.1 开发接手手册](docs/AI-DEVELOPMENT-HANDOFF.md)。其中包含产品边界、代码结构、触控与手势、BLE 对接顺序、烧录方法、已验证结果和下一步清单。
