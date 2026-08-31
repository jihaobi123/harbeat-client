# HarBeat DJ Control Default Render / Default Mix 事实确认补充

版本：2026-07-08
用途：补充 `docs/harbeat_dj_control_runtime_call_chain_20260708.md` 中 default render / default mix 的真实实现细节。
原则：只记录本轮从源码、真机、云端接口、RK 缓存、业务 API 中确认到的事实；未能在当前时刻连通验证的内容单独列出。

## 1. 本轮确认范围

本轮重点确认以下问题：

- 云端 `http://8.136.120.255` 当前到底是什么服务。
- `default_mix` / `default_render` 的真实后端入口和资源生成方式。
- `transition_render.wav` / `transition_render.json` 是否真实存在、是否可下载。
- 手机当前真实登录态和调用的业务 API。
- 当前曲库分析字段是否真实返回，而不是只存在于源码 schema。
- RK sync-worker / audio-engine 对 pair render 的消费方式。
- RK 当前 live 状态是否能再次连通确认。

## 2. 云端入口确认

### 2.1 `8.136.120.255` 是 HarBeat Gateway

确认命令：

```powershell
curl.exe -sS --max-time 8 http://8.136.120.255/openapi.json
```

确认结果：

- 返回 `info.title = "HarBeat Gateway"`。
- 网关 OpenAPI 只暴露少量代理路由：
  - `GET /health`
  - `GET /jetson/health`
  - `GET /edge/registry`
  - `/edge/{rk_id}/{path}`：代理到指定 RK。
  - `/{path}`：代理所有未匹配路由到 Jetson / 业务后端。

结论：

- `http://8.136.120.255` 当前不是业务后端本体的 OpenAPI，而是网关。
- 手机访问的 `/api/...` 路径会经该网关继续代理到后端服务。

### 2.2 网关健康状态确认

确认命令：

```powershell
curl.exe -sS --max-time 8 http://8.136.120.255/health
```

确认结果：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "service": "gateway",
    "status": "ok"
  }
}
```

### 2.3 RK registry 确认

确认命令：

```powershell
curl.exe -sS --max-time 10 http://8.136.120.255/edge/registry
```

确认结果：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "rk_ids": ["rk-001"]
  }
}
```

结论：

- 网关知道至少一个 RK 注册实例：`rk-001`。
- 这只确认 registry 记录存在，不等于当前局域网 `192.168.43.7` 在线。

## 3. 后端 default render 真实入口

### 3.1 业务后端入口

当前 default render 的业务入口是：

```text
POST /api/dj/transitions/plan
```

源码路径：

- `app/modules/dj_control/router.py`
- 函数：`plan_transition_endpoint`
- 关键分支：`if payload.transition_mode == "default_mix":`

调用链：

```text
plan_transition_endpoint()
  -> default_transition_planner.plan_default_transition()
  -> reference_renderer.ensure_reference_render()
  -> default_transition_planner.attach_render_resources()
  -> APIResponse(data=spec)
```

关键源码位置：

- `app/modules/dj_control/router.py:417`
- `app/modules/dj_control/router.py:428`
- `app/modules/dj_control/router.py:433`
- `app/modules/dj_control/router.py:441`
- `app/modules/dj_control/router.py:444`

结论：

- 后端不是只做 pair render URL 分发。
- 当前 `default_mix` 路径会先生成 pair plan，再生成或复用 pair 级 render 文件，最后把 render URL / meta URL / pair manifest 挂回响应。

### 3.2 `app/modules/dj_control/default_mix/*` 当前调用情况

已确认当前链路调用：

| 文件 | 当前作用 | 是否在 default render 链路内 |
|---|---|---|
| `app/modules/dj_control/default_mix/transition_planner.py` | 生成 pair plan、`pair_id`、切入切出点、`resume_at_sec` | 是 |
| `app/modules/dj_control/default_mix/reference_renderer.py` | 生成 / 复用 `transition_render.wav` 与 `transition_render.json` | 是 |
| `app/modules/dj_control/default_mix/playlist_selector.py` | default preset 排歌时使用 | 是，属于排歌阶段，不是 render 生成阶段 |

### 3.3 `transition_planner.py` 同名文件的真实角色

仓库里有两个容易混淆的 planner：

| 文件 | 当前真实角色 |
|---|---|
| `app/modules/dj_control/default_mix/transition_planner.py` | 业务后端 default render 当前真实链路使用 |
| `cypher-integration/rk3588-edge/audio-engine/transition_planner.py` | RK edge-agent `/transition/plan` 旁路接口使用；当前手机 default render 分支没有调用它 |

RK 旁路接口源码：

- `cypher-integration/rk3588-edge/edge-agent/edge_agent/transition_api.py`
- 路由：`POST /transition/plan`
- 函数：`transition_plan`
- 它 import 的是 RK `audio-engine/transition_planner.py` 中的 `plan_mix`。

## 4. default render 资源确认

### 4.1 云端 meta 真实可访问

确认命令：

```powershell
curl.exe -sS --max-time 15 `
  http://8.136.120.255/api/dj/default/render/2eb8c85e7badb99777f1/meta
```

确认返回：

```json
{
  "source": "default_mix_reference_renderer_v1",
  "pair_id": "2eb8c85e7badb99777f1",
  "from_song_id": "de625ac62dc4432e8500711fc9a54c51",
  "to_song_id": "13a612dcee7549aeb30d6651e1ab06b8",
  "from_at_sec": 253.515,
  "to_at_sec": 2.568,
  "duration_sec": 6.5,
  "resume_at_sec": 9.068,
  "render_strategy": "three_band_default",
  "transition_render_path": "data/default-mix/pair-cache/2eb8c85e7badb99777f1/transition_render.wav",
  "transition_render_meta_path": "data/default-mix/pair-cache/2eb8c85e7badb99777f1/transition_render.json",
  "energy_match_gain_db": 2.607,
  "prev_source_mtime": 1781597658.9072573,
  "next_source_mtime": 1781597691.1657531
}
```

结论：

- 云端业务后端真实存在 pair 级 `transition_render.json`。
- 字段与本地源码 `reference_renderer.ensure_reference_render()` 生成结构一致。
- 后端暴露时文件名是 `transition_render.json`。
- RK sync-worker 下载后保存名是 `transition_render_meta.json`。

### 4.2 云端 wav 真实可下载

确认命令：

```powershell
curl.exe -sS --max-time 15 -D - `
  http://8.136.120.255/api/dj/default/render/2eb8c85e7badb99777f1 `
  -o NUL
```

确认响应头：

```text
HTTP/1.1 200 OK
Content-Type: audio/wav
Content-Length: 573344
content-disposition: attachment; filename="transition_render.wav"
```

结论：

- 云端 `transition_render.wav` 真实存在。
- 文件大小 `573344` 字节。
- 该大小与此前通过 SSH 在 RK cache 中看到的同 pair 文件大小一致。

### 4.3 meta 字段说明

| 字段 | 来源 | 当前作用 |
|---|---|---|
| `source` | `reference_renderer.py` | 标识渲染器版本 |
| `pair_id` | `transition_planner.py` / `reference_renderer.py` | pair render 的核心索引 |
| `from_song_id` | `reference_renderer.py` | 调试 / 来源记录 |
| `to_song_id` | `reference_renderer.py` | 调试 / 来源记录 |
| `from_at_sec` | `plan_default_transition()` | 手机触发时机和 audio-engine 计算 late offset 使用 |
| `to_at_sec` | `plan_default_transition()` | 目标歌进入点 |
| `duration_sec` | `reference_renderer.py` | render 长度 |
| `resume_at_sec` | `reference_renderer.py` | render 播完后恢复目标 original 的位置 |
| `render_strategy` | `reference_renderer.py` | 调试 / 渲染策略标识 |
| `transition_render_path` | `reference_renderer.py` | 后端本地路径；RK 不直接使用这个云端路径 |
| `transition_render_meta_path` | `reference_renderer.py` | 后端本地 meta 路径 |
| `energy_match_gain_db` | `reference_renderer.py` | 调试 / 音量匹配信息 |
| `prev_source_mtime` | `reference_renderer.py` | 缓存复用校验 |
| `next_source_mtime` | `reference_renderer.py` | 缓存复用校验 |

重要结论：

- RK audio-engine 当前不直接读取 `transition_render_meta.json` 的内容。
- audio-engine 当前消费的是手机传来的 `transition_plan`。
- `transition_render_meta.json` 当前主要由 sync-worker 同步落盘，可用于调试或未来扩展。

## 5. 手机真实登录态与业务 API 确认

### 5.1 手机 SharedPreferences

确认方式：

```powershell
adb shell run-as com.example.mobile `
  cat /data/data/com.example.mobile/shared_prefs/FlutterSharedPreferences.xml
```

确认结果：

- 手机包名：`com.example.mobile`
- SharedPreferences 中存在：
  - `flutter.harbeat_token`
- 本文档不记录 token 明文。

### 5.2 当前真实用户

确认命令：

```powershell
curl.exe -H "Authorization: Bearer <phone-token>" `
  http://8.136.120.255/api/auth/me
```

确认结果：

```json
{
  "id": 2,
  "username": "qqq",
  "role": "user",
  "status": "active",
  "dance_style": "hiphop",
  "level": "beginner",
  "favorite_style": "hiphop"
}
```

结论：

- 本轮业务 API 验证使用的是手机当前真实登录态。
- 后续曲库验证不是匿名请求，也不是猜测用户。

## 6. 曲库分析字段真实返回确认

### 6.1 Do For Love

接口：

```text
GET /api/library/songs/de625ac62dc4432e8500711fc9a54c51
```

确认返回摘要：

| 字段 | 真实值 / 状态 |
|---|---|
| `title` | `Do For Love` |
| `artist` | `2Pac` |
| `bpm` | `95.7` |
| `key` | `C# minor` |
| `camelot_key` | `12A` |
| `energy` | `0.958` |
| `analysis_status` | `completed` |
| `beat_points` | 已返回，数组非空 |
| `cue_points` | 已返回，数组非空 |
| `beat_confidence` | `0.9684` |
| `beat_grid_offset` | `0.3715` |
| `beat_grid_interval` | `0.6269` |
| `beat_engines_used` | `["librosa"]` |
| `stems` | vocals / drums / bass / other 四轨路径均存在 |
| `music_features.dj` | 已返回，包含 band / groove / stem RMS 等字段 |

### 6.2 Juicy

接口：

```text
GET /api/library/songs/13a612dcee7549aeb30d6651e1ab06b8
```

确认返回摘要：

| 字段 | 真实值 / 状态 |
|---|---|
| `title` | `Juicy` |
| `artist` | `The Notorious B.I.G.` |
| `bpm` | `95.9` |
| `key` | `C# minor` |
| `camelot_key` | `12A` |
| `energy` | `0.941` |
| `analysis_status` | `completed` |
| `beat_points` | 已返回，数组非空 |
| `cue_points` | 已返回，数组非空 |
| `beat_confidence` | `0.858` |
| `beat_grid_offset` | `0.0651` |
| `beat_grid_interval` | `0.625652` |
| `beat_engines_used` | `["madmom", "beatnet", "librosa"]` |
| `stems` | vocals / drums / bass / other 四轨路径均存在 |
| `music_features.dj` | 已返回，包含 bpm / energy / low_ratio / mid_ratio / high_ratio |

### 6.3 字段确认结论

已通过真实业务 API 确认：

- `bpm`：已落库并返回。
- `key`：已落库并返回。
- `camelot_key`：已落库并返回。
- `energy`：已落库并返回。
- `beat_points`：已落库并返回；对应用户问题中的 `beat_times`。
- `cue_points`：已落库并返回。
- `stems`：已落库并返回。
- `music_features.dj`：已落库并返回。

源码中已建模、可落库的字段还包括：

- `downbeats`
- `phrase_map`
- `transition_windows`
- `transition_recommendations`
- `stem_activity`
- `stem_activity_windows`
- `loudness_profile`
- `time_signature`
- `groove_profile`
- `dancefloor_profile`

2026-07-08 对两首样例歌做字段定向查询，确认当前已部署曲库详情 API 的真实响应结构：

```text
GET /api/library/songs/de625ac62dc4432e8500711fc9a54c51
TITLE=Do For Love
top_keys=id,title,artist,duration,format,file_size,source_type,source_path,platform_id,platform_url,bpm,key,camelot_key,energy,genres,genre_status,genre_source,music_features,dance_styles,dance_style_scores,dance_style_status,classifier_params,classifier_version,analysis_status,analysis_stage,analysis_error,analyzed_at,beat_points,cue_points,beat_confidence,beat_grid_offset,beat_grid_interval,beat_engines_used,beat_needs_review,stems,song_id,created_at,user_id,updated_at
downbeats=null
phrase_map=null
transition_windows=null
music_features_keys=dj
music_features.phrase_map=null
music_features.transition_windows=null
```

```text
GET /api/library/songs/13a612dcee7549aeb30d6651e1ab06b8
TITLE=Juicy
top_keys=id,title,artist,duration,format,file_size,source_type,source_path,platform_id,platform_url,bpm,key,camelot_key,energy,genres,genre_status,genre_source,music_features,dance_styles,dance_style_scores,dance_style_status,classifier_params,classifier_version,analysis_status,analysis_stage,analysis_error,analyzed_at,beat_points,cue_points,beat_confidence,beat_grid_offset,beat_grid_interval,beat_engines_used,beat_needs_review,stems,song_id,created_at,user_id,updated_at
downbeats=null
phrase_map=null
transition_windows=null
music_features_keys=dj
music_features.phrase_map=null
music_features.transition_windows=null
```

结论：

- 对这两首样例歌，当前已部署 API 响应中没有返回 `downbeats` / `phrase_map` / `transition_windows` 顶层字段。
- 对这两首样例歌，`music_features` 当前只返回 `dj`，没有返回 `music_features.phrase_map` / `music_features.transition_windows`。

2026-07-08 21:27 通过 SSH 连接 Jetson，并使用 `/home/mark/harbeat/.env` 中服务实际数据库连接串查询云端 PostgreSQL：

```text
SSH: jetson
路径: /home/mark/harbeat
数据库: rhythm_prism
表: library_songs
```

确认 `library_songs` 表中存在这些列：

```json
[
  {"column_name": "downbeats", "data_type": "json", "is_nullable": "NO"},
  {"column_name": "id", "data_type": "character varying", "is_nullable": "NO"},
  {"column_name": "music_features", "data_type": "json", "is_nullable": "YES"},
  {"column_name": "phrase_map", "data_type": "json", "is_nullable": "NO"},
  {"column_name": "title", "data_type": "character varying", "is_nullable": "NO"},
  {"column_name": "transition_windows", "data_type": "json", "is_nullable": "YES"}
]
```

数据库真实记录摘要：

| 歌曲 | `downbeats` | `phrase_map` | `transition_windows` | `music_features` |
|---|---:|---:|---:|---|
| `Do For Love` / `de625ac62dc4432e8500711fc9a54c51` | 105 条 | 14 条 | 14 条 | dict，keys: `dj` |
| `Juicy` / `13a612dcee7549aeb30d6651e1ab06b8` | 122 条 | 16 条 | 0 条 | dict，keys: `dj` |

数据库样例字段：

```json
{
  "id": "de625ac62dc4432e8500711fc9a54c51",
  "title": "Do For Love",
  "artist": "2Pac",
  "downbeats": {
    "type": "list",
    "count": 105,
    "sample": [11.029, 13.56]
  },
  "phrase_map": {
    "type": "list",
    "count": 14,
    "sample": [
      {
        "start": 11.029,
        "end": 28.7,
        "bars": 8,
        "energy": 0.7867,
        "label": "intro",
        "intensity": 0.7182,
        "energy_range": 0.2559,
        "spectral_variation": 2.1176,
        "is_peak_section": true,
        "is_valley_section": false
      }
    ]
  },
  "transition_windows": {
    "type": "list",
    "count": 14,
    "sample": [
      {
        "start": 11.029,
        "end": 28.7,
        "label": "intro",
        "bars": 8,
        "energy": 0.7867,
        "mix_in_score": 0.88,
        "mix_out_score": 0.31,
        "clean_candidate": false,
        "stem_tags": ["drum_heavy", "bass_heavy"],
        "stem_snapshot": {
          "vocals": 0.47,
          "drums": 0.839,
          "bass": 0.833,
          "other": 0.431
        }
      }
    ]
  }
}
```

最终结论：

- `downbeats` / `phrase_map` / `transition_windows` 在数据库 schema 中真实存在。
- `Do For Love` 的 `downbeats` / `phrase_map` / `transition_windows` 均已落库且非空。
- `Juicy` 的 `downbeats` / `phrase_map` 已落库且非空，`transition_windows` 已落库但当前值为空数组。
- 当前曲库详情 API 没有把这三个字段返回给手机端；这是“接口响应缺字段”，不是“数据库没有字段”。

## 7. 手机 default render 调用流程确认

### 7.1 计划生成

源码路径：

- `mobile/lib/src/dj_control_page.dart`

关键函数：

- `_planDefaultMixRenderTransition()`
- `_prepareTransitionPlanForPair()`
- `_prepareAllTransitionPlansBeforePlay()`

调用方式：

```text
_prepareAllTransitionPlansBeforePlay()
  -> for each adjacent pair
  -> _prepareTransitionPlanForPair()
  -> _planDefaultMixRenderTransition()
  -> widget.apiClient.djPlanTransition(...)
```

请求体结构：

```json
{
  "prev_song_id": "<prev library song id>",
  "next_song_id": "<next library song id>",
  "cursor_sec": "<duration - 45s>",
  "rule_key": "default_mix_auto",
  "transition_mode": "default_mix",
  "eq_mix_user_mode": "render",
  "target_lufs": -14.0
}
```

结论：

- 点击开始混音前，手机会为所有相邻 pair 逐个生成 plan。
- 不是只生成当前 pair。
- 当前没有确认“后端后台滚动生成”；真实流程是手机端 for-loop 逐 pair 调用。

### 7.2 资源同步

源码路径：

- `mobile/lib/src/dj_control_page.dart`
- `mobile/lib/src/sync_worker_client.dart`

关键函数：

- `_defaultMixPairManifests()`
- `_syncDefaultMixAssetsForSession()`
- `SyncWorkerClient.startSync()`
- `SyncWorkerClient.syncAndWait()`

发送给 sync-worker 的 manifest 结构：

```json
{
  "plan_id": "default-mix-render-sync-<timestamp>",
  "tracks": [
    {
      "song_id": "<song id>",
      "files": {
        "original": {
          "url": "...",
          "format": "mp3"
        }
      }
    }
  ],
  "default_mix_pairs": [
    {
      "pair_id": "2eb8c85e7badb99777f1",
      "files": {
        "transition_render": {
          "url": "http://8.136.120.255/api/dj/default/render/2eb8c85e7badb99777f1",
          "format": "wav",
          "size": 573344
        },
        "transition_render_meta": {
          "url": "http://8.136.120.255/api/dj/default/render/2eb8c85e7badb99777f1/meta",
          "format": "json"
        }
      }
    }
  ]
}
```

结论：

- 手机同步 original 音频和 pair render。
- default pair render 通过 `default_mix_pairs` 传给 sync-worker。

### 7.3 播放与触发

源码路径：

- `mobile/lib/src/dj_control_page.dart`
- `mobile/lib/src/edge_agent_client.dart`

关键函数：

- `_startDefaultAutoplayOnRk()`
- `_startRkPolling()`
- `_maybeAutoXfade()`
- `_edgeDefaultRenderFromPlan()`
- `EdgeAgentClient.defaultRenderPlayback()`

流程：

```text
开始混音
  -> 同步 default mix assets
  -> POST /autoplay/default/prefetch
  -> POST /autoplay/default/start
  -> 手机每 600ms GET /state
  -> 到达 plan.from_at_sec
  -> POST /autoplay/default/render
```

`POST /autoplay/default/render` 请求体：

```json
{
  "transition_plan": {
    "transition_mode": "default_mix",
    "execution_mode": "default_render_playback",
    "pair_id": "2eb8c85e7badb99777f1",
    "from_at_sec": 253.515,
    "to_at_sec": 2.568,
    "duration_sec": 6.5,
    "resume_at_sec": 9.068,
    "default_mix": {
      "pair_id": "2eb8c85e7badb99777f1",
      "from_song_id": "de625ac62dc4432e8500711fc9a54c51",
      "to_song_id": "13a612dcee7549aeb30d6651e1ab06b8",
      "from_at_sec": 253.515,
      "to_at_sec": 2.568,
      "duration_sec": 6.5,
      "resume_at_sec": 9.068
    }
  },
  "to_song_id": "<target rk id>"
}
```

## 8. RK edge-agent 与 audio-engine 消费链路

### 8.1 edge-agent HTTP 入口

源码路径：

- `cypher-integration/rk3588-edge/edge-agent/main.py`

路由：

```text
POST /autoplay/default/render
```

函数：

```python
default_render_playback(req: DefaultRenderPlaybackRequest)
```

转发：

```python
_forward(
  "default_render_playback",
  transition_plan=req.transition_plan,
  to_song_id=req.to_song_id,
  render_path=req.render_path,
)
```

### 8.2 Pydantic 请求模型

源码路径：

- `cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py`

模型：

```python
class DefaultRenderPlaybackRequest(BaseModel):
    transition_plan: dict[str, Any]
    to_song_id: Optional[Union[int, str]] = None
    render_path: Optional[str] = None
```

### 8.3 audio-engine socket command

源码路径：

- `cypher-integration/rk3588-edge/audio-engine/socket_server.py`

关键分支：

```python
if cmd == "default_render_playback":
    result = engine.default_render_playback(
        msg.get("transition_plan") or {},
        to_song_id=msg.get("to_song_id"),
        render_path=msg.get("render_path"),
    )
```

### 8.4 audio-engine render path 解析

源码路径：

- `cypher-integration/rk3588-edge/audio-engine/engine.py`

函数：

```python
_resolve_default_render_path()
```

查找顺序包含：

- 请求显式 `render_path`
- `transition_plan.transition_render_path`
- `transition_plan.render_path`
- `transition_plan.transition_render_file`
- `transition_plan.default_mix.transition_render_path`
- `transition_plan.default_mix.render_path`
- `CACHE_DIR / "default-mix" / "pairs" / pair_id / "transition_render.wav"`
- `CACHE_DIR / "default-mix" / "pairs" / pair_id / "transition_render.mp3"`
- `CACHE_DIR / "default-mix" / "pairs" / pair_id / "render.wav"`
- `CACHE_DIR / "default-mix" / "pairs" / pair_id / "render.mp3"`

结论：

- 当前 RK audio-engine 最关键依赖是 `pair_id`。
- 只要 `~/cypher/cache/default-mix/pairs/{pair_id}/transition_render.wav` 存在，就能定位 render。

### 8.5 audio-engine 恢复 original 的依据

源码路径：

- `cypher-integration/rk3588-edge/audio-engine/engine.py`

函数：

- `default_render_playback()`
- `_resume_default_target_after_render_locked()`

关键字段：

| 字段 | 用途 |
|---|---|
| `to_song_id` | 目标歌 ID，优先使用请求顶层 `to_song_id` |
| `transition_plan.to_at_sec` | 目标歌进入点 |
| `transition_plan.default_mix.to_at_sec` | `to_at_sec` fallback |
| `transition_plan.resume_at_sec` | render 播完后恢复 original 的位置 |
| `transition_plan.default_mix.resume_at_sec` | `resume_at_sec` fallback |
| `duration_sec` | 如果没有 `resume_at_sec`，用于推导 `to_at_sec + duration_sec` |
| `from_at_sec` | 判断手机触发是否晚到，并计算 `render_offset_sec` |

恢复逻辑：

```text
播放 transition_render.wav
  -> 设置 _default_resume_after_render = {song_id, resume_at_sec}
  -> 当前 render deck 播放到末尾
  -> _resume_default_target_after_render_locked()
  -> Deck.load(target_song_id, resume_at_sec, load_stems=False)
```

结论：

- 转场片段播完后，audio-engine 恢复目标歌 original 音频。
- 恢复位置来自 `resume_at_sec`。
- 当前不是 stem-aware 实时混音。

## 9. sync-worker 与 cache 支持粒度

### 9.1 支持资源类型

源码路径：

- `cypher-integration/rk3588-edge/sync-worker/main.py`

函数：

- `_file_items()`
- `_safe_song_dir()`
- `_safe_pair_dir()`
- `_download_one()`

已确认支持：

| 类型 | 来源 manifest 字段 | RK 落盘路径 |
|---|---|---|
| original | `tracks[].files.original` | `~/cypher/cache/{song_id}/original.{ext}` |
| vocals | `tracks[].files.stems.vocals` | `~/cypher/cache/{song_id}/vocals.{ext}` |
| drums | `tracks[].files.stems.drums` | `~/cypher/cache/{song_id}/drums.{ext}` |
| bass | `tracks[].files.stems.bass` | `~/cypher/cache/{song_id}/bass.{ext}` |
| other | `tracks[].files.stems.other` | `~/cypher/cache/{song_id}/other.{ext}` |
| transition_render | `default_mix_pairs[].files.transition_render` | `~/cypher/cache/default-mix/pairs/{pair_id}/transition_render.{ext}` |
| transition_render_meta | `default_mix_pairs[].files.transition_render_meta` | `~/cypher/cache/default-mix/pairs/{pair_id}/transition_render_meta.json` |

### 9.2 cache 清理能力

源码确认存在：

```text
DELETE /cache/song/{song_id}
```

作用：

- 删除单首歌目录：`~/cypher/cache/{song_id}`

未发现源码中有：

- 自动容量上限。
- LRU 淘汰。
- 自动清理 `default-mix/pairs/{pair_id}` 的接口。

结论：

- sync-worker 支持 pair render 同步。
- 当前未确认存在 pair render 自动淘汰策略。

## 10. 生成时机确认

### 10.1 当前真实生成时机

手机源码确认：

```text
_startLiveMix()
  -> _prepareAllTransitionPlansBeforePlay()
  -> for i in 0..ordered.length-2
  -> _prepareTransitionPlanForPair()
  -> _planDefaultMixRenderTransition()
```

结论：

- 点击开始混音后，正式播放前，手机会一次性为所有相邻 pair 生成 transition plan。
- default 模式下，每个 pair 的计划生成会触发后端 `ensure_reference_render()`。
- 所以当前更接近“开始播放前批量准备相邻 pair render”，不是“边播边后台滚动生成”。

### 10.2 RK `default_autoplay_start` 的边界

源码路径：

- `cypher-integration/rk3588-edge/audio-engine/engine.py`

函数：

```python
default_autoplay_start()
```

已确认行为：

- 接收 `queue` 和 `transitions`。
- 但函数体里 `del transitions`。
- 实际只执行第一首歌 `play(song_id, start_at_sec)`。

结论：

- RK 当前没有在 `default_autoplay_start()` 内部自动滚动消费 transitions。
- 后续转场依赖手机轮询 `/state` 后主动调用 `/autoplay/default/render`。

## 11. RK 当前实时状态

### 11.1 RK 当前可连通

本轮在 2026-07-08 19:20-19:24 重新确认，RK `192.168.43.7` 当前可连通。

确认命令：

```powershell
Test-Connection -ComputerName 192.168.43.7 -Count 1 -Quiet
```

确认结果：

```text
True
```

### 11.2 edge-agent `/health` 实时响应

确认命令：

```powershell
curl.exe -sS --max-time 8 http://192.168.43.7:9000/health
```

确认返回：

```json
{
  "ok": true,
  "audio_ready": true,
  "audio_socket": "/tmp/cypher-audio.sock",
  "current_song_id": null,
  "plan_id": "mobile-v32-1781342383893",
  "session_id": "3ed4f86271604e2981426cb4de9dd6a1",
  "sync_status": {
    "running": false,
    "plan_id": null,
    "total": 0,
    "downloaded": 0,
    "completed": 0,
    "current_file": null,
    "percent": 0.0,
    "errors": []
  }
}
```

结论：

- edge-agent 当前在线。
- edge-agent 能连到 audio-engine socket：`/tmp/cypher-audio.sock`。
- 当前没有正在运行的 sync 任务。

### 11.3 edge-agent `/state` 实时响应

确认命令：

```powershell
curl.exe -sS --max-time 8 http://192.168.43.7:9000/state
```

确认返回：

```json
{
  "type": "playback_state",
  "ts": 1783509820841,
  "playing": false,
  "paused": false,
  "current_song_id": null,
  "position_sec": 0.0,
  "duration_sec": 0.0,
  "next_song_id": "e4d49cd6ba5f48058a8fad217ce6661a",
  "next_transition_in_sec": null,
  "active_loops": [],
  "active_stem_fx": null,
  "playback_tier": "non_stem",
  "last_transition": {}
}
```

结论：

- `/state` 当前真实可用。
- 当前 RK 不在播放状态：`playing=false`。
- 当前 playback tier 为 `non_stem`。

### 11.4 sync-worker `/status` 实时响应

确认命令：

```powershell
curl.exe -sS --max-time 8 http://192.168.43.7:9100/status
```

确认返回：

```json
{
  "running": false,
  "plan_id": null,
  "total": 0,
  "downloaded": 0,
  "completed": 0,
  "current_file": null,
  "percent": 0.0,
  "errors": []
}
```

结论：

- sync-worker 当前在线。
- 当前没有进行中的下载任务。
- 当前错误列表为空。

### 11.5 RK systemd 服务状态

确认命令：

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=8 cat@192.168.43.7 `
  "hostname; date; systemctl is-active cypher-edge-agent cypher-audio-engine cypher-sync-worker cypher-input-daemon"
```

确认结果：

```text
lubancat
2026年 07月 08日 星期三 19:23:59 CST
active
active
active
active
```

结论：

- RK 主机名：`lubancat`。
- 以下服务当前均为 `active`：
  - `cypher-edge-agent`
  - `cypher-audio-engine`
  - `cypher-sync-worker`
  - `cypher-input-daemon`

### 11.6 RK 运行配置

确认命令：

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=8 cat@192.168.43.7 `
  "grep -E 'JETSON_BASE_URL|CYPHER_HOME|HARBEAT|SYNC|AUDIO|RK' /home/cat/cypher/deploy/cypher.env | sed -E 's/(TOKEN|SECRET|PASSWORD)=.*/\1=<redacted>/I'"
```

确认结果：

```text
CYPHER_HOME=/home/cat/cypher
CYPHER_AUDIO_DEVICE=pulse
# CYPHER_AUDIO_DEVICE=2
# USB 声卡: CYPHER_AUDIO_DEVICE=USB
# JETSON_BASE_URL=http://100.87.142.21:8000
# RK_ID=rk-001
# HARBEAT_RK_TOKEN=<redacted>
JETSON_BASE_URL=http://8.136.120.255
```

结论：

- RK 当前 `CYPHER_HOME=/home/cat/cypher`。
- RK 当前通过 `JETSON_BASE_URL=http://8.136.120.255` 访问云端网关。
- token 已脱敏，不在文档记录明文。

### 11.7 RK default-mix pair cache 已确认

通过 SSH 确认 RK cache 中存在 pair render：

```text
/home/cat/cypher/cache/default-mix/pairs/2eb8c85e7badb99777f1/transition_render.wav
/home/cat/cypher/cache/default-mix/pairs/2eb8c85e7badb99777f1/transition_render_meta.json
```

并且同 pair 的 wav 大小为：

```text
573344 bytes
```

该大小与云端 `Content-Length: 573344` 一致。

当前 RK 本地 `transition_render_meta.json` 内容：

```json
{
  "source": "default_mix_reference_renderer_v1",
  "pair_id": "2eb8c85e7badb99777f1",
  "from_song_id": "de625ac62dc4432e8500711fc9a54c51",
  "to_song_id": "13a612dcee7549aeb30d6651e1ab06b8",
  "from_at_sec": 253.515,
  "to_at_sec": 2.568,
  "duration_sec": 6.5,
  "resume_at_sec": 9.068,
  "render_strategy": "three_band_default",
  "transition_render_path": "data/default-mix/pair-cache/2eb8c85e7badb99777f1/transition_render.wav",
  "transition_render_meta_path": "data/default-mix/pair-cache/2eb8c85e7badb99777f1/transition_render.json",
  "energy_match_gain_db": 2.607,
  "prev_source_mtime": 1781597658.9072573,
  "next_source_mtime": 1781597691.1657531
}
```

结论：

- RK 本地 meta 与云端 `/api/dj/default/render/2eb8c85e7badb99777f1/meta` 返回字段一致。
- RK 本地保存名是 `transition_render_meta.json`。
- 云端 meta 内部记录的原始后端文件名仍是 `transition_render.json`。

### 11.8 RK cache 目录结构样例

default-mix pair cache 样例：

```text
/home/cat/cypher/cache/default-mix/pairs/5944d52b651b21e43422/transition_render_meta.json 663
/home/cat/cypher/cache/default-mix/pairs/5944d52b651b21e43422/transition_render.wav 573344
/home/cat/cypher/cache/default-mix/pairs/2eb8c85e7badb99777f1/transition_render_meta.json 663
/home/cat/cypher/cache/default-mix/pairs/2eb8c85e7badb99777f1/transition_render.wav 573344
/home/cat/cypher/cache/default-mix/pairs/8cac08d2d900eaabd6d7/transition_render_meta.json 663
/home/cat/cypher/cache/default-mix/pairs/8cac08d2d900eaabd6d7/transition_render.wav 573344
```

original / stems cache 样例：

```text
/home/cat/cypher/cache/13a612dcee7549aeb30d6651e1ab06b8/original.mp3 12125588
/home/cat/cypher/cache/06e6422f7ea843d881df853ca498c1dd/original.mp3 2422298
/home/cat/cypher/cache/06e6422f7ea843d881df853ca498c1dd/vocals.wav 26690760
/home/cat/cypher/cache/06e6422f7ea843d881df853ca498c1dd/drums.wav 26690760
/home/cat/cypher/cache/06e6422f7ea843d881df853ca498c1dd/bass.wav 26690760
/home/cat/cypher/cache/06e6422f7ea843d881df853ca498c1dd/other.wav 26690760
```

结论：

- RK cache 中同时存在 original 文件、stems 文件、default-mix pair render 文件、pair meta 文件。
- `13a612dcee7549aeb30d6651e1ab06b8` 的 original 文件已在 RK 本地存在，对应前文确认的 `Juicy`。

### 11.9 RK 日志确认

edge-agent 最新日志确认手机正在轮询 `/state`：

```text
7月 08 19:23:51 lubancat cypher-edge[999]: INFO:     192.168.43.9:39412 - "GET /state HTTP/1.1" 200 OK
7月 08 19:24:27 lubancat cypher-edge[999]: INFO:     192.168.43.9:39542 - "GET /state HTTP/1.1" 200 OK
```

edge-agent 当天日志确认手机真实触发过 default render 播放：

```text
7月 08 17:53:36 lubancat cypher-edge[987]: INFO:     192.168.43.9:44036 - "POST /autoplay/default/prefetch HTTP/1.1" 200 OK
7月 08 17:53:37 lubancat cypher-edge[987]: INFO:     192.168.43.9:44038 - "POST /autoplay/default/start HTTP/1.1" 200 OK
7月 08 17:57:25 lubancat cypher-edge[987]: INFO:     192.168.43.9:45526 - "POST /autoplay/default/render HTTP/1.1" 200 OK
7月 08 18:00:59 lubancat cypher-edge[987]: INFO:     192.168.43.9:46944 - "POST /autoplay/default/render HTTP/1.1" 200 OK
7月 08 18:04:57 lubancat cypher-edge[987]: INFO:     192.168.43.9:47880 - "POST /autoplay/default/render HTTP/1.1" 200 OK
7月 08 18:09:39 lubancat cypher-edge[987]: INFO:     192.168.43.9:48960 - "POST /autoplay/default/render HTTP/1.1" 200 OK
7月 08 18:13:15 lubancat cypher-edge[987]: INFO:     192.168.43.9:49784 - "POST /autoplay/default/render HTTP/1.1" 200 OK
7月 08 18:15:59 lubancat cypher-edge[987]: INFO:     192.168.43.9:37396 - "POST /autoplay/default/render HTTP/1.1" 200 OK
7月 08 18:19:34 lubancat cypher-edge[987]: INFO:     192.168.43.9:38214 - "POST /autoplay/default/render HTTP/1.1" 200 OK
```

sync-worker 日志确认历史上已下载 default render / meta：

```text
6月 27 12:21:43 lubancat cypher-sync[984]: HTTP Request: GET http://8.136.120.255/api/dj/default/render/6e52d36040626497b505/meta "HTTP/1.1 200 OK"
6月 27 12:21:43 lubancat cypher-sync[984]: HTTP Request: GET http://8.136.120.255/api/dj/default/render/950f74b85027a3e77881 "HTTP/1.1 200 OK"
6月 27 12:21:45 lubancat cypher-sync[984]: HTTP Request: GET http://8.136.120.255/api/dj/default/render/f7ab2db4b56b119ac7fa/meta "HTTP/1.1 200 OK"
```

sync-worker 日志确认 2026-07-08 手机做过 original cache check 和 `/sync`：

```text
7月 08 17:53:02 lubancat cypher-sync[990]: INFO:     192.168.43.9:46552 - "GET /cache/check?song_id=de625ac62dc4432e8500711fc9a54c51&kind=original HTTP/1.1" 200 OK
7月 08 17:53:02 lubancat cypher-sync[990]: INFO:     192.168.43.9:46566 - "GET /cache/check?song_id=13a612dcee7549aeb30d6651e1ab06b8&kind=original HTTP/1.1" 200 OK
7月 08 17:53:26 lubancat cypher-sync[990]: INFO:     192.168.43.9:46690 - "POST /sync HTTP/1.1" 200 OK
```

audio-engine 日志确认 2026-07-08 有真实播放和转场记录：

```text
7月 08 17:53:37 lubancat cypher-audio[985]: INFO engine output stream started device=2 name=rockchip-es8388: dailink-multicodecs ES8323 HiFi-0 (hw:2,0)
7月 08 17:53:37 lubancat cypher-audio[985]: INFO engine playing song_id=fba025a6ef6e4ae7aa50ad1bc3e1c3f0 from 0.00s
7月 08 17:57:25 lubancat cypher-audio[985]: INFO engine crossfade start fba025a6ef6e4ae7aa50ad1bc3e1c3f0 -> 3083c66434a84af3b5ad4bee34d6d673 (0.1s style=blend execution=None)
7月 08 18:19:34 lubancat cypher-audio[985]: INFO engine crossfade start 9a374339c3704831b281e0190f2796ce -> ee2a9ab67d674914867b291caa45f39b (0.1s style=blend execution=None)
```

结论：

- RK 当前在线，且 edge-agent / sync-worker / audio-engine 均能通过接口或 systemd 确认。
- 手机当前仍在轮询 RK `/state`。
- edge-agent 日志确认 2026-07-08 17:57-18:19 多次真实收到 `POST /autoplay/default/render`。
- sync-worker 日志能确认 pair render / meta 的历史下载。
- audio-engine 日志能确认 2026-07-08 有真实播放与转场行为。

## 12. 对接本地算法方案的最小挂载点

这里不设计新系统，只列当前已有入口。

### 12.1 预处理缓存挂载点

适合位置：

- `app/modules/library/models.py`
- `app/modules/library/background_tasks.py`
- `app/modules/library/analysis.py`

原因：

- 当前歌曲分析字段已经落在 `LibrarySong`。
- `bpm`、`key`、`camelot_key`、`energy`、`beat_points`、`cue_points`、`stems` 已通过真实 API 确认返回。
- 如果要加入 phrase change、alignment candidate、local energy cache，最小改动是扩展 `LibrarySong` 的 JSON 字段或复用现有 `music_features` / `transition_windows` / `phrase_map`。

### 12.2 pair 级 transition plan 挂载点

适合位置：

- `app/modules/dj_control/default_mix/transition_planner.py`
- 函数：`plan_default_transition()`

原因：

- 当前 default render 的 pair plan 就在这里生成。
- 这里已经负责输出：
  - `pair_id`
  - `from_at_sec`
  - `to_at_sec`
  - `duration_sec`
  - `resume_at_sec`
  - `default_mix`

### 12.3 pair render 生成挂载点

适合位置：

- `app/modules/dj_control/default_mix/reference_renderer.py`
- 函数：`ensure_reference_render()`

原因：

- 当前 `transition_render.wav` 和 `transition_render.json` 就在这里生成。
- 替换本地算法生成的 render，最小入口就是替换或扩展该函数的 render 逻辑。

### 12.4 meta 新字段挂载点

适合位置：

- `app/modules/dj_control/default_mix/reference_renderer.py`
- `app/modules/dj_control/default_mix/transition_planner.py`

原因：

- `transition_planner.py` 适合写入计划级字段，例如 `phrase_change`、`alignment`、`curve_profile`。
- `reference_renderer.py` 适合写入渲染结果字段，例如实际 render 长度、能量匹配结果、缓存版本、渲染器版本。
- 当前 RK audio-engine 不直接读 meta 文件；如果要让 RK 消费新字段，应同步把字段放进手机传给 `/autoplay/default/render` 的 `transition_plan`。

### 12.5 RK 消费挂载点

适合位置：

- `cypher-integration/rk3588-edge/audio-engine/engine.py`
- 函数：`default_render_playback()`
- 函数：`_resolve_default_render_path()`
- 函数：`_resume_default_target_after_render_locked()`

原因：

- 当前 default render 播放与恢复 original 的逻辑都在这里。
- 如果只是替换 render 质量，不需要动这里。
- 如果要改变恢复点、late trigger offset、或读取更多 plan 字段，需要改这里。

## 13. 当前方案字段 vs 遗留字段判断

本节回答：`downbeats` / `phrase_map` / `transition_windows` / `stem_activity_windows` 到底是当前方案的一部分，还是之前链路遗留。

### 13.1 已确认运行环境

Jetson 当前运行的后端服务：

```text
service: harbeat-api.service
WorkingDirectory=/home/mark/harbeat
ExecStart=/home/mark/venvs/harbeat/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Active: active
```

systemd 当前注入的关键环境变量：

```text
PUBLIC_ASSET_BASE_URL=http://8.136.120.255
UPLOAD_DIR=/mnt/nas/harbeat/music-files
ENABLE_GPU_VOCAL_DETECTION=true
VOCAL_DETECTION_FAST=true
```

NAS 当前挂载：

```text
//192.168.5.63/harbeat on /mnt/nas/harbeat type cifs
```

Jetson 本地路径关系：

```text
/home/mark/harbeat/data/music-files -> /mnt/nas/harbeat/music-files
```

结论：

- 当前音频文件存储链路使用 NAS。
- 数据库是云端 PostgreSQL `rhythm_prism`，不是 NAS 上的 SQLite。
- NAS 上本轮未发现 `.db` / `.sqlite` / `.sql` 数据库文件。
- Jetson 本地存在 `data/harbeat.db` / `data/harbeat_local.db`，但当前 systemd 服务使用 `.env` 中的 PostgreSQL `DATABASE_URL`，不是这些 SQLite 文件。

### 13.2 default render pair cache 的真实落点

当前部署源码：

- `app/modules/dj_control/default_mix/reference_renderer.py`
- `NAS_DEFAULT_ROOT = /mnt/nas/harbeat/dj-control/default-mix/pair-cache`
- `LOCAL_DEFAULT_ROOT = data/default-mix/pair-cache`
- `pair_cache_root()` 逻辑：如果 `/mnt/nas/harbeat/dj-control/default-mix` 存在则使用 NAS，否则回退到本地。

本轮真实文件系统确认：

```text
/mnt/nas/harbeat/dj-control/default-mix/pair-cache 不存在
/home/mark/harbeat/data/default-mix/pair-cache 存在并有真实 transition_render.wav/json
```

样例：

```text
/home/mark/harbeat/data/default-mix/pair-cache/2eb8c85e7badb99777f1/transition_render.json
/home/mark/harbeat/data/default-mix/pair-cache/2eb8c85e7badb99777f1/transition_render.wav
```

该 pair 的 meta：

```json
{
  "source": "default_mix_reference_renderer_v1",
  "pair_id": "2eb8c85e7badb99777f1",
  "from_song_id": "de625ac62dc4432e8500711fc9a54c51",
  "to_song_id": "13a612dcee7549aeb30d6651e1ab06b8",
  "from_at_sec": 253.515,
  "to_at_sec": 2.568,
  "duration_sec": 6.5,
  "resume_at_sec": 9.068,
  "render_strategy": "three_band_default",
  "transition_render_path": "data/default-mix/pair-cache/2eb8c85e7badb99777f1/transition_render.wav",
  "transition_render_meta_path": "data/default-mix/pair-cache/2eb8c85e7badb99777f1/transition_render.json",
  "energy_match_gain_db": 2.607,
  "prev_source_mtime": 1781597658.9072573,
  "next_source_mtime": 1781597691.1657531
}
```

日志确认：

```text
2026-06-27 03:47:17 PermissionError: data/default-mix/pair-cache/434f7a61e209ad0cb8f6
2026-06-27 03:48:31 POST /api/dj/transitions/plan 200 OK
2026-06-27 03:50:08 GET /api/dj/default/render/434f7a61e209ad0cb8f6/meta 200 OK
2026-06-27 04:33:22-04:33:52 多次 POST /api/dj/transitions/plan 200 OK
2026-06-27 04:33:52 多个 GET /api/dj/default/render/{pair_id} 200 OK
```

结论：

- default render pair cache 是当前 2026-06-27 方案的真实产物。
- 当前 pair cache 实际落在 Jetson 本地 `/home/mark/harbeat/data/default-mix/pair-cache`，不是 NAS。

### 13.3 分析字段的生成时间和当前使用情况

RDS `library_songs` 当前样例记录：

| 歌曲 | `created_at` | `updated_at` | `downbeats` | `phrase_map` | `transition_windows` | `stem_activity_windows` |
|---|---|---|---:|---:|---:|---:|
| `Do For Love` | 2026-06-16 08:14:17 | 2026-06-21 08:05:58 | 105 | 14 | 14 | 141 |
| `Juicy` | 2026-06-16 08:14:50 | 2026-06-21 08:51:12 | 122 | 16 | 0 | 152 |

全表统计：

```json
{
  "total": 23,
  "downbeats_nonempty": 23,
  "phrase_nonempty": 23,
  "transition_windows_nonempty": 1,
  "stem_activity_windows_nonempty": 23
}
```

> 版本说明（2026-08-31）：以下数据库统计保留为历史快照，但旧的固定小节段落
> 生成逻辑已经删除。当前段落边界与标签只来自 All-In-One；`phrase_map` 只是同一
> All-In-One 段落结果的产品映射，能量仅作段落属性，不再生成或修改段落。

当前源码中的对应写入链路为：

- `app/modules/library/background_tasks.py`
  - `song.transition_windows = result.get("transition_windows", [])`
  - `song.downbeats = result.get("downbeats", [])`
  - `song.phrase_map = result.get("phrase_map", [])`
- `app/modules/library/analysis.py`
  - `_start_bar_grid_after_intro(...)`（正式段落来源为 SongFormer）
  - `_functional_segments_to_phrase_map(...)`
  - `_build_transition_windows(phrase_map)`
  - 返回 `downbeats` / `phrase_map` / `transition_windows`

日志时间线：

```text
2026-06-16 已有 Juicy 分析/manifest/stream/stems 访问日志
2026-06-21 两首样例歌 updated_at 更新
2026-06-27 default render 方案开始产生 pair-cache 和 /api/dj/default/render 访问日志
```

判断：

- `downbeats` / `phrase_map` 是当前分析模型和当前 default planner 仍在使用的字段，不是废弃字段。
- `stem_activity_windows` 在当前数据库中覆盖率最高，23/23 非空；manifest 也会输出它，属于当前分析资产。
- `transition_windows` 这个字段在模型、分析代码、manifest、planner 中都存在，但当前数据库只有 1/23 非空；因此不能把它判断成“当前稳定可依赖的主数据”。对当前这批库来说，它更像一次局部写入/历史增强留下来的数据，或者当前写入链路未完整跑通后的残留状态。
- `Do For Love` 的 `transition_windows` 非空，当前 default planner 会读到并用于候选区域。
- `Juicy` 的 `transition_windows` 为空，当前 default planner 会退回使用 `phrase_map` / `downbeats` 候选。

### 13.4 当前 default planner 实际怎么消费这些字段

源码：

- `app/modules/dj_control/default_mix/transition_planner.py`

关键事实：

```python
windows = getattr(song, "transition_windows", None) or []
```

如果 `transition_windows` 非空：

```python
source = "stem_transition_windows" if getattr(song, "stem_activity_windows", None) else "transition_windows"
```

如果 `transition_windows` 为空：

```python
phrases = getattr(song, "phrase_map", None) or []
```

再不够时：

```python
downbeats = list(getattr(song, "downbeats", None) or [])
beats = list(getattr(song, "beat_points", None) or [])
```

判断：

- 当前 default planner 的第一候选输入是 `transition_windows`。
- 但它没有直接遍历 `stem_activity_windows`；`stem_activity_windows` 当前更多通过 manifest / 其它分析链路存在。
- 对大多数当前库歌曲，由于 `transition_windows` 为空，default planner 实际主要依赖 `phrase_map` / `downbeats` 回退。

### 13.5 API 与 manifest 的差异

普通曲库详情接口：

- `app/modules/library/schemas.py`
- `LibrarySongBase` / `LibrarySongData`

当前 `LibrarySongData` 不包含：

- `downbeats`
- `phrase_map`
- `transition_windows`
- `stem_activity_windows`

所以：

```text
GET /api/library/songs/{id}
```

不会返回这些字段。

manifest 生成：

- `app/modules/manifest/__init__.py`
- `build_song_manifest(song, base_url)`

会返回：

- `analysis["transition_windows"]`
- `analysis["stem_activity_windows"]`
- `analysis["downbeats"]`
- `analysis["phrase_map"]`

判断：

- “手机曲库详情 API 看不到字段”是真的。
- “manifest / 同步资产链路可以拿到这些字段”也是真的。
- 这两个结论不冲突，是不同接口 schema 的差异。

### 13.6 最终判断

按本轮 Jetson + NAS + RDS 交叉确认：

| 项 | 判断 |
|---|---|
| `default render pair-cache` | 当前 2026-06-27 default render 方案产物，真实在线使用 |
| `downbeats` | 当前分析字段，当前 planner fallback 使用，不是遗留 |
| `phrase_map` | 当前分析字段，当前 planner fallback 使用，不是遗留 |
| `stem_activity_windows` | 当前分析资产，RDS 23/23 非空，manifest 输出；但当前 default planner 未直接遍历它 |
| `transition_windows` | 字段和代码仍存在，但当前库仅 1/23 非空；对当前数据集不能视为稳定主输入，更像历史/局部增强残留或未完整回填结果 |
| `/api/library/songs/{id}` 不返回这些字段 | 当前 schema 限制，不代表数据库没有 |
| NAS | 当前承载 music-files；本轮未发现 NAS 数据库；default render cache 当前不在 NAS |

因此，最准确的说法是：

```text
当前方案真实使用的是 default render pair-cache + DB 中的 beat/phrase 基础分析字段。
transition_windows 不是完全废弃字段，但当前库数据分布显示它不是当前稳定完整产物。
如果要把新算法接入现有 default render，不能假设 transition_windows 对所有歌可用；
应优先依赖 downbeats / phrase_map / stem_activity_windows，或先补齐/重建 pair 级 plan cache。
```

## 14. 本轮最终确认结论

已确认：

- 云端 `8.136.120.255` 是网关，且能代理业务 API。
- 云端 default render meta 和 wav 真实存在、可访问。
- `transition_render.json` 字段结构已通过真实接口确认。
- 手机当前登录态真实可用，用户为 `qqq` / user_id `2`。
- 业务曲库接口真实返回 default mix 所需核心分析字段。
- 手机 default 模式会在播放前逐 pair 生成 plan/render。
- sync-worker 支持 original、stems、pair render、pair meta 同步。
- audio-engine 使用 `transition_plan` 和 `pair_id` 消费 pair render，render 播完后按 `resume_at_sec` 恢复目标 original。
- RK `192.168.43.7` 当前可连通，`/health`、`/state`、sync-worker `/status` 均有实时响应。
- RK 上 `cypher-edge-agent`、`cypher-audio-engine`、`cypher-sync-worker`、`cypher-input-daemon` 当前均为 `active`。
- RK 本地 cache 中存在 original、stems、pair render、pair meta 文件。
- RK 日志确认手机当前轮询 `/state`，2026-07-08 当天真实调用过 `/autoplay/default/prefetch`、`/autoplay/default/start`、`/autoplay/default/render`。
- sync-worker 日志确认历史上下载过 default render / meta。
- audio-engine 日志确认 2026-07-08 有真实播放与转场记录，时间点与 edge-agent `/autoplay/default/render` 调用对应。
- 对 `Do For Love` / `Juicy` 两首样例歌，当前已部署 API 响应不返回 `downbeats` / `phrase_map` / `transition_windows`，`music_features` 下只返回 `dj`。
- 云端 PostgreSQL `rhythm_prism.library_songs` 表中真实存在 `downbeats` / `phrase_map` / `transition_windows` 列。
- `Do For Love` 的 `downbeats` / `phrase_map` / `transition_windows` 均已落库且非空；`Juicy` 的 `downbeats` / `phrase_map` 已落库且非空，`transition_windows` 已落库但当前为空数组。
- `transition_windows` 字段和代码仍存在，但当前库仅 1/23 非空，不能作为当前 default render 的稳定主输入；当前更可靠的基础输入是 `downbeats` / `phrase_map`，以及 manifest 可输出的 `stem_activity_windows`。
- NAS 当前承载 `music-files`；本轮未发现 NAS 数据库，当前业务数据库是云端 PostgreSQL `rhythm_prism`。

仍未确认：

- `Juicy` 的 `transition_windows` 为什么为空数组，本轮只确认了数据库当前值，没有追溯生成任务日志和写库原因。
