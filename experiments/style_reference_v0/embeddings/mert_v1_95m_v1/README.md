# HarBeat MERT-v1-95M 基础向量数据集

## 当前状态

- 音频：65 首，13 个现有风格，每类 5 首。
- 模型：`m-a-p/MERT-v1-95M`，冻结推理，不微调。
- 官方提交：`12af15fef9d0ac838c3f475bfbbf26d2060dd4f5`。
- MERT 原生输入：24 kHz 单声道；单窗口 5 秒；输出 13 层（投影层 + 12 个 Transformer 层），每层 768 维。
- 完成：65/65；失败：0；终检未发现 NaN/Inf、形状错误或版本混用。
- 标签仍未完成最终人工复核，因此这些文件可以立即用于无监督分析和训练流程开发，但监督学习指标仍需把标签噪声作为限制条件。

## “官方结果”与“HarBeat 派生结果”的边界

每个 5 秒窗口的 MERT 隐藏状态使用官方模型代码、官方预处理器、官方权重和官方配置生成。`official_compatibility_report.json` 记录了权重逐张量核验、CPU 可复现指纹和 CPU/MPS 数值一致性。

官方 MERT 没有定义“整首歌如何切窗、重叠窗口如何合并、小节如何池化”。以下三种数据是 HarBeat 为下游训练建立的派生表示，不能称作官方 MERT 的既定输出：

- `time_embeddings`：5 秒窗口、2.5 秒步长推理后，按 0.5 秒时间格对全部重叠 token 求均值。
- `bar_embeddings`：使用现有 downbeat 时间，把 0.5 秒向量按时间重叠比例汇聚到小节。
- `song_embedding`：对整首歌的 0.5 秒向量做时长加权平均。

## 文件结构

```text
mert_v1_95m_v1/
├── tracks/<track_id>.npz
├── index.csv
├── manifest.json
├── official_compatibility_report.json
└── README.md
```

## 从 GitHub 拉取

仓库中的 65 个 NPZ 通过 Git LFS 保存。首次拉取前需要安装 Git LFS：

```bash
git lfs install
git clone git@github.com:jihaobi123/harbeat-client.git
cd harbeat-client
git checkout archive/music-analysis-history-20260830
git lfs pull
```

如果 `tracks/*.npz` 只有约 130 字节，说明当前拿到的是 LFS 指针而不是向量本体，执行 `git lfs pull` 后再使用。

`index.csv` 用于筛选歌曲、风格、艺人和既有 fold。`manifest.json` 保存完整提取参数与逐曲状态。每个 NPZ 绑定原音频 SHA-256，避免音频被替换后仍误用旧向量。

## 单曲 NPZ 的主要字段

| 字段 | 形状 | 类型 | 用途 |
|---|---:|---|---|
| `time_embeddings` | `T × 13 × 768` | float16 | 片段内容、段落、人声/鼓/贝斯存在、情绪等时序任务 |
| `time_starts`, `time_ends` | `T` | float32 | 每个时间向量的实际时间范围 |
| `time_token_counts` | `T` | uint16 | 每格参与平均的 MERT token 数 |
| `bar_embeddings` | `B × 13 × 768` | float16 | 小节级结构、能量走势、接歌候选比较 |
| `bar_starts`, `bar_ends` | `B` | float32 | 小节时间范围；质量依赖现有 downbeat |
| `song_embedding` | `13 × 768` | float16 | 全曲风格、整体相似度、检索基线 |
| `primary_style`, `artist`, `fold` | 标量 | 字符串/整数 | 监督标签和拆分元数据，只能作为目标或分组，不得拼入模型输入 |
| `audio_sha256` | 标量 | 字符串 | 音频版本绑定 |
| `resolved_revision` | 标量 | 字符串 | 官方模型版本绑定 |

## 最小读取示例

```python
from pathlib import Path
import numpy as np

path = Path("tracks/6aa43bf8997b9757.npz")
with np.load(path, allow_pickle=False) as item:
    # 训练时转回 float32；不要直接用 float16 做归一化或损失计算。
    time_x = item["time_embeddings"].astype(np.float32)
    bar_x = item["bar_embeddings"].astype(np.float32)
    song_x = item["song_embedding"].astype(np.float32)
    target = str(item["primary_style"])
    group = str(item["primary_artist"])
    fold = int(item["fold"])
```

## 下游训练方式

不要默认只使用最后一层。针对每个任务训练一组 13 层的 softmax 权重：

```text
mixed_embedding = Σ softmax(layer_logits)[l] × embedding[l]
```

然后再接任务头：

- 全曲风格或相似度：`song_embedding` → 层混合 → 768→256 投影 → MLP/度量学习头。
- 片段人声、鼓、贝斯、情绪：`time_embeddings` → 层混合 → TCN/BiGRU/小型 Transformer → 逐时间格多标签头。
- 段落或结构：`time_embeddings` 或 `bar_embeddings` → 层混合 → 时序模型 → 边界头 + 段落标签头。
- 小节级接歌特征：优先 `bar_embeddings`；但小节时间可靠性必须单独由 downbeat 评估，MERT 向量不能修复错误的小节边界。

0.5 秒时间格适合内容和结构任务，不适合需要毫秒级起音、瞬态或精确拍点的任务；这些任务仍应使用高分辨率音频特征或节拍专用模型。

## 防止错误实验结论

1. 不允许把同一首歌的不同时间格随机拆进训练集和验证集。
2. 必须按歌曲拆分，风格评估继续按 `primary_artist` 隔离；同艺人不得跨训练和验证。
3. 标准化参数只能由训练 fold 计算。
4. `primary_style`、艺人、文件路径、track ID、fold 都不能作为模型输入。
5. 当前数据只有 13 类，不能用其结果推断21类准确率。
6. 训练新特征前先制定片段级标注规范；全曲风格标签不能自动当作每个0.5秒片段的内容标签。

## 复现与兼容性自检

在 `harbeat-client` 目录运行：

```bash
.runtime/mert-venv/bin/python \
  experiments/verify_mert_official_compatibility.py \
  --report ../style_reference_v0/embeddings/mert_v1_95m_v1/official_compatibility_report.json
```

只有报告状态为 `passed` 时才允许继续提取。模型使用 CC-BY-NC-4.0 许可，商业产品使用前需要单独处理授权问题。
