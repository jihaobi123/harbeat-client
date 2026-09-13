# 历史分析入口（不属于第二版默认预处理）

2026-09-13 从常用脚本目录移入，保留代码和 Git 历史，不删除数据或模型。
当前开发从 [第二版入口](../../HARBEAT_V2_START_HERE.md) 开始。

| 原位置 | 归档文件 | 原因 / 当前替代入口 |
|---|---|---|
| `experiments/run_allinone_isolated.py` | [run_allinone_isolated.py](run_allinone_isolated.py) | 独立原曲对比实验，无仓库内调用；正式段落使用 SongFormer。不是删除 All-In-One 的节奏分析与失败回退。 |
| `scripts/backfill_vocal_events.py` | [backfill_vocal_events.py](backfill_vocal_events.py) | 旧数据库 Demucs/RMS 补分析，无仓库内外部调用；第二版 NAS 人声标记使用 `scripts/backfill_vocal_activity.py`。 |

旧脚本不自动重定向到新脚本：两者输入、输出及写入目标不同，重定向会误写数据。
需要复现时显式使用本目录的新路径；旧人声脚本仍会写旧数据库，先检查目标并使用 `--dry-run`（它仍可能计算/分轨）。
外部私人脚本不在本次引用扫描范围，如有使用旧路径，请修改为这里的新路径。

保留未搬迁：

- `experiments/run_songformer_isolated.py`：正式流程和 Jetson 部署仍调用。
- `app/modules/library/analysis_vocal_patch_gpu.py`：旧 `background_tasks.py` 仍调用，不能直接删。
- MERT、风格分类、段落分类器、评审工具：保留研究复现用途，不视为默认算法。
- 训练数据、模型版本、标注、报告和 NAS 音频：没有删除或搬迁。

本次没有改动模型逻辑、阈值、分析缓存版本、已发布 Manifest 或 NAS 目录。
