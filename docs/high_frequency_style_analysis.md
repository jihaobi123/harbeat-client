# 高频音乐特征与 21 风格分析实现

## 处理顺序

1. 复用已有 BPM、Beat、Downbeat、调性与 Demucs 四轨结果。
2. 分别运行 Bass、打击乐音色、节奏语法、人声/和声/制作四个特征模块。
3. 输出 `pre_style_evidence_v3`。这一层只记录音乐事实，不判断风格。
4. 21 种风格并行评分，输出绝对分数、Top 3、证据贡献和复核原因。

## 特征模块

| 模块 | 主要输入 | 主要输出 |
|---|---|---|
| Bass / 808 / Log Drum | Bass Stem、Drums Stem、Kick 事件、整曲 | Sub Bass、Bass 滑音、808 身份、Sliding 808、Log Drum |
| 打击乐音色 | Drums Stem、鼓事件 | Snare/Clap/Rim 家族、短/长金属声、有音高鼓、手鼓、连续高频层、音高型动机 |
| 节奏语法 | BPM、Beat、Downbeat、鼓事件 | 16 步模板、8 小节窗口、四踩、Dembow、Jersey、Tamborzão、Two-step 等 |
| 音乐上下文 | Vocal/Other Stem、整曲、调性结果 | Rap、演唱、Vocal Chop、和声复杂度、Jazz/Soul 候选、制作质感 |

`availability=unavailable` 表示无法分析，此时 `detected` 和 `score` 为 `null`；它不会作为风格的反向证据。

## 808 与 Log Drum

- `sub_bass` 只代表 25–95 Hz 低频主体。
- `bass_slide` 只代表至少约 2.5 半音的连续音高运动。
- `sub_808` 综合低频主体、稳定基频、F0–5F0 谐波、延音、Kick/Drum 瞬态和整曲低频一致性。
- `sliding_808` 必须同时具备 808 身份和 Bass 滑音。
- `log_drum` 使用有音高低音打击的起音、衰减、切分及与 Kick 分离关系，不由固定低频比例直接推出。

## 风格结果

风格分数由正向特征、特征置信度、可用证据覆盖率、BPM 区间、必需证据和反向冲突共同决定。21 种风格同时计算，两个风格组只用于结果展示，不参与预先分流。分数是绝对分数，不强制总和为 1。

系统在下列情况标记 `needs_review`：最高分不足、前两名过近、关键证据缺失、特征覆盖不足或上游特征分析降级。

## 存储与接口

- 特征事实：`music_features.pre_style_features`
- 风格结果：`music_features.high_frequency_styles`
- 读取：`GET /api/library/songs/{song_id}/high-frequency-styles`
- 仅重算风格：`POST /api/library/songs/{song_id}/refresh-high-frequency-styles`
- 重算特征与风格：请求体传入 `{"refresh_features": true}`，且歌曲必须已有四轨文件。

现有 `dance_styles`、`dance_style_scores` 与 `genre_profile` 保持独立，不会被本模块覆盖。
