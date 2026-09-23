# HarBeat 预处理与混音源码入口

这份整理把 Jetson 实际使用的完整预处理、分析平台、在线混音控制代码，以及已确认的 V3 离线算法放进同一个仓库。它们独立启动，通过分析文件和转场计划衔接。

## 从哪里看

| 内容 | 入口 | 运行位置与状态 |
| --- | --- | --- |
| 完整预处理 | [services/preprocessing](services/preprocessing/README.md) | 从 Jetson 的实际发布目录提取；Core、SongFormer、Demucs、MDX23C、鼓组、人声时间轴及 NAS 发布 |
| 补充分析与可视化 | [analysis_platform](analysis_platform/README.md)、[web/src/analysis](web/src/analysis) | Jetson 独立分析服务；阿里云转发；原始结果与补充结果分开记录 |
| 接歌输入、选点与计划 | [dj_contract.py](analysis_platform/dj_contract.py)、[dj_plan.py](analysis_platform/dj_plan.py) | 提供段落、拍网格、人声、响度和计划；人工未确认的边界保留待确认状态 |
| 在线混音控制与播放 | [mixing/ONLINE.md](mixing/ONLINE.md) | 整理现有会话、策略、自动化和 RK 音频引擎源码；未在本次整理中部署或重接 V3 |
| V3 浏览器实时试听 | [mixing/REALTIME_V3.md](mixing/REALTIME_V3.md) | 六首 Hip-Hop 原型；动态选点、现场 EQ/淡化与音频线程日志；尚未接原生 App |
| 已认可的 V3 算法 | [mixing/README.md](mixing/README.md) | 离线渲染。冻结同事的原算法，保留选歌、选点、EQ、变速和执行日志 |
| 数据合同 | [contracts](services/preprocessing/contracts)、[schemas/music_analysis](schemas/music_analysis) | 用版本、曲目 ID、运行 ID、音频 SHA256 绑定来源 |
| 部署 | [部署关系](docs/audio-stack/DEPLOYMENT.md)、[分析服务配置](deploy/analysis-platform) | 模型环境、服务和数据分别管理 |

## 为什么先放同一个仓库

预处理产出的字段会直接影响混音。段落边界的单位、拍网格版本、人声区间和变速映射一旦改变，需要同时检查计划、执行和页面。放在一个仓库，可以在一次提交里核对这些变化；同事也只需要取得一个版本。

同仓库不等于装进同一个 Python 环境。完整预处理、补充模型、分析平台和音频播放各有依赖及运行入口。尤其 Jetson 的 CUDA/PyTorch、ARM TensorFlow、和弦模型不能直接混装。

当预处理需要对外提供独立产品、两个团队需要不同仓库权限，或合同已经稳定且各自发布互不依赖时，再拆成两个仓库。目前先按目录隔离更省事，也便于复现。

## 新同事开始工作

1. 查看上表，确定修改的是预处理、计划还是执行。完整预处理以 `services/preprocessing` 为源码根；根目录 `app/` 保留已有 API/在线控制代码，两者不可混用导入路径。
2. 按对应 README 建立独立环境。分析平台可以先导入已有 JSON，不必立即安装全部模型。
3. 运行 [验证说明](docs/audio-stack/VALIDATION.md) 中的本地检查。
4. 音频、模型、NAS 报告和运行凭据从受控存储取得。GitHub 保存代码、合同、配置模板和测试，不保存曲库。

V3 的复现成功只说明还原了你认可的算法；段落识别和小节计数是否正确，仍需单独校验。页面试听已有音频与在线实时生成混音也是两件不同的事。

## 2026-09-22 局部风格与能量联合选点

[实现与运行方法](mixing/LOCAL_INTENTS.md) · [验证记录](mixing/LOCAL_INTENTS_VALIDATION_20260922.md) · [独立新版试听](https://8.136.120.255/analysis-lab-static/v3-live-20260922/index.html)。原始分析与 V3 DSP 保留；增加源文件绑定的段落／窗口档案、精确区间模型候选、统一功率尺度与接管后16秒持续性筛选。

## 2026-09-23 V3.1 保护版候选

[实现、曲库覆盖与验证说明](docs/V31_CANDIDATE.md) · [20 首可视化对照及实时试听](https://8.136.120.255/analysis-lab-static/v31-candidate-20260923/index.html)。沿用已试听保护策略与 V3 DSP，增加原曲选区、人声／段落时间轴、播放中触发与可导出的偏好反馈。本轮不启用能量或风格奖励；保留冻结 V3，是否正式升级等待扩大试听后的决定。
