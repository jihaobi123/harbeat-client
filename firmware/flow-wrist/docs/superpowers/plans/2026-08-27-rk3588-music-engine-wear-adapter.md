# RK3588 Music Engine Wear Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有 `/tmp/cypher-audio.sock` 客户端的前提下，为 RK3588 audio-engine 增加 Flow Wear IPC v1，把能量/风格意图确定性地解析为真实候选曲目，并向 Gateway 连续反馈 accepted、progress、completed 或 rejected。

**Architecture:** 现有 `AudioSocketServer` 保留。新增第二个 `FlowWearSocketServer`，监听 `/run/flow-wear/engine.sock`，与旧服务共享同一个 `AudioEngineMVP` 实例。候选选择器读取原子更新的本地曲库清单，不访问网络；切歌工作在线程中执行，asyncio 只负责 IPC 和状态发布。

**Tech Stack:** Python 3.12、asyncio Unix socket、JSON Lines、jsonschema、pytest、现有 AudioEngineMVP

**Repositories:** `contracts/` 与 Gateway 修改发生在 `harbeat-wear`；audio-engine 修改发生在当前 `harbeat-client/cypher-integration/rk3588-edge`。两个仓库必须分别提交，Gate 证据同时记录两个 SHA。

---

### Task 1: 冻结曲库清单合同

**Files:**
- Create: `contracts/engine-catalog-v1.schema.json`
- Create: `contracts/examples/engine-catalog-v1.json`
- Modify: `tools/validate_contracts.py`
- Test: `tests/contracts/test_engine_catalog.py`

- [ ] **Step 1: 写失败测试**

测试以下约束：`version == 1`；`generated_at` 为 UTC RFC3339；每首歌含 `song_id`、`energy` 1–5、四选一 `style`、`bpm` 1–300、`audio_ready`；`song_id` 唯一；额外字段拒绝。

- [ ] **Step 2: 写 schema 与有效/无效样例**

正式路径固定为：

```text
/var/lib/flow-wear/engine/catalog.json
```

写入方必须先写同目录临时文件、`fsync`，再 `os.replace`；读取方每个新 Command 检查 mtime，解析失败时继续使用最后一份有效清单并记录 `catalog_invalid`。

示例条目固定为：

```json
{"song_id":"track-001","energy":3,"style":"hiphop","bpm":96,"audio_ready":true}
```

- [ ] **Step 3: 运行合同测试并提交 wear 仓库**

```bash
python3 tools/validate_contracts.py
pytest tests/contracts/test_engine_catalog.py -q
git add contracts tools/validate_contracts.py tests/contracts
git commit -m "docs: freeze engine catalog contract"
```

### Task 2: Engine 侧模型与候选选择器

**Files:**
- Create: `cypher-integration/rk3588-edge/audio-engine/flow_wear_models.py`
- Create: `cypher-integration/rk3588-edge/audio-engine/flow_wear_selector.py`
- Test: `cypher-integration/rk3588-edge/tests/test_flow_wear_selector.py`

- [ ] **Step 1: 先写选择规则测试**

必须覆盖：

1. `set_energy` 只选择目标能量，优先当前风格；
2. `set_style` 只选择目标风格，优先当前能量；
3. 排除当前曲和最近 5 首；
4. 排除 `audio_ready=false` 或缓存中不存在 `original.*` 的曲目；
5. 同分时按 `song_id` 字符串升序，保证重启后结果一致；
6. 无候选返回 `no_candidate`，不触发 engine；
7. 未知当前曲或当前曲元数据缺失时返回 `engine_error`。

- [ ] **Step 2: 实现冻结评分**

```text
set_energy: 目标能量必须相等；当前风格 +20；每 1 BPM 差 -1
set_style: 目标风格必须相等；当前能量相等 +20；每差 1 档 -5；每 1 BPM 差 -1
```

最近 5 首直接排除，不用负分。V0.1 不随机、不联网、不改变 BPM 或调性。选择结果包含目标曲完整 `MusicState`。

- [ ] **Step 3: 验证**

```bash
cd cypher-integration/rk3588-edge
pytest tests/test_flow_wear_selector.py -q
```

### Task 3: 新增独立 IPC v1 Server

**Files:**
- Create: `cypher-integration/rk3588-edge/audio-engine/flow_wear_server.py`
- Modify: `cypher-integration/rk3588-edge/audio-engine/config.py`
- Test: `cypher-integration/rk3588-edge/tests/test_flow_wear_server.py`

- [ ] **Step 1: 写协议失败测试**

用临时 Unix socket 验证：连接后必须先 `hello`；版本不等于 1 返回 `rejected/unsupported`；单行超过 16 KiB 或无效 JSON 返回 `rejected/protocol_error` 并断开；相同 `request_id` 返回缓存结果而不再执行；未知字段拒绝。

- [ ] **Step 2: 实现 Server**

每行一个 UTF-8 JSON 对象，以 `\n` 结束。socket 权限 `0660`，owner 为现有 audio-engine 用户 `cat`，group 为 `flow-wear`。`hello`、`get_state` 是单次请求；`set_direction` 连接保持到 `completed/rejected` 后由服务端关闭。

`set_direction` 的时序：

```text
validate -> select candidate -> validate cache -> accepted(<200 ms)
-> worker calls manual_transition -> progress(preparing)
-> engine.in_transition -> progress(transitioning)
-> current_song_id == target and !in_transition -> completed
```

`accepted` 后若工作线程异常，发送 `rejected/engine_error`；不得把它伪装成 completed。每 250 ms 最多发送一次 progress；30 秒仍未完成则 `rejected/engine_error`。

- [ ] **Step 3: 隔离阻塞音频加载**

`manual_transition()` 必须通过 `asyncio.to_thread` 调用，不能阻塞 IPC event loop。收到请求后先执行 `engine.prefetch([target])`；候选缓存文件已存在即可 accepted，预解码完成不是 accepted 的前置条件。

- [ ] **Step 4: 验证**

```bash
pytest tests/test_flow_wear_server.py -q
```

### Task 4: 在同一进程启动两套 Socket Server

**Files:**
- Modify: `cypher-integration/rk3588-edge/audio-engine/main.py`
- Test: `cypher-integration/rk3588-edge/tests/test_main_servers.py`

- [ ] **Step 1: 写失败测试**

注入 fake legacy server 和 fake wear server，断言二者得到同一 `AudioEngineMVP` 对象；任一 server 启动失败时 main 以非零退出，避免出现“进程存活但手环链路不存在”。

- [ ] **Step 2: 编排生命周期**

保留 `/tmp/cypher-audio.sock` 的 framing、权限和行为完全不变。新增 server 在独立 asyncio thread 中运行；SIGTERM 先停止接收 Wear Command，再停止旧 socket 和音频流。

- [ ] **Step 3: 回归旧测试并提交 engine 仓库**

```bash
pytest tests/test_flow_wear_models.py tests/test_flow_wear_selector.py tests/test_flow_wear_server.py tests/test_main_servers.py -q
pytest tests -q
git add cypher-integration/rk3588-edge/audio-engine cypher-integration/rk3588-edge/tests
git commit -m "feat: bridge wrist intent to music engine"
```

### Task 5: 补全 Gateway 的长响应流

**Files:**
- Modify: `hub-gateway/src/flow_wear_gateway/engine/ipc.py`
- Modify: `hub-gateway/src/flow_wear_gateway/controller.py`
- Modify: `hub-gateway/src/flow_wear_gateway/service.py`
- Test: `hub-gateway/tests/test_engine_ipc.py`
- Test: `hub-gateway/tests/test_controller.py`

- [ ] **Step 1: 写失败测试**

Fake Engine 在一个连接依次写 `accepted`、`progress/preparing`、`progress/transitioning`、`completed`。断言 Gateway：400 ms 内返回 accepted；后续更新同一 `ack_id`；completed 后把 target 提升为 current、`locked=false`；断线时写 `transport_error` 并解锁。

- [ ] **Step 2: 实现 submit API**

`submit(message, on_event)` 为每个 Command 建立一个流连接，等待首条 accepted/rejected 不超过 400 ms；accepted 后由后台 task 继续读到终态。Gateway 停止时取消 task 并关闭 writer。每种终态都必须写持久化 Snapshot，再经 GATT Notify 发给 Wrist。

- [ ] **Step 3: 实现 Engine 状态对账**

Gateway 启动时先 `hello`，再 `get_state`。若本地持久化存在未终结 Command：查询 Engine；目标已经成为 current 则合成为 completed，否则标为 `transport_error`，不自动重放。重连成功后发送最新 Snapshot。

- [ ] **Step 4: 全套 Gateway 回归并提交**

```bash
cd hub-gateway
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest -q
git add hub-gateway
git commit -m "feat: stream engine transition progress"
```

### Task 6: systemd、权限和 RK3588 真机 Gate 2

**Files:**
- Create: `hub-gateway/packaging/systemd/flow-wear-tmpfiles.conf`
- Modify: `hub-gateway/packaging/systemd/flow-wear-gateway.service`
- Create: `docs/runbooks/RK3588-ENGINE-INTEGRATION.md`
- Create: `docs/test-results/GATE-2-ENGINE.md`

- [ ] **Step 1: 安装运行账户和目录**

```bash
sudo groupadd --system flow-wear || true
sudo usermod -aG flow-wear cat
sudo install -d -o cat -g flow-wear -m 0750 /var/lib/flow-wear/engine
sudo install -d -o flow-wear-gateway -g flow-wear -m 0750 /var/log/flow-wear
sudo systemd-tmpfiles --create /etc/tmpfiles.d/flow-wear.conf
```

同时给 `cypher-audio-engine.service` 增加 `SupplementaryGroups=flow-wear`；修改组成员后必须重启该 service。Gateway 用户保持 `flow-wear-gateway`，二者只通过共享组访问 socket，不共享登录账户。

- [ ] **Step 2: 准备 8 首最小验收曲库**

四种风格每种至少 2 首；五档能量中至少覆盖 1、3、5；每条均有可读缓存。用原子替换方式安装 `catalog.json`，运行 schema 校验。

- [ ] **Step 3: 启动并确认双 socket**

```bash
sudo systemctl restart cypher-audio-engine flow-wear-gateway
sudo systemctl is-active cypher-audio-engine flow-wear-gateway
ss -xl | grep -E 'cypher-audio|flow-wear/engine'
```

- [ ] **Step 4: 真实切换验收**

从 Wrist 完成一次 `energy 3 -> 5` 和一次 `style hiphop -> funk`。保存 Gateway/Engine 结构化日志，确认：accepted ≤500 ms、10–20 秒内 completed、每个 `command_id` 只出现一次 engine 执行、旧 App 仍可通过 legacy socket 查询 state。

- [ ] **Step 5: 写 Gate 2 报告**

报告记录 wear SHA、client SHA、两次 command/request ID、accepted 延迟、完成耗时、旧 socket 回归结果。失败时不进入 Wrist hardening。
