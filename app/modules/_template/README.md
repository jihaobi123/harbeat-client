# Module Template

新增功能时可以复制这个目录，然后按下面步骤接入：

1. 重命名目录，例如 `battle_rooms`
2. 在模块内实现 `schemas.py / service.py / router.py`
3. 如果需要数据库表，再新增 `models.py`
4. 在 `app/modules/router.py` 注册路由
5. 如果新增了模型，确保它被 `app/modules/models.py` 导入
