# HarBeat 13 模块干净最终版执行规范

## 1. 目标

以 `functional-modules/v0.1.0` 为不可变行为基线，逐模块形成职责单一、依赖显式、无静默 fallback、可独立测试和可独立部署的最终代码。整理不是一次性重写，也不允许在同一提交中改变算法效果。

最终版定义为：

- 模块公开入口稳定，内部实现可替换；
- 核心逻辑不直接依赖 HTTP、数据库、文件系统或设备，外部能力通过 adapter 注入；
- 每种兼容行为有明确版本、到期条件和测试，不存在隐式旧路径；
- 错误显式返回，不能因为数据缺失自动换成不可追踪方案；
- 单模块、契约、行为对比、性能、三端 E2E 和回滚均通过。

## 2. 版本策略

| 版本 | 含义 |
|---|---|
| `v0.1.0` | 当前行为基础版，永久保留 |
| `v0.2.0` | 内部清理版，原则上不改变产品行为 |
| `v0.3.0` | 影子接入和 adapter 完成 |
| `v1.0.0` | 生产替换、E2E、性能和回滚全部通过 |

每个模块独立发布版本。完整系统只有在 13 个模块兼容矩阵通过后才能创建 `functional-modules/v1.0.0`。

## 3. 统一清理步骤

每个模块严格执行：

1. 从模块 `v0.1.0` 建立 clean 分支。
2. 收集公开函数、契约、错误、性能和真实样本输出。
3. 增加 characterization tests，锁定行为。
4. 标记所有 legacy、fallback、兼容桥、宽泛异常和重复实现。
5. 将纯领域逻辑与 adapter 分离。
6. 删除不可达重复代码；兼容路径改为显式 policy。
7. 比较 `v0.1.0` 与 clean 输出，不允许无说明漂移。
8. 运行模块测试、契约测试和性能基准。
9. 在影子 release 双跑并记录结果。
10. 通过真实手机/RK/Jetson E2E 和回滚演练后发布版本。

## 4. 整理顺序

按依赖由底向上，避免上层不断适配变化中的下层：

| 顺序 | 模块 | 主要整理内容 | v0.2.0 通过条件 |
|---:|---|---|---|
| 1 | `physical-input` | 固定单一映射表，拆 HID/audio/HTTP adapter | 所有键路由契约一致，核心无设备依赖 |
| 2 | `stem-separation` | 增加 CLI、配置和 runner adapter | 四轨完整性严格，模拟与真实单歌通过 |
| 3 | `library-catalog` | 固定 ID 类型和 repository port | 不按名称匹配，manifest schema 全通过 |
| 4 | `device-runtime` | 移除隐式旧地址状态，显式 migration | 热点换 IP 后 device_id 与任务隔离正确 |
| 5 | `audio-preprocess` | 拆 analyzer、candidate builder、persistence | 同输入 v2 候选行为一致，无实时 fallback |
| 6 | `sequence-planner` | preset schema 化，兼容 preset 独立 adapter | 排序确定性与基线一致 |
| 7 | `transition-orchestrator` | 纯状态机、幂等和 deadline 规则固定 | 重复请求和超时恢复状态确定 |
| 8 | `asset-sync` | transport/cache/verification 分层 | 并发合并、原子发布和校验全部通过 |
| 9 | `transition-renderer` | 共享 DSP pipeline，v7/v9 变成 policy | WAV/meta parity 和性能门槛通过 |
| 10 | `transition-planner` | 候选、评分、约束、对齐、模式策略分层 | 四入口 parity，无静默 v1/raw fallback |
| 11 | `audio-runtime` | 状态机、调度、DSP、设备和 socket 分层 | 触发误差、续播和无静音通过真实 RK |
| 12 | `mobile-dj-control` | controller 与 Flutter/network/storage adapter 接入 | 三种切歌共享一次执行链路 |
| 13 | `observability-e2e` | operation schema、采集 adapter 和报告统一 | 三端同一 operation 可完整追踪 |

`observability-e2e` 的现有能力从第一步开始用于取证，但其最终接口在其他模块状态字段稳定后再冻结。

## 5. 高风险模块专门规则

### 5.1 `transition-planner`

目标结构：

```text
domain/candidates.py
domain/scoring.py
domain/constraints.py
domain/alignment.py
policies/default.py
policies/fast.py
policies/energy.py
policies/style.py
contracts/plan.py
adapters/legacy_song.py
```

必须移除的形态：模式函数各自复制选点流程、数据缺失后静默扫描 raw beat、同一函数同时负责候选生成/评分/输出兼容。允许保留的兼容只能放在命名明确的 adapter，并通过参数显式开启。

### 5.2 `audio-runtime`

目标结构：

```text
domain/playback_state.py
domain/transition_state.py
scheduler/sample_clock.py
engine/deck.py
engine/render_executor.py
ports/audio_output.py
adapters/sounddevice_output.py
adapters/unix_socket.py
```

不能直接重写实时 callback。先对状态和命令建立 characterization tests，再逐层移动。设备 fallback 必须由启动配置选择，不得在播放中无提示切换设备。

### 5.3 `transition-renderer`

v7/v9 不再维护两份完整流程，改为共享加载、对齐、DSP、写出和验证流程，由 renderer policy 指定差异。任何 WAV 变化都必须记录响度、峰值、relative jump、长度和 resume point 对比。

## 6. 质量门槛

每个 clean 模块必须满足：

- 单元与契约测试全部通过；
- 新代码中无未说明 `TODO/FIXME`；
- 不新增裸 `except Exception`；边界捕获必须转换为 typed error 并保留 cause；
- fallback 必须是显式 policy、可观测且默认关闭；
- 依赖版本可重复安装；
- 核心测试不要求真实网络、数据库或音频设备；
- 真实依赖测试作为单独 integration profile；
- `MODULE.yaml`、README、contract 和 provenance 同步更新。

## 7. 最终系统验收

只有满足以下条件才发布 `functional-modules/v1.0.0`：

- 13 个模块都存在独立最终标签和 SHA256；
- fresh clone 可以执行完整模块测试；
- Jetson/RK 可从空 release 目录重建；
- 自动接歌、快切、能量切歌和风格切歌各连续 5/5；
- 快切 schedule `<=12s`、进入衔接 `<=15s`、trigger error `<=100ms`；
- 分轨对真实歌曲输出四个有效 stem；
- 实体功能每个动作 20/20；
- 弱热点、重复点击、响应丢失、进程重启和缓存缺失恢复通过；
- 所有操作能用一个 `operation_id` 跨手机、Jetson、RK 追踪；
- 完成逐模块和完整 release 回滚演练；
- 生产旧代码仅在无静态、运行、数据和配置引用证据后进入归档。

## 8. 禁止事项

- 禁止把整理代码与改变混音算法效果合并。
- 禁止为了测试通过重新引入静默 fallback。
- 禁止一次同时替换 Jetson、RK 和手机。
- 禁止删除 `v0.1.0` 基线、生产数据或旧 release。
- 禁止在没有真实设备验收时宣布最终版可交付。
