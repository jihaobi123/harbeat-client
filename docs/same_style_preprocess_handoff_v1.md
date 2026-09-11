# 同风格接歌：Jetson 预处理与混音协作合同 v1.2

> v1.2 增加人工目录标签 `source.style_labels`、曲库索引和可断点续跑的 ZIP 入库工具。当前曲库批次按要求禁用 ADTOF；MDX23C 鼓组分离不受影响。Pair Score 合同未改变。

## 1. 目标与边界

调用方只向预处理系统提供同风格歌曲。本合同不包含风格识别、候选风格判断或混音算法。

预处理团队负责在 Jetson 上生成可复现、带版本和质量状态的歌曲分析及音频资产，并发布到 NAS。混音团队只读取已经发布的 Manifest、分析字段和音频资产，不调用 SongFormer、Demucs、MDX23C，也不依赖算法内部 Python 对象、数据库列名或 Jetson 本地绝对路径。

```text
同风格歌曲 + track_id
        |
        v
Jetson 预处理 Worker
  Core -> Demucs -> Stem features（本批次不运行 ADTOF） -> MDX23C -> Drum groups
        |
        v
NAS staging -> 校验 Schema/时长/大小/SHA256 -> 原子发布
        |
        v
Track Manifest + Pair Score
        |
        v
混音协作者只读消费
```

## 2. 远端现有模块与真实完成度

远端分支：`archive/music-analysis-history-20260830`。

| 模块 | 版本/入口 | 当前状态 | 是否已形成统一 NAS 交付物 |
| --- | --- | --- | --- |
| BPM、Beat、Downbeat、拍号、小节、Key、能量 | `app/modules/library/analysis.py` | Jetson 真实音频验收通过 | 是；发布到单曲 Manifest |
| SongFormer 段落 | `songformer_sections_v1` | 正式段落来源；失败才回退 All-In-One；Jetson 验收 `fallback_used=false` | 是；含来源和回退状态 |
| Demucs 四轨 | `htdemucs` | Jetson CUDA 验收通过 | 是；四轨资产均带探测信息和 SHA256 |
| Stem 活动、Bass 风险、鼓事件 | `stem_analysis.py`、频谱回退路线 | 本批次按要求禁用 ADTOF，并在 Manifest 记录实际引擎 | 是；统一进入鼓组和质量字段 |
| Rhythm/Bass/Percussion 特征 | `rhythm_grammar_features_v5`、`bass_features_v5`、`percussion_timbre_features_v3` | 已由 Stem 特征链生成；验证状态混合 | 是；面向混音的五组摘要进入 Manifest |
| MDX23C 鼓组细分 | `music_analysis/drum_analysis/mdx23c_separator.py` | Jetson CUDA 验收通过 | 是；五个鼓组子轨进入 Manifest |
| 鼓组 Pair Score | `drum_pair_similarity_v2` | 类别分、落点分、权重、阈值路由、缓存已实现 | 否；尚未用真实人工 pair 完成 70%/85% 校准，也未接入正式排序 |

结论：Jetson 单曲一键预处理和统一 NAS 合同已经可用。混音负责人仍不能把当前
`LibrarySong` 行或旧 `/api/manifest` 当作长期合同；权威入口是
`published/tracks/<track_id>/latest.json`。

## 3. NAS 目录合同

所有进程通过环境变量取得根目录：

```text
HARBEAT_PREPROCESS_ROOT=/mnt/nas/harbeat/preprocess
```

`/mnt/nas/...` 只是 Jetson 的推荐挂载点。JSON 和 API 内只保存相对 `storage_key`，不得写入该绝对路径。混音机器可把同一 NAS 挂载到其他位置，再用自己的 `HARBEAT_PREPROCESS_ROOT` 解析。

```text
$HARBEAT_PREPROCESS_ROOT/
  staging/
    <analysis_run_id>.<attempt_id>/
  locks/
    <track_id>.lock
  failed/
  published/
    tracks/
      <track_id>/
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
        latest.json
    pairs/
      drum_pair_similarity_v2/
        <first-two-chars-of-cache-key>/
          <cache_key>.json
    indexes/
      tracks.jsonl
      style_library_v1.json
```

规则：

- Worker 只能先写 `staging/<analysis_run_id>`。
- JSON Schema、音频时长、采样率、声道、文件大小和 SHA256 全部通过后，才原子移动到 `published`。
- `_SUCCESS.json` 最后写入；混音方只读取存在 `_SUCCESS.json` 的 Run。
- `latest.json` 是小型指针，只包含 `track_id`、`analysis_run_id`、`manifest_storage_key` 和 `manifest_sha256`，原子替换。
- 历史 Run 不覆盖；重新分析创建新的 `analysis_run_id`。
- `tracks.jsonl` 用于批量发现，不是权威结果；单曲权威入口始终是 `latest.json -> manifest.json`。

`latest.json` 固定格式：

```json
{
  "schema_name": "same_style_track_pointer",
  "schema_version": "1.2.0",
  "track_id": "track-001",
  "analysis_run_id": "run-track-001-001",
  "manifest_storage_key": "published/tracks/track-001/runs/run-track-001-001/manifest.json",
  "manifest_sha256": "<64位小写sha256>",
  "published_at": "2026-09-10T08:00:00Z"
}
```

`_SUCCESS.json` 固定格式：

```json
{
  "analysis_run_id": "run-track-001-001",
  "manifest_sha256": "<64位小写sha256>",
  "asset_count": 10,
  "published_at": "2026-09-10T08:00:00Z"
}
```

数据库只保存任务状态、`track_id -> latest analysis_run_id` 和 Manifest storage key，NAS 保存不可变的完整 JSON 与媒体资产。迁移期间可以数据库/NAS双写，但混音协作者不得直接依赖 `LibrarySong` 字段。

## 4. 混音方唯一需要读取的格式

### 4.1 单曲 Manifest

Schema：`contracts/schemas/analysis/same-style-track-preprocess-v1.schema.json`。

示例：`contracts/fixtures/analysis/same-style-track-preprocess-v1.ready.json`。

关键内容：

- 身份：`track_id`、`analysis_run_id`、原文件名、标题、艺人、人工风格标签和源文件 SHA256。
- 版本：Git SHA、Core/SongFormer/Demucs/MDX23C/鼓组特征版本。
- 音频：Master、Demucs 四轨、MDX23C 五轨的 `storage_key + sha256 + size_bytes + 音频格式`。
- 节奏：BPM、Beat、Downbeat、Bar、拍号，统一使用整数毫秒。
- 段落：SongFormer 边界、标签、来源、是否回退。
- 音乐信息：Key/Camelot、能量和可用的过渡候选窗。
- 鼓组：Kick、Snare/Clap、Hi-hat、808/Bass、Percussion 五组的存在性、数量、subtype 和 16 步落点。
- 质量：每个模块的 `ready/degraded/unavailable` 与 `quality_flags`。

混音方不得从文件名、标题或目录顺序推断分析含义。

这是发布层合同，不是当前 `analyze_audio_file()` 的原始返回值。Jetson Publisher 必须负责字段整理、秒转毫秒、资产登记、hash 和版本外壳；混音方不负责兼容当前数据库平面字段。

### 4.2 歌曲 Pair Score

Schema：`contracts/schemas/analysis/same-style-pair-score-v1.schema.json`。

示例：`contracts/fixtures/analysis/same-style-pair-score-v1.ready.json`。

Pair Score 明确声明 `style_scoring_applied=false`，包括：

- 两首歌各自使用的 `analysis_run_id` 和分析指纹。
- `category_overlap_score`。
- `rhythm_landing_similarity_score`。
- `drum_overlap_score`。
- 权重、70%/85%阈值版本、原始阈值档位。
- 质量门控后的 `proposal_action`。

当前阈值和权重为 `provisional_unvalidated`。在真实人工 Pair 独立测试集完成前，混音方可以展示和记录它，但不得把它当作已经验证的自动执行结论。

当前 `score_drum_pair()` 返回的是算法内部可解释结果。Jetson Publisher 还需要补充 `schema_name/schema_version/generated_at`，并把两首歌曲各自的 `analysis_run_id` 写入发布合同后才能落 NAS。

## 5. 状态和缺失值

公共状态只有：

- `ready`：合同所需数据齐全且通过校验。
- `degraded`：结果可供评审，但存在质量标记或缺失可选模块。
- `unavailable`：没有可用结果。

未知必须为 `null` 或 `status=unavailable`，不能用 `0`、空字符串或空鼓型伪装。

对于同风格接歌 v1：

- Core、SongFormer、Demucs 四轨是单曲发布 `ready` 的必需项。
- MDX23C 五轨和五组鼓落点是启用鼓组 Pair 自动判断的必需项。
- Style analysis 明确不是必需项，也不进入本合同。
- `source.style_labels` 是人工提供的目录标签，不是模型推断结果；本批次取音频所在的最内层小文件夹名。
- 任一输入有 `needs_review` 时，Pair 仍可给出 `raw_threshold_route`，但正式 `proposal_action` 必须是 `manual_review`。

## 6. 两方职责

### 预处理负责人

- 保证同一个 `track_id + input_sha256 + pipeline_version` 幂等。
- 运行各分析阶段、记录模型和代码版本。
- 将所有秒转换成整数毫秒后发布。
- 生成 SHA256、Schema 校验、音频探测和 `_SUCCESS`。
- 重新分析时发布新 Run，不原地修改旧 Run。
- 提供 fixture 和变更说明；破坏性字段变化必须升级 `schema_version`。

### 混音负责人

- 只从 `latest.json` 或后续统一读取 API 取得 Manifest。
- 校验 `schema_version`、`status`、`_SUCCESS`、size 和 SHA256。
- 只用 `storage_key` 解析资产，不保存 Jetson/NAS 的绝对路径。
- 遇到不支持的主版本、缺失必需资产或 `unavailable` 时拒绝该曲目。
- 可以根据 `quality_flags` 决定是否允许 degraded，但不能静默当作 ready。
- 不重新运行或修改预处理模型，不回写预处理产物；混音输出使用自己的 Run 和目录。

最小读取流程只有五步：

1. 打开 `published/tracks/<track_id>/latest.json`。
2. 用 `manifest_storage_key` 打开 Manifest，并验证 `manifest_sha256`。
3. 确认对应 Run 的 `_SUCCESS.json` 存在且 hash 一致。
4. 按 `same-style-track-preprocess-v1` 解析分析字段和资产引用。
5. 使用 `HARBEAT_PREPROCESS_ROOT / storage_key` 读取音频；任何 `..` 或绝对路径都拒绝。

## 7. 同风格接歌第一阶段实施顺序

1. 冻结本合同、两个 JSON Schema 和 ready fixture。
2. 在 Jetson 建立 `staging/published` 目录、NAS 权限和容量监控。
3. 把现有 Core、Demucs、Stem 特征适配成单曲 Manifest。
4. 把 MDX23C 接到 Demucs `drums.wav` 后，并将五轨资产纳入 Manifest。
5. 从五组资产生成事件与 16 步落点；808/Bass 同时使用 Demucs Bass。
6. 原子发布单曲 Run，再生成同风格 Pair Score。
7. 用人工审查 Pair 校准权重和70%/85%阈值。
8. 混音协作者只用 fixture 开发读取层；Jetson 跑通后替换为真实 NAS 数据，不需要修改接口。

## 8. Jetson 部署基线与验收

- 曲库入库功能基线提交：`f509fdcf251e461f03014bd6e60b86a45760812e`。
- Jetson 当前只读版本目录由 `/opt/harbeat/same-style-preprocess-current` 指向；运行时
  `pipeline.git_sha` 与该目录的 `RELEASE_GIT_SHA` 一致。
- 当前版本指针：`/opt/harbeat/same-style-preprocess-current`。
- 单曲命令：`/usr/local/bin/harbeat-same-style-preprocess`。
- 生产发布根：`/mnt/nas/harbeat/preprocess`。
- 模型缓存：`/mnt/nas/harbeat/models`；通用缓存：`/mnt/nas/harbeat/cache`。
- v1.1 部署时的实际验收 Manifest（历史烟测，仅用于说明验收方式）：
  `/mnt/nas/harbeat/preprocess-smoke-final-b976942/published/tracks/real-smoke-final-b976942-2/runs/run-real-smoke-final-b976942-2-c8cbed514bbe-b976942/manifest.json`。

该验收样本生成了 4 个 SongFormer 段落、94 个 Beat、23 个 Bar、Demucs 四轨、MDX23C
五轨，以及 Kick/Snare/Hi-hat/Bass/Percussion 事件。重复提交同一输入在 1 秒内返回同一
`analysis_run_id`，没有新增 staging。现有 `harbeat-api.service` 未切换版本或重启。

验收样本的总状态为 `degraded`，但 Core、SongFormer、Demucs 和 MDX23C 均为 `ready`。
降级来自 `bass_pitch_spectral_fallback_used` 和
`drum_model_has_no_matching_heldout_validation`；这表示需要人工质量复核，不表示资产缺失。

## 9. 曲库批量入口

三个 ZIP 的可恢复入库状态与协作者索引分别是：

```text
/mnt/nas/harbeat/library-imports/2026-09-10/state/library.json
/mnt/nas/harbeat/preprocess/published/indexes/style_library_v1.json
```

`style_library_v1.json` 为全量快照，包含 `track_id`、`style_labels`、状态和完成后的
`manifest_storage_key`。Schema 为
`contracts/schemas/analysis/same-style-library-index-v1.schema.json`。同内容音频按 SHA256 去重，
若出现在多个目录则合并标签并保留 `duplicate_sources`。

## 10. 尚未完成、不能对协作者承诺的部分

- 自动监听 NAS 新文件尚未落地；本次 ZIP 工具已支持持久进度、失败保留和断点续跑，但不是常驻监听服务。
- 当前交付是独立单曲 CLI，不是 `background_tasks.py` 的自动阶段；这是为了与现有 API
  解耦并避免影响线上服务。
- Pair Score 尚未批量发布到 NAS，也未接入正式排序。
- 808/Bass 当前可用但允许频谱回退；Percussion 已有事件和落点，但真实曲库仍需专家抽检。
- 70%/85% 尚未经过真实独立测试集校准，不能用于无人值守自动混音决策。
- Pair Score 仍需等单曲分析完成后单独批量生成。

## 11. 单曲运行示例

```bash
sudo -u mark /usr/local/bin/harbeat-same-style-preprocess \
  /mnt/nas/harbeat/incoming/<file>.wav \
  --track-id <stable-track-id> \
  --title "<title>" \
  --artist "<artist>" \
  --style-label "<最内层小文件夹名>" \
  --disable-adtof
```

命令只在所有必需步骤、Schema 和 SHA256 校验完成后写 `_SUCCESS.json` 并更新
`latest.json`。失败尝试保留 `_FAILED.json`，不会出现在混音方的权威入口中。
