# HarBeat 手机前端开发负责人联调任务书

版本：`v1.0-draft`
基线日期：2026-08-28
收件人：手机 App 产品与前端开发负责人

## 1. 你需要交付的最终结果

你负责 Flutter 手机 App 的用户业务、设备连接、准备同步和现场控制界面。App 同时连接两个服务，但两者身份完全不同：

- 阿里云/Jetson 中央后端：登录、用户、公开曲库、个人曲库、歌单、上传、分析、设备权限、预设、Manifest。
- 手机热点局域网内的 RK：设备发现、实时状态、资源同步进度、现场操作、WebSocket。

最终 App 必须做到：

- 未连接 RK 时，仍可登录、浏览、整理、上传、看分析和播放试听；
- 未连接 RK 时，不能完整播放、同步或使用现场控制；
- 连接并验证 RK 后，根据 RK capability 动态展示设备能力；
- 手机只向 RK 下发 Manifest/任务和控制意图，不中转音频文件；
- 现场状态以 RK 为准，不能靠按钮乐观状态伪造“已执行”；
- 中央/RK 断线、App 重启后能够安全恢复，不重复操作。

## 2. 产品规则

1. 手机开启热点，RK 加入热点，并通过热点访问互联网。
2. RK 直接从阿里云 HTTPS Gateway 下载 Jetson/NAS 的歌曲、Stem、Render 和 Pad 音效。
3. 手机不代理下载大文件。
4. 一台 RK 一个 Owner，可临时授权 controller/viewer；一个用户可拥有多台 RK。
5. RK 保存执行事实，断网后补传；手机只读取 RK 状态。
6. Pad 数量不能写死。当前页面可按 8 个 Pad 设计，但必须读取 `capabilities.pad.slot_count/slot_ids`。
7. 播放/暂停、下一首、能量提高/降低、延长、Talk、Undo 是固定控制，不占 Pad。
8. 复杂 EQ、Stem Solo、Filter、专业 DJ 参数暂不向普通 P0 App 开放。
9. 用户从个人曲库删除歌曲时，只删除关联；文案必须是“从我的曲库移除”，不能写“删除音乐文件”。
10. 手机完整歌曲播放不在 P0；完整音频输出来自 RK。

上传公开策略当前默认审核后公开：上传者分析后立即能在个人曲库看到，其他用户仅在 `published` 后看到。状态模型兼容后续自动公开。

## 3. 系统和连接状态

前端不能只维护 `isOnline`。至少维护：

```text
central: online | degraded | offline
rk_lan: disconnected | discovered | pairing | connected | unauthorized
rk_readiness: unknown | not_ready | syncing | cache_ready | live
```

关键区别：

- `central=online` 不代表手机连接了 RK；
- 中央 API 返回 `device.online=true` 只表示最近心跳，不代表当前手机局域网可控；
- `rk_lan=connected` 不代表资源已准备；
- `sync 下载 100%` 不等于 `cache_ready`，还需要 size/hash/格式校验；
- 现场按钮必须同时满足用户权限、RK 连接、capability、session 和资源 ready。

## 4. 功能可用矩阵

| 功能 | 中央在线、RK 未连 | 中央离线、RK 未连 | RK 已连、中央离线 | RK 已连、中央在线 |
|---|---:|---:|---:|---:|
| 登录/刷新 | ✅ | ❌ | 不影响已建立短期现场控制 | ✅ |
| 浏览公开曲库 | ✅ | 缓存只读 | 缓存只读 | ✅ |
| 整理曲库/歌单 | ✅ | P0 不提交 | P0 不提交中央修改 | ✅ |
| 上传 | ✅ | ❌ | ❌ | ✅ |
| 查看分析 | ✅ | 最后缓存 | 最后缓存 | ✅ |
| 手机 Preview | ✅ | P0 可禁用 | P0 可禁用 | ✅ |
| 手机完整播放 | ❌ | ❌ | ❌ | ❌ |
| 设备同步 | ❌ | ❌ | 只能使用已缓存 | ✅ |
| 现场控制 | ❌ | ❌ | ✅，授权/资源仍有效 | ✅ |
| 完整音频输出 | ❌ | ❌ | ✅，RK 输出 | ✅，RK 输出 |

## 5. 代码位置和开发边界

| 路径 | 当前内容 | 本轮工作 |
|---|---|---|
| `mobile/` | Flutter App | 手机主开发目录 |
| `mobile/lib/src/library` | 曲库页面/逻辑 | 接新 Track/Library DTO 和 Preview |
| `mobile/lib/src/import` | 导入/上传相关骨架 | 接 UploadSubmission/AnalysisRun |
| `modules/mobile-dj-control` | 抽取的控制模块/测试 | 可参考状态模型，不等同最终协议 |
| `cypher-integration/rk3588-edge/edge-agent` | RK 局域网入口 | 联调用，不在 App 内复制服务逻辑 |

当前 App 有部分直接调用 RK sync-worker `:9100` 和 `/live/intent`、`/live/override` 的实现。目标必须收敛：

- 手机只访问 edge-agent HTTP `:9000` 和 WebSocket `:9001`；
- sync-worker `:9100` 只绑定 RK loopback；
- 现场命令统一为 versioned operation；
- 不长期同时维护 mock 协议和正式协议。

## 6. 前端代码分层

建议结构：

```text
Generated Central API Models
  → CentralApiClient
  → Auth/Catalog/Library/Upload/Device Repositories
  → Feature Controllers / State
  → Page ViewState

RK Protocol Models
  → DeviceDiscovery/RkApi/RkWebSocket
  → DeviceRepository
  → Prepare/Sync/Live Controllers
  → Page ViewState

Local Secure/Cache Storage
  → token、缓存、恢复上下文
```

要求：

- 中央 API client 从 OpenAPI 生成，生成代码不手工改；
- 页面不直接依赖原始 JSON；Repository/Mapper 处理 DTO；
- 中央状态和 RK 状态分开存；
- token refresh 单飞，同一时间只允许一个 refresh 请求；
- `track_id`、`library_item_id`、`playlist_item_id` 绝不能混用；
- `operation_id`、`sync_job_id`、`manifest_id` 必须持久到流程结束。

## 7. 中央 API

Base：生产通过阿里云 HTTPS，例如 `https://api.<domain>/api/v1`。

机器可读合同：

`docs/backend-handoff-v1/06_手机后端API.openapi.yaml`

接口分组：

| 页面/模块 | API |
|---|---|
| 注册登录 | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` |
| 我的资料 | `GET/PATCH /me` |
| 公开曲库 | `GET /catalog/tracks`, `GET /catalog/tracks/{id}` |
| 试听 | `POST /catalog/tracks/{id}/preview` |
| 上传 | `POST /uploads` → `PUT content` → `POST complete` |
| 分析状态 | `POST /tracks/{id}/analysis-runs`, `GET /analysis-runs/{id}` |
| 个人曲库 | `GET /me/library`, `PUT/DELETE /me/library/{track_id}` |
| 歌单 | `/playlists`, `/playlists/{id}/items` |
| 设备/配对 | `/devices`, `/device-pairings/*`, `/devices/{id}/bindings` |
| Pad 预设 | `/pad-presets` |
| 准备草稿 | `/prepare-drafts`, `/prepare-drafts/{id}/freeze` |
| Manifest/同步 | `/manifests/{id}`, `/devices/{id}/sync-jobs` |
| 会话 | `/devices/{id}/live-sessions` |
| 推荐 | `/recommendations`, `/recommendation-feedback` |

## 8. 页面和字段

### 启动与登录

- 启动：用 refresh token 换新 token，再 `GET /me`。
- Access token 只放内存；refresh token 放 Keychain/Keystore。
- Refresh 成功后先安全保存新 token，再删除旧 token。
- 401 只自动 refresh 一次；refresh 失败清会话回登录。
- 退出时清账户私有缓存和 RK session token。

### 首页、搜索和曲目详情

曲目摘要关键字段：

```json
{
  "id": "<track-uuid>",
  "title": "Track",
  "artist_name": "Artist",
  "cover_url": null,
  "publication_status": "published",
  "analysis": {
    "status": "completed",
    "quality": "ready",
    "duration_ms": 243120,
    "bpm": 128.02,
    "bpm_confidence": 0.94,
    "key": "F# minor",
    "camelot_key": "11A",
    "energy": 0.76,
    "style_labels": []
  },
  "in_my_library": false,
  "version": 1
}
```

展示规则：

- null 不显示伪造默认值；
- analysis pending/running 显示“分析中”；
- failed 显示可理解提示和 request_id，不显示 traceback；
- 风格 `certainty=possible` 使用“可能/相近”文案，不能当确定标签；
- Preview URL 短期有效，过期重新 grant；不缓存原曲 URL。

### 个人曲库

- `LibraryItem.id` 是用户关联 ID；内部包含 `track`。
- `processing`：上传/分析处理中，不可同步。
- `pending_review`：上传者可见“等待公开审核”。
- `rejected`：展示安全 reason/message。
- `blocked`：停止试听/同步。
- 删除使用 track_id 调 `DELETE /me/library/{track_id}`，只更新界面关联。

### 上传

UI 必须分开显示：

1. 文件 HTTP 上传进度；
2. 服务端媒体校验；
3. AnalysisRun 各阶段状态；
4. 公开审核状态。

上传流程中持久化 submission_id；App 重启后 `GET /uploads/{id}` 恢复。AnalysisRun 轮询从 2 秒开始，最大 10 秒，终态停止。

### 歌单/草稿

- 使用服务端 version/ETag。
- PATCH/PUT/排序带 `If-Match: "version"`。
- 409 `RESOURCE_VERSION_CONFLICT` 后拉最新状态，不能静默覆盖。
- 加歌发送 `track_id + after_item_id`，前端不自己计算数据库 position。
- 删除歌单项不删除曲库/Track。

### 设备列表

合并两种来源：

- 中央 `/devices`：账号拥有或被授权的设备；
- mDNS/局域网发现：当前真正可以连接的 RK。

合并键是中央 `device_id`，未配对时使用 `hardware_id` 临时展示。不能用 IP 当设备 ID。

## 9. RK 发现和配对

发现：mDNS `_harbeat-rk._tcp.local`，读取 hardware_id、edge_version、port、ws_port、pairing_state。

目标流程：

1. App 发现 RK，读取 `/api/v1/identity`。
2. 用户查看 RK 显示的配对码。
3. App 调中央 `/device-pairings/claim`。
4. App 调 RK `/pairing/proof`，完成本地物理确认。
5. App 调中央 `/device-pairings/{claim_id}/finalize`。
6. App 用中央授权证明向 RK `/sessions/exchange` 换短期 session token。
7. 清除一次性 code/proof，不写日志。

配对失败、过期、尝试过多要分别处理，不能无限重试。

## 10. 动态设备能力

连接后读取：`GET https://<rk>:9000/api/v1/capabilities`。

关键字段：

- `protocols.control/events/manifest/pad_preset`
- `pad.slot_count/slot_ids`
- `pad.supported_modes/supported_quantize_modes/codecs/size`
- `fixed_controls`
- `live_intents`
- `audio.stem_playback/max_simultaneous_stems`
- `storage.free_bytes/cache_budget/low_watermark`
- `capability_hash`

Pad 页面必须动态生成槽位；不支持的 mode/quantize/codec 直接禁用并解释，不能静默降级。

固定控制独立渲染，不占 slot。

## 11. 准备和同步

流程：

```text
中央保存 PrepareDraft
→ 选择已连接 RK 并读取 capability
→ freeze 生成 Manifest
→ 中央创建 SyncJob 镜像
→ App 向 RK edge-agent 下发 sync_job_id + manifest_id/URL/token
→ RK 直接下载/校验
→ App 通过 RK WebSocket 展示实际进度
→ required assets 全部 ready 后启用“开始现场”
```

同步状态：

```text
accepted → syncing → cache_ready | partial | failed | canceled
```

页面至少显示：总/已就绪资产、下载字节、当前 downloading/verifying、失败资源和重试动作。

重要规则：

- 中央 `GET /sync-jobs/{id}` 是镜像；手机当前连接时以 RK 较大 `rk_sequence` 为准。
- 杀掉 App 不应中断 RK 同步。
- 同一 sync_job_id 重发只能恢复原任务，不能生成重复下载。
- required 失败不能开始；optional 失败可显示 partial。

## 12. 现场控制

HTTP/WS 目标：edge-agent `:9000/:9001`。

初始连接必须先拿 `state.snapshot`。快照包含：

- device_id/device_boot_id/sequence；
- live session；
- transport state/track/position；
- energy/talk/transition；
- active pad preset/slots；
- sync/cache；
- audio ready/xrun；
- central connection/outbox pending。

P0 operation：

| intent | 参数 |
|---|---|
| `transport.play/pause/play_pause` | `{}` |
| `transport.next` | quantize 可选 |
| `energy.adjust` | `delta_steps: -1 | 1` |
| `transition.extend` | `bars: 1..16` |
| `talk.set` | `enabled: boolean` |
| `history.undo` | `{}` |
| `pad.trigger` | `slot_id, velocity` |
| `pad.release` | `slot_id` |

每次点击生成唯一 operation_id。UI 状态：

```text
sent → accepted → prepared/scheduled → executed
                     └→ rejected/failed/expired
超时 → timeout_unknown → 查询 operation 或 state snapshot
```

禁止：HTTP 超时后生成新 operation_id 自动重试。只可查询原 ID，或用完全相同 ID/payload 重发。

`talk` 使用 `talk.set(true/false)`，不要用模糊 toggle，避免丢包导致反向状态。

实体按键操作同样会通过 WS 返回，source=physical。App 无需知道 GPIO/Linux keycode。

## 13. WebSocket 恢复

- 连接参数携带 last sequence；token 使用 header 或一次性 ws_ticket。
- 增量 event 带 event_id、device_boot_id、sequence、operation_id。
- App 丢弃 `sequence <= last_applied`。
- 检测 gap 时暂停乐观状态并请求 snapshot。
- RK boot_id 变化或事件历史不足时，以新 snapshot 为基线。
- position 可 4–10Hz 更新并本地插值，但新 snapshot 覆盖插值。
- 重连使用指数退避 + jitter，连接成功不能直接处理旧缓存增量。

## 14. 错误、幂等和离线

统一错误：

```json
{
  "error": {
    "code": "DEVICE_CAPABILITY_MISMATCH",
    "message": "设备不支持此操作",
    "retryable": false,
    "retry_after_seconds": null,
    "details": {}
  },
  "request_id": "req_...",
  "timestamp": "2026-08-28T10:00:00Z"
}
```

客户端按 code 分支，不解析 message。

| 状态 | 行为 |
|---|---|
| 401 | 中央单次 refresh；RK 重新 exchange；失败回登录/配对 |
| 403 | 显示权限不足，不循环重试 |
| 404 | 刷新列表/快照 |
| 409 version | 拉最新实体并合并/提示 |
| 409 operation unknown | 查询原 operation/snapshot |
| 422 | 映射字段/设备能力错误 |
| 429/503 | 遵循 Retry-After，指数退避，保留页面 |

所有中央创建/修改/触发请求使用 Idempotency-Key。App 生成随机 UUID/128 bit，必须持久到响应确定。

### App 重启恢复

持久化但不包含 secret：

- active device_id；
- live_session_id；
- last_rk_sequence；
- pending operation IDs；
- sync_job_id/manifest_id；
- 上传 submission_id/analysis_run_id。

重启后：重新发现同 device_id → 换 RK token → 拉 snapshot/operation → 合并 sequence → 恢复中央数据。不能重放按钮动作。

## 15. 页面状态要求

每个页面都要设计/测试：

- 首次加载；
- 空数据；
- 刷新/分页；
- 401/403/404/409/422/429/503；
- 中央离线；
- RK 未发现、未授权、断开；
- RK 已连接但未 ready；
- WebSocket 断开/重连；
- 数据为缓存且非实时；
- 分析 pending/partial/failed；
- Manifest/同步失败和设备能力不足。

不能只提供成功态页面。

## 16. 隐私和缓存

- Access token 仅内存；refresh/RK session token 使用系统安全存储。
- 不记录密码、Authorization、refresh、配对码、device proof、签名 URL query。
- P0 不缓存完整歌曲/Stem/Render；RK 自己缓存。
- Preview 按产品缓存策略，URL 过期重新 grant。
- 退出账户清私有缓存和设备 token。
- 崩溃上报只含 request_id/operation_id，不含敏感 body。

## 17. 你必须向其他负责人索取的输入

向后端：

- 通过 CI 校验的 OpenAPI 和环境 Base URL；
- Mock server/成功与错误 fixtures；
- 每个 error code 的 retryable/用户动作；
- token TTL/refresh 行为；
- Preview 时长/格式、上传上限；
- 发布状态和审核文案。

向 RK：

- mDNS/identity/capability/state/operation/event Schema；
- 8 Pad 和低 capability fixture；
- 配对和 session exchange 流程；
- WebSocket replay/snapshot 规则；
- SyncJob/Operation 测试环境；
- 实体键触发的事件示例。

向算法/产品：

- 哪些字段 validated，可确定展示；
- 哪些只能显示“可能”或不显示；
- analysis partial/degraded 文案；
- 试听长度；
- 上传自动公开还是审核后公开最终决定。

## 18. 四方协作统一规范

### 18.1 责任边界

| 负责人 | 负责 | 不负责 |
|---|---|---|
| 后端 | Jetson FastAPI、PostgreSQL、媒体/Manifest、Worker编排、设备云端数据、Gateway | 算法结论、RK现场执行、手机页面 |
| 手机前端 | App 页面、中央客户端、RK连接/状态/控制、用户反馈 | 中央业务真相、算法计算、RK执行事实 |
| 服务端算法 | Jetson 分析 adapter、模型、Schema、质量/验证、Stem/Feature/Style | 用户/设备业务表、手机/RK状态机 |
| RK | edge/sync/audio/input、本地SQLite/缓存、Operation/Event、现场事实 | 中央用户曲库、公共审核、服务端分析 |

### 18.2 合同唯一来源

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

### 18.3 数据和协议规则

- 新 ID 使用 UUID；重试不更换 operation_id/event_id/sync_job_id。
- 时间使用 RFC 3339 UTC；顺序使用 version/sequence，不靠跨机器时钟排序。
- 未知值使用 null；禁止用 0、空字符串或空数组冒充未知事实。
- 枚举只可兼容新增；删除/改语义必须升级版本。
- 状态转换必须有允许表，终态不回退。
- 写操作有 Idempotency-Key/request hash；消费者必须容忍重复消息。
- 中央业务以 PostgreSQL 为准；算法语义以 versioned artifact 为准；现场事实以 RK 最大 sequence 为准；页面只是投影。
- 日志统一 request_id/correlation_id/analysis_run_id/manifest_id/sync_job_id/operation_id/event_id。
- token、配对码、proof、签名 URL、NAS 路径不进入日志/fixture。

### 18.4 版本和共享 Fixture

- Central API：`/api/v1` + OpenAPI version。
- Analysis：contract/schema/pipeline/model/calibration 分别版本化。
- RK：control/event/capability 版本化并 capability negotiation。
- Manifest/PadPreset：schema version + immutable version/hash。
- 发布提供 git SHA、release ID、数据库/SQLite revision、模型/协议版本。
- 跨端升级至少验证当前版和前一兼容版；不兼容时明确拒绝。
- 共享 Schema/fixture 放在 `contracts/schemas/`、`contracts/fixtures/`。
- 每个合同至少有 success、null/degraded、invalid、unauthorized、conflict、timeout/retry、旧版兼容示例。

### 18.5 联调门槛和共同完成定义

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

## 19. 最终交付清单

- OpenAPI 生成的 Central API client；
- Auth/Catalog/Library/Playlist/Upload/Analysis repositories；
- Device discovery/pairing/RK API/WS repository；
- 三类连接状态和 capability gate；
- 动态 PadPreset 编辑；
- Prepare/Manifest/Sync 页面；
- Live operation 状态机和 timeout_unknown 恢复；
- token 安全存储、refresh 单飞、退出清理；
- 页面加载/空/错/离线/断线设计；
- Central/RK Mock fixtures 和回放测试；
- 单元、Widget、集成和真机端到端测试报告。

## 20. 完成标准

- 未连接 RK 时能登录/浏览/整理/上传/试听，但所有设备/现场按钮正确禁用；
- App 永远拿不到完整歌曲/Stem 的手机播放 URL；
- 设备 online 与局域网 connected 不混用；
- 4 Pad/8 Pad/无 Stem 等 capability 页面都正确；
- App 退出不影响 RK 同步/现场；
- HTTP/WS 响应丢失不会导致操作执行两次；
- WS gap、RK reboot、App reboot 后能用 snapshot/sequence恢复；
- 中央断网时 RK 已缓存现场仍可控制，App 不代替 RK 上传事实；
- 删除个人曲库只移除 UI 关联；
- 低置信算法结果不会显示成确定事实；
- 日志、缓存和崩溃报告无 token/配对 secret/签名 URL；
- 后端 OpenAPI、RK Schema 和前端生成模型无字段漂移。

## 21. 仓库内详细合同位置

- `docs/backend-handoff-v1/06_手机后端API.openapi.yaml`
- `docs/backend-handoff-v1/07_前端页面与API字段映射.md`
- `docs/backend-handoff-v1/08_RK设备能力与控制协议.md`
- `docs/backend-handoff-v1/09_资源Manifest与同步协议.md`
- `docs/backend-handoff-v1/10_错误码幂等与离线恢复.md`
- `docs/backend-handoff-v1/12_联调测试与验收用例.md`
