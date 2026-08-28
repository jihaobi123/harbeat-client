# MTG-Jamendo 公开弱标签验证

## 数据与方法

- 从 MTG-Jamendo 自动标签数据中按 Funk、Disco、House 选择 30 首，29 位不同艺人。
- 标签计数：Funk 13、Disco 12、House 11，其中 5 首为多标签。
- 每首使用可复现的 30 秒片段；公开上传者标签仅作弱监督，不作为逐段真值。
- 30/30 完成 Demucs 分轨、通用特征、21 风格分类和 Discogs EffNet 辅助标签。
- 音频与模型文件保留在 `/tmp`，不提交到仓库，避免版权和模型许可混入源码。

## 修正后结果

| 指标 | 修正前基线 | 最终结果 |
|---|---:|---:|
| 21 类第一候选命中公开标签 | 33.3% | 30.0% |
| Funk/Disco/House 三类内部命中 | 56.7% | 60.0% |
| 完整主标签命中 | 23.3% | 26.7% |
| 多标签至少命中一个公开标签 | 36.7% | 43.3% |
| 多标签 micro-F1 | 0.2895 | 0.3333 |
| 无完整主标签 | 9/30 | 6/30 |

最终分标签表现：Funk precision 1.000、recall 0.154、F1 0.267；Disco precision 0.600、
recall 0.250、F1 0.353；House precision 0.571、recall 0.727、F1 0.640。

## 判读

- 改动提高了三类边界判断、完整标签覆盖和多标签召回，但没有提高 21 类全局第一候选命中。
- Funk 和 Disco 的主要问题是召回不足；House 的主要问题是召回较好但假阳性偏多。
- `bass_syncopation` 修正后范围为 0.250–0.816、均值 0.561，不再出现饱和。
- `bass_octave_pattern` 有 21/30 接近零，说明只靠八度跳进无法可靠覆盖 Disco。
- Four-on-the-floor 和 Open Hat 仍主要依赖低可靠度频谱回退，是下一阶段最值得补专用模型的部分。
- 不应为了这 30 个上传者标签继续临时改阈值；下一步需要人工逐段复核或更强标注集。

完整产物：

- `/tmp/harbeat-public-benchmarks-20260828/clip-analysis/results-v2.json`
- `/tmp/harbeat-public-benchmarks-20260828/clip-analysis/weak-label-summary-v2.json`
- `/tmp/harbeat-public-benchmarks-20260828/clip-analysis/weak-label-report-v2.md`

公开项目：

- MTG-Jamendo Dataset: https://github.com/MTG/mtg-jamendo-dataset
- Essentia models: https://essentia.upf.edu/models.html
- Basic Pitch: https://github.com/spotify/basic-pitch
