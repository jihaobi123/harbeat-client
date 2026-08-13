# HarBeat 13 个功能模块 v0.2.0 开发交接文档

文档日期：2026-08-13
适用仓库：`jihaobi123/harbeat-client`
统一分支：`delivery/functional-modules-clean-v0.2`
统一标签：`functional-modules/v0.2.0`

## 1. 交付结论

当前代码已经形成两个可回溯层级：

| 层级 | 版本 | 用途 | 测试 | 是否接管生产 |
|---|---|---|---:|---|
| 基础第一版 | `v0.1.0` | 冻结提取时的行为，作为回归和回滚基准 | 106 | 否 |
| 干净边界版 | `v0.2.0` | 将核心规则与网络、数据库、设备、UI adapter 分离 | 146 | 否 |

`v0.2.0` 是下一轮开发的默认基础。它解决的是模块边界、契约、测试和版本管理问题，不代表生产系统已经重构完成。

明确状态：

```text
production_integration_applied = false
production_replacement_applied = false
```

任何人不得仅凭 146 项测试通过，就删除或替换手机、Jetson、RK 当前部署代码。生产替换必须经过 adapter、影子双跑、真实设备验收和回滚演练。

## 2. 为什么分成 13 个模块

系统按一条真实 DJ 调用链拆分：

```text
曲库导入
  -> library-catalog
  -> stem-separation
  -> audio-preprocess
  -> sequence-planner

播放和切歌
  -> mobile-dj-control / physical-input
  -> device-runtime
  -> transition-planner
  -> transition-renderer
  -> asset-sync
  -> transition-orchestrator
  -> audio-runtime

全链路取证
  -> observability-e2e
```

边界规则：

- 选下一首歌属于 `sequence-planner` 或上层能量/风格选择策略。
- 确定两首歌怎么接属于 `transition-planner`。
- 把计划生成实际 WAV/meta 属于 `transition-renderer`。
- 把资源放到 RK 属于 `asset-sync`。
- 管理 prepare/schedule 任务属于 `transition-orchestrator`。
- 真正从声卡播放和到点切换属于 `audio-runtime`。
- 手机只表达意图、显示状态和恢复任务，不直接做音频处理。

这些职责禁止重新合并成一个大函数，否则会再次出现重复规划、重复下载、状态覆盖和无法定位耗时的问题。

## 3. 模块总览

| 模块 | 核心代码是否可独立测试 | 真实运行还依赖什么 | v0.2 整理结果 |
|---|---|---|---|
| `observability-e2e` | 是 | adb、SSH、三端日志 | 统一事件名、阶段名和耗时指标 |
| `device-runtime` | 是 | Flutter storage/HTTP、RK health API | 旧地址迁移显式化，换设备清理 session |
| `library-catalog` | 是 | SQLAlchemy、Jetson API、Flutter adapter | Repository port 和严格 manifest |
| `audio-preprocess` | 是 | librosa/Essentia、数据库、真实歌曲 | AnalysisRepository 和处理服务分离 |
| `stem-separation` | 是 | Demucs、模型缓存、GPU、音频文件 | runner 注入、CLI、验证后原子发布 |
| `sequence-planner` | 是 | 真实曲库分析数据 | preset resolver 与旧 preset 兼容观测 |
| `transition-planner` | 是 | 完整候选数据、真实曲库 | 四模式统一通过严格 facade 调用 |
| `transition-renderer` | 是 | numpy/librosa/soundfile、真实音频 | renderer 版本成为显式 policy |
| `asset-sync` | 是 | RK 文件系统、HTTP、弱热点 | cache/校验/原子发布核心已被 worker 调用 |
| `transition-orchestrator` | 是 | edge-agent HTTP、sync 和 audio adapter | typed state 与幂等 accept/reuse |
| `audio-runtime` | 是 | RK 声卡、sounddevice、Unix socket | default-render 命令统一严格校验 |
| `mobile-dj-control` | 是 | Flutter UI、HTTP、timer、storage | 三种切歌共享任务生命周期，无全局锁 |
| `physical-input` | 是 | evdev、HID、amixer、edge-agent | 按键领域规则和 socket 协议分离 |

“核心可独立测试”不等于“克隆后无需环境即可完成生产功能”。例如分轨模块的 runner 和发布逻辑可独立测试，但真实分轨仍必须安装 Demucs 并准备模型及 GPU 环境。

## 4. 逐模块交接

### 4.1 `observability-e2e`

产品功能：跨手机、Jetson、RK 收集同一次操作，计算规划、渲染、同步、prepare、schedule 和执行耗时。

输入：部署目录、Android UIAutomator XML、三端日志。
输出：脱敏 inventory、标准 operation trace、验收报告。
核心边界：只观察和报告，不改变生产状态。
v0.2：新增标准 source/stage 名称和自动耗时指标，schema 升级到 v2。
仍需：让手机、Jetson、RK 全部输出同一个 `operation_id`，完成真实日志采集 adapter。

### 4.2 `device-runtime`

产品功能：保存 RK 设备身份和地址、探测连接、解析播放状态、在断网和换 IP 后恢复。

输入：配对/发现得到的 endpoint、`/health`、`/state`、操作意图。
输出：连接 profile、typed playback state、短期 operation reference。
核心边界：不负责规划和播放。
v0.2：旧 IP 导入只允许走显式 migration；设备身份变化时清理旧 session；引入 `SessionBinding`。
仍需：Flutter SharedPreferences/HTTP adapter、手机热点 IP 变化和真实重连测试。

### 4.3 `library-catalog`

产品功能：统一曲库、歌单和资源 manifest，解决 LibrarySong UUID 与 Catalog Song 整数 ID 混用。

输入：歌曲记录、歌单行、资源 manifest。
输出：索引后的 catalog、解析成 LibrarySong UUID 的歌单、严格校验的 RK manifest。
核心边界：不分析音频，不选切点。
v0.2：引入 `CatalogRepository` port 和 `CatalogService`，manifest 缺字段时明确拒绝。
仍需：SQLAlchemy、HTTP、Flutter adapter 接入真实数据库回归。

### 4.4 `audio-preprocess`

产品功能：离线计算 beat/downbeat、phrase、energy、stem 特征和 Track1/Track2 候选切点。

输入：原始音频及已持久化节拍、段落、能量、音色数据。
输出：带版本的分析 payload、`dj_structure_v2` 候选和覆盖率报告。
核心边界：播放时只消费结果，不在实时链路重新扫描整首歌。
v0.2：算法与持久化分开，数据库只通过 `AnalysisRepository` port 使用。
仍需：全曲库真实歌曲回归、Jetson 数据库写入、候选分布和失败重跑测试。

### 4.5 `stem-separation`

产品功能：把歌曲离线分为 `vocals.wav`、`drums.wav`、`bass.wav`、`other.wav`，并计算 stem 活跃度。

输入：原始音频路径、可选已有 stem。
输出：四个经过完整性检查的 stem 及分析元数据。
核心边界：不在 RK 实时分轨，不负责实时 stem 混音。
v0.2：Demucs process runner 可注入；提供独立 CLI；输出验证成功后再原子发布。
仍需：Jetson 的真实 Demucs/htdemucs、CUDA/GPU、长歌曲、磁盘不足和中断恢复验收。

独立调用示例：

```powershell
python -m harbeat_stem_separation AUDIO_PATH OUTPUT_ROOT
```

### 4.6 `sequence-planner`

产品功能：根据 BPM、调性、能量和兼容性生成自动播放顺序及能量曲线。

输入：预计算后的歌曲特征。
输出：歌曲顺序、每个槽位目标/实际能量、pair 兼容评分。
核心边界：只选顺序，不决定精确切出/接入秒数。
v0.2：当前 preset 和历史 preset 由 resolver 显式解析，兼容命中可观测。
仍需：真实曲库重复执行确定性测试，以及生产旧 preset 请求回放。

### 4.7 `transition-planner`

产品功能：对已确定的两首歌，规划自动接歌、快切、能量切歌和风格切歌的精确选点及对齐。

输入：两首已分析歌曲、当前播放 cursor、快切窗口、可选模式约束。
输出：renderer-neutral plan，包含 exit、entry、duration、pair identity 和评分依据。
核心边界：不选择资源 URL，不生成 WAV，不控制 RK。
v0.2：四种模式进入严格 `TransitionPlanningService` facade；数据不足和未知模式明确失败。
仍保留：约 5600 行行为兼容算法仍在内部，尚未拆成候选、评分、约束和对齐四个纯子域。这是有意保留，不是已完成的最终重写。
仍需：真实曲库 A/B 听感、候选评分回归、`relative_jump`、人声冲突、局部最优和耗时测试。

### 4.8 `transition-renderer`

产品功能：根据 plan 和两首歌曲，生成 RK 实际播放的 `transition_render.wav` 与 meta。

输入：已验证计划、原始音频/stem、renderer policy。
输出：render WAV、meta、resume 点和质量指标。
核心边界：不选歌曲和切点，不下载到 RK。
v0.2：v7/v9 版本选择变为显式 policy，未知版本立即拒绝。
仍保留：v7/v9 的 DSP 流程尚未完全合并，避免在没有真实音频 parity 时改变听感。
仍需：真实 WAV 波形、响度、峰值、relative jump、resume、处理耗时和人工听感对比。

### 4.9 `asset-sync`

产品功能：将歌曲或当前 transition pair 下载到 RK，校验后写入缓存。

输入：manifest、URL、格式、大小、可选 SHA256、priority/wait。
输出：通过校验的本地文件和逐文件耗时。
核心边界：不规划、不渲染、不 schedule。
v0.2：asset spec、cache validation、atomic publication 抽为纯核心，并由现有 sync worker 实际调用。
仍保留：弱热点需要的重试和 curl transport fallback；在 v1.0 前需配置化且可观测。
仍需：真实 RK、断网、慢网、并发请求、磁盘不足、进程重启和缓存损坏测试。

### 4.10 `transition-orchestrator`

产品功能：在用户确认切歌后管理 plan 校验、资源同步、prepare、schedule、完成和失败状态。

输入：transition plan、pair manifest、RK 播放状态和 monotonic clock。
输出：priority sync 请求、任务状态、deadline 和错误元数据。
核心边界：不执行网络、文件下载和音频播放，只描述合法操作。
v0.2：状态改为 typed state；`accept_or_reuse` 对同一 operation 幂等复用，不使用手机全局锁。
仍需：接入 edge-agent adapter，验证重复点击、超时响应、进程重启、旧 operation 恢复。

### 4.11 `audio-runtime`

产品功能：RK 上解码歌曲、维护双 deck、按 sample clock 到点播放 render，并在结束后从目标歌 resume。

输入：缓存歌曲、render WAV/meta、已验证 plan、Unix socket command。
输出：真实 PCM、prepared/scheduled/transition/resume 状态和触发误差。
核心边界：不规划、不渲染、不下载资源。
v0.2：default-render 命令由统一 contract 校验；硬件 engine 改为惰性导入，使契约测试不要求声卡。
仍保留：实时 callback 和 engine 状态暂未重写，防止在无 RK parity 时引入静音、卡顿或时钟误差。
仍需：真实 RK 声卡、连续切换、触发误差 `<=100ms`、无静音、进程重启和 systemd 验收。

### 4.12 `mobile-dj-control`

产品功能：表达快切意图，预览并确认能量/风格目标，解析任务状态并恢复未完成操作。

输入：目标歌、plan、pair manifest、RK task/state。
输出：三种手动切歌共用的 orchestration request、typed task、pending operation。
核心边界：不渲染、不下载、不 schedule，不持有 Flutter widget 或 HTTP client。
v0.2：建立显式任务生命周期、合法状态和 TTL；三种切歌共用请求构造；不再用全局点击锁表达后端状态。
仍需：Flutter UI、HTTP、timer 和 storage adapter，验证进度条不卡顿、重复点击和失败恢复。

### 4.13 `physical-input`

产品功能：把实体按键和旋钮映射为 SFX、暂停、导航事件或音量动作。

输入：逻辑键 0-9、音量动作、按压时间和 HID source。
输出：audio socket 命令、edge-agent `key_event` 或本地音量调整。
核心边界：不选歌、不规划转场、不控制手机 UI。
v0.2：不可变按键规则在 `domain.py`；socket wire format 在 `protocol.py`；旧 `routing.py` 只保留显式兼容 facade。
仍需：真实 MYKB E9s、按键 7-9 的移动端消费逻辑及每动作 20/20 验收。

## 5. Git 交付结构

每个模块都有三条回溯路径：

```text
module/<name>/v0.1.0          原始行为基线
module/<name>-clean-v0.2      后续 clean 开发分支
module/<name>/v0.2.0          当前 clean 不可变版本
```

统一版本：

```text
functional-modules/v0.1.0     13 模块基础第一版
functional-modules/v0.2.0     13 模块干净边界版
```

开发某一模块时，从对应模块 `v0.2.0` 标签建立新分支；不要从主生产脏工作区复制代码，也不要在一个提交里同时修改多个模块。

推荐命名：

```text
module/<name>-clean-v0.3
module/<name>/v0.3.0
```

每次提交必须只包含：模块源码、模块测试、`MODULE.yaml`、模块 README 和必要 contract。禁止批量 `git add .`。

## 6. 测试和复现

统一运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/test_functional_modules.ps1
```

`v0.2.0` 结果：

| 模块 | 测试数 |
|---|---:|
| observability-e2e | 9 |
| device-runtime | 22 |
| library-catalog | 12 |
| audio-preprocess | 10 |
| stem-separation | 9 |
| sequence-planner | 7 |
| transition-planner | 7 |
| transition-renderer | 6 |
| asset-sync | 9 |
| transition-orchestrator | 7 |
| audio-runtime | 25 |
| mobile-dj-control | 11 |
| physical-input | 12 |
| **总计** | **146** |

当前测试覆盖核心领域规则、契约、错误拒绝和 adapter 边界。它不覆盖真实 GPU、数据库、热点、声卡、Android UI 和 systemd，因此不能替代设备验收。

## 7. 是否还有层层叠叠的补丁

结论分两层：

- 模块外部边界已经明显收敛：调用者可以通过 service/facade/contract 使用，设备和网络依赖不再混进核心测试。
- 模块内部仍有受控兼容实现：主要集中在 `transition-planner` 的大体量算法、`transition-renderer` 的 v7/v9 DSP、`audio-runtime` 的实时 callback、`asset-sync` 的网络重试。

这些兼容实现没有在 v0.2 中强删，因为它们直接影响听感、实时播放或弱热点稳定性。当前做法是把它们标记为显式 policy/adapter，并用 `v0.1.0` 锁定回归基线。下一阶段要逐块替换，不能继续在原函数上叠加匿名 fallback。

## 8. 下一阶段执行顺序

### 阶段 A：模块内部最终整理

1. `transition-planner`：拆出 candidates、constraints、scoring、alignment 和四模式 policy；用真实曲库保持计划结果或记录有意变化。
2. `transition-renderer`：建立共享 DSP pipeline；v7/v9 只保留 policy 差异；进行真实 WAV parity。
3. `audio-runtime`：先固定状态机和 sample clock characterization，再拆 deck/output adapter；禁止直接重写 callback。
4. `asset-sync`：transport policy 配置化，补断点、取消、缓存损坏和磁盘错误。
5. 其余模块：补齐真实环境 adapter，不改变已冻结领域 contract。

### 阶段 B：影子接入

按依赖从下到上：

```text
physical-input / device-runtime
-> library-catalog / audio-preprocess / stem-separation
-> sequence-planner
-> transition-planner / transition-renderer
-> asset-sync / transition-orchestrator / audio-runtime
-> mobile-dj-control
-> observability-e2e 全链路验收
```

影子期同时运行旧实现和 clean 实现，只比较结果，不让 clean 输出控制真实播放。对比通过后一次只切换一个 adapter，并保留配置开关回滚。

### 阶段 C：真实三端验收

至少满足：

- 自动接歌、快切、能量切歌、风格切歌分别连续 5/5 成功。
- 快切点击到 ready `<=12s`，进入衔接 `<=15s`，触发误差 `<=100ms`。
- UI 正常播放和切歌期间进度连续，不出现数秒停顿或大跳。
- 切歌失败不破坏后续自动接歌。
- 重复点击、超时响应、热点抖动、进程重启和缓存缺失能够恢复。
- 分轨对真实歌曲生成四个有效 stem。
- 实体动作分别达到 20/20。
- 同一操作可用 `operation_id` 跨三端完整追踪。

### 阶段 D：发布 `v1.0.0`

只有上述验收、fresh clone、空 release 目录重建和回滚演练全部通过，才能发布 `functional-modules/v1.0.0`。此时再依据静态引用、运行日志、数据和配置四类证据归档旧生产代码。

## 9. 开发红线

- 不直接清理主工作区中的未提交生产改动。
- 不删除 `v0.1.0` 标签或重写其历史。
- 不把测试替身通过描述成真实设备通过。
- 不在 UI 中重新实现后端任务状态机。
- 不在 planner 中下载资源，不在 sync 中重新规划，不在 runtime 中 fallback 到未知 render。
- 不将凭据、热点密码、SSH 密码、歌曲或模型缓存提交到 GitHub。
- 不同时替换 Jetson、RK 和手机三个生产端。

## 10. 接手开发人员的第一天操作

```powershell
git clone https://github.com/jihaobi123/harbeat-client.git
cd harbeat-client
git checkout functional-modules/v0.2.0
powershell -ExecutionPolicy Bypass -File scripts/test_functional_modules.ps1
```

确认 13 条命令全部通过后，选择一个模块，从其 `module/<name>/v0.2.0` 标签建立工作分支。先阅读该模块的 `MODULE.yaml`、README 和测试，再修改。任何生产接入必须另建 integration 提交，并附真实设备报告和回滚步骤。
