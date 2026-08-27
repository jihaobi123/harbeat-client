# Flow Wrist ↔ RK3588 BLE 协议 v1

版本：1.0
日期：2026-08-27
角色：Flow Wrist 是 BLE Peripheral / GATT Server，RK3588 Hub 是 Central / GATT Client。

## 先看这一段

Hub 连上手环后，按下面的顺序做：

1. 建立 LE Secure Connections，允许 Just Works，保存 bond。
2. 订阅 Command characteristic 的 indication。
3. 向 Catalog characteristic 写入完整目录。
4. 向 Hub State characteristic 写入首次 snapshot。
5. 收到手环命令后，先回 `accepted` snapshot，再执行选曲和切歌。

Catalog、Hub State 或 indication 订阅缺一项，手环都不会开放控制。建议协商 ATT MTU 247；双方仍须支持 GATT Long Write，不能假定每个 CBOR 包都能塞进一个 ATT packet。

## GATT

| 名称 | UUID | Wrist 视角 | 权限 | 最大长度 |
|---|---|---|---|---:|
| Flow Service | `464C4F57-0001-4F57-8101-000000000001` | Primary service | - | - |
| Command | `464C4F57-0001-4F57-8101-000000000002` | Wrist → Hub | Indicate | 192 B |
| Hub State | `464C4F57-0001-4F57-8101-000000000003` | Hub → Wrist | encrypted Read/Write with response | 512 B |
| Catalog | `464C4F57-0001-4F57-8101-000000000004` | Hub → Wrist | encrypted Read/Write with response | 512 B |
| Battery Service | `0x180F` | 标准服务 | Read/Notify | 1 B |
| Device Information | `0x180A` | 标准服务 | Read | UTF-8 |

广播名是 `FLOW-WRIST-XXXX`，末四位来自设备地址。广播包包含完整 Flow Service UUID。

Command 使用 indication，不用 notification。链路层确认只说明 Hub 收到了字节，不代表音乐系统接受了请求。业务确认必须看 snapshot 的 `ack_id`。

## 编码规则

- 所有自定义 characteristic 都传 CBOR map。
- map key 是 UTF-8 text string；key 顺序不影响解析。
- 整数使用 CBOR unsigned integer。
- 不使用 float。
- `v` 当前固定为 `1`。
- 单条消息最大 512 B；Command 最大 192 B。
- `session_id` 是 16 个十六进制字符。Hub 每次进程启动生成新值。
- 同一 `session_id` 内，`revision` 必须严格递增。

手环收到 `v != 1` 的 Catalog 后进入 `UPDATE REQUIRED.`，不会开放能量或风格控制。

## Catalog

Hub 每次连接或重连都要重发完整 Catalog。

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

v1 必须包含 1–5 五档能量和上述四个 style id。`label`、`order` 由 Hub 保存，当前手环只校验并使用 `id`。

## Command：Wrist → Hub

统一 envelope：

```json
{
  "v": 1,
  "kind": "command",
  "id": 42,
  "op": "set_energy",
  "value": 5
}
```

字段约束：

| 字段 | 类型 | 约束 |
|---|---|---|
| `v` | uint | 必须为 1 |
| `kind` | text | 必须为 `command` |
| `id` | uint32 | 非 0；由手环生成，重启后随机起点，随后递增 |
| `op` | text | `set_energy` 或 `set_style` |
| `value` | uint/text | 能量为 1–5；风格为 Catalog 中的 id |

能量 4 → 5，`id = 42`：

```text
a5 61 76 01 64 6b 69 6e 64 67 63 6f 6d 6d 61 6e
64 62 69 64 18 2a 62 6f 70 6a 73 65 74 5f 65 6e
65 72 67 79 65 76 61 6c 75 65 05
```

hiphop → breaking，`id = 43`：

```text
a5 61 76 01 64 6b 69 6e 64 67 63 6f 6d 6d 61 6e
64 62 69 64 18 2b 62 6f 70 69 73 65 74 5f 73 74
79 6c 65 65 76 61 6c 75 65 68 62 72 65 61 6b 69
6e 67
```

Hub 必须按 `session_id + command.id` 去重。重复 indication 可以重发当前 snapshot，但不能再次安排切歌。

## Snapshot：Hub → Wrist

```json
{
  "v": 1,
  "kind": "snapshot",
  "session_id": "8f3a19d04b7c221e",
  "revision": 18,
  "ack_id": 42,
  "phase": "preparing",
  "locked": true,
  "eta_ms": 9000,
  "current": {"energy": 4, "style": "hiphop", "bpm": 96},
  "target": {"energy": 5, "style": "hiphop", "bpm": 102},
  "error": null
}
```

| 字段 | 说明 |
|---|---|
| `session_id` | Hub 本次运行的会话。进程重启后换新值，Wrist 会重置 revision 判定。 |
| `revision` | 同一会话内严格递增。重复或更小的值会被 Wrist 丢弃。 |
| `ack_id` | 对应 Command id；没有待确认命令时为 0。 |
| `phase` | `idle`、`accepted`、`preparing`、`transitioning`、`completed`、`rejected`、`error`。 |
| `locked` | `true` 时 Wrist 禁止发送新命令。 |
| `eta_ms` | 距离整段切换完成的估计毫秒数。完成或无任务时为 0。 |
| `current` | 现场当前真正播放的能量、风格和 BPM。 |
| `target` | 目标状态；idle 时可以为 `null`。 |
| `error` | 正常时为 `null` 或空字符串；失败时使用下方错误码。 |

推荐时序：

| 时间 | phase | locked | eta_ms | 用途 |
|---:|---|---:|---:|---|
| 收到命令后 0–500 ms | `accepted` | true | 10000–20000 | 业务 ACK，手环立即进入执行页 |
| 选曲和分析阶段 | `preparing` | true | 单调递减 | 显示目标和倒计时 |
| 混音/切歌开始 | `transitioning` | true | 单调递减 | 现场正在变化 |
| 音乐切换完成 | `completed` | false | 0 | `current` 必须等于最终目标 |
| 完成页之后 | `idle` | false | 0 | 正常待命，可省略这一步 |

`accepted` 到 `completed` 的目标是 10–20 秒。`eta_ms` 是体验反馈，不要求绝对精准，但不能在同一任务中反向增加。当前手环以风格和剩余时间为主，BPM 与能量是次级信息。

## 忙碌、错误与超时

首版错误码：

| error | 使用场景 |
|---|---|
| `busy` | 上一段切歌还没完成 |
| `unsupported` | op 或 value 不受支持 |
| `no_candidate` | 曲库没有符合条件的下一首 |
| `engine_error` | 播放/混音引擎失败 |
| `protocol_error` | CBOR 或字段不符合 v1 |

Hub 如果收到不该出现的第二条命令，回 `phase: rejected`、`locked: true`、`error: "busy"`，同时继续提供当前任务的 target 和 eta。手环会提示上一阶段尚未切完，并保持原倒计时。

如果 Hub 已接受命令，但两秒内没有更新 snapshot，手环仍保留发送中的状态；Hub 应在恢复后用相同 `ack_id` 和更高 `revision` 接续。不要靠重发音乐操作修复 UI。

## 断线与重连

断线后，Wrist 保留最后一个可信 snapshot、禁用触控和 IMU 发送，并重新广播。Hub 重连时重新走完整顺序：加密、订阅、Catalog、snapshot。

- Hub 进程没有重启：沿用原 `session_id`，revision 继续递增。
- Hub 进程重启：换新 `session_id`，revision 可以从 1 开始。
- 重连时仍在切歌：首次 snapshot 直接写当前 phase、target 和 eta，Wrist 会恢复执行页。
- 重连时任务已经完成：首次 snapshot 写 `completed` 或 `idle`，`current` 写现场真实状态。

## RK3588 / BlueZ 实现检查

1. 扫描完整 Service UUID 或 `FLOW-WRIST-` 名称前缀。
2. Connect 后先 Pair；Hub 端保存 bond，避免每次重复配对。
3. Subscribe Command indication，确认 CCCD 已写成功。
4. Write Catalog with response，等待成功。
5. Write initial snapshot with response，等待成功。
6. 收到 Command 后先校验 v/kind/id/op/value，再做 id 去重。
7. 500 ms 内写 accepted snapshot。
8. 切歌期间按 phase 写 snapshot；每次 revision +1。
9. completed 时先更新 current，再把 locked 设为 false。

Mac 和 RK3588 共用的参考实现是 [`tools/flow_hub_mock.py`](../tools/flow_hub_mock.py)。它不是正式音乐引擎，但 GATT 顺序、CBOR 字段、ACK 和 phase 时序与本协议一致。
