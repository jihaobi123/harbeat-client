# Flow Wrist BLE 联调

## 广播与角色

- Wrist：BLE Peripheral / GATT Server
- RK3588 Hub：BLE Central / GATT Client
- 广播名：`FLOW-WRIST-XXXX`
- 配对：LE Secure Connections、Just Works、Bonding

自定义服务：

```text
464C4F57-0001-4F57-8101-000000000001
```

| 特征 | UUID 末尾 | 属性 |
|---|---:|---|
| Command | `0002` | Indicate |
| Hub State | `0003` | Read、Write with response |
| Catalog | `0004` | Read、Write with response |

另外提供标准 Battery Service `0x180F` 和 Device Information Service `0x180A`。

## Hub 初始化顺序

连接后必须依次完成：

1. 发现服务并完成 Pair，确认链路已经加密。
2. 订阅 Command Indication。
3. 写入完整 Catalog。
4. 写入完整 Hub State。
5. 此时 Wrist 才开放能量和风格控制。

完整字段和错误处理以 [ble-protocol-v1.md](ble-protocol-v1.md) 为准。

Hub State 和 Catalog 可以使用 GATT Long Write。建议协商 MTU 247，但实现不能把 MTU 247 当作前提。

## 最小 Catalog

以下 JSON 仅用于说明字段，链路实际传 CBOR：

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

## 联调验收

- 未收到 Catalog 和首次 Hub State 时，控制入口不可用。
- 点击能量或风格后只产生一次 Command Indication。
- Indication 确认只代表 BLE 送达；页面必须等待含对应 `ack_id` 的 Hub State。
- `locked: true` 时再次触摸不会产生第二条命令。
- `error: "busy"` 时继续显示 Hub 当前任务和倒计时。
- 重复或更旧的 `revision` 不会让页面回退。
- 断线后停止控制并重新广播；重连后重新同步 Catalog 和 Hub State。
- Hub 重启并更换 `session_id` 后，Wrist 接受新的 revision 序列。

## Mac 模拟 Hub

建议使用 Python 3.12。macOS 26 需要 Bleak 3 和 PyObjC 12，旧版 PyObjC 会把已开启的蓝牙误报为关闭。

```bash
cd "/Users/jihaobi/Documents/New project/firmware/flow-wrist"
python3 -m venv .venv-hub
.venv-hub/bin/pip install -r tools/requirements-hub-mock.txt
.venv-hub/bin/python tools/flow_hub_mock.py --transition-seconds 12 --verbose
```

手环连接页应依次显示：

```text
FINDING THE HUB.
SECURING THE LINK.
SYNCING THE ROOM.
READING THE FLOOR.
```

最后进入首页并显示绿色 `● HUB`。

macOS CoreBluetooth 没有显式 Pair API，正常情况下会在首次访问加密特征时自动配对。如果系统只返回 `Insufficient Encryption`，请改用 RK3588/BlueZ、Android nRF Connect 或 iOS Central 做安全链路验收，不要为了绕过桌面系统限制而关闭固件的加密权限。

## 当前硬件验收边界

2026-08-27 已在 ESP32-S3 真机完成：GATT 注册、广播、Mac 扫描与连接、ATT MTU 247、Command indication 订阅、断线后恢复广播。此前的 GATT 重启问题已经定位为 Command characteristic 缺少 NimBLE 必需的 access callback，并已修复。

本机 macOS 26.4 的 CoreBluetooth 在加密读写时返回 `Insufficient Encryption`，没有继续弹出自动配对，因此 Catalog、首次 snapshot、业务 Command 和重连恢复仍列为明天 RK3588/BlueZ 的必测项。正式固件保持 encrypted Read/Write，不降级为明文测试。
