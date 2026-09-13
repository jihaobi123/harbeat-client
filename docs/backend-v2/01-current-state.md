# 01｜仓库、Jetson 和 APK：哪些已核实

[返回手册](README.md)。核对时间：2026-09-13。本页的“已有”来自源码和只读检查；“建议”是待实施方案，两者不混写。

## 一、拉哪个仓库，先打开哪里

仓库：`jihaobi123/harbeat-client`；当前整理分支：`archive/music-analysis-history-20260830`。分支名有历史原因，但这里包含正式预处理，不要从旧 main 判断能力。

```bash
git clone --single-branch --branch archive/music-analysis-history-20260830 https://github.com/jihaobi123/harbeat-client.git
cd harbeat-client
git rev-parse HEAD
```

记录最后一条命令输出作为开发基线。不要直接运行根目录旧部署脚本；不要把 GitHub 源码误当成已包含音乐、模型、数据库或访问凭据的数据包。

## 二、A 类：第二版已有、继续使用

| 功能 | 实际代码 | 给后端什么 | 不能误解成什么 |
|---|---|---|---|
| BPM、Beat、拍号、小节 | `preprocessing/engines/analysis.py` | publisher 转为 `analysis.tempo`、`analysis.beat_grid` | 不在 API 请求线程重新跑分析 |
| 段落边界和名称 | `preprocessing/runners/songformer.py` + 上述整合引擎 | `analysis.sections`，保留 source / fallback_used | 正式来源仍是 SongFormer，实验分类器不接入 |
| Demucs 四轨 | `preprocessing/publisher.py::_run_demucs` | vocals、drums、bass、other 文件 | 不是五条鼓子轨 |
| MDX23C 鼓细分 | `music_analysis/drum_analysis/mdx23c_separator.py`，publisher 调用 | kick、snare、hihat、tom、cymbal 五条音频 | 输入是 Demucs drums，不是原曲；没有独立 808 子轨 |
| 鼓、低频、节奏等摘要 | `preprocessing/engines/stem_analysis.py` 与特征引擎 | `analysis.drum_groups` 与质量标记 | 五组语义摘要不等于五条音频；一些仍是频谱代理结果 |
| 人声出现时间 | `preprocessing/vocal_activity.py::publish_vocal_activity` | 独立 JSON，绑定基础 run 和 vocals SHA256 | Silero 检测时间，不再分离声音，不识别歌词 |
| 单曲发布 | `preprocessing/publisher.py::run_same_style_preprocess` | staging → 校验 → run + `_SUCCESS` + latest | 此底层函数不自动发布 Silero，CLI 才追加该步骤 |
| 曲库与补分析 | `preprocessing/cli/` 六个入口 | 导入、基础发布、人声补充、校验及打包 | 不是完整业务数据库任务队列 |
| 消费格式 | `contracts/schemas/analysis/` | 基础 1.2.0、人声 1.0.0 | 产品第二版不要求 JSON 全改成 2.0 |
| 模型运行包装 | `deploy/jetson/` | 已有环境和模型路径组织方式 | 新目录源码还没切换线上；要独立 release 验证 |

这些是“继续使用已有能力”，不是“每个输出准确率已通过验收”。不要重写模型、改阈值来完成业务后端。

## 三、B 类：能借鉴，但不能整包当第二版

| 代码 | 可以借鉴什么 | 为什么不能直接整包复用 |
|---|---|---|
| `modules/asset-sync/src/harbeat_asset_sync/core.py::sha256_file`、`verify_download`、`atomic_publish` | 分块计算 hash、核对大小与 hash、同文件系统原子发布 | `AssetSpec` 允许 hash/size 缺失；第二版交付必须都有。相邻缓存逻辑允许 converted_from，不能把转码文件视为原音轨校验成功 |
| `modules/library-catalog/.../identity.py` | 显式区分不同 ID 的思路 | 使用 library_song_id/catalog_song_id，不是 NAS track_id/run_id 绑定 |
| `modules/device-runtime/.../connection.py` | 超时、失联、状态过期的分类及测试 | 旧 endpoint/会话协议，不等于新设备身份和热点主动领取协议 |

本期建议直接使用已有标准库实现小型通用函数或按测试适配，不把旧包挂进新服务。借鉴一段函数不改变整个模块的“第一版参考”定位；真正复用后应记录调用位置和新合同测试。

## 四、C 类：第一版，仅作参考

| 区域 | 原来干什么 | 本期处理 |
|---|---|---|
| `app/main.py`、`app/modules/*` 业务代码 | 旧 API、用户、歌单、会话、推荐、后台分析状态 | 看历史，不用旧 API 约束新 APK；不直接挂进新 `/api/v2` |
| `app/shared/`、旧 ORM | 旧配置、认证、数据库连接和表模型 | 只用来理解旧数据；不删除表，不默认继承密码算法和字段 |
| `app/modules/library/analysis.py` 等转发 | 保护旧调用者的导入路径 | 不是第二套旧算法；新代码从 preprocessing 导入 |
| `mobile/`、`web/`、`cypher-integration/flutter-app/` | 历史客户端和页面操作 | 没有证据对应新 APK，不能当新前端 |
| `rk_deploy/`、`cypher-integration/rk3588-edge/` | 旧下载、播放、混音、控制与部署 | 交给 RK 负责人参考，后续重构 |
| 根 `jetson/` | DJ 和分析补丁副本 | 不是正式预处理目录，禁止覆盖正式模型 |
| `deploy/cloud_gateway/app/main.py` | 旧通用 API/RK 转发 | 缓冲完整请求/响应、60 秒超时、没有 HEAD 路由；不适合直接转发大音轨，也不等于新鉴权接口 |
| 根 Docker/旧部署脚本、旧任务书 | 历史整套服务安装和分工 | 仅参考；第二版独立部署和迁移 |

11 个 `modules/` 保留包的整体定位仍是第一版：library-catalog、device-runtime、asset-sync、observability-e2e 可参考目录/连接/传输/测试；sequence-planner、transition-planner、transition-renderer、transition-orchestrator、audio-runtime 属旧排歌/混音/执行/播放；mobile-dj-control、physical-input 属旧手机/按键控制。**均不是本期后端必须接入的包。** 版本和来源见 [模块清单](../../modules/REGISTRY.md)。

`research/`、`experiments/`、`reports/` 保存研究、训练和证据，不判为无用，不默认加载。Pair Score 实现保留，但 70%/85% 阈值仍未完成人工数据校准，本期不让它控制自动混音决策。

## 五、Jetson 实际部署与数据库

| 项目 | 本次只读结果 |
|---|---|
| 设备 | Jetson；私网地址 `100.87.142.21`，不是阿里云也不是 RK |
| 正式预处理指针 | `/opt/harbeat/same-style-preprocess-current` |
| 指针实际指向 | `/opt/harbeat/releases/same-style-preprocess-a268a5c-vocal-20260913` |
| 旧 API 服务 | `harbeat-api.service` active；WorkingDirectory `/opt/harbeat/releases/analysis-shadow-72564be` |
| 模型 Python | `/opt/harbeat/current/venv/bin/python`，另有 vendor / 附加环境；不是普通干净 Python |
| 数据根 | `/mnt/nas/harbeat/preprocess` |
| NAS 挂载 | `/mnt/nas/harbeat`，CIFS，来源 `//192.168.5.63/harbeat` |
| 数据库和缓存 | PostgreSQL、Redis 服务 active；已有数据库 `rhythm_prism` |

只查询了数据库表结构，没有导出用户记录、密码、Token 或业务内容。public 下有 13 张表：audit_logs、library_songs、playlist_songs、playlists、rk_session_events、session_events、sessions、song_cues、song_tags、songs、user_interaction_logs、user_profile_tags、users。

库中有旧曲库分析 JSON/秒数/音轨字段；没有发现本方案需要的独立 analysis_runs、vocal_reports、assets、preparations、device_credentials 等表。JSON 里可能已有历史状态，但不等于具备第二版外键、唯一性和授权关系。

本地 ORM 和线上也并非完全相同：线上有 `analysis_stage`、`analysis_error`、`original_sha256` 等列，不能仅导入本地 ORM 就认为数据库已同步。新版需要显式迁移设计；不运行旧 `create_all()` 来“修复”存量库。

阿里云 `8.136.120.255`：nginx active，HTTP/HTTPS 入口转到 `127.0.0.1:8080`；`harbeat-gateway.service` active。另一个 `cloud_gateway.service` 的退出码为 1，处于自动重启。两者 WorkingDirectory 都是 `/opt/harbeat-api`。还有 8765/8766/8767 标注评审服务，不能被本次后端部署覆盖。没有核验所有公网 URL 和鉴权链路；本次没有停服务或改 nginx。

## 六、NAS 实际已有数据

| 索引 | 本次结果 |
|---|---|
| `published/indexes/edm_8_handoff_v1.json` | 8 首，基础均 degraded |
| `published/indexes/edm_8_vocal_activity_v1.json` | 8 首，人声均 ready |
| `published/indexes/style_library_v1.json` | 157 首，基础均 degraded |
| `published/indexes/style_library_vocal_activity_v1.json` | 157 首，processed=157，人声均 ready |

抽查 The Spectre：core、sections、stem_separation、mdx23c 都 ready；drum_groups 为 degraded。标记有 `bass_pitch_spectral_fallback_used`、`dedicated_drum_model_unavailable`、`percussion_uses_spectral_drum_proxy`、`spectral_proxy_fallback`。这说明需保留质量风险，不是把所有歌曲标成 failed，也不能清空标记伪装全部 ready。

## 七、新 APK：已确认的事实与初步页面对应

文件名 `HarBeat-v0.5-release.apk.1.1`，大小 56,920,102 bytes。
SHA256：`0fa6f0d72ed7cccb1cbda6304b42aef21c5f7e284f4348bfef459780a98b215f`。
包名 `com.example.harbeat`，包内 versionName=`0.1.0`、versionCode=`1`，不能按外部文件名当成版本已核实。

用 Android SDK aapt 核对 Manifest：有 ACCESS_NETWORK_STATE、WAKE_LOCK 等，**没有 INTERNET 权限**。Flutter AOT 包含 `libapp.so`；assets 里有 `assets/audio/preview.wav`。这些只能证明包内内容，不能证明页面连接过后端或 RK。

先从 AOT 字符串发现以下符号，再连接用户的 Android 手机核对主要页面。表中接口仍是“初步建议”，不是抓包结果：

| 包内可确认线索 | 初步理解 | 后端初步接口 / 需前端核对 |
|---|---|---|
| HomeScreen | 首页 | 汇总曲库/设备/当前准备任务；是否独立 home 接口由页面确认 |
| MusicScreen、TrackDetail、TrackInfo | 曲库及歌曲详情 | GET tracks / tracks/{id}；详情读取已有分析摘要 |
| PlaylistDetail、createPlaylist、renamePlaylist、movePlaylistTrack | 歌单增删改和顺序 | 歌单 CRUD，使用版本号避免多人覆盖；本期是否云端同步待定 |
| prepareTracks、togglePrepareTrack、selectPlaylistForPrepare | 选择歌曲准备资源 | POST preparations，展开为固定 track_ids，不让歌单后续修改改变任务 |
| DeviceScreen、PairingScreen、pairDevice、deviceSnapshot | 设备显示/配对 | 查设备和授权绑定；不能按输入设备 ID 自动获得控制权 |
| LiveScreen、`LIVE / RK FACT`、nextTrack、previousTrack | 现场状态及切换线索 | 状态来自 RK；播放控制命令另评审，不拿下载成功代替播放成功 |
| ProfileScreen、`PROFILE / PERSONAL` | 个人资料 | GET/PATCH me 的字段待确认，未证实存在何种登录页 |
| local_store.dart、media_storage_io.dart、audio_service.dart、`NOW / PHONE` | 可能涉及本地存储/试听 | 手机试听和 RK 主输出必须区分；不能把内置 preview 当云端曲目 |

用户随后连接了 Android 手机。本次通过 ADB 检查已安装包，SHA256 与上面的交付包完全一致，并实看：首页、音乐推荐/搜索/曲库/歌单及歌单详情、设备、配对、我的、准备流程四步、Pad 编辑布局。逐页面对应见 [06：真机页面与后端](06-phone-page-mapping.md)。

最关键证据：PREP / 04 页面明确写“音乐与 Pad 预设已完成 Mock 校验”。因此 READY 100%、ONLINE、18ms、设备曲目数等界面数字，不能作为后端联通和实际下载完成的证据。安装包仍未声明 INTERNET 权限。

为查看准备后续页面，临时勾选了两首展示歌曲，完成查看后已取消两项勾选并返回首页；没有点击试听、播放全部、测试音、开始使用，也没有提交配对或修改歌单/Pad。未进入可能触发播放的 Live 流程，未抓包，源码仍未提供。**完成的是页面核对和初步设计，不是全页面联网验收。**

联网权限需前端在源码声明并重新构建；仅修改后端不能解决。依据：[Android 官方网络连接说明](https://developer.android.com/develop/connectivity/network-ops/connecting)。

## 八、本轮可运行校验的范围

本手册只读 reader 已在 Jetson 实际读取完整 EDM 8 首基础与人声索引：共 112 个文件、2,826,072,608 bytes。逐项核对了 JSON schema、JSON hash、完成标记、基础/人声绑定，以及音频文件存在和大小；**本轮未重新计算这 80 条真实音频的 SHA256**。正式目录激活前仍应运行 `--verify-audio`。完整音频 hash 分支另用离线测试样本验证，不混称真实曲库全量 hash 验收。
