# HarBeat 后端负责人开工与协作说明

版本：`v1.1-draft`
收件人：Jetson 中央业务与平台后端负责人
协作分支：`integration/harbeat-contract-first-v1`
详细参考：`docs/backend-handoff-v1/`

## 1. 你的任务结果

你负责把 Jetson 建成 HarBeat 唯一中央业务后端，并为手机、音乐算法 Worker 和 RK 提供稳定、可版本化、可恢复的服务。

你的最终交付必须包括：

- FastAPI `/api/v1` 中央 API；
- PostgreSQL 正式领域模型、Alembic 迁移和数据迁移；
- Redis 任务投递与独立 Worker 编排；
- 用户、公共曲库、个人曲库、歌单、上传、分析 Run、媒体资产；
- 设备 Owner/授权、准备草稿、PadPreset、Manifest、SyncJob；
- LiveSession、Operation 镜像和 RK Event 接收；
- 阿里云 Gateway 到 Jetson 的安全部署配置；
- OpenAPI、错误码、幂等、审计、监控、备份和回滚。

后端不是把当前所有路由继续补字段。核心任务是建立正确的领域真相和跨端合同，并为旧代码提供迁移路径。

## 2. 你必须理解的系统关系

- FastAPI、PostgreSQL、Redis、分析 Worker 实际运行在 Jetson。
- NAS 保存原曲、Preview、Stem、Render、Pad 资源；数据库只保存资产元数据和 storage key。
- 阿里云只做 TLS、公网 Gateway、限流和私网隧道，不建立第二套业务数据库。
- 手机同时连接中央 API 和 RK 局域网 API，但两者身份、状态和错误不能混合。
- RK 直接下载资产；后端生成授权和 Manifest，手机不转发音频。
- 现场 executed 事实以 RK 为准；后端只接收、去重、保存和统计。

## 3. 当前代码状态

主要代码：

| 路径 | 当前内容 | 判断 |
|---|---|---|
| `app/main.py`, `app/modules/router.py` | FastAPI 入口和路由聚合 | CURRENT，可迁移到统一 `/api/v1` |
| `app/modules/auth`, `users` | 登录、用户、JWT | PARTIAL，密码/refresh/撤销/审计需重做 |
| `app/modules/library`, `music` | 上传、用户曲库、分析和媒体入口 | PARTIAL，当前 Track/LibrarySong/分析耦合 |
| `app/modules/library/background_tasks.py` | 串行分析并直接写数据库 | CONFLICT，目标必须是独立持久 Worker |
| `app/modules/assets`, `stream` | 资产/Range 能力 | PARTIAL，必须统一 asset_id 授权和外部 URL |
| `app/modules/playlists` | 歌单 | PARTIAL，迁移到全局 track_id 和版本控制 |
| `app/modules/manifest` | Manifest 思路 | PARTIAL，按 resource-manifest-v1 重写 |
| `app/modules/session`, `sessions` | 两套会话概念 | CONFLICT，收敛为单一 LiveSession/Operation/Event |
| `deploy/`, `docker-compose.yml` | Jetson/网关/开发部署素材 | PARTIAL，配置与真实进程需对账 |

当前 `LibrarySong` 按用户保存大量分析字段；新的全局 Track/AnalysisRun 未落地。不得在旧 `LibrarySong` 上继续增加新一代设备、Manifest 或算法版本字段。

## 4. 你的责任与禁止事项

你负责：

- 中央数据模型、事务、权限、API、任务状态和资产发布；
- 校验算法输入输出，但不改变算法语义；
- 生成 App DTO 和 RK Manifest 投影；
- 设备云端授权和事件持久化，但不决定 RK 本地执行；
- Gateway、安全、运维和可观测性。

你不得：

- 把算法低置信结果自行升级为 confirmed；
- 让 FastAPI 请求进程直接执行长耗时 Demucs/模型推理；
- 用 Redis 代替 PostgreSQL 保存永久任务状态；
- 向 App/RK 返回本地 NAS 路径或 Tailscale 地址；
- 根据 App 按钮点击生成 `executed`；
- 在 OpenAPI 之外新增一套只在实现里存在的字段；
- 为赶进度让 App 直接访问 sync-worker 或 audio-engine。

## 5. P0 任务拆解

### BE-00 工程和版本基线

交付：

- Settings 分层：开发/测试/生产；配置类型、默认值、是否 secret；
- `/api/v1/system/build`：git SHA、release ID、DB revision、OpenAPI/analysis/manifest 合同版本；
- PostgreSQL + Redis 本地开发环境；
- request_id/correlation_id、统一错误外壳和结构化日志；
- 禁止生产依赖 `create_all()`，建立 Alembic 基线。

验收：空库升级、旧数据库快照升级、迁移回滚和数据对账测试通过。

### BE-01 Identity 与权限

交付：

- Argon2id 密码；
- 短期 access token；
- refresh token rotation、hash 存库、撤销和 reuse detection；
- `/auth/register/login/refresh/logout`、`/me`；
- 对象级权限、admin/reviewer 角色、限流和审计。

约束：所有用户身份从 token `sub` 获得，禁止相信请求体中的 `user_id`。

### BE-02 Catalog、个人曲库和歌单

目标模型：

- `tracks`：全局曲目和发布状态；
- `user_library_items`：用户关联；
- `catalog_reviews`：审核历史；
- `playlists/playlist_items`；
- `prepare_drafts/items/snapshots`。

关键规则：

- 公共接口只展示 `published`；
- 上传者可以看到自己的 processing/pending/rejected；
- 从个人曲库移除只操作关联；
- 可编辑实体使用 version/If-Match；
- 分页、排序和筛选语义必须进入 OpenAPI。

### BE-03 Upload 与 Media

交付上传状态机：

```text
created → uploading → uploaded → validating → accepted
                                   └→ rejected/failed
```

必须实现：大小/MIME/容器/音轨/时长/hash 检查；内容去重；临时区隔离；失败保留可诊断记录；成功创建 Track、MediaAsset、用户关联和 AnalysisRun。

资产要求：`asset_id, kind, variant, storage_key, size_bytes, sha256, content_type, status`。下载通过短期受限 URL 或受控 Range 接口，禁止公开真实文件路径。

### BE-04 AnalysisRun 与 Worker

你维护：

- `analysis_runs`；
- `analysis_stage_runs`；
- `analysis_artifacts`；
- Worker lease、heartbeat、attempt、retry、cancel、timeout；
- staged output 的 Schema、NaN、媒体和 hash 校验；
- immutable asset/artifact 登记和 `current_analysis_run_id` 原子切换。

算法负责人维护算法输入输出。后端只通过 `music-analysis-v1` adapter 调用，不导入 FastAPI request/session，不读取算法内部临时对象。

Run 发布门必须区分：Core 必需、Stem/Feature/Style 可形成 partial；具体依赖在合同评审中冻结。

### BE-05 Device、Owner、配对和授权

目标模型：`devices, device_bindings, pairing_tickets, device_capability_reports`。

中央负责 claim/finalize、Owner 唯一约束、临时授权、撤销、设备 credential 和审计；RK 负责本地 proof、物理确认和短期 session token 验证。配对码/proof/token 不写日志。

### BE-06 Preset、Prepare、Manifest 和 Sync

交付：

- PadPreset 不写死 8 槽，依据 capability 校验；
- PrepareDraft 冻结为不可变 snapshot；
- 针对 `device capability + analysis run + asset versions` 生成不可变 Manifest；
- 每个资源有 size/hash/format/compatibility；
- SyncJob 云端只保存期望和 RK 镜像，不替 RK 声称 cache_ready；
- 资源 URL 是短期 scoped grant，可续签，不把 token 固化进长期 Manifest hash。

### BE-07 LiveSession、Operation 镜像和 DeviceEvent

交付：

- 创建/结束 LiveSession 和控制授权；
- Operation 可由 App 直发 RK，中央保存计划/镜像，不作为现场调度器；
- 批量接收 RK Event；
- 按 `device_id + event_id` 去重；
- 检测 sequence 缺口并回执已接受范围；
- 事件 payload 按 schema version 校验和隔离非法数据。

### BE-08 Gateway、运维和安全

- 阿里云 Nginx/TLS/限流/上传超时/隧道健康；
- Jetson API、Worker、PostgreSQL、Redis、NAS 分进程健康；
- 备份、恢复、磁盘水位、队列积压、任务失败率；
- Gateway 隧道失败时快速失败，不写入本地第二套状态；
- secrets 通过受控环境或 secret store，不入库。

## 6. 你主维护的合同

1. 中央 OpenAPI：当前草案 `docs/backend-handoff-v1/06_手机后端API.openapi.yaml`。
2. 数据库模型：`docs/backend-handoff-v1/03_领域模型与数据库设计.md`。
3. Worker 状态机：`docs/backend-handoff-v1/05_分析任务状态机与Worker规范.md`。
4. Manifest：与 RK 共同维护 `resource-manifest-v1`。
5. 错误、幂等和恢复：`docs/backend-handoff-v1/10_错误码幂等与离线恢复.md`。

OpenAPI 发生变化时必须同时更新 fixture、生成客户端兼容测试和版本说明。后端实现不是合同真相，已评审 OpenAPI 才是。

## 7. 你需要从其他负责人取得的输入

算法负责人：

- stage 输入输出 Schema、adapter 和 fixtures；
- Core/Stem/Feature/Style 必需与可降级条件；
- pipeline/model/calibration version；
- timeout、资源、模型部署和错误码；
- App/RK 可公开投影规则。

手机负责人：

- 页面/API/字段覆盖表；
- loading/empty/error/offline/partial 文案；
- 生成客户端版本和 Mock 消费测试；
- token 存储和刷新行为确认。

RK负责人：

- identity/capability/pairing proof；
- Operation/Event/State Schema；
- codec/采样率/声道/最大文件/缓存水位；
- Manifest 和 SyncJob 回执；
- device credential 与离线授权边界。

## 8. 你的第一批提交顺序

1. `contract/mobile-central-api-v1`：先冻结 ID、状态、错误和核心 DTO；
2. Alembic + 新领域模型骨架；
3. Identity/Catalog/UserLibrary；
4. Upload/Media/AnalysisRun；
5. fixture Worker 接入，等待算法正式 adapter；
6. Device/Prepare/Manifest/Sync；
7. LiveSession/Event；
8. Gateway、故障恢复和真机联调。

不要等算法全部完成才写 Worker；可以先用算法共享 fixtures。但不得根据旧 `analyze_audio_file()` 返回字典设计永久数据库字段。

## 9. 完成标准

- 所有 P0 表由 Alembic 管理并通过迁移/回滚测试；
- OpenAPI lint/解析、生成客户端和后端合同测试通过；
- API 权限、对象级授权、幂等和审计齐全；
- Worker 重启、重复投递、timeout、cancel、OOM、非法输出不会留下 ready 半成品；
- 资产 hash、签名访问和 Range 正确，不暴露本地路径；
- RK 重复事件不重复入库，sequence 缺口可诊断；
- `/system/build` 可定位所有合同和发布版本；
- App、算法、RK 负责人完成相关合同评审；
- Jetson/NAS 和阿里云 Gateway 的部署、监控、备份和回滚经过演练。

## 10. 开工回执

请按 `docs/team-development-v1/05_任务状态评审与变更模板.md` 回复，并首先列出你认为中央 OpenAPI、数据库迁移和 Worker 合同中仍需四方决定的问题。
