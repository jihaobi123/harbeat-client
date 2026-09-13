# Analysis schemas

主维护：服务端音乐算法负责人。
批准：后端负责人。

已冻结供同风格接歌协作评审的合同：

- `same-style-track-preprocess-v1.schema.json`：Jetson 发布到 NAS 的单曲预处理结果。
- `same-style-pair-score-v1.schema.json`：两首已知同风格歌曲的鼓组 Pair Score。

对应说明见 `docs/same_style_preprocess_handoff_v1.md`。Core、Stem、Drum、Style 的通用正式 JSON Schema 仍待整理。

`pre-style-features-v5.schema.json` 已从退役的 modules/stem-separation 目录移入，内容未改，供现有内部特征测试使用。它不是新增的对外 NAS 发布协议，也不表示历史枚举漂移已经通过真实输出验收。公开交付继续以已有单曲预处理和人声 schema 为准。
