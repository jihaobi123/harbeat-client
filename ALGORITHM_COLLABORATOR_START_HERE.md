# HarBeat 已完成算法工作交接

这份入口只包含已经完成的算法工作：

1. 传统/显式 69 项音乐特征；
2. 已完成的 Discogs-EffNet 神经网络表示与风格分类实验；
3. 实验使用的数据集、划分、指标和限制；
4. 对应的代码、配置、测试和报告。

其他内容暂时不用考虑，包括段落网络、未来 MERT 架构、手机端、Web、RK、部署和接歌业务。

## 1. 怎么拉取

### 新电脑

```bash
git clone \
  --filter=blob:none \
  --single-branch \
  --branch archive/music-analysis-history-20260830 \
  git@github.com:jihaobi123/harbeat-client.git \
  harbeat-algorithm-history

cd harbeat-algorithm-history
```

如果希望本地也只显示算法相关目录，再执行：

```bash
git sparse-checkout init --cone
git sparse-checkout set \
  app/modules/library \
  app/tests \
  config \
  docs/history \
  experiments \
  scripts \
  tests \
  modules/stem-separation/contracts
```

没有配置 GitHub SSH 时使用：

```bash
git clone \
  --filter=blob:none \
  --single-branch \
  --branch archive/music-analysis-history-20260830 \
  https://github.com/jihaobi123/harbeat-client.git \
  harbeat-algorithm-history
```

### 已经有仓库

```bash
git fetch origin archive/music-analysis-history-20260830
git worktree add \
  ../harbeat-algorithm-history \
  origin/archive/music-analysis-history-20260830
cd ../harbeat-algorithm-history
```

这个分支用于了解历史。开始修改代码时，另建功能分支：

```bash
git switch -c feature/algorithm-followup
```

## 2. 只看这些文档

### 第一步：10 分钟了解结论

1. [69 项传统特征摘要](docs/history/music-analysis-20260830/01_传统69项特征.md)
2. [已完成的机器学习实验摘要](docs/history/music-analysis-20260830/02_风格机器学习实验.md)

### 第二步：看完整证据

3. [69 项特征的完整方法和验证结果](docs/HarBeat_音乐特征分析方法与验证结果_20260828.md)
4. [13 类神经网络表示实验方法](experiments/style_reference_v0/reports/methodology.md)
5. [13 类四折结果](experiments/style_reference_v0/reports/cross_validation.md)
6. [稳健性和反泄漏检查](experiments/style_reference_v0/reports/robustness.md)
7. [69 项规则与机器学习配对实验](experiments/traditional_vs_ml_20260829/reports/traditional_vs_ml_assessment.md)

### 第三步：需要核对数据时再看

8. [数据集审计](experiments/style_reference_v0/reports/dataset_audit.md)
9. [实验模型卡](experiments/style_reference_v0/model_card.json)
10. [数据集和 Git 边界](docs/history/music-analysis-20260830/04_数据集登记.md)

不需要阅读 `docs/roadmap/` 和段落识别文档；它们属于后续构想，不属于本次已完成工作交接。

## 3. 69 项传统特征已经完成了什么

69 项是高层特征注册表，不代表 69 项全部准确。它们被分为：

- 原始测量：能量、密度、音高范围等；
- 派生关系：Backbeat、Tresillo、Bass Syncopation 等；
- 语义身份：808、Open Hat、Rap、Rage Synth 等。

完成的工程工作：

- 69 项特征定义和语义层级；
- `validated`、`failed_validation`、`provisional`、`candidate_only`、`deprecated`、`unavailable` 状态；
- 21 项带 held-out 指标的版本化校准；
- 检测方法和验证域一致性检查；
- 失败特征不能成为风格硬条件的发布门禁；
- 公开数据集专项评测脚本；
- 单元、集成和真实曲库运行检查。

主要已验证结果包括：

| 能力 | 结果 |
|---|---:|
| BPM | 直接速度 83.87%，半/倍速容错 100% |
| Beat | F1 88.55% |
| 高置信 Downbeat | F1 90.18% |
| Meter | Accuracy 92.31% |
| Key | Exact 83.67%，MIREX 85.31% |
| Kick | F1 83.98% |
| 高频打击事件 | F1 83.64% |
| Backbeat 2/4 | F1 96.63% |
| Breakbeat | F1 88.46% |
| Tamborzão | F1 84.75% |
| Tresillo | F1 95.58% |
| Two-step | F1 93.33% |
| 人声密度 | F1 94.28% |
| 人声音高范围 | F1 94.12% |
| 人声延音比例 | ±0.15 内 91% |
| 旋律轮廓 | F1 91.30% |
| 和弦变化 | GuitarSet 孤立吉他域 F1 93.69% |

明确没有通过的包括 Four-on-the-floor、Four-floor stability、Timing quantization、808 身份、Bass staccato、精确 Snare/Rim/金属打击身份和 Open Hat 身份等。完整状态必须以校准文件和报告为准，不能只看代码是否有输出。

## 4. 传统特征相关代码

### 核心

| 文件 | 作用 |
|---|---|
| `app/modules/library/feature_registry.py` | 69 项定义、语义层级和默认状态 |
| `app/modules/library/feature_calibration.py` | 校准指标和发布门禁 |
| `config/feature_calibration/v1.json` | 21 项 held-out 指标、阈值和限制 |
| `config/model_validation/` | BPM、Beat、Key、鼓、Bass 模型验证配置 |
| `modules/stem-separation/contracts/pre-style-features-v5.schema.json` | 特征输出合同 |

### 分析实现

| 文件 | 作用 |
|---|---|
| `rhythm_feature_analysis.py` | 节奏语法和模板 |
| `bass_feature_analysis.py` | Bass 音符、运动和候选音色 |
| `percussion_feature_analysis.py` | 打击乐候选 |
| `vocal_pitch_analysis.py` | 音域、延音、旋律轮廓 |
| `musical_context_feature_analysis.py` | 和弦、和声和制作上下文 |
| `acoustic_measurement_analysis.py` | 客观声学测量 |
| `feature_model_adapters.py` | 外部模型路线和失败隔离 |

这些文件都位于 `app/modules/library/`。

### 验证脚本

`scripts/evaluate_*.py` 包含 BPM、Beat、Key、鼓、Bass、Groove、Jamendo 人声、MIR-1K 人声音高、GuitarSet 和弦等评测入口。

## 5. 已完成的神经网络工作是什么

已经完成的是：

```text
65 首、13 类参考歌曲
        ↓
按歌曲和主艺人隔离的 4-Fold
        ↓
切成 872 个片段
        ↓
冻结 Discogs-EffNet 神经网络
        ↓
提取每个片段 1280 维 embedding
        ↓
整曲聚合
        ↓
Logistic Regression / SVM / Nearest Neighbor
        ↓
与 65 项技术特征及融合路线比较
```

这里使用了预训练神经网络作为音乐表示，但没有从零训练大型神经网络，也没有微调 Discogs-EffNet。

结果：

| 路线 | Top-1 | Macro-F1 | Top-3 |
|---|---:|---:|---:|
| 65 项技术特征 Logistic | 44.62% | 0.432 | 78.46% |
| Discogs-EffNet embedding + Logistic | 78.46% | 0.781 | 95.38% |
| Embedding + 技术特征融合 SVM | 80.00% | 0.796 | 95.38% |
| 69 项规则主口径 | 9.23% | 0.069 | 27.69% |

融合只比 embedding 多识别正确 1 首，Macro-F1 增益 0.015，没有达到预设 0.03 门槛。因此模型卡状态是 `experimental_not_approved`，没有接入运行时。

尚未完成：

- 没有训练 MERT Head；
- 没有微调 MERT、MAEST 或 Discogs-EffNet；
- 没有完整 21 类数据；
- 没有独立外部测试集；
- 没有生产模型；
- 没有把模型结果接入产品。

## 6. 神经网络实验相关代码

| 文件 | 作用 |
|---|---|
| `scripts/build_style_reference_dataset.py` | 构建数据清单、艺人分组 Fold 和片段 |
| `scripts/extract_style_embeddings.py` | 使用 Discogs-EffNet 提取 embedding |
| `scripts/train_style_model.py` | 训练技术、embedding 和融合分类器 |
| `scripts/evaluate_style_model.py` | 四折评测、稳健性和模型卡 |
| `scripts/audit_style_reference_labels.py` | 标签与身份审计 |
| `tests/test_style_reference_pipeline.py` | 数据和训练流程测试 |
| `experiments/traditional_vs_ml_20260829/evaluate_traditional_vs_ml.py` | 69 项规则与 ML 配对比较 |

实验快照位于：

```text
experiments/style_reference_v0/
experiments/traditional_vs_ml_20260829/
```

## 7. 数据集

### 私有参考曲库

- 65 首；
- 13 类；
- 每类 5 首；
- 约 4.33 小时；
- 源 ZIP SHA-256：
  `1ef55ef33439fecef1db939f0e64015d06ec24b2f575f2d0db58432d746584c5`；
- 缺少目标 21 类中的 8 类；
- 音频不上传 Git。

匿名 Fold 在：

```text
experiments/style_reference_v0/track_splits.json
```

数据定义在：

```text
experiments/style_reference_v0/dataset_metadata.json
experiments/style_reference_v0/feature_schema.json
```

### 公开专项数据

历史工作还使用 Groove MIDI、Jamendo Singing Voice、MIR-1K、GuitarSet、GiantSteps、GTZAN/Beat 等数据进行单项能力评测。下载和许可按各数据集要求单独处理，Git 只保存评测脚本、配置和聚合指标。

## 8. 验证

安装环境后：

```bash
python -m pytest app/tests tests -q
```

历史分支完整回归：

```text
577 passed, 3 skipped
```

如果只检查本次算法交接，可重点运行：

```bash
python -m pytest \
  app/tests/test_feature_calibration.py \
  app/tests/test_rhythm_feature_analysis.py \
  app/tests/test_bass_feature_analysis.py \
  app/tests/test_musical_context_feature_analysis.py \
  tests/test_style_reference_pipeline.py \
  -q
```

## 9. 本次不需要看的内容

- `docs/roadmap/`：后续构想；
- 段落识别和未来 Boundary/Label Head；
- `mobile/`、`web/`、`jetson/`、`rk_deploy/`；
- DJ Transition 和播放控制；
- 部署、数据库和前端文档；
- 与 69 项特征和 13 类 embedding 实验无关的历史模块。
