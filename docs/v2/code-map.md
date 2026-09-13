# 第二版代码分层与本轮清理

本页为代码导航，不宣称整个系统已实现。仓库根入口见 [HARBEAT_V2_START_HERE](../../HARBEAT_V2_START_HERE.md)。

## 一、第二版现行预处理：保留

| 用途 | 入口 / 实现 | 注意 |
|---|---|---|
| 单曲预处理 | `scripts/run_same_style_preprocess.py` → `app/modules/library/same_style_preprocess.py` | 统一 NAS 发布；当前不用 ADTOF 时显式加 `--disable-adtof` |
| 曲库导入 | `scripts/import_same_style_library.py`、`deploy/jetson/run-same-style-library-import` | Jetson 包装脚本包含本批次配置与后续人声补分析 |
| BPM / Beat / 小节 / 段落 | `app/modules/library/analysis.py` | 保留节奏共识；正式段落 SongFormer |
| SongFormer 隔离环境 | `experiments/run_songformer_isolated.py` | 虽在 experiments，却是正式依赖，不可整目录删除 |
| 分轨 / 轨道特征 | `app/modules/library/stem_analysis.py` 与预处理编排 | 保留 Demucs 输出及真实时间轴 |
| 鼓组分离 | `music_analysis/drum_analysis/` | MDX23C；ADTOF 是可选事件路径，不是本批次分离器 |
| 人声标记 | `app/modules/library/vocal_activity.py`、`scripts/backfill_vocal_activity.py` | Silero 消费已有 vocals，不重跑 Demucs |
| 人声交付验证/打包 | `scripts/validate_vocal_activity.py`、`finalize_vocal_activity.py`、`export_vocal_activity_bundle.py` | 补充报告与基础 run/hash 绑定 |
| JSON 合同 | `contracts/schemas/analysis/` | 存储合同已实现；业务传输合同另行评审 |
| 部署 | `deploy/jetson/` | 模型/权重/音频不进入源码交接包 |
| 鼓组 pair 对比 | `scripts/score_drum_pairs.py`、`scripts/calibrate_drum_pair_thresholds.py` | 保留；70%/85% 阈值未经真实人工 pair 校准，不能宣称自动接歌已验收 |

## 二、可复用但不是已打通的第二版业务链路

`app/modules/auth/`、`library/models.py`、`playlists/` 有用户、歌曲和歌单基础；保留并迁移，不新建完全隔离的重复用户库。

`app/modules/library/background_tasks.py` 仍是旧业务分析编排；旧 RMS 人声补丁仍有调用。
`app/modules/manifest/` 和 `assets/` 也不是新 NAS 发布合同的安全公网适配器。
第二版后端应调用现有 NAS 预处理入口、增加目录和传输适配层，不把旧路由直接公开后宣布完成。

## 三、研究区：保留复现，不接入默认流程

MERT 向量、风格分类、段落分类器不同版本、数据集/评审/评测脚本继续保留。
`experiments/extract_mert_vector_dataset.py` 还有测试和复现脚本依赖；仅因当前不训练不能删。
功能归属 RK、手机或混音也不等于项目不再使用；等待相应负责人确认后再迁移。

## 四、已移出常用入口

详见 [历史分析脚本目录](../../archive/analysis-v1/README.md)。

1. `experiments/run_allinone_isolated.py` → `archive/analysis-v1/run_allinone_isolated.py`。
2. `scripts/backfill_vocal_events.py` → `archive/analysis-v1/backfill_vocal_events.py`。

检查了仓库内导入、脚本/文档引用和部署入口；旧人声脚本相对仓库根路径同步调整。
归档不是关闭 All-In-One 节奏功能，也不是删除旧数据库字段。

## 五、以后清理的规则

先检查 `git grep`/`rg`、部署命令、测试、运行中的服务及外部协作者调用，再决定迁移。
需要保留旧实验时移入带说明的历史区，不用静默重定向掩盖不同输入输出。
改变正式入口必须同时改调用方、路径、部署和测试；不要借清理改变模型参数、缓存版本或线上数据。
历史分支删除、默认分支切换、APK 大文件及 Git 历史瘦身另行确认，不混进代码整理提交。
