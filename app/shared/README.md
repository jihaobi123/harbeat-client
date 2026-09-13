# 第一版后端基础设施参考

<!-- harbeat:reference-only -->
第二版后端后续重构，预计不直接使用这里的旧业务基础设施；本目录不是必须沿用的技术/字段合同。

- `database.py`：原数据库连接及 ORM 基类；业务表定义在 app/modules 下各 models.py。
- `config.py`、`security.py`：原配置与鉴权实现，不代表新 APK 的登录/授权要求。
- `redis.py`、`audit.py`、`responses.py`：原缓存、审计和响应封装。
- `command_line.py`：例外，仅为已迁移通用工具的旧导入转发；实际实现为 music_analysis/command_line.py，没有业务逻辑副本。

可以据此了解存量数据，但不能因为代码被标为参考就删除数据库表或重置数据。数据库迁移要在新设计确认后单独做。本轮不改任何连接、字段或配置值。
