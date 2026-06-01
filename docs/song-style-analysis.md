# 歌曲风格分析说明

本文说明 HarBeat 当前“歌曲风格/流派分析”的接口、数据结构、实现方案和后续修改入口。这里的“风格”分成两层：

- `genre_profile`：音乐流派/曲风，如 `hip-hop`、`house`、`funk`、`drum-and-bass`。用于判断两首歌是否跨风格、是否调性/低频/人声风险较高。
- `dance_styles` / `dance_style_scores`：街舞适配风格，如 `breaking`、`hiphop`、`popping`、`locking`、`house`、`krump`、`waacking`。用于 DJ Control 的按舞种选歌和能量排序。

这两层不是同一个东西。Discogs / Spotify 主要补全 `genre_profile`；街舞适配度主要由本地音频特征评分得到。

## 一、相关接口

### 1. 获取曲库列表

```http
GET /api/library/songs
```

返回 `LibrarySongSummaryData`，用于列表页快速加载。当前 summary 包含：

- `id`
- `title`
- `artist`
- `duration`
- `bpm`
- `key`
- `camelot_key`
- `energy`
- `analysis_status`
- `stems`
- `cue_points`
- `beat_points`

注意：这个接口当前不返回 `genre_profile`、`dance_styles`、`dance_style_scores`。如果前端需要展示完整风格分析，应该调用歌曲详情接口。

### 2. 获取单曲详情

```http
GET /api/library/songs/{song_id}
```

返回 `LibrarySongData`，包含完整分析字段，包括：

- `genre_profile`
- `dance_styles`
- `dance_style_scores`
- `dance_style_status`
- `music_features`
- `stem_activity`
- `groove_profile`
- `dancefloor_profile`
- `phrase_map`
- `transition_windows`

### 3. 手动触发单曲分析

```http
POST /api/library/songs/{song_id}/analyze
```

这个接口会同步执行基础音频分析，然后刷新：

- BPM / key / energy / beatgrid / phrase
- `music_features["dj"]`
- `dance_styles`
- `dance_style_scores`
- `genre_profile`

对应实现：

- `app/modules/library/router.py::analyze_library_song_endpoint`
- `app/modules/library/analysis.py::analyze_audio_file`
- `app/modules/library/background_tasks.py::apply_dj_fingerprint`
- `app/modules/library/background_tasks.py::_apply_genre_classification`

### 4. 自动后台分析

部分导入链路会调用：

```python
run_analysis_and_separation(song_id)
```

对应文件：

```text
app/modules/library/background_tasks.py
```

后台任务流程：

1. 基础分析：BPM、key、energy、beatgrid、phrase、cue、transition windows。
2. Demucs stems 分离。
3. stems 后分析：vocal events、bass risk、stem activity、clean intro/outro。
4. DJ fingerprint：写入 `music_features["dj"]` 和 `dance_styles`。
5. Genre classification：写入 `genre_profile`。

如果已有歌曲之前已经分析过，不会自动拥有新加的 Discogs 标签，需要重新跑分析或使用 backfill 脚本。

## 二、数据存储位置

数据库模型：

```text
app/modules/library/models.py::LibrarySong
```

关键字段：

```python
music_features: dict
dance_styles: list[dict]
dance_style_scores: dict
dance_style_status: str
genre_profile: dict
```

返回 schema：

```text
app/modules/library/schemas.py::LibrarySongBase
app/modules/library/schemas.py::LibrarySongData
```

示例 `genre_profile`：

```json
{
  "genres": [
    {"name": "funk", "confidence": 0.8, "source": "discogs"},
    {"name": "hip-hop", "confidence": 0.42, "source": "audio_features"}
  ],
  "primary_genre": "funk",
  "primary_confidence": 0.8,
  "method": "discogs_audio_merged",
  "discogs_id": 123456,
  "discogs_labels_raw": ["Funk / Soul", "Boogie"]
}
```

示例 `dance_styles`：

```json
[
  {
    "style": "locking",
    "score": 0.82,
    "source": "v3",
    "breakdown": {
      "bpm": 0.96,
      "brass_likely": 0.8,
      "four_on_floor": 0.7
    }
  }
]
```

## 三、Genre Profile 实现方案

主入口：

```text
app/modules/library/genre_classifier.py::classify_genre
```

优先级：

```text
手动标签 > Spotify + Discogs + 本地音频特征合并 > 本地音频特征兜底
```

### 1. 手动标签

来源：

```text
app.modules.playlists.models.SongTag.style
```

调用位置：

```text
app/modules/library/background_tasks.py::_apply_genre_classification
```

如果存在手动 `style`，直接作为 `primary_genre`，置信度为 `1.0`，不会再用 Spotify / Discogs / 本地音频覆盖。

### 2. 本地音频特征推断

函数：

```text
app/modules/library/genre_classifier.py::_classify_from_features
```

输入：

- `bpm`
- `stem_activity`
- `groove_profile`
- `music_features["dj"]`
- `energy`

核心规则：

- BPM 区间：`GENRE_BPM_BANDS`
- stems 配比：`GENRE_STEM_PROFILES`
- spectral centroid、four-on-floor、sub bass、brass、groove、energy 等规则加权

它不依赖外部 API，是所有歌曲的兜底路径。

### 3. Spotify 元数据补全

函数：

```text
app/modules/library/genre_classifier.py::_enrich_from_spotify
```

环境变量：

```env
SPOTIPY_CLIENT_ID=
SPOTIPY_CLIENT_SECRET=
```

流程：

1. 按 `track:{title} artist:{artist}` 搜索 Spotify。
2. 读取 artist genres / album genres。
3. 使用 `_map_spotify_genres_to_dj()` 映射到内部 DJ taxonomy。

Spotify 适合补全艺人/专辑维度的 microgenre，但不一定精确到单曲。

### 4. Discogs 元数据补全

函数：

```text
app/modules/library/genre_classifier.py::_enrich_from_discogs
```

环境变量：

```env
DISCOGS_USER_TOKEN=
DISCOGS_USER_AGENT=HarBeat/1.0 +https://github.com/jihaobi123/harbeat-client
```

流程：

1. 调用 Discogs database search：

```http
GET https://api.discogs.com/database/search
```

参数：

- `type=release`
- `track={title}`
- `artist={artist}`
- `per_page=3`

2. 读取搜索结果里的 `genre` / `style`。
3. 再请求最佳 release：

```http
GET https://api.discogs.com/releases/{release_id}
```

4. 读取 release 详情里的 `genres` / `styles`。
5. 使用 `_map_discogs_labels_to_dj()` 映射到内部 DJ taxonomy。

Discogs 的优点是标签覆盖面很广，尤其适合 DJ crate 场景；缺点是标签是 release 级别，不一定等于单曲真实听感，所以目前置信度保守，作为 enrichment 而不是唯一判断。

### 5. 合并策略

函数：

```text
app/modules/library/genre_classifier.py::_merge_external_and_audio
```

逻辑：

1. 外部 metadata 的 genre 先进入候选。
2. 本地音频特征的 genre 作为补充，且 confidence 乘以 `0.7`。
3. 按 confidence 排序，最多保留前 5 个。
4. method 会记录来源，例如：

```text
spotify_audio_merged
discogs_audio_merged
spotify_discogs_audio_merged
audio_features
manual
```

## 四、Dance Style 实现方案

主入口：

```text
app/modules/dj_control/dance_style.py
```

刷新入口：

```text
app/modules/library/background_tasks.py::apply_dj_fingerprint
```

支持舞种：

- `breaking`
- `hiphop`
- `popping`
- `locking`
- `house`
- `krump`
- `waacking`

### 1. v3 加权指纹

优先使用：

```text
STYLE_FINGERPRINTS
score_song_for_style_v3()
```

输入来自：

```text
LibrarySong.music_features["dj"]
```

这些特征由：

```text
app/modules/library/dj_feature_extractor.py::extract_dj_features
```

生成。常见特征包括：

- `bpm`
- `beat_density`
- `four_on_floor`
- `groove_complexity`
- `bass_dominance`
- `sub_bass_score`
- `brass_likely`
- `drums_to_vocals_ratio`
- `spectral_centroid`
- `spectral_rolloff`
- `downbeat_consistency`
- `vocals_rms`

### 2. v1 兜底规则

如果没有 `music_features["dj"]`，使用：

```text
score_song_for_style()
```

只看：

- BPM
- energy
- beat density
- four-on-floor
- phrase bars

### 3. 输出

`apply_dj_fingerprint()` 会为每首歌计算全部舞种得分：

```python
song.dance_styles = ranked
song.dance_style_scores = scores
song.dance_style_status = "ready"
```

## 五、DJ Control 如何使用这些结果

### 1. 按舞种选歌

接口：

```http
GET /api/dj/styles
POST /api/dj/styles/pick
```

实现：

```text
app/modules/dj_control/router.py
app/modules/dj_control/dance_style.py
```

`/api/dj/styles/pick` 会按指定舞种调用：

```python
dance_style.pick_songs_for_duration(...)
```

本质是使用 `score_song_combined()` 的舞种适配分排序选歌。

### 2. 跨风格转场

实现：

```text
app/modules/dj_control/transition_strategy.py
```

它会读取歌曲的：

- `genre_profile.primary_genre`
- `dance_styles`
- BPM
- key / camelot
- energy
- vocal events
- phrase/downbeat
- stems availability

然后得到 `TransitionContext`，其中 `genreDistance` 会受 `genre_profile` 影响。也就是说 Discogs / Spotify 补全的 `genre_profile` 会间接影响跨风格转场策略选择。

## 六、如何修改或扩展

### 1. 修改 Discogs 标签映射

改这里：

```text
app/modules/library/genre_classifier.py::_DISCOGS_TO_DJ
```

例如想把 `UK Garage` 映射成 `house` 而不是 `breaks`，改这张表即可。

### 2. 修改 Spotify 标签映射

改这里：

```text
app/modules/library/genre_classifier.py::_SPOTIFY_TO_DJ
```

### 3. 修改本地流派判断规则

改这里：

```text
app/modules/library/genre_classifier.py::GENRE_BPM_BANDS
app/modules/library/genre_classifier.py::GENRE_STEM_PROFILES
app/modules/library/genre_classifier.py::_classify_from_features
```

### 4. 修改外部 metadata 和本地音频的权重

改这里：

```text
app/modules/library/genre_classifier.py::_merge_external_and_audio
```

当前音频补充项会乘以 `0.7`：

```python
confidence = audio_confidence * 0.7
```

如果你希望本地听感更重要，可以提高本地音频权重，或让外部 metadata 只作为候选不直接做 primary。

### 5. 修改街舞风格评分

改这里：

```text
app/modules/dj_control/dance_style.py::STYLE_FINGERPRINTS
```

例如要让 `locking` 更看重 brass/funk，可以提高 `brass_likely` 的权重；要让 `krump` 更偏 808，可以提高 `sub_bass_score` 权重。

### 6. 新增一个外部平台

推荐步骤：

1. 在 `genre_classifier.py` 新增 `_enrich_from_xxx(title, artist)`。
2. 输出统一结构：

```python
{
    "genres": [{"name": "house", "confidence": 0.75, "source": "xxx"}],
    "source": "xxx",
    "xxx_raw": [...]
}
```

3. 在 `classify_genre()` 里追加到 `external_results`。
4. 在 `_merge_external_and_audio()` 里保留需要写入 `genre_profile` 的 metadata。
5. 给 `app/tests/test_genre_classifier.py` 加映射和合并测试。

## 七、重新跑分析

配置 Discogs 后，已有歌曲不会自动补标签。需要重新跑分析或只补 genre。

可选方式：

1. 单曲重新分析：

```http
POST /api/library/songs/{song_id}/analyze
```

2. 用脚本批量 backfill 当前缺失/不完整分析：

```bash
python scripts/backfill_complete_analysis.py
```

如果后续只想重跑 `genre_profile`，建议新增一个轻量脚本，只调用 `_apply_genre_classification()`，避免重新跑 Demucs。

## 八、当前注意事项

- `GET /api/library/songs` 不返回完整风格字段；前端要展示完整分析请用 `GET /api/library/songs/{song_id}`。
- Discogs 需要 token；没有 `DISCOGS_USER_TOKEN` 时不会请求 Discogs。
- Spotify 需要 `SPOTIPY_CLIENT_ID` 和 `SPOTIPY_CLIENT_SECRET`；没有时自动跳过。
- 外部平台标签都是 metadata，不是实时音频听感。最终 DJ 转场仍应结合 BPM、beatgrid、key、stems、人声和低频风险。
- `genre_profile` 影响跨风格转场；`dance_styles` 影响按舞种选歌。后续改策略时要分清这两层。
