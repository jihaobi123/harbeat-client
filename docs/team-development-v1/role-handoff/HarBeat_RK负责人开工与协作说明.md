# HarBeat RK3588 负责人开工与协作说明

版本：`v1.1-draft`
收件人：RK3588 边缘端开发负责人
目标协议：`rk-control-v1 / rk-event-v1 / resource-manifest-v1`
协作分支：`integration/harbeat-contract-first-v1`

## 1. 你的任务结果

你负责 RK3588 上完整的边缘运行系统：

- edge-agent：手机局域网唯一入口；
- sync-worker：Manifest、资源下载、校验、缓存、取消和恢复；
- audio-engine：本地播放、混音、Pad、Transition 和 DSP；
- input-daemon：实体键读取和 logical intent 映射；
- SQLite WAL：配对、授权、Manifest、SyncJob、Operation、Event Outbox、缓存索引；
- REST/WebSocket：身份、能力、状态、操作和事件；
- Jetson 通信：设备心跳、资源直下和执行事件补传。

RK 是现场执行事实的权威源。手机只能发意图和读状态；Jetson 只做演出前准备与事后收集，不能参与现场毫秒级调度。

## 2. 已冻结的系统关系

```text
手机热点
  ├─ 手机 ↔ edge-agent：局域网 REST + WebSocket
  └─ RK → 阿里云 Gateway：Manifest/资产下载/事件补传

RK 内部
  edge-agent
    ├─ loopback → sync-worker
    ├─ Unix socket → audio-engine
    ├─ IPC ← input-daemon
    └─ SQLite WAL + cache filesystem
```

手机不得直接访问 sync-worker/audio-engine。现场操作不得等待 Jetson/阿里云响应。手机断开不应终止 RK 已接受的同步或现场会话。

## 3. 当前代码状态

RK 根目录：`cypher-integration/rk3588-edge/`

| 路径 | 当前内容 | 判断 |
|---|---|---|
| `edge-agent/` | HTTP/WS、状态、audio 转发和配对代码 | PARTIAL，需收敛为正式单一入口 |
| `sync-worker/` | Manifest 下载和 sha256 骨架 | PARTIAL，状态主要在内存，恢复不完整 |
| `audio-engine/` | 播放、混音、Transition/DSP、socket | CURRENT/PARTIAL，需冻结 IPC 和真机能力 |
| `input-daemon/` | 实体键输入 | PARTIAL，需 hardware profile 和统一 Operation |
| `deploy/` | systemd units、target、env、smoke | PARTIAL，需依赖/权限/watchdog/回滚 |
| `tests/` | state/sync/audio/transition 测试 | CURRENT/PARTIAL，需配对/SQLite/断网/重复包/真机 |
| `plans/`, `samples/` | 示例计划和资源 | 仅 fixture，不是生产状态真相 |

当前已知冲突：

- `main.py` 配对有随机 code/mock confirm；`pairing.py/app_compat.py/main` 有分叉；
- App 旧代码可能直接访问 `:9100`；
- `/live/intent`、`/live/override` 与目标 Operation 路由不一致；
- sync 状态、operation ledger、event outbox 和重启恢复未形成单一 SQLite 状态机；
- 当前 Manifest 可能缺强 hash、含私网地址或过大的分析 JSON。

## 4. 已冻结的产品和硬件规则

1. 一台 RK 一个 Owner，可临时授权 controller/viewer。
2. Pad 数量和实体键位尚可能调整，协议不能固定 8。
3. 当前 App 可显示 8 Pad，但 RK 必须上报真实 `slot_count/slot_ids`。
4. 播放/暂停、下一首、能量提高/降低、延长、Talk、Undo 为固定控制，不占 Pad。
5. 手机和实体键必须进入同一 Operation/Event/State 模型。
6. 复杂 EQ/Stem Solo/Filter 可作为内部能力保留，但 P0 不默认向普通 App 暴露。
7. 完整音频播放和输出只在 RK。
8. RK 实体操作不依赖 Jetson，但必须按统一事件合同记录并在联网后补传。

## 5. 你的责任与禁止事项

你负责：RK身份、能力、局域网鉴权、持久状态、资源缓存、现场操作、音频 IPC、实体键、离线恢复、事件补传和真机性能。

你不得：

- 实现用户登录、公共曲库审核或中央资产生命周期；
- 让手机直接访问 `:9100` 或 Unix socket；
- 把 IP 地址当作 device identity；
- 只在内存中保存已接受 Operation、SyncJob 或待补传 Event；
- 收到命令后先回复 executed 再尝试执行；
- 为当前实体键或 App 页面把 Pad 固定为 8；
- 接受缺 size/hash 的 ready 资源；
- 把 Jetson 私网/Tailscale 地址写进生产 Manifest；
- 在日志中输出 device credential、配对码、proof、session token 或签名 URL。

## 6. 目标进程边界

```text
edge-agent HTTPS :9000 / WSS :9001
  - 手机唯一入口
  - 鉴权、schema、幂等、权限、状态聚合

sync-worker 127.0.0.1:9100
  - 下载、Range、校验、缓存、取消和恢复

audio-engine /run/harbeat/audio.sock
  - 实时播放、混音、Pad、DSP

input-daemon → edge-agent IPC
  - hardware event → logical intent

SQLite WAL
  - durable device state / operation / event / sync / cache index
```

audio-engine 不处理用户 JWT；input-daemon 不直接修改音频状态；sync-worker 不对手机开放端口。

## 7. P0 任务拆解

### RK-00 版本和真机能力基线

- hardware_id、板卡、OS/kernel、音频设备、存储挂载；
- edge/sync/audio/input git SHA 和协议版本；
- 支持 codec、采样率、声道、文件大小、缓存容量；
- 当前实体键列表、硬件 profile 和可配置 Pad；
- `/api/v1/build` 或 identity 中可查询 build 信息。

### RK-01 Identity、mDNS、配对和授权

- mDNS `_harbeat-rk._tcp.local`；
- identity 返回 hardware_id、device_id、edge version、公钥指纹和支持协议；
- 一次性 code 只存 hash，有 TTL/次数限制；
- 中央 claim/finalize + RK local proof + 物理确认；
- Owner 唯一、转移/恢复出厂撤销全部 credential；
- App 只获得短期 RK session token；
- 离线授权有最大安全窗口和本地撤销规则。

### RK-02 Capability 合同

每次启动或能力变化生成不可变 report：

- hardware/audio/storage/network；
- supported control/event/manifest versions；
- Pad `slot_count/slot_ids`；
- fixed operations；
- codec/sample rate/channels/max asset size；
- Stem/Render/runtime metadata 能力；
- cache limits 和 audio-engine version。

未知版本或不满足 Manifest 要求时明确拒绝并返回稳定错误，不尝试半兼容执行。

### RK-03 State Snapshot 和 WebSocket

- state snapshot 有 schema version、device_boot_id、sequence、generated_at；
- 包含 pairing/session/cache/sync/playback/talk/pad/audio health；
- WebSocket 增量事件带 sequence，重连后先获取完整 snapshot；
- 新 boot_id 后 sequence 可重新开始，但 App/中央不能与旧 boot 混排；
- 状态由持久 ledger + 当前 audio/sync 进程重建，不依赖单一内存对象。

### RK-04 Operation 状态机

统一手机和实体键：

```text
received → accepted → scheduled → executed
                    └→ rejected/failed/canceled/expired
```

- 相同 operation_id + 相同 payload 返回已有结果；
- 相同 ID + 不同 payload 返回 conflict；
- accepted 前完成鉴权、capability、session、资源和 schema 校验；
- accepted 后先持久化，再调度 audio-engine；
- executed 只来自 audio-engine/本地执行确认；
- timeout 后可以按 operation_id 查询，不重复执行；
- Undo 引用明确的目标 operation，越界时安全拒绝。

### RK-05 Manifest、Sync 和缓存

- 校验 schema、device target、capability hash、有效期和 content hash；
- 资产只从受控公网 HTTPS 下载；
- 支持 Range/断点续传、临时文件、size/hash/媒体探测；
- 校验通过后原子 rename 入内容寻址缓存；
- SQLite 保存 job/item/progress/attempt/error/cancel；
- 重启后恢复 queued/downloading/verifying，不把临时文件当 ready；
- cache pin/lease/LRU/低水位，现场资源不得被错误驱逐；
- 签名 URL 过期通过后端授权刷新，不修改 Manifest 资产身份。

### RK-06 Audio Engine 和实体键

冻结 Unix socket 合同：command、request_id/operation_id、deadline、ack/result/error、状态查询和 engine version。

必须保证：

- 播放、Pad、Talk、能量、延长、Undo 和 Transition 不依赖公网；
- 不支持的能力返回稳定 code；
- 实体 keycode 仅在 hardware profile 内部存在，对外转 logical intent；
- 手机和实体键使用同一权限/幂等/状态记录；
- audio-engine 崩溃/重启后 edge-agent 状态可收敛，不谎报继续播放；
- 实体键最终定义未冻结时通过 capability/profile 配置，不阻塞其他端。

### RK-07 Event Outbox 和中央补传

- accepted/scheduled/executed/rejected/failed、播放、缓存、音频健康形成 Event；
- `event_id + device_sequence + device_boot_id + occurred_at + schema_version`；
- 先写 SQLite outbox，再尝试上传；
- 批量上传、指数退避、幂等重传和服务端回执；
- 删除只依据中央明确 ack，不依据 HTTP 连接成功；
- sequence 缺口可诊断和补传；
- payload 不含 token、签名 URL和本地敏感路径。

### RK-08 systemd、运维和恢复

- `cypher.target` 明确服务依赖；
- sync/audio 只绑定 loopback/Unix socket；
- 非 root、最小文件权限、只读模型/配置；
- watchdog/restart backoff、日志轮转、磁盘水位；
- SQLite migration、备份/损坏恢复、缓存重建；
- 安装、升级、协议兼容、回滚和 factory reset 手册；
- 真机 smoke、断网、掉电、热点切换和声卡拔插测试。

## 8. 你主维护和共同维护的合同

你主维护：identity、capability、pairing proof、state、operation、event、RK error、audio-engine IPC。

你与后端共同维护：Manifest/Asset/SyncJob、设备 credential、事件批量上传/回执。

你必须让手机使用同一套 Schema/fixture，并提供不依赖真实音频硬件的 simulator；真机能力差异通过 capability fixture 覆盖。

## 9. 你需要从其他负责人取得的输入

后端：device_id/Owner/Binding/Claim/credential、Manifest/asset grant、SyncJob、LiveSession、Event ingest/ack 和公网域名。

手机：发现和配对 UX、需要展示的 State、操作 timeout/恢复行为、未知 capability 的文案。

算法：RK 最小 runtime metadata、beat/downbeat/cue/transition 单位和置信度、Stem/Render 格式、低置信时禁用的强量化能力。

## 10. 第一批提交顺序

1. RK Capability/Identity/Operation/Event Schema 和 fixtures；
2. SQLite schema/migration 与单一状态源；
3. 配对和授权收敛；
4. edge-agent 单一入口，关闭手机访问 `:9100`；
5. Sync/Cache 重启恢复；
6. Operation→audio-engine→Event 全链路；
7. input-daemon 统一 Operation；
8. 中央补传、systemd、故障和真机验收。

## 11. 完成标准

- 手机只访问 edge-agent；
- identity/capability/control/event/manifest 版本可协商；
- 配对、授权、SyncJob、Operation、Event 和缓存状态全部可重启恢复；
- 重复 operation/event 不重复执行或入库；
- 现场在中央断网时继续运行已授权、已缓存资源；
- 恢复网络后 outbox 完整补传；
- hash/格式/空间不足/不兼容不会形成 cache_ready；
- 手机操作和实体键进入同一状态和事件模型；
- audio-engine 不受手机或云端瞬时断线影响；
- systemd、SQLite migration、升级和回滚经过真机演练；
- App simulator、中央事件接收和真实硬件端到端测试通过。

## 12. 开工回执

请首先回复：当前真机 hardware profile、现有四个进程可复用程度、配对分叉收敛方案、SQLite 表设计、正式端口/IPC、第一版 capability/operation/event fixtures，以及需要后端/算法决定的资源格式。
