# 高频音乐特征与 21 风格分析实现

## 处理顺序

1. 复用已有 BPM、Beat、Downbeat、调性与 Demucs 四轨结果。
2. 分别运行 Bass、打击乐音色、节奏语法、人声/和声/制作四个特征模块。
3. 输出 `pre_style_evidence_v4`。这一层分别记录匹配分数和证据可靠度，不判断风格。
4. 21 种风格并行评分，输出绝对分数、可靠度、Top 3、证据贡献和复核原因。

## 特征模块

| 模块 | 主要输入 | 主要输出 |
|---|---|---|
| Bass 行为 | Bass Stem、Drums Stem、Kick 事件、整曲 | Sub Bass、pYIN 音高轨迹、Bass 滑音、低频旋律、低频回答、808/Log Drum 候选 |
| 打击乐音色 | Drums Stem、鼓事件 | Snare/Clap/Rim 家族、短/长金属声、有音高鼓、手鼓、连续高频层、音高型动机 |
| 节奏语法 | BPM、Beat、Downbeat、鼓事件 | 16 步模板、4/8/16 小节稳定窗口、四踩、Dembow、Jersey、Tamborzão、Two-step 等 |
| 音乐上下文 | Vocal/Other Stem、整曲、调性结果 | Rap、演唱、Vocal Chop、人声密度、和声复杂度、制作质感多证据 |

`availability=unavailable` 表示无法分析，此时 `detected` 和 `score` 为 `null`；它不会作为风格的反向证据。

## Bass 行为与音色候选

- `sub_bass` 只代表 25–95 Hz 低频主体。
- `bass_slide` 只代表至少约 2.5 半音的连续音高运动。
- `sustained_harmonic_bass_candidate` 综合持续低频、pYIN 基频和谐波结构。
- `sliding_bass_candidate` 必须具有可用音高轨迹和连续音高运动。
- `bass_reply_pattern`、`low_frequency_melody` 和 `low_percussive_bass_candidate` 描述 Amapiano 等风格真正使用的低频行为。
- `808_timbre_candidate`、`log_drum_candidate` 只作增强证据；`sub_808`、`sliding_808`、`log_drum` 仅作为旧数据兼容别名。

## 风格结果

风格 `score` 表示规则匹配程度，`reliability` 表示该风格实际使用的测量链质量，兼容字段 `confidence` 不能超过二者。21 种风格同时计算，两个风格组只用于结果展示，不参与预先分流。分数是绝对分数，不强制总和为 1。

系统在下列情况标记 `needs_review`：最高分不足、前两名过近、关键证据缺失、特征覆盖不足或上游特征分析降级。

## 存储与接口

- 特征事实：`music_features.pre_style_features`
- 风格结果：`music_features.high_frequency_styles`
- 读取：`GET /api/library/songs/{song_id}/high-frequency-styles`
- 仅重算风格：`POST /api/library/songs/{song_id}/refresh-high-frequency-styles`
- 重算特征与风格：请求体传入 `{"refresh_features": true}`，且歌曲必须已有四轨文件。

现有 `dance_styles`、`dance_style_scores` 与 `genre_profile` 保持独立，不会被本模块覆盖。
