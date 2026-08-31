# SongFormer 段落标签合同兼容升级设计

日期：2026-08-31
状态：已实施，等待最终交付
目标分支基线：`archive/music-analysis-history-20260830@15c3c20`

## 1. 背景

SongFormer 的段落边界在当前样本上表现可用，但它只输出八类通用歌曲结构：`intro`、`verse`、`chorus`、`bridge`、`inst`、`outro`、`silence` 和 `pre-chorus`。HarBeat 的混音逻辑还需要 `drop`、`buildup`、`breakdown`、`transition` 等混音功能。两套概念不能共用一个单选标签。

提交 `15c3c20` 还存在三个数据问题：推理结果只保留最终标签，SongFormer 的 `intro` 标签参与裁剪基础 Downbeat，缓存键也没有包含模型和标签合同版本。模型输出有歧义时，系统既无法校准，也可能把语义错误传到小节编号和混音策略。

## 2. 设计目标

本次改造按兼容方案执行：

1. SongFormer 继续决定段落边界，但它的标签只作为结构候选。
2. 每个 SongFormer 段落保存八类完整概率、最高概率和前两名差值。
3. 通用结构标签与混音功能标签分开保存。
4. `inst` 在 HarBeat 合同中规范为 `instrumental`；原始模型标签仍保留。
5. `pre-chorus` 产生 `transition` 和 `buildup` 混音候选，不伪造成最终业务结论。
6. 基础 Downbeat 只由节奏分析决定，`intro_end_candidate` 单独保存。
7. 缓存必须随模型、Checkpoint、推理配置和标签合同版本变化而失效。

本次不训练新的标签模型，不新增数据库表，也不尝试用规则直接判断所有 Drop、Breakdown。旧 `label` 字段暂时保留，作为兼容投影。

## 3. 段落数据合同

SongFormer 段落的正式结构如下：

```json
{
  "start": 48.0,
  "end": 64.0,
  "boundary_source": "songformer",
  "songformer_label": "inst",
  "structure_label_candidate": "instrumental",
  "structure_label_probabilities": {
    "intro": 0.01,
    "verse": 0.08,
    "chorus": 0.24,
    "bridge": 0.06,
    "instrumental": 0.56,
    "outro": 0.01,
    "silence": 0.0,
    "pre-chorus": 0.04
  },
  "structure_label_confidence": 0.56,
  "structure_label_margin": 0.32,
  "mix_roles": ["instrumental_focus"],
  "mix_role_scores": {
    "instrumental_focus": 1.0
  },
  "label": "instrumental",
  "label_status": "candidate",
  "source": "songformer_functional_segment"
}
```

字段语义：

- `songformer_label`：模型原始输出，不做业务改写。
- `structure_label_candidate`：HarBeat 规范化后的通用结构候选。
- `structure_label_probabilities`：八类概率，`inst` 键规范为 `instrumental`。
- `structure_label_confidence`：候选标签概率。
- `structure_label_margin`：最高概率减第二高概率，用于发现模糊段落。
- `mix_roles`：多标签混音功能候选。
- `mix_role_scores`：候选分数，范围为 0 到 1。
- `label`：旧消费者使用的兼容字段，值等于 `structure_label_candidate`。
- `label_status`：固定为 `candidate`，避免旧字段被误认为人工真值。

All-In-One 回退结果继续使用同一合同。没有概率时，概率字典为空，置信度和 margin 为 `null`，来源明确标记为 fallback。

## 4. 标签适配规则

第一版只做确定性强、不会伪造语义的映射：

| SongFormer 原始标签 | 结构候选 | `mix_roles` | 分数 |
| --- | --- | --- | --- |
| `inst` | `instrumental` | `instrumental_focus` | 1.0 |
| `pre-chorus` | `pre-chorus` | `transition`、`buildup` | 1.0、0.7 |
| 其余六类 | 原标签 | 空 | - |

`drop` 和 `breakdown` 不从 SongFormer 单标签直接映射。后续应结合能量变化、Stem 活动、重复关系和人工修订生成，避免把所有 `chorus` 都当成 Drop。

## 5. 数据流

```text
MusicFM + MuQ
  -> SongFormer boundary/function logits
  -> 官方边界后处理
  -> 按最终段落重新汇总八类概率
  -> 标签合同适配
  -> section_analysis.functional_segments
  -> phrase_map / cue_points 兼容投影
  -> 数据库与 Manifest
```

`section_analysis` 增加：

- `authoritative_boundary_model: "songformer"`
- `structure_label_source: "songformer_candidate"`
- `label_contract_version`
- `intro_end_candidate`
- `semantic_intro_applied_to_bar_grid: false`
- 完整的模型和缓存指纹信息

## 6. Downbeat 与 Bar 网格

当前逻辑从 SongFormer 的 `intro` 结束位置开始导出 Downbeat。改造后：

1. Downbeat 共识先选出基础锚点。
2. 按真实 Beat 序列和拍号生成完整 Bar 网格。
3. 不读取任何段落标签，也不删除 Intro 内的 Downbeat。
4. SongFormer 的连续开头 `intro` 只生成 `intro_end_candidate`。
5. 需要跳过前奏的混音功能读取候选值，基础时间轴保持不变。

旧的 `downbeats` 字段改为完整权威网格。`bar_grid_origin` 记录节奏来源、锚点和 `removed_intro_downbeats: 0`。

## 7. 缓存版本

缓存命名空间由以下内容生成：

- 运行器版本和标签合同版本；
- SongFormer 源码 Git revision；
- SongFormer Checkpoint SHA-256；
- MusicFM Checkpoint 与归一化统计文件 SHA-256；
- MuQ 模型文件 SHA-256；
- 数据集 ID、采样率、特征层、精度和帧率。

权重文件的 SHA-256 结果保存在带路径、文件大小和修改时间校验的本地指纹清单中，避免每首歌重复读取大模型文件。Git 工作树存在未提交源码改动时，指纹同时包含源码树摘要。音频缓存键使用完整文件内容摘要，不依赖路径、大小和修改时间的组合。缓存目录包含命名空间；任何一项变化都会生成新缓存，不复用旧 Embedding 和旧标签。

Manifest 必须记录上述版本信息。无法取得 Git revision 时，使用 `unknown`，但 Checkpoint 哈希仍是必填项。

## 8. 兼容与错误处理

- 旧 `phrase_map[].label` 和 `cue_points[].label/raw_label` 保留。
- 新消费者优先读取 `structure_label_candidate` 和 `mix_roles`。
- 概率缺失或格式错误时不伪造置信度，标记 `label_evidence_status: "missing"`。
- SongFormer 失败时仍允许 All-In-One 回退，边界和标签来源不得伪装。
- 所有概率在落库前校验为有限数值，并归一化到总和约等于 1。

## 9. 测试与验收

自动化测试至少覆盖：

1. 八类概率经过最终段落边界重新汇总并保存。
2. `inst` 同时保留原始标签并规范为 `instrumental`。
3. `pre-chorus` 生成 `transition` 和 `buildup` 候选。
4. All-In-One 回退不会伪造概率。
5. Intro 标签变化不改变完整 Downbeat 网格。
6. 模型或合同版本变化后缓存命名空间变化。
7. `phrase_map`、`cue_points`、`section_analysis` 和数据库序列化字段一致。
8. 现有 BPM、Downbeat、段落回退和后台任务测试不回归。

验收结果需要包含目标测试、相关后端测试和完整测试套件的通过记录。真实模型抽样还要保存至少一首包含 `pre-chorus` 或 `inst` 的 Manifest，确认概率和版本字段存在；如果本机没有模型权重，该项明确记为环境未满足，不能用模拟测试冒充。
