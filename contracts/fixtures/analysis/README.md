# Analysis fixtures

这里保存不含版权音频和本地路径的算法合同 JSON：ready、degraded、unavailable、invalid、timeout、cancel、旧版兼容。

当前 V1 基线：

- `bar_feature_v1.valid.json`：一个 4/4 完整小节，包含显式分析值、真实零和未计算字段；
- `track_analysis_v1.valid.json`：包含一个 Bar 的最小 `partial` TrackAnalysis，并带完整 provenance；
- `app/tests/test_music_analysis_contracts.py`：在运行时派生越界概率和非法缺失状态，确保无效样本被拒绝。

后续仍需补充 Analysis Job 的 timeout/retry、上一主版本兼容样本和真实 Worker 输出
快照。Fixture 中的哈希和 ID 只用于合同测试，不能作为生产模型或音频证据。
