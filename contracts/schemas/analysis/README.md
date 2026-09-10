# Analysis schemas

主维护：服务端音乐算法负责人。
批准：后端负责人。

已冻结供同风格接歌协作评审的合同：

- `same-style-track-preprocess-v1.schema.json`：Jetson 发布到 NAS 的单曲预处理结果。
- `same-style-pair-score-v1.schema.json`：两首已知同风格歌曲的鼓组 Pair Score。

对应说明见 `docs/same_style_preprocess_handoff_v1.md`。Core、Stem、Drum、Pre-style、Style 的通用正式 JSON Schema 仍待迁入。

当前 `modules/stem-separation/contracts/` 只作为迁移输入；已知 Drum v3/v4 和 Pre-style v5 枚举存在漂移，修复并通过真实输出合同测试前不得复制为正式版本。
