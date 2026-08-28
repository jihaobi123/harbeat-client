# HarBeat RK 开发负责人开工任务书

版本：`v1.0-draft`
协议版本：`rk-control-v1` / `rk-event-v1` / `resource-manifest-v1`
基线日期：2026-08-28
收件人：RK3588 边缘端开发负责人

## 1. 你需要交付的最终结果

你负责 RK3588 上完整的边缘运行系统，包括：

- edge-agent：手机局域网唯一入口；
- sync-worker：Manifest、资源下载、校验、缓存和恢复；
- audio-engine：本地播放、混音、Pad、Transition 和 DSP 执行；
- input-daemon：实体键读取和 logical intent 映射；
- SQLite：配对、授权、Manifest、SyncJob、Operation、Event Outbox、缓存索引；
- REST/WebSocket：向手机提供能力、状态、控制和事件；
- Jetson 通信：直接下载资源、设备心跳和执行事件补传。

RK 是现场执行事实的权威源。手机只能发送控制意图和读取状态；Jetson 只做演出前准备与事后收集，不能参与现场毫秒级执行。

## 2. 已冻结的系统关系

```text
手机开启热点
  ├─ RK 加入热点并获得互联网
  ├─ 手机 ↔ RK：局域网 REST + WebSocket
  └─ 手机 → RK：Manifest/SyncJob/PadPreset/现场操作

RK
  ├─ HTTPS → 阿里云 Gateway → Jetson/NAS 直接下载资源
  ├─ 本地播放、混音、Pad、实体键、DSP
  ├─ 本地记录 Operation/Event/Outbox
  └─ 恢复网络后 → Jetson 批量补传执行事实

Jetson
  ├─ 用户/曲库/设备/Manifest/会话业务数据
  ├─ 音乐分析 Worker
  └─ NAS 资源
```

必须遵守：

1. 音频文件不经过手机中转。
2. 现场操作不等待 Jetson/阿里云响应。
3. RK 接受/执行操作前后都要持久化，不能只保存在内存。
4. RK 断网时继续使用已缓存、仍在授权期内的现场资源。
5. 手机断开/退出不应终止 RK 已接受的同步或现场会话。
6. RK 只把中央事件镜像上传 Jetson；Jetson 不反向伪造 executed。

## 3. 已冻结的产品规则

- 一台 RK 只有一个 Owner；可授权其他用户临时 controller/viewer。
- 一个用户可拥有多台 RK。
- Pad 数量和实体键位尚可调整，协议不能写死 8。
- 当前 App 视觉可以显示 8 Pad，实际 `slot_count/slot_ids` 由 RK 上报。
- 播放/暂停、下一首、能量提高/降低、延长、Talk、Undo 是固定控制，不占 Pad。
- 复杂 EQ、Stem Solo、Filter、专业 DJ 参数 P0 暂不开放给普通 App，但 RK 内部能力可以保留。
- 实体键和手机操作必须进入同一 Operation/Event/State 模型。
- 完整歌曲播放、混音和音频输出都在 RK。

## 4. 当前代码位置和现状

RK 根目录：`cypher-integration/rk3588-edge/`

| 路径 | 当前内容 | 本轮任务 |
|---|---|---|
| `edge-agent/` | HTTP/WS、状态、audio 转发、配对相关代码 | 收敛为唯一局域网入口和正式协议 |
| `sync-worker/` | Manifest/资源下载和 sha256 | 仅 loopback，增加 SQLite、Range、取消、恢复 |
| `audio-engine/` | 播放、混音、Transition/DSP 和 Unix socket | 固定 IPC、状态/错误回执、重启恢复边界 |
| `input-daemon/` | 实体按键 | hardware profile → logical intent |
| `deploy/` | systemd units/target/env | 修正依赖、权限、watchdog、日志和安装文档 |
| `tests/` | sync/state/audio/transition 等测试 | 补配对、SQLite、断网、重复包、真机测试 |
| `plans/`, `samples/` | 示例/计划 | 转为合同 fixtures，不作为生产状态真相 |

当前已知差距：

1. `main.py` 中配对存在随机 code/mock confirm，不能用于生产。
2. `pairing.py`、`app_compat.py` 和 main 中存在分叉实现/配置。
3. sync 状态主要在内存，重启恢复和取消不完整。
4. 手机部分代码直接访问 `:9100`；目标必须只访问 edge-agent。
5. `/live/intent`、`/live/override` 与当前 edge 主路由不一致。
6. transition-orchestrator 的 Operation 状态尚未完整接入主路径。
7. 事件补传中央当前缺少稳定的持久/去重/缺口闭环。
8. 当前 Manifest 仍可能缺少强 sha256、包含私网地址或过大分析 JSON。

## 5. 目标进程边界

```text
手机热点网卡
  ├─ edge-agent HTTPS :9000
  └─ edge-agent WSS   :9001

RK loopback/Unix IPC
  ├─ sync-worker 127.0.0.1:9100
  ├─ audio-engine /run/harbeat/audio.sock
  ├─ input-daemon → edge-agent IPC
  └─ SQLite WAL + 文件缓存
```

规则：

- 手机不得访问 sync-worker/audio-engine。
- edge-agent 负责认证、schema、幂等、权限、状态机和聚合。
- sync-worker 只负责下载/验证/缓存任务。
- audio-engine 只负责音频实时执行，不能自己处理用户 JWT/中央业务。
- input-daemon 不直接修改音频状态，必须生成 logical intent 交给同一 Operation 流程。

## 6. 网络发现与身份

### mDNS

Service：`_harbeat-rk._tcp.local`

TXT 至少包含：

- `hardware_id`
- `edge_version`
- `control_protocols=rk-control-v1`
- `port=9000`
- `ws_port=9001`
- `pairing_state`

IP 只用于当前连接，不能当设备身份。mDNS 不可用时允许二维码/地址兜底，但仍要校验 hardware_id 和设备公钥指纹。

### Identity

`GET /api/v1/identity`：

```json
{
  "hardware_id": "rk-serial-opaque",
  "device_id": "018f0000-0000-7000-8000-000000000010",
  "display_name": "HarBeat Stage 01",
  "pairing_state": "bound",
  "edge_version": "1.0.0",
  "public_key_fingerprint": "sha256:<base64url>",
  "control_protocols": ["rk-control-v1"],
  "event_protocols": ["rk-event-v1"],
  "server_time": "2026-08-28T10:00:00Z"
}
```

未绑定时 `device_id=null`。

## 7. 配对与授权

流程：

```text
RK 生成/显示一次性配对码
→ App 向中央 claim(code + hardware_id + device_nonce)
→ App 请求 RK 本地 proof
→ RK 验证 code、claim、nonce 和物理确认
→ App 向中央 finalize(device_proof)
→ 中央建立 Owner/device credential
→ App 用中央证明向 RK exchange 短期 session token
```

要求：

- 配对码 6–8 位、TTL 建议 5 分钟、最多 5 次错误。
- RK 只存 code hash；code/proof/nonce/token 不写日志。
- 已有 Owner 时不允许第二个用户重新配对抢占。
- Owner 转移/恢复出厂必须撤销所有授权和 device credential。
- 手机只拿短期 RK session token，不拿中央 device token。
- Session token 包含 device/user/role/permissions/exp/jti/audience。
- 离线授权只能在本地缓存有效期和最大安全窗口内使用。

## 8. Capability 合同

RK 每次启动/能力变化生成不可变报告：

```json
{
  "schema_version": "rk-capability-v1",
  "report_version": "<uuid>",
  "generated_at": "2026-08-28T10:00:00Z",
  "device": {
    "device_id": "<uuid>",
    "firmware_version": "1.0.0",
    "edge_version": "1.0.0",
    "audio_engine_version": "1.0.0"
  },
  "protocols": {
    "control": ["rk-control-v1"],
    "events": ["rk-event-v1"],
    "manifest": ["resource-manifest-v1"],
    "pad_preset": ["pad-preset-v1"]
  },
  "pad": {
    "slot_count": 8,
    "slot_ids": ["pad-01", "pad-02", "pad-03", "pad-04", "pad-05", "pad-06", "pad-07", "pad-08"],
    "supported_modes": ["one_shot", "toggle", "hold", "loop"],
    "supported_quantize_modes": ["off", "beat", "bar"],
    "max_sound_duration_ms": 120000,
    "max_sound_size_bytes": 104857600,
    "supported_codecs": ["wav_pcm_s16le", "flac"]
  },
  "fixed_controls": [
    "transport.play_pause",
    "transport.next",
    "energy.increase",
    "energy.decrease",
    "transition.extend",
    "talk.set",
    "history.undo"
  ],
  "audio": {
    "sample_rates_hz": [44100, 48000],
    "channels": [2],
    "stem_playback": true,
    "max_simultaneous_stems": 4,
    "supports_pre_rendered_transition": true
  },
  "storage": {
    "total_bytes": 256000000000,
    "free_bytes": 128000000000,
    "cache_budget_bytes": 180000000000,
    "low_watermark_bytes": 20000000000
  },
  "capability_hash": "<canonical-json-sha256>"
}
```

后端生成 Manifest、前端渲染功能都依赖该报告。能力改变必须更新 report_version/hash，不能静默改变同一报告。

## 9. 手机局域网 API

Base：`https://<rk-address>:9000/api/v1`

| 方法/路径 | 用途 | 要求 |
|---|---|---|
| `GET /identity` | 身份/配对状态 | 未配对可读，限流 |
| `GET /capabilities` | 当前能力 | session token |
| `POST /pairing/proof` | 本地物理确认/proof | 一次性 claim，严格限流 |
| `POST /sessions/exchange` | 中央证明换 RK token | proof 单次使用 |
| `GET /state` | 完整快照 | token |
| `GET /events` WS upgrade | 增量事件/快照 | token/ws ticket |
| `POST /pad-presets/activate` | 激活预设版本 | Idempotency-Key |
| `POST /sync-jobs` | 接受同步任务 | Idempotency-Key |
| `GET /sync-jobs/{id}` | RK 权威同步状态 | token |
| `POST /sync-jobs/{id}/cancel` | 取消同步 | Idempotency-Key |
| `POST /live-sessions` | 开始本地现场会话 | Idempotency-Key |
| `POST /live-sessions/{id}/operations` | 现场意图 | operation_id 幂等 |
| `GET /operations/{id}` | 查询未知结果 | token |
| `POST /live-sessions/{id}/end` | 结束会话 | Idempotency-Key |
| `GET /health/ready` | audio/cache/db ready | token |

所有响应带 X-Request-Id。Mutable body 必须做 JSON Schema、大小、Content-Type、权限和 token audience 校验。

## 10. State Snapshot 与 WebSocket

```json
{
  "schema_version": "rk-state-v1",
  "device_id": "<uuid>",
  "device_boot_id": "<uuid>",
  "sequence": 1024,
  "captured_at": "2026-08-28T10:31:00Z",
  "connection": {"central_online": false, "outbox_pending": 21},
  "live_session": {"id": "<uuid>", "status": "live"},
  "transport": {
    "state": "playing",
    "track_id": "<uuid>",
    "position_ms": 42130,
    "duration_ms": 243120,
    "track_index": 0
  },
  "mix": {"energy_level": 0.73, "talk_enabled": false, "active_transition": null},
  "pad": {"active_preset_version_id": "<uuid>", "active_slots": []},
  "sync": {"status": "cache_ready", "manifest_id": "<uuid>"},
  "audio": {"ready": true, "xrun_count": 0, "output_device": "logical-output"}
}
```

WS event 必须包含：schema_version、event_id、event_type、device_id、device_boot_id、live_session_id、sequence、occurred_at、operation_id、payload。

重连规则：

1. App 提供 last sequence。
2. RK 有事件历史时补发缺口。
3. 历史不足或 boot_id 改变，先发 snapshot。
4. sequence 会话内严格单调并持久。
5. Position 可 4–10 Hz 节流，操作终态不能丢。

## 11. Operation 合同

请求：

```json
{
  "schema_version": "rk-operation-v1",
  "operation_id": "018f0000-0000-7000-8000-000000000060",
  "source": "app",
  "intent": "energy.adjust",
  "parameters": {"delta_steps": 1},
  "client_sequence": 88,
  "requested_at": "2026-08-28T10:31:02.123Z",
  "expires_at": "2026-08-28T10:31:07.123Z",
  "expected_state_sequence": 1024
}
```

状态：

```text
accepted → syncing → cache_ready → prepared → scheduled → executed
    └→ rejected | failed | canceled | expired
```

P0 intent：

- transport.play/pause/play_pause/next
- energy.adjust(delta_steps -1|1)
- transition.extend(bars 1..16)
- talk.set(enabled)
- history.undo
- pad.trigger(slot_id,velocity)
- pad.release(slot_id)

规则：

- HTTP 202 只表示 accepted，不表示 executed。
- 先写 SQLite Operation，再向 audio-engine 排程，再广播状态。
- 同 operation_id 同 request hash 返回原结果；不同 payload 返回幂等冲突。
- App 超时后查询原 operation/snapshot，RK 不能把同一 operation 执行两次。
- expected_state_sequence 过旧且操作不安全时明确拒绝/要求重同步。
- expires_at 已过时进入 expired，不延迟执行陈旧命令。

## 12. 实体键和 Audio Engine

实体键配置只存在 RK：

```yaml
hardware_profile: rk-board-rev-a
bindings:
  KEY_PLAYPAUSE: transport.play_pause
  KEY_NEXTSONG: transport.next
  KEY_F13:
    intent: pad.trigger
    parameters: {slot_id: pad-01}
```

要求：

- keycode/GPIO 不进入中央 API/Manifest。
- input-daemon 生成 source=physical 的同一 Operation。
- 实体键执行也写 Operation/Event/Outbox，并通过 WS 让 App 看到。
- hardware profile 可版本化切换，不改 logical protocol。

Audio-engine Unix socket 合同必须定义：

- command schema/version/request ID；
- accepted/scheduled/executed/error 回执；
- 播放/暂停/next/energy/talk/undo/pad/transition；
- 当前 transport/mix/pad/audio health snapshot；
- timeout、进程重启、声卡断开和 xrun 语义；
- 实时线程不得被 SQLite/HTTP/下载阻塞。

## 13. Manifest 和资源同步

手机向 RK 只下发：sync_job_id、manifest_id/URL、短期 scoped token、expected manifest hash。

RK 必须：

1. 验证 Manifest schema、签名、content hash、target device、capability hash、过期/撤销。
2. 检查 required assets、格式和可用空间。
3. 直接从阿里云 HTTPS Gateway 下载。
4. 支持短期 grant 刷新、Range/If-Range/ETag。
5. 下载到同文件系统 `.part`，size 后完整 sha256。
6. 对音频/JSON 做格式/schema 验证。
7. fsync + 原子 rename 到内容寻址缓存。
8. SQLite 事务标 ready，之后才能上报 cache_ready。

SyncItem：

```text
pending → grant_pending → downloading → verifying → ready
              └→ retry_wait → downloading
              └→ failed | skipped | canceled
```

SyncJob：

```text
accepted → syncing → cache_ready | partial | failed | canceled | expired
```

required asset 失败则 failed；optional 失败可 partial。下载字节 100% 但 hash 未完成仍是 verifying。

## 14. 缓存

建议物理路径：`cache/sha256/{first2}/{sha256}`，asset_id 到 content hash 存 SQLite。

Cache entry 保存：

- asset_id/content hash/path/size；
- status/verified_at/last_access；
- policy：session/pinned/reusable；
- priority/ref_count；
- active Manifest/session 引用。

不能淘汰：audio-engine 当前打开、active session required、有效 pinned 资源。

低于 low watermark 时按无引用、低优先级、LRU GC。下载前仍不足则 `RK_STORAGE_INSUFFICIENT`，不能下到一半才静默删除其他活动资源。

## 15. 本地 SQLite

使用 WAL，至少包含：

- device_state
- authorization_cache
- manifests
- sync_jobs/sync_items
- cache_entries/cache_references
- pad_presets/active_preset
- live_sessions
- operations
- event_outbox
- runtime_snapshots
- schema_migrations

每个 mutable 操作事务化。进程启动先跑本地 migration，再恢复状态；不能因升级删除未确认 outbox。

## 16. 事件 Outbox 和中央补传

事件写入顺序：

1. SQLite 同事务写 Operation 状态、DeviceEvent、Outbox。
2. 再向手机 WS 广播。
3. 后台调用中央 `POST /api/v1/device/events:batch`。
4. 中央返回 accepted/duplicate/highest_contiguous_sequence/missing_ranges。
5. 只把明确 ack 的事件标 delivered；优先补缺。

中央断网时指数退避 + jitter。401 刷新 device credential；429 遵循 Retry-After；422 schema 错误隔离/告警，不能无限卡住后续批次。

Outbox 磁盘压力高时可以合并连续 position checkpoint，但不能丢 session/operation accepted/executed/rejected/failed 等事实。

## 17. 断网、重启和恢复

| 故障 | RK 必须行为 |
|---|---|
| 手机 App 被杀 | 同步/现场继续；重连给 snapshot |
| 手机热点短断 | 下载进入 retry_wait，保留合法 `.part` |
| 阿里云/Jetson 不可达 | 已缓存现场继续；事件写 outbox |
| Grant 过期 | 获取新 grant 并 Range resume |
| RK 进程/整机重启 | SQLite 恢复 sync/operation/outbox/cache；新 boot_id/snapshot |
| Audio-engine 重启 | edge-agent 明确 not_ready；安全重连/恢复，不伪造 executed |
| Hash 不符 | 删除/隔离 partial，有限重试并安全告警 |
| ETag 变化 | 清零重下，不拼接不同版本 |
| 磁盘不足 | 安全 GC；仍不足明确失败 |
| 重复 SyncJob/Operation/Event | 返回原状态/去重，不重复执行 |

## 18. 安全要求

- 生产使用 HTTPS/WSS 与设备证书/公钥 pin；如果 P0 暂时 HTTP，必须有短 token、nonce、局域网限制并列为上线阻塞改造。
- Pairing、session exchange、operation 速率限制。
- token audience/permissions/expiry/jti 全检查。
- Device credential root-only；日志不含 token/code/proof/签名 URL。
- sync-worker 只绑定 127.0.0.1；audio socket 最小 Unix 权限。
- Manifest 资源 URL 只允许阿里云 Gateway allowlist，拒绝 127.0.0.1/内网/任意域，防 SSRF。
- body/事件/Manifest 大小限制。
- 所有资产必须强 size/sha256；生产 `SYNC_VERIFY_FULL=1`。
- Owner 撤销/设备恢复出厂清 credential、授权和活动 session。

## 19. 配置和部署

关键变量：

- DEVICE_HARDWARE_ID/RK_ID
- GATEWAY_URL/JETSON_BASE_URL：阿里云 HTTPS，不是 Jetson 私网
- HARBEAT_RK_TOKEN/设备 credential 路径
- SYNC_WORKER_URL=`http://127.0.0.1:9100`
- AUDIO_SOCKET
- CYPHER_HOME
- CYPHER_AUDIO_DEVICE
- CYPHER_REQUIRE_STEMS_FOR_PLAY
- SYNC_MAX_CONCURRENCY（初始 2）
- SYNC_CURL_MAX_TIME_SEC
- SYNC_VERIFY_FULL=1
- INPUT_DEVICE_NAME/INPUT_RECONNECT_SEC
- event batch/flush/retention/authorization offline window

废弃重复 JWT_TOKEN/RKTOKEN 命名，统一 namespace 并提供迁移告警。

Systemd 目标：

1. audio-engine
2. edge-agent
3. input-daemon
4. sync-worker

要求：依赖/After/Requires 明确、EnvironmentFile root 权限、restart/watchdog、读写目录最小、unit 名与 journal 文档一致、开机恢复测试。

## 20. P0 任务拆解

| Epic | 任务 | 交付物 |
|---|---|---|
| RK-00 工程基线 | 统一版本/配置/目录/SQLite migration/systemd | build info、安装/升级/回滚 |
| RK-01 Identity/Pairing | mDNS、identity、code/proof/session token、Owner/授权缓存 | pairing Schema/安全测试 |
| RK-02 Capability | 动态 Pad/audio/storage/protocol capability | capability Schema/fixtures/hash |
| RK-03 Edge API/WS | 单一 9000/9001、state snapshot、event replay | OpenAPI/WS Schema/客户端 fixture |
| RK-04 Operation | Operation 账本、幂等、状态机、audio IPC | intent/operation tests |
| RK-05 Physical/Audio | hardware profile、实体键、audio-engine 状态/错误 | IPC 合同/真机报告 |
| RK-06 Sync/Cache | Manifest 验证、grant/Range/hash/cache/GC | SyncJob/恢复/压力测试 |
| RK-07 Outbox | Event sequence、batch/ack/gap、离线补传 | 断网/重复/缺口测试 |
| RK-08 稳定与安全 | 24h、断电、磁盘、声卡、网络、安全 | 性能/恢复/安全报告 |

## 21. 你需要向其他负责人索取的输入

向后端：

- device_id/Owner/Binding/Pairing Claim/device credential 合同；
- Manifest、Asset Grant、SyncJob、LiveSession、Event Batch API；
- 阿里云 Gateway 测试域名、Range、签名和错误 fixture；
- 统一 error code、Idempotency-Key、版本/过期策略；
- Staging 设备账号和可清理测试资源。

向手机前端：

- mDNS/配对/状态/控制交互流程；
- App 支持的 HTTP/WS token 方式；
- last sequence/reconnect/timeout_unknown 行为；
- 4 Pad/8 Pad/低能力页面验证结果；
- 操作节流、按钮连点和后台恢复行为。

向服务端算法：

- RK 运行所需 Beat/Cue/Transition 字段和质量语义；
- master/Stem/Render/runtime metadata 格式、采样率、声道、大小；
- 低置信 Downbeat/Transition 的禁用或降级规则；
- analysis/schema/model version 和兼容性；
- 代表性合法/异常资产 fixtures。

## 22. 四方协作统一规范

### 22.1 责任边界

| 负责人 | 负责 | 不负责 |
|---|---|---|
| 后端 | Jetson FastAPI、PostgreSQL、媒体/Manifest、Worker编排、设备云端数据、Gateway | 算法结论、RK现场执行、手机页面 |
| 手机前端 | App 页面、中央客户端、RK连接/状态/控制、用户反馈 | 中央业务真相、算法计算、RK执行事实 |
| 服务端算法 | Jetson 分析 adapter、模型、Schema、质量/验证、Stem/Feature/Style | 用户/设备业务表、手机/RK状态机 |
| RK | edge/sync/audio/input、本地SQLite/缓存、Operation/Event、现场事实 | 中央用户曲库、公共审核、服务端分析 |

### 22.2 合同唯一来源

| 合同 | 主维护 | 必须评审/消费 |
|---|---|---|
| 手机中央 OpenAPI | 后端 | 前端；算法评审分析 DTO |
| 音乐分析 Schema | 算法 | 后端校验；前端/RK评审投影 |
| RK Control/Event/Capability | RK | 后端、前端 |
| Manifest/Asset/Sync | 后端 + RK 共同维护 | 算法、前端 |
| 错误/幂等/离线恢复 | 后端定义公共码；RK定义本地执行码 | 四方互审相关部分 |

任何字段不能只在聊天中修改。统一变更流程：

```text
提出 Issue/ADR
→ 先修改 OpenAPI/JSON Schema/状态表
→ 增加 success/error/compatibility fixture
→ 受影响负责人评审
→ 更新生成客户端和合同测试
→ 再实现代码
→ 发布 release note、升级/回滚说明
```

### 22.3 数据和协议规则

- 新 ID 使用 UUID；重试不更换 operation_id/event_id/sync_job_id。
- 时间使用 RFC 3339 UTC；顺序使用 version/sequence，不靠跨机器时钟排序。
- 未知值使用 null；禁止用 0、空字符串或空数组冒充未知事实。
- 枚举只可兼容新增；删除/改语义必须升级版本。
- 状态转换必须有允许表，终态不回退。
- 写操作有 Idempotency-Key/request hash；消费者必须容忍重复消息。
- 中央业务以 PostgreSQL 为准；算法语义以 versioned artifact 为准；现场事实以 RK 最大 sequence 为准；页面只是投影。
- 日志统一 request_id/correlation_id/analysis_run_id/manifest_id/sync_job_id/operation_id/event_id。
- token、配对码、proof、签名 URL、NAS 路径不进入日志/fixture。

### 22.4 版本和共享 Fixture

- Central API：`/api/v1` + OpenAPI version。
- Analysis：contract/schema/pipeline/model/calibration 分别版本化。
- RK：control/event/capability 版本化并 capability negotiation。
- Manifest/PadPreset：schema version + immutable version/hash。
- 发布提供 git SHA、release ID、数据库/SQLite revision、模型/协议版本。
- 跨端升级至少验证当前版和前一兼容版；不兼容时明确拒绝。
- 共享 Schema/fixture 放在 `contracts/schemas/`、`contracts/fixtures/`。
- 每个合同至少有 success、null/degraded、invalid、unauthorized、conflict、timeout/retry、旧版兼容示例。

### 22.5 联调门槛和共同完成定义

开始联调前必须：Schema/OpenAPI 评审通过、四端解析同一 fixtures、后端 Mock/RK simulator/算法 fixture Worker 可运行、错误/超时/恢复用例明确、build/version 可查询。

跨端功能只有同时具备以下内容才算完成：

- 合同和字段说明；
- 正反 fixtures；
- 实现、权限和幂等；
- 单元/合同/集成测试；
- 日志、指标和可诊断错误；
- 断网/重启/重复包恢复；
- 配置、版本、部署和回滚；
- 受影响负责人评审记录。

## 23. 最终交付清单

- RK Control OpenAPI、Event/Capability/State/Operation JSON Schema；
- edge-agent 单一 9000/9001 正式实现；
- 安全配对、session token、Owner/临时授权缓存；
- 动态 capability 和 fixtures；
- PadPreset 激活、Operation 状态机和音频 IPC；
- input-daemon hardware profile 和实体键统一事件；
- sync-worker SQLite、Manifest签名、grant/Range/hash/cache/GC；
- LiveSession、Event Outbox、batch/gap/ack补传；
- SQLite migrations、重启/断电恢复；
- systemd/env/安装/升级/回滚手册；
- 真机 24h、网络、磁盘、声卡、性能、安全报告；
- 手机、后端、算法共享 fixtures 和联调报告。

## 24. 完成标准

- 手机只访问 edge-agent，不可访问 9100/audio socket。
- 配对码重放/抢占 Owner/过期 token 均被拒绝。
- 4 Pad/8 Pad/无 Stem 等能力能动态上报和拒绝不兼容 Manifest。
- App 超时/重发不会导致 Operation 执行两次。
- 实体键和 App 命令进入同一状态/事件模型。
- 手机退出、中央断网不影响已缓存现场。
- RK 重启后恢复 SyncJob、Operation、Outbox、Cache，不损坏 ready 文件。
- 下载断点/ETag变化/hash错误处理正确，未验证文件不进 audio-engine。
- required 资源全 ready 才 cache_ready。
- Event 重复补传不重复入库，sequence gap 可补齐。
- 同步与现场并行不产生不可接受音频 xrun/dropout。
- credential、token、proof、签名 URL 不泄露。
- 四方合同 fixture 和真机端到端验收全部通过。

## 25. 仓库内详细合同位置

- `docs/backend-handoff-v1/08_RK设备能力与控制协议.md`
- `docs/backend-handoff-v1/09_资源Manifest与同步协议.md`
- `docs/backend-handoff-v1/10_错误码幂等与离线恢复.md`
- `docs/backend-handoff-v1/11_配置部署安全与运维手册.md`
- `docs/backend-handoff-v1/12_联调测试与验收用例.md`
