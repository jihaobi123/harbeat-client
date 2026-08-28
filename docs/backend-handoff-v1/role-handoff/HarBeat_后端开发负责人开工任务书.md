# HarBeat 后端开发负责人开工任务书

版本：`v1.0-draft`
基线日期：2026-08-28
仓库基线：`feature/bpm-three-engine-consensus` / `d71acfa29cc7a0b3db0d09adea87fc73828b914f`
收件人：后端业务与平台开发负责人

## 1. 你需要交付的最终结果

你负责实现 Jetson 上的中央业务后端、数据库、异步分析任务编排、媒体资源服务和设备云端控制面，并配合运维完成阿里云公网 Gateway。

最终交付不是一个单体 FastAPI Demo，而是以下可恢复、可测试、可部署的系统：

- 用户注册、登录、refresh rotation、注销和对象级权限；
- 公共曲目目录、个人曲库关联、歌单、准备草稿和上传审核；
- 原曲、试听、Stem、Render、Pad 音效等资产元数据和授权下载；
- PostgreSQL 持久分析任务、Redis 投递、独立 Worker 和结果校验；
- RK 设备、Owner、临时授权、配对、能力镜像；
- PadPreset、Manifest、SyncJob、LiveSession、Operation、设备事件；
- 统一错误码、幂等、审计、离线补传和冲突恢复；
- Jetson 发布、阿里云 HTTPS Gateway、监控、备份和回滚。

RK 的底层 DSP、声卡、实体按键和现场音频执行不属于你的算法实现范围，但你负责和 RK 负责人共同定稿设备、同步、控制和事件协议。

## 2. 已冻结的架构，不要自行改变

```text
手机 App
  ├─ HTTPS → 阿里云 Gateway → 私网隧道 → Jetson FastAPI
  └─ 局域网 REST/WS → RK3588

RK3588
  ├─ 通过手机热点联网
  ├─ HTTPS → 阿里云 Gateway → Jetson/NAS 拉取资源
  ├─ 本地执行播放、混音、Pad、实体键、DSP
  └─ 本地保存事件，联网后 → Jetson 批量补传

Jetson
  ├─ FastAPI
  ├─ PostgreSQL：业务与任务真相
  ├─ Redis：队列/短期协调，不是持久真相
  ├─ Analysis Workers
  └─ NAS：原曲/试听/Stem/Render

阿里云
  └─ TLS/Nginx/限流/隧道，不保存业务主数据，不运行音乐分析
```

必须遵守：

1. 现场控制不经过 Jetson 实时决策；RK 是现场执行事实的权威源。
2. 手机不转发音频大文件，也不替 RK 保存执行事实。
3. PostgreSQL 是业务和任务状态真相；Redis 消息丢失后必须可从数据库恢复。
4. NAS 是媒体文件真相；数据库保存资产元数据、相对 storage key、size 和 sha256。
5. API 不返回 `/mnt/nas/...`、Jetson 私网或 Tailscale 地址。
6. 普通 RK 通过阿里云公网 HTTPS 下载，不要求加入 Tailscale。

## 3. 已冻结的产品规则

- 一台 RK 只有一个 Owner，可授权其他用户临时控制；一个用户可以有多台 RK。
- 手机未连接并验证 RK 时，可登录、浏览公开曲库、整理个人曲库/歌单、上传、查看分析和播放试听。
- 手机未连接 RK 时不能完整播放、同步设备资源或使用现场控制。
- 完整歌曲和现场混音由 RK 输出，不在手机端实现完整播放。
- 全局曲目只有一份；个人曲库是用户与 Track 的关联。
- 用户从个人曲库删除歌曲时，只删除个人关联，不删除 Track、资产或 NAS 文件。
- Pad 数量不能写死。当前 UI 可按 8 个 Pad 设计，但实际槽位由 RK capability 上报。
- 播放/暂停、下一首、能量提高/降低、延长、Talk、Undo 是固定控制，不占 Pad 槽。

上传公开策略暂时采用可配置状态机：

```text
draft → processing → pending_review → published | rejected | blocked
```

默认 `CATALOG_AUTO_PUBLISH=false`：上传者分析后立即在个人曲库看到，其他用户审核通过后才能看到。如果产品确认自动公开，只切配置和状态转换，不改表结构。

## 4. 当前仓库位置

仓库根：`harbeat-client/`

| 路径 | 当前内容 | 本轮处理 |
|---|---|---|
| `app/` | Jetson FastAPI、SQLAlchemy、业务路由、算法入口 | 中央后端主要开发位置 |
| `app/modules/auth`, `users` | 当前注册登录/用户 | 重做密码、refresh、对象级鉴权 |
| `app/modules/library`, `music` | 用户曲库、上传、分析、Stem | 拆为 Catalog/UserLibrary/Media/Analysis |
| `app/modules/library/background_tasks.py` | FastAPI BackgroundTasks 分析 | 替换为 PostgreSQL + Redis Worker |
| `app/modules/assets`, `stream` | 当前媒体/Range 接口 | 收敛为受权 asset_id 下载 |
| `app/modules/playlists` | 当前歌单 | 改用全局 track_id、version/If-Match |
| `app/modules/manifest` | 当前 Manifest | 按版本化、强 hash、签名规则重写 |
| `app/modules/recommendations`, `profiles` | 推荐与画像 | 接新 Track/反馈模型，低质量特征降级 |
| `app/modules/session`, `sessions` | 两套会话概念 | 收敛为 LiveSession/Operation/DeviceEvent |
| `app/modules/dj_control`, `dj_set`, `dev_mix` | DJ/规划内部能力 | 作为内部服务，不直接开放复杂 P0 控制 |
| `mobile/` | Flutter App | 依据 OpenAPI 生成客户端 |
| `web/` | React Web | 可用于管理审核/运维，不是手机现场主端 |
| `cypher-integration/rk3588-edge/` | RK edge/audio/sync/input | 与 RK 负责人联调，不在中央进程运行 |
| `modules/` | 抽取模块/合同草案 | 可参考，不能假设等于线上版本 |

当前生产现状：

- Jetson 上有完整 FastAPI、PostgreSQL 14、Redis、NAS；
- FastAPI 当前单 Uvicorn Worker；没有独立分析 Worker；
- `ENABLE_STARTUP_ANALYSIS=0`；必须保持，不能启动时扫描重分析；
- 阿里云已有 Nginx/轻量 Gateway，没有业务数据库/分析程序；
- 当前代码、`modules/` 和 Jetson release 存在版本漂移；必须提供 `/api/v1/system/build`。

## 5. 目标领域模型

### 身份

- `users`
- `refresh_sessions`
- `audit_logs`
- `idempotency_records`

### 曲目与用户内容

- `tracks`：全局曲目；UUID；唯一 content_sha256；发布/分析状态。
- `user_library_items`：用户与 Track 关联；删除只设置 removed_at。
- `upload_submissions`：上传会话和校验状态。
- `catalog_reviews`：审核历史，不覆盖。
- `playlists`, `playlist_items`
- `prepare_drafts`, `prepare_items`, `prepare_snapshots`

### 媒体和算法

- `media_assets`：kind/variant/storage_key/size/sha256/format/status。
- `analysis_runs`
- `analysis_stage_runs`
- `analysis_artifacts`
- `outbox_events`

### 设备和现场

- `devices`
- `device_bindings`
- `pairing_tickets`
- `device_capability_reports`
- `pad_presets`, `pad_preset_versions`, `pad_slots`
- `resource_manifests`
- `sync_jobs`, `sync_items`
- `live_sessions`
- `operations`
- `device_events`

统一要求：

- 新业务 ID 使用 UUID 字符串；旧整数只存迁移映射。
- 时间使用 PostgreSQL `timestamptz` UTC 和 RFC 3339 API 字符串。
- 可编辑实体有 `version`，使用 If-Match 乐观锁。
- JSONB 必须有 schema_name/schema_version。
- 文件路径不对外，资产发布后不可原地覆盖。
- 同一用户/Track 只能有一个活动个人库关联。
- 同一 `device_id + event_id` 事件唯一；旧 sequence 不覆盖新状态。

## 6. P0 模块任务

### BE-00 工程和数据库基线

- 引入 Alembic；从空库和旧生产快照升级。
- 生产关闭 `Base.metadata.create_all()`。
- 统一 Settings、错误外壳、request/correlation ID。
- 补开发 PostgreSQL/Redis Compose；当前 Compose 与 README 有漂移。
- 实现 `/api/v1/system/build`：git SHA、release、DB revision、分析/Manifest 合同版本。
- 建 `legacy_id_map`，迁移旧 Song/LibrarySong，不按歌名艺人盲目去重。

完成标准：migration、回滚方案、迁移对账、CI 空库/旧快照测试。

### BE-01 身份和权限

- 密码改 Argon2id。
- Access token 15–30 分钟；refresh token rotation、hash 存库、撤销和 reuse detection。
- `/auth/register/login/refresh/logout`, `/me`。
- 所有 user_id 从 token sub 获取，禁止请求体冒充。
- reviewer/admin 管理权限和对象级授权。
- 登录/配对/资源 grant 限流、审计、日志脱敏。

### BE-02 公共目录、个人曲库和歌单

- 公共目录只返回 `published` Track。
- 提交者可以看到自己的 processing/pending/rejected Track。
- `PUT /me/library/{track_id}` 幂等加入。
- `DELETE /me/library/{track_id}` 只删除关联，重复返回 204。
- 歌单/草稿用 track_id、version/If-Match。
- 审核 API 支持 publish/reject/block，并保存不可变审核历史。

### BE-03 上传和媒体

上传流程：

```text
POST /uploads
→ PUT /uploads/{id}/content
→ POST /uploads/{id}/complete
→ 媒体探测/size/hash
→ Track + user_library_item + analysis_run
```

- filename 不参与文件路径。
- 验证 MIME/codec/音轨/大小/hash。
- 相同 content_sha256 复用 Track/分析，新增用户关联。
- NAS 使用 staging → 校验 → 原子 ready。
- 生成 preview/waveform；手机只拿短期 preview grant。
- 资产下载支持 Range、Content-Length、ETag、sha256。

### BE-04 分析编排和 Worker

当前算法顺序：

```text
core → stem_separation → feature_analysis → style_analysis
core → media_derivatives(preview/waveform)
```

Run 状态：

```text
created → queued → running → succeeded | partial | failed | canceled
                       └→ retry_wait → queued
```

要求：

- PostgreSQL 保存 Run/Stage/lease/attempt/result；Redis 只投递 stage ID。
- 独立 API、dispatcher、core/stem/feature/style/media Worker、reaper 进程。
- Worker 20 秒心跳、约 90 秒 lease，具体值经测试调整。
- Stem GPU 初始并发 1，Demucs timeout 初始 1800 秒。
- 每阶段有 attempt_token；丢失 lease 的旧 Worker 不能提交结果。
- 先校验算法 JSON Schema、文件 size/hash/媒体格式，再提交 artifact/asset。
- optional style 失败可 partial；Core 失败必须 failed。
- Redis 清空、Worker/API/Jetson重启后任务可恢复。

算法只输出 artifact/文件，不直接改用户、设备和曲库业务表。

### BE-05 设备、配对和授权

- 一个 Device 一个 Owner；一个用户多个 Device。
- 临时 controller/viewer 必须有 permissions 和 expires_at。
- 配对码只存 hash，TTL 建议 5 分钟、最多 5 次尝试。
- 手机中央 claim + RK 本地物理确认 + 中央 finalize。
- Device token 与 User token audience 分离，只存 token hash。
- 保存 RK capability report，后端不能写死 Pad 数量/codec。

### BE-06 PadPreset、准备、Manifest 和同步

- PadPreset 发布后不可变；编辑产生新版本。
- 逻辑 `slot_id` 与实体 keycode 分离。
- Freeze PrepareDraft 时根据设备 capability 生成不可变 Manifest。
- Manifest 每个 asset 必须有 asset_id/kind/required/size/sha256/format/cache policy。
- Manifest 绑定 capability hash、analysis run、preset version；进行 content hash/签名。
- Asset grant 短期、限定 device/manifest/asset，只返回阿里云 HTTPS URL。
- SyncJob 中央状态只是 RK 报告镜像；只接受更大的 `rk_sequence`。
- 所有 required asset ready 才能 cache_ready。

### BE-07 会话、操作和设备事件

- 中央创建 LiveSession 记录，但 RK 是实时状态权威。
- Operation ID 全链路复用；同 ID 同 payload 返回原状态，不同 payload 409。
- `POST /api/v1/device/events:batch` 使用 Device token。
- 以 `(device_id,event_id)` 去重，以 `(session,sequence)` 检测缺口。
- Ack 返回 accepted、duplicate、highest_contiguous_sequence、missing_ranges。
- 重复批次不能重复入库；序号缺口补齐后推进 contiguous。

## 7. 手机 API 范围

机器可读合同位于：

`docs/backend-handoff-v1/06_手机后端API.openapi.yaml`

必须实现的 API 分组：

- Auth/Profile
- Catalog/Preview
- Upload/Analysis
- User Library/Playlist
- Devices/Pairing/Binding
- PadPreset/PrepareDraft
- Manifest/SyncJob
- LiveSession/Device Event Batch
- Recommendations/Feedback
- Admin Catalog Review

OpenAPI 是前端生成客户端和合同测试真相。破坏性字段变化必须评审并升级版本；不能只改 FastAPI 实现。

统一错误：

```json
{
  "error": {
    "code": "RESOURCE_VERSION_CONFLICT",
    "message": "内容已更新",
    "retryable": false,
    "retry_after_seconds": null,
    "details": {"current_version": 4}
  },
  "request_id": "req_...",
  "timestamp": "2026-08-28T10:00:00Z"
}
```

所有创建/触发/修改类 API 使用 Idempotency-Key；同键同请求重放原响应，同键不同请求返回 `IDEMPOTENCY_KEY_REUSED`。

## 8. 与服务端算法的接口

算法输入：受信任的 analysis_run/track/input_asset 信息、storage key、sha256、媒体信息、pipeline/version、deadline。

算法阶段产物：

- Core：BPM/Beat/Downbeat/Key/Cue/Energy/Transition；
- Stem：vocals/drums/bass/other；
- Feature：鼓、Bass、节奏、和声、production、pre-style evidence；
- Style：21 类高频风格候选和置信度；
- Media：preview/waveform/render。

后端责任：

- 为每个 artifact 保存 schema/version/input hash/pipeline/version/quality。
- `validated/provisional/candidate_only/unavailable` 不得混淆。
- JSON 禁 NaN/Infinity；未知值使用 null。
- App 只返回有界 AnalysisSummary，不直接返回整块原始 music_features。
- RK Manifest 只投影运行所需 Beat/Cue/Window/资产引用，不下发模型调试证据。

## 9. 与 RK 的接口

中央不处理现场毫秒级控制。你的范围是：

- 设备 Owner/授权/凭证/配对云端状态；
- capability 最近快照；
- PadPreset/Prepare/Manifest/SyncJob；
- scoped asset grant；
- LiveSession 云端记录；
- RK execution event 接收/去重/统计。

手机与 RK 的局域网操作由 RK edge-agent 提供。中央不能根据手机上报伪造 executed。

## 10. 配置和部署

### 开发目标命令

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
python -m app.workers.dispatcher
python -m app.workers.run --queues analysis.core,media.derivatives
pytest -q
```

当前仓库缺少完整 Alembic/Worker/开发 PostgreSQL Compose，这些是你的 P0 基础任务。

### 关键配置

- `DATABASE_URL`, `REDIS_URL`
- `JWT_SECRET`, access/refresh TTL、Argon2 参数
- `UPLOAD_DIR/ASSET_STORAGE_ROOT/ANALYSIS_TEMP_DIR`
- `PUBLIC_ASSET_BASE_URL=https://api.<domain>`
- `MANIFEST_SIGNING_KEY_FILE/KEY_ID`, `ASSET_GRANT_TTL_SECONDS`
- `ANALYSIS_*_TIMEOUT`, heartbeat/lease/max attempts/concurrency
- BPM/Downbeat/Key/Feature/Style 模型和 adapter 配置
- CORS allowlist、上传上限、外部 metadata 开关

生产密钥不能进 Git、镜像、命令行或日志。PostgreSQL/Redis 仅 loopback/容器私网。

### 生产进程

- `harbeat-api`
- `harbeat-dispatcher`
- `harbeat-worker-core`
- `harbeat-worker-stem`
- `harbeat-worker-feature-style`
- `harbeat-worker-media`
- `harbeat-reaper`
- PostgreSQL、Redis、NAS mount
- 阿里云 Nginx/Gateway

## 11. 安全硬要求

- Argon2id，refresh rotation/revocation/reuse detection。
- 所有对象级授权，禁止信任 body user_id。
- TLS、严格 CORS、请求大小/速率限制。
- 上传防路径穿越、伪 MIME、恶意媒体。
- Asset/Manifest 短期授权和签名，RK 下载域名 allowlist。
- Device credential 与用户 token 分离。
- 敏感日志脱敏：token、配对码、签名 URL、NAS 路径、密码。
- 管理审核、封禁、重试、切换分析版本均写 audit log。
- 备份加密，定期真实恢复演练。

## 12. 交付顺序

1. BE-00：工程、Alembic、统一配置/错误/版本。
2. BE-01/02：身份、Track、个人曲库、歌单、迁移。
3. BE-03/04：上传、媒体、分析 Run/Worker。
4. BE-05：设备、配对、授权和 capability。
5. BE-06：Preset、Prepare、Manifest、SyncJob。
6. BE-07：LiveSession、Operation、Event Batch。
7. Gateway、监控、备份、恢复和全链路联调。

共享枚举、JSON Schema、OpenAPI 和 migration 必须先合并，再让多端并行开发。

## 13. 你必须向其他负责人索取的输入

向算法负责人：

- 各阶段 JSON Schema 和 fixtures；
- 模型 manifest/hash/许可证；
- validated/provisional 边界；
- CPU/GPU/RAM/磁盘和 timeout 报告；
- pipeline/model/calibration 版本。

向前端负责人：

- 页面/API/字段覆盖表；
- 所有加载、空、401/403/409/422/429/离线状态；
- 生成客户端版本和 Mock 场景；
- App client_id、token 存储和重连行为。

向 RK 负责人：

- capability/state/operation/event Schema 和 fixtures；
- 当前实体键/Pad capability；
- 支持的 codec/大小/存储水位；
- sync/operation/outbox 重启恢复测试；
- device credential/pairing proof 实现。

## 14. 四方协作统一规范

### 14.1 责任边界

| 负责人 | 负责 | 不负责 |
|---|---|---|
| 后端 | Jetson FastAPI、PostgreSQL、媒体/Manifest、Worker编排、设备云端数据、Gateway | 算法结论、RK现场执行、手机页面 |
| 手机前端 | App 页面、中央客户端、RK连接/状态/控制、用户反馈 | 中央业务真相、算法计算、RK执行事实 |
| 服务端算法 | Jetson 分析 adapter、模型、Schema、质量/验证、Stem/Feature/Style | 用户/设备业务表、手机/RK状态机 |
| RK | edge/sync/audio/input、本地SQLite/缓存、Operation/Event、现场事实 | 中央用户曲库、公共审核、服务端分析 |

### 14.2 合同唯一来源

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

### 14.3 数据和协议规则

- 新 ID 使用 UUID；重试不更换 operation_id/event_id/sync_job_id。
- 时间使用 RFC 3339 UTC；顺序使用 version/sequence，不靠跨机器时钟排序。
- 未知值使用 null；禁止用 0、空字符串或空数组冒充未知事实。
- 枚举只可兼容新增；删除/改语义必须升级版本。
- 状态转换必须有允许表，终态不回退。
- 写操作有 Idempotency-Key/request hash；消费者必须容忍重复消息。
- 中央业务以 PostgreSQL 为准；算法语义以 versioned artifact 为准；现场事实以 RK 最大 sequence 为准；页面只是投影。
- 日志统一 request_id/correlation_id/analysis_run_id/manifest_id/sync_job_id/operation_id/event_id。
- token、配对码、proof、签名 URL、NAS 路径不进入日志/fixture。

### 14.4 版本和共享 Fixture

- Central API：`/api/v1` + OpenAPI version。
- Analysis：contract/schema/pipeline/model/calibration 分别版本化。
- RK：control/event/capability 版本化并 capability negotiation。
- Manifest/PadPreset：schema version + immutable version/hash。
- 发布提供 git SHA、release ID、数据库/SQLite revision、模型/协议版本。
- 跨端升级至少验证当前版和前一兼容版；不兼容时明确拒绝。
- 共享 Schema/fixture 放在 `contracts/schemas/`、`contracts/fixtures/`。
- 每个合同至少有 success、null/degraded、invalid、unauthorized、conflict、timeout/retry、旧版兼容示例。

### 14.5 联调门槛和共同完成定义

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

## 15. 最终交付清单

- Alembic migration 和旧数据迁移/对账报告；
- ORM、repository/domain service 和 API；
- 可解析 OpenAPI 与 generated client CI；
- Analysis Worker/dispatcher/reaper 和管理 CLI；
- 上传、资产、Preview、Manifest、Sync、Event 服务；
- 统一错误、幂等、审计、限流和对象级权限；
- `.env.example`、开发 Compose、systemd/发布配置；
- 健康/版本、结构化日志、指标、告警和 runbook；
- PostgreSQL/NAS 备份和恢复演练；
- 单元、合同、集成、故障、安全和性能测试报告。

## 16. 完成标准

以下全部通过才算完成：

- 用户 A 不能读取/修改用户 B 的私有对象和设备；
- 相同音频上传只产生一个 Track，多用户拥有各自关联；
- 删除个人曲库关联不删除资产；
- API/Worker/Redis/Jetson 重启不丢分析任务；
- Worker 重复消息/租约接管不产生重复产物；
- 普通 RK 不加入 Tailscale 也能经阿里云 HTTPS 下载并校验；
- 重复 Event Batch 不重复入库，sequence gap 可补齐；
- 手机未连 RK 只有试听，不获得完整歌曲 URL；
- Manifest 每个资产都有 size/sha256，篡改被拒；
- 生产 PG/Redis 不暴露，密钥不入日志；
- 备份恢复、发布回滚、监控告警和端到端联调都有证据。

## 17. 仓库内详细合同位置

如果需要查看某一模块的完整字段和测试矩阵，以这些文件为准：

- `docs/backend-handoff-v1/01_系统架构与职责边界.md`
- `docs/backend-handoff-v1/03_领域模型与数据库设计.md`
- `docs/backend-handoff-v1/04_音乐分析输入输出合同.md`
- `docs/backend-handoff-v1/05_分析任务状态机与Worker规范.md`
- `docs/backend-handoff-v1/06_手机后端API.openapi.yaml`
- `docs/backend-handoff-v1/08_RK设备能力与控制协议.md`
- `docs/backend-handoff-v1/09_资源Manifest与同步协议.md`
- `docs/backend-handoff-v1/10_错误码幂等与离线恢复.md`
- `docs/backend-handoff-v1/11_配置部署安全与运维手册.md`
- `docs/backend-handoff-v1/12_联调测试与验收用例.md`
