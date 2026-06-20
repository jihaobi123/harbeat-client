# HarBeat 本地 Spotify 风格混音真实调用方案

更新日期: 2026-06-11

## 结论

当前 DJ Control 的自动接歌正在执行本�?Spotify 风格混音方案，实际运行层级为 `eq_band_mix`。它不接�?Spotify API，也不依�?stems；RK 只使�?`original` 音频文件解码后的 PCM，在播放引擎里做�?deck 音量、三�?EQ、滤波和切点对齐�?
实时证据:

- 手机 UI 当前自动衔接提示包含 `tier:eq_band_mix / style:eq_band_mix`�?- RK `edge-agent /health` 正常，`audio_ready=true`�?- RK `sync-worker /status` 显示候选池 original-only 同步完成: `total=12, downloaded=12, completed=12, errors=[]`�?- RK audio-engine 日志显示连续 `crossfade start ...`，且目标歌曲从预取缓存加载�?
## 端到端调用链

1. Flutter DJ Control 生成/排定歌曲序列�?2. App 在开始播放前预拉主队列、能量备选池、风格备选池需要的 `original` 文件�?3. App 为相邻歌曲提前请�?Jetson:

```text
POST /api/dj/transitions/plan
transition_mode = eq_band_mix
eq_mix_user_mode = auto
mix_preset = auto/fade/rise/blend/cut/overlap
apply_phrase_alignment = true
target_lufs = -14.0
```

4. Jetson 生成 `eq_band_mix` transition plan�?5. 自动接歌或手动能�?风格切歌触发时，App �?RK:

```text
POST http://192.168.43.7:9000/xfade
transition_mode = eq_band_mix
transition_plan = <Jetson plan>
to_song_id = <target song uuid>
fade_sec / to_at_sec / style / fallback_style
```

6. RK edge-agent 收到 `transition_mode=eq_band_mix` 后转发给 audio-engine:

```text
xfade_eq_band_mix
```

7. audio-engine 执行 `manual_eq_band_mix()`，加载目�?deck:

```python
deck.load(target_song_id, safe_to_at_sec, load_stems=False)
```

这一步明确不加载 stems，只加载原曲音频�?
## Jetson 规划逻辑

入口: `app/modules/dj_control/router.py`

当请�?`transition_mode == "eq_band_mix"` 时，调用:

```python
eq_transition_strategy.plan_eq_band_mix_transition(...)
```

核心策略文件:

- `app/modules/dj_control/eq_transition_strategy.py`
- `app/modules/dj_control/eq_transition_presets.py`
- `app/modules/dj_control/band_analysis.py`
- `app/modules/dj_control/transition.py`

自动策略选择条件:

- 双方人声密度�? `vocal_safe`
- BPM 差大于约 8，或 Camelot 距离较远: `filter_sweep`
- 下一首能量高，或能量上升明显: `hard_bass_swap` �?`soft_bass_swap`
- 双方低频都重: `soft_bass_swap`
- 默认: `smooth_blend`

这些策略会生�?

- `deck_a.fader`
- `deck_b.fader`
- `deck_a.eq.low/mid/high`
- `deck_b.eq.low/mid/high`
- 可�?`filter`
- `fade_sec`
- `from_at_sec`
- `to_at_sec`
- `fallback_style`

## 本地 Spotify 风格增强

`mix_preset` 会通过 `app/modules/dj_control/transition.py` 附加本地混音效果元数据和曲线:

- `auto`: 自动选择
- `fade`: 标准淡化
- `rise`: 上升能量
- `blend`: 混合
- `cut`: 硬切
- `overlap`: 重叠

附加字段包括:

- `mix_effects`
- `decision`
- `volume_curves`
- `eq_curves`
- `filter_curves`
- `mix_preset`

注意: 目前 RK 真正执行的主路径�?`transition_plan.deck_a/deck_b` �?EQ/fader/filter 方案；这�?Spotify 风格字段主要用于计划增强、UI 展示和兼容扩展�?
## RK 执行逻辑

入口: `cypher-integration/rk3588-edge/edge-agent/main.py`

判断:

```python
if req.transition_mode == "eq_band_mix" and req.transition_plan:
    _forward("xfade_eq_band_mix", ...)
else:
    _forward("xfade", ...)
```

audio-engine 入口:

```text
cypher-integration/rk3588-edge/audio-engine/socket_server.py
cmd == "xfade_eq_band_mix"
```

真实执行:

```text
cypher-integration/rk3588-edge/audio-engine/engine.py
manual_eq_band_mix()
```

成功时返�?

```json
{
  "style": "eq_band_mix",
  "playback_tier": "eq_band_mix",
  "degraded": false
}
```

edge-agent 再包装为:

```json
{
  "requested_tier": "eq_band_mix",
  "actual_tier": "eq_band_mix",
  "actual_style": "eq_band_mix",
  "degraded": false
}
```

## 文件拉取策略

DJ Control 当前已改�?original-only:

- 主队�? 只拉 `files.original`
- 能量备选池: 只拉 `files.original`
- 风格备选池: 只拉 `files.original`
- 缓存修复: 只拉 `files.original`

不会提交:

- `files.stems.vocals`
- `files.stems.drums`
- `files.stems.bass`
- `files.stems.other`

如果 manifest �?original �?MP3，则�?MP3；如�?manifest �?original �?WAV，则�?WAV�?
## 回退条件

会回退到普�?xfade 的情�?

- Jetson 规划失败，App 使用本地 fallback plan�?- App 传给 RK �?plan 不是 `transition_mode=eq_band_mix`�?- RK `xfade_eq_band_mix` 转发失败�?- audio-engine 加载目标 original 失败�?- engine 当前没有 active deck、暂停或停止时，会先恢复播放目标曲�?
回退后应看到:

- `actual_tier` 不是 `eq_band_mix`，或
- `degraded=true`，或
- `degrade_reason` 非空�?
## 当前后台监督状�?
截至本次检�?

- `cypher-edge-agent`: system service active
- `cypher-audio-engine`: system service active
- `cypher-sync-worker`: API 可用，`/status` 正常返回 100% 完成
- 手机端当前自动衔�?UI 已显�?`tier:eq_band_mix / style:eq_band_mix`

需要注意的部署风险:

- RK 上曾出现 user-level sync-worker �?system-level sync-worker 同时尝试监听 9100 的情况。当�?9100 API 可用，但 system service 状态可能因为端口被 user service 占用而短暂显�?auto-restart。建议后续统一只保留一�?sync-worker 托管入口�?
## 评估重点

建议重点听测:

- `smooth_blend`: 是否比普�?xfade 更平滑�?- `soft_bass_swap`: 两首歌低频交接是否不浑�?- `hard_bass_swap`: 高能切换是否够利落�?- `filter_sweep`: BPM/调性跨度大时是否能遮蔽突兀感�?- `vocal_safe`: 双人声段是否避免明显打架�?
当前最影响体验的不�?stems，而是启动前候选池预缓存数量。候选池越大，第一首前等待越久；但之后能量/风格切歌更快�?
## 具体实现细节

这一节按真实执行顺序描述，不按理想设计描述�?
### 1. 音频文件进入 RK

DJ Control 只把 `files.original` 交给 sync-worker。sync-worker 会把文件放到:

```text
/home/cat/cypher/cache/{song_id}/original.mp3
�?/home/cat/cypher/cache/{song_id}/original.wav
```

audio-engine �?`check_song_cache()` 会查找这些扩�?

```text
wav, mp3, flac, m4a, ogg, opus, aac
```

播放�?`Deck.load()` 解码�?48kHz stereo float32 PCM。对�?`eq_band_mix`，调用是:

```python
deck.load(target_song_id, safe_to_at_sec, load_stems=False)
```

所以它不会加载:

```text
vocals.wav
drums.wav
bass.wav
other.wav
```

### 2. 转场点怎么�?
App 会提前为每一对相邻歌曲请�?transition plan。请求参数里�?

```text
cursor_sec = prev.duration - 45
transition_mode = eq_band_mix
apply_phrase_alignment = true
```

Jetson 先用�?`mixer_rules.build_transition_spec()` 给一个基础出点/入点，再�?`phrase_alignment.find_transition_point()` 修正:

1. �?A 歌的 downbeats 里找离目标出点最近的小节�?2. 在前�?8 小节范围内搜索�?3. 每个候选点打分:
   - downbeat 基础�?10
   - section boundary �?50
   - 8-bar boundary �?30
   - 4-bar boundary �?20
   - phrase intensity 极高或极低加 10
4. B 歌入点优�?
   - hot cue 里的 intro/main
   - vocal-free window
   - 第一�?downbeat
   - 否则 0 �?
App 轮询 RK 播放位置，每 600ms 检查一次。满足以下条件之一就触发自动接�?

```text
positionSec >= plan.from_at_sec
�?remainingSec <= 1.0
�?RK 已停止但 positionSec > 5.0
```

这意味着如果 `from_at_sec` 选得不好，实际会很早或很晚切；如果轮询错过点，会在接近结尾时强制切�?
### 3. 策略怎么�?
策略入口�?

```python
plan_eq_band_mix_transition(prev, next, eq_mix_user_mode="auto")
```

先构造两�?`mix_profile_v1`:

- BPM
- duration
- beat_grid
- downbeat_grid
- phrase_grid
- low/mid/high 粗略能量
- vocal/drum/bass/high_hat 粗略密度
- mix_in/mix_out/hard_cut 候选点

这些特征主要来自已有字段，不是重新做一次精细频谱分析。如果库里没有可�?beat/phrase/vocal 数据，就会用 BPM 网格和默认值合成�?
自动策略选择规则:

```text
prev_vocal > 0.55 �?next_vocal > 0.45
=> vocal_safe

BPM �?> 8 �?Camelot 距离 >= 4
=> filter_sweep

next_energy > 0.68 或能量差 > 0.12
=> hard_bass_swap �?soft_bass_swap

prev_low + next_low > 1.25
=> soft_bass_swap

否则
=> smooth_blend
```

目前共有 5 个真正被 RK `eq_band_mix` 执行的策�?

```text
smooth_blend
soft_bass_swap
hard_bass_swap
vocal_safe
filter_sweep
```

### 4. 每个策略的曲�?
策略�?`eq_transition_presets.py` 里定义。每个策略有:

```text
duration_beats
deck_a.fader
deck_a.eq.low/mid/high
deck_a.filter
deck_b.fader
deck_b.eq.low/mid/high
deck_b.filter
rk_style
```

曲线单位�?beat，不是秒。例�?

```text
deck_a.fader: [[0, 1.0], [24, 0.70], [32, 0.0]]
deck_a.eq.low: [[0, 0], [20, 0], [28, -9], [32, -18]]
```

audio-engine 在转场中把进度换算成 beat:

```python
progress = fade_frames_done / fade_total_frames
beat = progress * duration_beats
```

然后 `eval_deck(deck_plan, beat)` �?fader/EQ/filter 曲线做线性插值，得到当前 callback 的参数�?
### 5. 每个 audio callback 怎么�?
audio callback 里，如果当前 style �?`eq_band_mix`，走这条分支:

```python
a = _read_eq_band_deck(active_deck, deck_a_plan, beat, frames, "a")
b = _read_eq_band_deck(inactive_deck, deck_b_plan, beat, frames, "b")
main = (a + b) * headroom
```

`_read_eq_band_deck()` 做的�?

1. 从当�?deck 读一小块 PCM�?2. 根据当前 beat 计算:
   - low_db
   - mid_db
   - hi_db
   - fader
   - filter cutoff
3. 设置 deck �?3-band EQ:
   - low shelf: 80Hz
   - mid peak: 1kHz
   - high shelf: 8kHz
4. �?PCM �?EQ�?5. 如果�?filter，再�?lowpass/highpass�?6. �?fader�?
最�?A+B 相加，再乘安�?headroom，默�?

```text
headroom_db = -6
```

### 6. EQ �?filter 的真实限�?
这是影响听感的重点�?
`Deck.set_eq()` 对三个频段统一限幅:

```python
low_db = clamp(low_db, -12, +12)
mid_db = clamp(mid_db, -12, +12)
hi_db  = clamp(hi_db,  -12, +12)
```

�?preset 里写了很多更深的衰减:

```text
-18 dB
-24 dB
-30 dB
-60 dB
```

这些在真实执行时都会被压成最�?`-12 dB`。结果是:

- 低频并不会真�?kill 掉�?- hard_bass_swap 实际不够硬�?- 两首歌低频同时存在的时间会比计划更长�?- 人声/中频也可能没有被 duck 到足够低�?
这很可能是你觉得糊、不丝滑、接得不干净的主要原因之一�?
filter 的真实实现是 biquad:

- lowpass/highpass
- Q = 0.707
- cutoff 每个 callback 按曲线更�?
filter_sweep �?preset:

```text
deck_a lowpass: 18000Hz -> 350Hz
deck_b highpass: 900Hz -> 30Hz
```

这条理论上能遮掩跨度，但如果入点/出点不准，还是会听起来像突然变暗、突然冒出来�?
### 7. Spotify preset 现在到底生效了什�?
UI 上的:

```text
自动 / 标准淡化 / 上升能量 / 混合 / 硬切 / 重叠
```

会作�?`mix_preset` 发给 Jetson。Jetson 会调�?

```python
enrich_transition_plan_with_mix_effects(...)
```

它会生成:

- `decision`
- `volume_curves`
- `eq_curves`
- `filter_curves`
- `mix_effects`
- `mix_preset`

但是当前 RK `eq_band_mix` 主执行路径只读取:

```text
transition_plan.deck_a
transition_plan.deck_b
transition_plan.safety
transition_plan.target
transition_plan.fade_sec
```

也就是说，`volume_curves / eq_curves / filter_curves` 这些 Spotify preset 曲线目前更多是计划元数据�?UI/兼容字段�?*不是 RK 当前混音主循环的真实控制�?*�?
真实控制源仍然是 `eq_transition_presets.py` 里的 5 �?`eq_band_mix` preset�?
### 8. UI 里“stem:”提示的真实含义

当前自动衔接文案里可能出�?

```text
stem:bass互换+鼓桥�?人声后入
```

这来自旧�?plan 展示字段 `stem_curves`，用于提示“意图上�?stem 编排”。但�?`eq_band_mix` 路径�?

```python
load_stems=False
```

所以它不是实际 stem 分轨混音。实际仍然是原曲 PCM 上的 EQ/fader/filter�?
这个 UI 文案容易误导，建议改�?

```text
低频换底 / 鼓点保留 / 人声后入
```

不要再写 `stem:`�?
### 9. 当前为什么可能听起来不好

我认为当前听感差可能来自这些�?

1. EQ kill 深度不够
   preset 设计想用 -24/-60 dB，但 engine 只允许到 -12 dB，导致低频和中频清不干净�?
2. 策略选择太粗
   `low/mid/high/vocal` 多数是从 metadata 推断，不是真正按接歌窗口分析瞬时频谱。可能把不适合叠的两段硬叠�?
3. phrase alignment 只看 A 歌附�?downbeat
   B 歌入点选择比较简单，可能跳到 48s 这类很突兀的位置，也可能错过更自然的鼓点入口�?
4. Spotify preset 曲线没有真正驱动 RK 主循�?
   UI 选“上�?混合/硬切”会影响 plan 元数据和 style 字段，但 eq_band_mix 真正执行仍主要取 5 个内置策略�?
5. 转场时长有时过长
   32 beats �?90 BPM �?21.3 秒，�?120 BPM �?16 秒。长时间叠两�?full mix，若 EQ kill 不够，必然糊�?
6. beatmatch 只是预渲�?tempo hint
   当前不是完整 DJ 软件那种相位锁定、瞬时网格跟踪。日志里�?beatmatch render，但听感仍依赖入点和曲线�?
7. limiter/headroom 只是保底
   `headroom=-6dB` 能防炸，但不能解决两首歌频谱冲突。听起来可能变小、闷、糊�?
## 建议的改进方�?
如果要让效果更接近你想要�?Spotify 风格，我建议优先改这几件:

1. �?`eq_band_mix` �?EQ 限幅�?band 分开:
   - low 最低允�?-36 dB 或提�?isolator kill
   - mid/high 最低允�?-24 dB
   - 继续保留 limiter 防爆

2. 缩短默认转场:
   - 大多�?hiphop 接歌先用 8-12 �?   - 只在 smooth_blend �?BPM/key 很近时允�?16 秒以�?
3. �?Spotify preset 真正驱动 RK:
   - RK 直接读取 `volume_curves / eq_curves / filter_curves`
   - 而不是只读取 `deck_a/deck_b`

4. 改掉 UI �?`stem:` 提示:
   - 避免误判真实执行路径

5. 加一�?A/B debug 输出:
   - 每次转场记录策略、from_at、to_at、fade_sec、实�?EQ min/max、filter cutoff range、degraded
   - 这样你听到不好时能马上对应到算法原因

6. 先做 3 个固定高质量模板:
   - 短切: 2-4 秒，downbeat 对齐，低�?kill
   - 低频换底: 8 秒，A low kill �?-36 dB，B low �?-36 �?0
   - 扫频遮蔽: 8-12 秒，A lowpass 下沉，B highpass 打开

这比现在“自动策略很多但每个都不够狠”更容易听出稳定效果�?
