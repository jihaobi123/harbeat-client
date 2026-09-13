# 13 个历史抽取模块：本轮处置与第二版边界

2026-09-13。`modules/` 保存的是 2026-08-13 的独立抽取基线。它们有自己的测试和历史合同，不表示已经替换当前部署。**全部保留源码，本轮不把任何一个历史模块强行并入正式预处理。**

下表是代码职责和后续处置表，不是 13 个模块的线上安装清单。

| 历史模块 | 第二版对应位置或负责人 | 本轮结论 / 后续门槛 |
|---|---|---|
| audio-preprocess | `preprocessing/`，Jetson | 旧模块核心是 `dj_structure_v2` 切点候选，非当前 SongFormer 发布器的等价替代；保留参考，不切换 |
| stem-separation | publisher 的 Demucs + engines/stem_analysis，Jetson | 有独立旧特征实现且行为不同；保留回溯，不与正式引擎混用 |
| library-catalog | app 曲库/歌单 + NAS 发布合同，后端 | 旧 ID/资源 DTO 可参考，但不能直接代替当前 versioned manifest；待 V2 数据层设计 |
| device-runtime | 手机/RK 设备连接，前端与 RK 负责人 | 历史连接/状态合同；新 APK 是否采用尚未验证，不替前端改协议 |
| sequence-planner | 接歌算法负责人 | 旧表写 Jetson，不作为 V2 部署要求；不纳入后端离线预处理职责 |
| transition-planner | 接歌算法 / RK 负责人 | 旧选点与对齐逻辑仅参考；待对方确认是否复用，不在本轮改算法 |
| transition-renderer | RK 实时混音负责人 | 旧服务器预渲染 WAV 与 V2 实时混音职责不同，不部署到 Jetson 冒充新链路 |
| asset-sync | RK 下载与校验；服务端授权由后端实现 | 下载模块可参考，但需适配 NAS manifest、drums、人声报告及任务合同 |
| transition-orchestrator | RK 负责人 | 历史同步/预备/调度状态机；需与新算法协商，不在 Jetson 后端直接复用 |
| audio-runtime | RK 负责人 | 历史双 deck/播放实现保留；未证明已适配新 APK 与新算法 |
| mobile-dj-control | 手机前端负责人 | 旧 Dart 控制合同不是外部提供 APK 的已确认源码，不合并代替新前端 |
| physical-input | 戒指/手环/RK 负责人 | 原按键/SFX 合同不等于姿态控制实现；保留，排除出手机/Jetson 后端任务 |
| observability-e2e | 开发/测试 | 历史跨设备检查工具，按旧目标执行；不能用旧测试通过证明新链路已完成 |

## 已实际核对的三个高重叠模块

1. `audio-preprocess/src/harbeat_audio_preprocess/dj_structure_v2.py` 提供候选结构计算，配套 gate 要求 `track1_exit_candidates` / `track2_entry_candidates`。当前正式发布器提供 NAS 版本清单与 SongFormer 段落，两者职责及合同不同。
2. `stem-separation/src/harbeat_stem_separation/analysis.py` 在原曲缺失时返回固定重建质量值 `0.75`；正式 `preprocessing/engines/stem_analysis.py` 返回不可用值及原因，并含更多模型证据/校准。直接合并会改变结果含义。
3. `library-catalog/src/harbeat_library_catalog/manifest.py` 的 `AssetManifest` 主要包含歌曲 ID、original、四轨及 analysis_status；它不是 NAS 发布合同，缺少当前 run/成功标记、五条鼓子轨和独立人声报告绑定关系。

其他十项完成职责归类，**尚未完成逐函数等价性审查**，不宣称已去重。

## 什么时候才能真正删旧代码

必须先确认没有部署或协作者引用旧入口，列出与当前合同的差异，完成替代实现与回归，再单独归档/删除。静态没搜到 import 不是无人使用的证明。

历史 `MODULE.yaml`、`REGISTRY.md`、baseline/provenance 和不可变 tag 保持原义；新入口警示与本表优先用于 V2 选型，但不篡改历史验收记录。
