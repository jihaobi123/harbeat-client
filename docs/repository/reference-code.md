# 哪些继续使用，哪些只作第一版参考

更新：2026-09-13。用户已明确：**RK、App 后端、手机操作等后续重构，目前保留和上传代码只是供参考，预计不直接使用。** 本轮整理位置说明、备注和索引，不实施新的业务接口或混音算法。

后续补充：[第二版后端实施手册](../backend-v2/README.md) 已核对 Jetson/NAS/数据库和新 APK 真机主要页面，细分“继续用 / 可借鉴函数 / 第一版参考 / 待新增”，并给出接口与表设计。下文清理验证描述的是此前整理批次；新手册是待实现方案，不改变旧代码的参考定位。

## 1. 继续使用：正式预处理及其数据

| 内容 | 唯一维护入口 | 本轮处理 |
|---|---|---|
| BPM / Beat / 小节 / SongFormer 段落整合 | [preprocessing/engines](../../preprocessing/engines/README.md) | 保持现有算法 |
| Demucs 四轨、曲库导入、NAS 发布 | [preprocessing](../../preprocessing/README.md) | 保持现有实现 |
| MDX23C 鼓子轨 | [music_analysis/drum_analysis](../../music_analysis/drum_analysis/README.md) | 保持现有模型 |
| Silero 人声时间报告 | `preprocessing/vocal_activity.py` | 保持现有实现 |
| 发布结果、音轨、索引与人声报告格式 | [contracts/schemas/analysis](../../contracts/schemas/analysis/README.md) | 已有公开格式继续有效；内部特征 schema 不等于公开协议 |
| 正式预处理部署包装 | [deploy/jetson](../../deploy/jetson/README.md) | 保留；新目录尚未切换到线上 |

“继续使用预处理”不等于所有可选特征都已验收，也不表示 Pair Score 阈值已完成校准。当前曲库仍禁用 ADTOF。标注、模型、音乐和已经交付的 NAS 数据均保留。

## 2. 仅参考：默认不直接用于第二版

| 参考区域 | 里面是什么 | 第二版怎么对待 |
|---|---|---|
| [app](../../app/README.md) | 第一版 API、业务逻辑、后台任务、ORM | 后续重构；旧接口和旧状态机不是新后端要求 |
| [app/shared](../../app/shared/README.md)、各业务 models.py | 旧配置、鉴权、数据库连接、表映射 | 了解存量数据，不据此默认采用旧表设计；不删除线上表 |
| [mobile](../../mobile/README.md) | 旧 Flutter 客户端、页面和操作逻辑 | 后续重构；不能认定为外部提供的新 APK 源码 |
| [web](../../web/README.md) | 旧网页控制台和客户端逻辑 | 仅参考，不要求第二版继续建设或兼容 |
| [cypher-integration/flutter-app](../../cypher-integration/flutter-app/README.md) | 另一份历史 Flutter 集成代码 | 仅参考，不与新 APK 自动合并 |
| [cypher-integration/rk3588-edge](../../cypher-integration/rk3588-edge/README.md) | 旧 RK 服务、播放器、同步、控制和交接材料 | RK 负责人后续重构；旧协议和预渲染流程不约束新算法 |
| [rk_deploy](../../rk_deploy/README.md) | 历史部署脚本及 API/模型副本 | 不当作 RK 当前权威源码或第二版部署入口 |
| [jetson](../../jetson/README.md) | 旧 DJ/后台分析补丁副本 | 不是正式 Jetson 预处理目录，不覆盖 preprocessing |
| [modules](../../modules/README.md) 的 11 个保留包 | 第一版功能模块及后续维护版本 | 仅供评估，第二版是否采用仍需确认，默认不直接接入 |
| [_april_dist](../../_april_dist/README.md) | 历史安装包/构建产物 | 不作为新 APK 身份或当前版本的证明 |

这些目录保留原路径，避免整理过程破坏尚存的引用；通过 README 和索引区分用途，没有创建第二份源码副本。旧文件仍可从 Git 历史恢复。

## 3. 配置、脚本和文档怎样读

- [deploy](../../deploy/README.md)：区分正式预处理脚本、网关配置与旧整套服务部署。根目录 Dockerfile、docker-compose、deploy/start/stop 脚本不是第二版开工时默认执行的命令。
- [scripts](../../scripts/README.md)：正式预处理兼容入口与研究工具继续按原用途保留；旧业务、RK、数据库补丁只作参考。会改库或改设备的脚本不得因“仓库有文件”就直接运行。
- [docs](../README.md)：当前预处理合同继续有效；旧后端、手机、RK 任务书和开发计划仅作历史资料，其中“必须实现”“正式交付”等表述不构成新任务。
- [contracts](../../contracts/README.md)：公开预处理合同与旧手机/RK 草案分开。新手机接口、设备控制协议与业务资源下载协议均待重构设计，不能从旧草案推断已冻结。
- [research](../../research/README.md)、[experiments](../../experiments/README.md)、[reports](../../reports/README.md)：离线实验、训练版本和证据资料，保留评估价值，不自动接入正式流程。

## 4. 后续重构的边界

方向保持：Jetson 负责预处理及服务端数据，NAS 保存音频/分析结果，阿里云提供公网入口；手机选歌和控制，RK 拉取所选歌曲资源并实时混音播放。戒指/手环操作由硬件/RK 负责人设计。

新 APK 源码待用户提供。新手机接口不必兼容旧手机 API；即使决定复用旧模块，也须重新确认输入输出、数据格式和验收条件。本轮不把保留的参考代码变成后端或 RK 负责人的必做清单。

## 5. 本轮没有做什么

没有重写后端/手机/RK，没有迁数据库、删除线上表、重跑模型、改 NAS、换线上 release 或执行旧部署脚本。没有删除或合并远端历史分支，没有切换默认分支。

工作区原有未提交配置、文档、APK 删除和实验产物不纳入本轮提交。旧文档中有两份带未提交改动，未改其正文，所在目录已统一标明仅供历史参考。

机器可读目录定位和已加备注文件清单见 [reference-areas.json](reference-areas.json)。本轮上传的是索引、备注与说明，不是额外的音频、APK 或实验数据包。

## 6. 本轮验证

`tests/test_reference_catalog.py`、`tests/test_current_modules.py`、`tests/test_repository_layout.py`、`tests/test_analysis_engine_layout.py`：共 **129 passed**。

检查覆盖参考区标记、37 份历史文档去掉新增提示后原文指纹一致、导航链接有效、保留模块源码指纹及此前正式目录约束。本轮没有修改运行实现，没有运行新歌曲推理、数据库迁移、APK 或 RK 联调；测试通过不代表第二版业务链路完成。
