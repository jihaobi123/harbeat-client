# 第一版业务模块：参考代码，不是第二版任务清单

<!-- harbeat:reference-only -->
这些业务模块预计在第二版中重构，不默认复用旧 API。保留原路径只为阅读和保护尚存引用，本轮没有继续开发旧业务。

| 区域 | 历史职责 |
|---|---|
| auth、users、profiles | 鉴权、用户与资料 |
| library、playlists | 曲库、歌单、入库和旧后台分析任务 |
| assets、manifest、stream | 原资源访问、清单和播放流 |
| music、recommendations | 原歌曲业务与推荐 |
| dj_control、session、sessions、dev_mix | 旧排歌、切歌、会话和混音操作 |
| voice、fangpi | 原语音/关键词与外部音乐来源集成 |
| health、router.py、models.py | 原健康检查、路由及 ORM 注册 |

library 中已迁出的分析文件仅转发到 preprocessing/engines，当前正式预处理仍继续维护。其余旧业务和表定义不是新后端接口依据。是否复用个别实现需重新确认，不将旧混音逻辑安排到 Jetson 作为必做功能。

见 [参考代码说明](../../docs/repository/reference-code.md)。
