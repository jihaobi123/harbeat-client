# 代码部署在哪里：已知现状与目标分开写

更新：2026-09-13。本轮仅整理源码，没有通过部署、重启或迁库改变线上状态。
“已有部署”基于此前同日只读核对；本轮没有重新探测服务器。以下不是可直接执行的安装脚本，也不保证后来无人修改线上 release。

## 各模块归属

| 模块 | 仓库实现 | 运行位置 / 状态 | 数据去向 |
|---|---|---|---|
| BPM、Beat、小节、调性、段落整合 | `preprocessing/engines/analysis.py` | Jetson 已有旧路径实现；新目录尚未上线 | 经 publisher 写 NAS |
| SongFormer | `preprocessing/runners/songformer.py` | Jetson 隔离模型环境；新目录尚未上线 | 核心分析中的正式段落 |
| Demucs 四轨 | `preprocessing/publisher.py:_run_demucs` | Jetson；保持 NVIDIA PyTorch 环境 | NAS 的 vocals/drums/bass/other |
| MDX23C 五条鼓子轨 | `music_analysis/drum_analysis/mdx23c_separator.py` | Jetson；正式发布流程调用 | NAS 的 kick/snare/hihat/tom/cymbal |
| 轨道/鼓事件/节奏特征 | `preprocessing/engines/` | Jetson；新目录尚未上线 | manifest 的分析字段及质量标记；不代表事件精度已校准 |
| Silero 人声时间 | `preprocessing/vocal_activity.py` | Jetson 已有实现；新目录尚未上线 | NAS 独立 vocal_activity 报告 |
| 曲库批量导入/发布/补分析 | `preprocessing/cli/`、`deploy/jetson/` | Jetson 作业；源码入口已改，部署未切换 | NAS published、报告与交付回执 |
| 曲库/歌单/鉴权等业务 API | `app/` | Jetson 已有历史 API，尚非完整新 APK 后端 | PostgreSQL；NAS 结果到 V2 业务的衔接仍需实现 |
| 数据库/缓存 | `app/shared/` 与 ORM | 上次核对 Jetson PostgreSQL 14、Redis | 业务元数据；不把大音轨写入数据库 |
| 公网入口 | `deploy/` 中配置仅供核对 | 阿里云角色明确；完整生效配置尚未逐项审计 | 代理 API / 获准资产访问，不跑预处理模型 |
| 新手机 App | 外部提供 APK，旧 `mobile/` 不等同其源码 | 用户手机；接口仍待真实页面核对 | 用户选择与控制请求，不负责转发整套音轨 |
| 实时混音/播放/资源缓存 | `rk_deploy/`、`cypher-integration/` 等为已有代码 | RK3588；新算法适配由 RK 负责人确认 | RK 本地音轨缓存和播放输出 |
| 戒指/手环 | 现有控制相关目录仅参考 | 控制器/RK；不属本后端负责人范围 | 姿态控制事件 |
| `research/`、`experiments/` | 离线研究 | 不是正式作业自动加载清单 | 研究报告；不自动覆盖发布数据 |
| `modules/` 保留的 11 个模块 | 已核对的远端后续源码，版本见 modules/REGISTRY.md | 未部署本轮同步版本；仍待新 APK/RK 合同适配 | 不自动替换正式预处理或线上业务 |

## Jetson 已核对过的具体位置

- 正式预处理 release 指针：`/opt/harbeat/same-style-preprocess-current`。
- 上次指向：`/opt/harbeat/releases/same-style-preprocess-a268a5c-vocal-20260913`，仍是整理前目录。
- Python：`/opt/harbeat/current/venv/bin/python`；`current` 上次指向 `core-v0.5.0`，不能据此判断业务源码版本。
- 附加预处理 Python 包：`/opt/harbeat/runtime/preprocess-packages`。不可用普通 pip 安装覆盖 NVIDIA PyTorch。
- NAS 预处理根：`/mnt/nas/harbeat/preprocess`；模型缓存主要在 `/mnt/nas/harbeat/models`，通用缓存 `/mnt/nas/harbeat/cache`。
- 环境配置入口：`/etc/harbeat/same-style-preprocess.env`、`/etc/harbeat/same-style-library-import.env`。此处只列路径，不包含密钥。
- 作业入口：`/usr/local/bin/harbeat-same-style-library-import`、`/usr/local/bin/harbeat-vocal-activity-backfill`；对应 service 为 `harbeat-same-style-library-import.service`、`harbeat-vocal-activity-backfill.service`。是否正在运行需另行检查，文件存在不代表常驻运行。

特别注意：`harbeat-api.service` 的上次实际 WorkingDirectory 是 `/opt/harbeat/releases/analysis-shadow-72564be`，使用 `current/venv/bin/uvicorn`，且加载多个历史 release 的环境文件。**业务 API、预处理源码、Python 环境是三个不同的版本位置。** 不能用一次覆盖整个 `/opt/harbeat/current` 来“同步第二版”。

## NAS 消费者从哪里读

`HARBEAT_PREPROCESS_ROOT=/mnt/nas/harbeat/preprocess`。相对 storage key 必须在这个根目录下解析；不使用 Jetson Python 源码路径作为下载地址。

- 已交付 EDM 基础索引：`published/indexes/edm_8_handoff_v1.json`。
- EDM 人声增补：`published/indexes/edm_8_vocal_activity_v1.json`。
- 全曲库基础 / 人声索引：`published/indexes/style_library_v1.json`、`published/indexes/style_library_vocal_activity_v1.json`。
- 单首基础结果：`published/tracks/<track_id>/runs/<run_id>/manifest.json` 和同目录 `_SUCCESS.json`，以索引记录的固定 run 为准。
- 人声报告：`published/vocal_activity/<track_id>/<run_id>/<revision>/vocal_activity.json`，校验与基础 manifest/音轨的绑定，不随意混用不同版本。

已有交付合同没有改变。本说明不意味着公网已经提供这些文件的 V2 鉴权接口，也不提供服务器私钥。远端协作者仍需已授权的只读交付渠道。

## 新源码上线前还缺什么

新建独立 release，复制完整 preprocessing、music_analysis、config、contracts、运行器依赖及需要的 scripts；核对模型环境与配置；在非正式输出目录进行验收；记录旧指针再做受控切换。线上旧 app 后台也依赖引擎，若更新其源码必须同时带上新包，不能只复制 app。

本轮未做这些部署动作，未修改数据库、NAS 结果或远端默认分支。
