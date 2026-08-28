# 风格分析前置特征模块：后端部署与验收

## 1. 模块边界

本模块主体只输出可测量的音频证据。可选的开源风格模型标签以独立辅助路由保存，
由后续 21 类分类模块限幅使用，不能替代原生特征和必需条件。结果写入
`music_features.pre_style_features`，供后续风格分类模块读取。

当前输出六组证据：

- `rhythm_grammar`：四踩、Backbeat、Halftime、Jersey、Tamborzão、Dembow、Tresillo、Two-step、Drill Hat、Breakbeat、Swing、Afro Syncopation；
- `low_frequency`：Sub Bass、候选区段 pYIN、Bass滑音、Kick/Bass对齐、低频旋律/回答和808/Log Drum候选；
- `percussion_timbre`：Snare/Clap/Rim家族、短/长金属声、有音高鼓、手鼓、连续高频层和音高型动机；
- `vocal_delivery`：Rap、演唱和Vocal Chop；
- `harmony`：和声复杂度、Jazz/Soul和声候选与和弦变化活跃度；
- `production`：明暗、失真、Lo-fi、采样、电子/原声倾向和Rage Synth。

`Log Drum`、`808`以及相近打击乐音色仍属于候选标签，不能在没有人工标注
验收的情况下当作真值。

无法分析时使用 `availability=unavailable`、`detected=null`，不能解释成没有该特征。

## 2. 专用模型边界

```text
Demucs stems
  drums.wav -> 专用鼓转录worker -> Kick/Snare/Hi-hat/Tom/Cymbal
             -> 失败时 spectral_flux_fallback
  bass.wav   -> 候选区段pYIN + 频谱fallback -> F0、滑音、低频行为与音色候选
  beat/downbeat + 鼓点 -> 直线/三连音网格 + 16步节奏语法 + 4/8/16小节稳定窗口
```

鼓转录与辅助风格标签线路均返回 `status`、`engine`、`elapsed_seconds`、
`license`、`error` 和 `result`。其他特征由当前时频模块计算，结果通过
`analysis_method`、`sources`、`quality_flags` 和 `evidence` 保留依据。

## 3. 安装

基础 API 依赖保持不变。只有需要专用鼓转录或辅助风格标签时才部署独立 worker
或配置本地 Essentia Discogs 模型；程序不会自动下载权重。

## 4. 外部模型worker协议

配置：

```bash
FEATURE_DRUM_TRANSCRIBER_COMMAND="python /opt/harbeat-models/drum_worker.py --audio {audio}"
FEATURE_BASS_TRANSCRIBER_COMMAND="python /opt/harbeat/scripts/basic_pitch_bass_worker.py --audio {audio}"
FEATURE_STYLE_TAGGER_COMMAND="python /opt/harbeat-models/style_worker.py --audio {audio}"
FEATURE_INSTRUMENT_TAGGER_COMMAND="python /opt/harbeat-models/instrument_worker.py --audio {audio}"
# 或使用本地 Essentia Discogs EffNet（不要与 worker 同时配置）
ESSENTIA_DISCOGS_MODEL_PATH="/opt/harbeat-models/discogs-effnet-bs64-1.pb"
ESSENTIA_DISCOGS_METADATA_PATH="/opt/harbeat-models/discogs-effnet-bs64-1.json"
FEATURE_MODEL_TIMEOUT_SECONDS=300
```

命令通过参数数组直接执行，不经过Shell。命令必须包含 `{audio}`，并在标准输出
只返回一个JSON对象。

风格 worker 的 `result.labels` 使用 `[{"label": "Electronic---House",
"score": 0.81}]` 结构。本地 Essentia 路由会保存模型名、版本、帧数、聚合方法和
前 25 个原始标签。分类器最多增加 0.18 辅助分，且不会绕过 21 类规则的必需证据；
邻近或无法映射的顶部标签会设置 `out_of_taxonomy=true` 并要求复核。

Bass 和乐器 worker 都是可选路线。`basic-pitch` 不加入基础 API 依赖，应安装在
隔离的模型环境中；其音符起止、音高只增强 Bass Stem 的事件测量。乐器标签只作为
辅助观察，不能直接确认 808、Talkbox、Clavinet 等窄语义身份。

## 风格输出语义

- `primary_style_candidate`：21 类中的最高候选，即使证据门槛未完整通过也保留，供诊断使用。
- `primary_style`：完整通过分数、可靠度、必需证据和最小证据数的最高风格；否则为 `null`。
- `detected_styles`：独立通过完整条件的最多三个标签，不是强制 Top-3。
- `style_influences`：接近门槛但证据不完整的影响标签，不能当作已检测风格。
- `external_tags`：原始开源风格和乐器标签；21 类未覆盖时配合 `out_of_taxonomy` 使用。

Funk、Disco、House 只有在原始得分相差不超过 0.10 且双方边界特征覆盖率至少为
0.50 时才运行两两比较。总调整量不超过 0.08，而且不能绕过任一风格的必需证据。

鼓转录示例：

```json
{
  "engine": "licensed_drum_transcriber",
  "license": "deployment-specific",
  "events": {
    "kick": [{"time": 0.502, "confidence": 0.93, "velocity": 116}],
    "snare": [],
    "hihat": [],
    "tom": [],
    "cymbal": []
  }
}
```

## 5. 授权约束

- ADTOF和MTG Essentia预训练模型可作为非商业评测基准，但其公开权重通常是
  CC BY-NC-SA，未取得商业许可前不得作为商业生产默认模型；
- 外部worker必须在返回结果里报告实际模型和权重许可，部署人员负责保留权重
  来源、版本哈希和授权文件。

## 6. 验收

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  app/tests/test_feature_model_adapters.py \
  app/tests/test_feature_validation.py \
  app/tests/test_drum_analysis.py \
  app/tests/test_stem_analysis.py
```

自动测试验证协议、路由选择、降级行为和结构计算。真实准确率必须使用人工逐击
标注的歌曲集分别计算每类Precision、Recall和F1；合成测试成绩不能替代真实
歌曲准确率。

真实歌曲可使用最小人工复核流程。它会自动接受高置信度结果，仅为阈值附近、
模型冲突或808/Log Drum等高风险语义生成6秒片段：

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_pre_style_features.py manifest \
  --input-dir /data/audio --stem-root /data/stems \
  --rhythm-root /data/rhythm-raw --output /data/validation/manifest.json

PYTHONPATH=. .venv/bin/python scripts/validate_pre_style_features.py analyze \
  --manifest /data/validation/manifest.json \
  --output-dir /data/validation --max-review-items 8
```

人工只需打开`/data/validation/review/index.html`，听原曲上下文和分轨重点，完成
页面上保留的少量选择并导出JSON。真实歌曲、分轨、片段及机器绝对路径不得提交
到Git。
