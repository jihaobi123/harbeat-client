# 鼓组细分与鼓事件识别

该模块接收现有 Demucs 流程生成的 `drums.wav`，不修改 Demucs 主流程，并行执行两条互不依赖的链路：

```text
drums.wav
  ├─ MDX23C drumsep-6stem ──> kick/snare/hihat/tom/cymbal WAV
  └─ ADTOF-pytorch ─────────> 五类 onset JSON + drums.mid
```

ADTOF 始终读取完整的 `drums.wav`，不会读取 MDX23C 输出。JSON 中的 `confidence` 直接取自 ADTOF activation 在被 peak picker 选中的帧，不是由 MIDI 或音频能量反推。

当前项目正式评审的鼓组细分结果以 **MDX23C** 为准。ADTOF 只保留为实验性的鼓事件时间支路，不参与 MDX23C 五轨生成，也不作为当前鼓组细分质量的判断依据。

## 输入链路

```text
完整原曲
  └─ Demucs htdemucs ──> drums.wav
       └─ MDX23C drumsep-6stem ──> kick/snare/hihat/tom/cymbal WAV
```

MDX23C 的输入必须是对应歌曲由 Demucs 生成的 `drums.wav`，不是完整原曲，也不是其他歌曲的缓存结果。

## 安装

```bash
pip install -r requirements.txt
```

如果只安装该独立模块的新增依赖，也可以使用
`pip install -r requirements-drum-analysis.txt`。

ADTOF 固定到已审阅提交 `85c192e78f716ea0b111cc8a5ee4a8f6a3a4f8a9`。MDX23C checkpoint 在第一次使用时下载并校验，之后使用本地缓存。模型在进程内按设备缓存，同一设备处理多首歌不会重复初始化。

## Python API

```python
from music_analysis.drum_analysis import analyze_drums

result = analyze_drums(
    "data/song_001/drums.wav",
    "data/song_001/drum_analysis",
    device="auto",
)
```

如果本阶段只运行已选定的 MDX23C 鼓组细分，不运行 ADTOF：

```python
from music_analysis.drum_analysis.mdx23c_separator import MDX23CDrumSeparator

separator = MDX23CDrumSeparator(device="auto")
stems = separator.separate(
    "data/song_001/drums.wav",
    "data/song_001/drum_analysis/stems",
)
```

`stems` 固定包含 `kick`、`snare`、`hihat`、`tom`、`cymbal` 五个路径。模型在同一进程和设备上复用，不会为每首歌重复加载权重。

## CLI

```bash
python -m music_analysis.drum_analysis.pipeline \
  --input data/song_001/drums.wav \
  --output data/song_001/drum_analysis \
  --device auto
```

`--device` 支持 `auto`、`cpu`、`cuda`、`cuda:N` 和 `mps`。`auto` 依次选择 CUDA、MPS、CPU。CUDA 不可用或 CUDA OOM 时会记录明确日志并回退 CPU。

## 输出

```text
drum_analysis/
  stems/
    kick.wav
    snare.wav
    hihat.wav
    tom.wav
    cymbal.wav
  drums.mid
  drum_events.json
  analysis_meta.json
```

五个 WAV 文件固定写成 44.1 kHz、双声道、PCM 16-bit，即使某个声部非常弱也不会跳过。ADTOF 使用官方五类阈值 `0.22,0.24,0.32,0.22,0.30` 和 100 fps。

## 生产风险

`mdxnet-infer` 代码为 MIT，但其 DrumSep checkpoint 没有得到原作者正式许可声明。上游建议在许可澄清前只按“非商业安全”处理。商业发布前必须完成权重许可审查；这不影响本地研究和功能评估，但不能把代码许可证等同于模型权重许可证。
