# Flow Wrist V0.1 Field-Ready Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前 ESP32-S3 Wrist 原型、RK3588 Gateway 和正式音乐引擎推进到可重复验证、可回滚的小范围舞池 Alpha。

**Architecture:** 计划按五个可独立验收的 Gate 执行：先整理 `harbeat-wear` 并冻结合同，再建立独立 `hub-gateway`，随后接入现有 RK3588 audio-engine，最后加固 Wrist 并完成稳定性、续航和发布。每个 Gate 都有自动测试、真机证据和提交边界，前一 Gate 未通过不进入下一 Gate。

**Tech Stack:** ESP-IDF 5.5.5、LVGL 9.5.0、Waveshare BSP 2.0.0、Python 3.12、asyncio、BlueZ D-Bus、dbus-next、cbor2、Unix Domain Socket、systemd、pytest、Ruff、mypy、GitHub Actions

---

## 1. 执行前提

权威规格：

```text
docs/superpowers/specs/2026-08-27-flow-wrist-field-ready-v0.1-design.md
```

执行仓库：

```text
https://github.com/jihaobi123/harbeat-wear.git
```

正式执行时必须使用独立 clone，不再在 `harbeat-client` 的 subtree 导出分支上直接开发：

```bash
cd /Users/jihaobi/Documents
git clone https://github.com/jihaobi123/harbeat-wear.git harbeat-wear
cd /Users/jihaobi/Documents/harbeat-wear
git switch -c codex/wrist-field-ready-v0.1
```

Expected:

```text
Switched to a new branch 'codex/wrist-field-ready-v0.1'
```

执行前确认：

```bash
git status --short
git remote -v
```

Expected: 工作树为空，`origin` 指向 `harbeat-wear.git`。

## 2. 五份子计划

按以下顺序执行，不能并行修改跨计划合同：

| 顺序 | 文件 | 交付结果 | Gate |
|---:|---|---|---|
| 1 | `2026-08-27-wear-repository-contracts-baseline.md` | 独立仓库结构、BLE/IPC 合同、Golden Vectors、CI | Gate 0 |
| 2 | `2026-08-27-hub-gateway-vertical-slice.md` | 单主控配对、BlueZ GATT、Fake Engine、Command/Snapshot 闭环 | Gate 1 |
| 3 | `2026-08-27-rk3588-music-engine-wear-adapter.md` | 正式 audio-engine IPC v1 适配和真实切换 | Gate 2 |
| 4 | `2026-08-27-flow-wrist-field-hardening.md` | 手势默认关闭、诊断、内存、触控和故障 UI | Gate 3 |
| 5 | `2026-08-27-flow-wear-validation-release.md` | 2 小时、30 分钟、4 小时、发布和回滚 | Gate 4–5 |

## 3. 跨计划冻结类型

下列名称在五份计划中保持一致：

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Phase(StrEnum):
    IDLE = "idle"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    TRANSITIONING = "transitioning"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class MusicState:
    energy: int
    style: str
    bpm: int


@dataclass(frozen=True, slots=True)
class WristCommand:
    version: int
    command_id: int
    operation: Literal["set_energy", "set_style"]
    value: int | str
```

Engine IPC 的正式消息 `kind` 固定为：

```text
hello
hello_ok
get_state
state
set_direction
accepted
progress
completed
rejected
```

Wrist BLE phase 固定为：

```text
idle
accepted
preparing
transitioning
completed
rejected
error
```

错误码固定为：

```text
busy
unsupported
no_candidate
engine_error
protocol_error
unauthorized_device
transport_error
```

## 4. 跨计划时间预算

| 预算 | 上限 |
|---|---:|
| Wrist UI 生成并排队 Command | 100 ms |
| BLE Indication 到 Gateway 解码 | 150 ms |
| Gateway 校验、去重和 IPC 写入 | 50 ms |
| Engine accepted / rejected | 200 ms |
| Gateway 编码并写 accepted Snapshot | 100 ms |
| 合计 | 500 ms |

实现不得把完整 500 ms 全部分配给 Engine。Gateway 在 400 ms 尚未拿到 Engine 结果时返回 `engine_error`，并保持不执行或由 `request_id` 查询原任务，不能再提交一次。

## 5. 统一验证命令

### Wrist

```bash
cd wrist/flow-wrist
./tests/host/run.sh
python3 tests/host/test_hub_mock.py
python3 tests/host/test_dancer_assets.py
source /Users/jihaobi/.espressif/tools/activate_idf_v5.5.5.sh
idf.py -B build-sim build
idf.py -B build-ble build
```

Expected: 7 组 C tests、两组 Python tests 和两套 ESP-IDF build 全部通过。

### Gateway

```bash
cd hub-gateway
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest -q
```

Expected: Ruff 和 mypy 无错误，pytest 全部通过。

### Contract

```bash
python3 tools/validate_contracts.py
```

Expected:

```text
BLE v1 vectors: OK
Engine IPC v1 examples: OK
```

## 6. Gate 证据规则

每个 Gate 在 `docs/test-results/` 创建一份 Markdown：

```text
docs/test-results/GATE-0-CONTRACTS.md
docs/test-results/GATE-1-GATEWAY.md
docs/test-results/GATE-2-ENGINE.md
docs/test-results/GATE-3-WRIST.md
docs/test-results/GATE-4-STABILITY.md
docs/test-results/GATE-5-ALPHA.md
```

报告头固定为：

```markdown
# Gate N Verification

- Date: 2026-08-27
- Git commit: `<40-char SHA>`
- Wrist version: `wrist-v0.1.0-alpha.N`
- Gateway version: `gateway-v0.1.0-alpha.N`
- BLE contract: `1`
- Engine IPC contract: `1`
- RK3588 serial / asset ID: `<设备资产编号>`
- Wrist device ID: `FLOW-WRIST-F892`
```

设备资产编号由测试人员填写为实物标签，不写 MAC 地址。`<40-char SHA>` 和 `<设备资产编号>` 是报告模板字段，不是实施规格中的未决设计；生成报告时必须替换，CI 检测残留尖括号并失败。

## 7. 提交和合并规则

每项任务完成后运行：

```bash
git diff --check
git status --short
```

只 stage 当前任务列出的文件。提交信息使用：

```text
chore: organize wear repository boundaries
docs: freeze wear device contracts
feat: add gateway engine IPC
feat: add BlueZ wrist provisioning
feat: bridge wrist intent to music engine
fix: harden wrist field interaction
test: add wear stability harness
build: package wrist alpha release
```

Gate 合并前：

```bash
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
```

不得包含：

- `build/`、`build-ble/`、`build-sim/`；
- `.venv/`；
- `/var/lib/bluetooth` 内容；
- `/var/log/flow-wear` 日志；
- 实际 MAC、Bond key、数据库密码和设备 Token；
- 音频文件或现场录像。

## 8. 计划完成定义

五份子计划全部完成后必须同时成立：

- `main` 上 Wrist 和 Gateway CI 通过；
- RK3588 与真实 Wrist 完成加密 BLE v1 闭环；
- 能量和风格各完成一次真实音乐切换；
- accepted Snapshot 在 500 ms 内写回；
- 重复 Command 不会让 Engine 执行两次；
- Wrist、Gateway、Engine 任一单独重启后能恢复；
- 正式 Wrist 构建默认关闭手势；
- 2 小时桌面、30 分钟佩戴和 4 小时续航通过；
- Alpha 发布包可安装、校验和回滚；
- 所有 Gate 报告包含实际 commit 和测试设备资产编号。

满足这些条件后，才能创建：

```text
wrist-v0.1.0-alpha.1
gateway-v0.1.0-alpha.1
```

本轮结束后才讨论 Ring、OTA、BPM、调性和多手环控制。
