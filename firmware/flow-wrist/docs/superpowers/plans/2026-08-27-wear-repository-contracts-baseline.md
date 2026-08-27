# Wear Repository and Contracts Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `harbeat-wear` 整理为 Wrist、Gateway、Contracts 和 Docs 四个明确边界，并建立双方共同验证的 BLE v1、Engine IPC v1、Golden Vectors 和 CI 基线。

**Architecture:** 当前仓库根目录就是 Wrist 工程；本计划用 Git move 将它完整迁入 `wrist/flow-wrist`，把跨设备协议提升到 `contracts`，但不改变固件行为。合同示例由一个标准库 Python 校验器加载，Wrist host tests 和后续 Gateway tests 都读取相同 Golden Vectors。

**Tech Stack:** Git、ESP-IDF 5.5.5、C11、Python 3.12、JSON、CBOR hex vectors、GitHub Actions

---

### Task 1: 建立仓库结构而不改变 Wrist 行为

**Files:**
- Move: 当前根目录 Wrist 工程 → `wrist/flow-wrist/`
- Create: `README.md`
- Create: `.gitignore`
- Create: `ring/README.md`
- Modify: `wrist/flow-wrist/README.md`

- [ ] **Step 1: 记录迁移前测试基线**

Run:

```bash
./tests/host/run.sh
python3 tests/host/test_hub_mock.py
python3 tests/host/test_dancer_assets.py
```

Expected: 全部通过。把终端结果复制到 `docs/test-results/GATE-0-CONTRACTS.md` 的 `Before repository move` 小节。

- [ ] **Step 2: 创建目标目录并移动已跟踪文件**

Run from repository root:

```bash
mkdir -p wrist/flow-wrist ring contracts docs/superpowers
git mv .gitignore wrist/flow-wrist/.gitignore
git mv CMakeLists.txt README.md assets components dependencies.lock main partitions.csv sdkconfig.ble.defaults sdkconfig.defaults tests tools wrist/flow-wrist/
git mv docs/AI-DEVELOPMENT-HANDOFF.md docs/ble-test.md docs/hardware-bringup.md docs/imu-gesture-test.md wrist/flow-wrist/docs/
```

`docs/superpowers/` 是仓库级规格与计划目录，保持原位。

Expected: `git status --short` 把原路径显示为 rename，不显示 build 目录。

- [ ] **Step 3: 创建根目录 `.gitignore`**

```gitignore
.DS_Store
.idea/
.vscode/
**/__pycache__/
**/*.py[cod]
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
**/.venv/
**/build/
**/build-*/
release/
*.log
*.jsonl
.env
.env.*
!.env.example
```

- [ ] **Step 4: 创建根目录 `README.md`**

```markdown
# HarBeat Wear

HarBeat Wear 保存 Flow Wrist、Wear Hub Gateway 和未来 Ring 的设备侧代码。

## 当前状态

- Wrist：Waveshare ESP32-S3-Touch-AMOLED-2.06，V0.1 Alpha 开发中；
- Hub Gateway：RK3588 / BlueZ，V0.1 开发中；
- Ring：只保留未来边界，本轮不实现。

## 目录

- `wrist/flow-wrist`：ESP-IDF Wrist 固件；
- `hub-gateway`：RK3588 BLE 与音乐引擎网关；
- `contracts`：BLE 和 Engine IPC 的唯一协议来源；
- `docs/superpowers`：批准的设计和执行计划；
- `ring`：未来 Ring 的范围说明。

先阅读 `docs/superpowers/specs/2026-08-27-flow-wrist-field-ready-v0.1-design.md`。
```

- [ ] **Step 5: 创建 `ring/README.md`**

```markdown
# Flow Ring

Ring 不属于 Wrist V0.1 现场版本。本目录在以下条件全部满足前不添加实现：

1. Wrist 与 RK3588 的 BLE v1 全链路通过；
2. Wrist 2 小时稳定性、30 分钟佩戴和 4 小时续航通过；
3. Ring 的角色、供电、传感器、配对和优先级另有批准规格。

Ring 未来通过 Hub Gateway 接入，不复用 Wrist Command UUID。
```

- [ ] **Step 6: 修改 Wrist README 的路径**

把工程路径改为：

```text
/Users/jihaobi/Documents/harbeat-wear/wrist/flow-wrist
```

把所有构建命令的前置目录固定为：

```bash
cd /Users/jihaobi/Documents/harbeat-wear/wrist/flow-wrist
```

- [ ] **Step 7: 运行迁移后测试**

Run:

```bash
cd wrist/flow-wrist
./tests/host/run.sh
python3 tests/host/test_hub_mock.py
python3 tests/host/test_dancer_assets.py
```

Expected: 与迁移前相同，全部通过。

- [ ] **Step 8: 提交目录迁移**

```bash
git add .gitignore README.md ring wrist docs/superpowers
git commit -m "chore: organize wear repository boundaries"
```

### Task 2: 提升 BLE v1 为共享合同

**Files:**
- Move: `wrist/flow-wrist/docs/ble-protocol-v1.md` → `contracts/ble-v1.md`
- Modify: `wrist/flow-wrist/README.md`
- Modify: `wrist/flow-wrist/docs/AI-DEVELOPMENT-HANDOFF.md`
- Modify: `wrist/flow-wrist/docs/ble-test.md`
- Create: `contracts/README.md`

- [ ] **Step 1: 写链接失败检查**

Create `tools/check_markdown_links.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)")


def main() -> int:
    missing: list[str] = []
    for path in ROOT.rglob("*.md"):
        if ".venv" in path.parts:
            continue
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {target}")
    if missing:
        print("\n".join(missing))
        return 1
    print("Markdown links: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 移动合同并确认检查失败**

```bash
git mv wrist/flow-wrist/docs/ble-protocol-v1.md contracts/ble-v1.md
python3 tools/check_markdown_links.py
```

Expected: 至少报告 Wrist README、handoff 或 ble-test 的旧链接不存在。

- [ ] **Step 3: 修正所有 BLE 合同链接**

固定相对路径：

```text
wrist/flow-wrist/README.md                  ../../contracts/ble-v1.md
wrist/flow-wrist/docs/ble-test.md           ../../../contracts/ble-v1.md
wrist/flow-wrist/docs/AI-DEVELOPMENT-HANDOFF.md  ../../../contracts/ble-v1.md
```

不要复制第二份协议文件。

- [ ] **Step 4: 创建 `contracts/README.md`**

```markdown
# Wear Contracts

本目录是跨设备协议的唯一事实来源。

- `ble-v1.md`：Wrist 与 Hub Gateway；
- `engine-ipc-v1.md`：Hub Gateway 与 Music Engine；
- `golden-vectors/`：实现无关的编码与消息样例。

兼容修改可补充说明；改变字段含义、类型、UUID、framing 或错误语义必须升主版本。
```

- [ ] **Step 5: 验证链接并提交**

```bash
python3 tools/check_markdown_links.py
git add contracts tools/check_markdown_links.py wrist/flow-wrist
git commit -m "docs: promote BLE v1 to shared contract"
```

Expected: `Markdown links: OK`。

### Task 3: 写 Engine IPC v1 合同和机器可读 Schema

**Files:**
- Create: `contracts/engine-ipc-v1.md`
- Create: `contracts/engine-ipc-v1.schema.json`
- Create: `contracts/examples/engine-ipc-v1.jsonl`
- Create: `tools/validate_contracts.py`

- [ ] **Step 1: 写失败的合同校验器**

```python
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = {
    "hello", "hello_ok", "get_state", "state", "set_direction",
    "accepted", "progress", "completed", "rejected",
}


def validate_engine_examples() -> None:
    path = ROOT / "contracts/examples/engine-ipc-v1.jsonl"
    seen: set[str] = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        message = json.loads(raw)
        assert message["v"] == 1, f"line {number}: v"
        assert message["kind"] in KINDS, f"line {number}: kind"
        seen.add(message["kind"])
    assert seen == KINDS, f"missing kinds: {KINDS - seen}"


def main() -> int:
    validate_engine_examples()
    print("Engine IPC v1 examples: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 运行并确认失败**

```bash
python3 tools/validate_contracts.py
```

Expected: `FileNotFoundError` 指向 `contracts/examples/engine-ipc-v1.jsonl`。

- [ ] **Step 3: 创建完整示例 JSONL**

```jsonl
{"v":1,"kind":"hello","client":"hub-gateway","capabilities":["set_energy","set_style","transition_progress"]}
{"v":1,"kind":"hello_ok","server":"music-engine","capabilities":["set_energy","set_style","transition_progress"]}
{"v":1,"kind":"get_state","request_id":"gw-test-state-1"}
{"v":1,"kind":"state","request_id":"gw-test-state-1","phase":"idle","locked":false,"current":{"energy":3,"style":"hiphop","bpm":96},"target":null,"eta_ms":0}
{"v":1,"kind":"set_direction","request_id":"gw-test-command-1","wrist_command_id":42,"op":"set_energy","value":5,"received_at_ms":1787812345678}
{"v":1,"kind":"accepted","request_id":"gw-test-command-1","target":{"energy":5,"style":"hiphop","bpm":102},"eta_ms":14000}
{"v":1,"kind":"progress","request_id":"gw-test-command-1","phase":"transitioning","eta_ms":7000}
{"v":1,"kind":"completed","request_id":"gw-test-command-1","current":{"energy":5,"style":"hiphop","bpm":102}}
{"v":1,"kind":"rejected","request_id":"gw-test-command-2","error":"no_candidate"}
```

- [ ] **Step 4: 创建 JSON Schema**

Use this top-level schema in `contracts/engine-ipc-v1.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://harbeat.local/contracts/engine-ipc-v1.schema.json",
  "type": "object",
  "required": ["v", "kind"],
  "properties": {
    "v": {"const": 1},
    "kind": {
      "enum": ["hello", "hello_ok", "get_state", "state", "set_direction", "accepted", "progress", "completed", "rejected"]
    },
    "request_id": {"type": "string", "minLength": 1, "maxLength": 64},
    "wrist_command_id": {"type": "integer", "minimum": 1, "maximum": 4294967295},
    "op": {"enum": ["set_energy", "set_style"]},
    "value": {"oneOf": [{"type": "integer", "minimum": 1, "maximum": 5}, {"enum": ["hiphop", "breaking", "funk", "locking"]}]},
    "phase": {"enum": ["idle", "accepted", "preparing", "transitioning", "completed", "rejected", "error"]},
    "eta_ms": {"type": "integer", "minimum": 0, "maximum": 120000},
    "error": {"enum": ["busy", "unsupported", "no_candidate", "engine_error", "protocol_error"]}
  },
  "additionalProperties": true
}
```

- [ ] **Step 5: 创建人类可读合同**

`contracts/engine-ipc-v1.md` 必须逐字明确：

```text
Socket: /run/flow-wear/engine.sock
Transport: AF_UNIX / SOCK_STREAM
Framing: UTF-8 NDJSON, one object per line
Maximum line: 16384 bytes including newline
Permissions: 0660, group flow-wear
Gateway response budget: 400 ms
```

把设计规格第 9–11 节的九种消息、错误、去重和重启规则完整复制为权威合同，不添加新消息类型。

- [ ] **Step 6: 验证并提交**

```bash
python3 tools/validate_contracts.py
git add contracts tools/validate_contracts.py
git commit -m "docs: freeze engine IPC v1 contract"
```

Expected: `Engine IPC v1 examples: OK`。

### Task 4: 建立 BLE Golden Vectors

**Files:**
- Create: `contracts/golden-vectors/ble-v1.json`
- Create: `wrist/flow-wrist/tests/host/test_contract_vectors.py`
- Modify: `tools/validate_contracts.py`

- [ ] **Step 1: 创建 Golden Vector 文件**

```json
{
  "commands": [
    {
      "name": "set_energy_5",
      "semantic": {"v": 1, "kind": "command", "id": 42, "op": "set_energy", "value": 5},
      "cbor_hex": "a5617601646b696e6467636f6d6d616e64626964182a626f706a7365745f656e657267796576616c756505"
    },
    {
      "name": "set_style_breaking",
      "semantic": {"v": 1, "kind": "command", "id": 43, "op": "set_style", "value": "breaking"},
      "cbor_hex": "a5617601646b696e6467636f6d6d616e64626964182b626f70697365745f7374796c656576616c756568627265616b696e67"
    }
  ]
}
```

- [ ] **Step 2: 写 Wrist 侧失败测试**

```python
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_vectors_are_available_from_wrist_tree() -> None:
    path = ROOT / "contracts/golden-vectors/ble-v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert [item["name"] for item in data["commands"]] == [
        "set_energy_5", "set_style_breaking"
    ]
    assert all(bytes.fromhex(item["cbor_hex"]) for item in data["commands"])
```

- [ ] **Step 3: 运行测试**

```bash
python3 -m pytest wrist/flow-wrist/tests/host/test_contract_vectors.py -q
```

Expected: PASS。该测试证明迁移后的相对路径和 vector 文件可用。

- [ ] **Step 4: 扩展合同校验器**

在 `validate_contracts.py` 增加：

```python
def validate_ble_vectors() -> None:
    path = ROOT / "contracts/golden-vectors/ble-v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    names = {item["name"] for item in data["commands"]}
    assert names == {"set_energy_5", "set_style_breaking"}
    for item in data["commands"]:
        encoded = bytes.fromhex(item["cbor_hex"])
        assert 0 < len(encoded) <= 192
    print("BLE v1 vectors: OK")
```

并在 `main()` 先调用 `validate_ble_vectors()`。

- [ ] **Step 5: 验证并提交**

```bash
python3 tools/validate_contracts.py
python3 -m pytest wrist/flow-wrist/tests/host/test_contract_vectors.py -q
git add contracts tools wrist/flow-wrist/tests/host/test_contract_vectors.py
git commit -m "test: add shared BLE v1 golden vectors"
```

### Task 5: 建立 CI Gate 0

**Files:**
- Create: `.github/workflows/contracts.yml`
- Create: `.github/workflows/wrist-host.yml`
- Create: `docs/test-results/GATE-0-CONTRACTS.md`

- [ ] **Step 1: 创建合同 CI**

```yaml
name: contracts
on:
  pull_request:
  push:
    branches: [main]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python3 tools/check_markdown_links.py
      - run: python3 tools/validate_contracts.py
      - run: python3 -m pytest wrist/flow-wrist/tests/host/test_contract_vectors.py -q
```

- [ ] **Step 2: 创建 Wrist host CI**

```yaml
name: wrist-host
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: ./tests/host/run.sh
        working-directory: wrist/flow-wrist
      - run: python3 tests/host/test_hub_mock.py
        working-directory: wrist/flow-wrist
      - run: python3 tests/host/test_dancer_assets.py
        working-directory: wrist/flow-wrist
```

- [ ] **Step 3: 创建 Gate 0 报告**

Run:

```bash
git rev-parse HEAD
python3 tools/check_markdown_links.py
python3 tools/validate_contracts.py
cd wrist/flow-wrist && ./tests/host/run.sh
```

将真实 SHA 和结果写入 `docs/test-results/GATE-0-CONTRACTS.md`。报告必须包含：目录迁移前后测试相同、合同检查通过、Golden Vectors 数量为 2。

- [ ] **Step 4: 检查无构建产物后提交**

```bash
git status --short
git ls-files | grep -E '(^|/)(build|build-ble|build-sim|\.venv)/' && exit 1 || true
git add .github docs/test-results/GATE-0-CONTRACTS.md
git commit -m "ci: establish wear contract baseline"
```

### Task 6: Gate 0 最终验收

**Files:**
- Verify only

- [ ] **Step 1: 运行完整 Gate 0 命令**

```bash
python3 tools/check_markdown_links.py
python3 tools/validate_contracts.py
python3 -m pytest wrist/flow-wrist/tests/host/test_contract_vectors.py -q
cd wrist/flow-wrist
./tests/host/run.sh
python3 tests/host/test_hub_mock.py
python3 tests/host/test_dancer_assets.py
git diff --check
```

Expected: 全部通过，`git diff --check` 无输出。

- [ ] **Step 2: 人工检查仓库边界**

```bash
find . -maxdepth 2 -type d | sort
```

Expected 根目录至少包含：

```text
./contracts
./docs
./ring
./tools
./wrist
./wrist/flow-wrist
```

- [ ] **Step 3: 标记 Gate 0 完成**

在 `docs/test-results/GATE-0-CONTRACTS.md` 末尾写：

```markdown
## Decision

Gate 0: PASS

Gateway implementation may start. BLE v1 and Engine IPC v1 are frozen.
```

提交报告更新：

```bash
git add docs/test-results/GATE-0-CONTRACTS.md
git commit -m "docs: record Gate 0 verification"
```
