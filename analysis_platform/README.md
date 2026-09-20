# HarBeat 音乐分析工作台

在原有分析旁边增加报告、时间轴、独立补充模块和同曲对照。原始 JSON 完整保存，派生结果单独记录；没有修改现有节拍、结构、调性、分轨或混音策略。

## 本机运行

使用 Python 3.10–3.12，独立安装，避免改变已有 GPU 环境：

```bash
python3 -m venv .venv-lab
.venv-lab/bin/pip install -r analysis_platform/requirements.txt
cd web
npm ci
npm run build
cd ..
scripts/start_analysis_platform
```

打开 http://127.0.0.1:8765/analysis-lab 。本次工作会话也支持已安装的 `/tmp/harbeat-analysis-runtime`；该临时环境可能被系统清理，长期使用请安装 `.venv-lab`。

1. 导入单首或批量分析 JSON。支持旧分析、NAS manifest、TrackAnalysis；额外 PANNs、人声、分轨结果可通过“添加来源”导入。
2. 选择与报告对应的原曲，点击“运行补充分析”；服务端已保存音频时，可直接重跑，避免经阿里云重复上传。支持解码器能读取的格式，上传不超过 1 GB、时长不超过 2 小时。
3. 查看原始时间轴、补充曲线、全部字段和模块运行状态。点击段落或曲线可定位试听。
4. 导出完整报告 JSON、原始字段 CSV。在“版本对照”中选择同曲报告；音频 SHA256 相同才显示已确认同曲。
5. “转场盲听”使用你选择的两个音频片段，随机隐藏来源，投票保存在当前浏览器并可导出。需自行准备时间范围与听感音量可比的片段；平台未自动匹配响度，也没有替你作人工评价。

默认报告、音频副本和任务存放于 `data/analysis-platform/`；可用 `ANALYSIS_LAB_DIR` 改到 NAS。原分析文件不被覆盖。报告 ID 由原始内容、音频身份、补充结果及版本计算，不同运行保留独立报告。任务重启后标为 interrupted，可重新提交；当前队列是单工作进程，尚无断点续算和跨服务器分布式调度。

已有曲库 API 新增 `GET /api/library/songs/{song_id}/analysis-report`，沿用登录及歌曲所有权校验，导出全部持久化音乐分析列（不含账号和存储位置字段）。它是只读快照，独立工作台不会直接写生产数据库。

批量或服务器本地处理：

```bash
.venv-lab/bin/python -m analysis_platform.cli \
  --source data/analysis_results.json --track-key 100.wav \
  --audio data/tracks/100.wav --enrich
```

`--attach path.json` 可重复使用。没有来源音频哈希时，绑定会标记为“用户关联且时长检查”，不会把时长相同当作自动证明同曲。已有音频哈希冲突会拒绝绑定。

## 补充模块

| 模块 | 实现及边界 |
| --- | --- |
| 粗糙度 | 基于频谱峰对的临界带曲线，增益归一化；不是 Essentia 原实现的数值复制，也不是和声正确性或好听评分。每 0.25 秒取约 93 毫秒窗口，是抽样描述。 |
| 重复段落 | 使用现有段落的 chroma 与 RMS，平均链接聚类；保留原标签，仅增加 R1/R2 等组号。无段落时使用明确标注的 8 秒分析窗口。 |
| 愉悦度/激活度 | 可选 MusiCNN + DEAM 预训练头。模型支持窗口约 2.992 秒，步长约 1.488 秒；图表区间与实际模型观察窗口都记录。 |
| 通用乐器 | 可选 Discogs Effnet + Jamendo 乐器头，按 30 秒窗口输出；保留原模型类别索引，过滤 voice，不替换已有 PANNs/ADTOF。分数没有经过本曲库校准。 |

每个模块单独记录状态、耗时、参数、版本，完成一个模块即保存一次任务记录；模型运行成功时还记录权重 SHA256。失败不会清除原报告或其他成功模块。当前日志覆盖新增分析链路；现有混音引擎每个转场的全链路追踪尚未接入。

## 可选模型环境

Essentia TensorFlow 与主分析环境解耦。本次使用隔离的 Linux x86_64 容器，在真实的 101.wav（25.52 秒）上跑通了情绪和通用乐器模型。情绪耗时约 141 秒，乐器约 52 秒；这是本机跨架构容器数据，不代表 Jetson 性能。其他曲目的早期报告保留 unavailable 状态，不会被事后改写为成功。

研究试验下载命令（模型授权与源码授权不同）：

```bash
.venv-lab/bin/python -m analysis_platform.download_models --accept-research-license
```

Linux x86_64 可使用独立 Python 环境安装 `requirements-models.txt`，通过 `ANALYSIS_MODEL_PYTHON` 指向其解释器。也提供 `Dockerfile.models` 和 `scripts/analysis_model_python` 作为本机 Linux x86 试验路径；本次绕过失效镜像站、直接使用官方 registry 完成构建，并验证模型输出与容器超时清理。构建命令：`docker build --platform linux/amd64 -f analysis_platform/Dockerfile.models -t harbeat-analysis-models:1 analysis_platform`。本机启动时设置 `ANALYSIS_MODEL_PYTHON` 为 `scripts/analysis_model_python` 的绝对路径即可启用。

Jetson 是 ARM64，不能直接采用上述 x86 镜像。已部署独立 ARM TensorFlow Python CPU 适配器，使用 Essentia 原预处理算子；25 秒和 204 秒真实音频均跑通四模块。详见 `../deploy/analysis-platform/DEPLOYED.md` 和 `THIRD_PARTY.md`。

## Jetson 运算、阿里云转发

计划沿用当前链路：浏览器 → 阿里云 HTTPS/登录 → Tailscale → Jetson 独立分析服务 → NAS。新增报告路径与现有音乐文件、模型结果并存。

配置模板在 `deploy/analysis-platform/`。实际已沿用阿里云 IP 的有效 HTTPS 证书部署；以下子域名模板供其他环境使用，须替换占位值：

- Jetson 独立目录 `/home/mark/harbeat-analysis-platform`，独立虚拟环境与 systemd 服务，默认 CPU 低优先级、2 核配额、6 GB 内存上限。
- 服务只绑定 Jetson Tailscale 地址；非本机监听强制要求转发密钥。
- 当前阿里云转发配置允许 GET/HEAD 公开查看及试听，写操作保留管理员 Basic Auth；子域名配置为替代部署模板。Nginx 内部注入转发密钥，浏览器不能取得它；Jetson 校验密钥和精确网页来源。
- 目前所有查看者共享同一曲库视图；这不是按账号隔离数据的多租户系统。需要私有曲库时应另加用户级权限。
- 安装前验证 NAS 挂载和写权限、Tailscale 连通性、模型环境；先运行一首样本，再启用服务。Nginx 必须先 `nginx -t`，成功后才能 reload。保留现有 harbeat.service 不动。
- 停用独立服务及其 Nginx 站点即可撤回；不删除报告目录或原音乐数据。

2026-09-18 更新：新增平台已部署：https://8.136.120.255/analysis-lab 。独立登录凭据保存在本机 `~/.codex/private/harbeat-analysis/access.txt`。29 份报告与 7 首音频已同步到 NAS。现有 harbeat-api 主服务保持运行。SSH 连接配置留在运维机器，不随源码发布；部署、运行限制和回滚步骤见 deploy/analysis-platform/DEPLOYED.md。

## 人工标注与验证

人工标注 JSON 示例（数值仅是格式示例，不是真实标注）：

```json
{
  "annotation_id": "listener-01-track-100",
  "audio_sha256": "复制报告中的真实音频SHA256",
  "beats": [0.12, 0.62],
  "downbeats": [0.12],
  "section_boundaries": [16.1, 32.2],
  "instruments": ["piano", "drums"],
  "emotion": [{"time": 10, "valence": 0.2, "arousal": 0.7}]
}
```

拍点一对一匹配容差 70 毫秒，段落边界 0.5 秒。情绪采用本平台刻度：valence [-1,1]，arousal [0,1]。没有人工标注就没有准确率结论。要比较版本，需要对相同标签分别评估两份报告；小样本结论不可泛化到全部曲风。模型间的综合分数不能作为胜负依据。

```bash
.venv-lab/bin/python -m pytest tests/test_analysis_platform.py tests/test_analysis_platform_server.py -q
cd web
npm test -- --run
npm run build
```

现有曲库导出权限测试：安装原项目的 SQLAlchemy、pydantic-settings 和 PyJWT 依赖后，以 `DATABASE_URL=sqlite:///:memory:` 运行 `tests/test_analysis_platform_library.py`。测试使用替身数据库，不会访问生产数据。

## 风格与人工确认

2026-09-19 新增 Discogs400 风格模块，可在页面单独运行。细分类别和原始分数、已有规则、舞种评分、原人工标签及修正历史分别保存。整合范围、缓存协议和对照口径见 [STYLE_INTEGRATION.md](STYLE_INTEGRATION.md)。

## 曲库补算、和弦与动态（2026-09-19）

新增“和弦与动态”页：已有五组基础特征补算、大小三和弦/N 时间轴、RMS P95/P5 动态范围、相对静音占比、起音密度、段落 LUFS/RMS 与相邻差值、DEAM 时间加权摘要。和弦详情可展开并定位原曲。原始来源、段落标签和人工风格标签完整保留；新增结果没有接入混音决策。

Jetson `harbeat-analysis-backfill` 是独立、可续跑的后台服务，使用同一个串行分析队列。208 首正式来源按阶段补缺：基础特征 → 已有补充特征 → 和弦/动态 → 情绪曲线与摘要。已有成功模块跳过；失败有记录，下次运行可补试；关闭网页不影响任务。页面覆盖数量会随最新报告更新。原算法内部失败会单独记录，缺少拍点不伪造节奏指标。

和弦环境使用 `ANALYSIS_CHORD_PYTHON` 指向独立 Python 3.10 venv，安装顺序见 requirements-chords.txt。实际模型为 madmom 0.16.1 DeepChroma + CRF，24 个大小三和弦加 N，不支持七和弦解释，也不输出校准置信度。

当前全量动态与原算法补算在解码前检查内存预算；超长或高采样率音频可能标为 unavailable（需要后续分块实现），不会耗尽服务内存。原算法使用 mono/22050 Hz 分析副本，新响度测量使用原声道/采样率，两者按来源并列。RMS 范围不是 EBU LRA。验证记录在 outputs/feature-coverage-validation.json 与 outputs/feature-deployment-validation.json；整库运行进度保存在 NAS backfill-status.json，完成率不等于预测准确率。

## DEMO 1.0 接歌预处理

页面新增“接歌准备”：角色就绪检查、原始/人工/首拍边界、逐小节人声与声音特征、校准记录、变速及 EQ 计划。Jetson 串行队列新增 `dj_signals` 并优先补齐曲库。详见 [接歌输入与接口](DJ_PREPROCESSING.md)。
