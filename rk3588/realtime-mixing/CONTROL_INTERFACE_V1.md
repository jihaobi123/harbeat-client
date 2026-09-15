# 给戒指、手环协作者：接入 EDM 实时混音端

版本：`harbeat.control.v1`，2026-09-14；交付说明更新 2026-09-15。

先读 [负责人任务说明](WEARABLE_HANDOFF.md)。本文源码位于 harbeat-client，描述新增 HTTP 适配器，不替换另一个设备仓库 harbeat-wear/contracts 中旧 NDJSON Engine IPC 或 BLE 协议；二者不能直接互换。

> 能力更新：已接入原 vocal_v4 的实际入歌变速、原速尾部、配对淡变长度和最后一首淡出。最新说明见 [TEMPO_V4_INTEGRATION.md](TEMPO_V4_INTEGRATION.md)。硬件事件 JSON 不变；界面应读取 source_position_sec 作为原曲进度。

## 1. 谁负责什么

本次负责的是 RK 上的混音控制、切歌安排、播放器调用和模拟测试。**不修改戒指/手环固件、蓝牙协议、姿态识别或现有硬件网关。**

硬件负责人需要把识别出的“按键/手势”转换成本文的 JSON，由运行在 RK 上的网关发送给本地 HTTP 接口。硬件不需要选择切歌时间点，不需要操作音频文件，也不要同时向旧播放器重复发送同一动作。

数据已经在 RK `/home/cat/harbeat-mixing-v1/data/edm_8_bundle`，当前只支持这批 EDM 8 首。轨道 ID 与播放器内部 ID 对照位于 `reports/realtime_aliases.json`。保持 published 数据不变，不能把旧 hiphop/locking 歌单当作 EDM。

## 2. 现在能做什么，不能做什么

| 输入 | 混音端行为 |
| --- | --- |
| start | 首次加载并开始；已经暂停则从当前位置继续 |
| pause / stop | 暂停，保留进度；stop 不是清空歌单 |
| next | 安排最近的未来候选出歌点，按原算法配对时长与下一首实时淡变 |
| 不按 next | 自动在歌曲后部候选位置接下一首，8 首不重复播放 |
| gesture / trigger_effect | 播放中触发已有采样音效；暂停时拒绝 |
| set_style = EDM | 保持 EDM |
| 其他 style_id | 返回 style_assets_not_ready，保留当前播放 |

这是**入歌按原算法变速的双路 master 实时混合**，不是预先渲染整段音频再播放。已经接入原脚本 atempo 处理；16 小节平滑回速、分轨拆层混音不属于原推荐渲染脚本的已实现能力，本次也不宣称完成。其他风格曲库尚未接入。音效暂用播放器已有四个采样。

“最近候选”定义：当前播放位置至少 3 秒之后，出歌窗口中的小节起点，并且剩余音频足够完成本次转场。不会打断当前入歌变速阶段。无窗口候选时使用明确标记的段落边界附近小节回退；仍无点则报错，不强制硬切。因此按 next 不一定立即换歌。

## 3. 接口地址

在 **RK 本机**访问 `http://127.0.0.1:9130`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /v1/capabilities | 当前支持的动作、风格、手势映射、能力限制 |
| GET | /v1/state | 实际播放位置、当前歌、待执行转场、历史事件 |
| POST | /v1/device-events | 硬件网关正式接入入口；模拟器使用同一格式 |
| POST | /v1/commands | RK 本机诊断入口，使用 cmd/request_id；不是固件协议 |

服务只监听 loopback，没有开放公网，也没有宣称支持远程鉴权。手机、戒指不能把自己的 127.0.0.1 当作 RK；应通过 RK 上的网关接入。需要网络接口时另行设计鉴权，勿直接改成 0.0.0.0。

## 4. 网关必须发送的格式

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

| 字段 | 规则 |
| --- | --- |
| schema_version | 固定 harbeat.control.v1 |
| source | wrist_gateway、ring_gateway；测试使用 simulator 或 test_client |
| device_id | 稳定设备标识，字符串 1–128 字符 |
| boot_id | 本次网关启动标识；重启换新值，重试不要换 |
| event_id | 每个新动作一个新 ID；同一动作重发保持不变 |
| action | 下表中的动作 |
| params | 对象；不要放入 cmd、request_id 等额外字段 |

source 只是调用方声明，不代表已经验证了真实手势，也不是身份认证。

| action | params |
| --- | --- |
| start | {}；首次可选 {"track_id":"交付数据中的轨道ID"} |
| pause | {} |
| stop | {} |
| next | {}；也可指定尚未播放的 track_id |
| set_style | {"style_id":"EDM"} |
| gesture | {"gesture_id":"punch_forward"} |
| trigger_effect | {"effect_id":"snare_impact"} |

已配置手势：punch_forward → snare_impact；flick_up → air_horn；swipe_side → beat_stutter；wrist_roll → bass_drop。硬件负责人确认真实动作分类后再映射，不要求更改设备现有分类模型。

去重按 source/device_id/boot_id/event_id 组合计算，同一身份和相同内容重发返回原结果；同一身份换内容返回 request_id_conflict。只保留当前控制进程最近 512 条成功请求；重启不保留，**不是跨重启的严格一次执行保证**。

## 5. 接口返回后要怎么处理

成功含 `ok:true`、`request_id`、`schema_version`。next 返回 `status:scheduled` 和 `pending`：包含 from_track_id、to_track_id、from_at_sec、to_at_sec、fade_sec、candidate_reason、requested_at_position 等。单位为原曲时间的秒，不是 Unix 时间。

scheduled 只是排好计划，不代表已经换歌。随后轮询 GET /v1/state（建议 250–500ms）读取 pending.status：scheduled → transitioning；完成后 pending 清空，events 出现 completed，当前轨道变为下一首。8 首全部完成后结束。

暂停冻结实际音频位置和转场进度；start 继续。手动 next 已排好时，再按 next 返回已有安排，不累计多个切歌；转场中再切歌会拒绝。状态以播放器返回为准，不靠客户端自己倒计时猜测。

| HTTP 状态 | 处理 |
| --- | --- |
| 200 | 成功，仍需根据 status 判断排队/播放/暂停 |
| 400 | 参数、版本、未知动作等错误；修正后作为新请求发送 |
| 409 | 当前状态不允许，如转场忙、未开始、无候选、资源未就绪或 ID 冲突；读取 error 和状态 |
| 503 | 控制器/引擎不可用；恢复后同一动作仍用原 ID 重试 |

首次 start 需要载入音频，可能耗时数秒，建议调用超时 35 秒。超时不代表未执行，不要马上用新 ID 重放 start/next。当前服务串行处理控制动作，尚不是硬实时控制保证。

## 6. 不用硬件也能验收

以下命令在 RK 终端运行，工作目录 `/home/cat/harbeat-mixing-v1`：

```bash
venv/bin/python simulate_control.py capabilities
venv/bin/python simulate_control.py start
venv/bin/python simulate_control.py gesture --value punch_forward
venv/bin/python simulate_control.py next
venv/bin/python simulate_control.py state
venv/bin/python simulate_control.py pause
venv/bin/python simulate_control.py start
venv/bin/python simulate_control.py stop
```

每次运行默认生成新事件 ID。测试重发可显式传同一个 --event-id；新的真实动作不能沿用旧 ID。

自动测试：`venv/bin/python verify_realtime_live.py --http --tempo`。它通过同一 HTTP 事件入口模拟手环/戒指，检查开始、暂停、恢复、最近候选、重复切歌、转场中暂停、四个手势音效以及全部 7 次交接，并逐对核对原版变速参数和淡变时长。为了缩短测试，诊断程序会 seek 到候选点前，**不是整场连续试听**。测试会发声，应在无人进行现场演出时执行。

手势模拟验收：10 秒内至少有一次音效请求被播放器接受；不是要求延迟 10 秒才响，也不证明真实 IMU 识别准确率或扬声器听感。

## 7. 部署、内存及回退

本次文件：realtime.py（切歌状态机）、control_api.py（HTTP 适配）、simulate_control.py（模拟器）。cat 用户服务：harbeat-realtime-v1、harbeat-control-api-v1。服务启动不自动播放。

原播放器 engine.py 对这批 rtv1 原曲保留最多 8 首、1GiB 缓存；当前变速版本另有 rtv2 缓存，最多 10 份、1GiB，保护正在使用的两路音频。完整规则见 TEMPO_V4_INTEGRATION.md。缓存随引擎进程退出释放，不是无限曲库方案，未修改硬件网关。

查看服务：`systemctl --user status harbeat-realtime-v1 harbeat-control-api-v1`。日志和测试 JSON 位于 reports/。停止服务前先 pause，单纯停止控制服务不会自动停止原播放器。

当前变速版回退引擎：先暂停，由管理员核对 RK 上 `engine-patch/engine.before-tempo.py` 备份，再运行 `venv/bin/python install_tempo_engine.py --rollback`，然后重启 cypher-audio-engine.service 并将控制服务切回原速模式。脚本校验哈希，备份不匹配就停止。更早的 install_engine_patch.py 是针对原始引擎基线的工具，不能混用。部署备份不上传 Git；不能以 Git 快照替代本机匹配备份。勿用 python -O 绕过 assert 校验。

## 8. 硬件负责人剩下的工作

1. 将手环开始/暂停/切歌动作映射到本文 action。
2. 将戒指已识别手势映射到 gesture_id；识别算法由硬件负责人负责。
3. 新事件发新 ID，网络重发保留 ID；不要新旧接口双发。
4. 对照状态接口显示 scheduled/transitioning/paused，不将 HTTP 成功当成换歌完成。
5. 实物联调另验收蓝牙重连、误触发、真实声音及延迟；本次模拟通过不替代这些测试。

现有旧网关仍可能直接操作旧播放器；接入新接口后需由硬件负责人避免两套入口争用。混音端检测到旧歌曲接管时会退出自己的会话。
