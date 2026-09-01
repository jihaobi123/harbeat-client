# SongFormer 段落边界与小节标注块部署设计

日期：2026-09-01  
状态：设计已确认，等待实施计划确认  
范围：Jetson 上的 SongFormer 推理、段落边界转小节标注块、标注页交互与残差分类器预留接口

## 1. 背景与当前状态

阶段三需要标注人声、鼓、贝斯和其他/旋律在歌曲中的出现范围。时间轴仍以小节为最小精度，但日常标注应以包含多个小节的段落块为主要操作单位：标注者先给整个块赋值，只有局部小节不准确时才拆分或覆盖。

远端分支已经包含 SongFormer 的隔离推理运行器和后置残差分类器的代码合同。当前实际环境有以下约束：

- Jetson 为 64 GB NVIDIA Orin，CUDA 版 PyTorch 可用，具备运行 SongFormer 的资源条件。
- Jetson 和 NAS 目前没有 SongFormer、MusicFM、MuQ 模型资产。
- 远端仓库没有训练完成的残差分类器 JSON 权重，只有训练、校验和运行时代码。
- 现有公开标注站点使用版本化发布，标注记录保存在独立持久化目录中，部署不得覆盖该目录。
- 当前标注页的普通音频播放会被所选范围的结束时间误停，需要区分“普通播放”和“试听所选范围”。

## 2. 已确认的产品决策

1. 本次只部署 SongFormer，不部署、训练或启用残差分类器。
2. SongFormer 是段落时间边界的权威来源；它的段落名称只作为候选信息，不作为阶段三元素标签的真值。
3. SongFormer 的秒级边界必须吸附到权威 Bar 网格，再生成标注块。
4. 标注块内的小节默认共享同一组元素标签，标注者仍可拆分块或单独覆盖局部小节。
5. 现在保留稳定的残差分类器输入、输出和运行状态接口，后续放入训练好的权重即可启用，不再改标注数据结构和前端主流程。
6. SongFormer 失败时不得将其他模型结果伪装成 SongFormer；该歌曲进入人工划分状态。
7. 模型、运行器、缓存和网页均采用可回滚的版本化部署，已有页面、账号和标注记录保持不变。

## 3. 目标与非目标

### 3.1 目标

- 在 Jetson 上稳定运行官方 SongFormer 推理链路。
- 将每首歌曲的 SongFormer 段落时间转换为以 Bar 为边界的标注块。
- 在标注页中以段落块为默认选择范围，降低逐小节重复操作。
- 保存原始边界、吸附后的边界、吸附误差和模型指纹，便于人工复核和后续重跑。
- 修复普通播放自动停止的问题，并保留选区试听能力。
- 定义残差分类器的兼容接口，但保持其明确禁用。

### 3.2 非目标

- 本次不训练、评估或上线残差分类器。
- 本次不把 SongFormer 的 `verse`、`chorus` 等标签转换成人声、鼓或贝斯标签。
- 本次不修改阶段四的最终标签定义。
- 本次不重写或迁移已有人工标注。
- 本次不使用固定四小节或八小节规则替代 SongFormer 的真实段落边界。

## 4. 总体架构

```text
歌曲音频
  -> 现有 Beat / Downbeat 分析
  -> 权威 Bar 网格
  -> 隔离 SongFormer 推理
       MusicFM -> MuQ -> SongFormer -> 原始段落与八类概率
  -> 边界校验与 Bar 吸附
  -> 段落标注块
  -> /annotate 默认按块选择和赋值
  -> 局部 Bar 拆分、覆盖或合并
```

MusicFM、MuQ 和 SongFormer 按顺序加载，避免三个大模型同时占用 GPU 显存。推理输出按音频内容和完整运行时指纹缓存，模型或代码变化后自动进入新缓存命名空间。

## 5. Jetson 运行布局

建议使用以下稳定路径：

```text
/opt/harbeat/models/SongFormer/            # SongFormer 源码与 Checkpoint
/opt/harbeat/models/MuQ-MuLan-large/       # MuQ 本地模型
/opt/harbeat/runtime/songformer-venv/      # 隔离 Python 环境
/opt/harbeat/releases/<release>/scripts/   # 版本化推理入口
/mnt/nas/harbeat/cache/songformer-analysis/ # 大体积特征与结果缓存
```

模型放在 Jetson 本地存储，减少每次加载时的 NAS 延迟；可重建的中间特征和结果缓存放在 NAS。若模型实际体积导致本地安全余量不足，实施时改为 NAS 模型目录，但路径仍通过环境变量注入，不改业务代码。

核心运行配置包括：

```text
SECTION_ENABLE_SONGFORMER=true
SECTION_SONGFORMER_DEVICE=cuda
SECTION_SONGFORMER_PRECISION=float32
SECTION_SONGFORMER_TIMEOUT_SEC=1800
SECTION_SONGFORMER_SOURCE_ROOT=/opt/harbeat/models/SongFormer
SECTION_SONGFORMER_MUQ_MODEL=/opt/harbeat/models/MuQ-MuLan-large
SECTION_SONGFORMER_WORK_DIR=/mnt/nas/harbeat/cache/songformer-analysis
SECTION_RELABELER_ENABLED=false
SECTION_RELABELER_SHADOW_MODE=true
```

残差分类器即使没有模型文件也必须返回明确状态，不允许静默启用或把候选标签写成人工真值。

## 6. SongFormer 输出合同

每个原始段落至少保留：

```json
{
  "start": 31.84,
  "end": 48.12,
  "boundary_source": "songformer",
  "songformer_label": "verse",
  "structure_label_candidate": "verse",
  "structure_label_probabilities": {
    "intro": 0.02,
    "verse": 0.71,
    "chorus": 0.10,
    "bridge": 0.03,
    "instrumental": 0.06,
    "outro": 0.01,
    "silence": 0.01,
    "pre-chorus": 0.06
  },
  "structure_label_confidence": 0.71,
  "structure_label_margin": 0.61,
  "label_status": "candidate"
}
```

`start` 和 `end` 是模型原始时间，任何标签修正组件都不得修改它们。阶段三只消费边界和来源信息；结构标签与概率用于质量检查和未来残差分类器。

## 7. 段落边界转标注块

### 7.1 权威时间轴

Bar 网格只由现有 Beat、Downbeat 和拍号分析生成，不读取 SongFormer 的 `intro` 或其他语义标签。每个 Bar 具有稳定的 `bar_index`、`start_time` 和 `end_time`。

### 7.2 吸附算法

1. 校验 SongFormer 段落按时间单调、无负时长且覆盖范围不超过音频长度。
2. 歌曲首尾固定映射到第一个和最后一个可标注 Bar 边界。
3. 每个内部 SongFormer 边界选择时间距离最近的 Bar 边界。
4. 保存原始时间、吸附时间、误差秒数和局部 Bar 时长。
5. 吸附误差超过 `min(1.5 秒, 0.35 × 局部 Bar 时长)` 时，标记该边界 `needs_review=true`，但仍生成可编辑候选块。
6. 多个边界吸附到同一 Bar 时去重，不生成零长度块；被抑制的原始边界写入诊断信息。
7. 输出块使用半开区间 `[start_bar_index, end_bar_index)`，避免相邻块重复包含边界 Bar。

### 7.3 标注块合同

```json
{
  "block_id": "稳定且可重建的标识",
  "start_bar_index": 9,
  "end_bar_index": 14,
  "start_time": 31.62,
  "end_time": 48.40,
  "source": "songformer_bar_snap_v1",
  "source_segment_indexes": [2],
  "raw_start_time": 31.84,
  "raw_end_time": 48.12,
  "start_snap_error_sec": 0.22,
  "end_snap_error_sec": 0.28,
  "needs_review": false,
  "model_runtime_fingerprint": "...",
  "annotation_state": "unlabeled"
}
```

`block_id` 由歌曲标识、Bar 范围和边界模型指纹稳定生成。模型重跑后不直接覆盖已有人工标注；如果边界版本变化，生成新的候选块版本并保留旧人工数据供迁移或比较。

## 8. 标注行为

- 打开歌曲时，默认选中当前未完成的 SongFormer 标注块。
- 点击人声、鼓、贝斯或其他/旋律，将同一标签写入块内全部 Bar。
- 标注者可在块内重新选择较小 Bar 范围，形成局部覆盖。
- 标注者可拆分或合并候选块；人工修改后的边界优先级高于模型候选。
- 页面显示当前块的小节范围、原始 SongFormer 时间、吸附误差和是否需要复核。
- 自动保存继续按用户独立存储，所有用户看到相同歌曲和候选块，但人工标注互不覆盖。
- 汇总时保留用户、候选块版本和每次人工覆盖来源。

标注状态的优先级为：

```text
人工局部覆盖 > 人工块标注 > SongFormer 候选块 > 未分析
```

## 9. 播放模式修复

播放器增加明确的播放模式状态：

- `full`：用户点击原生播放键后连续播放，不因当前选区结束而暂停。
- `range_preview`：用户点击“试听所选范围”后，从选区起点播放，并在选区终点暂停。
- `range_loop`：用户开启“循环所选”后，仅循环当前范围。

只有后两种模式可以读取选区终点并主动暂停。切换歌曲、改变选择范围或手动拖动进度时，需要清除已经失效的范围播放状态。

## 10. 残差分类器预留接口

当前运行状态固定为：

```json
{
  "enabled": false,
  "mode": "disabled",
  "model_status": "not_installed",
  "model_version": null,
  "input_contract_version": "songformer_section_relabeler_input_v1",
  "output_contract_version": "songformer_section_relabeler_output_v1"
}
```

未来分类器接收 SongFormer 当前段落及相邻段落的八类概率、候选标签、时长、位置、置信度、margin 和熵等特征，输出原标签、建议标签、覆盖与否、置信度和模型版本。接口必须遵守两个约束：

1. 只能修正 `structure_label_candidate`，不能修改 `start`、`end` 或 Bar 标注块边界。
2. 权重缺失、损坏、合同不匹配或精度验收失败时采用 fail-closed，保留 SongFormer 原始候选。

后续训练完成后，只需部署验证通过的 JSON 模型并切换环境配置；阶段三标注块和人工标签无需迁移。

## 11. 失败、回退与可观测性

- SongFormer 超时、进程退出、输出损坏或模型指纹不完整时，歌曲状态设为 `songformer_failed`。
- 阶段三标注块不得将 All-In-One 或固定长度切分标为 SongFormer 结果；默认进入人工划分。
- 原有分析链路若仍需要 All-In-One 回退，可以继续保存，但来源必须明确，不自动提升为权威标注块。
- 每次运行记录音频内容摘要、模型 Checkpoint 摘要、源码版本、运行器版本、设备、精度、耗时、缓存命中和错误摘要。
- 标注页能够区分 `ready`、`needs_review`、`failed` 和 `not_analyzed`。

## 12. 发布与数据安全

1. 新建独立 SongFormer 虚拟环境和模型目录，不污染现有 API Python 环境。
2. 先在 Jetson 命令行对一首短歌和一首完整歌曲完成推理验收。
3. 再发布包含边界转块、接口和播放修复的新版本目录。
4. 仅通过新增的服务配置指向新版本和模型路径。
5. 不删除旧 release，不修改持久化标注目录，不批量重写已有 JSON。
6. 健康检查、登录注册、原网站、`/annotate` 和已有 API 全部通过后才批量处理歌曲。
7. 回滚只切换服务工作目录和配置，已生成的模型缓存可以保留，人工标注不回滚。

## 13. 验收标准

### 13.1 模型与边界

- Jetson CUDA 成功完成至少两首歌曲的 SongFormer 推理。
- 每个输出段落包含合法起止时间、来源和运行时指纹。
- 模型按顺序加载，完整歌曲推理期间不发生 GPU OOM。
- 相同音频和相同模型重跑能够命中缓存。

### 13.2 标注块

- 所有候选块边界均落在真实 Bar 边界上。
- 不产生重叠、负长度或零长度块。
- 高吸附误差和边界去重均有明确复核信息。
- 整块赋值、局部 Bar 覆盖、拆分、合并和自动保存均通过测试。
- 原有人工标注在部署前后字节级保持不变，除非标注者主动保存新修改。

### 13.3 播放与网页

- 普通播放超过第一个选区结束时间后仍继续播放。
- “试听所选范围”在范围终点准确停止。
- 循环所选只在明确启用时循环。
- 原网站、登录、注册、共享歌曲列表、独立标注和汇总接口不回归。

### 13.4 残差分类器接口

- 未安装权重时状态明确为禁用，不更改任何候选标签。
- 接口合同具备版本号并保留完整输入证据。
- 后续启用分类器不需要改变 SongFormer 边界、标注块合同或已有人工标注。

## 14. 实施顺序

1. 固化接口和边界转块测试。
2. 获取并校验官方 SongFormer、MusicFM 和 MuQ 模型资产。
3. 建立 Jetson 隔离运行环境并完成单曲推理。
4. 接入后端分析和标注块生成。
5. 更新标注页的按块交互并修复播放模式。
6. 本地自动化测试与浏览器回归测试。
7. Jetson 版本化发布和两首歌曲冒烟验证。
8. 经人工确认边界后，批量生成剩余歌曲的候选标注块。
