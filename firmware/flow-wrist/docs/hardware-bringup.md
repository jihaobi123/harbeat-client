# Flow Wrist 硬件启动记录

## 开发工具

- 开发电脑：Apple Silicon Mac（arm64）
- ESP-IDF：5.5.5
- Python：3.12.11（ESP-IDF 隔离环境）
- CMake：3.30.2
- Ninja：1.12.1
- 目标芯片：ESP32-S3
- 开发板：Waveshare ESP32-S3-Touch-AMOLED-2.06
- BSP：`waveshare/esp32_s3_touch_amoled_2_06` 2.0.0
- LVGL：9.5.0

Homebrew 当前无法识别 macOS 26.4，因此 EIM 0.18.0 使用 Espressif 官方的 Apple Silicon 独立包安装在 `~/.local/bin/eim`。ESP-IDF 通过下面的官方激活脚本进入当前终端：

```bash
source "$HOME/.espressif/tools/activate_idf_v5.5.5.sh"
```

## USB 连接

开发板的原生 USB 串口应显示为 `/dev/cu.usbmodem*`。如果没有出现：

1. 确认使用支持数据传输的 USB-C 线。
2. 按住 BOOT 后重新插入 USB-C。
3. 等串口出现后松开 BOOT。

截至 2026-08-26，本机还未检测到 `/dev/cu.usbmodem*`，因此可以完成主机测试和固件编译，但烧录与屏幕实机验收需要接入开发板。

## BSP 共享资源

- 触摸与电源设备共用 GPIO14 / GPIO15 上的 I²C 总线。
- 应用只通过 `bsp_i2c_get_handle()` 获取现有总线，不得再创建一个 I²C master bus。
- 屏幕亮度使用 `bsp_display_brightness_set()`，熄屏使用 `bsp_display_backlight_off()`。
