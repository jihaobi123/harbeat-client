# 公开音乐数据校准方案

本方案只用于验证和校准，不把公开标签当作无噪声真值，也不改变线上分类流程。

## 数据源与用途

| 数据源 | 首要用途 | 本项目使用方式 | 注意事项 |
|---|---|---|---|
| MTG-Jamendo | 多标签风格、乐器 | 优先构建 Funk / Disco / House 边界集，再覆盖 21 类 | 上传者标签存在噪声；保留原始多标签 |
| FMA | 风格正负样本补充 | 只补齐 MTG-Jamendo 稀缺类别 | 层级标签不能直接等同于 21 类 |
| OpenMIC-2018 | 乐器存在性 | 校准吉他、铜管、键盘、合成器等候选 | 不用于判断具体演奏技法 |
| Groove MIDI / E-GMD | 鼓件与律动 | 校准四拍、反拍踩镲、切分、量化和循环稳定性 | 合成鼓音色与商业混音存在域差异 |
| MedleyDB / MUSDB18 | Bass、Drums、Other 分轨 | 验证贝斯音符、滑音和分轨污染影响 | 样本规模较小，不能单独决定阈值 |
| GiantSteps | 电子舞曲 BPM | 复核现有 BPM 共识，不重新训练 BPM 模型 | 主要覆盖电子舞曲 |

## 分阶段样本规模

1. Funk、Disco、House：每类先收集 100～150 个 20～30 秒片段，允许重叠标签。
2. 其余 18 类：每类至少 30 个正样本，并提供相邻风格负样本。
3. 高风险语义特征：每个特征至少 30 个正片段和 30 个负片段后，才允许调整生产阈值。
4. 数据按艺术家分组切分，避免同一艺术家的相似制作同时进入校准集和验证集。

## 清单格式

公开或人工标注统一保存为 JSON/JSONL，不提交有版权限制的音频：

```json
{
  "clip_id": "dataset-track-start-end",
  "dataset": "mtg_jamendo",
  "source_track_id": "12345",
  "artist_group": "artist-123",
  "split": "validation",
  "start_seconds": 30.0,
  "end_seconds": 60.0,
  "expected_styles": ["funk", "disco"],
  "expected_features": {
    "low_frequency.bass_syncopation": true,
    "rhythm_grammar.four_floor_stability": true
  },
  "annotation_source": "public_tag_plus_human_review",
  "license": "source-specific"
}
```

## 发布门槛

- 单元测试通过只证明代码逻辑，不计作音乐准确率。
- 二值特征报告 Precision、Recall、F1 和正负样本数。
- 风格报告 micro/macro F1、每类指标及 exact-match；不使用单标签 Accuracy 代替多标签指标。
- 少于 30 个标注样本只能产生实验阈值，不得直接更新生产阈值。
- 报告必须按数据集分别展示结果，避免单一数据域掩盖错误。
- Essentia 模型权重的 CC BY-NC-SA 许可只适合当前研究验证；商业发布前必须完成授权审查。
