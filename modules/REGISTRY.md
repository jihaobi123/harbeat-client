# 当前保留版本与使用边界

本表替代旧 v0.1 清单。来源：远端 `rewrite/clean-core-operation-v0.4` 的 `15b8663683a94aa8aff19ccfba0152fdf9069f1d`。这里按安装包声明列版本；原 MODULE.yaml 的模块合同版本另存 CURRENT.json，不随整理伪造升级。

| 模块 | 保留的包版本 | 职责 / 第二版状态 |
|---|---|---|
| observability-e2e | 0.3.0 | 调试、观测、验收工具；需对新链路重做验收 |
| device-runtime | 0.3.0 | 设备身份与连接；新 APK/RK 对接未验证 |
| library-catalog | 0.3.0 | 曲库 ID、仓储接口、旧资源 DTO；仍需适配 NAS 发布合同 |
| sequence-planner | 0.3.0 | 排歌参考实现；交接歌算法负责人，不规定由 Jetson 执行 |
| transition-planner | 0.3.0 | 接歌选点参考实现；不等于已对接当前算法 |
| transition-renderer | 0.3.0 | 旧预渲染实现保留供算法方取舍；V2 实时混音仍由 RK 负责 |
| asset-sync | 0.3.0 | 资源下载与校验；V2 授权及完整音轨合同待适配 |
| transition-orchestrator | 0.4.1 | 操作状态机及执行器，包含后续终态/并发修复；不直接接入生产 |
| audio-runtime | 0.3.0 | RK 播放引擎参考实现；未部署本次同步的版本 |
| mobile-dj-control | 0.2.0 | 独立 Dart 控制逻辑；不是新 APK 源码，不约束新 API |
| physical-input | 0.3.0 | 按键/SFX 控制逻辑；不是戒指/手环姿态识别实现 |

以上模块各只保留一份实现，没有再建 v0.1/v0.2 并列源目录。附带 deploy/provenance 文件是来源证据，不表示当前设备已部署。

## 已去掉的重复实现

| 原目录 | 现在唯一维护位置 |
|---|---|
| modules/audio-preprocess | preprocessing/engines/analysis.py + preprocessing/publisher.py |
| modules/stem-separation | preprocessing/publisher.py + preprocessing/engines/stem_analysis.py |

两目录仅留导航，不再提供原 Python 包。ADTOF 继续不在当前曲库批次中启用；模型、算法版本和 NAS 数据不因这次代码清理而改变。

## 后端与 RK 的边界

新手机后端按新 APK 和现有预处理合同重构，不以旧 API 兼容为目标。Jetson 负责预处理及业务/数据服务，阿里云提供公网入口，RK 获取资源并实时混音。将旧 renderer 或 operation executor 保留下来，不等于授权把混音重新放回 Jetson。

当前实现来源、原始文件 SHA256、文本等价校验和退役映射均在 [CURRENT.json](CURRENT.json)。恢复整理前文件可查看 Git 提交 `3482daf`；不要整分支强行回退线上环境。
