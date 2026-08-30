# Analysis registries

`analysis_features_v1.jsonl` 是历史 69 项特征的机器可读迁移基线，由
`scripts/export_feature_registry_v1.py` 从原始 `feature_selection.csv` 确定性生成。

当前状态分布：

| 状态 | 数量 | 含义 |
|---|---:|---|
| `validated` | 10 | 保留原独立验证结论，不代表新模型已经上线 |
| `failed_validation` | 11 | 原验证未过，禁止自动升级为可用 |
| `provisional` | 23 | 测量或派生特征，尚无独立验证记录 |
| `candidate_only` | 20 | 音乐语义候选，只能用于标注候选与研究 |
| `deprecated` | 5 | 历史别名，指向 `canonical_feature_id` |

所有条目的 `definition_version` 当前为 `0.1.0`：它保证历史 ID、指标、样本量、
状态和别名关系已经纳管，但详细音乐语义、正反例和边界案例仍需音乐制作人签字。
签字后逐项升级定义版本；不得直接修改生成文件。
