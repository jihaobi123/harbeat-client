# HarBeat 后端开发交付包

> 四方正式开工入口已整理到 `docs/team-development-v1/`。本目录继续作为详细领域、API、算法、RK、Manifest、错误和验收参考；协作规则、代码归属和负责人开工顺序以新目录为准。

版本：`v1.0-draft`
基线日期：2026-08-28
仓库基线：`feature/bpm-three-engine-consensus` / `d71acfa29cc7a0b3db0d09adea87fc73828b914f`

## 四个可直接单独发送的任务书

这四份文件均为独立任务书，收件人不需要先阅读本 README 才能理解自己的工作；四份文件内含同一套合同、版本、fixture、变更和联调规范：

- [HarBeat_后端开发负责人开工任务书.md](role-handoff/HarBeat_后端开发负责人开工任务书.md)
- [HarBeat_手机前端开发负责人联调任务书.md](role-handoff/HarBeat_手机前端开发负责人联调任务书.md)
- [HarBeat_服务端音乐算法负责人交付任务书.md](role-handoff/HarBeat_服务端音乐算法负责人交付任务书.md)
- [HarBeat_RK开发负责人开工任务书.md](role-handoff/HarBeat_RK开发负责人开工任务书.md)

## 1. 这套文档解决什么问题

本目录是后端、手机前端、服务端音乐算法、RK 四位开发负责人的共同开工基线。它把产品规则、现有代码、Jetson/NAS、阿里云、手机和 RK3588 的职责统一成可实施的接口、数据和验收约束。

本套文档描述的是“目标生产架构”，同时明确标注“当前代码现状”和“必须改造项”。任何与现有代码不一致的地方，以文档中的 `P0` 目标合同作为本轮开发目标，不应通过继续依赖旧行为来规避改造。

上游产品资料作为需求来源，不作为运行时接口合同：

- `HarBeat 手机 App 产品与前端设计规格.md`
- `harbeat-mobile-product-handbook.html`
- `HarBeat 后端技术栈与架构说明.md`

编号 `02` 预留给产品范围与用户故事定稿；本包不伪造该文档。开发阶段的产品决策已分别冻结在 01、07 和本页。

## 2. 已冻结的产品与架构决策

| 编号 | 决策 |
|---|---|
| D-01 | Jetson + NAS 是业务数据、音乐资产和分析计算中心；PostgreSQL、Redis、FastAPI 和分析 Worker 均运行在 Jetson 侧。 |
| D-02 | 阿里云只承担公网 HTTPS 入口、反向代理、限流和到 Jetson 私网隧道，不保存业务主数据，不运行音乐分析。 |
| D-03 | 手机是用户控制器和 RK 联网入口。手机开热点，RK 加入热点并访问互联网。 |
| D-04 | 手机给 RK 下发预设、Manifest 或操作；RK 通过阿里云 HTTPS 网关直接拉取 Jetson/NAS 资源，音频不经过手机中转。 |
| D-05 | 现场播放、混音、Pad、固定按键和底层 DSP 全部在 RK 本地执行，不能依赖云端实时响应。 |
| D-06 | RK 是现场执行事实的权威源。RK 断网时本地保存事件，恢复后补传；手机只展示 RK 状态，不代替 RK 记账。 |
| D-07 | 一台 RK 只有一个 Owner，可给其他用户临时控制授权；一个用户可以拥有多台 RK。 |
| D-08 | Pad 数量和实体键位不能在云端写死。RK 上报能力，预设使用逻辑 `slot_id`，RK 映射到具体硬件键。 |
| D-09 | 曲目是全局公共目录实体；个人曲库只保存用户与曲目的关系。用户“删除歌曲”只删除个人关联，不删除全局曲目和文件。 |
| D-10 | 手机未连接 RK 时可以登录、浏览公开曲库、整理个人曲库与歌单、提交上传；只能播放试听片段，不能完整播放或使用设备/现场功能。 |

## 3. 一项待产品最终确认但不阻塞开发的配置

“用户上传后立即公开，还是审核后公开”尚未得到无歧义确认。本包采用兼容两种策略的状态模型：

`draft -> processing -> pending_review -> published | rejected | blocked`

默认配置为 `CATALOG_AUTO_PUBLISH=false`：上传者在分析成功后立即能在个人曲库看到曲目，其他用户只在管理员审核为 `published` 后可见。如果产品决定立即公开，只需改为自动从 `processing` 进入 `published`，无需修改表结构或 App 合同。

## 4. 文件、负责人和评审人

| 文件 | 主负责人 | 必须评审方 | 开工用途 |
|---|---|---|---|
| [01_系统架构与职责边界.md](01_系统架构与职责边界.md) | 架构师/后端 | 算法、前端、RK | 统一系统边界、数据真相和代码位置 |
| [03_领域模型与数据库设计.md](03_领域模型与数据库设计.md) | 后端 | 算法、前端 | 建库、迁移、约束与生命周期 |
| [04_音乐分析输入输出合同.md](04_音乐分析输入输出合同.md) | 算法 | 后端 | 固定算法输入、产物、质量与版本语义 |
| [05_分析任务状态机与Worker规范.md](05_分析任务状态机与Worker规范.md) | 后端 | 算法、运维 | 实现可恢复的异步分析流水线 |
| [06_手机后端API.openapi.yaml](06_手机后端API.openapi.yaml) | 后端 | 前端 | 生成客户端、Mock 和 API 契约测试 |
| [07_前端页面与API字段映射.md](07_前端页面与API字段映射.md) | 前端 | 后端、产品 | 页面字段、状态、权限和接口映射 |
| [08_RK设备能力与控制协议.md](08_RK设备能力与控制协议.md) | RK/后端 | 前端 | 配对、能力、预设、实时控制和事实回传 |
| [09_资源Manifest与同步协议.md](09_资源Manifest与同步协议.md) | 后端/RK | 算法、前端 | 资源清单、校验、缓存和断点恢复 |
| [10_错误码幂等与离线恢复.md](10_错误码幂等与离线恢复.md) | 后端 | 前端、RK | 统一失败语义、重试和离线补偿 |
| [11_配置部署安全与运维手册.md](11_配置部署安全与运维手册.md) | 后端/运维 | 架构师 | Jetson/阿里云部署、密钥、监控和备份 |
| [12_联调测试与验收用例.md](12_联调测试与验收用例.md) | 测试/架构师 | 全员 | 把交付范围转成可执行验收标准 |

### 4.1 发给后端开发负责人的文档

建议标题：`HarBeat 后端业务与平台开发包`

按以下顺序阅读：

| 级别 | 文档 | 后端需要解决的问题 |
|---|---|---|
| 必读 1 | `README.md` | 冻结决策、工作分解、开工顺序 |
| 必读 2 | `01_系统架构与职责边界.md` | Jetson、NAS、阿里云、手机、RK 各自负责什么；现有代码在哪里 |
| 必读 3 | `03_领域模型与数据库设计.md` | Track、个人曲库、上传、资产、任务、设备、同步、事件如何建表和迁移 |
| 必读 4 | `05_分析任务状态机与Worker规范.md` | 如何把当前 BackgroundTasks 改成 PostgreSQL + Redis 持久 Worker |
| 必读 5 | `06_手机后端API.openapi.yaml` | 需要实现的手机业务 API、字段、认证和响应 |
| 必读 6 | `10_错误码幂等与离线恢复.md` | 幂等、版本冲突、断网、重复请求和恢复策略 |
| 必读 7 | `11_配置部署安全与运维手册.md` | 本地开发、Jetson部署、阿里云 Gateway、安全、监控、备份 |
| 必读 8 | `12_联调测试与验收用例.md` | 后端完成标准和端到端验收 |
| 接口必读 | `04_音乐分析输入输出合同.md` | 后端如何调用算法、验证结果、保存 artifact；不能自行改变算法语义 |
| 联调必读 | `08_RK设备能力与控制协议.md` | 后端设备、Owner、授权、事件和 RK 协议责任 |
| 联调必读 | `09_资源Manifest与同步协议.md` | Manifest、资源授权、SyncJob 和 RK 直拉链路 |
| 评审参考 | `07_前端页面与API字段映射.md` | 检查 API 是否覆盖页面、连接状态和错误态 |

后端最终必须交付：Alembic、ORM/领域服务、OpenAPI 实现、认证权限、上传/媒体、独立 Worker、设备/Manifest/事件 API、Gateway 配置、监控备份和测试报告。

### 4.2 发给手机前端开发负责人的文档

建议标题：`HarBeat 手机 App 接口与设备联调包`

按以下顺序阅读：

| 级别 | 文档 | 前端需要解决的问题 |
|---|---|---|
| 必读 1 | `README.md` | 已冻结的产品规则，尤其是未连接 RK 时的能力 |
| 必读 2 | `07_前端页面与API字段映射.md` | 每个页面调用什么接口、显示什么字段、如何处理加载/离线/错误 |
| 必读 3 | `06_手机后端API.openapi.yaml` | 生成中央 API 客户端和 Mock；不要手写猜测 DTO |
| 必读 4 | `08_RK设备能力与控制协议.md` | 局域网发现、配对、动态 Pad、现场操作、WebSocket 和状态快照 |
| 必读 5 | `09_资源Manifest与同步协议.md` | 手机只下发任务，不中转音频；如何展示 RK 实际同步进度 |
| 必读 6 | `10_错误码幂等与离线恢复.md` | operation_id、timeout_unknown、401/409/429、断线重连 |
| 必读 7 | `12_联调测试与验收用例.md` | 手机页面、设备、离线和现场控制验收 |
| 架构摘要 | `01_系统架构与职责边界.md` | 理解中央在线、RK 连接和 RK ready 是三种不同状态 |
| 字段评审 | `04_音乐分析输入输出合同.md` | 只重点看对外 DTO、置信度、possible/needs_review 展示规则 |
| 按需参考 | `03_领域模型与数据库设计.md` | 理解 track_id、library_item_id、playlist_item_id、device_id 的区别 |
| 无需通读 | `05_分析任务状态机与Worker规范.md`、`11_配置部署安全与运维手册.md` | 只需理解 AnalysisRun 状态、API可用性和环境地址，不负责内部实现 |

前端最终必须交付：生成的 API client、CentralRepository、DeviceRepository、token refresh、页面字段映射、RK WebSocket 状态机、离线/错误页面、Mock fixture 和端到端测试。

### 4.3 发给服务端音乐算法负责人的文档

建议标题：`HarBeat 服务端音乐分析算法接入包`

按以下顺序阅读：

| 级别 | 文档 | 算法需要解决的问题 |
|---|---|---|
| 必读 1 | `04_音乐分析输入输出合同.md` | Core、Stem、Feature、Style 的输入、字段、单位、质量、版本和错误合同 |
| 必读 2 | `05_分析任务状态机与Worker规范.md` | 算法如何被独立 Worker 调用、超时、取消、重试和原子交付 |
| 必读 3 | `01_系统架构与职责边界.md` | 算法只负责技术产物，不直接操作用户、设备和曲库业务表 |
| 必读 4 | `09_资源Manifest与同步协议.md` | 哪些算法数据/Stem/Render 最终需要投影给 RK，哪些不能下发 |
| 必读 5 | `11_配置部署安全与运维手册.md` | Jetson GPU/模型/命令/超时/临时目录和部署配置 |
| 必读 6 | `12_联调测试与验收用例.md` | Schema、fixture、模型验证、性能和回归验收 |
| 必须评审 | `03_领域模型与数据库设计.md` 中“分析任务和产物” | 确认 artifact/schema/version/hash 能保存算法真实输出 |
| 必须评审 | `06_手机后端API.openapi.yaml` 中 `AnalysisSummary/AnalysisRun` | 确认 App 对外字段没有扩大算法结论 |
| 必须评审 | `07_前端页面与API字段映射.md` 的分析展示部分 | 确认低置信和 provisional 不被显示为确定事实 |
| 按需参考 | `08_RK设备能力与控制协议.md` | 只看 RK 使用分析数据、Stem 和 Transition 的边界 |
| 无需通读 | `10_错误码幂等与离线恢复.md` | 只需要实现第 4.4 节算法错误码和 Worker 可重试语义 |

算法最终必须交付：独立 adapter/CLI、各 artifact JSON Schema、成功/degraded/unavailable/invalid fixtures、模型 manifest/hash/许可证、验证报告、资源耗时报告和版本回归说明。

### 4.4 发给 RK 开发负责人的文档

建议标题：`HarBeat RK3588 边缘端开发与联调包`

按以下顺序阅读：

| 级别 | 文档 | RK 需要解决的问题 |
|---|---|---|
| 必读 1 | `README.md` | 四方职责、产品规则和统一协作规范 |
| 必读 2 | `08_RK设备能力与控制协议.md` | 配对、Capability、REST/WS、Operation、实体键和现场事实 |
| 必读 3 | `09_资源Manifest与同步协议.md` | Manifest签名、资源直拉、Range/hash、缓存和恢复 |
| 必读 4 | `10_错误码幂等与离线恢复.md` | operation幂等、timeout_unknown、Outbox、断网/重启 |
| 必读 5 | `11_配置部署安全与运维手册.md` | RK配置、systemd、credential、端口和安全 |
| 必读 6 | `12_联调测试与验收用例.md` | 配对、能力、同步、控制、断电、真机验收 |
| 架构必读 | `01_系统架构与职责边界.md` | RK是现场权威源，不依赖Jetson实时决策 |
| 数据评审 | `03_领域模型与数据库设计.md` 中设备/同步/事件部分 | 中央镜像和RK本地真相如何对应 |
| 算法评审 | `04_音乐分析输入输出合同.md` | RK实际使用的Beat/Cue/Stem/Transition数据和质量门 |
| 接口评审 | `06_手机后端API.openapi.yaml` | Manifest/SyncJob/LiveSession/Event Batch中央接口 |
| 页面联调 | `07_前端页面与API字段映射.md` | 手机发现、配对、同步、现场和重连行为 |

RK 最终必须交付：edge-agent、sync-worker、audio-engine、input-daemon、SQLite migrations、配对/授权、动态Capability、Operation/Event、Manifest/cache/outbox、systemd、真机稳定/恢复/安全报告。

### 4.5 四方必须共同评审的文档

不能完全按角色隔离，以下内容必须由四位负责人共同定稿：

| 文档/内容 | 后端确认 | 前端确认 | 算法确认 | RK确认 |
|---|---|---|---|---|
| `01` 系统边界和数据真相 | 中央服务/存储 | 页面/连接投影 | 计算职责 | 边缘执行真相 |
| `04` 对外/运行分析字段 | 存储、版本、投影 | 空值/置信展示 | 语义/验证边界 | 运行数据够用且可降级 |
| `06` 中央 OpenAPI | 实现/权限/幂等 | DTO/页面 | Analysis DTO不过度承诺 | Device/Manifest/Event可联调 |
| `08` RK Control/Event | 中央设备/授权对应 | 控制/状态/重连 | 运行数据边界 | 协议/执行/恢复实现 |
| `09` Manifest/Asset/Sync | 生成/授权/镜像 | 进度和错误展示 | 资产/运行数据 | 下载/校验/缓存/恢复 |
| `10` 错误和恢复 | 公共码/幂等 | 用户动作 | 算法错误可重试性 | 本地执行码/timeout/outbox |
| `12` 联调验收 | 中央/Worker | 页面/App | 算法/模型 | RK真机/现场 |

## 5. 后端负责人建议开工顺序

1. 评审 01、03、04，冻结 ID、状态枚举、资产类型和算法 schema 版本。
2. 建 Alembic 基线，完成全局曲目/个人关联/分析任务/设备/同步/事件表。
3. 先实现身份认证、目录、个人曲库、上传和分析任务，再接 Worker。
4. 同步实现设备配对、能力、Manifest、SyncJob、事件批量上报。
5. 依据 OpenAPI 生成前端客户端和 Mock；依据 08、09 给 RK 建合同测试夹具。
6. 完成公网 HTTPS、后台 Worker、监控、备份与恢复演练后再进入设备联调。

## 6. 后端 P0 工作分解

| Epic | 主要任务 | 直接交付物 | 依赖/验收 |
|---|---|---|---|
| BE-00 工程基线 | 统一 Settings、依赖锁、release/build 信息、开发 Compose、Alembic、统一错误外壳 | 可重复开发环境、`/system/build`、首个 migration | 11；空库/旧快照升级通过 |
| BE-01 身份安全 | Argon2id、access/refresh rotation、注销、对象级鉴权、审计/限流 | Auth/Profile API 和安全测试 | 03/06/10/11；A01/A02 |
| BE-02 公共目录与个人关系 | Track、Publication、UserLibrary、Playlist、PrepareDraft；旧 Song/LibrarySong 迁移 | ORM/migration/API/迁移对账 | 03/06；A03/A04/A06 |
| BE-03 上传与媒体 | 上传会话、媒体探测、hash 去重、NAS staging/ready、preview/waveform、grant/Range | Upload/Media API、存储 adapter | 03/06/09/11；A03/S01/S03 |
| BE-04 分析编排 | AnalysisRun/Stage/Artifact、outbox/dispatcher、独立 Worker、租约/重试/取消、schema gate | Worker services、管理 CLI/API、指标 | 04/05；W01–W06 |
| BE-05 设备身份 | Device/Owner/Binding、配对 ticket/proof、device credential、capability mirror | Device/Pairing API、审计 | 03/06/08/10；R01/R02 |
| BE-06 预设与资源包 | PadPresetVersion、prepare freeze、确定性 Manifest、签名/grant、SyncJob 镜像 | Preset/Manifest/Sync API 和 fixture | 08/09；S01–S06 |
| BE-07 现场事实 | LiveSession、Operation 云端记录、设备事件批量接收、去重、sequence gap/ack | Event ingest、查询/运维对账 | 08/10；R03–R06 |
| BE-08 Gateway 与生产运维 | 公网 HTTPS、隧道、上传/Range、systemd、监控告警、备份恢复、发布回滚 | Staging/生产 runbook 和演练报告 | 11；F01–F10/安全门 |
| BE-09 联调与收口 | OpenAPI 生成、三端 fixtures、端到端/性能/安全、文档回写 | 测试报告、发布清单、已知问题 | 07/12；G0–G6 |

每个 Epic 建议建立独立 MR/任务清单；共享枚举、Schema 和 migration 先合并，业务代码随后开发，避免前端、算法和 RK 同时猜字段。

## 7. 完成定义

后端不能仅以“接口能返回 200”作为完成。每个模块必须同时具备：

- Alembic migration、ORM 和数据库约束；
- OpenAPI 请求/响应/错误模型；
- 权限校验、幂等键、审计字段；
- 单元测试、合同测试和关键集成测试；
- 日志、指标、健康检查和告警；
- 失败重试、进程重启和断网恢复行为；
- 不含真实密钥的配置样例与部署说明。

## 8. 文档状态约定

- `CURRENT`：仓库或线上已存在，仍需测试确认。
- `TARGET/P0`：本轮后端必须交付。
- `P1`：不阻塞首轮联调，但数据模型不得阻止后续实现。
- `PROVISIONAL`：算法可输出但尚不允许作为强产品结论。
- 所有时间为 RFC 3339 UTC，例如 `2026-08-28T10:00:00Z`。
- 所有新业务主键使用 UUID 字符串；旧整数 ID 只出现在迁移映射中。
