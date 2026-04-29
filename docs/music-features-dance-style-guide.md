# 音乐特征与舞蹈风格推荐开发说明

本文档说明 HarBeat 新增的“音乐流派识别 → 中间音乐特征 → 舞蹈风格评分”功能，供后续开发、验证和调参使用。

## 1. 功能目标

用户导入歌曲并分析后，系统会生成：

1. 音乐流派 `genres`
2. 中间音乐特征 `music_features`
3. 推荐舞蹈风格 `dance_styles`
4. 每个舞种的分数、置信度和推荐理由

一首歌可以对应多个舞蹈风格。系统不是做单分类，而是对每个舞种独立评分后返回 Top K。

核心流程：

```text
音频文件
  ↓
Essentia Discogs EffNet
  ↓
音乐流派 genres
  ↓
中间音乐特征 music_features
  ↓
结合 BPM / energy / beat_confidence / beat_points / phrase_map / 用户参数
  ↓
舞蹈风格多标签评分 dance_styles
```

注意：系统不会直接做 `genre -> dance style` 的硬映射。例如不会因为 genre 是 `house` 就直接判定舞种是 `house`。genre 只会先转成中间特征，例如 `club_drive`、`groove`、`bounce`，再参与舞种评分。

---

## 2. 相关文件

### 后端

| 文件 | 作用 |
|---|---|
| `app/modules/library/genre_analysis.py` | Essentia Discogs EffNet 音乐流派识别 |
| `app/modules/library/dance_style_rules.py` | 中间特征、舞种画像、BPM 区间、权重配置 |
| `app/modules/library/dance_style_classifier.py` | 中间特征推导和舞种评分核心逻辑 |
| `app/modules/library/analysis.py` | 分析流程入口，接入 genre 和 dance style |
| `app/modules/library/router.py` | API 接口，包括 analyze 和重新分类 |
| `app/modules/library/models.py` | `LibrarySong` 数据库字段 |
| `app/modules/library/schemas.py` | Pydantic schema |
| `app/shared/config.py` | Essentia 模型路径配置 |

### 前端

| 文件 | 作用 |
|---|---|
| `web/src/types/index.ts` | `LibrarySong` 类型扩展 |
| `web/src/api/client.ts` | 重新分类 API 调用 |
| `web/src/store/useMusicStore.ts` | store 中封装 `classifyDanceStyles` |
| `web/src/components/SongDetail.tsx` | 展示音乐流派、中间特征、推荐舞种、分数和 reasons |

---

## 3. Essentia 模型配置

当前使用两个 `.pb` 模型：

```text
discogs-effnet-bs64-1.pb
 genre_discogs400-discogs-effnet-1.pb
```

推荐路径：

```text
d:\harbeat\models\essentia\discogs-effnet-bs64-1.pb
d:\harbeat\models\essentia\genre_discogs400-discogs-effnet-1.pb
```

`.env` 配置：

```env
ESSENTIA_DISCOGS_EFFNET_MODEL_PATH=d:\harbeat\models\essentia\discogs-effnet-bs64-1.pb
ESSENTIA_DISCOGS_CLASSIFIER_MODEL_PATH=d:\harbeat\models\essentia\genre_discogs400-discogs-effnet-1.pb
ESSENTIA_GENRE_TOP_K=8
```

对应配置字段在 `app/shared/config.py`：

```python
essentia_discogs_effnet_model_path: str = ""
essentia_discogs_classifier_model_path: str = ""
essentia_genre_top_k: int = 8
```

### 运行环境注意

`essentia-tensorflow` 通常需要 Linux 环境。Windows 本地可能没有可用 wheel。推荐在以下环境验证：

1. Jetson / Linux 服务器
2. Docker Linux 容器
3. WSL2 Ubuntu
4. 任何可安装 `essentia-tensorflow` 的 Linux Python 环境

---

## 4. 数据结构

### 4.1 `genres`

Essentia 输出的音乐流派数组。

示例：

```json
[
  {
    "name": "hip hop",
    "confidence": 0.82,
    "source": "essentia_discogs_effnet"
  },
  {
    "name": "trap",
    "confidence": 0.63,
    "source": "essentia_discogs_effnet"
  }
]
```

相关字段：

```text
genres: JSON
genre_status: String
genre_source: String
```

### 4.2 `music_features`

中间音乐特征，由 genre hints、现有音频分析参数和 phrase 结构融合得到。

示例：

```json
{
  "features": {
    "energy": 0.71,
    "beat_confidence": 0.88,
    "groove": 0.82,
    "power": 0.58,
    "choreo": 0.65,
    "technical": 0.49,
    "bounce": 0.74,
    "flow": 0.78,
    "club_drive": 0.52,
    "percussive_density": 0.66,
    "syncopation": 0.58,
    "smoothness": 0.52
  },
  "matched_genres": ["hip hop", "trap"],
  "beat_stability": 0.91,
  "top_features": [
    { "name": "beat_confidence", "value": 0.88 },
    { "name": "groove", "value": 0.82 }
  ],
  "source": "genre_hints+audio_params+phrase_v2"
}
```

`music_features.features` 当前包含：

| 特征 | 含义 |
|---|---|
| `energy` | 整体能量 |
| `beat_confidence` | 节拍清晰度 |
| `groove` | 律动感 |
| `power` | 力量感 |
| `choreo` | 编舞适配度 |
| `technical` | 技术动作适配度 |
| `bounce` | 弹跳感 |
| `flow` | 流动性 |
| `club_drive` | 俱乐部/持续驱动感 |
| `percussive_density` | 打击密度 |
| `syncopation` | 切分律动 |
| `smoothness` | 顺滑度 |

### 4.3 `dance_styles`

推荐舞种结果。每首歌可以有多个推荐舞种。

示例：

```json
[
  {
    "style": "hiphop",
    "score": 0.82,
    "confidence": 0.77,
    "reasons": [
      "BPM 92.0 在 70-112 的适跳区间",
      "律动感 0.72 贴合 hiphop",
      "流动性 0.78 贴合 hiphop"
    ],
    "feature_scores": {
      "bpm": 0.94,
      "energy": 0.88,
      "groove": 0.96,
      "flow": 0.91
    },
    "source": "feature_scoring_v2"
  }
]
```

相关字段：

```text
dance_styles: JSON
dance_style_scores: JSON
dance_style_status: String
classifier_params: JSON
classifier_version: String
```

---

## 5. 评分逻辑

核心代码在：

```text
app/modules/library/dance_style_classifier.py
```

### 5.1 第一步：genre 转中间特征

函数：

```python
_derive_feature_hints_from_genres(genres)
```

规则来自：

```python
GENRE_AUDIO_FEATURE_HINTS
```

例如：

```python
"funk": {
    "beat_confidence": 0.84,
    "groove": 0.92,
    "technical": 0.72,
    "bounce": 0.88,
    "syncopation": 0.86,
    "percussive_density": 0.66,
}
```

这表示 Essentia 输出 `funk` 时，系统认为歌曲可能具有较强的 groove、bounce、syncopation 等特征，但不会直接推断为 `locking` 或 `funk` 舞种。

### 5.2 第二步：现有音频参数补充中间特征

函数：

```python
derive_music_features(...)
```

融合来源：

```text
genre_hints      权重 0.42
measured audio   权重 0.43
phrase features  权重 0.15
```

现有音频参数包括：

| 参数 | 来源 |
|---|---|
| `bpm` | `analyze_audio_file` |
| `energy` | RMS / online info |
| `beat_confidence` | Beat engine |
| `beat_points` | Beat engine |
| `phrase_map` | phrase structure |

`beat_points` 会推导 `beat_stability`。

`phrase_map` 会辅助推导：

- `choreo`
- `flow`
- `power`
- `club_drive`
- `technical`

### 5.3 第三步：每个舞种独立评分

函数：

```python
classify_dance_styles(...)
```

每个舞种有自己的特征画像：

```python
STYLE_FEATURE_PROFILES
```

每个舞种还有 BPM 适跳区间：

```python
STYLE_BPM_RANGES
```

评分使用：

```python
FEATURE_WEIGHTS
```

当前权重：

```python
FEATURE_WEIGHTS = {
    "bpm": 0.22,
    "energy": 0.14,
    "beat_confidence": 0.13,
    "groove": 0.13,
    "power": 0.08,
    "choreo": 0.07,
    "technical": 0.06,
    "bounce": 0.06,
    "flow": 0.04,
    "club_drive": 0.03,
    "percussive_density": 0.03,
    "syncopation": 0.01,
    "smoothness": 0.00,
}
```

每个舞种单独计算分数，超过阈值后进入候选列表，最后按分数排序返回 Top K。

---

## 6. API

### 6.1 完整分析歌曲

```http
POST /api/library/songs/{song_id}/analyze
```

该接口会执行：

1. BPM / Key / Energy / Beat / Cue / Phrase 分析
2. Essentia genre 分析
3. `music_features` 推导
4. `dance_styles` 推荐
5. 保存到 `library_songs`

返回 `LibrarySongData`。

### 6.2 重新计算舞种推荐

```http
POST /api/library/songs/{song_id}/classify-dance-styles
```

请求：

```json
{
  "params": {
    "prefer_power": 0.7,
    "prefer_groove": 0.8,
    "prefer_choreo": 0.5,
    "prefer_technical": 0.6,
    "prefer_flow": 0.6,
    "prefer_bounce": 0.7,
    "prefer_club": 0.4,
    "allow_styles": ["hiphop", "popping", "urban"],
    "block_styles": ["krump"]
  },
  "top_k": 5,
  "threshold": 0.35
}
```

参数说明：

| 参数 | 说明 |
|---|---|
| `params.prefer_power` | 偏力量感 |
| `params.prefer_groove` | 偏律动感 |
| `params.prefer_choreo` | 偏编舞适配 |
| `params.prefer_technical` | 偏技术动作 |
| `params.prefer_flow` | 偏流动性 |
| `params.prefer_bounce` | 偏弹跳感 |
| `params.prefer_club` | 偏俱乐部驱动 |
| `params.allow_styles` | 限定候选舞种 |
| `params.block_styles` | 排除舞种 |
| `top_k` | 返回前 N 个舞种 |
| `threshold` | 最低分数阈值 |

---

## 7. 前端展示

`SongDetail` 的“音乐画像”区域展示：

1. 音乐流派
   - genre name
   - confidence
2. 中间音乐特征
   - top features
   - 百分比进度条
3. 推荐舞种
   - style label
   - score
   - reasons
4. 重新评分按钮

相关文件：

```text
web/src/components/SongDetail.tsx
```

重新评分按钮调用：

```text
useMusicStore().classifyDanceStyles(song.id)
```

---

## 8. 调参指南

后续拿到真实音频输出后，主要调这些文件和常量：

```text
app/modules/library/dance_style_rules.py
```

### 8.1 genre 到中间特征不准

调：

```python
GENRE_AUDIO_FEATURE_HINTS
```

例子：如果 Essentia 输出 `trap` 的歌曲总是把 `krump` 推太高，可以降低：

```python
"trap": {
    "power": 0.74,
    "percussive_density": 0.72,
}
```

或者提升：

```python
"trap": {
    "choreo": 0.64,
    "flow": 0.62,
}
```

### 8.2 某个舞种整体不准

调：

```python
STYLE_FEATURE_PROFILES
```

例子：如果 `popping` 出现太少，可以检查是否要求 `technical` 或 `beat_confidence` 过高。

### 8.3 BPM 影响不准

调：

```python
STYLE_BPM_RANGES
```

例如：

```python
"popping": (88, 122)
```

### 8.4 某类特征权重过大/过小

调：

```python
FEATURE_WEIGHTS
```

例如觉得 BPM 影响太大，降低：

```python
"bpm": 0.22
```

觉得 groove 对街舞更重要，提高：

```python
"groove": 0.13
```

### 8.5 推荐结果太多或太少

调接口参数：

```json
{
  "top_k": 5,
  "threshold": 0.35
}
```

---

## 9. 验证建议

换到 Linux / Jetson / Docker / WSL2 后，建议用测试音频跑：

```bash
cd /path/to/harbeat-client
export PYTHONPATH=$PWD
python -c "import json; from app.modules.library.analysis import analyze_audio_file; r=analyze_audio_file('SongFormer/src/SongFormer/test_audio/NotShy-ITZY-20s.wav', title='Not Shy', artist='ITZY'); print(json.dumps({k:r.get(k) for k in ['genres','genre_status','genre_source','music_features','dance_styles','dance_style_scores','classifier_version']}, ensure_ascii=False, indent=2))"
```

重点检查：

1. `genres` 是否有合理的 Essentia 输出
2. `music_features.top_features` 是否符合歌曲直觉
3. `dance_styles` 排序是否符合舞蹈经验
4. `reasons` 是否解释得通
5. `classifier_version` 是否为 `feature_scoring_v2`

---

## 10. 已知限制

1. 当前分类器是规则评分器，不是训练出来的模型。
2. `GENRE_AUDIO_FEATURE_HINTS` 需要基于真实歌曲结果继续调参。
3. Essentia 在 Windows 环境可能无法直接安装验证，建议 Linux 环境。
4. `smoothness` 当前保留在中间特征里，但默认权重是 0，后续可根据舞种细化使用。
5. 当前还没有用户反馈闭环。后续可以记录用户接受/拒绝的舞种，用于调参或训练模型。

---

## 11. 后续建议

### 短期

1. 在 Linux/Jetson 上跑 20-50 首歌验证。
2. 根据真实输出调 `GENRE_AUDIO_FEATURE_HINTS`。
3. 根据舞蹈经验调 `STYLE_FEATURE_PROFILES`。
4. 给重新评分接口加一个简单参数面板。

### 中期

1. 保存用户手动确认结果。
2. 增加 `accepted_styles` / `rejected_styles` 数据。
3. 用反馈数据训练轻量多标签分类器。

### 长期

1. 使用 audio embedding 做相似歌曲检索。
2. 用 kNN 或 ML 模型替换部分规则。
3. 支持个性化分类器，例如不同用户对同一首歌可得到不同舞种推荐。
