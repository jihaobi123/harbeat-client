# 鼓组重合率计算与校准方案

## 目标

本模块将两首已经完成鼓事件分析的歌曲转换为可解释的鼓组重合率。它对应《接歌方案》中同风格歌曲的第二层判断：先比较鼓类，再比较主要节奏落点，最后根据阈值输出候选接法。

当前版本只生成评审数据，不改变正式候选排序。70% 和 85% 仍是方案暂定阈值，必须经过人工标注歌曲对的独立测试集验证后才能启用。

当前分数是全歌主鼓型的对称预筛分数，即 `score(A, B) == score(B, A)`。最终执行混音还必须比较 A 的出歌窗口与 B 的入歌窗口；窗口分数是有方向的，需要单独的 `exit_window -> entry_window` 特征和缓存，不能直接用本缓存替代。

## 输入

每首歌输入现有 `drum_transcription_consensus_v4` 的以下字段：

- `version`
- `status` 与 `needs_review`
- 五类鼓事件及数量（用于音色类别重合）
- `pattern.bars_analyzed`
- `pattern.dominant` 中按 Downbeat 对齐的 16 步鼓型
- 置信度与质量标记

下一版接入 MDX23C 后，鼓事件应分别从 `kick.wav`、`snare.wav`、`hihat.wav`、`tom.wav`、`cymbal.wav` 提取，再沿用相同的 16 步表示。当前 `drum_transcription_consensus_v4` 的主鼓型实际只包含 Kick、Snare 和 Hi-hat，Tom/Cymbal 只参与类别重合；不能误写成五类都已经参与落点比较。

## 分数

### 音色类别重合分

五类鼓使用加权 Jaccard：

- Kick：0.30
- Snare：0.25
- Hi-hat：0.20
- Tom：0.10
- Cymbal：0.15

两首歌都不存在的鼓类不计为匹配，避免稀疏或失败分析得到虚高分数。

### 节奏落点相似分

逐类比较 Downbeat 对齐后的 16 步主鼓型。相同 16 分音符位置得到完整匹配，相邻一个 16 分音符只得到一半匹配，用于容忍少量检测抖动，但不允许整体旋转鼓型来人为抬高得分。两首歌在某一类都没有落点时，该类被忽略，不会因为“共同为空”得到满分。

### 合并权重

当前暂定：

```text
drum_overlap_score = 0.40 × category_overlap_score
                   + 0.60 × rhythm_landing_similarity_score
```

节奏落点权重更高，因为接歌时节奏落点冲突比仅存在相同鼓类更直接。该权重与阈值都带有 `provisional_unvalidated` 标记。

## 阈值路由

严格按方案边界执行：

- `< 0.70`：音效接歌情况一。
- `0.70 <= score <= 0.85`：常规混音接歌。
- `> 0.85`：继续判断调式。

如果缺少 16 步鼓型、有效小节不足、来源带 `needs_review` 或任一输入不可用，`proposal_route` 输出 `manual_review`，不会自动选择接法。系统仍保留 `raw_threshold_route`，便于专家看到未经质量门控时分数落在哪一档。

## 缓存

缓存键包含：

- 排序后的两个 `song_id`
- 两首歌鼓分析输入的 SHA-256 指纹
- 评分算法版本
- 权重、阈值和容差配置

因此 A/B 与 B/A 共用一份缓存；任一歌曲重新分析、算法升级或权重改变都会自动生成新键。缓存使用原子替换写入。Jetson 部署时建议把 `HARBEAT_DRUM_PAIR_CACHE_DIR` 指向 Jetson 本地 SSD，NAS 保存最终分析和审计结果，不建议把高频小文件缓存直接放在 NAS。

## 真实数据校准

先从歌曲分析结果批量生成待评审 pair：

```bash
.venv/bin/python scripts/score_drum_pairs.py \
  --songs data/drum_analyses.jsonl \
  --cache-dir var/drum_pair_cache \
  --output reports/drum_pairs_for_review.jsonl
```

`data/drum_analyses.jsonl` 每行格式为 `{"song_id":"...","drum_analysis":{...}}`。默认生成所有不重复组合，也可用 `--pairs` 指定抽样歌曲对。输出已经带三个分数、质量标记、阈值档位和空的 `human_band`，人工听审只需补最后一项。

标注数据采用 JSONL。只校准阈值时每行至少包含：

```json
{"song_a_id":"a","song_b_id":"b","score":0.81,"human_band":"standard_mix"}
```

`human_band` 仅允许：

- `fx_transition`
- `standard_mix`
- `harmonic_check`

若要同时校准 40%/60% 合并权重，应保存两个分项：

```json
{"song_a_id":"a","song_b_id":"b","category_overlap_score":0.75,"rhythm_landing_similarity_score":0.86,"score":0.816,"human_band":"standard_mix"}
```

当全部训练样本都包含两个分项时，脚本会联合搜索类别权重、节奏权重和两个阈值；否则保留 40%/60%，只搜索阈值。

训练集只用于搜索阈值，测试集不得参与选择：

```bash
python scripts/calibrate_drum_pair_thresholds.py \
  --train data/drum_pairs_train.jsonl \
  --test data/drum_pairs_test.jsonl \
  --output reports/drum_pair_thresholds.json
```

训练集和测试集必须先按歌曲划分，再生成歌曲对；同一首歌不能同时出现在两个集合，否则 pair 数据会泄漏。只有测试集歌曲完全独立、三类标签在训练/测试中都有覆盖时，输出状态才会是 `heldout_validated`。正式启用前还应检查三类各自的 precision、recall、F1 和混淆矩阵，不能只看总体准确率。

70%/85% 不是模型天然概率，而是《接歌方案》的业务阈值。校准的目标是回答两件事：这两个边界在真实听审上是否合适，以及 40%/60% 权重是否能把三类接法分开。没有独立测试集前，任何训练集高分都不能视为完成。

## Pair score 缓存具体要求

缓存的对象是一对歌曲在某一评分版本和配置下的完整可解释结果，而不是只存一个浮点数。每条缓存至少包括：

- 规范化后的两首 `song_id` 与各自鼓分析指纹。
- 总分、类别分、落点分、类别权重和合并权重。
- 阈值版本、原始阈值档位、质量门控后的建议动作。
- 每个鼓类的存在性与落点匹配证据、质量标记。
- 评分算法版本，用于升级后自然失效。

缓存键对 A/B 与 B/A 对称；歌曲重新分析、模型版本变化、事件或主鼓型变化、权重/阈值变化都会产生新键，不会误用旧分数。当前实现是本地原子 JSON 缓存，适合 Jetson 上先验证。正式多人或多设备运行时，应再增加数据库级唯一键或集中式缓存，避免多个设备重复计算和各自持有不一致版本。

未来的窗口级缓存不能对称化，键中至少还要加入 A 的 exit 时间窗、B 的 entry 时间窗、两段的 section/bar 版本，以及时间拉伸后的目标 BPM。

## 仍未覆盖

- Snare 与 Clap 的独立分类。
- Closed 与 Open Hi-hat 的独立分类。
- Percussion 类别。
- 808 与普通 Bass 的区分。
- MDX23C 五轨自动接入正式后台分析。
- 将经过验证的鼓组分数接入候选排序和 Transition Planner。
- 在 RK3588 上验证三种阈值路由对应的真实混音听感。
- 批量生成同风格候选 pair、抽样听审和冲突复核的工具页面。
- 正式服务中的 pair score 数据库表、过期清理与命中率监控。
- A 出歌窗口到 B 入歌窗口的有向鼓型比较；歌曲级对称分只负责预筛。
