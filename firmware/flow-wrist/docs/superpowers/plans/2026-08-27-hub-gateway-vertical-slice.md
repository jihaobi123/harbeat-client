# Hub Gateway Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `harbeat-wear` 中实现可由 systemd 运行的 RK3588 Hub Gateway，完成单主控 Wrist 配对、自动重连、BLE v1 GATT 初始化、Command 去重、Fake Engine IPC 和 500 ms Snapshot ACK 闭环。

**Architecture:** Gateway 核心不直接依赖 D-Bus。模型、CBOR、IPC 和命令状态机可在 Mac/Linux host tests 运行；BlueZ 和 Engine 通过 Port 注入。真实 BlueZ 使用 dbus-next，测试使用内存 Fake，service 只编排生命周期。

**Tech Stack:** Python 3.12、asyncio、dbus-next 0.2.3、cbor2 5.7.1、pytest、Ruff、mypy、systemd、BlueZ D-Bus

---

### Task 1: Python 包、配置和领域模型

**Files:**
- Create: `hub-gateway/pyproject.toml`
- Create: `hub-gateway/src/flow_wear_gateway/__init__.py`
- Create: `hub-gateway/src/flow_wear_gateway/model.py`
- Create: `hub-gateway/src/flow_wear_gateway/config.py`
- Test: `hub-gateway/tests/test_model.py`

- [ ] **Step 1: 写失败测试**

```python
from flow_wear_gateway.model import MusicState, WristCommand


def test_music_state_rejects_unknown_style() -> None:
    try:
        MusicState(energy=3, style="house", bpm=120)
    except ValueError as exc:
        assert str(exc) == "unsupported style: house"
    else:
        raise AssertionError("unknown style accepted")


def test_wrist_command_validates_operation_value_pair() -> None:
    command = WristCommand(1, 42, "set_energy", 5)
    assert command.command_id == 42
    try:
        WristCommand(1, 43, "set_style", 5)
    except ValueError as exc:
        assert str(exc) == "set_style requires a style id"
    else:
        raise AssertionError("invalid command accepted")
```

- [ ] **Step 2: 创建包配置后确认测试因缺少模型失败**

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "flow-wear-gateway"
version = "0.1.0a1"
requires-python = ">=3.12,<3.13"
dependencies = ["cbor2==5.7.1", "dbus-next==0.2.3"]

[project.optional-dependencies]
dev = ["mypy==1.17.1", "pytest==8.4.2", "pytest-asyncio==1.1.0", "ruff==0.12.11"]

[project.scripts]
flow-wear-gateway = "flow_wear_gateway.service:main"
flow-wearctl = "flow_wear_gateway.cli:main"
flow-wear-fake-engine = "flow_wear_gateway.fake_engine:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["flow_wear_gateway"]
```

Run:

```bash
cd hub-gateway
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest tests/test_model.py -q
```

Expected: `flow_wear_gateway.model` import 失败。

- [ ] **Step 3: 实现模型**

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

STYLES = ("hiphop", "breaking", "funk", "locking")


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

    def __post_init__(self) -> None:
        if not 1 <= self.energy <= 5:
            raise ValueError(f"energy out of range: {self.energy}")
        if self.style not in STYLES:
            raise ValueError(f"unsupported style: {self.style}")
        if not 1 <= self.bpm <= 300:
            raise ValueError(f"bpm out of range: {self.bpm}")


@dataclass(frozen=True, slots=True)
class WristCommand:
    version: int
    command_id: int
    operation: Literal["set_energy", "set_style"]
    value: int | str

    def __post_init__(self) -> None:
        if self.version != 1 or not 1 <= self.command_id <= 0xFFFFFFFF:
            raise ValueError("invalid command header")
        if self.operation == "set_energy":
            if not isinstance(self.value, int) or not 1 <= self.value <= 5:
                raise ValueError("set_energy requires an integer from 1 to 5")
        elif self.operation == "set_style":
            if not isinstance(self.value, str) or self.value not in STYLES:
                raise ValueError("set_style requires a style id")
        else:
            raise ValueError(f"unsupported operation: {self.operation}")


@dataclass(frozen=True, slots=True)
class EngineResult:
    request_id: str
    accepted: bool
    target: MusicState | None = None
    eta_ms: int = 0
    error: str = ""
```

- [ ] **Step 4: 实现配置**

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    adapter_path: str = "/org/bluez/hci0"
    engine_socket: Path = Path("/run/flow-wear/engine.sock")
    state_file: Path = Path("/var/lib/flow-wear/gateway/state.json")
    control_socket: Path = Path("/run/flow-wear/gateway-control.sock")
    pair_window_seconds: int = 120
    gatt_timeout_seconds: float = 5.0
    engine_ack_timeout_seconds: float = 0.4
    max_ipc_line_bytes: int = 16384
```

- [ ] **Step 5: 验证并提交**

```bash
.venv/bin/pytest tests/test_model.py -q
.venv/bin/ruff check .
.venv/bin/mypy src
git add hub-gateway
git commit -m "feat: add gateway domain model"
```

### Task 2: BLE v1 Codec

**Files:**
- Create: `hub-gateway/src/flow_wear_gateway/protocol/__init__.py`
- Create: `hub-gateway/src/flow_wear_gateway/protocol/ble_v1.py`
- Test: `hub-gateway/tests/test_ble_v1.py`

- [ ] **Step 1: 写共享 Vector 失败测试**

```python
import json
from pathlib import Path

from flow_wear_gateway.protocol.ble_v1 import decode_command

ROOT = Path(__file__).resolve().parents[2]


def test_decode_shared_command_vectors() -> None:
    data = json.loads((ROOT / "contracts/golden-vectors/ble-v1.json").read_text())
    decoded = [decode_command(bytes.fromhex(item["cbor_hex"])) for item in data["commands"]]
    assert [(item.command_id, item.operation, item.value) for item in decoded] == [
        (42, "set_energy", 5),
        (43, "set_style", "breaking"),
    ]
```

- [ ] **Step 2: 运行并确认 import 失败**

```bash
.venv/bin/pytest tests/test_ble_v1.py -q
```

- [ ] **Step 3: 实现 Command 解码和 Snapshot 编码**

```python
import cbor2

from flow_wear_gateway.model import MusicState, Phase, WristCommand


def decode_command(payload: bytes) -> WristCommand:
    if not 1 <= len(payload) <= 192:
        raise ValueError("command size out of range")
    value = cbor2.loads(payload)
    if not isinstance(value, dict) or value.get("kind") != "command":
        raise ValueError("invalid command envelope")
    return WristCommand(value.get("v"), value.get("id"), value.get("op"), value.get("value"))


def encode_snapshot(*, session_id: str, revision: int, ack_id: int, phase: Phase,
                    locked: bool, eta_ms: int, current: MusicState,
                    target: MusicState | None, error: str) -> bytes:
    if len(session_id) != 16 or any(ch not in "0123456789abcdef" for ch in session_id):
        raise ValueError("invalid session id")
    music = lambda item: {"energy": item.energy, "style": item.style, "bpm": item.bpm}
    payload = cbor2.dumps({
        "v": 1, "kind": "snapshot", "session_id": session_id,
        "revision": revision, "ack_id": ack_id, "phase": phase.value,
        "locked": locked, "eta_ms": eta_ms, "current": music(current),
        "target": None if target is None else music(target), "error": error or None,
    })
    if len(payload) > 512:
        raise ValueError("snapshot exceeds 512 bytes")
    return payload
```

- [ ] **Step 4: 添加 Snapshot 断言并验证**

```python
def test_snapshot_has_matching_ack() -> None:
    payload = encode_snapshot(
        session_id="8f3a19d04b7c221e", revision=18, ack_id=42,
        phase=Phase.ACCEPTED, locked=True, eta_ms=14000,
        current=MusicState(3, "hiphop", 96), target=MusicState(5, "hiphop", 102), error="",
    )
    assert cbor2.loads(payload)["ack_id"] == 42
```

Run and commit:

```bash
.venv/bin/pytest tests/test_ble_v1.py -q
git add hub-gateway
git commit -m "feat: add gateway BLE v1 codec"
```

### Task 3: Engine IPC Client 和 Fake Engine

**Files:**
- Create: `hub-gateway/src/flow_wear_gateway/engine/__init__.py`
- Create: `hub-gateway/src/flow_wear_gateway/engine/ipc.py`
- Create: `hub-gateway/src/flow_wear_gateway/fake_engine.py`
- Test: `hub-gateway/tests/test_engine_ipc.py`

- [ ] **Step 1: 写超长消息失败测试**

```python
import asyncio
from pathlib import Path

from flow_wear_gateway.engine.ipc import EngineClient


async def test_engine_client_rejects_oversized_line(tmp_path: Path) -> None:
    socket_path = tmp_path / "engine.sock"
    async def handler(reader, writer):
        await reader.readline()
        writer.write(b"{" + b"x" * 17000 + b"}\n")
        await writer.drain()
        writer.close()
    server = await asyncio.start_unix_server(handler, path=socket_path)
    try:
        client = EngineClient(socket_path)
        try:
            await client.request({"v": 1, "kind": "hello"}, timeout=0.4)
        except ValueError as exc:
            assert "exceeds 16384" in str(exc)
        else:
            raise AssertionError("oversized line accepted")
    finally:
        server.close()
        await server.wait_closed()
```

- [ ] **Step 2: 运行并确认 import 失败**

```bash
.venv/bin/pytest tests/test_engine_ipc.py -q
```

- [ ] **Step 3: 实现 NDJSON Client**

```python
import asyncio
import json
from pathlib import Path
from typing import Any


class EngineClient:
    def __init__(self, socket_path: Path, max_line_bytes: int = 16384) -> None:
        self._path = socket_path
        self._max = max_line_bytes

    async def request(self, message: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(self._path), timeout)
        try:
            data = json.dumps(message, separators=(",", ":")).encode() + b"\n"
            if len(data) > self._max:
                raise ValueError(f"engine IPC line exceeds {self._max} bytes")
            writer.write(data)
            await asyncio.wait_for(writer.drain(), timeout)
            line = await asyncio.wait_for(reader.readuntil(b"\n"), timeout)
            if len(line) > self._max:
                raise ValueError(f"engine IPC line exceeds {self._max} bytes")
            response = json.loads(line)
            if response.get("v") != 1 or not isinstance(response.get("kind"), str):
                raise ValueError("invalid engine IPC envelope")
            return response
        finally:
            writer.close()
            await writer.wait_closed()
```

- [ ] **Step 4: 实现 Fake Engine 的固定映射**

`fake_engine.py` 的 handler 使用以下完整分支，不加入随机选曲：

```python
async def handle_message(message: dict[str, object], state: dict[str, object]) -> dict[str, object]:
    kind = message.get("kind")
    if kind == "hello":
        return {"v": 1, "kind": "hello_ok", "server": "fake-engine",
                "capabilities": ["set_energy", "set_style", "transition_progress"]}
    if kind == "get_state":
        return {"v": 1, "kind": "state", "request_id": message["request_id"], **state}
    if kind == "set_direction":
        target = dict(state["current"])
        target["energy" if message["op"] == "set_energy" else "style"] = message["value"]
        state.update({"phase": "accepted", "locked": True, "target": target, "eta_ms": 12000})
        return {"v": 1, "kind": "accepted", "request_id": message["request_id"],
                "target": target, "eta_ms": 12000}
    return {"v": 1, "kind": "rejected",
            "request_id": message.get("request_id", "unknown"), "error": "protocol_error"}
```

Fake Engine 对 `set_direction` 写回 accepted 后保持连接，按固定时间轴在 250 ms、750 ms、1250 ms 写 `progress/preparing`、`progress/transitioning`、`completed`；completed 时把 target 提升为 current。增加 `flow-wear-fake-engine` CLI 入口，监听由 `--socket` 指定的路径。自动测试使用注入时钟，不使用真实 `sleep`。

- [ ] **Step 5: 验证并提交**

```bash
.venv/bin/pytest tests/test_engine_ipc.py -q
.venv/bin/ruff check .
.venv/bin/mypy src
git add hub-gateway
git commit -m "feat: add gateway engine IPC"
```

### Task 4: Controller、去重和 Snapshot Authority

**Files:**
- Create: `hub-gateway/src/flow_wear_gateway/ports.py`
- Create: `hub-gateway/src/flow_wear_gateway/controller.py`
- Create: `hub-gateway/tests/fakes.py`
- Test: `hub-gateway/tests/test_controller.py`

- [ ] **Step 1: 定义 Ports**

```python
from typing import Protocol
from flow_wear_gateway.model import EngineResult, WristCommand


class EnginePort(Protocol):
    async def submit(self, request_id: str, command: WristCommand,
                     on_event: "EngineEventCallback") -> EngineResult: ...


class WristPort(Protocol):
    async def write_snapshot(self, payload: bytes) -> None: ...
```

- [ ] **Step 2: 写重复命令失败测试**

```python
async def test_duplicate_executes_engine_once() -> None:
    controller, engine, wrist = make_controller()
    await controller.on_command(ENERGY_5_VECTOR)
    await controller.on_command(ENERGY_5_VECTOR)
    assert engine.command_ids == [42]
    assert len(wrist.snapshots) == 2
```

- [ ] **Step 3: 实现 Controller**

```python
import secrets
from flow_wear_gateway.model import MusicState, Phase
from flow_wear_gateway.protocol.ble_v1 import decode_command, encode_snapshot


class GatewayController:
    def __init__(self, session_id, engine, wrist, current: MusicState) -> None:
        self.session_id, self.engine, self.wrist, self.current = session_id, engine, wrist, current
        self.revision = 0
        self.locked = False
        self.by_command: dict[int, bytes] = {}

    async def on_command(self, payload: bytes) -> None:
        command = decode_command(payload)
        if command.command_id in self.by_command:
            await self.wrist.write_snapshot(self.by_command[command.command_id])
            return
        if self.locked:
            result = self._snapshot(command.command_id, Phase.REJECTED, True, 0, None, "busy")
        else:
            reply = await self.engine.submit("gw-" + secrets.token_hex(12), command,
                                             self.on_engine_event)
            if reply.accepted and reply.target is not None:
                self.locked = True
                result = self._snapshot(command.command_id, Phase.ACCEPTED, True,
                                        reply.eta_ms, reply.target, "")
            else:
                result = self._snapshot(command.command_id, Phase.REJECTED, False,
                                        0, None, reply.error or "engine_error")
        self.by_command[command.command_id] = result
        await self.wrist.write_snapshot(result)

    def _snapshot(self, ack_id, phase, locked, eta_ms, target, error) -> bytes:
        self.revision += 1
        return encode_snapshot(session_id=self.session_id, revision=self.revision,
            ack_id=ack_id, phase=phase, locked=locked, eta_ms=eta_ms,
            current=self.current, target=target, error=error)
```

`GatewayController` 同时保存 active `command_id/request_id/target`。`on_engine_event()` 只接受 active request：progress 生成同一 `ack_id` 的 Snapshot；completed 将 target 提升为 current 并 `locked=false`；rejected/error 清空 target 并 `locked=false`。每个新 Snapshot 都覆盖 `by_command[command_id]`，所以重复 Command 始终返回该命令的最新权威状态。非 active、倒序或终态后的 Engine 事件只记日志，不改变 UI。

补充测试：accepted 后依次收到 preparing/transitioning/completed 时 revision 严格递增、ack_id 不变、最终解锁；accepted 后 transport 断开进入 error 并解锁；completed 后重放相同 Command 返回 completed，Engine 总调用次数仍为 1。

- [ ] **Step 4: 添加 500 ms 测试**

```python
async def test_accepted_snapshot_is_written_under_500_ms() -> None:
    controller, _, wrist = make_controller(engine_delay=0.20)
    started = time.perf_counter()
    await controller.on_command(ENERGY_5_VECTOR)
    assert time.perf_counter() - started < 0.5
    assert len(wrist.snapshots) == 1
```

- [ ] **Step 5: 验证并提交**

```bash
.venv/bin/pytest tests/test_controller.py -q
.venv/bin/ruff check .
.venv/bin/mypy src
git add hub-gateway
git commit -m "feat: add authoritative gateway command flow"
```

### Task 5: 原子持久化和 Allowlist

**Files:**
- Create: `hub-gateway/src/flow_wear_gateway/persistence.py`
- Test: `hub-gateway/tests/test_persistence.py`

- [ ] **Step 1: 写失败测试**

```python
def test_store_never_persists_pending_command(tmp_path) -> None:
    store = GatewayStore(tmp_path / "state.json")
    store.save(device_id="FLOW-WRIST-F892", identity_address="28:84:85:90:F8:92",
               current={"energy": 3, "style": "hiphop", "bpm": 96})
    value = store.load()
    assert value["device_id"] == "FLOW-WRIST-F892"
    assert "pending_command" not in value
```

- [ ] **Step 2: 实现原子 Store**

```python
import json
import os
from pathlib import Path


class GatewayStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, object]:
        return {} if not self.path.exists() else json.loads(self.path.read_text())

    def save(self, *, device_id: str, identity_address: str,
             current: dict[str, int | str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = {"v": 1, "device_id": device_id, "identity_address": identity_address,
                 "current": current, "ble_contract": 1, "engine_ipc_contract": 1}
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w") as handle:
            json.dump(value, handle, separators=(",", ":"), sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
```

- [ ] **Step 3: 添加损坏 JSON 测试**

```python
def test_corrupt_state_is_not_ignored(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{broken")
    with pytest.raises(ValueError):
        GatewayStore(path).load()
```

- [ ] **Step 4: 验证并提交**

```bash
.venv/bin/pytest tests/test_persistence.py -q
git add hub-gateway
git commit -m "feat: persist one authorized wrist"
```

### Task 6: BlueZ Pairing Window

**Files:**
- Create: `hub-gateway/src/flow_wear_gateway/bluez/__init__.py`
- Create: `hub-gateway/src/flow_wear_gateway/bluez/agent.py`
- Create: `hub-gateway/src/flow_wear_gateway/bluez/manager.py`
- Test: `hub-gateway/tests/test_bluez_manager.py`

- [ ] **Step 1: 写候选选择测试**

```python
def test_pair_candidate_requires_service_and_uses_strongest_rssi() -> None:
    devices = [
        {"path": "/weak", "name": "FLOW-WRIST-1111", "rssi": -72, "uuids": [FLOW_SERVICE]},
        {"path": "/wrong", "name": "FLOW-WRIST-2222", "rssi": -30, "uuids": []},
        {"path": "/strong", "name": "FLOW-WRIST-F892", "rssi": -48, "uuids": [FLOW_SERVICE]},
    ]
    assert select_pair_candidate(devices)["path"] == "/strong"
```

- [ ] **Step 2: 实现候选选择**

```python
FLOW_SERVICE = "464c4f57-0001-4f57-8101-000000000001"


def select_pair_candidate(devices: list[dict[str, object]]) -> dict[str, object]:
    matching = [item for item in devices
        if str(item.get("name", "")).startswith("FLOW-WRIST-")
        and FLOW_SERVICE in [str(value).lower() for value in item.get("uuids", [])]]
    if not matching:
        raise LookupError("no Flow Wrist found")
    return max(matching, key=lambda item: int(item.get("rssi", -127)))
```

- [ ] **Step 3: 实现受限 Agent**

`NoInputNoOutputAgent` 只授权本次选择的 Device Path 和 Flow Service。核心方法固定为：

```python
@method()
def RequestAuthorization(self, device: "o") -> None:
    if str(device) != self.allowed_device_path:
        raise DBusError("org.bluez.Error.Rejected", "device outside pairing window")

@method()
def AuthorizeService(self, device: "o", uuid: "s") -> None:
    if str(device) != self.allowed_device_path or str(uuid).lower() != FLOW_SERVICE:
        raise DBusError("org.bluez.Error.Rejected", "service not authorized")
```

`Release` 和 `Cancel` 返回 `None`。Agent capability 固定为 `NoInputNoOutput`。

- [ ] **Step 4: 实现固定 D-Bus 顺序**

`BluezManager.open_pair_window()` 必须按以下顺序调用，每个 call 包裹 5 秒 timeout：

```text
Adapter Powered=true
Adapter Pairable=true
SetDiscoveryFilter UUIDs=[FLOW_SERVICE], Transport=le, DuplicateData=false
StartDiscovery
观察 ObjectManager，最长 120 秒
StopDiscovery
选择最强匹配设备
RegisterAgent
Device1.Pair
Adapter Pairable=false
UnregisterAgent
```

`finally` 无条件执行 StopDiscovery、Pairable=false 和 UnregisterAgent。

- [ ] **Step 5: 写清理测试**

```python
async def test_pair_failure_always_closes_window() -> None:
    bus = FakeBluezBus(pair_error=RuntimeError("auth failed"))
    with pytest.raises(RuntimeError, match="auth failed"):
        await BluezManager(bus, pair_window_seconds=1).open_pair_window()
    assert bus.calls[-3:] == ["StopDiscovery", "Pairable=false", "UnregisterAgent"]
```

- [ ] **Step 6: 验证并提交**

```bash
.venv/bin/pytest tests/test_bluez_manager.py -q
.venv/bin/ruff check .
.venv/bin/mypy src
git add hub-gateway
git commit -m "feat: add BlueZ wrist provisioning"
```

### Task 7: 远程 GATT 初始化

**Files:**
- Create: `hub-gateway/src/flow_wear_gateway/bluez/gatt.py`
- Test: `hub-gateway/tests/test_gatt.py`

- [ ] **Step 1: 写顺序测试**

```python
async def test_ready_sequence_is_subscribe_catalog_snapshot() -> None:
    remote = FakeRemoteGatt()
    client = WristGattClient(remote, timeout=5.0)
    await client.initialize(catalog=b"catalog", snapshot=b"snapshot")
    assert remote.calls == [
        ("StartNotify", COMMAND_UUID),
        ("WriteValue", CATALOG_UUID, b"catalog", "request"),
        ("WriteValue", STATE_UUID, b"snapshot", "request"),
    ]
```

- [ ] **Step 2: 实现 UUID 和查找**

```python
COMMAND_UUID = "464c4f57-0001-4f57-8101-000000000002"
STATE_UUID = "464c4f57-0001-4f57-8101-000000000003"
CATALOG_UUID = "464c4f57-0001-4f57-8101-000000000004"
```

ObjectManager 缺任何 UUID 时抛：

```python
raise RuntimeError(f"required characteristic missing: {uuid}")
```

- [ ] **Step 3: 实现初始化和 Command 回调**

严格执行 StartNotify → Catalog Write Request → State Write Request。只有三步完成才设置 `ready=True`。PropertiesChanged 只在接口为 `org.bluez.GattCharacteristic1` 且 `Value` 存在时读取。Command 长度必须为 1–192 B。

Snapshot 写入实现：

```python
async def write_snapshot(self, payload: bytes) -> None:
    if len(payload) > 512:
        raise ValueError("snapshot exceeds 512 bytes")
    await asyncio.wait_for(
        self.state_characteristic.call_write_value(
            payload, {"type": Variant("s", "request")}
        ),
        timeout=self.timeout,
    )
```

- [ ] **Step 4: 添加半同步失败测试**

```python
async def test_catalog_failure_never_marks_ready() -> None:
    remote = FakeRemoteGatt(fail_on="catalog")
    client = WristGattClient(remote, timeout=5.0)
    with pytest.raises(RuntimeError):
        await client.initialize(catalog=b"catalog", snapshot=b"snapshot")
    assert client.ready is False
```

- [ ] **Step 5: 验证并提交**

```bash
.venv/bin/pytest tests/test_gatt.py -q
.venv/bin/ruff check .
.venv/bin/mypy src
git add hub-gateway
git commit -m "feat: initialize wrist GATT session"
```

### Task 8: Service、重连和 CLI

**Files:**
- Create: `hub-gateway/src/flow_wear_gateway/service.py`
- Create: `hub-gateway/src/flow_wear_gateway/cli.py`
- Test: `hub-gateway/tests/test_service.py`
- Test: `hub-gateway/tests/test_cli.py`

- [ ] **Step 1: 写重连测试**

```python
def test_reconnect_delay_caps_at_15_seconds() -> None:
    delays = reconnect_delays(jitter=False)
    assert [next(delays) for _ in range(7)] == [1, 2, 4, 8, 15, 15, 15]
```

- [ ] **Step 2: 实现退避**

```python
def reconnect_delays(*, jitter: bool = True):
    base = 1
    while True:
        yield base * (random.uniform(0.8, 1.2) if jitter else 1.0)
        base = min(base * 2, 15)
```

- [ ] **Step 3: 实现启动顺序**

Service 固定顺序：load state → connect Engine → hello → get_state → connect authorized Wrist → discover GATT → subscribe → Catalog → initial Snapshot → READY。

任一连接断开后执行：

```python
self.ready = False
await self.gatt.close()
for delay in reconnect_delays():
    await asyncio.sleep(delay)
    if await self.try_full_startup():
        break
```

进程启动生成 `session_id = secrets.token_hex(8)`，不读取旧 session_id。

- [ ] **Step 4: 实现管理 Socket 和 CLI**

Control socket `/run/flow-wear/gateway-control.sock` 只接受 `status`、`devices`、`pair`、`unpair`、`doctor`。CLI 只通过这个 socket 调 Gateway，不直接调用 BlueZ。

`doctor` 固定检查：BlueZ、Adapter Powered、Bond/Allowlist 一致、Engine hello、三个 GATT UUID、Gateway READY。任一失败退出 1。

- [ ] **Step 5: 写未 READY 禁发测试**

```python
async def test_command_is_rejected_before_ready() -> None:
    service = make_service(engine_connected=False)
    with pytest.raises(RuntimeError, match="gateway not ready"):
        await service.accept_command(ENERGY_5_VECTOR)
```

- [ ] **Step 6: 验证并提交**

```bash
.venv/bin/pytest tests/test_service.py tests/test_cli.py -q
.venv/bin/ruff check .
.venv/bin/mypy src
git add hub-gateway
git commit -m "feat: run gateway as reconnecting service"
```

### Task 9: systemd 和权限

**Files:**
- Create: `hub-gateway/packaging/flow-wear-gateway.service`
- Create: `hub-gateway/packaging/flow-wear-gateway.tmpfiles.conf`
- Create: `hub-gateway/packaging/flow-wear-gateway.logrotate`
- Create: `hub-gateway/packaging/install.sh`
- Test: `hub-gateway/tests/test_packaging.py`

- [ ] **Step 1: 写 service 加固测试**

```python
def test_systemd_service_has_required_hardening() -> None:
    text = Path("packaging/flow-wear-gateway.service").read_text()
    for line in ["User=flow-wear-gateway", "Group=flow-wear", "Restart=on-failure",
                 "NoNewPrivileges=true", "ProtectSystem=strict"]:
        assert line in text
```

- [ ] **Step 2: 创建 systemd service**

```ini
[Unit]
Description=Flow Wear Hub Gateway
After=bluetooth.service cypher-audio-engine.service
Wants=bluetooth.service

[Service]
Type=simple
User=flow-wear-gateway
Group=flow-wear
ExecStart=/opt/flow-wear/gateway/venv/bin/flow-wear-gateway
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/run/flow-wear /var/lib/flow-wear /var/log/flow-wear

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: 创建目录和日志规则**

`tmpfiles.conf`：

```text
d /run/flow-wear 0770 flow-wear-gateway flow-wear -
d /var/lib/flow-wear/gateway 0750 flow-wear-gateway flow-wear -
d /var/log/flow-wear 0750 flow-wear-gateway flow-wear -
```

`logrotate`：

```text
/var/log/flow-wear/gateway.jsonl {
  daily
  rotate 7
  missingok
  notifempty
  compress
  copytruncate
}
```

- [ ] **Step 4: 创建 idempotent install**

`install.sh` 必须创建 group/system user、安装 wheel 到 `/opt/flow-wear/gateway/venv`、安装三个 packaging 文件并 daemon-reload。第二次执行返回 0，不自动进入配对模式。

- [ ] **Step 5: 验证并提交**

```bash
.venv/bin/pytest tests/test_packaging.py -q
shellcheck packaging/install.sh
git add hub-gateway
git commit -m "build: package gateway system service"
```

### Task 10: CI 和 Gate 1 RK3588 验收

**Files:**
- Create: `.github/workflows/gateway.yml`
- Create: `docs/test-results/GATE-1-GATEWAY.md`
- Modify: `wrist/flow-wrist/docs/ble-test.md`

- [ ] **Step 1: 创建 CI**

```yaml
name: gateway
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: hub-gateway
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: python -m pip install -e '.[dev]'
      - run: ruff check .
      - run: mypy src
      - run: pytest -q
```

- [ ] **Step 2: RK3588 安装并 Pair**

```bash
sudo /opt/harbeat-wear/hub-gateway/packaging/install.sh
sudo systemd-run --unit=flow-wear-fake-engine --uid=flow-wear-gateway --gid=flow-wear \
  /opt/flow-wear/gateway/venv/bin/flow-wear-fake-engine --socket /run/flow-wear/engine.sock
sudo systemctl start flow-wear-gateway
flow-wearctl pair
flow-wearctl doctor
```

Expected 六项均为 PASS：BlueZ、Adapter、Bond、Engine IPC v1、Wrist GATT、Gateway READY。

- [ ] **Step 3: 实机命令**

Wrist 各执行一次 ENERGY 和 STYLE。每次必须是一个 Wrist Command、一个 Engine Request、一个 matching `ack_id`，ACK < 500 ms。

- [ ] **Step 4: 重启和重复命令**

```bash
sudo systemctl restart flow-wear-gateway
sudo systemctl restart bluetooth
```

每次在 15 秒目标内恢复 READY。重放同一个 CBOR Command 两次，Fake Engine 只记录一次请求。

- [ ] **Step 5: 写 Gate 1 报告**

报告记录 RK OS、BlueZ、Adapter、Wrist ID、Pair 时间、两种 ACK latency、重复 Command 的 Engine 调用数、两次重启恢复时间和日志 SHA-256。

- [ ] **Step 6: 最终验证并提交**

```bash
cd hub-gateway
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest -q
cd ..
python3 tools/validate_contracts.py
git diff --check
git add .github docs/test-results/GATE-1-GATEWAY.md wrist/flow-wrist/docs/ble-test.md
git commit -m "docs: record Gate 1 gateway verification"
```

没有 RK3588 真机证据时，Gate 1 必须保持 FAIL，不能用 Fake test 代替。
