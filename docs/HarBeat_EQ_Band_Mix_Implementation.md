# HarBeat DJ 频段转场引擎落地执行文档

版本：v1.0
日期：2026-06-07
适用对象：后端 AI Agent、Flutter App 开发、RK3588 播放端开发、测试与部署人员
目标：按本文档完成后，HarBeat 可在现有 DJ Control 中使用 `eq_band_mix` 频段混音转场。
重要边界：第一版只需要 MP3，不需要 stems 文件。

---

## 0. 实施原则

### 0.1 只增强转场，不重写系统

不得重写以下模块：

```text
用户登录
曲库导入
候选池准备
App 启动前同步候选池
RK sync-worker 下载缓存
能量切歌选歌逻辑
风格切歌选歌逻辑
```

只增强：

```text
Jetson 转场计划生成
Flutter DJ Control 混音方式选择
RK audio-engine 转场执行
```

### 0.2 MP3 是唯一音频源

第一版不要生成 stems：

```text
不要生成 vocal.wav
不要生成 drums.wav
不要生成 bass.wav
不要生成 instrumental.wav
不要让 RK 依赖 stems 播放
```

正确流程：

```text
MP3 存储
Jetson 解码 MP3 做分析
生成 mix_profile_v1
RK 解码 MP3 播放
在 PCM 上实时做 EQ / fader / filter
```

### 0.3 任何失败都回退普通 xfade

如果 `eq_band_mix` 在任意阶段失败，必须回退：

```text
ordinary_xfade
```

不能静音，不能让播放卡死。

---

## 1. 最终用户流程

```text
1. 用户进入 DJ Control
2. 用户选择舞种 / 能量 / 目标歌曲
3. App 显示推荐下一首
4. App 显示混音方式：自动、丝滑、强节奏、人声保护、扫频
5. 用户点击确认切歌
6. App 请求 Jetson 生成 transition_plan
7. App 将 transition_plan 发给 RK edge-agent
8. RK audio-engine 执行 eq_band_mix
9. 成功后当前播放切换到目标歌曲
10. 失败时回退普通 xfade 或 play_fallback
```

---

## 2. 新增概念定义

### 2.1 transition_mode

新增：

```text
eq_band_mix
```

含义：

```text
用两路 deck 同时播放 A/B 两首歌，分别控制 Low / Mid / High / fader / filter，完成 DJ 频段转场。
```

### 2.2 eq_strategy

第一版支持：

```text
smooth_blend
soft_bass_swap
hard_bass_swap
vocal_safe
filter_sweep
```

第二版可扩展：

```text
drum_first
loop_bridge
echo_drop
iso_kill_drop
```

### 2.3 用户可选模式

Flutter UI 展示：

```text
auto          自动推荐
smooth        丝滑
rhythm        强节奏
vocal_safe    人声保护
filter        扫频
```

映射关系：

```text
auto       -> Jetson 自动决策
smooth     -> smooth_blend
rhythm     -> soft_bass_swap 或 hard_bass_swap
vocal_safe -> vocal_safe
filter     -> filter_sweep
```

---

## 3. 数据结构设计

### 3.1 mix_profile_v1

每首歌新增分析结果：

```json
{
  "mix_profile_v1": {
    "version": 1,
    "bpm": 96.0,
    "duration_sec": 213.4,
    "beat_grid": [0.52, 1.145, 1.77],
    "downbeat_grid": [0.52, 3.02, 5.52],
    "phrase_grid": [0.52, 10.52, 20.52],
    "band_energy": {
      "low_curve": [[0.0, 0.65], [1.0, 0.71]],
      "mid_curve": [[0.0, 0.52], [1.0, 0.55]],
      "high_curve": [[0.0, 0.38], [1.0, 0.42]]
    },
    "density": {
      "vocal_density_curve": [[0.0, 0.12], [1.0, 0.15]],
      "drum_density_curve": [[0.0, 0.62], [1.0, 0.67]],
      "bass_density_curve": [[0.0, 0.71], [1.0, 0.75]],
      "high_hat_density_curve": [[0.0, 0.48], [1.0, 0.52]]
    },
    "mix_flags": {
      "has_clean_intro": true,
      "has_drum_intro": true,
      "has_vocal_intro": false,
      "has_strong_bass_intro": false,
      "has_usable_outro": true
    },
    "safe_points": {
      "mix_in_points": [0.52, 10.52, 20.52],
      "mix_out_points": [150.52, 160.52, 170.52],
      "bass_swap_points": [10.52, 20.52, 30.52],
      "hard_cut_points": [20.52, 40.52]
    }
  }
}
```

### 3.2 transition_plan

`/api/dj/transitions/plan` 返回：

```json
{
  "transition_mode": "eq_band_mix",
  "strategy": "hard_bass_swap",
  "duration_beats": 32,
  "start": {
    "type": "next_phrase",
    "start_after_beats": 8
  },
  "target": {
    "song_id": "target_song_id",
    "start_cue_sec": 12.80
  },
  "deck_a": {
    "song_id": "current_song_id",
    "fader": [[0, 1.0], [24, 0.75], [32, 0.0]],
    "eq": {
      "low": [[0, 0], [24, 0], [28, -12], [32, -60]],
      "mid": [[0, 0], [16, -3], [28, -12], [32, -60]],
      "high": [[0, 0], [20, -3], [32, -60]]
    },
    "filter": null,
    "fx": null
  },
  "deck_b": {
    "song_id": "target_song_id",
    "fader": [[0, 0.0], [8, 0.35], [24, 0.75], [32, 1.0]],
    "eq": {
      "low": [[0, -60], [24, -60], [28, -9], [32, 0]],
      "mid": [[0, -15], [16, -6], [32, 0]],
      "high": [[0, -9], [8, -3], [16, 0]]
    },
    "filter": null,
    "fx": null
  },
  "safety": {
    "headroom_db": -6,
    "limiter_ceiling_db": -1,
    "smooth_ms": 30,
    "fallback_mode": "ordinary_xfade"
  },
  "reason": [
    "目标舞种偏重鼓点和低频",
    "两首歌 low_energy 都较高，避免低频叠加",
    "目标歌有可用鼓点 intro，适合先进入节奏再换底"
  ]
}
```

---

## 4. 后端 Jetson 修改

### 4.1 新增文件

在：

```text
app/modules/dj_control/
```

新增：

```text
mix_profile.py
band_analysis.py
eq_transition_presets.py
eq_transition_strategy.py
```

### 4.2 修改文件

```text
app/modules/dj_control/schemas.py
app/modules/dj_control/router.py
app/modules/dj_control/transition_strategy.py
app/modules/dj_control/mixer_rules.py
app/modules/library/*
```

---

## 5. 后端实现细节

### 5.1 schemas.py

新增枚举：

```python
class TransitionMode(str, Enum):
    ordinary_xfade = "ordinary_xfade"
    eq_band_mix = "eq_band_mix"
```

新增用户偏好：

```python
class EqMixUserMode(str, Enum):
    auto = "auto"
    smooth = "smooth"
    rhythm = "rhythm"
    vocal_safe = "vocal_safe"
    filter = "filter"
```

新增点曲线结构：

```python
class AutomationPoint(BaseModel):
    beat: float
    value: float

class EqBandCurve(BaseModel):
    low: list[list[float]]
    mid: list[list[float]]
    high: list[list[float]]

class DeckEqAutomation(BaseModel):
    song_id: str
    fader: list[list[float]]
    eq: EqBandCurve
    filter: dict | None = None
    fx: dict | None = None
```

新增计划：

```python
class EqBandMixPlan(BaseModel):
    transition_mode: Literal["eq_band_mix"]
    strategy: str
    duration_beats: int
    start: dict
    target: dict
    deck_a: DeckEqAutomation
    deck_b: DeckEqAutomation
    safety: dict
    reason: list[str]
```

### 5.2 mix_profile.py

职责：

```text
定义 mix_profile_v1 数据结构
从 Song / metadata 中读取 mix_profile
如果缺失则返回 None
```

最小函数：

```python
def get_mix_profile(song) -> dict | None:
    metadata = getattr(song, "metadata", None) or {}
    return metadata.get("mix_profile_v1")


def has_valid_mix_profile(song) -> bool:
    profile = get_mix_profile(song)
    if not profile:
        return False
    required = ["bpm", "beat_grid", "phrase_grid", "band_energy", "density", "mix_flags"]
    return all(k in profile for k in required)
```

### 5.3 band_analysis.py

职责：

```text
从 MP3 解码音频
计算 BPM / beat_grid / phrase_grid
计算 Low / Mid / High 能量曲线
估算 vocal_density / drum_density / bass_density
生成 safe_points
写回 metadata.mix_profile_v1
```

第一版推荐依赖：

```text
librosa
numpy
scipy 可选
ffmpeg 或 soundfile/audioread 用于解码
```

最小分析流程：

```python
def analyze_mix_profile(audio_path: str) -> dict:
    y, sr = load_audio(audio_path)
    bpm, beat_grid = estimate_beats(y, sr)
    downbeat_grid = estimate_downbeats_simple(beat_grid)
    phrase_grid = estimate_phrase_grid(downbeat_grid)
    band_energy = compute_band_energy(y, sr)
    density = estimate_density_curves(y, sr, band_energy)
    mix_flags = estimate_mix_flags(band_energy, density, beat_grid)
    safe_points = estimate_safe_points(beat_grid, phrase_grid, band_energy, density)

    return {
        "version": 1,
        "bpm": bpm,
        "duration_sec": len(y) / sr,
        "beat_grid": beat_grid,
        "downbeat_grid": downbeat_grid,
        "phrase_grid": phrase_grid,
        "band_energy": band_energy,
        "density": density,
        "mix_flags": mix_flags,
        "safe_points": safe_points,
    }
```

Low / Mid / High 第一版频段：

```text
Low: 20-180 Hz
Mid: 180-4000 Hz
High: 4000-20000 Hz
```

估算逻辑：

```text
bass_density = low_energy 的归一化强度
drum_density = onset_strength + low/high transient
high_hat_density = high_energy 中的短时瞬态
vocal_density = mid_energy + 谱平稳性 + 非鼓点区域中频持续性
```

说明：第一版 vocal_density 只是估算，用于“人声避让”，不用于单独控制人声。

### 5.4 eq_transition_presets.py

职责：

```text
存放固定转场模板
输入 duration_beats
输出 A/B 的 fader、eq、filter 曲线
```

#### smooth_blend

```python
def preset_smooth_blend(duration_beats=64):
    return {
        "strategy": "smooth_blend",
        "deck_a": {
            "fader": [[0, 1.0], [duration_beats * 0.75, 0.75], [duration_beats, 0.0]],
            "eq": {
                "low": [[0, 0], [duration_beats * 0.70, 0], [duration_beats, -60]],
                "mid": [[0, 0], [duration_beats * 0.50, -3], [duration_beats, -60]],
                "high": [[0, 0], [duration_beats * 0.70, -3], [duration_beats, -60]],
            },
        },
        "deck_b": {
            "fader": [[0, 0.0], [duration_beats * 0.25, 0.35], [duration_beats, 1.0]],
            "eq": {
                "low": [[0, -60], [duration_beats * 0.70, -60], [duration_beats, 0]],
                "mid": [[0, -15], [duration_beats * 0.50, -6], [duration_beats, 0]],
                "high": [[0, -12], [duration_beats * 0.25, 0], [duration_beats, 0]],
            },
        },
    }
```

#### soft_bass_swap

```text
A Low 慢慢下
B Low 慢慢上
交换发生在后 25% 时间
```

#### hard_bass_swap

```text
B Low 前 75% 保持 -60 dB
最后 25% 快速接管
必须卡在 downbeat / phrase boundary
```

#### vocal_safe

```text
如果当前 A vocal_density 高：
B Mid 前半段不超过 -9 dB
B High 可以轻微进入
B Low 只在后段进入
```

#### filter_sweep

```text
B filter 从窄/薄逐渐打开
A filter 反向关闭
最后完成 EQ 交换
```

### 5.5 eq_transition_strategy.py

职责：

```text
读取 A/B mix_profile
根据用户模式、舞种、低频冲突、人声冲突、目标歌开头判断策略
生成最终 transition_plan
```

核心函数：

```python
def plan_eq_band_mix_transition(
    current_song,
    target_song,
    target_style: str | None,
    user_mode: str = "auto",
    current_position_sec: float | None = None,
) -> dict:
    a = get_mix_profile(current_song)
    b = get_mix_profile(target_song)

    if not a or not b:
        return build_fallback_xfade_plan(current_song, target_song, reason="missing_mix_profile")

    features = compute_pair_features(a, b, current_position_sec)
    strategy = choose_strategy(features, target_style, user_mode)
    duration_beats = choose_duration_beats(strategy, target_style, features)
    preset = build_preset(strategy, duration_beats, features)
    start = choose_start_point(a, current_position_sec, strategy)
    target_cue = choose_target_cue(b, strategy)

    return assemble_plan(current_song, target_song, strategy, preset, start, target_cue, features)
```

配对特征：

```python
def compute_pair_features(a, b, current_position_sec):
    return {
        "bass_conflict": estimate_bass_conflict(a, b, current_position_sec),
        "vocal_conflict": estimate_vocal_conflict(a, b, current_position_sec),
        "drum_intro_quality": estimate_drum_intro_quality(b),
        "arrangement_density": estimate_arrangement_density(a, b, current_position_sec),
    }
```

策略选择：

```python
def choose_strategy(features, target_style, user_mode):
    if user_mode == "smooth":
        return "smooth_blend"
    if user_mode == "vocal_safe":
        return "vocal_safe"
    if user_mode == "filter":
        return "filter_sweep"
    if user_mode == "rhythm":
        if target_style in {"hiphop", "breaking", "krump", "popping"}:
            return "hard_bass_swap"
        return "soft_bass_swap"

    # auto
    if features["vocal_conflict"] >= 0.65:
        return "vocal_safe"
    if features["bass_conflict"] >= 0.65:
        if target_style in {"hiphop", "breaking", "krump", "popping"}:
            return "hard_bass_swap"
        return "soft_bass_swap"
    if features["arrangement_density"] >= 0.75:
        return "filter_sweep"
    return "smooth_blend"
```

### 5.6 router.py

在现有 `/api/dj/transitions/plan` 中新增：

```text
如果 request.transition_mode == "eq_band_mix":
  调用 plan_eq_band_mix_transition(...)
否则走原有 transition plan
```

请求示例：

```json
{
  "current_song_id": "A",
  "target_song_id": "B",
  "transition_mode": "eq_band_mix",
  "eq_mix_user_mode": "auto",
  "target_style": "hiphop",
  "current_position_sec": 123.4
}
```

响应必须包含：

```text
transition_mode
strategy
duration_beats
deck_a
deck_b
safety
reason
fallback_mode
```

---

## 6. Flutter App 修改

### 6.1 修改文件

```text
mobile/lib/src/models.dart
mobile/lib/src/api_client.dart
mobile/lib/src/edge_agent_client.dart
mobile/lib/src/dj_control_page.dart
```

### 6.2 models.dart

新增枚举：

```dart
enum EqMixUserMode {
  auto,
  smooth,
  rhythm,
  vocalSafe,
  filter,
}
```

新增模型：

```dart
class EqBandMixPlan {
  final String transitionMode;
  final String strategy;
  final int durationBeats;
  final Map<String, dynamic> deckA;
  final Map<String, dynamic> deckB;
  final Map<String, dynamic> safety;
  final List<String> reason;
}
```

### 6.3 api_client.dart

新增：

```dart
Future<Map<String, dynamic>> djPlanEqBandMixTransition({
  required String currentSongId,
  required String targetSongId,
  required EqMixUserMode userMode,
  String? targetStyle,
  double? currentPositionSec,
}) async {
  final payload = {
    'current_song_id': currentSongId,
    'target_song_id': targetSongId,
    'transition_mode': 'eq_band_mix',
    'eq_mix_user_mode': userMode.name,
    if (targetStyle != null) 'target_style': targetStyle,
    if (currentPositionSec != null) 'current_position_sec': currentPositionSec,
  };

  final res = await _dio.post('/api/dj/transitions/plan', data: payload);
  return Map<String, dynamic>.from(res.data);
}
```

### 6.4 edge_agent_client.dart

新增：

```dart
Future<void> xfadeWithTransitionPlan(Map<String, dynamic> transitionPlan) async {
  await _dio.post('/xfade', data: {
    'transition_mode': transitionPlan['transition_mode'],
    'transition_plan': transitionPlan,
  });
}
```

如果 RK 不支持 `eq_band_mix`，App 应回退：

```dart
await ordinaryXfade(targetSongId);
```

### 6.5 dj_control_page.dart

UI 新增混音方式选择：

```text
混音方式
[自动推荐] [丝滑] [强节奏] [人声保护] [扫频]
```

状态变量：

```dart
EqMixUserMode _selectedEqMixMode = EqMixUserMode.auto;
```

确认切歌流程修改：

```text
1. 确认目标歌已在 RK 缓存并 playable
2. 调用 Jetson /api/dj/transitions/plan，transition_mode=eq_band_mix
3. 展示 reason，可选
4. 调用 RK /xfade，带 transition_plan
5. 成功后更新当前队列状态
6. 失败时普通 xfade
```

重要：不要改变现有 `_syncMissingLiveCandidatesBeforePlay`、`_ensurePlayableRkCacheIds`、`/cache/validate` 逻辑。

---

## 7. RK3588 修改

### 7.1 修改文件

新增：

```text
cypher-integration/rk3588-edge/audio-engine/eq_filters.py
cypher-integration/rk3588-edge/audio-engine/envelope_runner.py
cypher-integration/rk3588-edge/audio-engine/eq_mixer.py
```

修改：

```text
cypher-integration/rk3588-edge/audio-engine/engine.py
cypher-integration/rk3588-edge/edge-agent/main.py
```

### 7.2 edge-agent/main.py

`/xfade` 接收：

```json
{
  "transition_mode": "eq_band_mix",
  "transition_plan": {...}
}
```

逻辑：

```python
if transition_mode == "eq_band_mix":
    forward_to_audio_engine_eq_mix(transition_plan)
else:
    forward_to_existing_xfade(...)
```

如果 audio-engine 返回不支持或错误：

```text
fallback ordinary xfade
```

### 7.3 audio-engine/eq_filters.py

第一版用三段 EQ：

```text
Low shelf: 120 Hz
Mid peaking: 1000 Hz, Q=0.8
High shelf: 8000 Hz
```

要求：

```text
参数平滑 20-50 ms
EQ gain 限制 -60 dB 到 +3 dB
禁止第一版大幅 boost
```

### 7.4 audio-engine/envelope_runner.py

职责：

```text
把 beat-based 自动化曲线转换成实时参数
```

输入：

```python
points = [[0, -60], [24, -60], [28, -9], [32, 0]]
current_beat = 26.5
```

输出：

```python
gain_db = interpolate(points, current_beat)
```

要求：

```text
线性插值即可
输出再做 smooth_ms 平滑
```

### 7.5 audio-engine/eq_mixer.py

核心结构：

```text
Deck A:
  decode PCM
  fader
  low/mid/high EQ
  optional filter

Deck B:
  decode PCM
  fader
  low/mid/high EQ
  optional filter

Master:
  sum
  headroom -6 dB
  soft limiter ceiling -1 dB
  output
```

执行流程：

```python
def run_eq_band_mix(plan):
    load_current_deck_a(plan.deck_a.song_id)
    load_target_deck_b(plan.deck_b.song_id, plan.target.start_cue_sec)
    wait_until_start(plan.start)

    while transition_not_finished:
        current_beat = compute_transition_beat()

        a_params = envelope_runner.eval_deck(plan.deck_a, current_beat)
        b_params = envelope_runner.eval_deck(plan.deck_b, current_beat)

        a_pcm = deck_a.read_frame()
        b_pcm = deck_b.read_frame()

        a_out = apply_eq_and_fader(a_pcm, a_params)
        b_out = apply_eq_and_fader(b_pcm, b_params)

        master = mix(a_out, b_out)
        master = apply_headroom(master, -6)
        master = soft_limit(master, -1)
        output(master)

    switch_current_song_to_target()
```

### 7.6 engine.py

新增方法：

```python
def xfade_eq_band_mix(transition_plan: dict):
    try:
        return eq_mixer.run_eq_band_mix(transition_plan)
    except Exception as exc:
        log.exception("eq_band_mix_failed")
        return ordinary_xfade_fallback(transition_plan)
```

保留现有 play_fallback：

```text
如果 engine 当前已经停播，直接 play target，不要假装 xfade 成功。
```

---

## 8. 安全策略

必须固定：

```text
master_headroom_db = -6
limiter_ceiling_db = -1
smooth_ms = 30
max_eq_boost_db = +3
min_eq_cut_db = -60
```

禁止：

```text
两首歌 Low 同时 0 dB 持续超过 1 小节
EQ 参数瞬间跳变
转场失败后静音
转场失败后返回 200 但没播放
```

---

## 9. 测试计划

### 9.1 后端单测

新增：

```text
app/tests/test_eq_transition_strategy.py
app/tests/test_eq_transition_presets.py
app/tests/test_mix_profile.py
app/tests/test_eq_band_mix_router.py
```

必须覆盖：

```text
缺少 mix_profile 时返回 fallback xfade
低频冲突高时选择 bass_swap
人声冲突高时选择 vocal_safe
用户选择 smooth 时强制 smooth_blend
用户选择 filter 时强制 filter_sweep
返回 JSON 包含 deck_a/deck_b/safety/reason
```

### 9.2 RK 单测

新增：

```text
cypher-integration/rk3588-edge/tests/test_eq_envelope_runner.py
cypher-integration/rk3588-edge/tests/test_eq_mixer_plan_parse.py
cypher-integration/rk3588-edge/tests/test_eq_band_mix_fallback.py
```

必须覆盖：

```text
自动化曲线插值正确
EQ 参数平滑
非法 plan 回退 ordinary xfade
engine_not_playing 时 play_fallback
```

### 9.3 端到端测试

测试场景：

```text
1. 普通丝滑融合：A -> B，不爆音，能听到渐入
2. 硬低频换底：B Low 前期关闭，最后接管
3. 人声保护：B Mid 前半段被压低
4. 扫频过渡：B 从薄到完整
5. RK 不支持 eq_band_mix：App 自动回退普通 xfade
```

音频验收：

```text
peak <= -1 dB
无明显 click/pop
无静音
低频不糊
切歌发生在小节/段落附近
```

---

## 10. 部署步骤

### 10.1 后端部署到 Jetson

本地测试：

```powershell
cd D:\work\harbeat-client
python -m pytest app/tests/test_eq_transition_strategy.py
python -m pytest app/tests/test_eq_transition_presets.py
python -m pytest app/tests/test_mix_profile.py
python -m pytest app/tests/test_eq_band_mix_router.py
```

同步到 Jetson：

```bash
# 确保代码进入真实运行目录
/home/mark/harbeat
```

重启：

```bash
ssh root@100.87.142.21
cd /home/mark/harbeat
systemctl restart harbeat-api
journalctl -u harbeat-api -n 120 --no-pager
```

健康检查：

```bash
curl -i http://127.0.0.1:8000/api/health
curl -i http://8.136.120.255/api/auth/me
```

`/api/auth/me` 未登录返回 401 是正常现象。

### 10.2 RK3588 部署

同步目标：

```text
/home/cat/cypher
```

重启：

```bash
ssh cat@192.168.43.7
cd /home/cat/cypher
sudo systemctl restart cypher-edge-agent
sudo systemctl restart cypher-audio-engine
systemctl is-active cypher-edge-agent cypher-audio-engine cypher-sync-worker cypher-input-daemon
```

日志：

```bash
journalctl -u cypher-edge-agent -n 120 --no-pager
journalctl -u cypher-audio-engine -n 120 --no-pager
```

### 10.3 Flutter App 重新安装

```powershell
cd D:\work\harbeat-client\mobile
D:\flutter_install\flutter\bin\flutter.bat clean
D:\flutter_install\flutter\bin\flutter.bat pub get
D:\flutter_install\flutter\bin\flutter.bat build apk --debug
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
```

如果旧行为仍存在：

```powershell
C:\Android\platform-tools\adb.exe shell pm clear com.example.harbeat_mobile
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
```

---

## 11. 联调检查清单

### 11.1 手机可达性

```powershell
C:\Android\platform-tools\adb.exe shell curl -i http://8.136.120.255/api/auth/me
C:\Android\platform-tools\adb.exe shell curl -i http://192.168.43.7:9000/health
```

### 11.2 后端转场计划

请求：

```bash
curl -X POST http://8.136.120.255/api/dj/transitions/plan \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "current_song_id":"A",
    "target_song_id":"B",
    "transition_mode":"eq_band_mix",
    "eq_mix_user_mode":"auto",
    "target_style":"hiphop",
    "current_position_sec":123.4
  }'
```

应返回：

```text
transition_mode = eq_band_mix
strategy 非空
deck_a 非空
deck_b 非空
safety 非空
reason 非空
```

### 11.3 RK 执行

调用 App 或直接调用 edge-agent：

```bash
curl -X POST http://192.168.43.7:9000/xfade \
  -H "Content-Type: application/json" \
  -d @transition_plan.json
```

日志应看到：

```text
eq_band_mix_start
eq_band_mix_strategy=<strategy>
eq_band_mix_finished
```

失败时应看到：

```text
eq_band_mix_failed
fallback=ordinary_xfade 或 play_fallback
```

不能出现：

```text
200 OK 但 state.playing=false
静音
audio-engine crash
```

---

## 12. 完成标准

全部完成后，应满足：

```text
1. App DJ Control 页面出现混音方式选择
2. 用户可选择自动、丝滑、强节奏、人声保护、扫频
3. App 能请求 Jetson 生成 eq_band_mix transition_plan
4. transition_plan 包含 deck_a/deck_b 的 EQ 与 fader 曲线
5. RK edge-agent 能接收 transition_plan
6. RK audio-engine 能执行 EQ 频段混音
7. 转场失败时回退普通 xfade
8. 现有能量切歌、风格切歌、候选池同步不受影响
9. 第一版全流程只依赖 MP3，不依赖 stems
10. 真实手机、Jetson、公网 API、RK 局域网联调通过
```

---

## 13. 禁止项

第一版禁止做：

```text
禁止把 MP3 预先全部转 WAV 常驻存储
禁止生成 vocal/drums/bass/instrumental stems
禁止让 RK 播放依赖 stems
禁止改掉现有 sync-worker 缓存流程
禁止播放期间临时下载目标歌
禁止删除普通 xfade fallback
禁止没有 limiter 就上线
禁止没有参数平滑就上线
禁止 App 展示复杂 Low/Mid/High 参数给普通用户
```

---

## 14. 给代码修改 AI Agent 的执行提示词

把下面这段直接发给代码修改 AI：

```text
你现在要在 HarBeat 项目中新增 DJ EQ 频段转场功能。不要重写项目，不要改动登录、曲库同步、候选池准备、能量切歌和风格切歌选歌逻辑。只新增 transition_mode=eq_band_mix。

后端 Jetson：
1. 在 app/modules/dj_control 下新增 mix_profile.py、band_analysis.py、eq_transition_presets.py、eq_transition_strategy.py。
2. 在 schemas.py 增加 transition_mode=eq_band_mix、EqMixUserMode、EqBandMixPlan 等 schema。
3. 在 router.py 的 /api/dj/transitions/plan 支持 eq_band_mix。
4. eq_transition_strategy.py 根据 mix_profile_v1、target_style、eq_mix_user_mode 决策 smooth_blend、soft_bass_swap、hard_bass_swap、vocal_safe、filter_sweep。
5. 缺少 mix_profile 或任何异常时返回 ordinary_xfade fallback。

Flutter：
1. 在 DJ Control 页面新增混音方式选择：自动、丝滑、强节奏、人声保护、扫频。
2. 确认切歌时先请求 /api/dj/transitions/plan 获取 transition_plan，再把 transition_plan 发给 RK /xfade。
3. 如果 RK 不支持或失败，回退普通 xfade。

RK3588：
1. 在 audio-engine 新增 eq_filters.py、envelope_runner.py、eq_mixer.py。
2. edge-agent /xfade 支持 transition_mode=eq_band_mix 并把 transition_plan 传给 audio-engine。
3. audio-engine 执行两 deck MP3 解码后的 PCM 混音，对 A/B 分别应用 Low/Mid/High EQ、fader、filter。
4. 固定 headroom=-6dB，limiter=-1dB，smooth_ms=30。
5. 异常时 ordinary_xfade fallback；engine_not_playing 时 play_fallback。

第一版只允许 MP3，不允许 stems，不允许 vocal/drums/bass/instrumental 文件依赖。
完成后新增对应 pytest 和 RK 测试，确保现有普通 xfade、能量切歌、风格切歌不回归。
```

---

## 15. 参考资料

1. HarBeat 项目交接与真实部署手册，2026-06-07，用户上传文档 `project(7).md`
2. Serato Play - https://support.serato.com/hc/en-us/articles/360001274856-Serato-Play
3. Pioneer DJM-900NXS - https://www.pioneerdj.com/en/product/dj-mixers/djm-900nxs/
4. Native Instruments Traktor EQ and Filter Models - https://support.native-instruments.com/hc/en-us/articles/210273465-EQ-and-Filter-Models-in-TRAKTOR-PRO-2
5. DJ.Studio EQ Mixing - https://dj.studio/blog/dj-eqmixing
6. Digital DJ Tips Basic Transitions - https://www.digitaldjtips.com/rock-the-dancefloor/five-basic-dj-transitions/
7. Automatic DJ Transitions with Differentiable Audio Effects and GANs - https://arxiv.org/abs/2110.06525
8. Automatic Detection of Cue Points for DJ Mixing - https://arxiv.org/abs/2007.08411
