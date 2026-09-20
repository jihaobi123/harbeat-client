# 音乐分析工作台验证记录

日期：2026-09-18。实测环境：当前 Mac；可选模型运行在隔离 Linux x86_64 容器中。

| 音频 | 时长（秒） | 原分析保留 | 粗糙度 | 重复分组 |
| --- | ---: | --- | --- | --- |
| 100.wav | 181.03 | 完整 | ready | ready |
| 101.wav | 25.52 | 完整 | ready | ready |
| 102.wav | 245.76 | 完整 | ready | ready |
| 103.wav | 2291.54 | 完整 | ready | ready |
| 106.wav | 203.81 | 完整 | ready | ready |
| 107.wav | 201.57 | 完整 | ready | ready |
| 108.wav | 298.94 | 完整 | ready | ready |

101.wav 另外跑通了情绪和乐器模型：17 个情绪时间点，乐器输出 drums / bass / electricguitar / guitar。标签是模型估计，尚无人工验证。

模型报告 ID：`5ce495e3f1b6a9740039c534356cb356a4c58182730c818d606f6dfe31bff500`。模型文件、参数、耗时与哈希见对应完整报告。

103.wav 是 2291.54 秒专场，已有段落只到 420 秒。平台提示来源覆盖不足；没有补造后续段落。早期触发 30 分钟限制的失败报告也保留在历史中，调整为 2 小时后重跑成功。

验证内容：原始 JSON 逐首深比较；秒/毫秒时间轴、缺失值、同曲身份校验；失败隔离、重启中断记录、模型索引、静音与增益行为；原曲库登录及所有权；转发密钥与来源限制；实际容器超时清理；网页段落定位到 15.047 秒及同曲版本对照。

自动测试：22 项 Python 测试、57 项前端测试通过；前端类型检查和生产构建通过。

远端部署已完成：独立 Jetson ARM CPU 模型环境、NAS 存储及阿里云 HTTPS 登录入口均已验证。101.wav 的 ARM 情绪输出与原 x86 Essentia 实现最大差 3.815e-6，乐器标签一致、分数最大差 1.2e-7。106.wav（203.808 秒）四模块全部 ready，总耗时约 128 秒；原始 documents 和 source_hashes 与本地报告完全一致。浏览器验证了执行机器 jetson、任务完成状态、四模块耗时、情绪曲线和标签。

无登录访问页面、接口、静态文件为 401，跨源写入为 403；现有 /health 和 /jetson/health 均为 200。完整记录见 ../deploy/analysis-platform/DEPLOYED.md，机器可读任务记录见 ../outputs/jetson-full-track-validation.json。

尚未完成：真实人工标注与转场盲听实验、原混音引擎每次转场的全链路日志接入。没有证据判定补充算法比原算法更准确。

## Complete-source integration, 2026-09-18

- Read-only production snapshot: 43 library rows; published NAS imports: 163. No source DB/audio/model changes. Source import errors: 0.
- Audio registration audit: 206 masters, 205 sets of vocals/drums/bass/other, 163 sets of five drum sub-stems; 163 vocal activity documents and 10 each SongFormer/EDM structure/instrument sidecars.
- Public authenticated HTTP checks: page 200; six master/stem requests with `Range: bytes=0-1023` returned 206 and 1024 bytes; unauthenticated reports returned 401; original gateway and Jetson health checks returned 200.
- Browser checks: supplied logo visible, Big Poppa shows four real stem curves (125 windows each), vocal selection changes the player, all-dimensions view exposes 5,939 source fields for that report, LOVE ME RIGHT exposes original + four stems + five drum sub-stems.
- Added regressions: path/symlink boundary, stale media identity, missing stems remain unknown, opposite-polarity stereo retains energy, NAS raw fields preserved, wrong/missing sidecar fingerprints cannot become active source identities, uploaded audio retains stem associations, protected media Range, old report migration when a worker writes before first list.
- Stem curves are measurements of the actual separated audio, not ground-truth voice or instrument presence. Catalog batch completion is tracked separately from deployment; consult `/api/analysis-lab/catalog` rather than inferring all curves are finished from source import count.

Final checks: 31 focused backend tests passed; 7 analysis frontend tests passed after the label update; TypeScript and production build passed. The 51 unrelated frontend tests passed in the full run.

Public single-track stem job also completed: LOVE ME RIGHT, 103 measurement windows, all 10 audio associations retained, every original source hash unchanged (outputs/jetson-stem-job-validation.json). Independent platform memory at the final check was about 199 MiB and the original API service remained active.

## Structure display correction, 2026-09-18 evening

Audit confirmed the main timeline had rendered only the primary `phrase_map`, even when verified SongFormer and EDM sidecars existed. Production library heuristic groups eight bars, applies energy/position rules and returns whole-track intro when downbeats are insufficient. Library primary outputs across 43 records: intro 74, buildup 2, drop 333, outro 28, verse 43, breakdown 1. Published NAS outputs additionally contain chorus, pre-chorus, bridge, inst and silence. These label families have different semantics.

Added a source-specific structure panel without rewriting primary documents, replacing algorithms or renaming their raw labels. Ready SongFormer, published NAS structure, EDM candidates and old phrase rules are separately shown with Chinese legends and coverage warnings. Failed/unverified sidecars are not promoted. Three source-selection/rendering regressions pass; analysis frontend total 10 tests and production build pass. Public HTML and JS were verified after deployment.

## 2026-09-19 同步分轨试听

根因：AnalysisLab 用 `key={audioUrl}` 重建单个 `<audio preload="metadata">`，每次分轨选择都会重新打开远程文件，并且恢复进度后需要再次播放。替换为独立 SyncedStemPlayer / StemTransport：原曲轻量试听保留，用户准备或首次选择分轨时缓存、解码原曲与可用四轨；所有已准备音轨用同一个 AudioContext 时间与偏移启动，选择只做 20 ms GainNode 交叉渐变。原曲与四轨合听互斥，细分鼓组可提前准备，或首次选择时准备并加入共同时间线。

验证：20 项分析前端测试通过，其中 10 项覆盖共同时钟、选择不重复取文件／不重启节点、定位与恢复、快速连续定位、追加音轨、失败重试、内存保护、切歌取消，以及浏览器 fetch 绑定回归。类型检查与生产构建通过。实际浏览器 OfflineAudioContext 验证原曲／鼓独听／四轨合听三种输出：首个非零帧均为 1440（48 kHz 下统一预定 30 ms），输出分别约 0.500015、0.199988、0.374981，与预期 0.5／0.2／0.375 一致（16-bit PCM 量化误差范围）。每次五个文件请求，独听没有混入其他声源。

实际 NAS 曲目 DSK（74.266 秒，44.1 kHz）经受保护公网媒体接口读取，原曲与四轨准备完成，连续切换鼓、人声、贝斯、四轨合听期间保持播放状态和递增进度；段落定位后底鼓独听也保持播放。细分鼓组在后台准备，其已完成音轨可直接选择。没有据此声称主观盲听评价或全设备延迟实测。

限制：首次仍需完整传输并解码，慢链路的首次准备可能较长；缓存仅保留当前歌曲页面生命周期。四轨与原曲按来源零点对齐，不修复源文件本身的偏移。解码 PCM 限额 768 MiB、每轨请求 180 秒超时；长音轨／大量鼓组超限时明确报错并保留已有轨道和原曲试听。后续若需长专场边传边播，应采用按块预缓冲的音频工作线程，而非无限增加全曲内存。

## 2026-09-19 风格整合验证

- 后端分析平台相关测试 43 项通过；前端分析测试 21 项通过；TypeScript 和正式构建通过。
- 新增测试覆盖原始分数保留、有效特征帧加权、大类最大值、异常模型形状／数值、缓存损坏与身份变化、不同来源隔离、人工版本冲突、音频绑定迁移、防止再次改绑另一段音频、指纹不匹配时拒绝推理、单模块运行保留其他结果、目录同步继承兼容结果。
- 独立代码复核发现的来源归属、逗号标签、旧报告重复统计、音频核验和标注身份问题均已修复并加入回归检查。
- 浏览器实测：400 类列表可搜索；原规则、舞种、人工标签并列；带逗号的类名与多行标签可完整保存，刷新后保留；原人工标签不变。写入测试在本地隔离数据中完成，未给真实曲目伪造人工确认。见 `outputs/style-ui-validation.json`。
- 公网页面与 JS/CSS 字节和本地构建一致；未认证访问风格接口返回 401；执行机器为 jetson。见 `outputs/style-deployment-validation.json`。
- 《Shook Ones, Pt. II》先运行风格再运行乐器：全部 11 / 11 窗口复用 EffNet 缓存，风格结果与原始来源哈希完全保持。见 `outputs/style-instrument-cache-validation.json`。
- 一段约 54.9 分钟的连续混音从单曲对照样本中排除，任务主动中断，已生成缓存保留。见 `outputs/style-cohort-exclusions.json`。不将该中断当作模型准确性证据。
- 完成 8 首完整单曲样本，全部风格模块 ready，每首保留 400 个原始分数，8 / 8 原始来源哈希及其他扩展保持不变，实际模型音频 SHA 与报告一致。最终对照覆盖 208 首正式来源：规则 22、原人工 23、舞种评分 2、模型完成 8。
- 8 首中仅 4 首具有可映射的原人工标签：首选一致 1 / 4，前五候选覆盖 3 / 4。Breaking 标签未强制映射，其余 3 首未标注。不把这些小样本的一致数解释为准确率；《In the Summertime》的旧 jazz 标签与模型候选不一致，保留待人工复核。见 `outputs/style-library-comparison.json`。
- 最终检查生产 `harbeat-api.service` 仍 active，启动时间为 2026-09-18 18:19:18 CST；本次未重启生产主服务。独立 Lab 任务队列已空。
