# HarBeat 干净环境核心重写与旧环境隔离方案

文档日期：2026-08-14

## 1. 决策结论

本方案不再继续把 Stage E 的临时生产兼容逻辑叠加到现有手机页面，也不从零重写已经通过验证的音频算法和设备内核。

采用以下路线：

1. 保留 `functional-modules/v0.2.0`、clean deployment v0.3、Stage D parity 和 Stage E 真机证据。
2. 将当前 Stage E 实现冻结为“行为原型”，只用于契约提取、回归样本和听感对照，不直接发布为最终架构。
3. 先保存 RK/Jetson 的硬件基础环境、依赖制品、模型和业务数据，再隔离旧业务运行环境。
4. 在 clean release 中重写手机到 RK 的控制面和统一转场 operation；复用已验证的 v2 planner、v7 renderer、asset sync 和 RK sample-clock 播放能力。
5. 先交付自动接歌、快切、能量切歌和风格切歌；分轨、实时 stem 和实体输入保留依赖与模块制品，后续逐模块接入。

清理授权拆成三个独立状态，避免“停止旧服务”和“永久删除文件”被混为一件事：

```text
legacy_runtime_quarantine_authorized = false
legacy_runtime_disable_authorized = false
legacy_files_delete_authorized = false
cleanup_authorized = false
```

前两项可以在本方案的基础环境与最小替代链路通过后提前执行；永久删除必须等完整核心验收和镜像恢复演练通过。

## 2. 对之前工作的评估

### 2.1 可以直接继承

| 已完成成果 | 证据 | 新方案用途 |
|---|---|---|
| 13 个功能模块边界 | `functional-modules/v0.2.0`，146/146 | 作为核心领域边界和模块制品基础 |
| 12 个 Python wheel | v0.3 acceptance，12/12 | 进入审核后的离线 wheelhouse |
| clean root 部署工具 | bootstrap/stage/verify/activate/rollback 已通过 | 作为新环境唯一部署入口 |
| RK/Jetson 基础运行核验 | Python 3.10 wheel import、CUDA/ALSA/FFmpeg 等通过 | 生成基础镜像和 profile lock |
| Stage D 新旧 parity | 四模式 plan 一致、WAV 字节一致 | 防止重写改变选点和听感 |
| 全库 v2 和实体音频审计 | 43/43 | planner 的正式数据输入 |
| Demucs clean repo 验证 | 四 stem 4/4 | 保存为后续分轨模块制品 |
| RK 同步与 sample-clock schedule | 同步、prepare、trigger error 已通过 | 复用，不重写实时声卡 callback |
| Stage E 真机证据 | 自动、快切、能量、风格真实操作记录 | 形成 characterization fixtures 和 E2E 基准 |

### 2.2 作为原型保存，但不直接进入最终版

| 内容 | 评估 | 处理 |
|---|---|---|
| Stage E 的 `dj_control_page.dart` 改动 | 证明真机链路可工作，但新增约 3000 行，重新混合 UI、预热、同步、排程和恢复 | 冻结到原型分支；提取契约后重写 controller |
| 手机 rolling prewarm | 能缩短部分点击耗时，但与预览同步、自动接歌竞争 | 从手机移除，改由服务端 operation/prewarm 管理 |
| 手机保存完整 prepared plan | 热点恢复时状态复杂，容易过期 | 只保存 `device_id`、`session_id`、`operation_id` |
| 多入口 RK compatibility API | Stage E 调试有用，正式链路入口过多 | 保留诊断端口，正式 App 只调用统一 operation API |
| UI 轮询推断任务状态 | 已出现队尾无效点击、自动转场抢先、显示和 RK 状态短暂不一致 | 任务状态以 RK operation store 为权威 |

### 2.3 必须重新实现

- 手机 DJ 页面中的会话、队列、目标预览、operation 和播放状态 controller。
- 自动接歌与三种手动切歌共用的服务端 transition operation。
- 服务端预热去重、目标原音频准备、pair render 同步和任务恢复。
- 跨手机、Jetson、RK 的统一 `operation_id` 和阶段耗时事件。
- 队尾、歌曲自然结束、自动转场与手动转场并发时的确定性规则。

### 2.4 明确不重写

- `dj_structure_v2` 离线候选数据及全库 backfill 结果。
- 已验证的 transition planner 核心算法；先以 adapter 接入，后续单独重构内部 5600 行兼容算法。
- v7 reference renderer 的 DSP 行为和 WAV/meta 结果。
- RK 双 deck、sample clock、render playback 和 resume 的实时音频 callback。
- Demucs 模型和四 stem 输出规则。

## 3. 新架构

### 3.1 统一操作模型

四种播放模式只在“目标歌曲来源”和“是否需要当前 cursor”上不同：

```text
auto    -> 队列下一首，由服务端提前创建 operation
fast    -> 队列下一首，使用当前 cursor 的短窗口候选
energy  -> 用户确认能量 preview 返回的 target_song_id
style   -> 用户确认风格 preview 返回的 target_song_id
```

确认目标后全部进入同一状态机：

```text
accepted
  -> source_snapshot
  -> planned
  -> rendered_or_reused
  -> target_audio_ready
  -> pair_synced
  -> prepared
  -> scheduled
  -> executing
  -> resumed
```

失败状态必须包含 `stage`、`code`、`retryable` 和 `operation_id`，不能静默 fallback。

### 3.2 正式 API

手机正式链路只保留：

```text
POST /v1/transition-previews/energy
POST /v1/transition-previews/style
POST /v1/transition-operations
GET  /v1/transition-operations/{operation_id}
DELETE /v1/transition-operations/{operation_id}
GET  /v1/playback-state
```

`POST /v1/transition-operations` 输入：

```json
{
  "device_id": "rk3588-01",
  "session_id": "set-...",
  "intent": "fast|energy|style|auto",
  "target_song_id": "optional-for-fast-and-auto",
  "request_id": "phone-generated-idempotency-key"
}
```

手机不提交完整 plan、manifest、缓存路径或 schedule 时间。服务端根据 sample-clock 快照生成并持久化这些内容。

### 3.3 服务责任

| 服务 | 责任 | 禁止 |
|---|---|---|
| Mobile | 表达意图、确认 preview、显示权威状态 | 规划、渲染、同步、计算 schedule |
| Planning API | 目标选择、v2 选点、对齐 | 访问 RK 文件系统 |
| Render worker | 幂等生成 WAV/meta | 选择歌曲、操作播放 |
| Asset sync | 下载、校验、原子发布、并发合并 | 规划和 schedule |
| Edge orchestrator | operation 状态机、deadline、幂等、恢复 | DSP 和歌曲选择 |
| Audio runtime | prepare、sample-clock schedule、render playback、resume | HTTP 下载、云端规划 |

### 3.4 服务端预热

预热由服务端按以下 key 去重：

```text
device_id + session_id + from_song_id + to_song_id + planner_version + renderer_version + cursor_bucket
```

每个 pair 只允许：

- 1 个 active render；
- 1 个 active sync；
- 最多 2 个未来有效时间桶；
- operation 确认后，priority 任务可复用预热结果，但不能被后台任务覆盖。

手机不再启动 rolling prewarm，也不轮询 sync-worker 全局状态。

## 4. 基础环境保存与旧环境隔离

### 4.1 RK 必须保存

- 系统镜像、分区表、bootloader 和内核版本。
- 网卡驱动、USB ID、固件、udev 规则和 NetworkManager 配置模板。
- ALSA card/device、ES8388 配置、实时权限和已验证采样率。
- FFmpeg、libsndfile、Python 3.10 和系统包版本清单。
- 当前 systemd unit 仅作为只读 inventory，不复制到新运行目录。

### 4.2 Jetson 必须保存

- JetPack/L4T、CUDA、cuDNN、TensorRT、NVIDIA container runtime 版本。
- Torch/torchaudio/Demucs wheel、构建来源和 SHA256。
- Demucs 模型 manifest，不直接迁移未知来源的模型 cache。
- FFmpeg、libsndfile、Python 3.10 和 GPU doctor 输出。

### 4.3 业务数据必须保存

- PostgreSQL schema 和结构化导出。
- 歌曲、stem、v2 分析、模型和 render 元数据的 manifest 与 SHA256。
- secrets 的字段清单和权限；值单独保管，不写入 Git。
- 当前有效 APK、旧 release、systemd inventory 和三端版本矩阵。

### 4.4 禁止迁入新环境

- 旧 venv、`site-packages` 和用户级 Python 环境。
- 旧源码目录、服务器 hotfix、`.bak` 和临时脚本。
- 旧 render cache、`.part`、日志和任务状态文件。
- 指向 `/home/cat/cypher` 或历史 Jetson 目录的配置。
- 未进入 manifest 或无法校验来源的二进制与模型。

### 4.5 隔离方式

旧环境不是直接删除，而是：

1. 制作整盘/分区镜像并验证可读取。
2. 生成文件、systemd、端口、包、模型和数据 inventory。
3. 将旧业务目录打包到外部存储或 NAS，只读挂载为 `/srv/harbeat-legacy-ro`。
4. 禁用旧业务 unit 的开机启动，并从 PATH、PYTHONPATH 和新配置中移除旧目录。
5. 新 release 只能访问 `/opt/harbeat`、`/etc/harbeat`、`/var/lib/harbeat` 和 `/srv/harbeat-assets`。

这一步完成后，设备在运行意义上已经是干净环境；旧文件是否永久删除不影响新架构纯净度。

## 5. 分阶段执行方案

### 阶段 R0：冻结与取证

工作：

- 将当前未提交 Stage E 代码、测试和证据保存到独立原型分支。
- 生成 diff manifest，标记 `retain_as_fixture`、`extract_contract`、`do_not_port`。
- 从干净提交 `d737e3e` 新建核心重写分支和独立 worktree。

通过标准：所有现有改动可回溯；重写分支没有 Stage E 大文件补丁；不修改生产设备。

### 阶段 R1：基础镜像与制品库

工作：

- 为 RK/Jetson 制作基础镜像和恢复说明。
- 固定 apt/system package lock、wheelhouse、模型 manifest 和硬件 doctor。
- 备份并校验 PostgreSQL、歌曲、stem 和 v2 数据。

通过标准：在不读取旧业务目录的临时 root 中，13 个模块可安装；GPU、声卡、网卡和 FFmpeg doctor 通过；所有资产校验无缺失。

达到该门禁后：

```text
legacy_runtime_quarantine_authorized = true
```

### 阶段 R2：最小设备运行层

部署顺序：

1. `device-runtime`
2. `audio-runtime`
3. `asset-sync`
4. clean edge transport

只实现播放、暂停、seek、状态、歌曲缓存、render prepare/schedule/resume。使用独立端口和 Unix socket，不接入 planner/UI。

通过标准：连续播放 30 分钟无卡顿；状态连续；缓存损坏可重下；prepare/schedule 20/20；触发误差 `<=100ms`；服务重启可恢复或明确终止任务。

### 阶段 R3：统一 transition operation

接入：

1. `transition-planner`
2. `transition-renderer`
3. `transition-orchestrator`
4. operation persistence 与 trace

先用 API/脚本，不接手机。逐项测试：

- 自动 operation 5/5；
- 快切 operation 10/10；
- 幂等重复请求 20/20；
- render/cache 复用；
- 热点断开后恢复；
- source song 改变时确定性取消。

快切时间门槛从用户请求接收开始计算：ready `<=12s`，实际进入 render `<=15s`，且规划必须预留网络和检测余量，不能把切点放在硬上限。

### 阶段 R4：目标选择与手机重写

后端接入能量/风格 selector；手机拆为：

```text
device_controller
playback_controller
queue_controller
transition_preview_controller
transition_operation_controller
dj_control_view
```

页面不持有完整 plan、manifest、sync 状态或 RK schedule 逻辑。

通过标准：

- 手机只产生一个 operation 请求；
- 重复点击复用相同 `request_id`；
- 队尾快切禁用；
- 自动转场发生时未确认 preview 明确失效；
- UI 进度由播放状态驱动，不被 operation 轮询阻塞；
- App 重启后可用 `operation_id` 恢复。

### 阶段 R5：核心功能真机验收

测试顺序固定：

1. 自动接歌 5/5；
2. 快切 5/5；
3. 能量切歌 5/5；
4. 风格切歌 5/5；
5. 以上四类随机交错 20 次；
6. 重复点击、断网、进程重启、缓存损坏各 5 次。

全部要求：无静默 fallback、无 degraded、trigger error `<=100ms`、UI 进度连续、失败不破坏后续自动接歌。

达到该门禁并完成 activate/rollback 后：

```text
legacy_runtime_disable_authorized = true
```

此时可以停止并禁用旧业务服务，让 clean release 成为唯一活动环境。

### 阶段 R6：延后模块接入

按模块独立处理：

- `stem-separation`：真实歌曲四 stem 5/5；
- `audio-runtime` 内的 stem 能力：solo 和 stem curves 单独验收；稳定后再评估是否拆成新的 `stem-runtime` 模块；
- `physical-input`：每个动作 20/20；
- `observability-e2e`：三端同一 `operation_id` 完整追踪。

这些模块不阻止 R5 后隔离旧业务服务，但其旧制品必须保留在只读归档中，直到各自替换完成。

### 阶段 R7：永久删除旧文件

必须同时满足：

- 基础镜像从空目录恢复成功；
- clean release 独立运行一个完整验收周期；
- 所有需要上线的延后模块已替换；
- 新环境无旧路径、端口和 Python import 引用；
- 整盘镜像和只读归档完成恢复抽查；
- 团队书面批准逐项删除清单。

然后才能设置：

```text
legacy_files_delete_authorized = true
cleanup_authorized = true
```

## 6. 可行性与主要风险

总体可行性为高。Stage D 已证明 clean 模块能产生与旧环境一致的 plan 和 WAV，Stage E 又证明真实手机、热点和 RK 能执行完整转场。需要重写的是控制面和状态归属，不是重新发明选点、渲染或声卡播放。

| 风险 | 当前证据 | 新方案处理 |
|---|---|---|
| 手机控制逻辑再次膨胀 | Stage E 页面新增约 3000 行 | UI 只保留 controller adapter；服务端持有 operation |
| 快切压线超过 15 秒 | 实际切点 14.907 秒，500ms 观测为 15.258 秒 | planner 必须预留传输/检测余量；超过 deadline 的候选不得 schedule |
| 自动与手动转场竞争 | 目标音频准备时自动转场可先发生 | operation 绑定 source song/version；source 改变后确定性取消并通知 UI |
| 弱热点重复请求或响应丢失 | Stage E 曾出现 timeout、重复触发和状态迟到 | `request_id` 幂等、RK 持久化任务、手机只恢复 operation ID |
| 全局 sync 状态互相覆盖 | target audio sync 曾被 rolling prewarm 状态覆盖 | 每个 operation 使用独立任务状态；禁止手机读取全局 worker 状态判断完成 |
| 风格无候选 | `Popping` 返回 `no_style_candidate` | 作为正常 typed 业务结果，不创建 transition operation |
| 歌曲 ID 映射混乱 | 现有链路同时出现 catalog/raw/`mt2_` ID | `library-catalog` 固定 canonical ID 与 RK asset ID 映射契约 |
| 误删驱动或模型环境 | 基础镜像和空机恢复尚未完成 | R1 通过前不允许隔离；R7 前不允许永久删除 |
| 重写实时音频导致静音或 xrun | 当前 sample-clock 和 callback 已通过真机 | R2 只包 adapter，不重写 callback；用 20/20 与 30 分钟播放守门 |

当前最大前置阻塞不是算法，而是：

1. RK/Jetson 基础镜像尚未制作并恢复验证；
2. 当前 Stage E 未提交原型需要先冻结，不能丢失证据；
3. Jetson 的稳定远程管理入口仍需确认；
4. 新 operation API 尚未落地，旧服务暂时仍是播放回滚来源。

## 7. Git 与发布策略

建议建立两个分支：

```text
archive/stage-e-prototype-20260814
rewrite/clean-core-operation-v0.4
```

- 原型分支保存当前 Stage E 代码、证据和测试，不继续堆生产补丁。
- 重写分支从 `d737e3e` 开始，只按模块提交。
- 每个模块仍执行：contract -> implementation -> tests -> deploy -> acceptance。
- 手机 controller、edge operation、sync、audio runtime 分开提交，禁止一个提交跨四端改变行为。
- 每个设备 release 都必须有 manifest、SHA256、compatibility matrix 和 rollback target。

## 8. 新方案相对原方案的变化

| 原方案 | 新方案 |
|---|---|
| Stage E 原型继续逐步修补后升为生产 | 冻结为行为样本，重写控制面 |
| 完整 Stage F 后才允许任何清理 | 基础镜像和最小替代通过后允许只读隔离；永久删除仍后置 |
| 手机参与 rolling prewarm、同步和任务恢复 | 服务端 operation 统一管理，手机只发意图 |
| 四种模式存在多个调用入口 | 目标选择不同，执行统一为一个 operation |
| 先要求所有模块完成再停止旧服务 | 核心四功能通过即可禁用旧业务；延后模块独立替换 |
| `cleanup_authorized` 单一布尔值 | 隔离、禁用、永久删除三级授权 |

## 9. 最终交付结果

核心交付完成后应达到：

- RK/Jetson 保留稳定驱动和硬件环境，但不加载旧代码、旧 venv 或旧 systemd 业务逻辑。
- 所有 Python 服务从固定 wheelhouse 安装到独立 venv。
- 手机、Jetson、RK 通过一个 `operation_id` 描述一次转场。
- 自动、快切、能量和风格使用同一套 plan-render-sync-prepare-schedule-resume 流程。
- 任一模块可以独立构建、测试、部署和回滚。
- 旧环境只作为外部只读归档存在，不会污染新环境。

当前状态保持：

```text
production_ready = false
legacy_runtime_quarantine_authorized = false
legacy_runtime_disable_authorized = false
legacy_files_delete_authorized = false
cleanup_authorized = false
```
