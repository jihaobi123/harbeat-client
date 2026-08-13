# HarBeat 13 个功能模块 v0.1.0 开发交接手册

日期：2026-08-13

目标读者：后端、音频算法、RK 边缘端、Flutter、测试与运维开发人员

基线标签：`functional-modules/v0.1.0`

## 1. 交付结论

当前 13 个模块构成 HarBeat 新架构的**基础第一版**。这一版完成了：

- 从现有手机、Jetson、RK 代码中按真实产品功能划分模块；
- 每个模块拥有独立目录、说明、清单、测试、来源证明、分支和标签；
- 模块可以在 fresh clone 后独立运行核心测试；
- 统一分支同时包含全部 13 个模块，可用于联调和后续重构；
- 原生产代码、设备环境、数据库、歌曲、模型和缓存未被替换或删除。

`v0.1.0` 的定位是**可回溯的行为基线**，不是最终干净代码，也不是已经上线的新架构。任何后续重构都必须保留该标签，使用行为对比证明没有丢失功能。

## 2. GitHub 交付结构

### 2.1 完整基线

```text
repository: https://github.com/jihaobi123/harbeat-client.git
branch:     delivery/functional-module-extraction-20260813
tag:        functional-modules/v0.1.0
path:       modules/
```

完整拉取：

```powershell
git clone https://github.com/jihaobi123/harbeat-client.git
cd harbeat-client
git checkout functional-modules/v0.1.0
powershell -ExecutionPolicy Bypass -File scripts/test_functional_modules.ps1
```

### 2.2 单模块版本

每个模块同时具有：

```text
branch: module/<module-name>
tag:    module/<module-name>/v0.1.0
```

标签是不可变回滚点。模块分支可以继续产生提交，但不得移动或覆盖 `v0.1.0` 标签。

### 2.3 目录约定

```text
modules/<module-name>/
  MODULE.yaml       输入、输出、依赖、接口、来源和部署边界
  README.md         模块行为与测试方式
  src/ or lib/      核心实现
  contracts/        可序列化契约或 JSON Schema（适用时）
  tests/            不依赖生产设备的模块测试
  deploy/           来源证明、兼容报告或部署资料
```

歌曲、stem、WAV、数据库、模型权重、密钥、设备配置和缓存属于外部部署资产，不进入 Git。

## 3. 系统边界

| 运行端 | 应负责 | 不应负责 |
|---|---|---|
| 手机 | 用户意图、界面、设备连接、展示统一任务状态 | 音频分析、render、资源同步和多轮后台编排 |
| Jetson | 曲库、离线分析、分轨、排歌、选点、转场渲染 | RK 本地播放时钟和设备音频输出 |
| RK edge-agent | 接收幂等操作、同步资源、prepare/schedule、任务状态 | 重新选歌、重新分析或生成转场 WAV |
| RK audio-engine | 精确播放、双 Deck、采样时钟触发和目标歌续播 | HTTP、下载、曲库和业务选歌 |

## 4. 模块详细说明

### 4.1 `observability-e2e`

- 产品功能：三端测试、日志采集、故障定位和验收报告。
- 调用时机：部署前后、复现超时/409/错误切歌、执行真实手机 E2E 时。
- 输入：文件元数据、UIAutomator XML、手机/Jetson/RK 日志。
- 输出：脱敏资产清单、统一 operation timeline、验收 JSON。
- 外部依赖：真实测试需要 `adb`、SSH 和三端可达。
- 边界：只观察，不选歌、不渲染、不下载、不播放。
- 当前技术债：仍需替代部分历史测试脚本，并统一 operation_id 日志字段。

### 4.2 `device-runtime`

- 产品功能：手机连接 RK、设备身份确认、断线恢复、状态读取。
- 调用时机：App 配对、启动、热点地址变化、请求超时后恢复时。
- 输入：RK endpoint、`/health`、`/state` 和用户操作引用。
- 输出：稳定 `device_id`、连接会话、播放状态和错误分类。
- 边界：IP 是地址而不是设备身份；不保存完整 render plan。
- 当前技术债：生产 Flutter adapter 尚未接入；保留旧地址迁移逻辑。

### 4.3 `library-catalog`

- 产品功能：曲库、歌单、歌曲 ID 映射、RK 资源 manifest。
- 调用时机：导入歌曲、浏览曲库、生成队列、准备资源同步时。
- 输入：LibrarySong UUID、Catalog Song ID、playlist rows 和资源描述。
- 输出：已解析曲库快照、歌单歌曲 UUID、经过校验的 manifest。
- 关键规则：播放和 RK 缓存只使用 LibrarySong UUID，不按歌名匹配。
- 当前技术债：需要带真实用户会话完成生产 API replay。

### 4.4 `audio-preprocess`

- 产品功能：歌曲 BPM、beat/bar/phrase、能量和 v2 转场候选预处理。
- 调用时机：歌曲进入曲库后离线执行，不在实时切歌请求中扫描音频。
- 输入：原音频及已有 beat/downbeat/phrase/energy 数据。
- 输出：`dj_structure_v2`、Track1 切出候选、Track2 接入候选和质量报告。
- 外部依赖：Jetson Python 3.10、NumPy、librosa、Essentia 和本地音频。
- 当前技术债：部分异常处理较宽；需要把完整分析 pipeline 进一步接口化。

### 4.5 `stem-separation`

- 产品功能：人声、鼓、贝斯、其他四轨离线分离。
- 调用时机：歌曲预处理阶段或用户明确请求重新分轨时。
- 输入：原音频路径和可选的已有 stem 路径。
- 输出：`vocals.wav`、`drums.wav`、`bass.wav`、`other.wav` 及完整性元数据。
- 外部依赖：Demucs、`htdemucs` 模型缓存、NumPy、SoundFile、FFmpeg。
- 边界：四轨不完整即失败；不能将部分结果标记为成功。
- 当前技术债：核心代码相对干净；需补独立 CLI、依赖锁和容器化运行入口。

### 4.6 `sequence-planner`

- 产品功能：自动排歌、BPM/调性兼容排序和整套能量曲线。
- 调用时机：开始自动播放或用户重新生成播放顺序时。
- 输入：已预计算的歌曲 BPM、key、Camelot、能量和频段摘要。
- 输出：歌曲 ID 顺序、目标/实际能量和配对评分。
- 边界：只排序，不选转场点、不 render、不调用 RK。
- 当前技术债：仍保留旧 preset 兼容，需要版本化 preset schema。

### 4.7 `transition-planner`

- 产品功能：自动接歌、快切、能量切歌、风格切歌的选点与对齐。
- 调用时机：上下两首歌已确定后、生成衔接 WAV 前。
- 输入：两首已分析歌曲、当前播放位置、执行窗口和可选目标约束。
- 输出：Track1 exit、Track2 entry、时长、对齐与候选评分 plan。
- 边界：不选下一首歌、不生成 WAV、不下载、不调用 RK。
- 当前技术债：这是最高风险模块；包含 v1/v2、四种入口、兼容桥和多级 fallback，需要拆成候选、评分、约束、对齐和模式策略五层。

### 4.8 `transition-renderer`

- 产品功能：生成用户实际听到的转场 WAV 和 metadata。
- 调用时机：planner 输出确定后、RK 同步前。
- 输入：两首本地音频和 renderer-neutral transition plan。
- 输出：`transition_render.wav`、metadata、版本、连续性和缓存状态。
- 外部依赖：NumPy、librosa、SoundFile、SciPy 和本地音频。
- 当前技术债：快切 v7 与自动接歌 v9 并行，需要抽共享 DSP pipeline，并保留明确 renderer policy。

### 4.9 `asset-sync`

- 产品功能：RK 下载、校验、缓存和原子发布歌曲及转场包。
- 调用时机：manifest 中的目标资源尚未在 RK 缓存时。
- 输入：资源 URL、格式、大小、SHA256、优先级和等待参数。
- 输出：本地缓存、同步状态、单文件耗时和错误。
- 边界：不选歌、不 render、不 prepare/schedule。
- 当前技术债：保留旧缓存兼容和 httpx 到 curl 的 transport fallback；最终版应把 transport 作为显式 adapter。

### 4.10 `transition-orchestrator`

- 产品功能：串联同步、缓存就绪、prepare、schedule 和任务状态。
- 调用时机：用户确认切歌后到 RK 接受定时执行之间。
- 输入：plan、pair manifest、当前播放/时钟状态。
- 输出：幂等任务、priority sync 请求、deadline 和状态迁移。
- 边界：不选点、不 render、不直接读写音频设备。
- 当前技术债：核心较干净；需要与 edge-agent HTTP/persistence adapter 正式组合。

### 4.11 `audio-runtime`

- 产品功能：RK 真正发声、双 Deck、转场 prepare/schedule、到点切换和续播。
- 调用时机：整个播放过程，尤其是已缓存转场的实际执行阶段。
- 输入：原歌曲、转场 WAV/meta 和已验证 plan。
- 输出：PCM、prepared/scheduled/transition/resume 状态和触发误差。
- 外部依赖：NumPy、SoundFile、SoundDevice、RK 音频设备和缓存。
- 当前技术债：代码规模大，混合了 engine、调度、协议和硬件 fallback；最终版要先拆纯状态机与设备 adapter，不能直接重写实时音频循环。

### 4.12 `mobile-dj-control`

- 产品功能：手机快切、能量/风格预览确认、pending task 恢复和播放确认。
- 调用时机：用户点击三个切歌入口和 App 恢复待执行任务时。
- 输入：目标歌曲、plan/manifest、RK task 和播放状态。
- 输出：共享手动切歌请求、typed task 和执行确认。
- 关键规则：能量/风格 preview 只选目标歌；确认后与快切复用同一执行链路。
- 当前技术债：核心 Dart 模块较干净，但 Flutter 页面、网络、轮询和持久化 adapter 尚未迁出生产页面。

### 4.13 `physical-input`

- 产品功能：三个实体模块、九键 SFX/导航、暂停和音量旋钮。
- 调用时机：用户操作实体按键或旋钮时。
- 输入：逻辑键 0-9、音量动作和 HID 来源。
- 输出：audio trigger、key_event 或本地音量调整。
- 边界：不选歌、不规划转场、不直接操作手机 UI。
- 当前技术债：核心映射较干净；键 7-9 尚无完整手机业务消费者。

## 5. 产品调用链

### 5.1 曲库导入与预处理

```text
library-catalog 接收歌曲身份
  -> stem-separation 生成四轨（可选但首版需要）
  -> audio-preprocess 生成分析和 v2 候选
  -> library-catalog 发布版本化资源与分析状态
  -> sequence-planner 使用持久化摘要排歌
```

### 5.2 正常自动接歌

```text
sequence-planner 确定下一首
  -> transition-planner(default)
  -> transition-renderer(v9)
  -> asset-sync
  -> transition-orchestrator
  -> audio-runtime 到点执行
```

### 5.3 快切

```text
mobile-dj-control(fast，目标为队列下一首)
  -> transition-planner(fast，当前播放位置后的实时窗口)
  -> transition-renderer(v7)
  -> asset-sync(只同步 pair WAV/meta)
  -> transition-orchestrator
  -> audio-runtime
```

### 5.4 能量与风格切歌

```text
preview 只选择目标歌曲
  -> 用户确认
  -> mobile-dj-control(目标为已选择歌曲)
  -> 与快切共享 planner/render/sync/orchestrator/audio-runtime
```

## 6. 开发与测试

### 6.1 最低工具要求

- Git；
- Python 3.10 或兼容版本；
- `pytest`；
- Dart 3.7 或兼容版本；
- 音频模块完整测试另需 NumPy、librosa、SciPy、SoundFile；
- 真实分轨另需 Demucs、FFmpeg 和 `htdemucs` 模型；
- 真实 RK 播放另需 SoundDevice 和 RK 音频设备。

统一模块测试使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test_functional_modules.ps1
```

脚本只运行模块测试，不连接生产设备、不修改数据库、不播放真实音频。

### 6.2 单模块工作流程

```text
1. 从 module/<name> 创建 module/<name>-clean-v0.2 工作分支
2. 运行 v0.1.0 测试并保存结果
3. 补 characterization tests，锁定当前输入输出
4. 一次只移除一类兼容/重复逻辑
5. 运行单元、契约、行为对比测试
6. 由 adapter 在影子环境双跑，不切生产流量
7. 通过真实 E2E 和回滚演练
8. 发布 module/<name>/v0.2.0
```

禁止在整理代码时顺便改变算法权重、切歌窗口、缓存协议或 UI 行为。行为变化必须作为独立版本和独立评审处理。

## 7. 生产接入原则

模块代码不能直接覆盖当前 Jetson/RK 工作目录。推荐 release 结构：

```text
/opt/harbeat/releases/<release-id>/
/opt/harbeat/current -> /opt/harbeat/releases/<release-id>/
/opt/harbeat/shared/{audio,models,cache,db-config}
```

接入顺序：

1. Jetson 数据与纯逻辑：`library-catalog`、`audio-preprocess`、`sequence-planner`。
2. 转场计算：`transition-planner`、`transition-renderer`。
3. RK 下载和编排：`asset-sync`、`transition-orchestrator`。
4. RK 播放：`audio-runtime`。
5. 手机：`device-runtime`、`mobile-dj-control`。
6. 实体输入：`physical-input`。
7. 全程由 `observability-e2e` 收集证据。

每次只替换一个模块，通过后再进入下一个。旧 API 首先变成 adapter，不立即删除。

## 8. 验收与回滚

### 8.1 模块级门槛

- fresh clone 测试通过；
- 输入输出契约不变或有明确迁移版本；
- 不新增静默 fallback；
- 所有外部依赖有版本和健康检查；
- 可退回对应 `module/<name>/v0.1.0`。

### 8.2 产品级门槛

- 自动接歌、快切、能量确认和风格确认分别连续 5/5；
- 实体动作分别 20/20；
- 手动切歌 `scheduled <= 12s`、进入衔接 `<= 15s`；
- RK trigger error `<= 100ms`；
- 无静音、硬切、重复播放、错误目标和进度倒退；
- 一次操作至多一次 planning、render、sync、schedule；
- 断网、超时后已接受、设备重启、缓存缺失和重复点击均有确定恢复语义。

### 8.3 回滚

```powershell
git checkout functional-modules/v0.1.0
```

设备部署回滚必须切换 release 软链接并重启单一服务，不覆盖共享歌曲、模型、数据库或缓存。没有完成回滚演练的模块不能替换生产入口。

## 9. 当前明确不能删除的内容

- 当前生产 App、Jetson DJ control/library 代码；
- RK sync-worker、edge-agent、audio-engine、input-daemon；
- systemd unit、环境变量、数据库和模型；
- 歌曲、stem、render cache 与 manifest；
- 任何仍被 import graph、配置、systemd 或真实 E2E 调用的历史文件。

只有新模块完成影子双跑、生产验收和回滚证明后，旧文件才能进入归档候选；永久删除需要单独审批。

## 10. 开发人员接手检查表

- [ ] 确认当前 checkout 是总标签或目标模块标签。
- [ ] 阅读 `modules/REGISTRY.md` 与目标模块 `MODULE.yaml`。
- [ ] 确认模块边界和不负责的内容。
- [ ] 安装模块依赖，但不导入生产密钥或媒体到 Git。
- [ ] 在修改前运行全部现有测试。
- [ ] 为历史行为补 characterization test。
- [ ] 小步提交；一个提交只处理一种技术债。
- [ ] 不修改 `v0.1.0` 标签。
- [ ] 双跑结果、性能、E2E 和回滚证据随版本归档。
