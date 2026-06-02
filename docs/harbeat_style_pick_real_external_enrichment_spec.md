# HarBeat DJ Control 舞种选歌多源评分真实落地执行规格

版本：V1.0  
日期：2026-06-02  
读者：后端工程师、Flutter 工程师、Jetson 部署工程师、AI Agent  
状态：可直接执行  
范围：只修改 **DJ Control「舞种 + 目标时长 → 生成候选歌曲」选歌准确率**，不修改 RK 播放、xfade、transition plan、stem 混音执行链路。

---

## 0. 文档用途

本文档用于指导 AI Agent 对当前 HarBeat 项目进行一次针对性代码修改：  
将现有 DJ Control 的舞种候选歌曲选择，从“主要依赖本地 v3 fingerprint 规则评分”，升级为“导入阶段真实调用外部音乐平台 API，并与本地分析结果统一融合评分”。

本次修改必须做到：

1. 外部平台 API 必须真实调用，不允许只保留 adapter / stub。
2. 外部平台数据必须在**歌曲导入 / 分析阶段**完成并保存。
3. DJ Control 点击“舞种 + 目标时长 → 生成候选”时，不再实时调用外部 API，而是读取已经保存的综合评分。
4. 外部数据、本地分析、人工标签、可调项进入同一套 `dance_style_scores`。
5. 必须补充 live API 测试与集成测试，证明模块真实有效。

本文档不处理：

- RK 播放问题。
- xfade schema。
- stem curves / eq curves。
- DJ Set 编排。
- Transition plan 生成。
- 音频 callback 实时执行。

---

## 1. 当前系统依据

当前项目中，DJ Control 舞种选择相关链路为：

```text
Flutter DJ Control
→ GET /api/dj/styles
→ POST /api/dj/styles/pick
→ 后端根据 dance_styles / dance_style_scores / energy / BPM 等字段选歌
```

关键代码位置：

```text
mobile/lib/src/dj_control_page.dart
mobile/lib/src/api_client.dart
app/modules/dj_control/router.py
app/modules/dj_control/dance_style.py
app/modules/library/genre_classifier.py
app/modules/library/background_tasks.py
app/modules/library/models.py
app/modules/library/schemas.py
```

当前核心数据表为 `library_songs`，其 `LibrarySong` 已经包含适合承接本次改造的字段：

```text
genre_profile
music_features
dance_styles
dance_style_scores
dance_style_status
groove_score
danceability_score
dancefloor_profile
energy
energy_curve
beat_confidence
tempo_stability
transition_windows
intro_clean_score
outro_clean_score
stem_quality_score
```

当前项目中也已有如下原则：后续接入 Discogs、Spotify、MusicBrainz 或自训练模型时，应写入 `genre_profile` 和 `dance_style_scores` 的来源与置信度，不要直接覆盖本地分析结果。

---

## 2. 本次修改目标

### 2.1 修改前

当前 `/api/dj/styles/pick` 的主要行为：

```text
用户选择 style + target_duration
→ 后端读取当前用户 LibrarySong
→ 使用本地 v3 fingerprint 或 v1 fallback 计算舞种分
→ min_score 过滤
→ BPM bucket 去重
→ 累计完整歌曲直到达到目标时长
→ 返回候选歌曲
```

当前问题：

1. 本地规则权重过高，容易把“音频特征像”但街舞实际不适合的歌曲推荐出来。
2. 外部音乐文化标签不足，例如 Funk / Boogie / Electro / Breakbeat / Disco / Soul 等信息不稳定。
3. 外部 API 如果只放在 `/styles/pick` 实时调用，会导致用户点击生成候选时变慢、不稳定、受限于网络和 API 额度。
4. 当前用户无法明确看到推荐分数来源。

---

### 2.2 修改后

改成：

```text
歌曲导入 / 分析阶段
→ 本地音频分析
→ 真实调用 MusicBrainz / Last.fm / Discogs
→ 归一化外部 genre / style / tags
→ 与本地 fingerprint、人工标签、可调项统一融合
→ 写入 genre_profile.style_evidence_v1
→ 同步写入 dance_style_scores / dance_styles / dance_style_status

DJ Control 选歌阶段
→ /api/dj/styles/pick 只读取已保存的 dance_style_scores
→ 不实时调用外部 API
→ 返回候选歌曲、综合分、评分来源、推荐理由
```

---

## 3. 权重方案

本次按用户指定权重执行：

```text
final_style_score =
0.50 × external_platform_score
+ 0.35 × local_fingerprint_score
+ 0.10 × manual_style_score
+ 0.05 × tunable_adjustment_score
```

### 3.1 各项含义

| 维度 | 权重 | 含义 |
|---|---:|---|
| `external_platform_score` | 50% | MusicBrainz / Last.fm / Discogs 等外部平台标签映射分 |
| `local_fingerprint_score` | 35% | 现有 v3 fingerprint 本地音频特征分 |
| `manual_style_score` | 10% | 人工标签、用户反馈、歌单标签修正 |
| `tunable_adjustment_score` | 5% | 可调策略项，如偏好、置信度、可混性、测试阶段手动校准 |

### 3.2 外部平台内部权重

第一阶段真实接入三个外部平台：

```text
external_platform_score =
0.45 × discogs_score
+ 0.35 × lastfm_score
+ 0.20 × musicbrainz_score
```

原因：

- Discogs 对 genre / style 更有价值，尤其适合 Funk、Boogie、Electro、Disco、Soul、Breakbeat 等街舞相关曲风。
- Last.fm 用户标签能补充 funky、old school、b-boy、dance、hip-hop 等民间语义。
- MusicBrainz 主要用于歌曲身份对齐、基础 tags / genres 补充，权重低于 Discogs 和 Last.fm。

如果某个外部平台没有命中，不得直接把该项记为 0 拉低总分；应对可用平台权重做动态归一化。

示例：

```text
如果 Discogs 和 Last.fm 有结果，MusicBrainz 无结果：

external_platform_score =
(0.45 × discogs_score + 0.35 × lastfm_score) / (0.45 + 0.35)
```

---

## 4. 外部 API 接入要求

### 4.1 必须真实接入的 API

#### 4.1.1 MusicBrainz

用途：

```text
歌曲身份对齐
recording / artist / release metadata
genres / tags
MBID
```

建议请求：

```http
GET https://musicbrainz.org/ws/2/recording?query=recording:"{title}" AND artist:"{artist}"&fmt=json
```

如果命中 MBID，再尝试 lookup：

```http
GET https://musicbrainz.org/ws/2/recording/{mbid}?inc=artist-credits+releases+genres+tags&fmt=json
```

要求：

- 必须设置规范 User-Agent。
- 不允许高频无节制请求。
- 请求失败不得阻塞本地分析。
- 命中结果需要保存 `mbid`、`score`、`tags`、`genres`、`matched_title`、`matched_artist`。

环境变量：

```text
MUSICBRAINZ_APP_NAME=HarBeat
MUSICBRAINZ_CONTACT_EMAIL=your_email@example.com
```

---

#### 4.1.2 Last.fm

用途：

```text
track top tags
artist top tags fallback
用户众包标签
```

请求：

```http
GET https://ws.audioscrobbler.com/2.0/?method=track.getTopTags&artist={artist}&track={title}&api_key={LASTFM_API_KEY}&format=json&autocorrect=1
```

如果 track 级别没有 tags，再 fallback：

```http
GET https://ws.audioscrobbler.com/2.0/?method=artist.getTopTags&artist={artist}&api_key={LASTFM_API_KEY}&format=json&autocorrect=1
```

环境变量：

```text
LASTFM_API_KEY=...
```

保存内容：

```text
track_tags[]
artist_tags[]
raw_count
status
matched_artist
matched_track
```

---

#### 4.1.3 Discogs

用途：

```text
release genre
release style
artist / release metadata
街舞相关子风格补强
```

请求流程：

```http
GET https://api.discogs.com/database/search?q={artist}+{title}&type=release&token={DISCOGS_USER_TOKEN}
```

选择 top result 后：

```http
GET https://api.discogs.com/releases/{release_id}
```

保存内容：

```text
release_id
title
artist
genres[]
styles[]
year
status
```

环境变量：

```text
DISCOGS_USER_TOKEN=...
```

注意：

- 不要把 Discogs 的 genre/style 直接覆盖本地 genre。
- 只写入 `genre_profile.sources.discogs`。
- 如果搜索结果置信度低，要标记 `needs_review=true`。

---

## 5. 标签归一化与舞种映射

### 5.1 新增标准标签归一化

新增模块：

```text
app/modules/library/external_metadata/normalizer.py
```

职责：

```text
Hip Hop / hip-hop / rap → hiphop
old school hip hop / old skool → hiphop_oldschool
funky / funk → funk
electro funk / electro-funk → electro_funk
r&b / rhythm and blues → rnb
boogie funk → boogie
g funk / g-funk → g_funk
```

输出统一小写 snake_case 标签。

---

### 5.2 舞种标签画像

新增或集中维护：

```text
app/modules/dj_control/style_taxonomy.py
```

第一版支持 7 个现有舞种：

```text
breaking
hiphop
popping
locking
house
krump
waacking
```

示例：

```python
STYLE_TAG_PROFILE = {
    "popping": {
        "strong": ["funk", "electro", "boogie", "electro_funk", "g_funk"],
        "medium": ["hiphop_oldschool", "synth_funk", "groovy", "west_coast"],
        "negative": ["ambient", "acoustic", "ballad"]
    },
    "locking": {
        "strong": ["funk", "soul", "disco", "jazz_funk"],
        "medium": ["groovy", "dance", "old_school", "bright"],
        "negative": ["trap", "ambient", "ballad"]
    },
    "breaking": {
        "strong": ["breakbeat", "hiphop_oldschool", "funk", "boom_bap"],
        "medium": ["electro", "latin_funk", "drum_breaks", "raw"],
        "negative": ["ambient", "ballad", "acoustic"]
    },
    "house": {
        "strong": ["house", "deep_house", "garage_house", "jackin_house"],
        "medium": ["dance", "club", "percussive", "soulful_house"],
        "negative": ["ballad", "ambient"]
    },
    "waacking": {
        "strong": ["disco", "funk", "soul", "vocal_house"],
        "medium": ["dance", "glamorous", "dramatic", "bright"],
        "negative": ["trap", "ambient", "minimal"]
    },
    "krump": {
        "strong": ["krump", "trap", "aggressive_hiphop", "battle_rap"],
        "medium": ["dark", "heavy_bass", "hard_hitting", "urban"],
        "negative": ["soft_pop", "acoustic", "ambient"]
    },
    "hiphop": {
        "strong": ["hiphop", "boom_bap", "rap", "rnb", "trap_soul"],
        "medium": ["urban", "groovy", "pop_rap", "old_school"],
        "negative": ["ambient", "classical"]
    }
}
```

---

### 5.3 外部平台标签评分

新增：

```text
app/modules/library/external_metadata/scorer.py
```

核心函数：

```python
score_external_tags_for_style(
    normalized_tags: list[str],
    style: str,
    source_confidence: float = 1.0,
) -> float
```

建议规则：

```text
strong tag 命中：+0.30
medium tag 命中：+0.15
negative tag 命中：-0.25
同一标签重复来源：增加置信度，不重复无限加分
最终 clamp 到 0.0 - 1.0
```

每个平台单独算分：

```text
discogs_score
lastfm_score
musicbrainz_score
```

再融合为 `external_platform_score`。

---

## 6. 数据结构要求

优先复用 `LibrarySong.genre_profile`，避免强制新增数据库字段。  
如果项目已有 JSON 字段能力足够，本次不强制做 migration。

### 6.1 写入 `genre_profile`

结构：

```json
{
  "sources": {
    "local": {
      "labels": ["funk", "groovy"],
      "confidence": 0.82,
      "version": "v3"
    },
    "discogs": {
      "status": "hit",
      "labels": ["funk", "electro", "boogie"],
      "raw": {
        "release_id": 123,
        "genres": ["Funk / Soul"],
        "styles": ["Electro", "Boogie"]
      },
      "confidence": 0.80,
      "fetched_at": "2026-06-02T00:00:00Z"
    },
    "lastfm": {
      "status": "hit",
      "labels": ["funky", "old_school", "electro"],
      "confidence": 0.75,
      "fetched_at": "2026-06-02T00:00:00Z"
    },
    "musicbrainz": {
      "status": "hit",
      "mbid": "xxx",
      "labels": ["funk", "electro_funk"],
      "confidence": 0.70,
      "fetched_at": "2026-06-02T00:00:00Z"
    }
  },
  "style_evidence_v1": {
    "popping": {
      "external_platform_score": 0.86,
      "local_fingerprint_score": 0.74,
      "manual_style_score": 0.0,
      "tunable_adjustment_score": 0.70,
      "final_score": 0.77,
      "confidence": 0.82,
      "status": "ready",
      "weights": {
        "external": 0.50,
        "local": 0.35,
        "manual": 0.10,
        "tunable": 0.05
      },
      "reason": [
        "Discogs 命中 funk / electro / boogie",
        "Last.fm 命中 funky / old_school",
        "本地 fingerprint 显示 groove 和 BPM 接近 popping"
      ]
    }
  }
}
```

### 6.2 同步写入旧字段

为了兼容现有 DJ Control，不改变前端主链路：

```text
LibrarySong.dance_style_scores = {
  "popping": 0.77,
  "locking": 0.61,
  "breaking": 0.42
}

LibrarySong.dance_styles = ["popping", "locking", "breaking"]

LibrarySong.dance_style_status = "ready"
```

如果外部平台失败但本地分析成功：

```text
dance_style_status = "partial"
```

如果本地和外部都失败：

```text
dance_style_status = "needs_review"
```

---

## 7. 导入 / 分析阶段调用位置

### 7.1 新增外部 metadata 包

新增目录：

```text
app/modules/library/external_metadata/
  __init__.py
  clients.py
  musicbrainz_client.py
  lastfm_client.py
  discogs_client.py
  normalizer.py
  scorer.py
  service.py
  schemas.py
```

### 7.2 核心服务函数

```python
async def enrich_song_external_metadata(
    db: Session,
    song: LibrarySong,
    *,
    force: bool = False,
    timeout_sec: float = 8.0,
) -> ExternalEnrichmentResult:
    ...
```

职责：

1. 根据 `song.title`、`song.artist`、`song.platform_id`、`song.platform_url` 构造查询。
2. 并发调用 MusicBrainz / Last.fm / Discogs。
3. 对返回 tags / genres / styles 做归一化。
4. 计算各舞种 `external_platform_score`。
5. 调用本地 `dance_style.py` 中已有 v3 fingerprint 分数。
6. 读取 manual tags / song_tags / user feedback，生成 `manual_style_score`。
7. 生成 `tunable_adjustment_score`。
8. 计算 `final_score`。
9. 写入 `genre_profile.style_evidence_v1`、`dance_style_scores`、`dance_styles`、`dance_style_status`。
10. commit 或由调用方统一 commit。

### 7.3 挂入现有导入分析流程

必须在以下入口接入：

```text
app/modules/library/background_tasks.py
app/modules/library/analysis.py
app/modules/fangpi/router.py
```

典型流程：

```text
上传 / fangpi 下载
→ LibrarySong 入库
→ 本地 analyze
→ 本地 genre_classifier
→ external_metadata_enrichment
→ write dance_style_scores
```

注意：

- 外部 API 失败不得导致歌曲导入失败。
- 外部 API 超时不得阻塞整个分析队列超过配置阈值。
- 如果缺少 API key，必须标记 source.status = "disabled"，不能假装 hit。
- 所有调用必须写日志，但不得打印 token。

---

## 8. `/api/dj/styles/pick` 修改要求

### 8.1 不再调用外部 API

`POST /api/dj/styles/pick` 只读取已保存的 `dance_style_scores` 和 `genre_profile.style_evidence_v1`。

不得在该接口里请求：

```text
MusicBrainz
Last.fm
Discogs
Cyanite
Bridge
AIMS
```

原因：

- 保证现场 DJ Control 选歌速度。
- 避免外部 API 抖动影响用户点击。
- 避免每次生成候选都重复消耗 API 额度。

### 8.2 返回新增解释字段

保持旧字段兼容，同时新增：

```json
{
  "final_pick_score": 0.77,
  "score_breakdown": {
    "external_platform_score": 0.86,
    "local_fingerprint_score": 0.74,
    "manual_style_score": 0.0,
    "tunable_adjustment_score": 0.70
  },
  "style_evidence_status": "ready",
  "external_sources": {
    "discogs": {"status": "hit", "labels": ["funk", "electro", "boogie"]},
    "lastfm": {"status": "hit", "labels": ["funky", "old_school"]},
    "musicbrainz": {"status": "hit", "labels": ["funk", "electro_funk"]}
  },
  "reason": [
    "Discogs 命中 funk / electro / boogie",
    "本地 fingerprint 显示 BPM 和 groove 接近 popping"
  ]
}
```

---

## 9. 后台刷新与补数据

### 9.1 新增单曲刷新接口

新增后端接口：

```http
POST /api/library/songs/{song_id}/refresh-style-evidence
```

请求：

```json
{
  "force": true
}
```

作用：

```text
对单首歌重新调用外部 API
重算 style_evidence_v1
重写 dance_style_scores
```

仅用于调试、曲库详情页或管理员手动刷新。

### 9.2 新增批量回填脚本

新增：

```text
scripts/backfill_style_evidence.py
```

用法：

```bash
python scripts/backfill_style_evidence.py --limit 50
python scripts/backfill_style_evidence.py --force --user-id <uuid>
python scripts/backfill_style_evidence.py --only-missing
```

要求：

- 支持断点。
- 支持 limit。
- 支持 only-missing。
- 不打印 token。
- 输出每首歌的 source status 和 final score。

---

## 10. 配置项

在 `app/shared/config.py` 和 `.env.example` 中补充：

```text
ENABLE_EXTERNAL_STYLE_ENRICHMENT=true
EXTERNAL_STYLE_CACHE_TTL_DAYS=30
EXTERNAL_STYLE_TIMEOUT_SEC=8
EXTERNAL_STYLE_MAX_CONCURRENCY=3

LASTFM_API_KEY=
DISCOGS_USER_TOKEN=
MUSICBRAINZ_APP_NAME=HarBeat
MUSICBRAINZ_CONTACT_EMAIL=

STYLE_SCORE_WEIGHT_EXTERNAL=0.50
STYLE_SCORE_WEIGHT_LOCAL=0.35
STYLE_SCORE_WEIGHT_MANUAL=0.10
STYLE_SCORE_WEIGHT_TUNABLE=0.05

STYLE_EXTERNAL_WEIGHT_DISCOGS=0.45
STYLE_EXTERNAL_WEIGHT_LASTFM=0.35
STYLE_EXTERNAL_WEIGHT_MUSICBRAINZ=0.20
```

要求：

- 权重总和必须校验。
- 缺省权重按本文档执行。
- 如果总和不等于 1.0，启动时 warning，并在计算时自动归一化。
- 生产日志不得输出 API token。

---

## 11. Flutter 修改要求

Flutter 不负责外部 API 调用，只展示结果。

涉及文件：

```text
mobile/lib/src/dj_control_page.dart
mobile/lib/src/api_client.dart
mobile/lib/src/models.dart
```

### 11.1 保持现有操作

用户仍然：

```text
进入 DJ Control
→ 选择舞种
→ 选择目标时长
→ 点击生成候选
→ 加入 DJ 池
```

### 11.2 新增展示

候选歌曲卡片新增：

```text
推荐指数：77%
多源状态：ready / partial / local_only / needs_review
主要原因：
- Discogs 命中 funk / electro / boogie
- 本地 groove / BPM 接近 popping
```

如果外部 API 未完成：

```text
多源分析未完成，当前使用本地评分
```

---

## 12. 测试要求

本次修改必须补充测试。  
测试分为 mock 单元测试、真实外部 API 冒烟测试、导入阶段集成测试、DJ Control 选歌测试。

---

### 12.1 Mock 单元测试

新增：

```text
app/tests/test_external_metadata_normalizer.py
app/tests/test_external_metadata_scorer.py
app/tests/test_style_score_fusion.py
```

必须测试：

1. `Hip Hop / hip-hop / rap` 能统一成 `hiphop`。
2. `electro funk / electro-funk` 能统一成 `electro_funk`。
3. Popping 命中 `funk/electro/boogie` 时 external score 明显高。
4. Negative tag 命中时分数下降。
5. 权重 50/35/10/5 计算正确。
6. 某一外部来源缺失时，external 内部权重动态归一化。
7. 所有分数 clamp 在 `0.0 - 1.0`。

运行：

```bash
python -m pytest app/tests/test_external_metadata_normalizer.py -q
python -m pytest app/tests/test_external_metadata_scorer.py -q
python -m pytest app/tests/test_style_score_fusion.py -q
```

---

### 12.2 真实外部 API 冒烟测试

新增：

```text
app/tests/test_external_metadata_live.py
```

该测试默认跳过，只有设置以下变量时运行：

```bash
RUN_LIVE_EXTERNAL_API_TESTS=1
LASTFM_API_KEY=...
DISCOGS_USER_TOKEN=...
MUSICBRAINZ_APP_NAME=HarBeat
MUSICBRAINZ_CONTACT_EMAIL=...
```

测试歌曲：

```text
Zapp - More Bounce To The Ounce
James Brown - Get Up Offa That Thing
Afrika Bambaataa - Planet Rock
```

测试要求：

1. MusicBrainz 至少返回 recording 或明确返回 miss，不得异常崩溃。
2. Last.fm `track.getTopTags` 至少对一首歌返回 tags。
3. Discogs search + release lookup 至少对一首歌返回 genre 或 style。
4. 测试输出必须包含：
   ```text
   source
   status
   labels
   raw_id / mbid / release_id
   ```
5. 如果缺 API key，测试必须 fail 或 skip with explicit reason，不允许假装成功。
6. 不允许使用 mock 替代 live API。

运行：

```bash
RUN_LIVE_EXTERNAL_API_TESTS=1 python -m pytest app/tests/test_external_metadata_live.py -q -s
```

---

### 12.3 导入阶段集成测试

新增：

```text
app/tests/test_style_enrichment_pipeline.py
```

使用 mock adapter 模拟外部返回，但要验证流程写库。

测试要求：

1. 创建一首 `LibrarySong`。
2. mock Discogs 返回 `["Funk", "Electro", "Boogie"]`。
3. mock Last.fm 返回 `["funky", "old school"]`。
4. mock MusicBrainz 返回 `["electro-funk"]`。
5. 调用 `enrich_song_external_metadata()`。
6. 验证：
   ```text
   genre_profile.sources.discogs.status == "hit"
   genre_profile.sources.lastfm.status == "hit"
   genre_profile.sources.musicbrainz.status == "hit"
   genre_profile.style_evidence_v1.popping.external_platform_score > 0.7
   dance_style_scores["popping"] > 0.6
   dance_style_status in ["ready", "partial"]
   ```

---

### 12.4 `/api/dj/styles/pick` 集成测试

新增：

```text
app/tests/test_dj_style_pick_multisource.py
```

测试要求：

1. 准备 5 首歌，其中 3 首 `dance_style_scores.popping` 高。
2. 调用：
   ```json
   {
     "style": "popping",
     "target_duration_sec": 600,
     "min_score": 0.35
   }
   ```
3. 验证返回候选中优先包含高分歌曲。
4. 验证返回包含：
   ```text
   final_pick_score
   score_breakdown
   external_sources
   reason
   style_evidence_status
   ```
5. 验证 `/styles/pick` 中没有调用 external client。  
   可通过 monkeypatch external clients，如果被调用则测试失败。

---

### 12.5 回填脚本测试

新增：

```text
app/tests/test_backfill_style_evidence.py
```

测试要求：

1. `--only-missing` 只处理缺少 `style_evidence_v1` 的歌曲。
2. `--limit 2` 只处理 2 首。
3. `--force` 会重新计算已有结果。
4. API key 缺失时不崩溃，标记 source disabled。

---

## 13. 验收标准

本轮完成必须满足：

- [ ] `app/modules/library/external_metadata/` 已新增真实 client、normalizer、scorer、service。
- [ ] MusicBrainz / Last.fm / Discogs 至少三个 client 中，Last.fm 和 Discogs 必须在配置 key 后真实调用。
- [ ] MusicBrainz 必须设置 User-Agent 并能真实请求。
- [ ] 歌曲导入或分析阶段会触发 external enrichment。
- [ ] 外部结果写入 `genre_profile.sources`。
- [ ] 综合评分写入 `genre_profile.style_evidence_v1`。
- [ ] `dance_style_scores` 使用 50% 外部、35% 本地、10% 人工、5% 可调融合结果。
- [ ] `/api/dj/styles/pick` 不实时调用外部 API，只读取保存结果。
- [ ] `/api/dj/styles/pick` 返回 score breakdown、external sources、reason。
- [ ] 缺少 API key 时系统能降级到本地分数，不影响歌曲导入。
- [ ] live API 测试能证明至少一个真实外部 API 返回 tags / genre / style。
- [ ] mock 单元测试、pipeline 测试、styles/pick 集成测试全部通过。
- [ ] `.env.example` 已补充配置项，但没有提交真实 API key。
- [ ] 日志不输出 token、JWT、设备密钥。

---

## 14. 推荐提交顺序

每个阶段单独提交，不要全部塞进一个 commit。

### Phase 0：建立测试基线

```text
chore(style-pick): establish current test baseline
```

任务：

- 跑现有后端测试。
- 确认当前 `/api/dj/styles/pick` 行为。
- 检查 `.env` 不包含需要提交的真实 token。

---

### Phase 1：新增外部 metadata 模块

```text
feat(style-pick): add real external metadata clients
```

任务：

- 新增 MusicBrainz / Last.fm / Discogs client。
- 新增 normalizer。
- 新增 live API smoke test。
- 配置 `.env.example`。

---

### Phase 2：新增多源评分融合

```text
feat(style-pick): fuse external local manual and tunable scores
```

任务：

- 新增 external scorer。
- 新增 final score fusion。
- 权重 50/35/10/5 可配置。
- 单元测试覆盖计算。

---

### Phase 3：接入导入 / 分析流程

```text
feat(library): enrich dance style evidence during song analysis
```

任务：

- 在导入/分析阶段调用 `enrich_song_external_metadata()`。
- 写入 `genre_profile.sources`、`style_evidence_v1`、`dance_style_scores`。
- 外部失败时 graceful fallback。

---

### Phase 4：修改 `/styles/pick`

```text
feat(dj-control): use persisted multisource style evidence for picking
```

任务：

- `/styles/pick` 读取保存结果。
- 不再实时调用 external clients。
- 返回 score breakdown、external sources、reason。
- 集成测试确保 external clients 不被调用。

---

### Phase 5：补回填脚本和前端展示

```text
feat(style-pick): add backfill script and evidence display
```

任务：

- 新增 `scripts/backfill_style_evidence.py`。
- Flutter 候选卡片展示多源状态与推荐原因。
- 不在 Flutter 中调用外部 API。

---

## 15. 交接给 AI Agent 的执行提示

```text
请阅读本文档并只修改 DJ Control 舞种选歌准确率相关代码。
本轮目标不是改 RK、xfade、transition plan、stem 混音或自动 Set 编排。
必须真实接入 MusicBrainz、Last.fm、Discogs 外部 API，并在歌曲导入/分析阶段调用。
不得只写 adapter/stub。
不得在 /api/dj/styles/pick 中实时调用外部 API。
/styles/pick 只读取已保存的 genre_profile.style_evidence_v1 和 dance_style_scores。
最终分数权重固定为：外部 50%，本地 35%，人工 10%，可调 5%，并支持配置。
必须补充 live API 冒烟测试，证明真实外部 API 返回了 tags/genre/style。
必须补充 mock 单元测试和 /styles/pick 集成测试。
不要提交真实 API key、JWT、token、设备密钥或 .env。
每完成一个 Phase，运行对应测试并报告结果。
```
