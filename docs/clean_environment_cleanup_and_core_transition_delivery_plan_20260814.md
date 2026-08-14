# HarBeat 环境清理与核心接歌算法保全执行方案

文档日期：2026-08-14

执行分支：`rewrite/clean-core-operation-v0.4`

原始方案：`clean_environment_core_rewrite_and_legacy_quarantine_plan_20260814.md`

## 1. 执行结论

本方案继续执行原方案的环境保存、制品固化、clean release、旧运行时隔离和清理目标，但调整原 R5 的交付边界：

1. 13 个功能模块已经整理并上传，不重复拆分。
2. 本轮必须交付可独立安装和验证的核心接歌算法，包括 v2 候选、选点、节拍对齐、局部速度拉伸、v7 渲染和 WAV/meta 契约。
3. 手机、RK、Jetson 之间的资源拉取、预热、缓存、同步、operation 调度和 15 秒切歌体验不在本轮继续修补，进入第二版重新设计。
4. 旧环境可以在备份、clean 基础环境和核心算法制品验收通过后隔离；不能因为核心算法通过就跳过数据备份和恢复验证。
5. 永久删除必须按批准清单执行。系统、驱动、网络、声卡、CUDA、模型、歌曲、数据库和核心算法制品不得删除。

本轮最终状态不是“旧 App 的切歌功能已经稳定”，而是：

```text
设备基础环境干净且可恢复
+ 13 个模块制品可安装
+ 核心接歌算法可独立验证
+ 旧业务运行时已隔离
+ 第二版资源拉取可在此基础上重新开发
```

## 2. 当前真实情况

### 2.1 Git 与本地目录

已经完成：

- 原型归档：`archive/stage-e-prototype-20260814`，提交 `22085d8`。
- clean 执行分支：`rewrite/clean-core-operation-v0.4`，远端已上传。
- 13 个模块分支及模块制品已上传。
- 本地 Python `build`、`*.egg-info`、`__pycache__`、pytest、Flutter/Gradle 构建缓存已清理。
- 13 个重复模块 worktree 和旧聚合 worktree已移除，本地 Git 分支和远端提交保留。

保留的本地工作目录：

| 目录 | 用途 | 处理 |
|---|---|---|
| `D:\work\harbeat-client` | 用户生产参考与历史证据 | 只读，不清理用户改动 |
| `D:\work\harbeat-clean-environment-v0.3` | Stage E 冻结原型 | 保留，不继续开发 |
| `D:\work\harbeat-clean-core-v0.4` | 当前唯一 clean 执行目录 | 继续开发和提交 |
| `D:\work\harbeat-device-backups` | 恢复包、第三方 wheel、模型和模块 wheelhouse | 保留并校验 |

仍待删除的可重建验证副本：

```text
D:\work\harbeat-functional-modules-v0.2-fresh-20260813-2321
D:\work\harbeat-functional-modules-v0.2-fresh-sparse
D:\work\harbeat-module-verification
D:\work\harbeat-transition-planner-fresh-20260813
D:\work\harbeat-transition-renderer-fresh-20260813
```

这些目录没有未提交源码，但当前工具策略禁止对工作区根外执行递归删除。它们不参与后续构建，待获得允许后按固定绝对路径删除。

### 2.2 RK3588

当前设备：`cat@192.168.93.209`

| 项目 | 当前值 |
|---|---|
| 根分区 | 58GB，总使用 37GB，67%，可用 19GB |
| 旧业务目录 | `/home/cat/cypher`，约 6.5GB |
| 旧缓存 | `/home/cat/cypher/cache`，约 6.5GB |
| 默认混音缓存 | 约 1.2GB |
| 旧 Python | `/home/cat/venvs/edge` |
| 旧服务 | `cypher-audio-engine`、`cypher-edge-agent`、`cypher-input-daemon`、`cypher-sync-worker` |
| 服务状态 | 四个服务均运行且开机启用 |
| 正式入口 | `9000`、`9100` |
| clean 正式目录 | 尚未部署到 `/opt/harbeat` |

`harbeat-audio-restore.service` 只负责 ES8388 mixer 恢复，属于硬件基础配置，必须保留或等价迁移，不能与旧业务服务一起删除。

### 2.3 Jetson

当前设备：`mark@100.87.142.21`

| 项目 | 当前值 |
|---|---|
| 根分区 | 54GB，总使用 43GB，84%，可用 8.7GB |
| 旧源码 | `/home/mark/harbeat`，约 4.6GB |
| 旧 venv | `/home/mark/venvs`，约 2.6GB |
| 用户 cache | `/home/mark/.cache`，约 3.0GB |
| 本轮临时环境 | `/tmp/harbeat-*`，合计约 5.3GB |
| 旧服务 | `harbeat-api.service`，当前运行于 `8000` |
| 旧服务依赖 | `/home/mark/harbeat` 和 `/home/mark/venvs/harbeat` |
| clean 正式目录 | 尚未部署到 `/opt/harbeat` |

临时 clean venv 已证明 CUDA、Torch、torchaudio、Demucs 和 12 个模块可运行，但临时目录不是正式 release，不能直接作为最终环境保留。

### 2.4 制品与数据

已经验证：

- RK/Jetson 硬件配置恢复包可读且 SHA256 一致。
- 两端系统包 lock、Python lock、Torch/torchaudio 和 Demucs 模型 SHA 已记录。
- 12 个 Python wheel 已生成，核心 wheelhouse 位于：

```text
D:\work\harbeat-device-backups\20260814\wheelhouse-core-v0.4.1
```

- 当前歌曲库 43/43 具有实体音频和完整 v2 数据。
- NAS 音频目录约 27GB。

尚未完成：

- 恢复包只是硬件配置归档，不是整盘镜像。
- 没有验收通过的 PostgreSQL 结构化 dump。
- 没有覆盖歌曲、stem、v2 数据和模型的统一资产 SHA manifest。
- 没有在正式 `/opt/harbeat` clean release 上做安装/回滚验证。

因此当前不能停止旧服务，也不能删除旧源码、venv 或数据库。

## 3. 本轮保留和延期范围

### 3.1 必须保留并验收

核心接歌链路：

```text
dj_structure_v2 候选数据
-> Track1/Track2 候选过滤与评分
-> v2 切出/接入选点
-> beat/downbeat 对齐
-> 局部鼓点/onset 对齐
-> 重叠区轻微速度拉伸
-> 三频段曲线和能量匹配
-> resume 点搜索
-> v7 WAV/meta 输出
```

正式约束：

```text
audio_feature_source = dj_structure_precomputed_window_v2
renderer_version = three_band_default_v7_standalone_curve_no_energy_floor
fallback = false
degraded = false
```

同时保留：

- RK sample-clock、双 deck、render playback 和 resume 的已验证实现/契约；
- Demucs 模型、四 stem 输出规则和依赖制品；
- 13 个功能模块、测试、MODULE.yaml 和部署说明；
- 硬件驱动、网卡配置、ALSA/ES8388、CUDA、FFmpeg、libsndfile；
- PostgreSQL、歌曲、stem、v2 和模型数据。

### 3.2 第二版重新设计

以下内容不作为本轮环境清理的通过条件，也不再继续叠加补丁：

- 手机 UI 到 RK 的资源拉取流程；
- rolling prewarm 和 cursor bucket 预热；
- target audio 与 pair 的同步顺序；
- 弱热点断线、重试和缓存恢复；
- 自动、快切、能量、风格的完整三端 operation；
- 15 秒切歌 SLA；
- UI 进度轮询与 operation 状态恢复；
- 自动接歌与手动切歌的并发仲裁。

现有代码保留为原型证据，但不得作为 clean release 的正式控制面启动。

## 4. 目标目录与环境隔离

两台设备统一使用：

```text
/opt/harbeat/releases/<release-id>/   只读代码和 wheel 安装结果
/opt/harbeat/current                  当前 release 符号链接
/etc/harbeat/                         配置；secret 值不进入 Git
/var/lib/harbeat/                     可写状态和测试输出
/srv/harbeat-assets/                  歌曲、stem、模型和 v2 资产入口
/srv/harbeat-legacy-ro/               旧环境只读归档挂载点
```

禁止正式 release 引用：

```text
/home/cat/cypher
/home/cat/venvs/edge
/home/mark/harbeat
/home/mark/venvs/harbeat
/tmp/harbeat-*
用户级 site-packages
旧 render cache
```

## 5. 直接执行步骤

### 阶段 A：更新门禁和冻结清单

执行：

1. 将本方案提交到 clean 分支。
2. 生成 `retain/quarantine/delete/defer-v2` 四类清单。
3. 给核心算法源码、wheelhouse、模型、恢复包和 Stage D fixtures 生成 SHA256。
4. 创建核心算法 release tag，禁止再从旧工作区复制代码。

通过标准：

- 每个待处理目录均有分类和理由；
- 所有唯一资产都在 `retain`；
- `delete` 中不能出现系统、驱动、数据库、歌曲、模型或核心算法；
- Git 工作区干净且远端分支存在。

失败处理：任何路径归属不明确就标记 `retain_pending_review`，不删除。

### 阶段 B：补齐不可替代数据备份

执行顺序：

1. 导出 PostgreSQL schema、数据和角色清单，secret 值单独保存。
2. 记录每张核心表行数，并对歌曲 ID、v2 字段完整性做校验。
3. 为 27GB NAS 音频生成相对路径、size、mtime、SHA256 manifest。
4. 为 stem、Demucs 模型和 v2 分析资产生成同类 manifest。
5. 归档 RK/Jetson 旧 systemd unit、环境变量字段、旧源码 Git HEAD 和有效 APK。
6. 对恢复包执行解包抽查；记录无法远程完成的整盘镜像风险。

通过标准：

- PostgreSQL dump 可在临时数据库恢复，schema 和关键表行数一致；
- 43/43 歌曲、v2 与源文件可由 manifest 解析；
- 所有模型和第三方制品 SHA 匹配；
- 备份至少存在于设备外的 `D:\work\harbeat-device-backups`；
- 生成一份恢复步骤，不依赖旧 venv。

失败处理：任何一项失败，立即停止设备清理，旧服务保持运行。

### 阶段 C：固化核心算法 release

执行：

1. 从 clean 分支重新构建12个 wheel。
2. 在全新 Python 3.10 venv 中离线安装，不读取旧 venv/site-packages。
3. 运行13个模块的独立测试。
4. 用 Stage D 的两首真实音频和 v2 数据运行 planner 与 renderer。
5. 保存 plan、WAV、meta、耗时、版本、SHA 和音频质量指标。
6. 扫描 import graph、配置和输出，确保没有旧路径。

通过标准：

- 12/12 wheel 安装，`pip check` 通过；
- 核心算法测试全部通过；
- planner 只使用 v2 候选，无 fallback/degraded；
- renderer 使用指定 v7，WAV 可解码且 meta 完整；
- 与 Stage D 基准 plan/WAV 行为一致；
- 核心算法在 RK-Jetson 网络不可达时仍可在 Jetson 本地独立验证。

失败处理：只修核心算法、制品或依赖问题；不进入资源拉取和手机控制逻辑。

### 阶段 D：部署正式 clean 基础环境

Jetson：

1. 在 `/opt/harbeat/releases/<release-id>` 创建正式 release。
2. 从锁定 wheelhouse 创建 Python 3.10 venv。
3. 安装 CUDA 兼容的 Torch/torchaudio、Demucs 和12个模块。
4. 配置只读资产入口和独立 `/var/lib/harbeat`。
5. 只部署 health、hardware doctor 和核心算法 smoke 命令，不启动第二版资源服务。

RK：

1. 创建相同 release 结构和独立 venv。
2. 安装 RK 锁定依赖及12个模块。
3. 验证 ALSA、ES8388、FFmpeg、Unix socket 和 monotonic clock。
4. 保留或迁移 `harbeat-audio-restore.service`。
5. 不启动旧 edge/sync API 的 clean 仿制品。

通过标准：

- 两端 `pip check`、12/12 import 和 hardware doctor 通过；
- Jetson CUDA tensor、Demucs model SHA 和 v7 render smoke 通过；
- RK 声卡设备、FFmpeg 和 socket smoke 通过；
- release 只引用规定的 `/opt`、`/etc`、`/var/lib`、`/srv` 路径；
- stage/activate/rollback 三次执行结果一致。

失败处理：回滚 `/opt/harbeat/current`，旧服务不受影响。

### 阶段 E：核心算法替代验收

本阶段替代原方案 R5 的完整四功能真机验收。

固定验收：

1. v2 选点 fixture 10/10；
2. v7 render fixture 5/5；
3. 相同输入重复运行输出计划确定性 20/20；
4. 缺失 v2、错误 renderer、缺失音频均明确失败；
5. clean release 重启后重复执行5/5；
6. 不连接手机、不要求资源同步和15秒切歌。

通过标准：

- 核心算法结果正确、可重复、可追溯；
- 所有失败均为 typed error，无静默 fallback；
- 不读取任何旧业务目录；
- 生成独立验收报告和制品 SHA。

通过后设置：

```text
core_transition_algorithm_accepted = true
resource_pipeline_v2_required = true
legacy_r5_feature_acceptance_deferred = true
```

这不等于 `production_ready=true`。

### 阶段 F：旧运行时隔离

前置条件：阶段 B、C、D、E 全部通过并完成 rollback 演练。

执行：

1. 保存旧服务最终状态、日志尾部和端口快照。
2. 停止并禁用 RK 四个 `cypher-*` 业务服务。
3. 停止并禁用 Jetson `harbeat-api` 旧业务服务。
4. 不停止 SSH、NetworkManager、Tailscale、ALSA、CUDA、PostgreSQL、Redis、NAS mount 和硬件恢复服务。
5. 从新 PATH、PYTHONPATH、systemd 和配置中移除旧目录。
6. 将旧源码/venv归档到设备外；设备内只保留只读恢复索引。

通过标准：

- 重启后旧业务服务不自动启动；
- 新 clean release 的 doctor 和核心算法仍通过；
- 旧端口 `9000/9100/8000` 不再由旧业务进程监听；
- SSH、网络、声卡、GPU、数据库和NAS保持正常；
- rollback 文档可以恢复旧服务，但不会自动执行。

失败处理：按保存的 unit 和 release 快照恢复旧服务，不继续删除文件。

### 阶段 G：空间清理和永久删除审核

第一批可删除：

- Jetson `/tmp/harbeat-*` 临时 venv、wheelhouse、日志和 Stage C/D/R2临时输出；
- RK 旧 render cache 和可重新下载的歌曲缓存；
- 已归档并校验的旧日志、`.part` 和任务状态；
- 本机一次性 fresh/verification clone。

第二批需单独批准：

- `/home/cat/cypher` 旧源码；
- `/home/cat/venvs/edge`；
- `/home/mark/harbeat`；
- `/home/mark/venvs/harbeat`；
- 旧 systemd unit 文件。

永不随业务清理删除：

- 内核、bootloader、驱动、固件、udev 和网卡配置；
- ALSA/ES8388 和 `harbeat-audio-restore` 等硬件配置；
- CUDA、cuDNN、TensorRT、FFmpeg、libsndfile；
- PostgreSQL、NAS 音频、stem、v2 和模型；
- clean release、wheelhouse、恢复包和验收报告。

通过标准：

- 每个删除目标都有绝对路径、size、SHA/备份位置和批准状态；
- 删除后执行磁盘、端口、服务、旧路径和核心算法复检；
- Jetson 根分区回到安全余量，建议使用率低于75%；
- RK不再保留可重建的6.5GB旧 cache。

## 6. 风险评估

| 风险 | 当前等级 | 处理 |
|---|---|---|
| PostgreSQL尚无恢复 dump | 极高 | 阶段B失败就禁止清理 |
| 27GB资产只有可读验证、无统一SHA manifest | 高 | 后台生成manifest，不移动NAS原文件 |
| Jetson根分区84% | 高 | 先部署最小正式release，再删除已归档的5.3GB `/tmp` |
| RK旧cache占6.5GB | 中 | 业务服务隔离后优先删除cache，不先删源码 |
| 停旧服务后当前App不可用 | 高且已知 | 本轮目标是干净环境；第二版完成前接受功能停机 |
| RK不能直达Jetson Tailscale地址 | 中 | 不阻塞核心算法本地验收；第二版重新设计传输网络 |
| 把旧补丁复制进新环境 | 高 | 只允许Git提交、锁定wheel和manifest资产进入release |
| 误删硬件配置 | 极高 | 硬件目录永不进入自动删除清单 |
| 没有完整整盘镜像 | 高 | 保留配置恢复包和外部旧业务归档；永久删除前记录剩余风险并人工批准 |

## 7. 最终交付物

必须交付：

1. 本执行方案及逐阶段状态报告；
2. 13 个模块源码、测试、版本和远端提交；
3. 核心接歌算法 release、wheelhouse 和 SHA256 manifest；
4. PostgreSQL dump、schema、行数验收和恢复记录；
5. 歌曲、stem、v2、模型资产 manifest；
6. RK/Jetson 系统、依赖、硬件和旧运行时归档；
7. `/opt/harbeat` clean release 与 activate/rollback 记录；
8. 核心算法独立验收报告；
9. 旧服务隔离记录和删除批准清单；
10. 第二版资源拉取架构的明确待办边界。

## 8. 门禁状态

当前保持：

```text
core_transition_algorithm_accepted = false
resource_pipeline_v2_required = true
legacy_r5_feature_acceptance_deferred = true
production_ready = false
r1_passed = false
legacy_runtime_quarantine_authorized = false
legacy_runtime_disable_authorized = false
legacy_files_delete_authorized = false
cleanup_authorized = false
```

只有阶段 B-D 通过后，才允许进入核心算法验收；只有阶段 E 和 rollback 通过后，才允许隔离旧运行时；永久删除仍要求逐项批准。
