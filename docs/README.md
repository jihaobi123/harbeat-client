# 文档阅读入口

先读 [第二版统一入口](../HARBEAT_V2_START_HERE.md) 和 [继续使用 / 仅参考清单](repository/reference-code.md)。文件名的 v1 不足以判断是否有效，要看以下分类。

| 文档区域 | 怎样使用 |
|---|---|
| [repository](repository/README.md) | 当前源码分区、迁移记录、部署位置与参考区说明 |
| [基础预处理合同](same_style_preprocess_handoff_v1.md)、[人声增补合同](jetson_vocal_activity_handoff_v1.md) | 当前已发布数据仍使用的格式；供数据消费者读取，不因产品第二版而废弃 |
| [backend-handoff-v1](backend-handoff-v1/README.md)、[team-development-v1](team-development-v1/README.md) | 第一版开工任务、API、数据库和跨端协议资料；后续重构，预计不直接使用 |
| `functional_modules_*`、[roadmap](roadmap/README.md)、根目录旧 PROJECT_PLAN/混音计划 | 历史规划和完成记录，不是第二版必须实现的任务书 |
| `v2/backend-owner-handoff.md`、`v2/preprocess-consumer.md` | 先前整理稿，不是基于新 APK 源码完成验收的接口；有未提交修订，暂不作为新后端开工合同 |
| 模型实验、训练、阈值与验证报告 | 特定版本的研究记录，不能据此认定正式模型已替换或准确率已验收 |

旧后端、手机、RK 文档中的“正式开工”“必须实现”“已完成”等措辞仅描述当时版本。新手机接口、数据库设计、RK 数据领取协议须重新确认；目前不要求兼容旧手机 API。
