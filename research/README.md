# 研究与离线评测：不自动参与正式分析

这里存放对比、评测、风格数据集和训练代码。它们不是废文件，也不代表已经接入产品。
2026-09-13 将 24 个脚本从常用 `scripts/` 移入，数据集、模型、报告均不搬迁、不删除。

- `evaluation/`：GiantSteps、Ballroom、GTZAN、GuitarSet、Groove、Jamendo、MIR-1K、鼓/贝斯等专项评测，以及公共基准准备工具。
- `style/`：风格数据集建立、embedding 提取、分类器训练、评估、标签审计和已有结果再评估。
- MERT 的既有代码和固定历史实验暂仍在 `experiments/`；其相对模型/数据路径及历史记录保持原状，不在本轮擅自迁移大型制品。

从仓库根目录使用模块方式运行（先查看参数，不会运行训练）：

```bash
python -m research.evaluation.evaluate_drum_transcriber --help
python -m research.style.train_style_model --help
python -m research.style.evaluate_style_model --help
```

环境仍使用各实验原先的依赖，不因为整理就升级 torch 或更改种子、数据划分、参数。
旧的 `scripts/evaluate_*.py` / 风格脚本路径已经移走，仓库内代码与当前操作说明已更新。
外部个人脚本请按 [完整迁移表](../docs/repository/moves-20260913.json) 更新路径。
固定历史报告中的旧命令保留原貌，用迁移表查新路径；不能修改历史结果来伪装成重新验证。

当前正式管线使用 SongFormer 段落及目录人工风格标签，研究结果不会因为搬到这里就改变正式输出。
