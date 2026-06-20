# HarBeat 项目交接与模块扩展指南

本文给接手者说明当前 HarBeat 项目的真实结构、数据流、混音链路、三端部署方式，以及后续如何安全修改或增添模块。当前项目目标是：在不接入 Spotify API 的前提下，用本地曲库、音频分析数据和 RK 端实时音频引擎实现 Spotify 风格自动接歌效果。

## 1. 项目整体架构

代码根目录：

```text
D:\work\harbeat-client
```

核心分为四层：

```text
app/                                  Jetson/FastAPI 后端
mobile/                               Flutter Android App
cypher-integration/rk3588-edge/       RK3588 边缘播放端
docs/                                 方案、交接、运行说明
```

运行时三端关系：

```text
Android App
  -> Jetson FastAPI: 选歌、排歌、曲库、分析数据、生成转场计划
  -> RK edge-agent: 播放、预加载、crossfade、加花、状态查询

Jetson FastAPI
  -> PostgreSQL: 曲库和分析字段
  -> NAS/music-files: 原始音频、stems、素材文件
  -> RK sync-worker: 通过 manifest 提供可下载音频资源

RK3588
  -> sync-worker: 根据 manifest 下载 original/stem 到本地 cache
  -> edge-agent: HTTP API，给 App 调用
  -> audio-engine: 本地 socket，真正播放和混音
```

当前部署主机：

```text
Jetson API: root@100.87.142.21, repo /home/mark/harbeat, service harbeat-api
RK3588: cat@192.168.43.7, repo /home/cat/cypher
RK services: cypher-sync-worker, cypher-audio-engine, cypher-edge-agent
Android package: com.example.mobile
ADB: C:\Android\platform-tools\adb.exe
```

不要把密码写进代码或文档。需要重启 RK sudo 服务时向项目 owner 获取密码。

## 2. 后端入口与模块挂载

FastAPI 入口：

```text
app/main.py
```

全局路由聚合：

```text
app/modules/router.py
```

新增后端模块的标准流程：

1. 在 `app/modules/<module_name>/` 下新增：
   - `router.py`
   - `schemas.py`
   - `service.py`
   - `models.py`，如果需要数据库表
2. 在 `app/modules/router.py` 中 include：

```python
from app.modules.<module_name>.router import router as <module_name>_router
api_router.include_router(<module_name>_router, prefix="/api/<module_name>", tags=["<module_name>"])
```

3. 如果有 SQLAlchemy model，要确保被 `app/modules/models.py` import，否则 ORM relationship 可能初始化失败。
4. 返回格式统一使用：

```python
from app.shared.responses import APIResponse
return APIResponse(data={...})
```

5. 新增接口要加测试到：

```text
app/tests/
```

## 3. 重要后端模块

### 曲库模块

```text
app/modules/library/
```

关键文件：

```text
models.py              LibrarySong 数据表
router.py              /api/library/songs 等接口
service.py             创建/替换曲库歌曲
background_tasks.py    run_analysis_and_separation 音频分析与分轨入口
schemas.py             曲库返回结构
```

`LibrarySong` 当前保存了混音需要的大量分析字段：

```text
bpm
key
camelot_key
energy
beat_points
bpm_curve
energy_curve
loudness_profile
dj_hot_cues
vocal_events
bass_risk_windows
transition_windows
stem_activity
cue_points
downbeats
phrase_map
genre_profile
stems
```

如果新增分析字段：

1. 修改 `app/modules/library/models.py`。
2. 补迁移脚本或一次性 backfill 脚本。
3. 修改 `background_tasks.py` 写入逻辑。
4. 修改 `schemas.py` 是否对 App 暴露。
5. 更新相关测试。

### 音频流与 Manifest

```text
app/modules/stream/router.py
app/modules/manifest/router.py
```

用途：

- App 本地预览播放走 `/api/stream/...`
- RK sync-worker 根据 manifest 下载音频文件
- 当前 Spotify 风格混音只需要 `original.mp3` 或其他 original 格式，不强制 stems
- 详情页单独点人声/鼓组等 stem 时，才需要拉取 stem mp3

注意：不要再让自动混音启动阶段强制下载全部 stems，否则加载会很慢。

## 4. DJ Control 后端

核心目录：

```text
app/modules/dj_control/
```

关键文件：

```text
router.py                         /api/dj 所有接口
dance_style.py                    风格选歌
sequencer.py                      排歌/能量序列
cut_strategy.py                   能量/风格切歌
vibe_search.py                    本地 vibe 检索
eq_transition_strategy.py          MP3-only EQ band mix 老策略
eq_transition_presets.py           EQ/fader/filter 曲线 preset
mix_profile.py                    从 LibrarySong 构造 mix_profile_v1
spotify_mix/section_matcher.py     当前默认 Spotify 风格段落匹配计划器
spotify_mix/section_features.py    段落特征抽取
spotify_mix/section_scorer.py      段落对打分
```

### 当前默认混音计划

App 默认调用：

```json
{
  "transition_mode": "section_match",
  "eq_mix_user_mode": "auto"
}
```

后端入口：

```text
app/modules/dj_control/router.py
plan_transition_endpoint
```

分支逻辑：

```text
section_match     -> plan_section_match_transition
eq_band_mix       -> plan_eq_band_mix_transition
ordinary_xfade    -> mixer_rules.build_transition_spec
```

`section_match` 会返回：

```text
transition_mode: section_match
execution_mode: eq_band_mix
strategy: smooth_blend / soft_bass_swap / hard_bass_swap / vocal_safe / filter_sweep
from_at_sec
to_at_sec
fade_sec
deck_a
deck_b
section_match.debug 信息
```

注意：虽然业务模式叫 `section_match`，但 RK 执行模式仍是 `eq_band_mix`。这是为了复用 RK 已经稳定的 EQ-band 自动化执行通道。

## 5. 当前 Spotify 风格混音算法

当前实现不调用 Spotify API，也不依赖 stems。它使用本地已分析好的：

```text
phrase_map
downbeats
bpm
camelot_key
energy_curve
vocal_events
bass_risk_windows
loudness_profile
```

### 5.1 候选出点

上一首 A 歌会枚举最多 3 个 outro candidates：

1. label 为 `outro`
2. 最后一个或倒数第二个 `chorus`
3. 最后 30 秒内段落
4. 倒数 2-3 个 phrase

实现位置：

```text
app/modules/dj_control/spotify_mix/section_features.py
enumerate_outro_sections
```

### 5.2 候选入点

下一首 B 歌会枚举最多 3 个 intro candidates：

1. 第一个 `chorus`
2. 第一个 `drop`
3. 前几段 `verse`
4. 首段 `intro` 的后半部分
5. 第一段 fallback

实现位置：

```text
app/modules/dj_control/spotify_mix/section_features.py
enumerate_intro_sections
```

### 5.3 段落对评分

每个 `(A section, B section)` 组合按 100 分制评分：

```text
base_priority      20 分，段落语义优先级
bpm                20 分，BPM 比例
key                15 分，Camelot 距离
loudness           10 分，响度差
vocal              15 分，人声重叠风险
low_band           10 分，低频冲突
completeness       10 分，downbeat/phrase 对齐
cursor_penalty     可选，如果离当前播放位置太远会扣分
```

实现位置：

```text
app/modules/dj_control/spotify_mix/section_scorer.py
score_section_pair
```

### 5.4 策略选择

评分后选择下列策略之一：

```text
smooth_blend       高兼容度，平滑 EQ/fader
soft_bass_swap     中等低频冲突，渐进换低频
hard_bass_swap     重低频冲突，较快切低频
vocal_safe         双人声风险，压中频保护人声
filter_sweep       BPM/调性跨度大，用扫频遮蔽冲突
```

曲线 preset 在：

```text
app/modules/dj_control/eq_transition_presets.py
```

### 5.5 回退

回退顺序：

```text
section_match 正常计划
  -> 缺 phrase/downbeat 等数据时，生成 section_match fallback，但 execution_mode 仍是 eq_band_mix
  -> App 请求失败时，回退 eq_band_mix
  -> RK eq_band_mix 执行失败时，edge-agent 回退普通 xfade
  -> App 没有任何计划时，本地生成 8 秒 ordinary_xfade
```

## 6. App 端混音流程

核心文件：

```text
mobile/lib/src/dj_control_page.dart
mobile/lib/src/api_client.dart
mobile/lib/src/edge_agent_client.dart
mobile/lib/src/sync_worker_client.dart
mobile/lib/src/library/song_detail_page.dart
```

### 6.1 启动自动混音

入口：

```text
mobile/lib/src/dj_control_page.dart
_startLiveMix
```

启动时流程：

1. 根据用户选择的风格、vibe 或手选歌曲得到 `ordered`。
2. 同步候选池 original 文件到 RK。
3. 调用 `_prepareAllTransitionPlansBeforePlay`。
4. 对每一对相邻歌曲调用 `_planSectionMatchTransition`。
5. 保存到 `_preparedTransitionPlans`。
6. 播第一首。
7. 到转场点时调用 `_edgeXfadeFromPlan`。

### 6.2 转场计划生成

```text
_planSectionMatchTransition
```

请求 Jetson：

```dart
transitionMode: 'section_match'
eqMixUserMode: 'auto'
applyPhraseAlignment: false
```

这里 `applyPhraseAlignment` 关闭，是因为 `section_match` 自己已经完成段落选择和 downbeat 对齐。如果再套通用 phrase alignment，会覆盖 section_match 选出的点。

### 6.3 发给 RK 执行

```text
_edgeXfadeFromPlan
```

如果 plan 是：

```text
transition_mode == eq_band_mix
transition_mode == section_match
execution_mode == eq_band_mix
```

App 都会把它作为 `eq_band_mix` 执行计划发给 RK：

```dart
transitionMode: 'eq_band_mix'
transitionPlan: plan
```

这是当前三端联动的关键适配。

### 6.4 详情页播放策略

```text
mobile/lib/src/library/song_detail_page.dart
```

当前策略：

- 曲库整首播放：拉取 `original.mp3`
- 详情页整首播放：拉取 `original.mp3`
- 点击鼓组/人声/bass/other：拉取对应 stem mp3
- 不再把 wav 当作 MP3 cache target 命中

## 7. RK3588 端结构

目录：

```text
cypher-integration/rk3588-edge/
```

关键服务：

```text
edge-agent/       HTTP API，App 直接调用
sync-worker/      下载 Jetson manifest 里的音频资源
audio-engine/     真正播放、crossfade、EQ、filter、stem solo
input-daemon/     外设按键输入
```

### 7.1 edge-agent

关键文件：

```text
cypher-integration/rk3588-edge/edge-agent/main.py
cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py
```

重要接口：

```text
GET  /health
GET  /state
POST /play
POST /xfade
POST /prefetch
POST /cache/validate
POST /load_plan
POST /trigger
```

`/xfade` 中：

```text
transition_mode == eq_band_mix && transition_plan exists
  -> forward xfade_eq_band_mix to audio-engine
else
  -> ordinary xfade
```

### 7.2 sync-worker

关键文件：

```text
cypher-integration/rk3588-edge/sync-worker/main.py
```

职责：

- 读取 manifest
- 下载 original 和可选 stems
- 写入：

```text
/home/cat/cypher/cache/<song_id>/original.mp3
/home/cat/cypher/cache/<song_id>/vocals.mp3
/home/cat/cypher/cache/<song_id>/drums.mp3
/home/cat/cypher/cache/<song_id>/bass.mp3
/home/cat/cypher/cache/<song_id>/other.mp3
```

当前自动混音应只要求 original。不要在启动自动混音时强制 stems。

### 7.3 audio-engine

关键文件：

```text
cypher-integration/rk3588-edge/audio-engine/engine.py
cypher-integration/rk3588-edge/audio-engine/socket_server.py
```

`eq_band_mix` 执行入口：

```text
engine.py
manual_eq_band_mix
```

实际混音 block 处理：

```text
_read_eq_band_deck
_automation_eq_db
```

EQ 限幅：

```text
low:  -36dB ~ +12dB
mid:  -24dB ~ +12dB
high: -24dB ~ +12dB
```

注意：`section_match` 本身不会发给 audio-engine。audio-engine 只认识实际执行层的 `eq_band_mix`。

## 8. 新增混音策略的方法

假设要新增一种策略 `my_new_strategy`：

1. 在后端 preset 中加曲线：

```text
app/modules/dj_control/eq_transition_presets.py
```

要包含：

```python
"duration_beats": 32,
"rk_style": "blend" 或 "filter" 等 RK 支持 style,
"deck_a": {"fader": ..., "eq": ..., "filter": ...},
"deck_b": {"fader": ..., "eq": ..., "filter": ...},
```

2. 在策略选择器中加入条件：

```text
app/modules/dj_control/spotify_mix/section_scorer.py
choose_strategy
```

3. 如果用户可以手动指定，扩展：

```text
app/modules/dj_control/spotify_mix/section_matcher.py
_strategy_override
```

4. 如果 App UI 要出现新选项，改：

```text
mobile/lib/src/dj_control_page.dart
```

5. 加测试：

```text
app/tests/test_section_matching.py
app/tests/test_eq_transitions.py
```

6. 如果 EQ 曲线超出现有限幅，要同步修改 RK：

```text
cypher-integration/rk3588-edge/audio-engine/engine.py
```

## 9. 新增选歌/排歌模块的方法

新增选歌模块建议放在：

```text
app/modules/dj_control/<new_selector>.py
```

输入尽量使用 `LibrarySong`，输出保持：

```python
[
  {
    "song_id": "...",
    "score": 0.82,
    "reason": [...],
    "score_breakdown": {...}
  }
]
```

然后在：

```text
app/modules/dj_control/router.py
```

新增 endpoint，例如：

```text
POST /api/dj/my_selector
```

App 端新增调用：

```text
mobile/lib/src/api_client.dart
```

UI 接入：

```text
mobile/lib/src/dj_control_page.dart
```

如果输出要进入自动混音，最后一定要转换为 `List<LibrarySong> ordered`，走现有 `_startLiveMix` 流程，避免新模块绕过缓存和转场预生成。

## 10. 测试清单

后端编译：

```powershell
D:\python\python3.13.7\python.exe -m py_compile app\modules\dj_control\router.py app\modules\dj_control\spotify_mix\section_matcher.py
```

后端关键测试：

```powershell
D:\python\python3.13.7\python.exe -m pytest app\tests\test_section_matching.py app\tests\test_spotify_mix_integration.py app\tests\test_eq_transitions.py
```

RK 测试：

```powershell
D:\python\python3.13.7\python.exe -m pytest cypher-integration\rk3588-edge\tests\test_engine_envelopes.py
```

移动端：

```powershell
cd mobile
dart format lib\src\dj_control_page.dart
flutter analyze
flutter build apk --debug
```

当前 `flutter analyze` 可能存在项目既有 warning/info。如果只改混音模块，要确认没有新增 error 或新增明显 warning。

## 11. 部署清单

### Jetson

```powershell
scp app\modules\dj_control\router.py root@100.87.142.21:/home/mark/harbeat/app/modules/dj_control/router.py
scp app\modules\dj_control\spotify_mix\section_*.py root@100.87.142.21:/home/mark/harbeat/app/modules/dj_control/spotify_mix/
ssh root@100.87.142.21 "cd /home/mark/harbeat && /home/mark/venvs/harbeat/bin/python -m py_compile app/modules/dj_control/router.py app/modules/dj_control/spotify_mix/section_matcher.py && systemctl restart harbeat-api && systemctl is-active harbeat-api"
```

验证：

```bash
curl http://127.0.0.1:8000/health
```

### RK

```powershell
scp cypher-integration\rk3588-edge\audio-engine\engine.py cat@192.168.43.7:/home/cat/cypher/audio-engine/engine.py
ssh cat@192.168.43.7 "cd /home/cat/cypher && /home/cat/venvs/edge/bin/python -m py_compile audio-engine/engine.py && sudo systemctl restart cypher-audio-engine cypher-edge-agent && systemctl is-active cypher-audio-engine cypher-edge-agent"
```

验证：

```bash
curl http://127.0.0.1:9000/health
curl http://127.0.0.1:9000/state
```

### Android

```powershell
cd mobile
flutter build apk --debug
C:\Android\platform-tools\adb.exe install -r build\app\outputs\flutter-apk\app-debug.apk
```

取 token：

```powershell
C:\Android\platform-tools\adb.exe shell run-as com.example.mobile cat /data/data/com.example.mobile/shared_prefs/FlutterSharedPreferences.xml
```

## 12. 真实端到端验证方法

1. 从手机 token 或登录接口取得 JWT。
2. 在 Jetson 调：

```bash
POST http://127.0.0.1:8000/api/dj/transitions/plan
Authorization: Bearer <token>
{
  "prev_song_id": "...",
  "next_song_id": "...",
  "cursor_sec": 120,
  "transition_mode": "section_match",
  "eq_mix_user_mode": "auto"
}
```

期望：

```text
transition_mode == section_match
execution_mode == eq_band_mix
section_match.is_fallback == false，若真实有 phrase_map
deck_a/deck_b 有 fader/eq/filter 曲线
```

3. 让 RK 先播放上一首：

```bash
POST http://127.0.0.1:9000/play
```

4. 将 plan 包成 RK `/xfade` 请求：

```json
{
  "to_song_id": "...",
  "fade_sec": 3.5,
  "to_at_sec": 24.9,
  "style": "filter",
  "fallback_style": "blend",
  "transition_mode": "eq_band_mix",
  "transition_plan": { ...Jetson 返回的 section_match plan... }
}
```

期望：

```text
requested_tier == eq_band_mix
actual_tier == eq_band_mix
degraded == false
```

## 13. 常见问题

### 13.1 曲库页面能播，详情页 stem 不能播

检查：

```text
App 是否请求的是 stem mp3 manifest
RK cache/<song_id>/<stem>.mp3 是否存在
sync-worker status 是否 busy/failed
audio-engine stem_solo 是否返回 stems_not_loaded
```

### 13.2 自动混音启动特别慢

优先检查是否误拉 stems。Spotify 风格本地混音只需要 original，不应在启动阶段下载 vocals/drums/bass/other。

### 13.3 RK 网络请求失败

检查：

```bash
adb devices
adb shell ping <RK_IP>
ssh cat@192.168.43.7 "curl http://127.0.0.1:9000/health"
ssh cat@192.168.43.7 "systemctl is-active cypher-edge-agent cypher-audio-engine cypher-sync-worker"
```

### 13.4 section_match 总是 fallback

检查 PostgreSQL 中对应歌曲是否有：

```text
phrase_map
downbeats
energy_curve
```

没有的话先跑分析：

```text
app/modules/library/background_tasks.py
run_analysis_and_separation(song_id)
```

### 13.5 转场听起来仍然像普通 xfade

检查 RK 返回：

```text
actual_tier
degraded
degrade_reason
```

如果 `actual_tier != eq_band_mix`，说明计划没有走 `xfade_eq_band_mix` 或执行失败回退。

## 14. 当前约束和原则

1. 不接入 Spotify API。
2. 不从非授权来源下载商业歌曲。
3. 自动混音优先使用 original MP3/PCM，不强制 stems。
4. stems 只用于详情页分轨播放或明确的 stem-aware 效果。
5. 新模块必须接入现有缓存、manifest、预加载、fallback 流程，不要单独开一条绕过 RK 状态管理的播放链路。
6. 修改 RK 音频引擎后必须跑 `test_engine_envelopes.py`。
7. 修改后端转场计划后必须跑 `test_section_matching.py` 和 `test_eq_transitions.py`。

## 15. 最近已验证状态

最近一次端到端验证结果：

```text
Jetson harbeat-api: active
RK cypher-sync-worker: active
RK cypher-audio-engine: active
RK cypher-edge-agent: active
Android APK: build/install success
section_match API: success
RK xfade: requested_tier=eq_band_mix, actual_tier=eq_band_mix, degraded=false
```

最近一次测试：

```text
22 passed
```

覆盖：

```text
app/tests/test_section_matching.py
app/tests/test_spotify_mix_integration.py
app/tests/test_eq_transitions.py
cypher-integration/rk3588-edge/tests/test_engine_envelopes.py
```
