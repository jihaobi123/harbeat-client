# 测试曲库 1.0：特征与 21 风格最终增量验证

## 结论

旧版曾出现 10 首第一候选全部为 Disco。本轮使用修正后的通用时频特征、Funk/Disco/House
边界证据和可选 Discogs EffNet 辅助标签重新分析，10/10 成功，第一候选分布为 House 5、
Disco 3、R&B 1、Rage 1。Rage 与 R&B 两首都没有满足完整标签条件，不能作为最终主标签。

- 自动测试：470 passed，3 skipped，0 failed。
- 完整主标签：8/10；无完整主标签：2/10。
- 可选 Discogs 模型：10/10 路由成功；只提供最高 0.18 的正向加分，不能绕过原生必需证据。
- 完整 JSON：`/tmp/harbeat-test-library-1.0-20260828-final/results.json`。
- 逐曲证据报告：`/tmp/harbeat-test-library-1.0-20260828-final/report.md`。

## 逐曲结果

“第一候选”是 21 类中的最高证据分；“完整主标签”必须同时通过分数、可靠度、必需证据和
最少证据数门槛。两者不同是有意设计，不再把低分候选伪装成确定标签。

| # | 曲目 | 第一候选 | 完整主标签 | 完整多标签 | 关键说明 |
|---:|---|---|---|---|---|
| 1 | Afrika Bambaataa - Funky Heroes | House 0.778 | House | House、Disco | 模型中心段强支持 House/hip-house；标题中的 Funky 不能替代声学证据 |
| 2 | Basic Element - Night Eyes | House 0.697 | House | House、Disco | 模型为 Euro House/Eurodance；Eurodance 不在 21 类中，保留越界提示 |
| 3 | Cerrone / Mike City - You Only Live Once | Disco 0.734 | Disco | Disco | 模型同时支持 Disco、Nu-Disco，原生 Disco 条件完整 |
| 4 | Dogg Master / XL Middleton - Pop Lock Funk | House 0.612 | House | House、R&B | 模型强支持 Funk/G-Funk；Funk 0.580 但缺原生必需证据，属于明确冲突样本 |
| 5 | Ghosthouse - Crazy in Love | House 0.642 | House | House、Funk | House/Funk/Disco 分差小，应按交叉风格保留多标签 |
| 6 | Look Twice - FUNK YOU UP | R&B 0.543 | 无 | 无 | 低于检测阈值；模型偏 K-pop/RnB-Swing，不能按歌名强制 Funk |
| 7 | Uptown Funk (Wideboys VIP Remix) | House 0.704 | House | House、Disco | Remix 的 House 制作证据显著，不继承原曲单一标签 |
| 8 | Mass Production - Turn up the Music | Disco 0.627 | House | House | 模型支持 Disco/Funk；Disco 第一候选缺必需证据，保持候选与主标签分离 |
| 9 | S Club 7 - Don't Stop Movin' | Disco 0.672 | Disco | Disco、House | 两者只差 0.002，明确标记近邻复核 |
| 10 | Dreamgirls - One Night Only (Disco) | Rage 0.547 | 无 | 无 | 模型偏 Gospel/Soul且整体很弱；Rage 未达阈值，只是低分候选，不是结论 |

## 新增特征分布

| 特征 | 最小 | 最大 | 均值 | 平均可靠度 | 解释 |
|---|---:|---:|---:|---:|---|
| bass_syncopation | 0.225 | 0.732 | 0.451 | 0.869 | 已取消旧版不自然的除数，公开集和曲库均不再饱和 |
| bass_staccato_ratio | 0.329 | 0.787 | 0.523 | 0.850 | 音符持续时间相对拍长的断奏比例 |
| bass_riff_repetition | 0.106 | 0.508 | 0.259 | 0.603 | 拍对齐低音轮廓的重复性 |
| bass_octave_pattern | 0.000 | 0.321 | 0.108 | 0.646 | 约 12 半音跳进；精度可用但召回仍低 |
| bass_kick_interlock | 0.375 | 0.777 | 0.573 | 0.848 | Bass onset 与 Kick 的错位/互锁关系 |
| offbeat_open_hat | 0.000 | 0.628 | 0.330 | 0.341 | 无专用鼓模型时为受限频谱回退，可靠度保持低上限 |
| four_floor_stability | 0.000 | 0.446 | 0.141 | 0.294 | Kick 在四拍格点上的覆盖与稳定性 |
| timing_quantization | 0.122 | 0.624 | 0.291 | 0.550 | 鼓击相对节拍子网格的贴合程度 |
| drum_loop_repetition | 0.717 | 0.882 | 0.805 | 0.550 | 鼓型周期重复，曲库中整体较高但未饱和 |
| drum_machine_consistency | 0.353 | 0.696 | 0.482 | 0.680 | 起音强度、音色和时间稳定度的组合证据 |

## 客观限制

1. 这 10 首不是平衡、人工逐段标注的数据集，不能据此训练或直接确定生产阈值。
2. `Pop Lock Funk` 证明原生 Funk 必需证据召回仍不足；不能仅提高模型权重来迎合文件名。
3. `One Night Only` 证明 21 类不是闭集。无完整标签时应返回空主标签，并保留模型原始标签。
4. 专用鼓转录模型未配置，Open Hat、Four-on-the-floor 等鼓语义的可靠度仍受限。
5. Basic Pitch 贝斯路线已实现为可选适配器，但本轮因 PyPI 网络不可达未实跑，不计入结果。
