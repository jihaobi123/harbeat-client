# HANDOFF — Mix Quality Sprints (Spotify-parity DSP)

> 给下一位 AI 的工作交接。**第一件事：读完本文再动手。** 所有路径基于 `d:\work\harbeat-client`（Windows 开发机）和 `cat@192.168.43.7:~/cypher`（RK3588 边缘盒）。

---

## 0. 整体目标 & 现状一句话

把 RK3588 的混音/转场质量推到「Spotify 级别」。已完成 3 个 Sprint 的代码（在 PC 仓库已 commit + push），**但尚未部署到 RK3588**。RK 当前用 17:48 前的旧代码也能正常播放（已用 `POST /play` 验证 song 101 出声）。

---

## 1. 仓库 / 分支 / 部署拓扑

| 角色 | 仓库 | 路径 | 分支 |
|------|------|------|------|
| PC 主仓（开发） | `jihaobi123/harbeat-client` | `d:\work\harbeat-client` | **`feature/harbeat-full-project`** |
| RK 边缘盒仓 | `Trail-0511/cypher-rk3588` | `cat@192.168.43.7:~/cypher` | `main` |

**重点**：两个仓库**独立**。`harbeat-client/cypher-integration/rk3588-edge/` 子树是 RK 代码的「权威副本」。RK 那边 `~/cypher` 是另一个 git 仓，**部署靠 scp 覆盖**（不是 git pull）。RK 的 `~/cypher` 里有大量未提交修改 + .bak 文件，**不要去 git pull**，只用 scp 直接覆盖单个 .py 文件。

最新 commit（PC 仓 `feature/harbeat-full-project`）：

```
21d135f  feat(mix-quality): Sprint 3-A - per-deck 3-band DJ EQ
7a684f4  feat(mix-quality): Sprint 2 - biquad style FX
fa6db3c  feat(mix-quality): Sprint 1 - LUFS gain + lookahead limiter
```

---

## 2. 已完成工作（代码层面，已 push）

### Sprint 1 — Loudness + Limiter（commit `fa6db3c`）

文件：`cypher-integration/rk3588-edge/audio-engine/engine.py`

- **歌曲级 LUFS-style 增益归一化**：加载 stems 时计算近似 LUFS（K-weighted RMS），target = -14 LUFS，存到 `Deck.gain` 作为静态预增益。
- **块级 lookahead limiter**：threshold = 0.95，instant attack，200 ms release，64-sample ramp 平滑。位置：`_callback` 最后一步，summing 之后。
- 无 scipy 依赖（用户硬性要求），全部 numpy。

### Sprint 2 — Biquad style FX（commit `7a684f4`）

新文件：`cypher-integration/rk3588-edge/audio-engine/dsp.py`

- **`class Biquad`**（DF-II Transposed，RBJ cookbook）：
  - `__slots__`: `_b0/_b1/_b2/_a1/_a2`，状态 `_z1L/_z2L/_z1R/_z2R`，`_bypass`
  - `set_lpf / set_hpf / set_lowshelf / set_peak / set_highshelf / set_bypass / reset`
  - `process(x: np.ndarray) -> np.ndarray`：per-sample Python 循环（局部变量缓存系数/状态），输入 shape `(frames, 2)` float32
- 性能：x86 1.16 ms / 2048×2 块；估算 RK3588 A76 ≈ 3 ms / 块（callback 预算 46 ms）
- 修改 `engine.py`：`bass_swap / filter / echo_out` 三种风格的 envelope 已切换为真实 biquad（之前是 EMA 假滤波）

### Sprint 3-A — Per-deck 3-band DJ EQ（commit `21d135f`）

修改 4 个文件：

#### `cypher-integration/rk3588-edge/audio-engine/engine.py`
`class Deck`：
```python
__slots__ = (
    "audio", "pos", "song_id", "stems", "gain",
    "eq_low_db", "eq_mid_db", "eq_hi_db",
    "_eq_lo", "_eq_mid", "_eq_hi",
)
# 80 Hz low-shelf (Q=0.707) / 1 kHz peak (Q=0.9) / 8 kHz high-shelf (Q=0.707)
# clip ±12 dB；|dB|<0.05 自动 bypass（零开销）
def set_eq(self, low_db, mid_db, hi_db, sr=44100.0) -> tuple: ...
def apply_eq(self, chunk): ...  # 三段链式
```
`clear()` 重置 EQ + biquad 状态。

`_callback` 信号链路（**顺序很重要**）：
```
read (stem-gain) → deck.apply_eq → style FX (filter/echo) → sum A+B → stem_fx → loops/oneshots → limiter
```
匹配硬件 DJ：EQ 先于 channel filter / fader。

公共 API：`engine.set_deck_eq(deck_id, low_db, mid_db, hi_db)`，`deck_id ∈ {a, b, active, inactive}`，返回 `{ok, deck, low_db, mid_db, hi_db}`。位置：~L696，紧挨 `def trigger` 之前。

#### `cypher-integration/rk3588-edge/audio-engine/socket_server.py`
新增 cmd 分支（位于 `"trigger"` 和 `"load_plan"` 之间）：
```python
if cmd == "set_deck_eq":
    result = engine.set_deck_eq(
        str(msg.get("deck", "active")),
        float(msg.get("low_db", 0.0)),
        float(msg.get("mid_db", 0.0)),
        float(msg.get("hi_db", 0.0)),
    )
    return {"ok": bool(result.get("ok", True)), **result}
```
协议：4-byte big-endian length + JSON over Unix socket `/tmp/cypher-audio.sock`。

#### `cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py`
```python
class DeckEqRequest(BaseModel):
    deck: Literal["a", "b", "active", "inactive"] = "active"
    low_db: float = Field(default=0.0, ge=-12.0, le=12.0)
    mid_db: float = Field(default=0.0, ge=-12.0, le=12.0)
    hi_db:  float = Field(default=0.0, ge=-12.0, le=12.0)
```

#### `cypher-integration/rk3588-edge/edge-agent/main.py`
- import 加 `DeckEqRequest`（L15-25 那个 multi-line 块）
- 在 `/stem_solo` 后新增：
```python
@app.post("/eq", dependencies=[Depends(_optional_auth)])
async def deck_eq(req: DeckEqRequest) -> dict[str, Any]:
    result = await _forward("set_deck_eq", deck=req.deck,
                            low_db=req.low_db, mid_db=req.mid_db, hi_db=req.hi_db)
    return {"ok": True, "result": result}
```

---

## 3. 关键运行参数（务必记住）

| 项 | 值 |
|----|----|
| SAMPLE_RATE | 44100 |
| BLOCK_SIZE | 2048 (≈ 46.4 ms / callback) |
| 输出 | sounddevice OutputStream → PulseAudio device `pulse` → ES8388 (card 2) |
| RK 上 audio-engine | `~/cypher/audio-engine/main.py`，systemd `cypher-audio-engine` |
| RK 上 edge-agent | `~/cypher/edge-agent/main.py`，systemd `cypher-edge-agent`，监听 `:9000` |
| RK 上 sync-worker | systemd `cypher-sync-worker`，监听 `:9100`（当前 inactive，stems 已手工 prefetch） |
| Unix socket | `/tmp/cypher-audio.sock`（edge-agent ↔ audio-engine） |
| Cache 根 | `~/cypher/cache/<song_id>/{original,bass,drums,vocals,other}.wav` + .sha256 |
| 已缓存 song_id | 12, 16, 66, 68, 70, 72, 91, 92, 94, 96, 98, 99, 100, 101, 102, 103 |
| limiter | threshold=0.95, attack=0 块, release=200 ms, ramp=64 samples |
| LUFS target | -14 (近似 K-weighted RMS) |
| 用户硬性约束 | **禁 scipy**，DSP 必须 numpy 手写 |

---

## 4. 当前 RK 可用性（2026-05-23 验证）

```
systemctl is-active:
  cypher-audio-engine  active
  cypher-edge-agent    active
  cypher-sync-worker   inactive  (不影响：cache 已齐)
  cypher-input-daemon  active

POST http://192.168.43.7:9000/play  body={"song_id":101,"start_at_sec":0}
→ {"ok":true,"result":{"song_id":101,"position_sec":0.0,"duration_sec":25.5...}}
GET /state 2s 后 → playing:true, position_sec:1.07, next:102

→ 旧代码能播。Sprint 1/2/3-A 未部署，所以听到的是旧 DSP。
```

历史日志可见大量 `ALSA underflow`（17:44 / 17:45 / 17:47 时段），重启后暂未复发。**部署后要重点听 underflow 是否回归**——biquad+EQ 加重了 callback 负载。

---

## 5. 待办（按优先级）

### 🟥 Task A：部署 Sprint 1+2+3-A 到 RK3588（**下次首要任务**）

**部署方式**：scp 覆盖（不要 git pull RK 仓）。需要传 5 个文件：

| PC 源 | RK 目标 |
|-------|---------|
| `cypher-integration/rk3588-edge/audio-engine/dsp.py` | `~/cypher/audio-engine/dsp.py`（**新文件**） |
| `cypher-integration/rk3588-edge/audio-engine/engine.py` | `~/cypher/audio-engine/engine.py` |
| `cypher-integration/rk3588-edge/audio-engine/socket_server.py` | `~/cypher/audio-engine/socket_server.py` |
| `cypher-integration/rk3588-edge/edge-agent/main.py` | `~/cypher/edge-agent/main.py` |
| `cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py` | `~/cypher/edge-agent/edge_agent/models.py` |

**推荐命令（PowerShell）**：
```powershell
cd D:\work\harbeat-client\cypher-integration\rk3588-edge

# 先备份 + 上传
ssh cat@192.168.43.7 "cp ~/cypher/audio-engine/engine.py ~/cypher/audio-engine/engine.py.bak.$(date +%s) ; cp ~/cypher/audio-engine/socket_server.py ~/cypher/audio-engine/socket_server.py.bak.$(date +%s) ; cp ~/cypher/edge-agent/main.py ~/cypher/edge-agent/main.py.bak.$(date +%s) ; cp ~/cypher/edge-agent/edge_agent/models.py ~/cypher/edge-agent/edge_agent/models.py.bak.$(date +%s)"

scp audio-engine/dsp.py            cat@192.168.43.7:~/cypher/audio-engine/dsp.py
scp audio-engine/engine.py         cat@192.168.43.7:~/cypher/audio-engine/engine.py
scp audio-engine/socket_server.py  cat@192.168.43.7:~/cypher/audio-engine/socket_server.py
scp edge-agent/main.py             cat@192.168.43.7:~/cypher/edge-agent/main.py
scp edge-agent/edge_agent/models.py cat@192.168.43.7:~/cypher/edge-agent/edge_agent/models.py

# 重启服务（约 5-10 s 断流）
ssh cat@192.168.43.7 "sudo systemctl restart cypher-audio-engine cypher-edge-agent && sleep 2 && systemctl is-active cypher-audio-engine cypher-edge-agent"

# 触发播放验证
curl.exe -s -X POST http://192.168.43.7:9000/play -H "Content-Type: application/json" -d '{\"song_id\":101,\"start_at_sec\":0}'

# 测试新 /eq 端点（低频 +6 dB）
curl.exe -s -X POST http://192.168.43.7:9000/eq -H "Content-Type: application/json" -d '{\"deck\":\"active\",\"low_db\":6,\"mid_db\":0,\"hi_db\":0}'

# 1 分钟后查 underflow
ssh cat@192.168.43.7 "journalctl -u cypher-audio-engine -n 100 --no-pager | grep -i underflow | tail -20"
```

**回滚**：如出现严重 underflow，`ssh` 上去把 `.bak.<ts>` 文件 mv 回来再 restart。

### 🟧 Task B：实地听感测试（部署后）

按以下顺序试听：
1. 单曲 song 101 平直 EQ — 验证 limiter / LUFS 正常，无削波无爆音
2. EQ 推单一 band 到 +12 / -12 — 验证三段不串扰
3. `POST /xfade {"target_song_id":102,"style":"smooth","duration_sec":4}` — 平滑 crossfade
4. 各 style 切换：`bass_swap / filter / echo_out` — 验证 Sprint 2 biquad
5. 关注 journalctl underflow 计数；可接受阈值：< 2 次 / 分钟

### 🟨 Task C：Sprint 4 — Beatmatching（未启动）

目标：转场前对齐 BPM ±6 %。计划：

1. **Jetson 侧**（`jihaobi123/harbeat-client` 的 backend，路径 `app/modules/...`）：
   - 用 `librosa.beat.beat_track` 离线对每首 cache song 算 beatgrid（beats array + tempo）
   - 写进 mix_plan manifest 字段：`{"song_id": 101, "tempo": 124.5, "beats": [0.48, 0.96, ...]}`
2. **RK 侧**：
   - 收到 transition 前 ~10 s，根据双 deck tempo 比算出拉伸率 `r = tempo_B / tempo_A`
   - 用 `rubberband` CLI **离线**预渲染 B deck 的 stems（输出到 `~/cypher/cache/<id>/<stem>.rb.wav`）—— 不要在 callback 里做实时拉伸
   - prefetch 流程加一道"如果 |r-1|>0.005 则预渲染"逻辑
   - rubberband CLI 已在 RK 上：`which rubberband` 应可用，若无：`sudo apt install rubberband-cli`
3. 用 phase align：crossfade 起点对齐到 A 的下一拍 + B 的下一拍

### 🟦 Task D：Sprint 5 — Flutter UI 暴露 EQ 旋钮

`cypher-integration/flutter-app/`：
- 每个 deck 3 个旋钮（low / mid / hi），范围 ±12 dB，居中 detent
- 调用 `POST http://<rk-ip>:9000/eq`，节流 100 ms / 次
- 状态推送：暂未做 GET（引擎端 set_deck_eq 返回了 clipped 值，UI 信任 POST 响应即可）
- 注意 Flutter 构建：见 终端历史，需 `JAVA_HOME=D:\android-sdk\jdk-17-final` 和 `D:\flutter_install\flutter\bin` 在 PATH；上次 `flutter build apk --debug` exit 1，原因未深查

### 🟪 Task E：Sprint 3-B 等冷门优化（低优先）

- `_apply_stem_fx` 里 key=9 的 LPF 还是老 EMA（`y = y + 0.15*(x-y)`），可换成 dsp.Biquad 统一
- 当前 LUFS 估计是 RMS-based 近似，未来若需精确可加 ITU-R BS.1770 K-weighting 前置滤波

---

## 6. 用户偏好（**不要违背**）

- **禁 scipy / librosa runtime**（RK 上）—— DSP 必须 numpy 手写
- 用户信任 AI 选技术细节，他主要说"继续 / 一步到位"。**不要列 N 个方案让他选**，自己选最优的做。
- 中文回复，简短。代码注释中英文都行，PR/commit msg 英文。
- Commit 用 `git commit -F <临时文件>`（PowerShell 处理 `-m` 多段不可靠）

---

## 7. 常用查验命令速查

```powershell
# RK 全量诊断（脚本在 PC 仓 _rk_diag.sh）
ssh cat@192.168.43.7 "bash /tmp/_rk.sh 2>&1"

# 实时日志跟随
ssh cat@192.168.43.7 "journalctl -u cypher-audio-engine -f"

# 当前播放状态
curl.exe -s http://192.168.43.7:9000/state

# 列 cache 歌曲
ssh cat@192.168.43.7 "ls ~/cypher/cache/ | sort -n"

# PC 仓 push
git push origin feature/harbeat-full-project
```

---

## 8. 给下一位 AI 的开工建议

1. **先读本文件 + 跑诊断**确认 RK 还活着
2. **第一步就是 Task A 部署**（5 个 scp + 1 个 restart + 1 个 curl 验证）
3. 若 Task A 成功 → Task B 听感
4. 若 Task B 出现 underflow > 阈值 → 回滚（用 .bak），分析 callback 占用，**优化目标是缩短 biquad 内循环**（首选 numpy vectorize SOS 数学公式，不上 numba/cython）
5. 听感 OK 后再开 Sprint 4 / 5

**绝对不要做**：
- 不要去 git pull RK 的 `~/cypher`（会跟未提交修改冲突）
- 不要把 scipy / librosa 加进 RK 的 requirements
- 不要在 callback 里做实时 rubberband / 实时 STFT
- 不要 force push、不要碰 main 分支
