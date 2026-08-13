# HarBeat 13 个功能模块注册表

本表记录 `v0.2.0` 干净边界版。`accepted` 表示该模块的独立代码、契约和测试已通过并推送到 GitHub，不表示已经替换生产服务。

| 模块 | 产品功能 | clean 分支 | v0.2.0 提交 | 测试 | 状态 | 仍需生产验收 |
|---|---|---|---|---:|---|---|
| `observability-e2e` | 三端日志和 E2E 验收 | `module/observability-e2e-clean-v0.2` | `886532d` | 9 | accepted | 接入真实手机/Jetson/RK 日志 |
| `device-runtime` | 手机连接 RK 与播放状态 | `module/device-runtime-clean-v0.2` | `291d102` | 22 | accepted | Flutter 持久化、热点换 IP、真实重连 |
| `library-catalog` | 曲库、歌单、ID 和 manifest | `module/library-catalog-clean-v0.2` | `98e89dd` | 12 | accepted | SQLAlchemy/HTTP adapter 与真实数据库 |
| `audio-preprocess` | 离线音乐结构和候选切点 | `module/audio-preprocess-clean-v0.2` | `79c88d3` | 10 | accepted | 全曲库回归、Jetson 数据库写入 |
| `stem-separation` | Demucs 四 stem 分轨 | `module/stem-separation-clean-v0.2` | `e6b25eb` | 9 | accepted | 真实模型、GPU、完整歌曲和原子发布 |
| `sequence-planner` | 自动排歌和能量曲线 | `module/sequence-planner-clean-v0.2` | `e380156` | 7 | accepted | 真实曲库排序与旧 preset 兼容观测 |
| `transition-planner` | 四种模式的选点和对齐 | `module/transition-planner-clean-v0.2` | `94c7fb6` | 7 | accepted | 真实曲库听感、候选评分和四模式回归 |
| `transition-renderer` | 生成衔接 WAV/meta | `module/transition-renderer-clean-v0.2` | `bb2d676` | 6 | accepted | v7/v9 真实音频 parity、响度和耗时 |
| `asset-sync` | RK 资源下载、校验和缓存 | `module/asset-sync-clean-v0.2` | `99e524f` | 9 | accepted | 弱热点、断点、并发和 RK 磁盘测试 |
| `transition-orchestrator` | 同步/准备/schedule 状态机 | `module/transition-orchestrator-clean-v0.2` | `1331b5b` | 7 | accepted | 真实 edge-agent adapter 与重试恢复 |
| `audio-runtime` | RK 双 deck 播放和到点切换 | `module/audio-runtime-clean-v0.2` | `d5f91ef` | 25 | accepted | 真实声卡、触发误差、无静音和 systemd |
| `mobile-dj-control` | 三种手动切歌意图和任务生命周期 | `module/mobile-dj-control-clean-v0.2` | `2473f66` | 11 | accepted | Flutter UI/HTTP/timer/storage adapter |
| `physical-input` | 实体按键、SFX 和音量 | `module/physical-input-clean-v0.2` | `c0334da` | 12 | accepted | 真实 HID、按键 7-9 消费端和 20/20 操作 |

每个模块的不可变标签为 `module/<module-name>/v0.2.0`，其回滚标签为 `module/<module-name>/v0.1.0`。

完整版本：

- 基础行为版：分支 `delivery/functional-module-extraction-20260813`，标签 `functional-modules/v0.1.0`。
- 干净边界版：分支 `delivery/functional-modules-clean-v0.2`，标签 `functional-modules/v0.2.0`。

## 验收含义

当前已经完成：

- 13 个模块边界、输入输出和依赖清单。
- 13 个独立 clean 分支和不可变标签。
- 13 条模块测试命令、146 项测试。
- 每个模块从 `v0.1.0` 回滚的路径。

当前没有完成：

- 手机 App 对 clean controller 的生产接入。
- Jetson API、数据库、Demucs 和渲染服务的生产替换。
- RK edge-agent、sync-worker、audio-engine 和 input-daemon 的 systemd 替换。
- 真实手机、Jetson、RK 的完整 E2E 和弱热点稳定性验收。

因此统一状态固定为：

```text
production_integration_applied = false
production_replacement_applied = false
```

## 接收规则

- 每个提交必须可从对应 clean 分支和 `v0.2.0` 标签到达。
- fresh clone 必须能执行该模块的 health check。
- 生产接入前必须保留旧实现和模块级回滚开关。
- 高风险音频模块必须比较真实 WAV、时间点、响度和主观听感，不以 mock 测试代替。
- 生产旧代码只有在静态引用、运行日志、数据引用和配置引用均为零后才允许归档。
