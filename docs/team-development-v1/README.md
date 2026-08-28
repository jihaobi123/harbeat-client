# HarBeat 四方协作开发开工包

版本：`v1.1-draft`
日期：`2026-08-28`
协作分支：`integration/harbeat-contract-first-v1`
代码基线：`d71acfa29cc7a0b3db0d09adea87fc73828b914f`

## 1. 这套文件怎么发送

先把下面这份共同文件发给四位负责人：

- [00_HarBeat_四方协作开发总则.md](00_HarBeat_四方协作开发总则.md)

再分别发送对应任务书：

- 后端负责人：[HarBeat_后端负责人开工与协作说明.md](role-handoff/HarBeat_后端负责人开工与协作说明.md)
- 手机前端负责人：[HarBeat_手机前端负责人开工与协作说明.md](role-handoff/HarBeat_手机前端负责人开工与协作说明.md)
- 服务端音乐算法负责人：[HarBeat_服务端音乐算法负责人开工与协作说明.md](role-handoff/HarBeat_服务端音乐算法负责人开工与协作说明.md)
- RK3588 负责人：[HarBeat_RK负责人开工与协作说明.md](role-handoff/HarBeat_RK负责人开工与协作说明.md)

项目负责人另外保留：

- [05_任务状态评审与变更模板.md](05_任务状态评审与变更模板.md)
- [contracts/README.md](../../contracts/README.md)

## 2. 文件之间的关系

本目录是“谁做什么、按什么顺序、如何协作、什么才算完成”的开工入口。

`docs/backend-handoff-v1/` 是详细的领域、API、算法、RK、Manifest、错误和验收参考。两者发生冲突时按以下优先级处理：

1. 已评审合并的机器可读合同：OpenAPI、JSON Schema、fixture；
2. 本目录的四方协作总则和责任边界；
3. `docs/backend-handoff-v1/` 的详细设计；
4. 当前旧代码行为；
5. 聊天记录、截图和口头描述。

任何人发现冲突都必须登记，不得自行选择一个版本继续开发。

## 3. 当前仓库状态的重要说明

当前工作区包含大量尚未提交的音乐算法改动，新分支是在原工作区基础上创建的，这些改动没有被删除或覆盖。

当前状态不能视为正式 release：

- 后端仍以现有 FastAPI/SQLAlchemy 业务模型为主；
- 音乐分析仍主要由 FastAPI `BackgroundTasks` 串行触发并直接写 `LibrarySong`；
- 算法存在正在更新但尚未全部进入稳定提交的验证、校准和 Schema 文件；
- 手机中央 API、RK 局域网协议和 Manifest 仍存在目标合同与旧实现并存；
- RK edge-agent、sync-worker、audio-engine、input-daemon 已有骨架，但持久化配对、操作账本、outbox 和重启恢复尚未形成完整生产闭环。

因此，本轮开发采用“合同先行、兼容迁移、分阶段替换”，禁止把旧代码现状直接宣布为正式合同。

## 4. 开工前每位负责人必须回复

收到文件后，每位负责人必须提交一次开工回执：

```text
负责人/角色：
负责模块：
确认使用的仓库和分支：
已阅读的合同：
认领的 P0 任务：
发现的合同冲突：
需要其他负责人提供的输入：
计划先提交的 Schema/fixture/代码：
当前阻塞项：
```

未提交回执前，不进入跨端接口开发。

## 5. 状态术语

能力现状使用：

- `CURRENT`：当前代码已存在，并有可复现测试证据；
- `PARTIAL`：存在实现，但不满足目标合同或恢复要求；
- `MISSING`：目标能力不存在；
- `CONFLICT`：代码、文档或不同端实现互相冲突；
- `VALIDATION_BLOCKED`：代码存在，但没有足够证据允许生产声明。

任务进度使用：

- `NOT_STARTED`
- `IN_PROGRESS`
- `BLOCKED`
- `READY_FOR_REVIEW`
- `ACCEPTED`

只有评审和验收通过后才能使用 `ACCEPTED`。
