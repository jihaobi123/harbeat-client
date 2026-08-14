# 干净环境重构执行状态

日期：2026-08-14
分支：`rewrite/clean-core-operation-v0.4`

## 已完成

| 阶段 | 结果 | 证据/提交 |
|---|---|---|
| R0 原型冻结 | Stage E 代码和真机证据已归档，clean 分支从 `d737e3e` 开始 | `22085d8` |
| R1 只读设备盘点 | RK/Jetson 系统包、Python、端口、systemd、硬件清单已采集 | `b3eaacf` |
| R1 精确基础锁 | 多架构包名已修正；RK Rockchip FFmpeg 6.1 以独立 SHA256 制品锁定 | `0d968f4` |
| R1 恢复包 | 两台设备的硬件配置包已保存到 Git 外，禁入内容扫描为 0 | `r1-recovery-bundles-20260814.json` |
| R2 clean transport | edge-agent 已提供 state/play/pause/resume/seek 和 cached-render 转发，错误明确返回 | `709f748` |
| R3 operation 状态 | 四类意图共用幂等、持久、可查询/取消的 operation 状态机 | `8a24c06` |
| R3 render 边界 | Jetson 不再向 RK 暴露本地路径，改为 SHA256/size manifest 和受限 URL | `c07ae23` |
| R2 RK clean venv | 12/12 模块导入、锁定依赖、11 个声卡设备和临时 Unix socket ping 通过 | `r2-target-venv-validation-20260814.json` |
| R2 Jetson clean venv | 12/12 模块导入、CUDA 张量、锁定 Torch/torchaudio/Demucs、模型 SHA 和 FFmpeg 通过 | `r2-target-venv-validation-20260814.json` |
| 第三方制品库 | 根据目标机实际 freeze 生成 RK 21 个、Jetson 65 个经过筛选的 wheel SHA 清单 | `*.third-party-wheelhouse.json` |
| clean root 回滚 | 两个 release 完成 stage/verify/activate/rollback | 本次执行记录 |

当前测试：

```text
transition-orchestrator: 10 passed
clean deployment: 20 passed, 2 target-only skipped
harbeatctl validate: passed
12 个团队 Python wheel: built
```

## 当前阻塞

两台目标设备的 clean venv 已创建并验证。系统 Python 仍只作为只读证据，不作为新服务环境。

| 设备 | 当前缺口 |
|---|---|
| RK3588 | 尚未完成真实声卡连续播放 30 分钟与 prepare/schedule 20/20 |
| Jetson | clean venv 和 GPU doctor 已通过；R3 服务尚未在隔离端口做完整 operation 验收 |

新的 12 wheel 已保存到：

```text
D:\work\harbeat-device-backups\20260814\wheelhouse-r3\
```

它们已在两台目标机的 Python 3.10 clean venv 中完成 12/12 导入和 `pip check`。Torch/torchaudio 来自锁定 SHA 制品，不从旧 venv 复制 site-packages。

## 未完成

- R1：厂商基础镜像构建和空设备恢复测试。
- R2：真实声卡 30 分钟播放、prepare/schedule 20/20。
- R3：operation 执行器接入 planner/render/sync/audio，网络恢复和 15 秒快切验收。
- R4：能量/风格 preview 及手机 controller 重写。
- R5-R6：四类切歌真机验收、分轨、实体输入和三端 trace。
- R7：完整验收周后才允许永久删除旧文件。

## 门禁

```text
production_ready = false
r1_passed = false
legacy_runtime_quarantine_authorized = false
legacy_runtime_disable_authorized = false
legacy_files_delete_authorized = false
cleanup_authorized = false
```

下一执行项是完成 R3 operation 执行器，并在隔离端口串联 Jetson planning/render、RK sync/audio；不修改旧服务，不复用旧 venv。
