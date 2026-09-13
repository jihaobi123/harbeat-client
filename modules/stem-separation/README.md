# 正式分轨已经统一，不在这里维护第二份源码

唯一正式实现：[preprocessing](../../preprocessing/README.md)。

- Demucs 四轨：`preprocessing/publisher.py:_run_demucs`，模型 `htdemucs`。
- 四轨特征：`preprocessing/engines/stem_analysis.py`。
- MDX23C 鼓子轨：`music_analysis/drum_analysis/mdx23c_separator.py`。
- 分轨后的人声时间：`preprocessing/vocal_activity.py`（Silero VAD）。

本目录原有 `harbeat_stem_separation` 的源码、测试和旧合同已退役；不再作为可安装包。正式代码仍使用的 `pre-style-features-v5.schema.json` 已迁到 `contracts/schemas/analysis/`，内容不变。
旧源码可从提交 `3482daf` 的同路径恢复。没有删除音轨、模型或 NAS 结果，也没有改动线上服务。
