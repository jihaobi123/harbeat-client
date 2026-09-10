# HarBeat 同风格接歌：混音协作者数据接入说明 v1.1

> v1.1 在首次正式 NAS 发布前增加了歌曲原文件名、标题和艺人字段；Pair Score 格式未改变。

## 1. 这份文档解决什么问题

你负责混音，不需要运行或维护 HarBeat 的预处理模型。预处理程序会在 Jetson 上完成歌曲分析，并把已经校验的音频资产和 JSON 分析结果发布到 NAS。

你只需要：

1. 从 NAS 找到歌曲的最新分析结果。
2. 按固定 JSON 格式读取 BPM、节拍、小节、段落、能量和鼓组信息。
3. 根据 JSON 中的相对路径读取原曲、分轨和鼓组音频。
4. 把混音结果保存到你自己的输出目录，不修改预处理产物。

当前阶段只处理已经确认属于同一风格的歌曲。数据中不会再次计算或提供风格匹配分数。

## 2. 数据入口

双方各自在机器上配置 NAS 根目录：

```bash
HARBEAT_PREPROCESS_ROOT=/mnt/nas/harbeat/preprocess
```

这里的 `/mnt/nas/harbeat/preprocess` 是示例挂载点。如果你的机器把 NAS 挂载在其他目录，只需修改环境变量，不需要修改 JSON。

单曲的固定入口为：

```text
$HARBEAT_PREPROCESS_ROOT/published/tracks/<track_id>/latest.json
```

批量发现歌曲可以读取：

```text
$HARBEAT_PREPROCESS_ROOT/published/indexes/tracks.jsonl
```

`tracks.jsonl` 只用于发现歌曲。单曲结果始终以 `latest.json` 指向的 Manifest 为准。

## 3. NAS 目录结构

```text
$HARBEAT_PREPROCESS_ROOT/
  published/
    tracks/
      <track_id>/
        latest.json
        runs/
          <analysis_run_id>/
            manifest.json
            _SUCCESS.json
            audio/
              master.<ext>
              stems/
                vocals.wav
                drums.wav
                bass.wav
                other.wav
              drums/
                kick.wav
                snare.wav
                hihat.wav
                tom.wav
                cymbal.wav
    pairs/
      drum_pair_similarity_v2/
        <prefix>/<cache_key>.json
    indexes/
      tracks.jsonl

  # 以下目录由预处理 Worker 使用，混音方不读取
  staging/
  locks/
  failed/
```

每次重新分析都会生成新的 `analysis_run_id`，不会覆盖历史结果。`latest.json` 会原子更新到最新的完整 Run。

## 4. 单曲读取流程

### 第一步：读取 latest.json

```json
{
  "schema_name": "same_style_track_pointer",
  "schema_version": "1.1.0",
  "track_id": "track-001",
  "analysis_run_id": "run-track-001-001",
  "manifest_storage_key": "published/tracks/track-001/runs/run-track-001-001/manifest.json",
  "manifest_sha256": "<64位小写sha256>",
  "published_at": "2026-09-10T08:00:00Z"
}
```

### 第二步：读取 Manifest

使用：

```text
HARBEAT_PREPROCESS_ROOT / manifest_storage_key
```

得到该歌曲完整的 `manifest.json`。读取后应校验文件 SHA256 是否等于 `manifest_sha256`。

### 第三步：确认发布完成

同一 Run 目录必须存在 `_SUCCESS.json`，并且其中的 `analysis_run_id` 和 `manifest_sha256` 与前两步一致。没有 `_SUCCESS.json` 的目录可能仍在写入，不能读取。

### 第四步：读取音频资产

Manifest 内所有音频只保存相对路径，例如：

```json
{
  "storage_key": "published/tracks/track-001/runs/run-track-001-001/audio/stems/drums.wav",
  "sha256": "<64位小写sha256>",
  "size_bytes": 12345678,
  "content_type": "audio/wav",
  "sample_rate_hz": 44100,
  "channels": 2
}
```

实际文件路径为：

```text
HARBEAT_PREPROCESS_ROOT / storage_key
```

不要在程序中写死 Jetson 的 `/mnt/nas/...` 路径，也不要根据文件名猜测音频含义。

Manifest 的 `source` 同时提供 `original_filename`、可空的 `title` 和可空的 `artist`，用于人工识别歌曲；程序的稳定主键仍然是 `track_id`。

## 5. Manifest 可以提供什么

### 基础节奏

- BPM。
- Beat 时间序列。
- Downbeat 时间序列。
- Bar 起点与编号。
- 3/4、4/4 等拍号。

### 段落结构

- SongFormer 输出的段落起止时间。
- 前奏、主歌、副歌、预副歌、桥段、尾奏等标签。
- 段落来源和是否使用回退结果。

### 音乐信息

- Key 和 Camelot 编号。
- 能量与响度信息。
- 可用的过渡候选时间窗。

### 音频资产

- 原始 Master。
- Demucs：vocals、drums、bass、other 四轨。
- MDX23C：kick、snare、hihat、tom、cymbal 五个鼓组子轨。

### 鼓组信息

- Kick。
- Snare/Clap。
- Closed/Open Hi-hat。
- 808/Bass。
- Percussion。
- 各类别是否存在、事件数量、subtype 和 16 步节奏落点。

全部时间字段统一使用整数毫秒，不使用浮点秒。

## 6. 数据状态

公共状态只有三种：

| 状态 | 含义 | 建议处理 |
| --- | --- | --- |
| `ready` | 必需分析和资产齐全，校验通过 | 可以进入混音流程 |
| `degraded` | 可以读取，但有缺失模块或质量警告 | 根据 `quality_flags` 决定人工检查或继续 |
| `unavailable` | 没有可用结果 | 拒绝处理并记录原因 |

未知值会写成 `null` 或 `status=unavailable`，不会用 `0`、空字符串或空数组伪装成有效结果。

如果遇到以下情况，应停止读取该歌曲：

- 不支持的 Schema 主版本。
- 找不到 `_SUCCESS.json`。
- Manifest SHA256 不一致。
- 必需音频不存在或文件大小、SHA256 不一致。
- `storage_key` 是绝对路径或包含 `..`。
- 单曲状态为 `unavailable`。

## 7. 两首歌曲的鼓组 Pair Score

Pair Score 只用于已经确认同风格的两首歌曲，不判断音乐风格。主要字段包括：

- `category_overlap_score`：鼓组音色类别重合分。
- `rhythm_landing_similarity_score`：主要节奏落点相似分。
- `drum_overlap_score`：上述两项按版本化权重合并后的总分。
- `raw_threshold_route`：原始阈值档位。
- `proposal_action`：经过质量门控后的建议动作。
- 两首歌曲使用的 `analysis_run_id` 和分析指纹。

当前 70% 和 85% 阈值仍属于待校准参数。在完成人工 Pair 独立测试前，可以展示和记录分数，但不应把它直接当作无人值守的自动混音决定。

## 8. 固定格式与示例

- 单曲 JSON Schema：`contracts/schemas/analysis/same-style-track-preprocess-v1.schema.json`
- 单曲示例：`contracts/fixtures/analysis/same-style-track-preprocess-v1.ready.json`
- Pair Score JSON Schema：`contracts/schemas/analysis/same-style-pair-score-v1.schema.json`
- Pair Score 示例：`contracts/fixtures/analysis/same-style-pair-score-v1.ready.json`

混音读取程序应优先使用 Schema 和示例开发，不依赖当前数据库 `LibrarySong` 的字段结构。

## 9. 当前交付状态

Jetson 单曲预处理和 NAS Publisher 已部署，部署基线为
`b9769422ecc090cbca2ee136baef2335cbbe3fc1`。真实音频端到端验收已经覆盖：

- SongFormer 正式段落，且验收样本 `fallback_used=false`。
- BPM、Beat、Downbeat、Bar、拍号、Key、能量和过渡窗。
- Demucs 的 vocals、drums、bass、other 四轨。
- ADTOF 专用鼓事件识别。
- MDX23C 的 kick、snare、hihat、tom、cymbal 五个子轨。
- 五组鼓事件和 16 步落点、Schema、音频探测、SHA256、原子发布和幂等重跑。

生产曲库尚未导入；因此当前可以用仓库 fixture 开发读取层，也可以等预处理方通知具体
`track_id` 后读取 NAS 真实结果。不要读取 `staging`、`locks`、`failed` 或历史烟测目录。

以下能力不属于本次已完成交付：自动监听压缩包、持久任务队列和自动重试、断电后自动续跑、
Pair Score 的批量 NAS 发布，以及 70%/85% 阈值的真实独立测试集校准。单曲命令本身已有
排他锁、失败标记、幂等和原子发布；任务调度层仍需后续补充。

`status=degraded` 不等于文件生成失败。混音方必须查看 `quality.modules` 和
`quality_flags`：例如当前 Bass/808 频谱回退或鼓事件模型尚未匹配 held-out 校准会要求人工
复核，但只要 `_SUCCESS.json`、资产校验和必需模块成立，数据仍可用于专家评审。

## 10. 发现问题时如何反馈

请至少提供：

- `track_id`。
- `analysis_run_id`。
- Manifest 的 `pipeline.git_sha`。
- 出错字段或 `storage_key`。
- `quality_flags`。
- 预期结果和实际结果。

不要直接修改已经发布的 Run。预处理方修复后会生成新的 `analysis_run_id`，历史数据会保留以便复现和比较。
