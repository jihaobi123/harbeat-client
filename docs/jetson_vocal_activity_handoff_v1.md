# Jetson 人声时间标记与协作者交付 v1

## 本次增加什么

在现有 BPM、SongFormer、Demucs、MDX23C 预处理旁增加 **Silero VAD 人声时间标记**。
输入固定为已有的 Demucs `vocals.wav`，不是原曲，也不是再次分离音频。
现有全部歌曲补做该阶段；新歌通过 `run_same_style_preprocess.py` 自动执行。
不启用 ADTOF，不改段落识别，不实现混音算法。

计算在 Jetson；结果写 NAS 的 `/mnt/nas/harbeat/preprocess`。
每个模型在 CPU 上单线程执行，批量默认最多 3 首并行，每个线程独占模型以隔离时序状态。
可用 `--workers 1` 改为串行。复用现有 NVIDIA PyTorch，避免替换 CUDA 环境。

## 与原交付合同的兼容

基础 manifest 保持 `same_style_track_preprocess 1.2.0`，旧 run、`latest.json`、
`_SUCCESS.json`、音频和原 EDM ZIP 均不修改。
新增的 **vocal_activity 1.0.0 补充合同**通过基础 manifest SHA256、track_id、run_id、
人声音轨 SHA256 精确关联。协作者原读取代码继续可用；需要人声时间时增加一次读取。
旧 ZIP 本身不含本次结果；需另取补充包或从 NAS 读取。

## 协作者从哪里读

根目录环境变量：`HARBEAT_PREPROCESS_ROOT=/mnt/nas/harbeat/preprocess`。
根目录也可以指向完整离线交付包解压位置。

全曲库人声索引：
`published/indexes/style_library_vocal_activity_v1.json`

EDM 原 8 首快照的人声索引（单独生成）：
`published/indexes/edm_8_vocal_activity_v1.json`

索引 `items[]` 包含 `track_id`、`analysis_run_id`、`manifest_storage_key`、
`manifest_sha256`、`vocal_storage_key`、`vocal_sha256`、
`vocal_activity_storage_key`、`vocal_activity_sha256`、`status`、`error`。
失败项不提供可消费的成功结果。批量执行中 `processed_tracks < total_tracks`，不能视为完成。

单曲结果的位置是：
`published/vocal_activity/<track_id>/<analysis_run_id>/<revision>/vocal_activity.json`

同级 `_SUCCESS.json` 保存报告 SHA256，父层 `latest.json` 指向该 run 的最新人声报告。
`revision` 是输入绑定信息、模型、参数和实现版本的内容哈希；改变模型/参数会创建新版本。
不要只按歌名关联，也不要把另一 run 的时间标记混用。

## 输出格式

```json
{
  "schema_name": "harbeat_vocal_activity",
  "schema_version": "1.0.0",
  "status": "ready",
  "unit": "ms",
  "time_origin": "master_audio_start",
  "interval_convention": "[start_ms,end_ms)",
  "duration_ms": 240000,
  "intervals": [
    {"start_ms": 12000, "end_ms": 18500},
    {"start_ms": 20000, "end_ms": 31000}
  ],
  "has_vocals": true,
  "active_duration_ms": 17500,
  "coverage_ratio": 0.0729166667,
  "needs_review": true
}
```

以上为说明用节选，真实报告另有 `generated_at`、`source`、`producer`、`quality_flags`。
`source` 包含上述基础输入绑定；`producer` 记录包版本、权重 SHA256、运行后端、参数。
完整机器可读格式见 `contracts/schemas/analysis/vocal-activity-v1.schema.json`。

- 时间从原曲第 0 秒起算，不以段落起点计时；区间按时间排序、不重叠，左闭右开。
- `ready + intervals=[]` 表示运行成功、没有检出；`failed` 表示没有可靠可用的结果。
- `coverage_ratio` 只是检出时长占比，**不是准确率或置信度**。
- 检出范围包括可能的歌唱、说唱、和声等；不区分主唱/伴唱、歌词、说话者。
- Silero 原本是语音 VAD，对唱歌和 Demucs 残留仍可能漏检/误检。
  `ready` 只表示计算和发布成功，不代表人工验收准确；因此保留 `needs_review=true`。

## 固定推理配置

Silero VAD `6.2.1`，随包的 TorchScript 权重，CPU，16 kHz 单声道。
多声道取均值，使用 `scipy.signal.resample_poly` 重采样，不做逐曲增益归一化。
进入阈值 0.5，退出阈值 0.35，最短检出 250 ms，最短静音 300 ms，边缘扩展 100 ms。
直接接收模型的采样点索引再转毫秒，避免默认秒数输出按 0.1 秒四舍五入。
短间隙可能被合并；这不是逐字定位，也不保证边缘误差小于 100 ms。

## Jetson 部署与补分析

在已部署的 NVIDIA Python 环境提供 `silero-vad==6.2.1` 包，**不要升级现有 torch/torchaudio**。
可用 `pip install --no-deps --target /opt/harbeat/runtime/preprocess-packages -r deploy/jetson/requirements-vocal-activity.txt`。
随包包含模型，无需运行时联网拉权重。既有 soundfile、scipy、torch、torchaudio 必须可导入。

将部署包装脚本安装为 `/usr/local/bin/harbeat-vocal-activity-backfill`，安装对应 systemd unit 后执行：

```bash
systemctl start --no-block harbeat-vocal-activity-backfill.service
journalctl -u harbeat-vocal-activity-backfill.service -f
```

该服务只读取已发布的基础 manifest/人声 WAV，写新增人声目录和人声索引。
无需源曲重新下载，也不重跑 SongFormer、Demucs 或 MDX23C。
失败项记入索引并继续处理其他歌；结束时有失败则返回非零。
重跑复用已校验的成功结果，只补缺失或新版本。不要并行启动相同索引的作业。

EDM 原快照单独生成：

```bash
harbeat-vocal-activity-backfill \
  --index published/indexes/edm_8_handoff_v1.json \
  --output published/indexes/edm_8_vocal_activity_v1.json
```

后续新歌由单曲 CLI 自动补做人声检测；导入包装脚本结束后刷新全库人声索引。
底层基础发布函数仍只处理基础合同。直接调用它的其他入口必须显式调用
`publish_vocal_activity`，不能把基础 manifest 的 ready/degraded 当成人声完成。

批量完成后可执行 `preprocessing/cli/finalize_vocal_activity.py --root /mnt/nas/harbeat/preprocess`。
它会验证全部报告的 Schema、SHA256、基础 run 关联、时间顺序和时长统计，
再生成 JSON-only 增补 ZIP。结果回执：
`/mnt/nas/harbeat/preprocess/reports/vocal_activity/latest_delivery.json`，
其中记录实际包路径、SHA256、验证歌曲数量。
这些是数据完整性验证，不是人工精度评估。

## 读取示例

```python
import hashlib, json, os
from pathlib import Path

root = Path(os.environ["HARBEAT_PREPROCESS_ROOT"])
index = json.loads((root / "published/indexes/edm_8_vocal_activity_v1.json").read_text())
for item in index["items"]:
    if item["status"] != "ready":
        continue
    raw = (root / item["vocal_activity_storage_key"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item["vocal_activity_sha256"]
    base = (root / item["manifest_storage_key"]).read_bytes()
    assert hashlib.sha256(base).hexdigest() == item["manifest_sha256"]
    report = json.loads(raw)
    for span in report["intervals"]:
        print(item["track_id"], span["start_ms"], span["end_ms"])
```

协作者仅需文件只读权限，不需要数据库或 NAS 写入权限。
