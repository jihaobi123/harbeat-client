# Jetson 远程分析部署记录

2026-09-18 已部署： https://8.136.120.255/analysis-lab

浏览器 → 阿里云 HTTPS（免登录查看、管理员写入）→ Tailscale → Jetson 独立分析服务 → NAS。

管理员账号保存在本机 `~/.codex/private/harbeat-analysis/access.txt`，未写入仓库。2026-09-19 按用户要求开放同事免登录查看：独立分析平台 GET/HEAD（页面、报告、任务状态、静态文件、原曲与分轨试听）不再要求 Basic Auth；其他 HTTP 方法仍校验原管理员账号。任何持有链接的人均可读取这些内容。HTTP 入口仍重定向到 HTTPS，Jetson 仍验证阿里云中转令牌和同源请求。

## 实际安装位置

- 代码：`/home/mark/harbeat-analysis-platform`
- 通用运行环境：`/home/mark/harbeat-analysis-venv`
- ARM 模型运行环境：`/home/mark/harbeat-analysis-model-venv`
- 独立环境文件：`/home/mark/.config/harbeat-analysis.env`（600 权限）
- 数据：`/mnt/nas/harbeat/data/analysis-platform`
- 权重：`/mnt/nas/harbeat/models/analysis-platform`
- 用户服务：`harbeat-analysis-lab.service`，启用了 mark 的 linger 和开机启动。
- 服务日志：`/home/mark/harbeat-analysis-platform/service.log`

Jetson Tailscale 实际为 `--tun=userspace-networking`，虚拟 IP 并未分配给网卡。因此服务监听 `127.0.0.1:8765`，阿里云访问 `100.87.142.21:8765` 由 Tailscale 转交。不要将这里的监听地址改成虚拟 IP，否则出现 `cannot assign requested address`。

现有 `harbeat-api.service` 和 `harbeat-gateway.service` 保持独立；没有更新它们的模型环境或重启主分析服务。本页面运行四项补充分析，读取、保留已有分析结果；未将原有全量预处理流水线改为由本页面重新调度。

## 运维

使用本目录 `ssh.config` 连接 `harbeat-cloud` 和 `harbeat-jetson`。在 Jetson 上：

```sh
systemctl --user status harbeat-analysis-lab
systemctl --user restart harbeat-analysis-lab
tail -n 50 /home/mark/harbeat-analysis-platform/service.log
```

任务逐步结果保存在 NAS `jobs/*.json`，报告不可覆盖。进程重启会把未完成任务标为中断，页面可重新运行。并行计算数为 1、队列上限 8、每模块超时 1800 秒、CPU 配额 2 核、总内存上限 6 GB。启动前检查 NAS 挂载，避免 NAS 掉线时落到本地同名空目录。

前端构建使用 `npm --prefix web run build -- --base=/analysis-lab-static/`，静态资源走独立路径，避免覆盖原有前端资源。

阿里云新增 `harbeat-analysis-relay.conf` / `harbeat-analysis-http.conf` 两个 location 配置；原配置备份位于 `/root/harbeat-analysis-deploy/*.pre-analysis`。撤销转发时只删除新增 include，经 `nginx -t` 后 reload。独立服务可通过 `systemctl --user disable --now harbeat-analysis-lab` 停止，NAS 原始结果保留。

## ARM 模型适配与实测

本机 x86 的 Essentia TensorFlow wheel 不能直接在 ARM 安装。Jetson 使用已有 Essentia 的预处理算子副本，加独立 TensorFlow 2.16.1 Python Graph 执行相同冻结模型；本次走 CPU，不声称使用 GPU。原主环境未安装或替换任何包。

`101.wav` 对照原 Essentia TensorFlow 推理：情绪 17 点，原始愉悦度/激活度最大绝对差 0.000003815；乐器标签一致，四个标签分数最大差 0.000000120。这验证实现一致性，不证明音乐识别准确率。

通过公网实际提交三次完整任务。第一次四模块均 ready，耗时约 79 秒；第二次约 44 秒，包含分块音频读取与内存保护修正。第三次 106.wav（203.808 秒）四模块全部 ready，总耗时约 128 秒。阶段耗时保存在 `outputs/jetson-analysis-job-validation.json` 和 `outputs/jetson-full-track-validation.json`。原始来源哈希已与本地版本核对一致。

已同步 7 首原曲和 29 份历史及新报告，原音频共约 581 MiB。界面支持全部原始特征查看、版本比较、导出、试听和补充任务重跑。

Native 解码按块下混，预估单声道源信号超过 1 GiB 时明确返回错误而不尝试大规模分配。保留最长 2 小时的总时长限制；这不是对所有采样率、时长、曲风的性能保证。模型仍按研究试验用途运行，其授权见 `analysis_platform/THIRD_PARTY.md`。

## 完整来源与真实分轨接入（2026-09-18 更新）

补齐此前仅导入 7 个历史样本的缺口：只读导出生产 `library_songs` 的 43 条完整记录，导入 NAS 已发布的 163 份最新预处理清单，合计 206 份正式来源。审计结果：206 份有原曲，205 份有四大分轨，163 份另有 kick/snare/hihat/tom/cymbal 五类细分鼓轨。全部 NAS 清单关联了对应版本的 163 份人声活动记录；43 条曲库记录中接入各 10 份 SongFormer、EDM 结构、PANNs/ADTOF 独立结果，以及一组历史人工标注集合。侧车必须与实际原曲完整/前缀 SHA 匹配；无法核验的归档只能作为参考，不能提升为当前分析身份。

原始音乐特征完整保留，账户归属和外部平台URL不进入报告。音轨使用服务端登记 ID 读取，限制到 `ANALYSIS_MEDIA_ROOTS=/mnt/nas/harbeat`；禁止任意客户端路径和符号链接越界。媒体注册是来源引用，不声称完成全量内容校验。公开 API、Range 试听继续受原有 HTTPS 登录和中转令牌保护。

新增 `harbeat-analysis-catalog.service` 为独立、低优先级、单次批处理，不依赖 SSH 连接。它先同步已有来源，再逐首读取真实四轨计算 2 秒窗口 RMS（所有声道均方后开方，避免相消），每轨以自身 P95 归一化。该曲线不是乐器存在概率，不适合跨轨比较绝对响度；原始 RMS/dBFS 同时保留。可从页面查看批处理歌曲、当前音轨、进度与错误，也能单独启动一首的分轨测量。关闭浏览器不会停止批处理。已完成缓存可用于恢复，旧报告不覆盖。

前端新增「全部维度」「分轨试听」、曲目搜索、历史版本开关、源模型降级记录，并采用用户提供的原始 logo。所有来源及新增模块可分类、检索、分页、导出；时间曲线可定位播放器。原有历史样本的七组归档算法结果也已附加，整曲频谱估算明确标识来源。报告列表改用原子摘要索引，避免逐份扫描大报告造成加载超时。

维护命令：

```sh
systemctl --user status harbeat-analysis-catalog
# 手动更新曲库快照（生产解释器只读事务，不修改生产表）：
cd /opt/harbeat/releases/analysis-shadow-72564be
PYTHONPATH=/home/mark/harbeat-analysis-platform /opt/harbeat/current/venv/bin/python -m analysis_platform.export_library_snapshot /mnt/nas/harbeat/data/analysis-platform/catalog-library.json
# 完成快照后手动同步和补齐尚未计算的曲线：
systemctl --user start --no-block harbeat-analysis-catalog
```

当前为导入时的快照，不会擅自调度原有全量分离／结构流水线。后台曲线进度以页面实时记录为准；服务异常退出后，已产出的报告和缓存保留，可重新启动该单次服务。

## 2026-09-19 同步分轨播放器

前端增加原曲与四轨共享时钟的同步试听、20 ms 音量切换、统一定位／暂停／恢复、当前歌曲内缓存与细分鼓组提前准备。仅更新独立分析平台前端；不改原有分轨模型、生产服务或 NAS 音频。原曲轻量播放入口仍保留。首次需要传输和解码，已准备轨道的选择不再请求文件。

回滚页面入口：`deploy-backups/20260919-stem-player/index.html`（相对独立平台安装目录）；旧哈希静态资源保留。验证记录见 `analysis_platform/VALIDATION.md`。

## 2026-09-19 风格证据整合

独立 Lab 新增第五个补充模块 Discogs400，模型运行于 Jetson，公网入口和原 HTTPS 鉴权保持不变。现有规则、舞种、人工与外部平台标签分别展示，新增结果保存为 `extensions.genre`，暂不用于原生产选歌。可在“风格与人工确认”中单独运行、查看 400 类分数、按时间查看候选、记录人工修正并导出对照。

新增权重：`genre_discogs400-discogs-effnet-1.pb` 及同名 JSON，安装到原可选模型目录。Jetson 下载时发生 DNS 解析失败，本机从官方 HTTPS 地址下载后通过现有 SSH 传输，再由安装器登记哈希；没有改系统 DNS 或主模型环境。

代码与旧页面备份：`deploy-backups/20260919-style-model/`。回滚应恢复该目录的 `analysis_platform/` 和 `index.html` 并重启独立 Lab；旧静态资源保留。新报告、标注与模型缓存均在 NAS 独立目录，不需要删除。

人工修正存储：`style-reviews/`；EffNet 共享缓存：`embedding-cache/`。服务端先核验原曲完整 SHA，再运行模型；身份别名保证绑定原曲后人工修正仍保留，并禁止旧报告改绑其他音频。新增标注不会写入生产曲库。

本次只读更新了 45 条曲库记录，加 163 份 NAS 来源共 208 份；批量分轨曲线为 207 份可用、1 份无分轨、0 错误。完整口径见 `analysis_platform/STYLE_INTEGRATION.md`。

### 2026-09-19 和弦与覆盖补算

- 新增隔离解释器 `/home/mark/harbeat-analysis-chord-venv/bin/python`，madmom 0.16.1；Lab 环境增加 pyloudnorm 0.1.1。
- `harbeat-analysis-backfill.service` 已安装、启用，调用现有本机认证 API 单任务补缺；后台服务仅承担调度，计算仍受 Lab 的 2 核/6GB 限制。
- 可见入口：`/analysis-lab` 的“和弦与动态”页、顶部曲库补算进度；`GET /api/analysis-lab/coverage` 返回最新报告覆盖及批次状态。
- NAS 进度文件 `data/analysis-platform/backfill-status.json`，持久化已尝试模块、当前 job、错误与开始时的来源指纹。中断后重启调度服务会等待/恢复已有 job。
- 回退备份 `/home/mark/harbeat-analysis-platform/deploy-backups/20260919-coverage-chords/`。回退前停止新增 backfill 服务并等待当前 Lab job 结束，再恢复 Lab 代码和 index.html；保留 NAS 报告与旧静态资源。主混音服务未重启。
- 实际通过公网运行 Woman 四项新模块并验证原始 source_hashes 与此前补充结果保持一致。全曲库任务已启动，不能据此称 208 首全部完成。

## 2026-09-19 Public read access for colleagues

At the owner's request, the existing analysis platform permits anonymous GET/HEAD requests. The Aliyun relay keeps Basic Auth inside `limit_except GET` for all other methods. The upstream relay token, HTTPS, same-origin checks and upload limit remain unchanged. Uploads, saved reviews, reruns and plan generation still require administrator authentication.

Configuration: `aliyun-analysis-public-read.conf`. Live file: `/etc/nginx/snippets/harbeat-analysis-relay.conf`. Backup: `/root/harbeat-analysis-deploy/20260919-170613.before-public-read.conf` on Aliyun. Nginx configuration validation and graceful reload succeeded; Jetson services were not restarted. Restore the backup, validate and reload to revoke anonymous viewing.

Validation: anonymous platform/report/log GET returned 200, media ranges returned 206; anonymous POST/PUT/PATCH/DELETE/OPTIONS returned 401. Valid existing admin credentials reached a nonexistent test route (404); invalid credentials returned 401. A fresh unauthenticated browser displayed 215 library records, loaded song details and played a transition without errors. Local validation records: `outputs/analysis-access-20260919/`. Earlier deployment notes describing authenticated GET reflect historical policy.
