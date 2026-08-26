# 鼓组分析模块：后端部署与验收

## 1. 当前实现

鼓组分析使用 Demucs `htdemucs` 输出的 `drums.wav`，当前协议为
`drum_transcription_consensus_v2`：

1. 优先读取专用鼓转录worker的Kick、Snare、Hi-hat、Tom、Cymbal事件；
2. 模型不可用或返回无效协议时，自动降级到原有三频段谱通量检测；
3. 使用 BPM、逐拍点和 downbeat 将事件量化到每小节16步网格；
4. 输出密度、主节奏型、稳定度、Fill候选、来源及置信度；
5. 通过 `selected_engine`、`detector_mode` 和 `engine_routes` 明确区分
   专用模型与自研降级结果。

入口文件：

- `app/modules/library/drum_analysis.py`：应用内分析器；
- `app/modules/library/stem_analysis.py`：四轨分析集成；
- `modules/stem-separation/src/harbeat_stem_separation/`：独立部署副本。

## 2. 输出字段

结果写入 `library_songs.drum_analysis`，并通过歌曲接口和 analysis manifest 返回。

```json
{
  "version": "drum_transcription_consensus_v2",
  "source": "demucs_drums_stem",
  "selected_engine": "licensed_drum_transcriber",
  "detector_mode": "dedicated_model",
  "status": "ready",
  "needs_review": false,
  "events": {
    "kick": [{"time": 1.002, "confidence": 0.91, "velocity": 114}],
    "snare": [],
    "hihat": [],
    "tom": [],
    "cymbal": []
  },
  "counts": {"kick": 1, "snare": 0, "hihat": 0, "tom": 0, "cymbal": 0},
  "density_curve": [],
  "pattern": {
    "resolution": 16,
    "bars_analyzed": 32,
    "dominant": {"kick": "K.......K.......", "snare": "....S.......S...", "hihat": "H.H.H.H.H.H.H.H."},
    "stability": 0.91,
    "syncopation": 0.32
  },
  "fills": [],
  "confidence": {
    "overall": 0.73,
    "kick": 0.88,
    "snare": 0.84,
    "hihat": 0.81,
    "beat_alignment": 0.66,
    "stem_quality": 0.75
  },
  "quality_flags": [],
  "engine_routes": {}
}
```

`status` 可能为 `ready`、`degraded` 或 `unavailable`。调用方必须同时检查
`needs_review`、`confidence.overall` 和 `quality_flags`，不能只看事件数量。

## 3. 部署

基础运行时依赖已在根目录 `requirements.txt` 中锁定。成熟特征模型及worker
配置见 `docs/pre_style_feature_analysis_backend_deployment.md`。部署主服务后先执行：

```bash
cd /path/to/harbeat-client
source .venv/bin/activate
python scripts/migrate_library_analysis_fields.py
```

新上传歌曲会在分轨完成后自动写入鼓组分析。已有歌曲可通过正常的完整分析
回填任务刷新：

```bash
python scripts/backfill_complete_analysis.py --dry-run
python scripts/backfill_complete_analysis.py
```

独立模块验收：

```bash
PYTHONPATH=modules/stem-separation/src \
python -m unittest discover modules/stem-separation/tests -v
```

应用回归验收：

```bash
PYTHONPATH=. pytest -q app/tests/test_drum_analysis.py app/tests/test_stem_analysis.py
```

## 4. 准确性边界

当前自动测试用带真值的合成120 BPM鼓循环验证基础三类事件、误触发上限、
16步节奏型、成熟模型路由优先级和降级行为。真实Demucs鼓轨用于检查输出
合理性和性能，但没有人工逐击标注，因此不能据此宣称真实歌曲达到某个准确率。

本版本已经修正两类明显误差：孤立 Hi-hat 被重复计为 Snare，以及中频瞬态被
重复计为 Kick。复杂叠击、鼓刷、开放镲、Tom 与强压缩母带仍可能发生混淆。
Tom和Cymbal只有在专用模型worker返回时才作为模型事件；Clap、Rim、开放镲等
细分由前置特征层结合音频标签模型输出。仍需用人工标注K-pop测试集计算逐类
Precision、Recall、F1；在完成该测试前，不应对外承诺“零误差”。

## 5. 回滚

应用可忽略 `drum_analysis` 字段而继续使用既有 stem activity。数据库新增 JSON
列不影响旧数据；代码回滚时无需删除该列。独立模块版本为 `0.2.0`。
