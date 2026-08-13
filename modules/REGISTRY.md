# Functional module registry

This registry tracks independently extracted modules. `accepted` means the
module passed a fresh-clone test and immutable tag check. It does not mean the
module has replaced production code.

| Module | 对应产品功能 | 调用时机 | Version | Fresh-clone implementation | Tests | Status | Production integration |
|---|---|---|---|---|---:|---|---|
| `observability-e2e` | 三端测试、日志采集、故障定位 | 部署验收和复现问题时 | `0.1.0` | `53e8736961a0cd8251a6c3f8c7ad5f016e8b2b02` | 7 | tested, pushed, accepted | Read-only tools; no runtime replacement |
| `device-runtime` | 手机连接 RK、重连、读取播放状态 | App 连接设备及播放状态刷新时 | `0.1.0` | `523d0053c145a9e70541505308f44a555bcd742e` | 20 | tested, pushed, accepted | Adapter and dual-read migration still required |
| `library-catalog` | 曲库、歌单、歌曲 ID 和资源清单 | 导入曲库、选歌和准备同步资源时 | `0.1.0` | `56d92b37a61bb9ed606d94f9f254ca575ba567db` | 8 | tested, pushed, accepted | Authenticated mobile replay still required |
| `audio-preprocess` | 歌曲预处理、鼓点/段落/能量和候选切点 | 歌曲进入曲库后的离线处理阶段 | `0.1.0` | `237ee91b7336613ff1fae54c0567c78261c8f19a` | 7 | tested, pushed, accepted | 43/43 real Jetson payloads pass gate; production replacement not applied |
| `stem-separation` | 人声、鼓、贝斯、其他四轨分离 | 歌曲离线预处理和 stem 分析时 | `0.1.0` | `e9e3f515ea80dbb6a78ba92a995c66ba3bae281a` | 5 | tested, pushed, accepted | 42/43 songs have four stems; one remains unprocessed |
| `sequence-planner` | 自动排歌和整套能量走势 | 用户生成播放顺序、开始自动播放前 | `0.1.0` | `f54e38dfaad09e586d8d52fe3d95cdaa0f3650ae` | 5 | tested, pushed, accepted | 43 input, 30 default-compatible output in 168ms; production replacement not applied |
| `transition-planner` | 自动接歌、快切、能量切歌、风格切歌的选点和对齐 | 已确定上下两首歌后、渲染转场前 | `0.1.0` | `b276cff9193cd13b46e304a28232958c51f9f1d4` | 4 | tested, pushed, accepted | Four plan entry points match current production planner; Jetson production replacement not applied |
| `transition-renderer` | 生成两首歌之间实际听到的混音衔接 WAV/meta | 选点完成后、资源发送到 RK 前 | `0.1.0` | `f903c5b22bb9d79f5f911b831558809fcd3253ca` | 3 | tested, pushed, accepted | v7 fast-cut and v9 normal WAV/meta paths pass; Jetson replacement not applied |
| `asset-sync` | 将歌曲和混音衔接包下载、校验并缓存到 RK | 播放或切歌所需资源尚未在 RK 时 | `0.1.0` | `d8a8c5a3aeca3154e14466c459573a0e562d6e5d` | 6 | tested, pushed, accepted | Manifest, cache, atomic download, cancellation and priority sync paths pass; RK SSH probe blocked by legacy KEX |
| `transition-orchestrator` | 串联同步、准备、定时切换并记录任务状态 | 用户确认切歌后到 RK 接受 schedule 之间 | `0.1.0` | `423a65e9b620ba4b54741edfb2a481bf9ee566ac` | 5 | tested, pushed, accepted | Pure plan/manifest validation, priority sync request and task state machine; production replacement not applied |
| `audio-runtime` | RK 实际播放、双 deck 混音、到点切换和接续目标歌曲 | 整个播放过程及转场真正发声时 | `0.1.0` | `6223dddb8dfc01493a393b046c787e202a5177ed` | 22 | tested, pushed, accepted | Real RK dual-deck engine, render prepare/schedule/sample-clock trigger/resume and socket contract; systemd replacement not applied |
| `mobile-dj-control` | 手机快切、能量/风格预览确认、任务恢复和状态显示 | 用户点击三个切歌功能及等待执行结果时 | `0.1.0` | `16dadc03834d385012637b0c8978668d6b54e61e` | 7 | tested, pushed, accepted | Pure Dart shared fast/energy/style confirm request and task recovery contract; Flutter integration not applied |
| `physical-input` | 三个实体模块、九键 SFX、暂停和旋钮输入 | 用户操作实体按键或旋钮时 | `0.1.0` | `bfd94afdd0af3774f77f5c6fb6953222974d005e` | 7 | tested, pushed, accepted | MYKB key/SFX/volume routing fixed as pure contract; keys 7-9 lack a deployed mobile DJ action consumer |

Module branches remain `module/<module-name>`, and immutable rollback tags are
`module/<module-name>/v0.1.0`.

The complete 13-module baseline is available from branch
`delivery/functional-module-extraction-20260813` and immutable tag
`functional-modules/v0.1.0`. Its machine-readable inventory is
`modules/BASELINE-v0.1.0.json`.

## Acceptance rules

- Every accepted commit must be reachable from its module branch and tag.
- Tests must pass from a fresh clone of the remote branch.
- Deployment probes must be read-only until a module-specific integration gate
  is approved.
- Existing production files and environments remain protected until all core
  modules pass a fresh-environment end-to-end replay.
