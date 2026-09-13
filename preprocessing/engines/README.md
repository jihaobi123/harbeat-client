# 共享分析引擎：Jetson 离线计算，不是手机后端

本目录是从 `app/modules/library/` 迁出的现有实现。不是重新训练模型，也不是将历史 `modules/` 的实现接入生产。

| 工作 | 实现入口 | 输入与输出 |
|---|---|---|
| BPM / Beat / 小节 / SongFormer 段落整合 / 调性 / 能量 | `analysis.py:analyze_audio_file` | 音频路径 → 核心分析字典 |
| 四轨特征 | `stem_analysis.py:analyze_stem_files` | vocals/drums/bass/other 路径及节拍信息 → 特征字典 |
| 鼓事件及节奏模式特征 | `drum_analysis.py` | 鼓轨及可用模型证据 → 事件、计数、节奏模式；不是 MDX 分离器 |
| 贝斯、人声音高、音色、节奏特征 | `bass_feature_analysis.py`、`vocal_pitch_analysis.py`、`percussion_feature_analysis.py`、`rhythm_feature_analysis.py` 等 | 音频/轨道测量 → 特征及质量证据 |
| 模型验证与特征校准 | `*_model_validation.py`、`feature_calibration.py` | 原有 `config/` 配置 → 验证/校准信息 |
| 两曲鼓组相似度 | `drum_pair_similarity.py` | 两份鼓分析 → 可解释分数；不自动选歌或混音，阈值仍是待真实数据校准的配置 |

这些是内部 Python 计算接口，时间单位和字段沿用原实现。不能直接把内部字典当作手机/RK 公开协议：应由上层 `preprocessing/publisher.py` 转换成已有发布 schema，并写入版本目录。

运行关系：CLI → publisher → engines / Demucs / MDX23C → NAS；Silero 在独立 `preprocessing/vocal_activity.py` 中处理已发布 vocals。

引擎不导入 `app`、FastAPI、SQLAlchemy，不初始化业务数据库。通用命令解析复用 `music_analysis/command_line.py`。旧 app 导入路径仅转发到这些实现，保证缓存、锁及测试替换使用同一个模块对象。

目录迁移仅改变导入和仓库根路径定位。算法版本、缓存规则、模型权重、参数、质量标记和输出合同未改。MDX23C 仍在 `music_analysis/drum_analysis/`；模型权重不放在本目录。

当前仓库源码已整理；没有同步替换 Jetson 线上 release。实际部署边界见 [部署位置与状态](../../docs/repository/deployment-map.md)。
