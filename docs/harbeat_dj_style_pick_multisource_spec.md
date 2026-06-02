# HarBeat DJ Control 舞种选歌多源评分改造执行规格

版本：V1.0  
日期：2026-06-02  
读者：后端工程师、Flutter 工程师、AI Agent  
状态：可直接执行  
范围：只修改 DJ Control 的“舞种 + 目标时长 → 生成候选歌曲”选歌准确率；不修改 RK 播放、xfade、transition plan、DJ Set 编排和混音执行。

---

## 0. 文档用途

本文档用于指导 AI Agent 对 HarBeat 当前项目的 DJ Control 选歌模块进行针对性修改。

本轮只处理一件事：

```text
提升 /api/dj/styles/pick 的舞种选歌准确率
```

当前功能已经可以完成：

```text
用户选择舞种 + 目标时长
→ 后端从当前曲库中选择候选歌曲
→ 返回候选歌曲列表
→ 前端加入 DJ 池
```

但当前选歌主要依赖 v3 fingerprint 规则评分。本轮目标是把它升级为：

```text
v3 fingerprint
+ 多平台标签证据
+ 舞种参考曲库相似度
+ 人工反馈修正
+ DJ 可用性分
= final_pick_score
```

不要把本轮改造成完整 DJ Set 编排，也不要改 RK 播放链路。

---

## 1. 当前接口与功能边界

### 1.1 前端调用

前端入口：

```text
mobile/lib/src/dj_control_page.dart
mobile/lib/src/api_client.dart
```

当前用户操作：

```text
打开 DJ Control
→ GET /api/dj/styles
→ 用户选择舞种和目标分钟数
→ POST /api/dj/styles/pick
→ 返回候选歌曲
→ 前端加入 _picked 歌池
```

当前请求参数保持不变：

```json
{
  "style": "hiphop",
  "target_duration_sec": 600,
  "min_score": 0.35
}
```

本轮不得破坏该请求结构。

---

### 1.2 后端入口

后端入口：

```text
app/modules/dj_control/router.py
POST /api/dj/styles/pick
```

当前职责：

```text
校验 style
→ 读取当前用户 LibrarySong
→ 调用 dance_style.pick_songs_for_duration(...)
→ 返回候选歌曲、分数、BPM、时长、能量
```

本轮保持该职责不变。

不要在 `/styles/pick` 中做：

```text
DJ Set 编排
transition plan
RK prefetch
RK xfade
混音策略选择
```

---

### 1.3 支持舞种

当前固定支持：

```text
breaking
hiphop
popping
locking
house
krump
waacking
```

本轮不要新增舞种，避免扩大测试范围。

---

## 2. 当前问题

### 2.1 过度依赖规则特征

当前主路径主要依赖 v3 fingerprint：

```text
bpm
beat_density
four_on_floor
groove_complexity
bass_dominance
sub_bass_score
brass_likely
drums_to_vocals_ratio
spectral_centroid
energy
```

这些特征可以判断“歌曲音频结构像不像某个舞种”，但不一定能判断：

```text
歌曲在街舞文化语境中是否真的适合该舞种
舞者是否真的会接受
外部音乐平台是否把它归为相关风格
这首歌是否与该舞种代表曲库相似
这首歌是否适合进入 DJ 池
```

---

### 2.2 缺少多源证据

当前风格分析已经有规则和 metadata 基础，但 `/styles/pick` 仍应进一步融合：

```text
本地 fingerprint
外部平台 genre/style/tag
舞种参考曲库相似度
人工反馈
mixability
```

---

### 2.3 目标时长逻辑缺少多样性

当前目标时长逻辑主要是：

```text
按分数排序
→ 过滤 min_score
→ BPM bucket 去重
→ 累计歌曲时长直到 >= target_duration_sec
→ 不够再放宽 BPM bucket
```

这能凑够时长，但可能出现：

```text
同一 BPM 段歌曲过多
同一艺人过多
同一子风格过多
能量变化不明显
候选歌虽然适合舞种但不适合后续混音
```

---

## 3. 改造目标

### 3.1 总目标

将 `/api/dj/styles/pick` 从：

```text
单一 fingerprint 规则评分
```

升级为：

```text
多源证据融合评分
```

最终返回的候选歌曲应更准确、更稳定、更可解释。

---

### 3.2 不做的事情

本轮不要做：

```text
不要修改 RK audio-engine
不要修改 /xfade schema
不要修改 transition_strategy.py 的混音策略
不要训练大型模型
不要让 /styles/pick 实时调用外部 API
不要让外部 API 失败阻塞用户选歌
不要把 App 改成专业 DJ 台
不要提交 token、JWT、API key、.env
```

---

## 4. 新评分方案

### 4.1 最终分数

新增统一评分：

```text
final_pick_score =
0.35 × fingerprint_score
+ 0.25 × platform_tag_score
+ 0.20 × reference_similarity_score
+ 0.10 × manual_feedback_score
+ 0.10 × mixability_score
```

如果某些维度缺失，必须动态归一化：

```text
final_score = available_weighted_sum / available_weight_sum
```

示例：如果没有 reference_similarity_score：

```text
final_score =
(0.35 × fingerprint
+ 0.25 × platform_tag
+ 0.10 × manual_feedback
+ 0.10 × mixability) / 0.80
```

不得因为某个平台没有结果导致整首歌无法参与推荐。

---

### 4.2 维度 1：fingerprint_score

保留当前 v3 fingerprint 逻辑。

实现要求：

```text
如果 song.music_features["dj"] 存在：
    使用 v3 fingerprint
否则：
    fallback 到 v1 老规则
```

位置：

```text
app/modules/dj_control/dance_style.py
```

要求：

```text
不要删除现有 v3/v1 逻辑
把当前规则分数包装成 fingerprint_score
返回 score、confidence、version、matched_features
```

建议输出：

```json
{
  "score": 0.76,
  "confidence": 0.82,
  "version": "v3",
  "matched_features": ["bpm", "groove_complexity", "bass_dominance"]
}
```

---

### 4.3 维度 2：platform_tag_score

新增平台标签证据。

数据来源优先级：

```text
第一阶段：Discogs / Last.fm / MusicBrainz
第二阶段：Cyanite / Bridge.audio / AIMS
```

本轮实现要求：

```text
先设计可扩展 adapter 接口
允许没有 API key 时跳过
不要在 /styles/pick 请求中实时请求外部平台
外部结果应在导入、分析、刷新 metadata 时写入 genre_profile
```

建议模块：

```text
app/modules/library/metadata_adapters/
  __init__.py
  base.py
  discogs_adapter.py
  lastfm_adapter.py
  musicbrainz_adapter.py
  cyanite_adapter.py       # 可先留 stub
  bridge_adapter.py        # 可先留 stub
  aims_adapter.py          # 可先留 stub
```

统一 adapter 输出：

```json
{
  "source": "discogs",
  "labels": ["electro", "boogie", "funk"],
  "label_type": "genre_style",
  "confidence": 0.75,
  "raw": {}
}
```

写入位置：

```text
LibrarySong.genre_profile["sources"]
```

平台标签映射到舞种：

```text
popping:
  strong: electro, boogie, funk, electro funk, g-funk, synth funk
  medium: old school, groovy, robotic, west coast

locking:
  strong: funk, soul, disco, jazz funk
  medium: upbeat, funky, old school, dance

breaking:
  strong: breakbeat, old school hip-hop, boom bap, funk breaks, b-boy
  medium: hip hop, electro, raw, drum breaks

house:
  strong: house, deep house, garage house, jackin house, soulful house
  medium: club, dance, 4/4, percussive

waacking:
  strong: disco, funk, soul, vocal house, diva vocal
  medium: dramatic, glamorous, dance, vocal

krump:
  strong: krump, aggressive hip-hop, trap, battle beats, hard rap
  medium: dark, heavy bass, high energy, urban

hiphop:
  strong: hip hop, boom bap, rap, old school hip-hop, r&b
  medium: urban, groove, vocal, street
```

建议实现：

```text
compute_platform_tag_score(style, genre_profile) -> score evidence
```

位置：

```text
app/modules/dj_control/dance_style.py
```

---

### 4.4 维度 3：reference_similarity_score

新增“舞种参考曲库相似度”。

目的：

```text
解决标签正确但舞者感觉不对的问题
```

每个舞种建立参考曲库配置，不要求本轮一定接外部 similarity API。

第一阶段可以用静态配置 + 标签相似度近似：

```text
app/modules/dj_control/style_reference_profiles.py
```

示例：

```python
STYLE_REFERENCE_PROFILES = {
    "popping": {
        "reference_tags": ["electro", "boogie", "funk", "g-funk", "synth funk"],
        "reference_artists": ["Zapp", "Egyptian Lover"],
        "description": "Electro funk / boogie / g-funk oriented popping music"
    }
}
```

第二阶段再接：

```text
Cyanite similarity
AIMS similarity
自建 embedding
```

本轮函数接口先固定：

```text
compute_reference_similarity_score(style, song, evidence) -> score evidence
```

输出：

```json
{
  "score": 0.81,
  "confidence": 0.70,
  "method": "tag_reference_profile_v1",
  "matched_refs": ["electro", "boogie", "funk"]
}
```

如果没有相似度数据：

```text
score = null
available = false
```

不得强行返回 0。

---

### 4.5 维度 4：manual_feedback_score

新增人工反馈证据，但第一阶段不强制做复杂 UI。

优先复用现有人工标签能力：

```text
song_tags
dance_styles
manual_tags
```

如果当前没有稳定结构，可新增最小表：

```text
song_style_feedback
```

建议字段：

```text
id
user_id
library_song_id
style
feedback_type       # suitable | unsuitable | better_as
target_style        # better_as 时使用
weight
created_at
updated_at
```

第一版规则：

```text
suitable:
  manual_feedback_score = 0.90

unsuitable:
  manual_feedback_score = 0.10

better_as:
  当前 style = 0.20
  target_style = 0.90
```

如果没有人工反馈：

```text
manual_feedback_score = null
available = false
```

不要让缺失人工反馈降低歌曲得分。

---

### 4.6 维度 5：mixability_score

新增 DJ 可用性分，但只占 10%。

目的：

```text
避免推荐出舞种很像但后续难接的歌
```

使用现有字段：

```text
beat_confidence
tempo_stability
transition_windows
intro_clean_score
outro_clean_score
stem_quality_score
duration
analysis_status
```

建议规则：

```text
beat_confidence 高：加分
tempo_stability 高：加分
transition_windows 非空：加分
intro/outro clean score 高：加分
stem_quality_score 高：小幅加分
analysis_status 未完成：降分
duration 过短或过长：小幅降分
```

---

## 5. 数据结构设计

### 5.1 推荐存储位置

优先不新增数据库字段，先复用：

```text
LibrarySong.genre_profile
LibrarySong.dance_style_scores
```

在 `genre_profile` 中新增：

```text
style_evidence
```

示例：

```json
{
  "sources": {
    "discogs": {
      "labels": ["electro", "boogie", "funk"],
      "confidence": 0.75
    },
    "lastfm": {
      "labels": ["funky", "old school"],
      "confidence": 0.62
    }
  },
  "style_evidence": {
    "popping": {
      "fingerprint": {"score": 0.76, "confidence": 0.82, "version": "v3"},
      "platform_tags": {"score": 0.84, "confidence": 0.75, "matched_labels": ["electro", "boogie", "funk"]},
      "reference_similarity": {"score": 0.81, "confidence": 0.70, "method": "tag_reference_profile_v1"},
      "manual_feedback": {"score": null, "available": false},
      "mixability": {"score": 0.73, "confidence": 0.80},
      "final_pick_score": 0.79,
      "confidence": 0.78,
      "version": "style_picker_multisource_v1"
    }
  }
}
```

同时写回兼容字段：

```text
dance_style_scores["popping"] = final_pick_score
dance_styles 包含 final_pick_score >= threshold 的舞种
dance_style_status = "completed" 或 "partial"
```

---

### 5.2 是否需要 migration

第一阶段不强制 migration。

允许：

```text
只修改 JSON 字段内容
不新增列
```

如果要做人工反馈表，则需要 migration 或项目现有建表方式。

---

## 6. 后端改造任务

## 6.1 新增证据计算函数

文件：

```text
app/modules/dj_control/dance_style.py
```

新增函数：

```python
def score_song_multisource(style: str, song: LibrarySong) -> dict:
    ...
```

输出：

```json
{
  "style": "popping",
  "final_pick_score": 0.79,
  "confidence": 0.78,
  "components": {
    "fingerprint": {},
    "platform_tags": {},
    "reference_similarity": {},
    "manual_feedback": {},
    "mixability": {}
  },
  "reason": [
    "BPM/groove matches popping fingerprint",
    "Discogs/Last.fm labels matched electro, boogie, funk",
    "Reference profile matched electro funk tags",
    "Beat confidence and transition windows are usable"
  ]
}
```

要求：

```text
score_song_multisource 必须复用现有 v3/v1 评分，不要重写旧逻辑。
外部 API 缺失时不得抛异常。
所有分数必须 clamp 到 0.0 - 1.0。
```

---

## 6.2 修改 pick_songs_for_duration

文件：

```text
app/modules/dj_control/dance_style.py
```

新逻辑：

```text
1. 对每首 LibrarySong 调用 score_song_multisource(style, song)
2. 得到 final_pick_score
3. 过滤 final_pick_score < min_score
4. 按 final_pick_score 降序
5. 第一轮选择时做多样性约束
6. 累计完整歌曲时长直到 >= target_duration_sec
7. 不够时第二轮放宽多样性约束
8. 返回候选歌曲和 reason
```

多样性约束：

```text
BPM bucket 去重
energy bucket 去重
artist 去重
substyle bucket 去重
```

建议 bucket：

```text
bpm_bucket = round(bpm / 5) * 5
energy_bucket = low / mid / high / peak
substyle_bucket = platform_tags 中 strongest matched label
```

不要让多样性约束导致无法凑够时长。第二轮必须放宽约束补齐。

---

## 6.3 修改 /api/dj/styles/pick 返回结构

文件：

```text
app/modules/dj_control/router.py
```

保持旧字段不变，新增解释字段。

旧字段示例：

```json
{
  "song_id": "...",
  "title": "...",
  "artist": "...",
  "score": 0.79,
  "bpm": 96,
  "duration": 215,
  "energy": 0.72
}
```

新增字段：

```json
{
  "score_breakdown": {
    "fingerprint": 0.76,
    "platform_tags": 0.84,
    "reference_similarity": 0.81,
    "manual_feedback": null,
    "mixability": 0.73
  },
  "confidence": 0.78,
  "matched_labels": ["electro", "boogie", "funk"],
  "recommendation_reason": [
    "Popping fingerprint matched BPM/groove/bass profile",
    "Platform tags matched electro, boogie, funk",
    "Mixability is acceptable"
  ]
}
```

前端没使用这些字段时不应报错。

---

## 6.4 修改前端展示

文件：

```text
mobile/lib/src/dj_control_page.dart
mobile/lib/src/models.dart
mobile/lib/src/api_client.dart
```

本轮前端只做轻量修改：

```text
保留舞种 + 目标时长入口
保留原候选列表
增加可选“推荐原因/证据”展示
把文案从 “BPM/Phrase/Energy 匹配” 改为 “多源舞种匹配”
```

推荐文案：

```text
多源舞种匹配
综合音频特征、曲风标签、参考曲库相似度和 DJ 可用性生成候选
```

不要在前端计算舞种分数。前端只展示后端返回结果。

---

## 7. 外部平台接入要求

### 7.1 配置

新增配置项：

```text
DISCOGS_USER_TOKEN
LASTFM_API_KEY
MUSICBRAINZ_APP_NAME
CYANITE_API_KEY
BRIDGE_API_KEY
AIMS_API_KEY
ENABLE_EXTERNAL_MUSIC_TAGS
```

要求：

```text
.env.example 只写变量名，不写真实 key
缺 key 时 adapter 自动 disabled
disabled adapter 不得影响分析任务
```

---

### 7.2 外部请求不能发生在 /styles/pick

禁止：

```text
用户点生成候选
→ /api/dj/styles/pick
→ 实时请求 Discogs/Last.fm/Cyanite
```

正确做法：

```text
导入 / 分析 / 手动刷新 metadata
→ 后台请求外部平台
→ 缓存到 genre_profile.sources
→ /styles/pick 只读缓存
```

原因：

```text
/styles/pick 必须快
外部 API 可能慢、限流、失败
现场 DJ Control 不能被外部网络阻塞
```

---

## 8. 推荐提交顺序

### Phase 0：基线测试

提交名：

```text
test(dj-style): add baseline tests for current style picker
```

任务：

```text
为现有 /styles/pick 增加测试
确认旧请求结构仍可用
确认 target_duration_sec 能凑够歌曲
确认 min_score 生效
```

---

### Phase 1：多源评分结构

提交名：

```text
feat(dj-style): add multisource style evidence scoring
```

任务：

```text
新增 score_song_multisource
封装 fingerprint_score
新增 platform_tag_score 空实现
新增 reference_similarity_score 静态 profile 版
新增 mixability_score
动态权重归一化
```

---

### Phase 2：改造 pick_songs_for_duration

提交名：

```text
feat(dj-style): rank style picks by final multisource score
```

任务：

```text
/styles/pick 改用 final_pick_score
保留 min_score
增加 diversity selector
返回 score_breakdown 和 recommendation_reason
```

---

### Phase 3：平台标签 adapter

提交名：

```text
feat(metadata): cache external music tags for style evidence
```

任务：

```text
新增 metadata_adapters
实现 Discogs/Last.fm/MusicBrainz adapter
Cyanite/Bridge/AIMS 先做 stub 或 feature flag
写入 genre_profile.sources
失败不阻塞
```

---

### Phase 4：前端解释展示

提交名：

```text
feat(app): show multisource style pick reasons
```

任务：

```text
更新模型解析
候选卡片展示 score_breakdown 或 recommendation_reason
修改文案为“多源舞种匹配”
```

---

## 9. 测试要求

### 9.1 后端 py_compile

执行：

```bash
python3 -m py_compile \
  app/modules/dj_control/dance_style.py \
  app/modules/dj_control/router.py \
  app/modules/library/genre_classifier.py
```

如果新增 adapter：

```bash
python3 -m py_compile app/modules/library/metadata_adapters/*.py
```

---

### 9.2 后端单元测试

新增或修改：

```text
app/tests/test_dj_style_pick_multisource.py
app/tests/test_dance_style_evidence.py
app/tests/test_metadata_adapters.py
```

必须覆盖：

1. `score_song_multisource` 返回 0-1 范围内分数。
2. v3 fingerprint 存在时使用 v3。
3. `music_features["dj"]` 缺失时 fallback 到 v1。
4. platform tags 命中舞种 strong labels 时加分。
5. 没有任何外部 tags 时不报错。
6. manual feedback suitable 提高分数。
7. manual feedback unsuitable 降低分数。
8. mixability 使用 beat_confidence / transition_windows 等字段。
9. 动态权重归一化正确。
10. `/api/dj/styles/pick` 保持旧请求参数可用。
11. 返回结果包含旧字段 `score`, `bpm`, `duration`, `energy`。
12. 返回结果新增 `score_breakdown`, `confidence`, `recommendation_reason`。
13. `target_duration_sec` 最终候选总时长 >= 目标时长，除非曲库不足。
14. diversity selector 不会导致候选为空。
15. 外部 adapter disabled 时分析和 pick 不失败。

---

### 9.3 API 手工测试

请求：

```bash
curl -X POST http://127.0.0.1:8000/api/dj/styles/pick \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "style": "popping",
    "target_duration_sec": 600,
    "min_score": 0.35
  }'
```

检查：

```text
返回 200
songs 非空
每首歌有 score
每首歌有 score_breakdown
每首歌有 recommendation_reason
总时长 >= 600 秒，或返回明确 insufficient_library 标记
```

---

### 9.4 Flutter 测试

执行：

```bash
cd mobile
flutter analyze
flutter build apk --debug
```

手工验收：

```text
打开 DJ Control
选择舞种
输入目标时长
点击生成候选
候选列表正常出现
候选卡片能看到推荐原因
点击全部加入后仍进入 _picked 歌池
不影响后续能量排序 / set 编排 / transition plan
```

---

## 10. 完成定义

满足以下条件才算完成：

- [ ] `/api/dj/styles/pick` 请求参数完全兼容旧版。
- [ ] 旧版前端不使用新字段也不会崩。
- [ ] 新版返回包含 `score_breakdown` 和 `recommendation_reason`。
- [ ] `final_pick_score` 由多源证据融合得到，不再只等于 fingerprint 分。
- [ ] 外部 API key 缺失时系统正常工作。
- [ ] 外部平台请求不发生在 `/styles/pick` 实时路径中。
- [ ] `genre_profile.sources` 能保存平台标签证据。
- [ ] `style_evidence` 能保存每个舞种的评分证据。
- [ ] `dance_style_scores` 仍被写入，兼容现有 DJ Control。
- [ ] `min_score` 仍生效。
- [ ] `target_duration_sec` 仍能凑够目标时长。
- [ ] diversity selector 不会让候选列表异常为空。
- [ ] 后端新增测试全部通过。
- [ ] Flutter 能正常构建。
- [ ] 不修改 RK、xfade、transition plan 和 audio-engine。

---

## 11. 交接给 AI Agent 的执行提示

```text
请只修改 DJ Control 的“舞种 + 目标时长 → 生成候选歌曲”选歌准确率。

当前接口：
GET  /api/dj/styles
POST /api/dj/styles/pick

当前前端：
mobile/lib/src/dj_control_page.dart
mobile/lib/src/api_client.dart

当前后端：
app/modules/dj_control/router.py
app/modules/dj_control/dance_style.py

任务：
1. 保留现有 v3 fingerprint/v1 fallback。
2. 新增 score_song_multisource(style, song)。
3. 将 fingerprint_score、platform_tag_score、reference_similarity_score、manual_feedback_score、mixability_score 融合为 final_pick_score。
4. /styles/pick 改用 final_pick_score 排序和 min_score 过滤。
5. 返回 score_breakdown、confidence、matched_labels、recommendation_reason。
6. 平台标签只读缓存，不要在 /styles/pick 中实时请求外部 API。
7. 外部 API 缺 key 或失败时不得影响选歌。
8. 保持旧请求和旧返回字段兼容。
9. 不要修改 RK、audio-engine、xfade、transition_strategy。
10. 写单元测试并运行 py_compile / pytest / flutter analyze。

每次修改后说明：
- 修改了哪些文件；
- 是否影响前端、后端、数据库；
- 如何测试；
- 是否保持旧接口兼容。
```
