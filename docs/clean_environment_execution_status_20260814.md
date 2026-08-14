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
| clean root 回滚 | 两个 release 完成 stage/verify/activate/rollback | 本次执行记录 |

当前测试：

```text
transition-orchestrator: 10 passed
clean deployment: 20 passed, 2 target-only skipped
harbeatctl validate: passed
12 个团队 Python wheel: built
```

## 当前阻塞

目标设备尚未创建 clean venv。系统 Python 仅作为只读证据：

| 设备 | 当前缺口 |
|---|---|
| RK3588 | 缺 `soundfile`；`sounddevice/FastAPI/uvicorn` 与锁定版本不同 |
| Jetson | 缺 `Demucs/torch/torchaudio/FastAPI/httpx/uvicorn/SQLAlchemy/psycopg2/soundfile/librosa` 等 clean 依赖 |

新的 12 wheel 已保存到：

```text
D:\work\harbeat-device-backups\20260814\wheelhouse-r3\
```

它们尚未在目标 Python 3.10 clean venv 中安装验证。不得从旧 venv 复制包。

## 未完成

- R1：厂商基础镜像构建和空设备恢复测试。
- R2：目标 RK clean venv、真实声卡 30 分钟播放、prepare/schedule 20/20。
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

下一执行项是构建目标架构第三方 wheelhouse，在 RK/Jetson 的全新隔离目录创建 clean venv并执行 import/doctor；不修改旧服务，不复用旧 venv。
