# 团队开发文档 · RK3588 现场盒（负责人 B）

> 自包含实现规范。基础与协议见 [cypher-feature-flows.md](cypher-feature-flows.md)。

## 0. 你的目标
在 RK3588 上实现"现场盒"：接 App 命令、读 MixPlan、本地播放 + 实时切歌 + 实时 9 键加花、上报事件。**所有现场实时逻辑都在你这里**。

## 0.1 工作环境
- 硬件：RK3588 板子 + USB 声卡（输出到调音台）+ 9 键 USB HID 盒
- OS：Debian/Ubuntu ARM64
- Python：3.10+，venv `~/venvs/edge/`
- 工作目录：`~/cypher/`，结构：
  ```
  ~/cypher/
    edge-agent/        FastAPI :9000 + WS :9001
    audio-engine/      Python sounddevice 播放器（MVP）
    input-daemon/      evdev 监听 HID
    sync-worker/       下载 stems
    samples/           9 键预置 sample（01_ha.wav ~ 06_hat_loop.wav）
    cache/<song_id>/   原文件 + 4 stem（同步下来）
    plans/             当前 MixPlan json
    logs/
  ```
- systemd unit：4 个进程各一份，`Restart=always`

## 0.2 任务总览

| # | 任务 | 进程 | 完工标志 |
|---|---|---|---|
| T1 | edge-agent FastAPI 接口集 | edge-agent | App 能命令 RK |
| T2 | sync-worker 拉清单 + 下载 + 校验 | sync-worker | manifest 下完 ready 可播 |
| T3 | audio-engine 双 deck + crossfade | audio-engine | MixPlan 自动切歌无停顿 |
| T4 | 9 键加花引擎 | audio-engine | sample/loop/stemfx 三类都生效 |
| T5 | input-daemon + SessionEvent 上报 | input-daemon, edge-agent | 硬件键 → 声响 < 30ms；事件批量回 Jetson |

> **MVP 策略**：T3/T4 第一版用 Python `sounddevice` + numpy。性能不够再换 Rust `cpal`。Rust 是 stretch goal，不阻塞集成。

---

## 进程间通信

```
[App] ──HTTP/WS──▶ edge-agent ──Unix socket──▶ audio-engine
[硬件键] ─USB HID─▶ input-daemon ─Unix socket─▶ audio-engine
[Jetson] ◀──httpx── sync-worker (拉 manifest, 下文件)
                    edge-agent (推 SessionEvent)
```

Unix socket 路径：`/tmp/cypher-audio.sock`。协议：长度前缀（4 字节 big-endian uint32）+ JSON。每条消息独立。

---

## T1 edge-agent

文件：`~/cypher/edge-agent/main.py`，FastAPI + uvicorn :9000，独立 WS server :9001。

### REST 接口（全部见协议 P4）

```python
POST /play         {"song_id": int, "start_at_sec": float=0}
POST /pause        {}
POST /resume       {}
POST /next         {}
POST /seek         {"sec": float}
POST /trigger      {"key": int}     # 0~9
POST /load_plan    {"mix_plan": ..., "manifest": ...}
GET  /health       -> {"ok": true, "audio_ready": bool, "current_song_id": ...}
GET  /state        -> RKPlaybackState (协议 P5)
```

每个 endpoint 把命令通过 unix socket 转发给 audio-engine，等返回 ack。

`/load_plan` 逻辑：
1. 写入 `~/cypher/plans/current.json`
2. 调 sync-worker `POST http://127.0.0.1:9100/sync` 开始下载（异步）
3. 立即返回 `{"plan_id": ..., "sync_started": true}`

### WebSocket /ws

- 客户端连上后，服务端每 200ms 发一帧 `RKPlaybackState`
- 每 5s 发一帧 `DeviceInfo`
- 当 audio-engine 产生事件（transition 开始、加花触发）立即推

实现：从 audio-engine 订阅一个 unix socket subscribe topic，把消息转给所有 WS 客户端。

### Auth
内网够用。可加 header `X-Edge-Token` 与 env 对比。

### systemd
```ini
# /etc/systemd/system/edge-agent.service
[Service]
ExecStart=/home/<user>/venvs/edge/bin/uvicorn main:app --host 0.0.0.0 --port 9000
Restart=always
WorkingDirectory=/home/<user>/cypher/edge-agent
```

### 验证
```bash
curl -X POST http://<rk-ip>:9000/play -d '{"song_id":101}' -H "Content-Type: application/json"
# 音箱响
wscat -c ws://<rk-ip>:9001/ws
# 看到 playback_state 帧
```

---

## T2 sync-worker

文件：`~/cypher/sync-worker/main.py`，FastAPI :9100（内网内监听）。

### 接口
```
POST /sync       # body: {manifest: AssetManifest}
GET  /status     # {total, downloaded, current_file, percent, errors:[]}
```

### 下载逻辑
```python
async def sync(manifest):
    for track in manifest.tracks:
        for kind, finfo in flatten_files(track):  # original + 4 stems
            local = f"~/cypher/cache/{track.song_id}/{kind}.wav"
            if exists(local) and sha256(local) == finfo.sha256:
                continue  # 已存且匹配
            await download(finfo.url, local, expected_size=finfo.size)
            actual = sha256(local)
            if actual != finfo.sha256:
                os.remove(local); raise SyncError(...)
        mark_track_ready(track.song_id)
```

并发：用 `asyncio.Semaphore(4)` 限制同时下载 4 个文件，避免打爆带宽。

URL：manifest 里给的是相对路径（`/api/stream/...`），用环境变量 `JETSON_BASE_URL` 拼前缀。

### 拒绝未 ready
audio-engine `play(song_id)` 时检查 `~/cypher/cache/<song_id>/` 是否有 `original.wav` + 4 个 stem，缺则返回 409 错（edge-agent 透传给 App）。

### 验证
```bash
curl -X POST http://localhost:9100/sync -d @manifest.json -H "Content-Type: application/json"
curl http://localhost:9100/status
ls ~/cypher/cache/101/   # original.wav vocals.wav drums.wav bass.wav other.wav
```

---

## T3 audio-engine（核心）

文件：`~/cypher/audio-engine/main.py`，**Python + sounddevice MVP**。

### 数据流

```
                  ┌─── deck_a (sf.SoundFile + np.ndarray pos)
                  │     │
sd.OutputStream ──┼─ mix ─ master_gain ─ optional LPF biquad ─▶ 声卡
  callback(out)   │     │
                  ├─── deck_b
                  ├─── stem_overlay[vocals,drums,bass,other] 当前歌
                  ├─── one_shot_queue [(np.ndarray, pos)]    # 1/2/3 触发
                  └─── loop_layer[4],[5],[6]                  # 4/5/6 toggle
```

### 关键类

```python
class AudioEngine:
    SR = 44100  # 所有 wav 统一 44100 Hz 16-bit stereo（sync-worker 下完转一次）
    BLOCK = 512
    
    def __init__(self):
        self.deck_a = Deck()
        self.deck_b = Deck()
        self.active = 'a'
        self.one_shots = []  # list[(np.ndarray, int_pos)]
        self.loops = {}      # {key:int -> (np.ndarray, pos)}
        self.stem_fx = None  # None | ('mute_vocals', t_end) | ('solo_drums', t_end) | ('lpf', t_end, cutoff_state)
        self.mix_plan = None
        self.master_gain = 1.0
        
    def load_song(self, song_id):
        """加载到 inactive deck，并预读 4 stem 到内存（每个 mmap 即可）"""
        deck = self.deck_b if self.active=='a' else self.deck_a
        deck.load(f"~/cypher/cache/{song_id}/original.wav")
        deck.stems = {n: sf.read(f"~/cypher/cache/{song_id}/{n}.wav")[0]
                      for n in ['vocals','drums','bass','other']}
    
    def callback(self, outdata, frames, time_info, status):
        # 1. 从 active deck 取主轨片段
        main = self.active_deck.read(frames)        # (frames, 2) float32
        # 2. 如在 transition 期内，从 inactive deck 也取并按曲线 fade
        if self.in_transition:
            other = self.inactive_deck.read(frames)
            a_gain, b_gain = self.fade_curve(self.fade_progress)
            main = main * a_gain + other * b_gain
            self.fade_progress += frames/self.SR
            if self.fade_progress >= self.fade_total:
                self._swap_decks()
        # 3. stem_fx 改写 main（用 stems 重组）
        if self.stem_fx:
            main = self._apply_stem_fx(main, frames)
        # 4. 叠 loop（4/5/6）
        for buf, pos in self.loops.values():
            main += self._read_loop(buf, pos, frames)
        # 5. 叠 one-shot（1/2/3）
        main += self._mix_one_shots(frames)
        # 6. LPF（key 9 期间）
        if self.stem_fx and self.stem_fx[0]=='lpf':
            main = self._lpf(main)
        # 7. master_gain
        outdata[:] = (main * self.master_gain).astype(np.float32)
        # 8. 推送 progress（限频 200ms 一次）
        self._maybe_emit_state()
```

### Crossfade 曲线

```python
def fade_curve(self, t, total=8.0):  # equal-power
    x = t/total
    return math.cos(x*math.pi/2), math.sin(x*math.pi/2)
```

到点判定：每 callback 检查 `active_deck.pos_sec >= transition.from_at_sec` → 触发 `start_transition(next_song)`。提前 3s 调 `load_song(next)` 预读。

### 9 键命令处理

```python
def trigger(self, key:int):
    if key == 0:
        self.toggle_pause()
    elif key in (1,2,3):
        self.one_shots.append((self.samples[f'0{key}'], 0))
    elif key in (4,5,6):
        if key in self.loops: del self.loops[key]
        else: self.loops[key] = (self.samples[f'0{key}'], 0)
    elif key == 7:
        self.stem_fx = ('mute_vocals', self.now()+2.0)
    elif key == 8:
        self.stem_fx = ('solo_drums', self.now()+2.0)
    elif key == 9:
        self.stem_fx = ('lpf', self.now()+2.0)
```

### `_apply_stem_fx`
```python
def _apply_stem_fx(self, main, frames):
    if self.now() > self.stem_fx[1]:
        self.stem_fx = None; return main
    kind = self.stem_fx[0]
    deck = self.active_deck
    pos = deck.pos
    if kind == 'mute_vocals':
        return main - deck.stems['vocals'][pos:pos+frames]
    if kind == 'solo_drums':
        return deck.stems['drums'][pos:pos+frames]
    if kind == 'lpf':
        return main  # 在 step 6 单独处理
    return main
```

LPF：scipy biquad，cutoff 从 8kHz 扫到 200Hz（持续 2s），用一阶滤波 + 状态保留。

### samples 预加载
启动时 `~/cypher/samples/0[1-6]_*.wav` 全部 `sf.read()` 到 `self.samples` dict，44.1k stereo float32。

### 性能预算
RK3588 Cortex-A76：500-frame callback < 11ms。每 callback 工作量：1 mix（FMA 1024 op）+ 偶尔 stem 读切片。Python + numpy 实测 RK3588 大约 2~3ms 占用，留够 buffer。如 xrun 频繁，先把 BLOCK 改 1024 看是否解决，仍不行再切 Rust。

### systemd
独立服务 `audio-engine.service`，`Restart=always`，CPU affinity 绑 A76 大核：
```ini
CPUAffinity=4 5 6 7
Nice=-10
IOSchedulingClass=realtime
```

### 验证
```bash
# 装好两首歌 cache 后
echo '{"cmd":"load_plan","plan":{"tracks":[{"song_id":101,...},{"song_id":102,...}], ...}}' | nc -U /tmp/cypher-audio.sock
echo '{"cmd":"play","song_id":101}' | nc -U /tmp/cypher-audio.sock
# 听音箱 + 等过渡点 + 手动 trigger 各 key 听效果
```

---

## T4 9 键加花（已并入 T3 audio-engine 实现）

需要单独准备的产物：
- `~/cypher/samples/01_ha.wav` ~ `06_hat_loop.wav`，44100/stereo/PCM16
- 校准音量：所有 sample peak ≤ -6dB，避免削顶

记忆要点：1-3 是 fire-and-forget，4-6 是 toggle，7-9 是 2s 限时操作。

---

## T5 input-daemon + SessionEvent

### input-daemon

文件：`~/cypher/input-daemon/main.py`，evdev 监听 USB HID keyboard。

```python
from evdev import InputDevice, list_devices, ecodes

dev = find_device_by_name("9-key Pad")  # 启动时打印所有设备让运维确认
for ev in dev.read_loop():
    if ev.type != ecodes.EV_KEY or ev.value != 1: continue
    key = KEY_MAP[ev.code]  # KEY_1..KEY_9, KEY_0
    send_to_audio_socket({"cmd":"trigger","key":key,"ts":time.time()})
    send_to_agent({"type":"key_event","ts":...,"key":key,"source":"hid"})
```

设备消失时 5s 重连。

### SessionEvent 上报

edge-agent 维护 buffer：
```python
event_buffer = []  # 内存 deque
def append(evt): event_buffer.append(evt); if len(event_buffer) > 200 or stale(): flush()
def flush():
    payload = {"rk_id": RK_ID, "events": event_buffer[:]}
    try:
        httpx.post(f"{JETSON}/api/sessions/{SID}/events", json=payload, timeout=5)
        event_buffer.clear()
    except: pass  # 留 buffer，下次重试
```

需要持久化（断电不丢）：buffer 满 50 条或 10s 时写一份到 `~/cypher/logs/events-buffer.jsonl`，启动时优先 flush 这个文件。

### 验证
```bash
# 按硬件键 1
# 1. 音箱立刻有 "ha!"（< 30ms）
# 2. WS 客户端收到 key_event 帧
# 3. 5min 内 Jetson 上 select count(*) from session_events 看到记录
```

---

## 完工自检
- [ ] `curl /play` 能放歌
- [ ] MixPlan 到 transition 时刻自动 fade 8s 切下一首，无停顿
- [ ] 硬件键 1~9 全部生效，延迟 < 30ms
- [ ] 拔掉键盒再插回，5s 内恢复
- [ ] audio-engine kill 后 systemd 5s 内拉起，状态从 plans/current.json 恢复
- [ ] App WS 持续收到 200ms 一帧的 playback_state
- [ ] Jetson 一侧能查到本场所有 SessionEvent
- [ ] sync-worker 对一份 manifest（5 首 1GB）能 10min 内完成下载并 sha256 全部匹配
