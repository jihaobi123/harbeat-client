# HarBeat 音乐分析历史工作入口

算法同事第一次进入仓库，请直接阅读 [ALGORITHM_COLLABORATOR_START_HERE.md](ALGORITHM_COLLABORATOR_START_HERE.md)，无需浏览整个仓库。

本文件是 2026-08-30 冻结的团队协作入口，覆盖三条已经开展的工作：

1. 传统/显式 69 项音乐特征的定义、实现、验证和失败记录；
2. 13 类风格数据集上的预训练音乐表示、技术特征与融合模型实验；
3. 段落识别基线与后续神经网络架构。

请先阅读 [历史总览](docs/history/music-analysis-20260830/README.md)，再按任务进入：

- [69 项显式特征](docs/history/music-analysis-20260830/01_传统69项特征.md)
- [风格机器学习实验](docs/history/music-analysis-20260830/02_风格机器学习实验.md)
- [段落识别与神经网络架构](docs/history/music-analysis-20260830/03_段落识别与神经网络架构.md)
- [数据集与产物边界](docs/history/music-analysis-20260830/04_数据集登记.md)
- [复现、协作和下一步](docs/history/music-analysis-20260830/05_复现与协作.md)
- [后续音乐分析与神经网络完整路线](docs/roadmap/README.md)

后续构想的两份完整原始方案也已纳入版本控制：

- [完整实施方案、Pipeline、数据集与工程路线](docs/roadmap/01_HarBeat_音乐分析系统_完整实施方案与工程路线.md)
- [MERT、音乐表征与专项模型技术背景](docs/roadmap/02_HarBeat_相关技术原理与成熟状态_背景资料.md)

必须先知道的结论：

- 69 项特征是“音乐事实与候选证据库”，不是 69 个都已准确的分类开关。
- 当前 13 类实验中，显式规则主路线 Top-1 为 9.23%，Discogs-EffNet 嵌入为 78.46%，融合为 80.00%。
- 该实验只有 65 首、每类 5 首，缺少目标 21 类中的 8 类，不能作为 21 类生产准确率。
- All-In-One 段落模型已能真实推理并输出起止时间和标签，但正式落库、人工真值评测和下游统一尚未完成。
- 原始商业歌曲、受许可约束的数据集、模型缓存和带本机路径的逐帧结果不进入 Git；仓库保存代码、划分、哈希、聚合指标和复现说明。
