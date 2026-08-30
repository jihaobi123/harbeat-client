# Analysis schemas

- 合同版本：`1.0.0`
- 主维护：服务端音乐算法负责人
- 批准：后端负责人
- 音乐语义评审：音乐制作人
- JSON Schema：Draft 2020-12
- 兼容策略：同一主版本只能新增可选字段或放宽消费者；删除、改名、单位变化和语义变化必须升主版本

## V1 文件

| Schema | 用途 | 当前状态 |
|---|---|---|
| `analysis_job_v1.schema.json` | 分析任务状态与阶段错误 | draft |
| `annotation_record_v1.schema.json` | 人工标注及复核记录 | draft |
| `bar_feature_v1.schema.json` | 单个小节的时间、结构、元素和音乐特征 | active |
| `dataset_track_v1.schema.json` | 可训练音轨与授权信息 | draft |
| `feature_registry_entry_v1.schema.json` | 单项特征定义、状态与生产门槛 | active |
| `mert_cache_manifest_v1.schema.json` | MERT 向量缓存及可复现信息 | draft |
| `model_manifest_v1.schema.json` | 模型注册、指标、权重与审批信息 | draft |
| `track_analysis_v1.schema.json` | 一首歌完整的小节级分析结果 | active |

`TrackAnalysis` 除 JSON Schema 外还必须通过
`app/modules/library/track_analysis_v1_validation.py` 的语义不变量校验；该层负责
父子 ID、Bar/Beat 数量、索引连续性、时间顺序、provenance 引用和缺失集合一致性。

所有生产者必须输出 schema 声明的缺失状态，不得以 `0`、空字符串或固定置信度
代替未知值。`validated` 只允许用于通过独立验证集门槛的特征；
`failed_validation`、`candidate_only`、`unavailable` 和 `deprecated` 会原样保留，
不能在迁移时自动提升状态。

当前 `modules/stem-separation/contracts/` 只作为迁移输入；已知 Drum v3/v4 和
Pre-style v5 枚举存在漂移，修复并通过真实输出合同测试前不得复制为正式版本。
