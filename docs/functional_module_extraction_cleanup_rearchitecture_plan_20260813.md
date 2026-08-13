# HarBeat 按功能模块拆分、环境清理与重构执行方案

日期：2026-08-13
范围：Android App、Jetson 云端服务、RK3588 边缘服务与音频引擎
原则：先取证、再拆分、后清理；先独立验收、后融合；现阶段不删除生产文件和数据。

## 1. 直接结论

按功能模块拆分是当前最稳妥的路线，但不能先按现有目录拆，也不能先重装 Jetson/RK。当前部署代码大量未提交，手机页面、云端 DJ router、RK edge-agent 都同时承担多个职责，现有目录并不等于真实模块边界。

正确顺序是：

1. 用手机 App 真实触发一个用户功能。
2. 记录手机、Jetson、RK 的接口、状态、文件、数据和耗时。
3. 为该功能建立明确输入/输出契约和独立测试夹具。
4. 从现有部署中提取最小可运行实现，先保持行为不变。
5. 独立测试通过后，再重构内部实现。
6. 所有核心模块通过后，才构建干净环境并进行端到端融合。

当前最严重的问题不是单一算法或热点速度，而是后台预热、自动播放、手动切歌和 UI 状态集中在同一个状态机中，任务会互相制造负载和覆盖状态。

## 2. 2026-08-13 真实 App 调用结果

测试设备：

| 端 | 实际状态 |
|---|---|
| 手机 | `2106118C`，ADB `130ddcca`，App `com.example.mobile 1.0.0` |
| RK3588 | `192.168.93.209:9000`，`cypher-audio-engine/edge-agent/sync-worker/input-daemon` 均运行 |
| Jetson | `100.87.142.21`，`harbeat-api.service` 运行，生产 API 经 `8.136.120.255` 访问 |

真实测试结果：

| 功能 | 结果 | 关键数据 | 判断 |
|---|---|---|---|
| App 登录、曲库、歌单 | 通过 | App 能读取用户、23 首测试歌单和曲库 | 必须保留 |
| 默认排歌并开始播放 | 通过 | App 建立 13 首队列，RK 播放成功 | 基础链路可用 |
| 快切 | 单次通过 | 点击到目标歌恢复 `18.442s`；切点误差 `0.005ms`；`degraded=false` | RK 调度准确，准备时间未达 15 秒目标 |
| 能量预览 | 通过 | 选出目标能量候选，来源可为曲库扩展 | 选歌模块可独立保留 |
| 能量确认执行 | 单次通过 | 确认后 `14.861s` 进入 6.5 秒 render；误差 `-0.009ms` | 共享执行链可用，但状态语义需明确 |
| 风格预览 | 通过 | Hip Hop 推荐 `Do For Love`，风格分 `1.00` | 风格选歌模块可独立保留 |
| 风格确认执行 | 本轮未完成 | 确认态在长时间 UI 抓取/后台刷新后消失 | 不能判定通过，需独立复测 |

测试工具问题：现有 `scripts/test_dj_control_modes_e2e.py` 会在滚动页面中读取过期 XML 帧，曾把已经出现的“确认切歌”误报为不可用。它只能作为历史工具保留，修复前不能作为交付判定依据。

### 2.1 已确认的主要故障

约 14 分钟的真实 App 会话中，实际只完成一次快切和一次能量确认，但产生：

| 请求/任务 | 次数 |
|---|---:|
| Jetson `POST /api/dj/transitions/fast-cut` | 87 |
| RK `POST /autoplay/default/render/orchestrate` | 88 |
| RK sync-worker `POST /sync` | 73 |
| RK `/state` | 1520 |
| sync-worker `/status` | 570 |

根因是 [dj_control_page.dart](../mobile/lib/src/dj_control_page.dart) 的 `600ms` 状态轮询不断调用 rolling default prepare 和 rolling fast-cut prewarm。每次预热又会重新调用云端选点/渲染、RK 同步和 orchestration。用户没有点击切歌时，这套循环仍持续工作。

因此要保留的是“选点、渲染、同步、预热、调度”能力，不是当前由手机轮询反复发起任务的实现。

## 3. 目标架构边界

三端职责固定如下：

| 端 | 只负责什么 | 不再负责什么 |
|---|---|---|
| 手机 | 发送用户意图；展示单一任务状态；控制播放 | 不做 rolling planner；不保存完整 render plan；不编排多轮重试 |
| Jetson | 曲库预处理；候选选择；转场规划；render 生成；资源发布 | 不依赖手机页面生命周期管理任务 |
| RK edge-agent | 接收幂等任务；驱动同步、prepare、schedule；持久化任务状态 | 不重新做选歌或云端算法 |
| RK sync-worker | 下载、校验、原子写入缓存 | 不决定播放，不持有 UI 会话逻辑 |
| RK audio-engine | 精确调度和播放；报告真实播放状态 | 不进行网络下载和业务选歌 |

统一状态机只允许：

```text
created -> planning -> rendering -> syncing -> prepared -> scheduled
        -> playing_transition -> resumed -> completed
任意未提交状态 -> failed/cancelled/expired
```

每次用户操作只有一个 `operation_id`。同一 `operation_id` 的重试返回同一任务；新操作不得覆盖已进入 `scheduled` 的任务。

## 4. 功能模块清单与处理结论

| # | 功能模块 | 当前真实代码/数据 | 处理结论 | 独立交付标准 |
|---:|---|---|---|---|
| 1 | 设备连接与运行状态 | `edge_agent_client.dart`、RK `/health` `/state`、SharedPreferences | 保留能力，重写状态存储 | 设备以稳定 `device_id` 识别；IP 可变；切换设备后旧任务不会复用 |
| 2 | 登录与用户会话 | 手机 token、`/api/auth/me` | 保留 | 冷启动、token 过期、重新登录均可测 |
| 3 | 曲库与歌单 | library/playlists API、DB、manifest | 保留并抽契约 | 全库与歌单分页、歌曲 ID、资源 ID 一致 |
| 4 | 云端歌曲预处理 | beat/bar/phrase、能量、style、vocal/drum、v2 candidates | 核心保留，单独服务化 | 单歌可重复处理；44/44 数据覆盖；版本和质量字段可查询 |
| 5 | 特征与候选数据仓库 | DB 中 v2 候选、能量和风格证据 | 保留，增加 schema/version gate | 缺字段明确报 `analysis_missing`，不静默 fallback |
| 6 | 默认排歌 | `/api/dj/sequence`、playlist selector | 保留并从 DJ router 拆出 | 固定输入得到稳定队列；不触发 render/sync |
| 7 | 自动接歌规划 | `/transitions/plan`、default transition planner | 核心保留 | 只输出 plan；不下载、不播放；无 fallback 时来源可追踪 |
| 8 | 快切选点 | `/transitions/fast-cut`、v2 10-15 秒候选 | 核心保留，移除手机循环调用 | 一次请求只生成一个结果；15 秒窗口无点时返回最近点和原因 |
| 9 | 能量目标选歌 | `/cut/plan` target energy | 保留并与执行彻底分离 | preview 只返回目标歌曲和解释，不生成 render |
| 10 | 风格目标选歌 | `/cut/plan` target style | 保留并与执行彻底分离 | preview 只返回目标歌曲和解释，不生成 render |
| 11 | 共享手动切歌执行 | fast/energy/style 确认后的 plan-render-sync-schedule | 核心保留，重构成一个服务 | 三种模式只在 `target_song_id` 来源上不同，执行状态机完全相同 |
| 12 | Render 生成与发布 | reference renderer、WAV/meta API | 核心保留 | 相同输入幂等复用；输出 hash/version/duration；无重复生成 |
| 13 | RK 资源同步缓存 | sync-worker、manifest、cache/check | 核心保留，简化接口 | 单任务 2/2 下载；校验 hash；并发同资源合并；失败可恢复 |
| 14 | RK 编排 | edge-agent orchestration、task persistence | 核心保留，收敛入口 | 一个 create、一个 status、一个 cancel；409 有结构化原因 |
| 15 | RK 音频执行 | audio-engine default render schedule/resume | 核心保留，晚于接口层再拆 | 切点误差 `<=100ms`；无静音；resume ID/时间正确 |
| 16 | 手机实时控制 UI | 当前 7994 行 `dj_control_page.dart` | 必须拆分重写 | UI 只消费状态；进度连续；preview 不被后台刷新清空 |
| 17 | 实体按键 | input-daemon、`/internal/key_event` | 保留但后置测试 | 每键一个命令；去抖；与 App 操作共用 operation API |
| 18 | 可观测性与 E2E | session events、三端日志、E2E 脚本 | 保留并重写测试工具 | 每次操作可按 `operation_id` 跨三端查询耗时和错误 |

## 5. 保留、重构、归档和删除规则

### 5.1 必须保留

- 已部署数据库、歌曲原文件、分析特征、v2 候选和有效 render 元数据。
- Jetson 的 default planner、reference renderer、energy/style selector。
- RK sync-worker 的下载校验能力、edge-agent 的任务持久化、audio-engine 的精确 schedule/resume。
- 手机登录、曲库、歌单、队列和基本播放控制。
- 当前 systemd unit、环境变量和模型版本，直到新环境回放通过。

### 5.2 必须重构

- `dj_control_page.dart`：拆为连接、会话、队列、播放状态、目标预览、转场操作六个 controller/store，页面只渲染。
- `app/modules/dj_control/router.py`：按 sequence、selection、transition、render、catalog 拆 router，业务逻辑不得留在 endpoint。
- `cut_strategy.py`：能量/风格目标选择与转场规划分文件，preview 不做 render。
- RK `edge-agent/main.py`：保留一个手动转场 orchestration API，旧 prepare/schedule/render 入口先兼容代理，稳定后移除。
- 手机 SharedPreferences：不再以动态 RK URL 为 key 保存大段完整 plan；只保存 `device_id`、`operation_id` 和短 TTL 引用。
- rolling prewarm：从手机轮询移除。若后续仍需要，只允许由服务端按“当前 pair + 版本 + 时间桶”去重生成一个活动包。

### 5.3 先归档，不直接删除

- `spotify_mix`、`auto_mixer`、`dj_set` 中未被核心流程调用的实验策略。
- `mix_effects`、vibe search、DJ set preview 等当前首版非核心接口。
- 历史 E2E 脚本、一次性 backfill/benchmark 脚本和报告。
- Jetson/RK 上所有 `.bak`、旧 release、旧 service drop-in。

归档标准：复制到只读归档包，记录 SHA256、来源设备、原路径、Git HEAD、systemd 配置和 Python 依赖。完成核心回归后才允许从运行目录删除。

### 5.4 验证后可以删除

- 已过 TTL 且没有任务引用的旧 render WAV/meta。
- 无数据库/manifest 引用的 RK 临时缓存和 `.part` 文件。
- 已确认不被 systemd、import graph、App 或验收测试调用的备份文件。
- 被新统一 orchestration API 完全替代且经过兼容期的旧 API 实现。

禁止凭文件名、修改时间或“看起来没用”删除任何生产代码。

### 5.5 防止误删的强制证据链

模块提取阶段执行 **copy-only**：只从现有部署复制到新的模块目录，不移动、不重命名、不删除源文件。旧 Jetson、RK 和手机 APK 在所有模块融合验收完成前均作为只读基线保留。

每个现有文件必须进入资产台账，不能直接进入“删除”结论：

```text
asset_id
source_device
absolute_path
sha256
size
owner_module
secondary_modules
imported_by
runtime_called_by
data_read_or_written
systemd_or_config_reference
classification = retain | refactor | archive_candidate | delete_candidate
evidence
replacement
rollback_source
```

一个文件只有同时满足以下五项，才能从 `archive_candidate` 升级为 `delete_candidate`：

1. **静态依赖证明**：Python/Dart import graph、配置、systemd、脚本和构建文件均无引用。
2. **运行依赖证明**：真实 App 覆盖全部核心功能时，三端调用跟踪未加载或调用该文件。
3. **数据依赖证明**：数据库、manifest、缓存索引、模型路径和 render metadata 均无引用。
4. **影子删除证明**：仅在新影子 release 中删除后，模块单测、契约测试和真实 App E2E 全部通过。
5. **替代与回滚证明**：有明确替代模块；归档包可按 SHA256 恢复原路径和权限。

删除操作不得批量按扩展名或目录执行。最终删除清单必须逐项列出绝对路径、SHA256、证据和恢复命令，并在执行前单独批准。

### 5.6 核心能力的特殊保护

以下能力即使当前没有出现在一次 UI 调用中，也不得据此删除：

- 分轨：Demucs 调用、四 stem 文件、stem 分析、manifest/stream、RK stem 缓存和 `stem_solo`。
- 默认混音：默认排歌、转场选点、v2 候选、reference renderer、WAV/meta 发布、RK schedule/resume。
- 实时四 stem 混音：`stem_curves`、RK stem gain automation 和相关音频引擎代码。它与当前默认三频段 render 分开登记，可归档或独立演进，但不能混入默认混音模块后误删。
- 数据预处理：beat/bar/downbeat/phrase、能量、风格、vocal/drum 和 handoff 特征。
- 设备运行：systemd unit、环境变量、模型路径、数据库迁移和硬件音频配置。

这些能力必须分别建立独立模块资产清单。是否进入首版运行链路与是否保留源代码是两个不同判断。

## 6. 模块化代码、上传与部署规则

### 6.1 模块不是现有目录

模块以稳定输入输出和独立测试定义，不以当前文件夹定义。一个旧文件可以同时服务多个模块；提取时先复制共享逻辑到明确的 shared contract/core，完成行为对比后再处理旧文件。

首批模块编号固定如下：

| 模块 ID | 模块名称 | 部署端 |
|---|---|---|
| `device-runtime` | 设备连接、身份和运行状态 | Mobile + RK |
| `library-catalog` | 曲库、歌单和 manifest | Mobile + Jetson |
| `audio-preprocess` | BPM/结构/能量/风格分析 | Jetson |
| `stem-separation` | Demucs 分轨、stem 分析和发布 | Jetson |
| `sequence-planner` | 默认排歌 | Jetson |
| `transition-planner` | 自动接歌和快切选点 | Jetson |
| `target-selector` | 能量、风格目标选歌 | Jetson |
| `transition-renderer` | 三频段 reference render | Jetson |
| `asset-sync` | RK 下载、校验和缓存 | RK |
| `transition-orchestrator` | 手动/自动转场任务状态机 | RK |
| `audio-runtime` | prepare、schedule、render playback、resume | RK |
| `stem-runtime` | 四 stem 加载、solo 和 stem curves | RK |
| `mobile-dj-control` | 用户意图、preview 和状态展示 | Mobile |
| `physical-input` | 三个实体模块和按键映射 | RK |
| `observability-e2e` | 三端 trace、指标和真实 App 验收 | 全端 |

### 6.2 每个模块必须有自己的目录和清单

目标结构采用模块目录，而不是把新代码继续堆进现有大文件：

```text
modules/<module-id>/
  MODULE.yaml
  src/
  contracts/
  tests/
  fixtures/
  migrations/       # 没有则省略
  deploy/            # systemd/env/health check
  README.md
```

`MODULE.yaml` 至少包含：

```yaml
id: transition-renderer
version: 0.1.0
owners: [jetson]
inputs: []
outputs: []
runtime_dependencies: []
data_dependencies: []
models: []
source_assets: []
replaces: []
public_endpoints: []
health_check: ""
tests: []
artifact_sha256: ""
rollback_artifact: ""
```

模块清单没有列出的文件不能进入该模块上传包；清单列出的依赖没有准备好时，模块不能部署。

### 6.3 Git 提交必须按模块隔离

每一个模块按以下提交序列完成，不允许将多个未验收模块混在一个提交：

```text
module(<id>): add inventory and contracts
module(<id>): extract behavior-compatible implementation
test(<id>): add unit, contract and golden tests
deploy(<id>): add versioned artifact and health check
cleanup(<id>): archive replaced legacy code
```

规则：

- 一个提取 PR/提交只允许修改一个模块和必要的 shared contract。
- shared contract 的改变单独提交，并运行所有消费者的契约测试。
- 生产环境临时修改必须先回收到对应模块提交，禁止继续让服务器目录成为唯一真相。
- 不提交数据库、歌曲、模型和缓存；这些作为版本化数据资产单独登记。
- 在模块通过独立测试前，不做 `cleanup(<id>)` 提交。

### 6.4 上传产物必须按模块生成

上传单位不是整个杂乱的 Jetson/RK 目录，而是模块版本产物：

```text
harbeat-<module-id>-<version>-<git-sha>.tar.zst
harbeat-<module-id>-<version>-<git-sha>.manifest.json
harbeat-<module-id>-<version>-<git-sha>.sha256
```

manifest 必须列出所有文件、权限、SHA256、运行依赖、配置版本、数据库版本和兼容矩阵。上传后先解压到：

```text
/opt/harbeat/releases/<module-id>/<version>/
```

然后执行模块自己的 health check 和 smoke test。通过后只切换该模块的 `current` 软链接；失败只回滚该模块，不回滚其他已通过模块。

### 6.5 融合发布与模块上传分开

所有模块独立上传通过后，才生成一个只包含版本引用的整体 release manifest：

```yaml
release: 2026.08.x
modules:
  transition-planner: 0.1.0+sha
  transition-renderer: 0.1.0+sha
  asset-sync: 0.1.0+sha
  transition-orchestrator: 0.1.0+sha
  audio-runtime: 0.1.0+sha
```

整体发布不再次复制模块源码，只锁定已经独立验收的模块版本。这样后续只调整分轨、选点或 RK 播放时，可以单独构建、测试、上传和回滚对应模块。

### 6.6 每整理完一个模块立即提交并推送 Git

模块采用“整理一个、测试一个、提交一个、推送一个”的流水线，不等待全部模块整理完后再做一次大提交。

每个模块的固定操作顺序：

```text
1. 建立该模块资产清单和依赖图
2. 从旧部署 copy-only 提取代码
3. 补齐 MODULE.yaml、contracts、tests 和 fixtures
4. 运行该模块的单元测试、契约测试和行为对比
5. 检查 git diff，确认只包含该模块和已批准的 shared contract
6. 独立 commit
7. push 到远端模块分支
8. 用 git ls-remote 确认远端提交存在
9. 记录远端 commit SHA、测试报告和模块版本
10. 再开始下一个模块
```

模块分支命名：

```text
module/device-runtime
module/stem-separation
module/transition-planner
module/transition-renderer
module/asset-sync
module/audio-runtime
```

如果团队希望保持单一集成分支，也必须保持“一模块一组连续提交”，并为每个通过的模块创建不可变 tag：

```text
module/<module-id>/v<version>
```

推送成功不等于模块完成。模块台账必须保存：

| 字段 | 内容 |
|---|---|
| module_id | 模块 ID |
| version | 模块版本 |
| branch | 远端分支 |
| commit_sha | 远端完整 SHA |
| tag | 验收 tag |
| included_files | 本次提交文件列表 |
| excluded_assets | 未上传的数据/模型/缓存及其存储位置 |
| test_report | 独立测试报告路径和 SHA256 |
| status | extracted/tested/pushed/integrated/accepted |

### 6.7 Git 上传内容边界

必须上传 Git：

- 模块源码、公开接口契约和 schema。
- 数据库迁移，不包含真实数据库文件。
- 单元测试、契约测试、小型脱敏 fixture 和测试脚本。
- `MODULE.yaml`、README、部署模板、systemd 模板和 health check。
- Python/Dart/系统依赖锁定文件。
- 资产索引和校验信息，但不包含敏感值。
- 模块提取、测试、部署和回滚文档。

禁止上传 Git：

- `.env`、token、SSH key、热点密码和设备密码。
- 用户数据库、日志、SharedPreferences 原件和个人数据。
- 歌曲原文件、stem 音频、render WAV、RK 缓存和模型权重。
- venv、Flutter build、APK、临时文件和服务器完整备份。

大型模型、测试音频和生产数据必须进入独立对象存储或离线备份，Git 只保存版本、URI、许可信息和 SHA256。没有外部资产恢复清单的模块不能认为已完整上传。

### 6.8 全部上传后的远端重建验收

所有模块达到 `pushed` 后，禁止直接使用当前工作区做最终验收。必须在新的空目录从远端重新克隆，以证明 Git 中确实包含重建系统所需的全部代码：

```text
fresh clone
-> checkout integration release manifest
-> 按 external-assets manifest 恢复模型/测试数据
-> 安装锁定依赖
-> 构建各模块
-> 运行全部模块测试
-> 部署 Jetson/RK 影子端口
-> 安装测试 APK
-> 手机真实端到端验收
```

远端重建验收必须检查：

1. 不读取原工作区、Jetson 旧源码或 RK 旧源码，也能完成构建。
2. 每个模块的 checkout SHA 与模块台账一致。
3. 外部数据和模型均能通过 manifest + SHA256 恢复。
4. 每个模块独立测试通过。
5. 新系统组合后的基础播放、自动接歌、快切、能量切歌、风格切歌和实体按键达到最终交付标准。
6. 从任一模块当前版本回滚到上一个 tag 后，系统仍能启动并给出兼容性提示。

全部通过后创建整体 release tag；在此之前，任何本地或设备旧代码都不得清理。

### 6.9 最后才清理本地和设备旧环境

清理顺序固定为：

```text
远端模块全部存在
-> fresh clone 重建成功
-> 影子部署成功
-> 手机真实 E2E 全通过
-> 回滚演练通过
-> 生成待清理清单
-> 人工批准
-> 先移动到隔离归档区
-> 观察一个完整验收周期
-> 最终删除
```

“本地”包括开发电脑、Jetson 和 RK 的旧源码，但不包括仍被生产运行引用的数据、模型、歌曲和缓存。第一次清理只移动到隔离归档区，不直接永久删除。隔离后再次完成全链路测试，才允许最终删除。

清理完成后仍长期保留：整体 release manifest、所有模块 tag、源码、依赖锁、迁移、外部资产 manifest、SHA256、最终测试报告和恢复手册。

## 7. 拆分执行顺序

### 阶段 0：冻结和可回滚基线

1. 停止功能开发，只允许审计和测试修复。
2. 分别导出手机 APK/配置、Jetson `/home/mark/harbeat`、RK `/home/cat/cypher`、systemd、venv lock、DB schema 和缓存索引。
3. 对部署目录生成文件清单和 SHA256。
4. 建立 `release-current` 只读快照，禁止直接覆盖。

交付：任一设备可在 15 分钟内恢复到当前部署状态。

### 阶段 1：先修验收工具，不改产品行为

1. E2E 控件按 `resource-id/semantic key` 查找，不靠文字滚动和坐标。
2. 每个功能启动独立 App 会话；不得在一个会话连续混测四种模式。
3. 同时采集手机 logcat、Jetson journal、RK 三服务 journal 和 RK state。
4. 报告分开记录 preview、planning、render、sync、prepare、schedule、transition、resume。

交付：同一个静态页面连续识别控件 20 次无误报。

### 阶段 2：提取无副作用的云端模块

按顺序独立提取：预处理 -> 数据仓库 -> 默认排歌 -> 自动规划 -> 快切选点 -> 能量选歌 -> 风格选歌 -> render。

每个模块只能通过显式 DTO 输入输出；单测不得连接 RK；preview 模块不得写 render 文件。

交付：模块单测和 golden fixture 全通过，原 API 响应兼容。

### 阶段 3：提取 RK 模块

按顺序独立提取：同步缓存 -> orchestration -> audio schedule/resume -> 按键。

使用本地固定 WAV/meta fixture，先完全断开 Jetson 测试 RK；再只开放下载接口测试弱热点、超时和断点恢复。

交付：重复 operation 不重复下载/播放；重启 edge-agent 后任务状态可恢复。

### 阶段 4：建立统一手动切歌服务

统一请求：

```json
{
  "operation_id": "uuid",
  "intent": "fast|energy|style",
  "from_song_id": "...",
  "target_song_id": "...",
  "cursor_sec": 123.4,
  "deadline_sec": 15.0
}
```

能量和风格先独立 preview，用户确认后只把选中的 `target_song_id` 交给该服务。此后与快切使用完全相同的选点、render、sync、prepare 和 schedule。

交付：相同歌曲对、相同 cursor 下，三种 intent 的执行 plan 结构一致。

### 阶段 5：重写手机状态层

1. App 只订阅一个 playback stream 和一个 operation stream。
2. 本地 200ms ticker 只做视觉插值，不触发网络任务。
3. 网络状态更新建议 1 秒一次或 WebSocket 推送；不得在回调中启动 planner/render。
4. preview 是独立 immutable state，播放刷新不能清空。
5. 页面关闭不取消 RK 已提交任务；重开通过 operation ID 恢复。

交付：播放进度连续；页面前后台切换不重复发请求；一次点击只产生一个 operation。

### 阶段 6：干净环境重建与融合

1. Jetson/RK 使用版本化 release 目录和 `current` 软链接。
2. Python 依赖锁定；模型、音乐、缓存、DB 与代码目录分离。
3. systemd 指向固定 release；切换软链接即可回滚。
4. 先部署影子端口验证，再切换生产端口。

## 8. 最终交付条件

### 功能稳定性

| 功能 | 连续通过要求 |
|---|---:|
| 基础选歌、排歌、开始播放 | 5/5 |
| 自动接歌 | 5/5 |
| 快切 | 5/5 |
| 能量预览 + 确认切歌 | 5/5 |
| 风格预览 + 确认切歌 | 5/5 |
| 三个实体模块与按键 | 每个动作 20/20 |

### 性能与听感门槛

- 用户确认到 `scheduled <= 12s`，确认到进入衔接 `<=15s`。
- RK trigger error `<=100ms`。
- 无突然静音、硬切、重复播放、目标歌错误或进度倒退。
- `degraded=false`，生产核心路径禁止静默 fallback。
- 一次手动操作最多一次 planning、一次 render（缓存命中为零次）、一次 sync、一次 schedule。
- 30 分钟正常播放期间，后台 fast-cut planning 为 `0`；只有显式预热策略启用时才允许出现，且同一 pair/time bucket 最多一个任务。

### 清理门槛

只有同时满足以下条件，才允许清理旧环境：

1. 新 release 完成上述全部连续测试。
2. 旧部署快照和 SHA256 清单可恢复。
3. import graph、systemd、App 调用和 E2E 均证明待删除项无引用。
4. 在影子环境删除后完整测试仍通过。
5. 形成最终“保留/归档/删除”文件清单并人工批准。

### 模块化交付门槛

每个模块必须同时交付：`MODULE.yaml`、资产清单、依赖图、契约、测试报告、版本产物、SHA256、health check 和回滚产物。缺少任意一项时，不能标记为已提取，也不能上传到生产端。

最终验收报告必须能回答：某个功能由哪些模块版本提供；某个模块包含哪些文件；某个文件为什么保留或删除；某次部署如何只回滚一个模块。

此外，模块只有在远端 commit 可查询、从远端独立 checkout 可测试、外部资产可按 manifest 恢复后，才算“已经上传完毕”。本地存在但远端不存在的代码、服务器上的未提交补丁、未登记模型和手工配置都视为未交付。

## 9. 当前下一步

第一步不是删除文件，而是完成阶段 0 和阶段 1：冻结三端部署快照，并重写可靠的真实 App 验收工具。随后先提取“设备连接与运行状态”模块，再提取“基础播放”模块。两者通过后，停止当前手机 rolling prewarm 编排，在隔离条件下分别验证自动接歌与统一手动切歌执行链。

这能保证后续每次调整只影响一个模块，也能准确回答某个文件究竟是核心依赖、实验代码还是历史残留。
