# HarBeat 四方协作开发总则

版本：`v1.1-draft`
适用角色：后端、手机前端、服务端音乐算法、RK3588
协作分支：`integration/harbeat-contract-first-v1`

## 1. 本轮共同目标

本轮目标不是让四方分别“把自己的页面或接口做出来”，而是形成一个可以稳定部署、升级、断网恢复和共同验收的完整系统：

```text
Jetson + NAS
  ├─ FastAPI / PostgreSQL / Redis / Worker
  ├─ 用户、曲库、设备、任务和事件业务真相
  └─ 原曲、Preview、Stem、Render 和分析产物

阿里云
  └─ 公网 HTTPS Gateway、TLS、限流、到 Jetson 的私网隧道

手机 App
  ├─ 中央用户业务客户端
  ├─ RK 局域网控制器
  └─ 手机热点，为 RK 提供局域网和互联网

RK3588
  ├─ 现场权威执行器
  ├─ 资源缓存、播放、混音、Pad、实体键、DSP
  └─ 离线事实记录和恢复联网后的补传
```

最终系统必须满足：中央业务可以独立使用；现场操作不依赖云端实时响应；资源不经过手机中转；每一份数据都有唯一权威来源；接口变化有版本、fixture、评审和兼容方案。

## 2. 已冻结的架构与产品规则

以下内容任何负责人不得自行改变：

1. Jetson + NAS 是中央业务、数据库、分析计算和媒体资产中心。
2. 阿里云只做公网 Gateway 和到 Jetson 的私网转发，不建立第二套业务数据库或分析系统。
3. 手机开启热点，RK 加入热点；手机与 RK 走局域网，RK 经热点直接访问阿里云公网 HTTPS。
4. 手机向 RK 发送 Manifest、同步任务和控制意图；歌曲、Stem、Render、Pad 资源由 RK 直接下载。
5. 现场播放、混音、Pad、固定控制、实体按键和底层 DSP 全部在 RK 本地执行。
6. RK 是现场状态和 executed 事实的权威源；手机不能通过本地按钮状态伪造执行成功，Jetson不能反向生成 RK 已执行事实。
7. RK 断网时保存 Operation/Event/Outbox，恢复后补传；重复上传不得生成重复中央事件。
8. 一台 RK 只有一个 Owner，可临时授权 controller/viewer；一个用户可拥有多台 RK。
9. Pad 数量和实体按键不能由后端或 App 永久写死。当前界面可以按 8 Pad 设计，但必须读取 RK capability。
10. 播放/暂停、下一首、能量提高/降低、延长、Talk、Undo 是固定控制，不占 Pad 槽。
11. Track 是全局曲目；个人曲库保存用户与 Track 的关联。用户移除歌曲时先删除/软删除个人关联，不正常删除全局 Track、资产或 NAS 文件。
12. 手机未连接并验证 RK 时，可以登录、浏览、整理、上传、查看分析和播放 Preview；不能完整播放、同步 RK 资源或使用现场功能。
13. 用户上传后的公开策略暂未最终冻结。统一状态机必须兼容 `pending_review -> published/rejected/blocked`，默认按审核后公开实现，禁止把“分析成功”和“公开成功”合并为一个状态。

## 3. 四方责任边界

| 角色 | 对结果负责 | 明确不负责 |
|---|---|---|
| 后端 | Jetson FastAPI、PostgreSQL、Redis、Worker 编排、中央业务、资产、Manifest、设备云端数据、事件接收、阿里云 Gateway 配置 | 音乐算法结论、RK 毫秒级执行、手机页面、底层 DSP |
| 服务端算法 | Core/Stem/Feature/Style 算法、stage adapter、算法 Schema、模型/阈值/校准、质量语义、验证和性能报告 | 用户/设备业务表、API 权限、Worker 租约重试、手机/RK状态机 |
| 手机前端 | Flutter 页面、中央 API 客户端、RK 发现/配对/状态/控制、用户可理解的错误和恢复 | 中央业务真相、算法计算、RK executed 事实、音频文件中转 |
| RK | edge-agent、sync-worker、audio-engine、input-daemon、SQLite、缓存、Operation/Event/Outbox、现场执行 | 用户登录、公共曲库审核、中央资产生命周期、服务端音乐分析 |

任何跨边界功能必须拆成合同和两端任务。例如“同步歌曲”不是一个人的任务：后端生成 Manifest/授权，App 发起并展示，RK 下载/校验/恢复，算法评审 runtime metadata 是否足够。

## 4. 数据权威来源

| 数据 | 权威源 | 其他端允许保存什么 | 冲突规则 |
|---|---|---|---|
| 用户、登录、权限 | Jetson PostgreSQL | App 安全 token/只读缓存 | 服务端 session/version 为准 |
| 公共曲库和发布状态 | Jetson PostgreSQL | App/RK 有版本缓存 | 服务端 version/ETag 为准 |
| 个人曲库、歌单、准备草稿 | Jetson PostgreSQL | App 草稿或只读缓存 | If-Match/版本冲突，不静默覆盖 |
| 媒体文件 | NAS + `media_assets` 元数据 | RK 内容寻址缓存 | sha256/size 不符立即废弃 |
| 分析 Run/Stage/Artifact | PostgreSQL | Redis 只传任务；App 只读摘要 | PostgreSQL 状态为准 |
| 算法语义 | 版本化 analysis artifact | App/RK 只收投影 | schema/pipeline/model/calibration 版本共同决定 |
| 设备 Owner/授权 | PostgreSQL；RK 缓存短期授权 | App 当前 session | 撤销/过期后拒绝新操作 |
| RK capability | RK 当前运行时 | Jetson 最近报告、App 当前快照 | 在线时以 RK 新 report_version 为准 |
| 现场播放、控制和执行 | RK | App WS 快照、Jetson 事件副本 | RK 最大合法 sequence 为准 |
| 同步完成状态 | RK | Jetson/App 镜像 | 只有 RK 校验全部资产后可声明 ready |

## 5. 共享合同唯一来源

仓库根目录 `contracts/` 是新合同的唯一归档入口。详细设计可以在 Markdown 中讨论，但可执行字段必须进入机器可读合同。

| 合同 | 主维护人 | 必须批准人 | 消费者 |
|---|---|---|---|
| 中央手机 OpenAPI | 后端 | 手机前端；算法评审 AnalysisSummary | App、Mock、后端合同测试 |
| 音乐分析输入输出 Schema | 算法 | 后端 | Worker；App/RK只消费投影 |
| RK Capability/Control/State/Event Schema | RK | 后端、手机前端 | App、RK、中央事件接收 |
| Manifest/Asset/Sync Schema | 后端与 RK | 算法、手机前端 | RK 下载、App 展示、后端生成 |
| 公共错误码和幂等规则 | 后端 | 手机前端、RK、算法评审相关码 | 四方 |
| App 页面字段映射 | 手机前端 | 后端、产品 | App 测试和产品验收 |

当前 `docs/backend-handoff-v1/06_手机后端API.openapi.yaml` 是中央 API 草案；`modules/*/contracts` 是历史或模块级合同。迁移到 `contracts/` 并通过评审前，不得把它们称为冻结生产合同。

## 6. 全局字段和协议规则

### 6.1 ID 和时间

- 新业务 ID 使用 UUID；旧整数 ID 只作为迁移映射。
- 任何实体 ID 不通过标题、文件名或数组位置推导。
- 时间戳统一 RFC 3339 UTC。
- 毫秒级媒体时间使用整数 `*_ms`；禁止同一字段在不同端使用秒和毫秒。
- 跨机器事件顺序使用 version/sequence，不使用设备墙上时钟排序。

### 6.2 未知值和枚举

- 未知事实使用 `null` 或明确的 `unavailable`，不使用 0、空字符串、空数组伪装未知。
- 枚举只允许兼容新增；删除、改名、改语义必须升级合同主版本。
- 消费端遇到未知枚举必须进入安全降级，不能崩溃或当成成功。
- 终态不能回退；需要重做时创建新 Run/Operation/Manifest version。

### 6.3 幂等和重复消息

- 中央写请求使用 `Idempotency-Key + request hash`。
- Worker 使用 `analysis_run_id + stage_key + attempt_token`。
- RK Operation 重试保持同一个 `operation_id`。
- RK Event 重传保持同一个 `event_id` 和 `device_sequence`。
- 同一 key 配不同 payload 必须返回 conflict，不能覆盖旧请求。

### 6.4 文件和安全

- API/Manifest 不得包含 `/mnt/nas`、Jetson 私网地址、Tailscale 地址或任意本地绝对路径。
- 文件资产必须有 `asset_id/storage_key/size_bytes/sha256/content_type`。
- Ready 资产不可原地覆盖；新版本创建新 asset。
- token、配对码、proof、签名 URL、NAS 路径不得进入日志、fixture 和截图。
- App 不保存 device credential；RK 不接收用户 refresh token。

## 7. 当前代码基线与共同认知

### 7.1 后端

`app/` 已有 FastAPI、SQLAlchemy、认证、用户、曲库、播放列表、资产、Manifest、推荐、Session 等模块，但当前领域模型仍以 `Song/LibrarySong` 和旧路由为主。分析通过 FastAPI `BackgroundTasks` 运行，尚无正式 AnalysisRun/StageRun/Redis Worker/Alembic 生产基线。

结论：业务和算法能力可复用，但领域模型、权限、任务编排和资产合同属于 `PARTIAL`，不能围绕旧表继续堆叠新协议。

### 7.2 服务端音乐算法

`app/modules/library/` 已有 Core、Demucs、鼓/Bass/Feature、21 类 Style 和模型验证代码。当前完整测试基线为 `568 passed, 3 skipped`，但仍存在：未提交算法文件、旧扁平秒单位输出、无统一 stage adapter、Drum v3/v4 Schema 漂移、Pre-style v5 枚举漂移、Style 必要条件未消费 `style_required_allowed`、21 类 Style 验证不足。

结论：算法主体为 `CURRENT/PARTIAL`；生产合同、版本发布和 Style confirmed 能力为 `MISSING/VALIDATION_BLOCKED`。

### 7.3 手机前端

`mobile/` 已有 Flutter App、中央 `api_client`、曲库/导入页面、DJ 控制页面、`edge_agent_client` 和 `sync_worker_client`。目标上手机必须只访问 RK edge-agent，但旧代码仍可能直接访问 sync-worker 或使用旧 `/live/*` 路径。

结论：UI 和客户端骨架可复用；生成 OpenAPI 客户端、双连接状态、正式配对/同步/Operation 和重启恢复为 `PARTIAL/MISSING`。

### 7.4 RK

`cypher-integration/rk3588-edge/` 已有 edge-agent、sync-worker、audio-engine、input-daemon、systemd 和测试。当前配对存在 mock/分叉实现，同步状态主要在内存，SQLite Operation/Event/Outbox 与重启恢复未闭环，手机与 edge 路由仍有漂移。

结论：音频和进程骨架可复用；身份、持久状态、协议收敛、断网恢复和真机验收为 `PARTIAL/MISSING`。

## 8. Git、分支和提交规则

### 8.1 分支

- 四方集成基线：`integration/harbeat-contract-first-v1`。
- 合同变更：`contract/<domain>-<short-name>`。
- 后端：`feature/backend-<module>`。
- 算法：`feature/analysis-<stage-or-model>`。
- 手机：`feature/mobile-<feature>`。
- RK：`feature/rk-<feature>`。
- 紧急修复：`fix/<owner>-<problem>`，仍需补测试和变更说明。

不得在一个提交中混合无关的后端、算法、手机和 RK 重构。共享合同与实现可在同一合并请求中出现，但合同必须先于或同时于消费者测试。

### 8.2 提交和合并请求

推荐提交前缀：`contract`、`backend`、`analysis`、`mobile`、`rk`、`test`、`docs`、`ops`。

每个合并请求必须写明：

- 任务编号和负责人；
- 改动范围与明确不改的范围；
- 对应合同版本；
- 数据库/SQLite/缓存迁移；
- 配置和 secret 变化；
- 测试命令与结果；
- 兼容性、部署顺序和回滚方式；
- 受影响负责人和评审结果。

禁止把“我本地可以”作为验收证据；禁止提交模型、大型音频、token、生产地址和本地绝对路径。

## 9. 合同变更流程

任何新增/改名/改类型/改单位/改状态语义，必须执行：

```text
登记 Change/ADR
→ 修改机器可读合同
→ 增加 success/degraded/error/compatibility fixtures
→ 主维护人自测
→ 所有受影响消费者评审
→ 消费端合同测试通过
→ 实现代码
→ 集成测试
→ release note + 部署/回滚顺序
```

以下行为一律禁止：

- 在群聊中改字段但不改 Schema/OpenAPI；
- 后端、App 或 RK 各自维护一份同名枚举；
- 前端手写复制生成模型并静默改字段；
- 算法在不升级 schema/pipeline version 时改变单位或语义；
- RK 为迁就 App 硬编码当前 8 Pad；
- 用 message 文案代替稳定错误码分支。

## 10. Fixture 和合同测试规则

每个共享合同至少提供：

- success/ready；
- null/unavailable/degraded；
- unauthorized/forbidden；
- conflict/idempotency mismatch；
- timeout/retry/cancel；
- invalid type/missing field/unknown enum；
- 当前版与前一兼容版。

四方不得自己编造“差不多的 Mock”。后端 Mock、算法 adapter、App 测试和 RK simulator 必须读取同一份 fixture。

## 11. 开发和联调阶段门槛

### Gate 0：基线冻结

- 四方提交开工回执；
- 确认分支、负责人和 P0 范围；
- 当前代码/数据库/RK/算法版本可查询；
- 所有冲突和待决策登记。

### Gate 1：合同冻结

- 中央 OpenAPI、Analysis Schema、RK Schema、Manifest Schema 通过对应评审；
- ID、单位、枚举、错误码、幂等键和权限明确；
- 共享 fixtures 可被消费者解析。

### Gate 2：各端实现完成

- 单元和合同测试通过；
- 迁移、重启、重复包和异常测试通过；
- build/version 可查询；
- 没有 secret、本地路径和未版本化输出。

### Gate 3：实验室联调

- 后端 Mock + 算法 fixture Worker；
- App + RK simulator；
- Jetson + 一台 RK + 手机热点；
- 上传→分析→Manifest→同步→现场→断网补传全链路通过。

### Gate 4：真机和发布验收

- Jetson/NAS、阿里云 Gateway、真实手机、真实 RK 和声卡；
- 性能、断网、重启、磁盘水位、token 过期、重复操作、hash 失败验收；
- 发布顺序、兼容窗口和回滚演练完成。

## 12. 四方共同完成定义

跨端功能只有同时具备以下内容才算完成：

1. 明确负责人和责任边界；
2. 机器可读合同及字段说明；
3. 正常、降级、错误和兼容 fixtures；
4. 权限、幂等、状态机和持久化实现；
5. 单元、合同、集成和恢复测试；
6. 日志、指标、版本和安全错误；
7. 配置、部署、迁移和回滚说明；
8. 受影响负责人评审记录；
9. 项目负责人或指定验收人标记 `ACCEPTED`。

“代码完成”“接口能返回 200”“页面能点”“真机偶尔成功”均不等于完成。

## 13. 固定协作节奏

- 每位负责人维护自己的任务状态表，状态变化时更新，不用聊天消息代替。
- 合同评审围绕 Schema/fixture/状态转换表，不围绕口头描述。
- 每次联调只使用带 git SHA、合同版本和数据库/SQLite revision 的构建。
- 阻塞项必须写清负责解决的人和需要的决定；不能只写“等接口”。
- 发现跨端缺陷时先确定权威源和责任合同，再决定修哪一端，禁止四端同时打补丁。

## 14. 当前必须优先形成的四个共同决定

1. `music-analysis-v1` 的真实 Core/Stem/Feature/Style Schema 和 stage adapter。
2. `rk-control-v1/rk-event-v1` 的 Capability、State、Operation、Event 枚举和持久语义。
3. `resource-manifest-v1` 的资源格式、签名下载、inline runtime metadata 上限和兼容策略。
4. 中央 OpenAPI 的 Track/UserLibrary/Upload/AnalysisRun/Device/Prepare/Sync/Live DTO。

这四项没有定稿前，可以开发内部实现和 Mock，但不得宣称跨端联调完成。
