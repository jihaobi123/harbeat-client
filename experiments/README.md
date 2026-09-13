# 固定实验与历史制品

本目录保留原有数据集、embedding、训练模型、实验报告和 MERT 复现代码。
不要删除数据集/模型，也不要因为目录名是 experiments 就把结果接入产品。

- 正式 SongFormer 实现已迁到 `preprocessing/runners/songformer.py`；这里的 `run_songformer_isolated.py` 只是旧命令兼容入口。
- 日常专项评测和风格训练脚本已整理到 `research/`。
- `style_reference_v0/` 和 `traditional_vs_ml_20260829/` 保持原路径，避免破坏已交付的模型、实验记录与引用。

当前入口：[正式预处理](../preprocessing/README.md) / [研究代码](../research/README.md)。
