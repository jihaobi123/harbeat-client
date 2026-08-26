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

1. 发现服务并订阅 Command Indication。
2. 写入完整 Catalog。
3. 写入完整 Hub State。
4. 此时 Wrist 才开放能量和风格控制。

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

## 当前硬件验收边界

主机测试和两种配置的固件构建已经完成。开发板尚未接入这台 Mac，因此广播包、配对、Long Write、屏幕布局、BOOT 实际电气行为和 AXP2101 电量值仍需上板确认。
