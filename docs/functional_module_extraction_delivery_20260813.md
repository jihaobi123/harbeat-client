# HarBeat 功能模块提取交付说明（2026-08-13）

## 1. 直接结论

本轮已完成 13 个功能模块的独立提取、独立测试、独立 Git 分支、不可变标签和远端 fresh clone 验收。总计 106 项模块测试通过。生产 App、Jetson、RK systemd、数据库、歌曲、模型和缓存均未替换、未删除、未清理。

当前状态是“核心代码已经安全摘出并可单独调整”，不是“新架构已经上线”。在影子接入、手机真实 E2E、回滚演练通过前，原生产文件仍是运行依赖，禁止删除。

模块总登记见 `modules/REGISTRY.md`。每个模块目录均包含 `MODULE.yaml`、README、测试、来源证明和回滚标签。

## 2. 模块与真实职责

| 层 | 模块 | 当前真实职责 | 测试 | 生产替换 |
|---|---|---|---:|---|
| 验收 | observability-e2e | 部署盘点、手机语义控件、跨端追踪 | 7 | 否 |
| 连接 | device-runtime | RK 身份、端点、健康、播放状态和操作引用 | 20 | 否 |
| 曲库 | library-catalog | 曲库、歌单、manifest 和 ID 映射 | 8 | 否 |
| 云端分析 | audio-preprocess | beat/bar/phrase、能量和 v2 候选 | 7 | 否；Jetson 43/43 验证 |
| 分轨 | stem-separation | Demucs 四 stem 与活动度分析 | 5 | 否；42/43 有四 stem |
| 排歌 | sequence-planner | 默认混音兼容排序和能量曲线 | 5 | 否 |
| 选点 | transition-planner | 自动、快切、能量、风格四种转场 plan | 4 | 否 |
| 渲染 | transition-renderer | v7 快切和 v9 自动接歌 WAV/meta | 3 | 否 |
| 下载 | asset-sync | RK 下载、校验、原子发布、优先同步和取消 | 6 | 否 |
| 编排 | transition-orchestrator | plan/manifest 校验、任务状态机、priority sync 请求 | 5 | 否 |
| 播放 | audio-runtime | RK 双 deck、prepare、schedule、采样时钟触发、resume | 22 | 否 |
| 手机控制 | mobile-dj-control | 三种手动切歌共享请求、任务恢复和播放确认 | 7 | 否 |
| 实体输入 | physical-input | 九键 SFX、暂停、导航事件和旋钮路由 | 7 | 否 |

### 2.1 按用户功能反查模块

| 你看到或操作的功能 | 主功能模块 | 同时依赖的支撑模块 |
|---|---|---|
| 导入歌曲、查看曲库和歌单 | `library-catalog` | `audio-preprocess`、`stem-separation` |
| 歌曲分轨 | `stem-separation` | `audio-preprocess`、`library-catalog` |
| 歌曲鼓点、段落、能量和候选点分析 | `audio-preprocess` | `library-catalog` |
| 自动排歌和能量走势 | `sequence-planner` | `library-catalog`、`audio-preprocess` |
| 正常自动接歌 | `transition-planner` + `transition-renderer` | `asset-sync`、`transition-orchestrator`、`audio-runtime` |
| 手机点击快切 | `mobile-dj-control` + `transition-planner` | `transition-renderer`、`asset-sync`、`transition-orchestrator`、`audio-runtime` |
| 能量切歌预览和确认 | `mobile-dj-control` | 确认后与快切使用同一组转场模块 |
| 风格切歌预览和确认 | `mobile-dj-control` | 确认后与快切使用同一组转场模块 |
| RK 下载歌曲或混音包 | `asset-sync` | `library-catalog` 提供 manifest |
| RK 真正发声、混音和到点切换 | `audio-runtime` | `transition-orchestrator` 提交任务 |
| 手机连接 RK、重连和进度状态 | `device-runtime` | `mobile-dj-control` |
| 三个实体模块、按键、SFX 和旋钮 | `physical-input` | `audio-runtime`；导航键还需要手机 adapter |
| 手机/RK/Jetson 联调和日志定位 | `observability-e2e` | 读取其他模块状态，不参与播放 |

最容易混淆的三个名称：`transition-planner` 负责“决定怎么接”，`transition-renderer` 负责“生成实际衔接音频”，`transition-orchestrator` 负责“确保资源准备完成并命令 RK 到点执行”。

## 3. 目标架构调用链

```text
曲库导入
  -> stem-separation
  -> audio-preprocess
  -> library-catalog
  -> sequence-planner

自动接歌
  -> transition-planner(default)
  -> transition-renderer(v9)
  -> asset-sync
  -> transition-orchestrator
  -> audio-runtime

快切
  -> mobile-dj-control(fast target = queue next)
  -> transition-planner(fast)
  -> transition-renderer(v7)
  -> asset-sync
  -> transition-orchestrator
  -> audio-runtime

能量/风格切歌
  -> preview 只选 target song
  -> 用户确认
  -> mobile-dj-control(energy/style target = selected)
  -> 与快切完全相同的 planner/render/sync/orchestrator/audio-runtime

实体输入
  -> physical-input
  -> SFX/暂停直接进入 audio-runtime
  -> 导航事件经 device-runtime/mobile adapter 进入 mobile-dj-control
```

## 4. 必须保留的当前生产代码

以下文件仍被当前部署直接调用，现阶段不能删除：

| 区域 | 必须保留的核心 |
|---|---|
| Jetson | `app/modules/library/*`、`app/modules/dj_control/default_mix/*`、`cut_strategy.py`、`router.py`、`schemas.py` |
| RK 下载 | `cypher-integration/rk3588-edge/sync-worker/main.py` |
| RK 编排 | `cypher-integration/rk3588-edge/edge-agent/main.py`、`edge_agent/models.py`、`edge_agent/state.py` |
| RK 播放 | `cypher-integration/rk3588-edge/audio-engine/*` |
| 实体输入 | `cypher-integration/rk3588-edge/input-daemon/*` |
| 手机 | `mobile/lib/src/dj_control_page.dart`、`api_client.dart`、`edge_agent_client.dart`、`sync_worker_client.dart`、`live_models.dart` |

模型、歌曲、stem、数据库、render cache、systemd 配置和设备环境也必须保留。模块目录目前是可测试副本，不是生产服务入口。

## 5. 已确认的遗留问题

| 问题 | 影响 | 处理阶段 |
|---|---|---|
| App 页面同时承担 UI、prewarm、规划、同步、提交、轮询和队列修改 | 状态竞争、超时后重复流程、难以单测 | 先接入 mobile-dj-control，再瘦身页面 |
| RK edge-agent 同时承担 HTTP、编排、状态持久化和 audio 转发 | 409/超时难定位 | 接入 transition-orchestrator，保留 HTTP adapter |
| `input-daemon/main.py` 重复定义两次 `KEY_MAP` | 后续修改可能只改一份 | 接入 physical-input 后删除重复定义 |
| 实体键 7-9 只广播事件，手机没有消费映射 | 不能真实触发快切/能量/风格 | 新增 mobile key-event adapter 后验收 |
| 1 首歌没有完整四 stem | stem 功能不能宣称全库完成 | 单独补处理并重新验证 43/43 |
| RK SSH 仅提供旧 SHA-1 KEX | 自动部署/只读探针受阻 | 设备维护窗口升级 SSH，不在业务代码绕过 |

## 6. 下一阶段直接执行顺序

1. 建立新 release 目录，不覆盖当前 Jetson/RK 工作目录；锁定 Python/Dart 依赖。
2. Jetson 先接入 library-catalog、audio-preprocess、sequence-planner、transition-planner 和 transition-renderer，采用旧接口与新模块双跑比对，不切生产流量。
3. RK 先接入 asset-sync，再接入 transition-orchestrator，最后接入 audio-runtime；每次只替换一个 systemd release 软链接。
4. 手机接入 device-runtime 与 mobile-dj-control，把页面中的任务状态迁出；保留当前 UI 外观和 API adapter。
5. 接入 physical-input，并实现 key 7/8/9 到快切/能量/风格操作的显式消费规则。
6. 使用 observability-e2e 在手机真实触发，分别验收自动接歌、快切、能量、风格各 5 次；实体动作各 20 次。
7. 完成弱热点、POST 超时后已接受、RK/Jetson 重启、缓存缺失、重复点击和切点过期恢复测试。
8. 完成单模块回滚和整套 release 回滚演练，形成旧文件引用证明。
9. 只生成清理候选清单并移动到隔离归档区；观察一个完整验收周期后再申请永久删除。

## 7. 最终交付门槛

必须同时满足以下条件，才可以说“新架构可交付并允许清理旧环境”：

- 自动接歌、快切、能量确认切歌、风格确认切歌分别连续 5/5；
- 实体模块每个动作 20/20，键 7-9 确实触发对应手机业务动作；
- 手动切歌 `scheduled <= 12s`、进入衔接 `<= 15s`、RK trigger error `<= 100ms`；
- 无突然静音、硬切、重复播放、目标歌曲错误或进度倒退；
- 核心路径 `degraded=false` 且无静默 fallback；
- 一次操作至多一次 planning、render、sync 和 schedule；
- 新 release 可从远端标签重建，所有外部资产可按 manifest/SHA256 恢复；
- Jetson、RK、手机分别完成单模块回滚和整套回滚；
- import graph、systemd、App 调用和 E2E 均证明清理候选无引用。

## 8. 当前允许与禁止事项

现在允许：单独修改任一 `modules/<name>`，在对应模块分支发布新版本；建立影子 adapter；补充测试和部署清单。

现在禁止：删除旧生产代码；清理 Jetson/RK 环境；让 systemd 直接指向未影子验证模块；把模块 accepted 误认为 App 功能已稳定交付。
