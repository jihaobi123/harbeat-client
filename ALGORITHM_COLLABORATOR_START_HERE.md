# HarBeat 算法协作者：从这里开始

这份文件只面向音乐信息检索、机器学习和神经网络协作者。你不需要阅读整个 HarBeat 仓库，也不需要先理解手机端、RK 设备、Web 或部署系统。

## 1. 精简拉取

### 新电脑：只检出算法相关目录

```bash
git clone \
  --filter=blob:none \
  --no-checkout \
  --single-branch \
  --branch archive/music-analysis-history-20260830 \
  git@github.com:jihaobi123/harbeat-client.git \
  harbeat-algorithm

cd harbeat-algorithm
git sparse-checkout init --cone
git sparse-checkout set \
  app/modules/library \
  app/tests \
  config \
  docs/history \
  docs/roadmap \
  experiments \
  scripts \
  tests \
  modules/stem-separation/contracts
git checkout archive/music-analysis-history-20260830
```

如果没有配置 GitHub SSH，把仓库地址换成：

```text
https://github.com/jihaobi123/harbeat-client.git
```

### 已经有仓库：使用独立 Worktree

```bash
git fetch origin archive/music-analysis-history-20260830
git worktree add \
  ../harbeat-algorithm \
  -b feature/section-model-v1 \
  origin/archive/music-analysis-history-20260830
cd ../harbeat-algorithm
```

不要直接在 archive 分支开发。拉取后新建自己的功能分支：

```bash
git switch -c feature/section-model-v1
```

## 2. 只看这五份文档

按顺序阅读，前四份约 30–45 分钟：

1. [历史总览](docs/history/music-analysis-20260830/README.md)：知道已经做了什么。
2. [段落识别现状](docs/history/music-analysis-20260830/03_段落识别与神经网络架构.md)：知道当前能做和不能做什么。
3. [后续路线索引](docs/roadmap/README.md)：知道未来架构和当前实现的边界。
4. [完整实施方案](docs/roadmap/01_HarBeat_音乐分析系统_完整实施方案与工程路线.md)：重点阅读 Stage 2–8、9.4、9.5、18–20、26、28。
5. [69 项特征详细说明](docs/HarBeat_音乐特征分析方法与验证结果_20260828.md)：需要使用显式特征时再查，不必首次逐行阅读。

技术背景文档 [02_HarBeat_相关技术原理与成熟状态_背景资料.md](docs/roadmap/02_HarBeat_相关技术原理与成熟状态_背景资料.md) 是参考手册，不要求首次通读。

## 3. 当前算法事实

### 已有

- Beat、Downbeat、Meter、Bar 共识时间轴；
- Demucs vocals/drums/bass/other 分轨；
- 部分经过独立验证的节奏、Bass、人声、和声测量；
- 69 项高层特征注册、校准和发布门禁；
- All-In-One 功能段落候选；
- Discogs-EffNet 13 类风格表示原型；
- 数据构建、训练、评测和反泄漏脚本。

### 没有完成

- 正式 `sections[]` 数据合同和完整持久化；
- 段落人工真值；
- Boundary F1、Bar Macro-F1、Segment IoU；
- MERT 表示缓存基础设施；
- HarBeat 自己的 Boundary Head 和 Section Label Head；
- 21 类完整数据及独立外部盲测；
- 生产可用的校准概率和 OOD。

## 4. 先看的代码

| 目的 | 文件 |
|---|---|
| 完整音频分析与 All-In-One 段落 | `app/modules/library/analysis.py` |
| 分析结果落库 | `app/modules/library/background_tasks.py` |
| 特征注册和状态 | `app/modules/library/feature_registry.py` |
| 校准和发布门禁 | `app/modules/library/feature_calibration.py` |
| 节奏特征 | `app/modules/library/rhythm_feature_analysis.py` |
| Bass 特征 | `app/modules/library/bass_feature_analysis.py` |
| 人声音高 | `app/modules/library/vocal_pitch_analysis.py` |
| 和声/制作上下文 | `app/modules/library/musical_context_feature_analysis.py` |
| 风格数据构建 | `scripts/build_style_reference_dataset.py` |
| 表示提取 | `scripts/extract_style_embeddings.py` |
| 原型训练 | `scripts/train_style_model.py` |
| 原型评测 | `scripts/evaluate_style_model.py` |

## 5. 当前第一项共同研发任务

不要先训练大模型。第一项任务是建立可评价的段落识别基线：

```text
All-In-One 原始段落导出
        +
统一 sections[] Schema
        +
30 首人工边界/标签真值
        +
Boundary F1 / Bar Macro-F1 / Segment IoU
```

推荐拆成四个小任务：

1. 定义 `section_taxonomy_v1` 和 `sections[]` JSON Schema。
2. 导出 All-In-One 的 start/end/raw_label/source/model_version，保留 Downbeat 冲突标志。
3. 建立人工标注文件和一致性检查。
4. 实现基线评价程序，先确定错误来自 Boundary 还是 Label。

得到基线以后再决定：

- 边界可用、标签较差：只训练 Label Head；
- 标签可用、边界偏移：训练 Boundary Correction Head；
- 两者都差：训练 Bar-sequence Boundary + Label 两阶段模型。

## 6. 后续模型实验约束

每个任务都必须做三路对照：

```text
Explicit Only
Representation Only
Fusion
```

首轮比较 Discogs-EffNet、MERT、MAEST 的冻结表示，先训练线性 Probe 或小型 Head。只有小型 Head 已证明表示有效、数据规模足够且错误明确来自领域差异时，才考虑 LoRA 或顶部层微调。

数据拆分必须以歌曲和艺人为单位，片段不能跨 Fold。所有指标必须注明评价单位是 Frame、Event、Bar、Segment 还是 Track。

## 7. 验证

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest app/tests tests -q
```

当前历史分支验收基线：

```text
577 passed, 3 skipped
```

模型和数据集音频不在 Git 中。数据来源、SHA-256、划分和复现边界见 [数据集登记](docs/history/music-analysis-20260830/04_数据集登记.md)。

## 8. 提交要求

每个算法提交至少包含：

- 数据版本或 SHA-256；
- train/validation/test 或 Fold 划分；
- 随机种子；
- 模型和特征版本；
- 可复现命令；
- 聚合指标和逐类指标；
- 已知失败案例；
- 是否允许进入运行时。
