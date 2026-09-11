# HarBeat EDM 预处理结果交付与读取说明 v1

> 面向接歌与混音算法协作者。本文只定义 HarBeat 已经生成的数据、音频资产及其读取方式，不规定接歌排序、转场选择、效果器或混音算法。

## 1. 本次交付范围

本次固定使用人工确认的 `EDM` 风格组，共 8 首歌。HarBeat 已在 Jetson 上完成预处理，并将不可变的分析 Run 发布到 NAS。

协作者不需要运行 SongFormer、Demucs 或 MDX23C，也不需要访问 HarBeat 数据库。协作者只需要读取 EDM 索引、每首歌的 Manifest，以及 Manifest 引用的音频资产。

本次交付提供：

- 原始 Master 音频。
- BPM、Beat、Downbeat、Bar 和拍号。
- SongFormer 段落边界与段落标签。
- Key、Camelot、能量曲线和预处理生成的候选过渡窗口。
- Demucs 的 vocals、drums、bass、other 四轨。
- MDX23C 的 kick、snare、hihat、tom、cymbal 五个鼓组子轨。
- Kick、Snare/Clap、Hi-hat、Bass/808、Percussion 的事件数量、类别和 16 步落点摘要。
- 每个分析模块的版本、状态和质量标记。

本次交付不提供也不约束：

- 接歌候选排序算法。
- 两首歌的进出点组合算法。
- Tempo/key/energy 的匹配权重。
- Time-stretch、pitch-shift、EQ、FX、crossfade 或 stem mixing 算法。
- 最终音频渲染方式。
- 已校准的 Pair Score 自动决策。当前 70%/85% 阈值尚未完成独立测试集校准。

## 2. 数据权威入口

协作者机器需要能访问同一个 NAS。先配置该机器上的实际挂载根目录：

```bash
export HARBEAT_PREPROCESS_ROOT=/mnt/nas/harbeat/preprocess
```

如果 NAS 在协作者机器上挂载到其他位置，只修改这个环境变量；JSON 内没有写死 Jetson 绝对路径。

本次 EDM 冻结索引：

```bash
export HARBEAT_LIBRARY_INDEX="$HARBEAT_PREPROCESS_ROOT/published/indexes/edm_8_handoff_v1.json"
```

权威读取链路：

```text
edm_8_handoff_v1.json
  -> item.manifest_storage_key
  -> manifest.json
  -> 同一 Run 的 _SUCCESS.json
  -> manifest.assets.*.storage_key
  -> Master、Demucs 四轨和 MDX23C 五轨
```

不要从 `staging/`、`locks/`、`failed/` 或历史烟测目录读取数据。不要根据歌曲文件名猜测资产路径。

## 3. 本次 EDM 歌曲

| track_id | 艺人 | 标题 |
| --- | --- | --- |
| `track-b36fb933dcd2d9cff436` | Alan Walker | The Spectre |
| `track-0a1c8c54ff45b04f1568` | Alan Walker, Noah Cyrus, Digital Farm Animals | All Falls Down |
| `track-274577b1e51f104f4658` | Arc North, Krista Marina | Meant To Be |
| `track-8d55cb314b5aff07d3ac` | Marshmello | Alone |
| `track-8c616fddb7ca97986acc` | Martin Garrix, Bebe Rexha | In the Name of Love |
| `track-f4219339062cac4ce823` | Mr. Polska | Move Up (Lost Gravity) |
| `track-f83cf73c441f8e96e0d5` | The Chainsmokers, Halsey | Closer |
| `track-aab34351ca8529caf4f2` | Vicetone, Cozi Zuehlsdorff | Nevada |

索引内每首歌的 `style_labels` 都包含 `EDM`。该标签来自人工目录，不是模型预测结果。

## 4. EDM 索引格式

索引 Schema：

```text
contracts/schemas/analysis/same-style-library-index-v1.schema.json
```

当前索引版本：

```text
schema_name    = same_style_library_index
schema_version = 1.0.0
total_tracks   = 8
```

协作者主要读取：

| 字段 | 含义 |
| --- | --- |
| `track_id` | 稳定歌曲主键，后续结果应引用它 |
| `analysis_run_id` | 本次不可变分析 Run 的标识 |
| `artist` / `title` | 人工识别用歌曲信息 |
| `style_labels` | 人工风格标签；本次必须包含 `EDM` |
| `status` | `ready`、`degraded` 或不可用状态 |
| `manifest_storage_key` | 相对 NAS 根目录的单曲 Manifest 路径 |
| `input_sha256` | 原始歌曲内容指纹 |
| `error` | 分析失败信息；正常完成时为 `null` |

`manifest_storage_key` 的解析方式：

```python
manifest_path = HARBEAT_PREPROCESS_ROOT / manifest_storage_key
```

它是相对路径，禁止接受绝对路径或含 `..` 的路径。

## 5. 单曲 Manifest 格式

单曲 Schema：

```text
contracts/schemas/analysis/same-style-track-preprocess-v1.schema.json
```

当前单曲版本：

```text
schema_name     = same_style_track_preprocess
schema_version  = 1.2.0
contract_version = same-style-preprocess-v1.2
```

注意：曲库索引版本 `1.0.0` 与单曲 Manifest 版本 `1.2.0` 是两个独立 Schema 的版本号，不是数据不一致。

### 5.1 身份与可复现信息

| JSON 路径 | 内容 |
| --- | --- |
| `track_id` | 歌曲稳定主键 |
| `analysis_run_id` | 当前 Manifest 对应的不可变 Run |
| `source.input_sha256` | Master 输入内容 SHA256 |
| `source.original_filename` | 原始文件名 |
| `source.title` / `source.artist` | 标题和艺人 |
| `source.duration_ms` | 歌曲时长，整数毫秒 |
| `source.style_labels` | 人工风格标签 |
| `pipeline.git_sha` | 生成该结果的代码版本 |
| `pipeline.*` | SongFormer、Demucs、MDX23C 和鼓事件实际执行路线 |

本批 EDM 的 `pipeline.git_sha` 为：

```text
a268a5c04791ee506bbf22a3e66557dcdd0272d2
```

### 5.2 Tempo 与节拍网格

| JSON 路径 | 内容 |
| --- | --- |
| `analysis.tempo.bpm` | BPM |
| `analysis.tempo.confidence` | BPM 置信度，范围 0–1 |
| `analysis.tempo.stability` | Tempo 稳定度，范围 0–1，可为空 |
| `analysis.tempo.needs_review` | 是否建议人工检查 |
| `analysis.beat_grid.beats_ms` | 每个 Beat 的整数毫秒位置 |
| `analysis.beat_grid.downbeats_ms` | Downbeat 的整数毫秒位置 |
| `analysis.beat_grid.bars_ms` | 小节起点的整数毫秒位置 |
| `analysis.beat_grid.time_signature` | 拍号分子和分母 |
| `analysis.beat_grid.needs_review` | 节拍网格是否建议人工检查 |

所有时间统一为整数毫秒。协作者不需要自行从音频重新检测 BPM 或 Beat。

### 5.3 SongFormer 段落

段落入口：

```text
analysis.sections
```

主要字段：

| 字段 | 内容 |
| --- | --- |
| `version` | 当前为 `songformer_sections_v1` |
| `source` | `songformer` 或明确标记的 `all_in_one_fallback` |
| `fallback_used` | 是否启用了回退结果 |
| `items[].start_ms` | 段落开始时间 |
| `items[].end_ms` | 段落结束时间 |
| `items[].label` | `intro`、`verse`、`chorus`、`pre-chorus`、`bridge`、`inst`、`outro`、`silence` 等标签 |
| `items[].confidence` | 可空置信度 |

边界和标签是预处理输出，可作为接歌算法输入；如何利用这些段落由混音协作者决定。

### 5.4 Key、能量与候选窗口

| JSON 路径 | 内容 |
| --- | --- |
| `analysis.key.name` | 调性名称，例如 `E major` |
| `analysis.key.camelot` | Camelot 编号，例如 `12B` |
| `analysis.key.confidence` | 调性置信度 |
| `analysis.energy.overall` | 全曲归一化能量 |
| `analysis.energy.curve[]` | 带 `start_ms/end_ms/value` 的局部能量曲线 |
| `analysis.transition_windows[]` | 预处理建议窗口，含 `start_ms/end_ms/role/confidence` |

`transition_windows` 只是预处理提供的候选信息，不是最终接歌决定。

### 5.5 Master、Demucs 与 MDX23C 音频资产

资产入口：

```text
assets.master
assets.stems.vocals
assets.stems.drums
assets.stems.bass
assets.stems.other
assets.drum_stems.kick
assets.drum_stems.snare
assets.drum_stems.hihat
assets.drum_stems.tom
assets.drum_stems.cymbal
```

每个资产对象都包含：

| 字段 | 内容 |
| --- | --- |
| `storage_key` | 相对 NAS 根目录的音频路径 |
| `sha256` | 音频文件 SHA256 |
| `size_bytes` | 文件大小 |
| `content_type` | 文件类型 |
| `duration_ms` | 音频时长 |
| `sample_rate_hz` | 采样率 |
| `channels` | 声道数 |

实际路径永远按以下方式解析：

```python
asset_path = HARBEAT_PREPROCESS_ROOT / asset["storage_key"]
```

不要把 `/mnt/nas/...` 绝对路径写进混音工程的持久数据。混音结果至少应保存来源歌曲的 `track_id` 和 `analysis_run_id`，保证以后可以复现。

### 5.6 鼓组摘要

入口：

```text
analysis.drum_groups
```

提供五组可读摘要：

- `kick`
- `snare_clap`
- `hihat`
- `bass_808`
- `percussion`

每组包含：

| 字段 | 内容 |
| --- | --- |
| `present` | 是否检测到该组 |
| `event_count` | 事件数量 |
| `subtypes` | 可解释子类别 |
| `pattern_16` | 16 步主要落点摘要 |
| `status` | 该组数据状态 |

如需直接处理鼓音频，应优先读取 `assets.drum_stems.*`；`analysis.drum_groups.*` 是事件和节奏摘要，不是音频。

## 6. 完整性校验

每首歌开始使用前必须完成：

1. 读取索引中的 `manifest_storage_key`。
2. 计算 `manifest.json` 的 SHA256，并与该歌曲 `latest.json` 中的 `manifest_sha256` 比较。
3. 确认 Manifest 同目录存在 `_SUCCESS.json`。
4. 确认 `_SUCCESS.json` 的 `analysis_run_id` 和 `manifest_sha256` 与 Manifest/Pointer 一致。
5. 对实际使用的音频资产校验 `size_bytes` 和 `sha256`。
6. 拒绝绝对 `storage_key`、包含 `..` 的路径和 `status=unavailable` 的歌曲。

单曲 Pointer 固定位置：

```text
$HARBEAT_PREPROCESS_ROOT/published/tracks/<track_id>/latest.json
```

不要只依赖索引中的状态；真正使用前仍应完成 `latest.json -> manifest.json -> _SUCCESS.json` 校验。

## 7. 当前质量状态

截至本次冻结，8 首 EDM 均已成功发布，共有 Master 1 个、Demucs 4 轨和 MDX23C 5 轨，即每首 10 个音频资产。

8 首歌当前都显示 `status=degraded`，但以下必需模块均为 `ready`：

```text
quality.modules.core             = ready
quality.modules.sections         = ready
quality.modules.stem_separation  = ready
quality.modules.mdx23c           = ready
```

降级集中在鼓事件摘要：

```text
quality.modules.drum_groups = degraded
```

已知质量标记包括：

```text
bass_pitch_spectral_fallback_used
dedicated_drum_model_unavailable
percussion_uses_spectral_drum_proxy
spectral_proxy_fallback
```

原因是本批次按要求没有运行 ADTOF，鼓事件使用频谱回退。它不表示 BPM、SongFormer 段落、Demucs 四轨或 MDX23C 五轨文件生成失败。

本次专家接歌测试可以使用这 8 首歌，但协作者应保留 `quality_flags`，不要把鼓事件摘要当成已经完成独立数据校准的绝对真值。

## 8. 最小读取示例

以下示例从已经挂载的 NAS 读取 EDM 索引和 Manifest，并输出每首歌可用的资源路径。它不包含任何混音逻辑。

```python
import hashlib
import json
import os
from pathlib import Path


root = Path(os.environ["HARBEAT_PREPROCESS_ROOT"]).resolve()
index_path = Path(os.environ.get(
    "HARBEAT_LIBRARY_INDEX",
    root / "published/indexes/edm_8_handoff_v1.json",
))


def resolve_storage_key(storage_key: str) -> Path:
    relative = Path(storage_key)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe storage_key: {storage_key}")
    result = (root / relative).resolve()
    if root not in result.parents:
        raise ValueError(f"storage_key escapes root: {storage_key}")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


index = json.loads(index_path.read_text(encoding="utf-8"))
if index["schema_name"] != "same_style_library_index":
    raise ValueError("unsupported library index")
if index["total_tracks"] != 8:
    raise ValueError("EDM frozen index must contain 8 tracks")

for item in index["items"]:
    if "EDM" not in item["style_labels"]:
        raise ValueError(f"non-EDM item: {item['track_id']}")

    manifest_path = resolve_storage_key(item["manifest_storage_key"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    pointer_path = root / "published/tracks" / item["track_id"] / "latest.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if sha256(manifest_path) != pointer["manifest_sha256"]:
        raise ValueError(f"manifest hash mismatch: {item['track_id']}")

    success_path = manifest_path.parent / "_SUCCESS.json"
    success = json.loads(success_path.read_text(encoding="utf-8"))
    if success["analysis_run_id"] != manifest["analysis_run_id"]:
        raise ValueError(f"run mismatch: {item['track_id']}")
    if success["manifest_sha256"] != pointer["manifest_sha256"]:
        raise ValueError(f"success hash mismatch: {item['track_id']}")

    assets = manifest["assets"]
    paths = {
        "master": resolve_storage_key(assets["master"]["storage_key"]),
        **{
            f"stem_{name}": resolve_storage_key(asset["storage_key"])
            for name, asset in assets["stems"].items()
        },
        **{
            f"drum_{name}": resolve_storage_key(asset["storage_key"])
            for name, asset in assets["drum_stems"].items()
            if name != "status" and asset is not None
        },
    }

    print(item["track_id"], item["artist"], "-", item["title"])
    for name, path in paths.items():
        print(f"  {name}: {path}")
```

## 9. 将资源复制到协作者本机

推荐方式是直接挂载 NAS 并按 `storage_key` 读取。如果协作者只获得 Jetson SSH 访问，可以先复制冻结索引，再按索引列出的 Run 目录复制；SSH 主机名、账号和密钥由项目负责人单独提供，不写入仓库。

示例：

```bash
export JETSON_HOST='<已授权的SSH主机>'
mkdir -p edm_8_bundle/published/indexes

rsync -a \
  "$JETSON_HOST:/mnt/nas/harbeat/preprocess/published/indexes/edm_8_handoff_v1.json" \
  edm_8_bundle/published/indexes/

jq -r '.items[] | [.track_id, .manifest_storage_key] | @tsv' \
  edm_8_bundle/published/indexes/edm_8_handoff_v1.json |
while IFS=$'\t' read -r track_id manifest_key; do
  run_key="$(dirname "$manifest_key")"
  mkdir -p "edm_8_bundle/published/tracks/$track_id"
  mkdir -p "edm_8_bundle/$run_key"
  rsync -a \
    "$JETSON_HOST:/mnt/nas/harbeat/preprocess/published/tracks/$track_id/latest.json" \
    "edm_8_bundle/published/tracks/$track_id/latest.json"
  rsync -a \
    "$JETSON_HOST:/mnt/nas/harbeat/preprocess/$run_key/" \
    "edm_8_bundle/$run_key/"
done
```

复制后配置：

```bash
export HARBEAT_PREPROCESS_ROOT="$PWD/edm_8_bundle"
export HARBEAT_LIBRARY_INDEX="$HARBEAT_PREPROCESS_ROOT/published/indexes/edm_8_handoff_v1.json"
```

上述命令会同时复制每首歌的 `latest.json`，因此可以执行与 NAS 直读相同的完整 Pointer 校验。

## 10. 协作者产物与问题反馈

混音输出不得写入：

```text
$HARBEAT_PREPROCESS_ROOT/published/tracks/
```

建议混音方使用独立目录，并在自己的结果元数据中至少记录：

- 输入 A/B 的 `track_id`。
- 输入 A/B 的 `analysis_run_id`。
- 实际使用的 Master/stem `sha256`。
- 自己的算法版本与参数版本。

发现预处理问题时，请反馈：

- `track_id`。
- `analysis_run_id`。
- `pipeline.git_sha`。
- 出错的 JSON 字段或 `storage_key`。
- `quality_flags`。
- 预期结果与实际结果。

预处理方修复后会生成新的 `analysis_run_id`，不会原地修改旧 Run。

## 11. 后续扩展到其他风格

混音方的读取代码应接收“索引路径”作为输入，不要把 EDM 的 8 个 `track_id` 写死在算法里。

当前：

```text
index = published/indexes/edm_8_handoff_v1.json
style = EDM
```

未来 KPOP、Afrobeats 等风格完成分析后，只替换风格索引；单曲 Manifest、音频资产结构、毫秒时间单位和校验流程保持一致。混音算法无需运行任何预处理模型。

## 12. 仓库合同文件

- 总体协作合同：`docs/same_style_mixing_collaborator_handoff_v1.md`
- 本次 EDM 交付说明：`docs/edm_preprocess_delivery_for_mixing_v1.md`
- 曲库索引 Schema：`contracts/schemas/analysis/same-style-library-index-v1.schema.json`
- 单曲 Manifest Schema：`contracts/schemas/analysis/same-style-track-preprocess-v1.schema.json`
- 单曲示例：`contracts/fixtures/analysis/same-style-track-preprocess-v1.ready.json`
