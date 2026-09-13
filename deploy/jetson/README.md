# Jetson 正式预处理运行包装

这里不是旧 `jetson/` 补丁目录。对应正式实现位于 [preprocessing](../../preprocessing/README.md)，继续维护。

| 文件 | 作用 |
|---|---|
| `run-same-style-preprocess` | 单曲预处理运行包装 |
| `run-same-style-library-import` | 曲库导入运行包装 |
| `run-vocal-activity-backfill` | 为已发布歌曲补 Silero 人声时间报告 |
| `harbeat-same-style-library-import.service` | 曲库导入 systemd 单元 |
| `harbeat-vocal-activity-backfill.service` | 人声补分析 systemd 单元 |
| `harbeat-same-style-preprocess.env.example` | 运行环境变量示例，不含实际密钥 |
| `requirements-vocal-activity.txt` | 人声步骤依赖清单，不是全部模型环境 |

本轮已整理仓库运行入口，但没有切换线上 release。执行前核对模型环境、NAS 挂载、目标 release 和任务参数；不能把此目录直接覆盖在线 API 服务。具体位置见 [部署说明](../../docs/repository/deployment-map.md)。
