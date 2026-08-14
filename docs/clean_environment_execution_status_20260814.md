# 干净环境重构执行状态

日期：2026-08-14
分支：`rewrite/clean-core-operation-v0.4`
核心代码基线：`870dbbc`

## 本轮结论

核心算法、模块边界和统一 transition operation 已整理为可独立构建、测试和部署的代码制品。本轮不再要求当前 RK/Jetson 混乱环境通过生产验收；设备网络、连续播放和手机真机验收转入后续单独计划。

这不代表生产环境可用，也不授权停止或删除旧服务。

## 已完成

| 阶段 | 结果 | 证据/提交 |
|---|---|---|
| R0 原型冻结 | Stage E 代码和真机证据已归档 | `22085d8` |
| R1 只读盘点与依赖锁 | RK/Jetson 系统、硬件、Python、模型和第三方 wheel 已形成清单 | `b201519` |
| R2 clean transport | RK 播放控制、asset sync、Unix socket 和 render 命令边界已实现 | `709f748` |
| R2 clean venv | RK 12/12 模块导入；Jetson 12/12 模块导入、CUDA 张量和 Demucs 模型 SHA 通过 | `508245a`, `b201519` |
| R3 operation 状态机 | `auto/fast/energy/style` 共用持久、幂等、可取消的 operation | `8a24c06` |
| R3 render manifest | Jetson 用 URL、size、SHA256 暴露 WAV/meta，不泄漏本地路径 | `c07ae23` |
| R3 执行器 | snapshot -> v2 plan -> v7 render -> target/pair sync -> prepare/schedule -> resume | `17ad432` |
| R3 并发规则 | 同 session 只允许一个活动 operation；终态不会被迟到 worker 覆盖 | `93f4678`, `870dbbc` |

核心算法保留：

- `dj_structure_v2` 预计算候选和全库 backfill 数据契约；
- v2 快切候选窗口、选点和节拍对齐；
- `three_band_default_v7_standalone_curve_no_energy_floor` 渲染；
- 局部鼓点对齐、重叠区轻微速度拉伸、三频段曲线、能量匹配和 resume 搜索；
- RK sample-clock prepare/schedule/render/resume 行为。

## 回归结果

| 范围 | 结果 |
|---|---|
| 12 个 Python 功能模块 | `144 passed` |
| mobile-dj-control 纯 Dart 契约 | `11 passed` |
| clean deployment adapters | `23 passed, 2 target-only skipped` |
| transition-orchestrator | `15 passed` |
| 12 个 Python wheel | 构建成功并生成 SHA256 manifest |

wheelhouse 位于 Git 外：

```text
D:\work\harbeat-device-backups\20260814\wheelhouse-core-v0.4.1
```

核心 orchestrator 制品：

```text
harbeat_transition_orchestrator-0.4.1-py3-none-any.whl
sha256=8777114a0f11a604195e8eb5a9a1f5889edb7518c5d0d13a7b4201adec0060c6
```

## 未通过与后续处理

| 项目 | 当前事实 | 后续处理 |
|---|---|---|
| RK 到 Jetson 网络 | RK 访问 `100.87.142.21:19020/19030` 均在 3 秒超时；本机可分别访问两端 | 新环境部署前单独设计固定网络或受管隧道，不写进核心算法 |
| R1 基础恢复 | 尚未做厂商基础镜像的空设备恢复 | 后续环境计划执行 |
| R2 真声卡验收 | 未完成连续播放 30 分钟、prepare/schedule 20/20 和误差 `<=100ms` | 后续设备运行层计划执行 |
| R3 真链路时间 | 隔离服务健康，但受 RK-Jetson 网络阻断，未做 5/5、10/10 和 15 秒验收 | 环境稳定后用现有 operation API 验收 |
| R4 手机重写 | preview backend 和 intent-only controllers 尚未实现 | 后续产品控制面计划执行 |
| R5 真机验收 | 自动、快切、能量、风格及随机交错未执行 | 不计入本轮核心代码交付 |

## 三端职责

| 端 | 最终职责 |
|---|---|
| 手机 | 选择目标、发送意图和 `request_id`、显示服务端 operation/playback 状态 |
| Jetson | 读取全库 v2 数据，执行选点、对齐和 v7 WAV/meta 渲染 |
| RK3588 | 同步目标音频与 pair，按 sample clock prepare/schedule，播放 render 后 resume |

## 门禁

```text
production_ready = false
r1_passed = false
legacy_runtime_quarantine_authorized = false
legacy_runtime_disable_authorized = false
legacy_files_delete_authorized = false
cleanup_authorized = false
```

旧环境仍是回滚来源。不得因为核心代码已上传而清理 RK/Jetson 旧服务或文件。
