# 给戒指、手环负责人的接入任务

## 先说结论

混音端已留好开始、暂停、切歌、风格选择和手势音效入口。请在 **RK 上的蓝牙网关**接入，不把混音逻辑写入戒指或手环。先用 EDM 8 首联调。

职责链路：戒指/手环识别动作 → BLE 网关收到事件 → 网关转换一次 HTTP 请求 → RK 混音端安排播放/转场 → 网关读取实际状态并反馈设备。混音端负责找候选点、变速和淡变；你不需要计算出入歌时间。

入口：RK 本机 `http://127.0.0.1:9130/v1/device-events`，方法 POST，UTF-8 JSON。完整字段见 [接口说明](CONTROL_INTERFACE_V1.md)。从手机访问其自己的 127.0.0.1 无效。

## 1. 你需要完成的映射

| 设备意图 | action | params | 注意 |
| --- | --- | --- | --- |
| 手环开始/继续 | start | {} | 暂停后继续原位置，不重播 |
| 手环暂停/停止键 | pause（也兼容 stop） | {} | 本版 stop 就是暂停，不清空 |
| 手环下一首 | next | {} | 最近的未来候选点接歌，不是立即硬切 |
| 手环切换到 EDM | set_style | {"style_id":"EDM"} | 其他风格明确报未就绪，不自动替换为 EDM |
| 戒指向前出拳 | gesture | {"gesture_id":"punch_forward"} | 当前对应 snare_impact |
| 戒指向上甩动 | gesture | {"gesture_id":"flick_up"} | 当前对应 air_horn |
| 戒指侧向挥动 | gesture | {"gesture_id":"swipe_side"} | 当前对应 beat_stutter |
| 戒指手腕转动 | gesture | {"gesture_id":"wrist_roll"} | 当前对应 bass_drop |

上表是**逻辑动作**，不是已确认的固件 gesture 数值或按钮编号。请你确认现有分类结果/键码，再维护一个明确映射表；不认识的事件拒绝并记日志，不按名称猜测。若设备只有一个播放切换键，请根据最新实际 `engine.paused` / `engine.playing` 决定 pause 或 start，不发送本版不存在的 toggle。

旧协议中的 hiphop、breaking、funk、locking 和 energy 1–5 不能直接套进 EDM 本版。不要在界面显示“切换成功”来掩盖 `style_assets_not_ready`。

## 2. 每次动作怎么发

手环切歌的请求结构如下。实际使用时替换设备和事件标识：

```json
{
  "schema_version": "harbeat.control.v1",
  "source": "wrist_gateway",
  "device_id": "wrist-001",
  "boot_id": "gateway-boot-unique-id",
  "event_id": "123",
  "action": "next",
  "params": {}
}
```

戒指只需把 source 改为 `ring_gateway`，device_id 使用戒指标识，action/params 按上表填写。不要传物理 IMU 数据给此接口；姿态识别仍由你负责。

同一动作因重连/超时重发时，四个标识和动作内容保持不变。新动作使用新 event_id。保留“设备原事件 → HTTP 事件”的映射，别把一次 BLE 重传当作新按键。接口只保留当前控制进程最近 512 条成功请求，重启或记录淘汰后不保证去重；未确认动作不能在重启后盲目重放。

## 3. 别阻塞 BLE，也别把接收成功当播放成功

HTTP 首次 start 可能加载数秒；应放在工作队列/异步任务里，不在 BLE 接收回调中同步等待。每台设备保持操作顺序，设置有界队列，防止扫描/手势洪水挤满控制服务。建议 HTTP 超时 35 秒，超时后先读 state 再决定是否用原事件重试。

BLE 收到包、网关入队、混音命令接受、转场完成是不同阶段：

- 可以按既有 BLE 约定反馈“收到/排队”，但不能把它说成已执行混音。
- HTTP `ok:true` 才能报告混音端已接受；next 的 `scheduled` 仍只是排程成功。
- `transitioning` 表示正在交接；完成后当前 track_id 变更、pending 清空、events 出现 completed。
- 400 修正请求；409 根据 error 与 state 提示忙/未就绪等；503 表示控制链路不可用。所有失败都记录并反馈，不能吞掉后返回成功。

设备仓库的旧 [engine-ipc-v1](https://github.com/zhanghangming-gif/harbeat-wear/blob/0922af956ba23105762334596fa194f1802c818a/contracts/engine-ipc-v1.md) 约定的是 400ms 预算内的 NDJSON 交互和特定状态流；本 HTTP 服务**不保证这些时延和回包形式**。不能仅换 URL 就宣称旧协议兼容。要改 BLE ACK/共享状态字段，在 harbeat-wear 另开 shared 分支评审；本次没有替你改这些协议。

建议每 250–500ms 查询一次 `/v1/state`；读取 `source_position_sec` 显示原曲位置，不用 `engine.position_sec` 去定位原曲段落。所有曲内时间为秒；预处理 manifest 内的毫秒需显式换算。

## 4. 只保留一条播放控制链

现有旧网关可能直接播放旧歌曲/音效。本目录**没有**自动接管或关闭旧网关。你接入新接口时必须将对应动作切到新目标，不能新 HTTP 和旧 Cypher 入口双发；否则会重复响、跳到旧歌或让新会话失去控制。

建议增加清晰的网关配置开关选择 `legacy` 或 `harbeat_http_v1`，一次只启用一个目标。这是交给网关负责人的待实现工作，不是当前已实现开关。切回旧模式时也不要自动重新播放旧歌。

本次交付位于 harbeat-client；不修改 harbeat-wear 的 `ring/**`、`wrist/**` 和现有 Gateway。你们在 harbeat-wear 接入时，网关工作应使用 `codex/gateway-*`，需要修改固件时按该仓库规则分别使用 ring/wrist 分支。

## 5. 按这个顺序验收

1. 不操作硬件，只查 capabilities/state，确认 EDM、tempo 模式和服务可用。
2. 得到现场允许后，用本目录 simulate_control.py 验证 start → pause → start → next。此操作会发声。
3. 把一枚真实手环的逻辑动作接入同一接口，记录原始事件 ID、HTTP request_id、响应和状态变化。
4. 验证真实戒指四类事件；10 秒观察窗口内是否有事件到达及音效接受，另记录实际延迟和误触发，不把“允许观察 10 秒”当作可接受响应延迟。
5. 重发同一事件，确认不重复执行；新按键确认能执行。转场中 next 应拒绝，暂停应冻结两路及转场进度。
6. 暂停时手势音效应拒绝；不支持的风格保留原播放状态。测试蓝牙断连重连、网关重启、服务不可用和旧入口争用。
7. 完整听完一轮 8 首，再交付“实物已通过”。此前模拟和加速 seek 验证不能替代这一步。

请回传：网关分支/提交号、按键/姿态映射表、一次完整 start/pause/next/gesture 请求与状态日志、失败/重连处理结果，以及实物试听结论。日志不要包含热点密码、密钥或公网鉴权凭据。

## 6. 本次已交付与尚待你完成

已交付：混音控制服务、独立变速入歌资产准备代码、引擎修改快照、HTTP 适配器、模拟发送器、测试代码及历史验证报告。

待你完成：真实 BLE/按键/姿态事件到 HTTP 的适配、反馈到设备的 UI/振动/ACK、去重映射与重连处理、旧入口切换及实物验收。未来新的音效素材/连续姿态效果由项目负责人另行提供，不需要现在猜测实现。
