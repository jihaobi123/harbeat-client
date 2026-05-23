# HANDOFF — Mix Quality Next (RK deployed, presets + beatmatch)

> 给下一位 AI：**先读完本文再动手**。当前上下文很长，用户可能会换模型；本文是接手用的事实源。

---

## 0. 当前一句话状态

RK3588 已经能实机播放并执行多种 DJ / Spotify Mix 风格转场。已完成：

- Sprint 1/2/3-A 部署：LUFS gain、limiter、Biquad FX、per-deck 3-band EQ。
- Task B 自动化试听：EQ 极限、`smooth / bass_swap / filter / echo_out / power / cut / slam` 都触发成功。
- Sprint 4 最小闭环：Jetson manifest 带 `tempo/beats`；RK 解析 beat metadata；RK 用 `rubberband` 离线预渲染 beatmatched target original。
- 新增 Spotify Mix 风格 preset 映射：`fade / rise / blend / wave / melt`。

还没有做到“Spotify 全量产品级 Automix”。目前是稳定的 RK 播放/转场基础 + 12 种可触发 preset + beatmatch 预渲染雏形。

---

## 1. 仓库与工作区

### PC 主仓

- GitHub：`jihaobi123/harbeat-client`
- 原 workspace：`/Users/jihaobi/Documents/New project`
- 原 workspace 当前有很多用户/历史 mobile 脏改动，**不要乱改、不要 reset**。
- 我为了隔离，创建了独立 worktree：

```bash
/tmp/harbeat-mix-quality
```

- 当前分支：

```bash
codex/mix-quality-next
```

- 基线来自：

```bash
origin/feature/harbeat-full-project
```

### 本轮已提交的 commits

请先看：

```text
57054d1 feat(mix-quality): add Spotify-style transition presets
83150e7 feat(mix-quality): stabilize RK transitions and add beatmatch preload
```

`83150e7` 包含：

- 避免 live 转场期间持 audio lock 做大文件 I/O。
- 手动/计划转场目标只读 `original.wav`，避免实时加载 4 条 stems 造成 xrun。
- Sprint 4 beatmatch 最小闭环。
- Manifest 输出 `tempo` / `beats`。

`57054d1` 包含：

- 新增 `fade/rise/blend/wave/melt` preset。
- `slam` 改为不依赖 stems。
- 新增本文档。

---

## 2. RK3588 连接信息

### 当前网络

RK 当前地址不是旧文档里的 `192.168.43.7`，本轮已确认新地址：

```text
192.168.5.17
```

### 服务

```text
cypher-audio-engine active
cypher-edge-agent   active
edge-agent HTTP     http://192.168.5.17:9000
audio socket        /tmp/cypher-audio.sock
```

### SSH

```bash
ssh cat@192.168.5.17
```

密码由用户在对话里临时提供过。**不要把密码写进 repo 或 commit**；下一位 AI 如需 SSH，直接向用户索取。

建议使用临时 known_hosts 和 control socket：

```bash
rm -f /tmp/harbeat_rk_known_hosts /tmp/harbeat_rk_mux
ssh-keyscan -H 192.168.5.17 > /tmp/harbeat_rk_known_hosts
ssh -M -S /tmp/harbeat_rk_mux -N -o ControlPersist=10m \
  -o UserKnownHostsFile=/tmp/harbeat_rk_known_hosts \
  -o StrictHostKeyChecking=yes cat@192.168.5.17
```

之后命令加：

```bash
ssh -S /tmp/harbeat_rk_mux -o BatchMode=yes \
  -o UserKnownHostsFile=/tmp/harbeat_rk_known_hosts \
  -o StrictHostKeyChecking=yes cat@192.168.5.17 "..."
```

---

## 3. 已部署到 RK 的核心文件

RK 目标路径：

```text
~/cypher/audio-engine/engine.py
~/cypher/audio-engine/dsp.py
~/cypher/audio-engine/mix_plan.py
~/cypher/audio-engine/socket_server.py
~/cypher/edge-agent/main.py
~/cypher/edge-agent/edge_agent/models.py
```

重要：最初 handoff 只写了 5 个文件，但实际 Sprint 1 还改了：

```text
cypher-integration/rk3588-edge/audio-engine/mix_plan.py
```

如果漏传，会导致：

```text
AttributeError: 'NormalizedPlan' object has no attribute 'track_meta'
```

我已经补传并验证。

---

## 4. 本轮实机验证记录

### 基础播放 / EQ

已验证：

```bash
POST /play {"song_id":101,"start_at_sec":0}
POST /eq {"deck":"active","low_db":6,"mid_db":0,"hi_db":0}
POST /eq low/mid/hi 分别 +12 / -12
```

结果：接口返回 `ok:true`，播放状态正常。

### 已试听/触发的旧风格

已触发：

```text
smooth
bass_swap
filter
echo_out
power
cut
slam
```

试听串曾使用：

```text
101 -> 102 smooth
102 -> 103 bass_swap
103 -> 100 filter
100 -> 99  echo_out
99  -> 98  power
98  -> 96  cut
96  -> 94  slam
```

日志观察：

- 大多数转场无持续 underflow。
- `filter` 落点曾有 1 次 underflow。
- `power/cut/slam` 那组三段日志里没有 underflow/error。

### 新增 Spotify Mix preset 试听

新增并部署：

```text
fade
rise
blend
wave
melt
```

试听串：

```text
101 -> 102 fade
102 -> 103 rise
103 -> 100 blend
100 -> 99  wave
99  -> 98  melt
```

API 全部返回 `ok:true`。日志里 `blend` 附近出现过 1 次 underflow：

```text
ALSA underrun occurred
WARNING engine sounddevice status: output underflow
```

没有持续爆发。

---

## 5. 当前支持的 12 种转场风格

`XfadeRequest.style` 当前允许：

```text
smooth, power, bass_swap, echo_out, filter, cut, slam,
fade, rise, blend, wave, melt
```

### 1. smooth

等功率 crossfade。最稳，默认。

### 2. power

B 轨更快、更有冲击地进入。实现为 A `cos^1.2`，B `sin^0.7`。

### 3. bass_swap

低频交接感。现在不再实时依赖 stems，而是全轨包络 + biquad：

- A：HPF 20 -> 220 Hz
- B：LPF 160 -> 16000 Hz

### 4. filter

扫频转场：

- A：LPF 18 kHz -> 200 Hz
- B：LPF 200 Hz -> 18 kHz

### 5. echo_out

A 轨进入 0.25s feedback echo，B 轨正常进入。

### 6. cut

转场进度 5% 处硬切。

### 7. slam

已改成不依赖 stems：

- 前 68%：A 保留但轻微下压，B 静音
- 68%-78%：短暂静默
- 后 22%：B 全开

### 8. fade

Spotify Mix 风格 preset 映射：线性 fade。

### 9. blend

Spotify Mix 风格 preset 映射：等功率融合，类似 smooth 但作为显式 preset 暴露给 App/plan。

### 10. rise

Spotify Mix 风格 preset 映射：上扬进入。

- A 越来越薄：HPF 30 -> 1130 Hz
- B 从电话感打开成全频：HPF 1200 -> 30 Hz

### 11. wave

Spotify Mix 风格 preset 映射：轻微能量波动。实现是 4 个周期的轻微 gain pulse，不额外加滤波。

### 12. melt

Spotify Mix 风格 preset 映射：融化式出场。

- A：echo + LPF 18 kHz -> 450 Hz
- B：LPF 650 Hz -> 18 kHz

---

## 6. Sprint 4 Beatmatching 当前实现

### Jetson / backend 侧

文件：

```text
app/modules/playlists/service.py
```

`build_asset_manifest()` 现在每首 track 输出：

```json
{
  "song_id": 101,
  "duration_sec": 25.5,
  "bpm": 124.0,
  "tempo": 124.0,
  "beats": [0.48, 0.96]
}
```

注意：backend 原本已经有 `lib.bpm` 和 `lib.beat_points`，本轮只是把它们带进 P3 manifest。

### RK mix_plan 解析

文件：

```text
cypher-integration/rk3588-edge/audio-engine/mix_plan.py
```

`Transition` 新增：

```python
tempo_ratio: float | None
from_beat_interval_sec: float | None
to_beat_interval_sec: float | None
phase_anchor_sec: float | None
```

`track_meta` 也吸收：

```text
tempo / bpm
beats / beat_points
replay_gain_db
loudness_lufs
```

### RK audio-engine 预渲染

文件：

```text
cypher-integration/rk3588-edge/audio-engine/engine.py
```

常量：

```python
PRELOAD_BEFORE_SEC = 10.0
BEATMATCH_MAX_SHIFT = 0.06
BEATMATCH_MIN_SHIFT = 0.005
```

逻辑：

- Scheduled transition 到 `from_at_sec - 10s` 时，后台线程预加载目标曲。
- 如果 transition 带 beat interval 或 tempo_ratio：
  - 计算 `ratio = tempo_B / tempo_A`。
  - 若 `0.5% <= |ratio - 1| <= 6%`，用 `rubberband` 离线渲染 target original。
  - 输出类似：

```text
~/cypher/cache/101/original.rb.1p03327.wav
```

- 转场时 Deck 加载该 `original.rb.*.wav`。
- 没有 metadata、没有 rubberband、ratio 超阈值、渲染失败：自动回退 `original.wav`。

RK 已安装：

```bash
/usr/bin/rubberband
```

安装命令曾执行：

```bash
sudo apt-get update
sudo apt-get install -y rubberband-cli
```

### Beatmatch 实机 smoke test

曾下发临时 plan：

```text
102 -> 101
tempo_ratio=1.0333
from_beat_interval_sec=0.5
to_beat_interval_sec=0.4839
```

日志：

```text
beatmatch render ok: song_id=101 ratio=1.0333 in 1786ms
crossfade start 102 -> 101 (4.0s)
```

验证生成：

```text
/home/cat/cypher/cache/101/original.rb.1p03327.wav
```

60 秒后无新增 underflow。

---

## 7. 关键修复：转场超时 / underflow

最初部署 Sprint 2 后，`bass_swap / filter / echo_out` 会 `/xfade` timeout，并持续 underflow。

根因：

- `manual_transition()` 在持有 engine lock 时同步加载目标歌曲。
- 目标 102 的 4 条 stems 每条加载约 0.8s，总 I/O 约 3.7s。
- audio callback 需要同一把 lock，于是卡住并 xrun。

修复：

- `play()`：先在临时 Deck 外部加载，再短锁替换 active deck。
- `manual_transition()`：先在临时 Deck 加载目标，再短锁安装 inactive deck。
- scheduled preload：后台线程做，不在 callback 里做大 I/O。
- 手动/计划转场目标默认只加载 `original.wav`，不加载 stems。
- `bass_swap/filter/echo_out` 改成全轨 + biquad/echo，不再依赖 stems。

结果：

- 三种风格 `/xfade` 不再 timeout。
- 大多数窗口 underflow 为 0；偶尔边界 1 次，仍需后续优化。

---

## 8. 重要限制与未完成工作

### 还不是 Spotify 完整 Automix

没有完成：

- Spotify 级自动选转场点。
- 完整 playlist mixing UI。
- waveform / beatgrid 可视化编辑。
- 自动选择 preset。
- 所有 preset 的真实 Spotify 官方内部参数（Spotify 未公开）。
- 多段 phase align 的精细拍点对齐。

### Beatmatching 仍是最小闭环

未完成：

- 只预渲染 `original.wav`，没有预渲染 stems。
- `phase_anchor_sec` 当前只是解析保存，尚未用于精确落拍。
- 手动 `/xfade` 没有传 tempo metadata，所以一般不会 beatmatch；beatmatch 主要服务 scheduled plan。
- ratio 超过 ±6% 会跳过，不做极端拉伸。
- 没有清理旧 `original.rb.*.wav` 的 LRU。

### Task D 未完成：Flutter EQ 旋钮

路径大概率是：

```text
cypher-integration/flutter-app/
```

需求：

- 每个 deck 3 个旋钮：low / mid / hi。
- 范围 ±12 dB，居中 detent。
- 调用：

```http
POST http://<rk-ip>:9000/eq
```

- 节流 100ms。

注意：原 workspace 的 `mobile/` 有大量脏改，不要碰错目录。若要做 Flutter，优先在 `/tmp/harbeat-mix-quality/cypher-integration/flutter-app/` 里做。

### Task E 未完成：key=9 LPF

文件：

```text
cypher-integration/rk3588-edge/audio-engine/engine.py
```

`_apply_stem_fx()` 里 key=9 还是老 EMA：

```python
self._lpf_state = self._lpf_state + 0.15 * (main[i] - self._lpf_state)
```

可改成 `Biquad` 统一，但低优先。

### audio-engine shutdown 慢

每次：

```bash
sudo systemctl restart cypher-audio-engine
```

旧进程常常要等 systemd `TimeoutStopUSec=90s` 才退出。服务最终能 active，但后续应优化 `shutdown()` / OutputStream stop 逻辑。

### BrokenPipeError 日志

看到过：

```text
BrokenPipeError: [Errno 32] Broken pipe
```

通常来自 client 侧超时/断开，服务未死。不是首要问题，但 socket_server 可补 try/except 忽略 BrokenPipe，减少日志噪音。

### 本机测试环境

这台 Mac 没有 `pytest`：

```text
python3: No module named pytest
```

已跑过：

```bash
python3 -m py_compile ...
```

---

## 9. 常用验证命令

### 状态

```bash
curl -s http://192.168.5.17:9000/health
curl -s http://192.168.5.17:9000/state
```

### 播放

```bash
curl -s -X POST http://192.168.5.17:9000/play \
  -H "Content-Type: application/json" \
  -d '{"song_id":101,"start_at_sec":0}'
```

### 手动转场

```bash
curl -s -X POST http://192.168.5.17:9000/xfade \
  -H "Content-Type: application/json" \
  -d '{"to_song_id":102,"style":"rise","fade_sec":6,"to_at_sec":0}'
```

可测 style：

```text
smooth power bass_swap echo_out filter cut slam fade rise blend wave melt
```

### EQ

```bash
curl -s -X POST http://192.168.5.17:9000/eq \
  -H "Content-Type: application/json" \
  -d '{"deck":"active","low_db":6,"mid_db":0,"hi_db":0}'
```

### 日志

```bash
ssh cat@192.168.5.17 \
  "journalctl -u cypher-audio-engine --since '3 min ago' --no-pager | grep -iE 'crossfade|beatmatch|underflow|underrun|error|exception|traceback' | tail -120"
```

### 重启

```bash
ssh cat@192.168.5.17 \
  "sudo systemctl restart cypher-audio-engine cypher-edge-agent && sleep 2 && systemctl is-active cypher-audio-engine cypher-edge-agent"
```

需要密码。重启可能等 90s。

---

## 10. 下一步建议

按优先级：

1. 让用户主观听 12 种 preset，标记哪些好听、哪些刺耳。
2. 优化 `blend/filter` 边界偶发 underflow。
3. 给 `socket_server._send_response()` 加 BrokenPipe 容错。
4. 做 Flutter EQ 旋钮（Task D）。
5. 做 key=9 Biquad LPF（Task E）。
6. 改 audio-engine shutdown，避免每次 restart 等 90s。
7. 完善 beatmatch phase align：使用 `phase_anchor_sec` / beat arrays 找 A 下一拍和 B 下一拍。
8. 给 `original.rb.*.wav` 加缓存清理。

---

## 11. 用户偏好

- 中文回复，简短但交接文档可以详细。
- 不要让用户在多方案里选太久，直接选稳妥路径做。
- RK 上 DSP 禁 scipy / librosa runtime；DSP 纯 numpy / Python / rubberband CLI 离线都可以。
- commit message 英文。
- commit 用：

```bash
git commit -F /tmp/some_msg.txt
```

---

## 12. 安全提醒

- 不要 `git reset --hard` 原 workspace。
- 不要 `git pull` RK 的 `~/cypher` 仓，RK 有未提交修改和 `.bak.*` 文件。
- 部署 RK 用 `scp` 覆盖单文件，并先备份。
- 不要把 SSH 密码写进 git。
- 不要在 audio callback 里做实时 rubberband、STFT、磁盘 I/O、大文件解码。
