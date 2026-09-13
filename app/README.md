# app：现有业务后端，尚不是完整第二版接口

## 已经分开的部分

BPM、SongFormer 结果整合、轨道特征及其验证/校准实现已移到 `preprocessing/engines/`。`app/modules/library/` 的同名旧文件只做兼容转发，没有第二套算法。

业务后台 `background_tasks.py` 仍保留原有状态机和数据库写入；调用新位置的同一份引擎。没有借目录整理改变旧服务的执行方式、路由或数据库字段。

## 这里还负责什么

| 目录 / 文件 | 当前职责 | 整理边界 |
|---|---|---|
| `main.py`、`modules/router.py` | FastAPI 启动与总路由注册 | 保留现行启动方式；未宣称与线上所有路由完全一致 |
| `shared/database.py`、各业务 `models.py`、`modules/models.py` | 数据库连接、ORM、模型注册 | 未迁表、未更名字段、未执行 create_all |
| `modules/library/` 的 router/service/models/background_tasks | 旧曲库 API、入库、后台任务 | 仍有数据库耦合；后续才分离 V2 曲库与预处理任务适配层 |
| `modules/auth/`、users、profiles、playlists | 身份、用户、歌单 | 现有实现保留，不据此决定新 APK 的最终接口 |
| `modules/assets/`、manifest、stream | 原有资源访问接口 | 不等于已实现新的 NAS 版本化授权下载协议 |
| `modules/music/`、dj_control、session、sessions、dev_mix | 历史推荐/会话/切歌/混音业务 | 总路由仍有引用，不能直接删；V2 实时混音归 RK 负责人 |
| `modules/recommendations/`、fangpi、voice | 其他原业务能力 | 尚未确认 V2 是否需要，暂不删除 |
| `modules/library/analysis_vocal_patch_gpu.py` | 旧后台使用的人声修补 | 不是当前 NAS 交付的 Silero 入口；仍有调用，不能直接删除 |

当前路由注册有 16 个业务 router。迁移到 V2 前应逐个核对：调用者、鉴权、依赖表、输入输出、替代接口、删除条件；不能只按目录名字决定退役。

## 后端开发现在怎样使用

- 阅读或修改分析算法：去 [共享引擎](../preprocessing/engines/README.md)，不要在旧转发文件添加业务代码。
- 消费歌曲结果：以 `preprocessing/publisher.py` 和 `contracts/schemas/analysis/` 的发布合同为准，而非直接序列化 ORM 或内部计算字典。
- 新手机接口：尚需结合新 APK 页面与实际数据库设计，本次整理没有生成或上线这些接口。
- 线上 Web API 与离线预处理不是同一个 release；不要直接覆盖 `/opt/harbeat/current`。见 [部署说明](../docs/repository/deployment-map.md)。
