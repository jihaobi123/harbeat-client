# 风格分析前置特征模块：后端部署与验收

## 1. 模块边界

本模块只输出可测量的音频证据，不输出音乐风格名称。结果写入
`music_features.pre_style_features`，供后续独立的风格分类模块读取。

当前输出四组证据：

- `rhythm_grammar`：四踩、Backbeat、Halftime、Tresillo、Dembow、2-Step、Swing、Shuffle、Hi-hat Roll、Ghost Notes；
- `low_frequency`：Sub Bass、808候选、Kick/Bass对齐、Bass滑音、Log Drum候选；
- `percussion_timbre`：Clap、Rim/Snap、开闭镲、Ride/Crash、Tom及其他打击乐候选；
- `sonic_profile`：明亮度、失真、Lo-fi、和声复杂度、Acoustic倾向、Synth明亮度。

`Log Drum`、`808`以及相近打击乐音色仍属于候选标签，不能在没有人工标注
验收的情况下当作真值。

## 2. 成熟模型优先级

```text
Demucs stems
  drums.wav -> 专用鼓转录worker -> Kick/Snare/Hi-hat/Tom/Cymbal
             -> 失败时 spectral_flux_fallback
  bass.wav   -> torchcrepe + Spotify Basic Pitch -> 音高、音符、滑音交叉证据
  full mix   -> YAMNet/PANNs worker -> 乐器/打击乐时间窗标签
  beat/downbeat + 鼓点 -> 确定性节奏语法
```

每条线路均返回 `status`、`engine`、`elapsed_seconds`、`license`、`error` 和
`result`。调用方必须检查 `selected_models`、`quality_flags` 以及每项特征的
`evidence.source_type`，不能把DSP降级输出解释成成熟模型结果。

## 3. 安装

基础API依赖保持不变。Bass成熟模型建议安装在单独分析worker：

```bash
python -m venv .venv-feature-models
source .venv-feature-models/bin/activate
pip install -r requirements.txt
pip install -r requirements-feature-models.txt
```

Spotify Basic Pitch建议使用其官方支持的独立Python环境，避免TensorFlow版本
影响主API。鼓组和音频标签同样可使用独立worker，只要遵守下面的JSON协议。

## 4. 外部模型worker协议

配置：

```bash
FEATURE_DRUM_TRANSCRIBER_COMMAND="python /opt/harbeat-models/drum_worker.py --audio {audio}"
FEATURE_AUDIO_TAGGER_COMMAND="python /opt/harbeat-models/yamnet_worker.py --audio {audio}"
FEATURE_BASIC_PITCH_COMMAND="python /opt/harbeat-models/basic_pitch_worker.py --audio {audio}"
FEATURE_MODEL_TIMEOUT_SECONDS=300
```

命令通过参数数组直接执行，不经过Shell。命令必须包含 `{audio}`，并在标准输出
只返回一个JSON对象。

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

YAMNet/PANNs标签示例：

```json
{
  "engine": "yamnet",
  "license": "Apache-2.0",
  "tags": [
    {"label": "Rimshot", "score": 0.81, "start": 12.0, "end": 12.96},
    {"label": "Tambourine", "score": 0.64, "start": 24.0, "end": 24.96}
  ]
}
```

## 5. 授权约束

- ADTOF和MTG Essentia预训练模型可作为非商业评测基准，但其公开权重通常是
  CC BY-NC-SA，未取得商业许可前不得作为商业生产默认模型；
- torchcrepe为MIT许可；Spotify Basic Pitch为Apache-2.0；
- 外部worker必须在返回结果里报告实际模型和权重许可，部署人员负责保留权重
  来源、版本哈希和授权文件。

## 6. 验收

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  app/tests/test_feature_model_adapters.py \
  app/tests/test_drum_analysis.py \
  app/tests/test_stem_analysis.py
```

自动测试验证协议、路由选择、降级行为和结构计算。真实准确率必须使用人工逐击
标注的歌曲集分别计算每类Precision、Recall和F1；合成测试成绩不能替代真实
歌曲准确率。
