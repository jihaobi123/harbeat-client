# HarBeat 干净环境与模块化部署执行方案

文档日期：2026-08-14

## 1. 最终目标

建立不继承旧 RK/Jetson 代码、虚拟环境、systemd 和缓存的全新运行基础。新设备完成基础镜像后，应能仅依赖以下受控输入恢复 HarBeat：

1. GitHub 固定 release 标签。
2. 经过 SHA256 校验的模块制品。
3. 锁定的系统包和 Python wheelhouse。
4. 通过 schema 校验的设备配置。
5. 独立保管的 secrets。
6. 经过白名单审核的歌曲、stem、模型和数据库导出。

目标操作：

```bash
harbeatctl bootstrap --profile rk3588 --root /
harbeatctl stage --profile rk3588 --bundle harbeat-release-v1.0.0.tar.gz --root /
harbeatctl verify --release v1.0.0 --root /
harbeatctl activate --release v1.0.0 --root /
harbeatctl doctor --root /
```

RK/Jetson 业务版本更新不修改驱动和基础系统。版本切换失败时，必须能够通过 `harbeatctl rollback` 恢复上一个已验证 release。

## 2. 当前起点与限制

当前起点为 `functional-modules/v0.2.0`：13 个模块边界已经冻结，146 项核心和契约测试通过。

当前仍不具备直接清理设备的条件：

- Python 模块尚未全部形成标准 wheel。
- 生产 API、数据库、Flutter、systemd 和硬件 adapter 尚未接入 clean 模块。
- Jetson 的 Demucs/CUDA 和 RK 的声卡/输入设备尚未在新目录验收。
- 尚未证明从空设备可重建全部功能。

因此本方案分成基础部署平台、生产 adapter、影子运行、分模块切换、旧环境归档五个阶段。任何阶段失败都不允许跳过门禁清理旧环境。

## 3. 防止旧环境污染新环境

### 3.1 允许进入新环境的白名单

| 内容 | 来源 | 验证 |
|---|---|---|
| 模块源码和部署工具 | GitHub 固定标签 | Git commit + 文件 SHA256 |
| Python/Dart 制品 | CI 从固定标签构建 | artifact manifest + SHA256 |
| 系统依赖 | profile lock | 包名、版本、架构 |
| 模型 | 独立对象存储/离线盘 | model manifest + SHA256 |
| 歌曲和 stem | 资产库 | asset manifest + SHA256 |
| 数据库内容 | 结构化导出 | schema、行数、ID 一致性 |
| secrets | 人工或 secrets manager | 权限和必填字段，不记录值 |

### 3.2 明确禁止迁移

- 旧 venv 和 `site-packages`。
- 旧代码目录和手工 hotfix。
- 旧 systemd unit 原文件。
- `/etc`、用户 home 或 Docker volume 的整体复制。
- 日志、临时 render、下载缓存和 `.part` 文件。
- 来源不明的二进制、脚本和模型。
- 配置中指向 `/home/cat/cypher`、旧 Jetson 项目目录或固定旧 IP 的内容。

旧设备只用于只读取证、接口回放和行为对比，不能作为新环境的软件包来源。

## 4. 新环境目录与隔离

```text
/opt/harbeat/
  releases/<release>/         不可变 release
  current -> releases/<release>
  wheelhouse/                 审核后的离线依赖
  bootstrap/                  harbeatctl

/etc/harbeat/
  profiles/                   非敏感设备配置
  modules/                    模块配置
  secrets/                    权限 0700，不进入 Git
  active-release

/var/lib/harbeat/<service>/   服务私有状态
/var/log/harbeat/<service>/   服务日志
/srv/harbeat-assets/          歌曲、stem、模型、render
```

每个服务使用独立 Linux 用户、venv、配置和状态目录。release 目录只读，运行时不得写回源码。

## 5. 模块到服务的部署关系

13 个模块保持独立制品，但不创建 13 个网络服务。

### Jetson

| 服务 | 模块 | 隔离状态目录 |
|---|---|---|
| `harbeat-catalog-api` | `library-catalog` | `/var/lib/harbeat/catalog-api` |
| `harbeat-analysis-worker` | `audio-preprocess` | `/var/lib/harbeat/analysis-worker` |
| `harbeat-stem-worker` | `stem-separation` | `/var/lib/harbeat/stem-worker` |
| `harbeat-planning-api` | `sequence-planner`, `transition-planner` | `/var/lib/harbeat/planning-api` |
| `harbeat-render-worker` | `transition-renderer` | `/var/lib/harbeat/render-worker` |

### RK3588

| 服务 | 模块 | 隔离状态目录 |
|---|---|---|
| `harbeat-sync-worker` | `asset-sync` | `/var/lib/harbeat/sync-worker` |
| `harbeat-edge-agent` | `device-runtime`, `transition-orchestrator` | `/var/lib/harbeat/edge-agent` |
| `harbeat-audio-engine` | `audio-runtime` | `/var/lib/harbeat/audio-engine` |
| `harbeat-input-daemon` | `physical-input` | `/var/lib/harbeat/input-daemon` |

### 手机和验收端

- Flutter：`mobile-dj-control` 与 `device-runtime` Dart adapter。
- QA：`observability-e2e`。

## 6. 分阶段执行

### 阶段 A：部署工程 v0.3

交付：

- 12 个 Python 模块的 `pyproject.toml`。
- 1 个 Dart package 的现有 `pubspec.yaml` 校验。
- RK/Jetson profile 和 release manifest。
- 配置 schema 与示例配置。
- `harbeatctl` 的 bootstrap、build、stage、verify、activate、rollback、doctor。
- 本地 clean-room 测试。

构建工具固定为 `build==1.2.2.post1`、`setuptools==81.0.0`、`wheel==0.45.1`。构建脚本设置 `SOURCE_DATE_EPOCH`，并在发布前执行两次 wheel 构建哈希比较；若哈希不一致，release 不得进入设备。

通过标准：所有 Python wheel 可从 fresh clone 构建；模块测试 146/146；临时 root 中可以 stage、verify、activate 和 rollback；污染扫描拒绝旧路径。

### 阶段 B：基础镜像 v0.4

Jetson 固定 Ubuntu/JetPack、CUDA、cuDNN、Python、FFmpeg 和 libsndfile。RK 固定内核、网卡驱动、ALSA、实时权限、Python、FFmpeg 和 udev。

交付：

- `jetson-base-image-v1`、`rk-base-image-v1`。
- `system-packages.lock`。
- wheelhouse 和 manifest。
- 模型 manifest。
- 基础镜像恢复说明和校验脚本。

通过标准：同型号空设备可在不访问旧目录的情况下恢复基础环境；重启后驱动、GPU、声卡、网卡和时钟正常。

### 阶段 C：生产 adapter v0.5

为 clean core 补齐 HTTP、SQLAlchemy、Demucs、Flutter、sync transport、Unix socket、sounddevice 和 HID adapter。systemd 模板只能引用 `/opt/harbeat/current`、`/etc/harbeat`、`/var/lib/harbeat` 和 `/srv/harbeat-assets`。

通过标准：每个服务可独立启动和 health check；没有 `/home/cat/cypher` 等旧路径；缺少配置时明确失败，无静默 fallback。

### 阶段 D：影子环境 v0.9

新环境接收与旧生产相同输入，但不控制真实播放。逐项比较歌单、候选点、plan、WAV/meta、manifest、任务状态和耗时。

音频比较至少包含 WAV 长度、峰值、响度、relative jump、resume、beat phase 和人工听感。

### 阶段 E：分模块生产切换

依次切换 catalog、预处理/分轨、排歌、规划/渲染、同步、编排、播放、手机、实体输入。一次只切一个服务，每一步都保留回滚开关。

### 阶段 F：v1.0 与旧环境清理

发布 `functional-modules/v1.0.0` 前必须满足：

- 自动接歌、快切、能量切歌、风格切歌分别连续 5/5。
- 快切 ready `<=12s`，进入衔接 `<=15s`，触发误差 `<=100ms`。
- UI 进度连续，失败不破坏后续自动接歌。
- 真实 Demucs 输出四个有效 stem。
- 实体动作分别 20/20。
- 弱热点、断网、重复点击、进程重启和缓存损坏恢复通过。
- 同一 `operation_id` 可跨手机、Jetson、RK 追踪。
- 从空基础镜像重建成功。
- activate 和 rollback 演练成功。

旧环境先制作磁盘镜像并只读归档。新环境稳定运行一个完整验收周期，且断开旧目录后无引用，才允许删除旧运行目录。

## 7. 本轮直接执行清单

1. 从 `functional-modules/v0.2.0` 创建 `delivery/clean-environment-deployment-v0.3`。
2. 增加 Python 模块 package metadata。
3. 增加 release/profile/config manifests。
4. 实现并测试 `harbeatctl`。
5. 构建 12 个 wheel，校验 Dart package。
6. 在临时 clean root 执行 bootstrap、stage、verify、activate、rollback。
7. 执行 146 项模块测试。
8. 对可连接的 RK/Jetson 做只读 inventory；不修改服务。
9. 推送 GitHub 分支和可回滚标签。
10. 输出当前是否达到“允许清理设备”的明确判断。

## 8. 当前清理准入判断

本轮阶段 A 完成后，只表示新环境部署骨架可用。只有阶段 B 至 F 均通过，`cleanup_authorized` 才能从 `false` 改为 `true`。该字段必须写入 release acceptance report，不能由口头判断替代。

本轮执行报告：`deploy/clean-environment/acceptance-report-v0.3.0.json`。

本轮已完成阶段 A 的本地门禁：13 条模块命令、146 项测试、3 项部署控制器测试、12/12 wheel 构建、clean root 激活/回滚和旧路径扫描。工作站只有 Python 3.13，而 profile 锁定 Python 3.10，因此目标 runtime smoke 仍需在 Jetson/RK 基础镜像执行。该差异不能用工作站测试替代。
