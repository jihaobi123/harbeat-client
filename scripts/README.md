# 运维与兼容脚本

本轮已把 24 个离线研究脚本移到 `research/`，6 个正式预处理 CLI 的实现移到 `preprocessing/cli/`。
本目录不再是所有分析脚本的混放入口。

| 类别 | 本目录保留的内容 | 使用原则 |
|---|---|---|
| 正式入口兼容 | run_same_style_preprocess、import_same_style_library、backfill/validate/export/finalize_vocal_activity | 仅转发；新开发使用 preprocessing.cli |
| 隔离模型工具 | adtof_drum_worker、basic_pitch_bass_worker、essentia_vocal_activity_worker、madmom_chord_worker、madmom_key_cli | 某些正式/可选特征配置仍引用，不能因当前禁用某路线就删 |
| 数据库补分析/迁移 | backfill_complete_analysis、backfill_mp3_band_features、backfill_style_evidence、migrate_library_analysis_fields、cleanup_library_duplicates | 会写数据，非新同事开工命令；运行前核对库与备份 |
| 数据回归工具 | reanalyze_feature_test_library、validate_downbeats、validate_pre_style_features | 保留现有用途，不能当成全库发布入口 |
| 鼓组 pair 研究 | score_drum_pairs、calibrate_drum_pair_thresholds | 已有引用与测试，真实阈值校准状态不因整理改变 |
| RK / 混音工具 | jetson_stem_*、auto_mix_e2e、dj_set_smoke、gen_fx_for_rk、patch_rk_engine_fx 等 | 第一版历史参考；第二版后续重构，预计不直接使用，不作为开工命令 |

旧业务和数据库脚本保留不等于批准沿用；新后端表设计、迁移方案仍需确认。不要直接运行旧补丁、清库、部署或设备控制命令。详见 [参考代码与重构边界](../docs/repository/reference-code.md)。

统一目录说明见 [仓库代码地图](../docs/repository/README.md)。没有把未跟踪的本地评审脚本或音频加入提交。
