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
