# HarBeat 项目技术交接文档

> **项目名称**：HarBeat — 街舞音乐曲库管理与分析平台
> **代码仓库**：`harbeat-client`
> **交接日期**：2026-04-27
> **最后更新人**：（上一任负责人）

---

## 目录

- [0. 快速概览（TL;DR）](#0-快速概览tldr)
- [1. 服务器与网络拓扑](#1-服务器与网络拓扑)
- [2. 阿里云 ECS — 它做什么 & 怎么管理](#2-阿里云-ecs--它做什么--怎么管理)
- [3. Jetson Orin NX — 它做什么 & 怎么管理](#3-jetson-orin-nx--它做什么--怎么管理)
- [4. 后端模块（app/）— 各模块功能与技术方案](#4-后端模块app--各模块功能与技术方案)
- [5. 前端（web/）— 技术栈与组件](#5-前端web--技术栈与组件)
- [6. 数据库 — 数据模型与表](#6-数据库--数据模型与表)
- [7. 第三方依赖与凭证](#7-第三方依赖与凭证)
- [8. 常见运维场景](#8-常见运维场景)
- [9. 已知问题 & 待改进项](#9-已知问题--待改进项)
- [10. 凭证与密码清单（请单独移交）](#10-凭证与密码清单请单独移交)
- [11. 历史/原型子项目（仓库内，未集成到主服务）](#11-历史原型子项目仓库内未集成到主服务)
- [12. 联系信息 & 快速求助](#12-联系信息--快速求助)

---

## 0. 快速概览（TL;DR）

- 这是一个面向街舞老师 / DJ 的「**音乐管理 + AI 分析 + DJ 混音**」系统。
- 用户通过浏览器访问 <http://8.136.120.255/> 使用。
- **后端** = FastAPI + PostgreSQL + Redis；**前端** = React + Vite + TailwindCSS。
- 运行环境分布在两台服务器：
  - **阿里云 ECS**（公网入口）`8.136.120.255`
  - **Jetson Orin NX**（业务主机，做 GPU 推理）通过 Tailscale 内网连接
- 数据库已经从「远程阿里云 RDS」迁到「**Jetson 本地 PostgreSQL**」。
- 本仓库中还有几个历史/原型子项目（`FinalReco` / `Rec0` / `GrooveEngine` / `SongFormer`），目前未集成到主服务，详见 [第 11 节](#11-历史原型子项目仓库内未集成到主服务)。

---

## 1. 服务器与网络拓扑

### 整体数据流

```text
浏览器
  │ HTTP
  ▼
阿里云 ECS  8.136.120.255  (华东1·杭州 / 2核4G)
  ├─ Nginx :80              ←  公网入口
  ├─ Cloud Gateway :8080    ←  FastAPI 透传网关
  └─ Tailscale 客户端       ←  连入 tailnet
        │
        │ Tailscale 加密虚拟网络  (100.x.x.x 网段)
        ▼
Jetson Orin NX             tailscale IP: 100.91.30.53
  ├─ FastAPI uvicorn :8000   ←  真正的业务后端
  ├─ PostgreSQL :5432        ←  本地数据库（apt 安装）
  ├─ Redis :6379             ←  缓存 / 任务锁
  └─ /home/mark/harbeat/data/  ←  音频文件、模型权重、向量索引
```

> **说明**
> - Jetson 没有公网 IP（位于本地网络 `220.200.73.1` NAT 后），通过 Tailscale 与阿里云 ECS 建立加密 P2P/中继连接。
> - 阿里云 ECS 自身**不存任何数据**，纯粹做"公网入口 + 反代"。
> - 前端 SPA 静态文件实际由 Jetson 上的 FastAPI 提供（StaticFiles 挂载）。

### 关键 IP / 域名汇总

| 节点 | 地址 | 备注 |
|---|---|---|
| 公网入口 | `8.136.120.255` | 阿里云 ECS 公网 |
| Jetson Tailscale | `100.91.30.53` | tailnet 内部地址 |
| Jetson 公网（NAT 后）| `220.200.73.1` | 动态公网，不可直连 |
| 阿里云账号 | `nick6331...` | ECS 在此账号下 |
| frp 备用（已停用）| port `7000/7500` | 早期方案，现已废弃 |

### ⚠️ 已废弃的旧 RDS（重要）

曾经使用 `pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432`：

- 这个 RDS **不在我们的阿里云账号下**，无法管理白名单
- 一段时间后 Jetson 公网 IP 变化，被白名单拒绝，无法登录
- **2026-04-27 已切换为 Jetson 本地 PostgreSQL**，原 RDS 数据放弃
- 代码、文档中如还出现该域名，均为历史遗留，可忽略

---

## 2. 阿里云 ECS — 它做什么 & 怎么管理

### 职责

1. 提供公网 80 端口入口。
2. 通过 Nginx 反向代理把 `/` 请求转发给本机 8080 的 `cloud_gateway`。
3. `cloud_gateway` 是一个轻量 FastAPI（见 [deploy/cloud_gateway/app/main.py](deploy/cloud_gateway/app/main.py)），做的只有一件事：把所有请求按原样转发到 `http://100.91.30.53:8000`。
4. 通过 Tailscale 客户端进入 tailnet，让 Jetson 能被访问到。
5. 备份 PostgreSQL 转储到 ECS 磁盘（建议未来加入定时任务，目前暂无）。

### SSH 登录

```bash
ssh root@8.136.120.255
# 密码: (问交接人)
```

> Jetson 上已配置免密：在 Jetson 上 `ssh root@8.136.120.255` 直接进入。

### 关键文件

| 路径 | 作用 |
|---|---|
| `/etc/nginx/conf.d/default.conf` | Nginx 配置 |
| `/opt/cloud_gateway/` | Gateway FastAPI 项目（部署位置以实际为准）|
| `/etc/systemd/system/cloud_gateway.service` | 服务单元（如有）|
| `/etc/systemd/system/tailscaled.service` | Tailscale 服务 |

### 常用运维命令

```bash
systemctl status nginx
systemctl status cloud_gateway          # 如配置为 systemd
systemctl status tailscaled
tailscale status                        # 看 tailnet 成员
journalctl -u cloud_gateway -f          # 跟踪 gateway 日志
curl http://127.0.0.1:8080/health       # 本机测网关
curl http://127.0.0.1:8080/jetson/health # 经 Tailscale 测 Jetson
```

### Gateway 关键代码

- 仓库内：[deploy/cloud_gateway/app/main.py](deploy/cloud_gateway/app/main.py)
- 环境变量：`JETSON_BASE_URL=http://100.91.30.53:8000`（默认值已写在代码里）

---

## 3. Jetson Orin NX — 它做什么 & 怎么管理

### 硬件

- **NVIDIA Jetson Orin NX**（ARM64, JetPack 6.x, CUDA 11.4+）
- 内存 8GB / 16GB（CPU 与 GPU 共享）

### 职责

1. 跑 FastAPI 业务后端（端口 `8000`，所有 API 都在这里）。
2. 跑 PostgreSQL 数据库（端口 `5432`，apt 安装的 14.x 版本）。
3. 跑 Redis（端口 `6379`）。
4. 跑音频分析（librosa / madmom / essentia）。
5. 跑 GPU 推理（Demucs 声轨分离 / CLAP 语义嵌入）。
6. 存储：音频原文件、stems、模型、向量索引。
7. 通过 Tailscale 接入 tailnet。

### SSH 登录

```bash
# 本地局域网（如同一 Wi-Fi）
ssh mark@<Jetson 局域网 IP>
# 通过 Tailscale 远程
ssh mark@100.91.30.53
# 用户名: mark      密码: (问交接人)
```

### 路径地图

```text
/home/mark/harbeat/                     项目根目录（git clone 的位置）
  ├── app/                              FastAPI 后端代码
  ├── web/                              前端源码与 dist/
  ├── data/music-files/                 音频文件（持久数据）
  ├── data/clap_model/                  CLAP 模型权重 (~600MB)
  ├── data/chroma_db/                   语义向量索引
  ├── .env                              环境变量（含 DATABASE_URL 等）
  └── uvicorn.log                       后端运行日志

/home/mark/venvs/harbeat/               Python 虚拟环境
  └── bin/uvicorn                       启动命令使用此 uvicorn

/var/lib/postgresql/14/main/            PostgreSQL 数据目录（apt 默认）
```

### 启动 / 停止 FastAPI

> 当前**没有 systemd 服务**（建议后续补上）。手工启停命令：

```bash
# 查看进程
ps aux | grep uvicorn | grep -v grep

# 停止
pkill -f "uvicorn app.main:app"

# 启动（后台）
cd /home/mark/harbeat
nohup /home/mark/venvs/harbeat/bin/uvicorn \
    app.main:app --host 0.0.0.0 --port 8000 --workers 1 \
    > uvicorn.log 2>&1 &

# 查看日志
tail -f /home/mark/harbeat/uvicorn.log
```

### 数据库管理

```bash
# 系统服务
sudo systemctl status postgresql

# 连接
PGPASSWORD=Hb12345678 psql -h 127.0.0.1 -U harbeat -d rhythm_prism

# 备份
pg_dump -h 127.0.0.1 -U harbeat rhythm_prism > backup.sql

# 恢复
psql -h 127.0.0.1 -U harbeat rhythm_prism < backup.sql
```

### `.env` 文件示例（重要）

```ini
APP_NAME=Street Dance MVP API
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
DATABASE_URL=postgresql+psycopg2://harbeat:Hb12345678@127.0.0.1:5432/rhythm_prism
REDIS_URL=redis://127.0.0.1:6379/0
JWT_SECRET=<32 字节随机串>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080
UPLOAD_DIR=/home/mark/harbeat/data/music-files
SPOTIPY_CLIENT_ID=...
SPOTIPY_CLIENT_SECRET=...
```

### 依赖安装（以防重装）

```bash
sudo apt-get install -y postgresql postgresql-contrib redis-server
sudo apt-get install -y libsndfile1 ffmpeg rubberband-cli
sudo apt-get install -y build-essential libblas-dev liblapack-dev libopenblas-dev gfortran

python3 -m venv /home/mark/venvs/harbeat
source /home/mark/venvs/harbeat/bin/activate
pip install -r requirements.jetson.txt
# torch / torchaudio 必须使用 NVIDIA 提供的 Jetson 专用 wheel，详见 deploy/JETSON_SETUP.md
```

参考：[deploy/JETSON_SETUP.md](deploy/JETSON_SETUP.md)

---

## 4. 后端模块（app/）— 各模块功能与技术方案

> 本节先用 [4.1](#41-核心功能端到端详解) 讲清楚每一个**核心功能**到底用了什么模型、怎么实现、效果如何；
> 然后 [4.2](#42-入口文件) ~ [4.4](#44-业务模块概览-appmodules) 再列出代码层面的模块速查表。
> 想快速上手的人**直接看 4.1 即可**。

### 4.1 核心功能端到端详解

下面 7 个功能是这个项目的全部业务核心，每个都按「触发 → 调用链 → 模型/算法 → 关键参数 → 输出」给出。

---

#### ① 音轨分离（Stem Separation）—— 把一首歌拆成 4 轨

**用户怎么触发**

- 任何一次「上传歌曲」或「歌单导入」之后，**后台自动**触发，无需用户点击。
- 涉及 API：`POST /api/library/songs`（上传）/ 歌单导入流程的最后一步。
- 前端 `AnalysisPanel.tsx` 显示分析进度；`StemPlayer.tsx` 显示 4 轨独立音量。

**调用链**

```text
上传 → service.create_or_replace_library_song
     → background_tasks.run_analysis_and_separation
        ├─ Phase 1: BPM/Key/段落分析（见功能 ③）
        └─ Phase 2: Demucs 子进程分离 4 轨
            └─ stems/htdemucs/<song_id>/{vocals,drums,bass,other}.wav → 转 mp3
```

为了避免 OOM，整个分析跑在**独立子进程**里（`app/modules/library/_run_analysis.py`），并通过 **Redis 全局锁**确保「同一时刻只跑一首歌」（默认 TTL 1800s）。

**模型**

| 项 | 值 |
|---|---|
| 模型 | **Demucs htdemucs**（Facebook 开源，PyTorch）|
| 输出轨 | `vocals` 人声、`drums` 鼓、`bass` 贝斯、`other` 其它 |
| 命令 | `python -m demucs -n htdemucs -d cuda --segment 7 <input>` |
| Segment | 7 秒分块推理，峰值显存 ~2GB |
| 设备 | 自动检测 CUDA；Jetson 上走 GPU |

**效果**

- 4 轨分离质量接近商用工具（Spleeter / RX10），适合街舞老师抽人声、抽鼓做训练。
- 一首 4 分钟歌：Jetson GPU 上约 **30~60 秒**完成。
- 原始 WAV 约 40MB/轨 → 自动转码为 MP3（约 4MB/轨），加速前端流播。

**输出产物**

- 文件：`/home/mark/harbeat/data/.../stems/htdemucs/<song_id>/{vocal,drum,bass,other}.{wav,mp3}`
- 数据库：`library_songs.stems`（dict，stem 名 → 文件路径）
- 状态：`library_songs.analysis_status` 由 `analyzing` 变为完成

---

#### ② 自动 DJ 混音（DJ Mix Plan / Offline Render）—— 一键把歌单变成一首连续混音

**用户怎么触发**

- 在「歌单详情页」点 **生成 DJ 混音** 按钮 → 选择风格、时长 → 提交。
- API：
  - `POST /api/playlists/dj-mix-plan` — 只生成排序方案与过渡参数（轻量、可预览）
  - `POST /api/playlists/dj-mix-offline` — 生成完整 mp3 主混音 + 4 轨分轨

**调用链**

```text
playlists/router.py
  → service.generate_dj_mix_plan / generate_style_mix_playlist
      → groove_adapter.library_song_to_track_metadata        # 适配数据格式
      → groove_adapter.run_groove_engine_plan
          → GrooveEngine/logic/brain.py  TransitionPlanner.plan
          → GrooveEngine/audio/offline_renderer.py  OfflineDualDeckRenderer.render_transition
              → 输出最终 mp3
```

**算法核心：GrooveEngine（自研 DJ 引擎）**

GrooveEngine 是这个项目的**核心知识资产**，位于仓库 `GrooveEngine/`。它不依赖深度学习模型，是一套**多因素加权打分 + 过渡策略库**的规则引擎：

排序时对每一对「上一首 → 下一首」候选计算综合分（11 个因素，权重在 `TransitionPlanner.PlannerWeights`）：

| 因素 | 权重 | 含义 |
|---|---|---|
| `phrase_alignment` | 0.16 | 8 小节短语对齐（最重要）|
| `phase_alignment` | 0.14 | 节拍相位对齐 |
| `energy_delta` | 0.12 | 能量差不要太大 |
| `strategy_bias` | 0.12 | 策略本身的偏好（如 chorus→intro 加分）|
| `bar_position` | 0.10 | 落在 bar 边界 |
| `harmonic` | 0.08 | Camelot Wheel 和声距离 |
| `style_fit` | 0.08 | 舞种风格匹配 |
| `spectral_conflict` | 0.08 | 频谱冲突避让 |
| `loudness_continuity` | 0.06 | 响度连续 |
| `dance_continuity` | 0.06 | 律动连续 |
| `sync_quality` | 0.04 | 同步质量 |

**过渡策略库**（`STRATEGY_REGISTRY`）：

- `crossfade` — 等功率（cos/sin 曲线）淡入淡出
- `tempo_sync` — 用 librosa 时间拉伸把下一首 BPM 渐变对齐当前
- `phase_align` — 把下一首的下拍位移到当前的下拍上
- `bass_swap` — 出轨低音提前衰减、入轨低音延迟进入（避免低频堆积浑浊）
- `vocal_duck` — 重叠期把出轨人声压低 ~42%，让入轨人声接管
- `drum_soft_entry` — 入轨鼓循序渐进进入

**关键参数（API 入参）**

- `style` 风格、`duration_minutes` 目标时长
- `quality_mode` 渲染质量、`strict_harmonic` 是否强制和声兼容
- `max_tempo_shift` 最大允许变速比（默认 ~6%）
- `phase_offset` 相位修正、`diversity` 风格多样性比例

**渲染细节**

- 采样率 44.1 kHz、块大小 2048
- 后端按需选择：`librosa` / `madmom` / `soundfile` （`sync_backend` 字段记录用了哪个）
- 同步失败会留 `sync_warning_count` 与 `sync_backend` 标记，便于调试

**效果**

- 输出一首约 30~60 分钟的连续 DJ 混音（按 `duration_minutes` 决定）。
- 拐点处的过渡接近人工 DJ 水平，特别在节拍/相位/低频处理上。
- 同时保留每首歌的 4 轨**分轨混音**（vocals/drums/bass/other 全程整合版），便于二次创作。

**输出产物**

- API 返回：`DjMixPlanResult { playlist, transition_plan, processed_files, score_breakdown }`
- 文件：`data/.../mix_<id>.mp3`（主混）+ 4 个 stem 全程混 mp3
- 启动时 `_cleanup_old_mix_files()` 会清掉 1 小时之前的 mix 文件（防止盘满）

---

#### ③ BPM / Key / 段落分析（多引擎投票）

**用户怎么触发**

- 上传歌曲后**自动**作为 Phase 1 触发（早于 stem 分离）。
- 也可以通过 `PATCH /api/library/songs/{id}` 手动重跑。

**调用链**

```text
background_tasks.run_analysis_and_separation
  → 子进程 _run_analysis_subprocess
      → analysis.analyze_audio_file
          ├─ _detect_beats_and_downbeats → beat_engine.analyze_beats   # ★多引擎投票
          ├─ _detect_key                                               # Chroma + 模板
          ├─ _detect_structure                                         # SSM 段落分析
          └─ _detect_phrase_structure                                  # 8 小节短语聚类
```

**BPM 多引擎投票**

| 引擎 | 干什么 |
|---|---|
| **essentia** `RhythmExtractor2013` + `PercivalBpmEstimator` | 多特征 BPM；返回 beats、confidence、bpm_histogram |
| **madmom** RNN + DBN | beat / downbeat 联合追踪；fps=100 |
| **BeatNet+**（3 模型集成，FP16，CUDA）| GTZAN/Ballroom/Rock 三个模型共享 LOG_SPECT 特征，再过 DBN |
| **librosa** tempogram | 兜底校验 |

最终融合：加权平均置信度，**confidence < 0.65** 标记 `beat_needs_review=true`，前端会有"需要复核"的标识。

**Key 检测**

- `librosa.feature.chroma_cqt()` 提取 12 维和声特征
- 用 **Krumhansl-Kessler 调式模板**做匹配 → 得到 `key`（C/D/E...） 与 Camelot 表示（如 `8B`）

**段落识别**

- 计算 **Self-Similarity Matrix (SSM)**
- 用 **Foote 棋盘核**做卷积，得到段落边界（kernel ≤ 64 帧，最小段落 ≥ 8s）
- 再做 8 小节短语分组、能量聚类，标签：`intro / verse / chorus / bridge / drop / buildup / breakdown / outro`
- ⚠️ `SongFormer/` 子项目可以做更精细的段落识别，但**当前主服务还没接入**。

**输出产物（数据库字段）**

```
bpm, beat_points[], downbeats[], beat_confidence,
beat_grid_offset, beat_grid_interval,
beat_engines_used[], beat_needs_review,
key, camelot_key, key_confidence,
phrase_map[], cue_points[]
```

---

#### ④ Vibe 智能推荐（自然语言 → 歌曲）

**用户怎么触发**

- 在搜索框输入"雨夜街道，孤独"、"激烈的练舞氛围"等自然语言。
- API：`POST /api/recommendations/vibe-search`
- 旁支：`POST /api/recommendations/discover`（分类推荐）、`/for-user`（协同过滤）

**调用链**

```text
recommendations/router.vibe_search_endpoint
  → service.vibe_search
      → vibe_service.interpret_vibe         # 中文 → 英文描述 + 流派/年代提取
      → _run_clap_text_subprocess           # CLAP 文本编码 → 512-d 向量
      → vector_store.get_clap_collection().query()   # ChromaDB top_k 检索
      → 返回 top_k 歌曲
```

**模型**

| 项 | 值 |
|---|---|
| 模型 | **CLAP** `laion/clap-htsat-unfused`（HuggingFace Transformers）|
| 向量维度 | 512，已 L2 归一化 |
| 跨模态 | 文本和音频共享同一向量空间，可互相检索 |
| 索引 | **ChromaDB**（HNSW，cosine 距离），路径 `data/chroma_db/` |
| 集合 | `harbeat_clap`（CLAP 音频嵌入）+ `harbeat_songs`（备选：SentenceTransformer all-MiniLM-L6-v2）|

**自然语言理解（vibe_service）**

- 中文关键词 → 英文描述映射，例：`雨夜 → "rainy midnight atmosphere"`、`伤感 → "sad reflective"`
- 正则提取流派：hip-hop / jazz / electronic / ambient / rock 等
- 正则提取年代：`90s / 2000s / 80s` → 后续做时间过滤

**索引怎么建**

- 上传歌曲后的 Phase 3（在 stem 分离之后）：把音频以 48 kHz 输入 CLAP → 得到 512-d 向量 → 写入 ChromaDB。

**关键参数**

- top_k 默认 5
- 子进程加载模型，跑完释放，避免常驻吃显存

**输出产物**

- API 返回：`{ songs: [{song_id, title, artist, style, energy, in_library}, ...] }`
- ChromaDB 中歌曲向量持久化，可被反复查询

---

#### ⑤ 流式播放（HTTP Range + 多轨同步）

**用户怎么触发**

- 前端 `<audio>` / `WaveformPlayer.tsx` 加载 `src` 时浏览器会自动发 Range 请求。
- API：`GET /api/stream/processed/{filename}` 等流播放端点。

**实现要点**

- 解析请求头 `Range: bytes=start-end`
- 命中：返回 **206 Partial Content** + `Content-Range: bytes start-end/total`
- 未命中：返回 **200 OK** 全量
- 分块大小 **256KB**（平衡内存与网络包）
- Content-Type 表：mp3 → `audio/mpeg`，flac → `audio/flac`，wav → `audio/wav`
- Header 都带 `Accept-Ranges: bytes`，浏览器支持任意 seek

**多轨同步（StemPlayer）**

- 前端为 4 轨各起一个 `<audio>` 元素，主轨为时钟源，其它轨用 `currentTime` 对齐。
- 拖动进度条时统一发 Range 请求，4 个流同时跳转。

**权限**

- `_get_user_from_request` 校验 JWT；歌曲必须属于当前用户的曲库或公开资源。

---

#### ⑥ 歌单导入（网易云 / QQ 音乐 / Spotify）

**用户怎么触发**

- 前端 `PlaylistImportModal.tsx`（6 步流程）粘贴歌单链接。
- API：`POST /api/playlists/import`

**调用链**

```text
playlists/router.import_playlist_endpoint
  → playlists/service.import_playlist
      → fangpi/playlist_parser.parse_playlist_url
          ├─ detect_platform: 正则识别平台
          ├─ _fetch_netease  (music.163.com/api/v3/playlist/detail, n=5000)
          └─ _fetch_qqmusic  (y.qq.com)
      → 拿到歌曲列表后，对每首歌：
          → fangpi/service.download_fangpi_song
              ├─ 优先 fangpi.net 搜索（快）
              └─ 兜底 search.kuwo.cn + antiserver.kuwo.cn 直接下载
      → 入库 + 触发 Phase 1 分析
```

**URL 识别正则**

- 网易云：`music\.163\.com.*[?&#]id=(\d+)`
- QQ 音乐：`y\.qq\.com/n/ryqq/playlist/(\d+)` 或 `y\.qq\.com.*[?&]id=(\d+)`

**下载源**

实际上**所有源最终都来自 Kuwo CDN**（fangpi.net 也是 Kuwo 的代理）。统一音质：mp3 320kbps。

**关键参数**

- 网易云单次最大 5000 首
- 文件最小 200KB（过滤占位符）
- CDN 偶发断流，自动重试

**输出**

- API 返回：`{ playlist_id, import_count, pending_analysis_count }`
- 数据库：新建 `playlists` 行 + N 条 `playlist_songs` + N 条 `library_songs`
- 文件：`data/songs/...`

---

#### ⑦ NCM 解密（网易云加密音频 → 普通 mp3/flac）

**用户怎么触发**

- 上传 `.ncm` 文件时**自动**识别后缀走解密流程。

**算法（无外部依赖，纯 cryptography 库）**

`app/modules/library/ncm_decrypt.py` 三步：

1. **校验魔数**：文件头 `0x4354454E464441 4D`（`CTENFDA M`），跳过 8 字节 magic + 2 字节 padding。
2. **解出 RC4 密钥**：
   - 读 4 字节小端长度 → 取出加密 key 数据
   - 每字节 `XOR 0x64`
   - **AES-128-ECB** 用内置 `CORE_KEY` 解密 → PKCS7 反填充
   - 跳过前 17 字节固定前缀 `"neteasecloudmusic"` → 得到 RC4 主密钥
3. **解元数据**：
   - 读 4 字节长度
   - 每字节 `XOR 0x63`
   - **AES-128-ECB** 用内置 `META_KEY` 解密 → PKCS7 反填充 → Base64 解码 → JSON

**输出**

```json
{ "musicName": "...", "artist": [["name","id"]], "format": "mp3|flac", ... }
```

最终：解密成普通 mp3/flac 写入 `data/songs/`，并按元数据自动建 `LibrarySong` 记录。

---

### 4.2 入口文件

[app/main.py](app/main.py)：

- 创建 FastAPI 实例，挂载 CORS 中间件
- `lifespan` 内执行：
  - `Base.metadata.create_all()` — 自动建表
  - `_migrate_add_missing_columns()` — 增量加列（无 Alembic）
  - `_cleanup_old_mix_files()` — 清理 1 小时前的 mix 文件
  - `_schedule_pending_analyses()` — 重启时把"未分析"的歌曲重新排队
- 通过 **Redis SETNX** 实现"多 worker 时只有一个执行启动钩子"的锁
- 挂载前端静态文件（`web/dist/`）作为 SPA fallback

### 4.3 公共层 `app/shared/`

| 文件 | 作用 |
|---|---|
| `config.py` | Pydantic Settings，统一读取 `.env` |
| `database.py` | SQLAlchemy 引擎、Session 工厂、Base |
| `redis.py` | Redis 单例 |
| `security.py` | bcrypt 密码哈希、JWT 编码/解码 |
| `responses.py` | 统一响应格式 `{code, message, data}` |
| `audit.py` | 审计日志（写入数据库或文件）|

### 4.4 业务模块概览 `app/modules/`

> 详细的功能实现见 [4.1](#41-核心功能端到端详解)，本表只用作"找文件用"的速查表。

每个模块标准结构：`router / service / models / schemas`。

| 模块 | 职责（一句话）| 主要文件 |
|---|---|---|
| **auth** | 注册 / 登录 / JWT | `dependencies.py` (get_current_user) |
| **users** | 用户档案 CRUD | `service.py` |
| **library** | 曲库 + Phase1/2 分析 + Stem 分离 | `analysis.py`、`beat_engine.py`、`background_tasks.py`、`_run_analysis.py`、`ncm_decrypt.py`、`bpm_lookup.py` |
| **playlists** | 歌单 CRUD + DJ 混音入口 | `transition_planner.py`、`offline_renderer.py`、`groove_adapter.py` |
| **fangpi** | 第三方歌单解析与歌曲下载 | `playlist_parser.py`、`service.py` |
| **music** | 单曲分析对外接口 | `router.py` |
| **recommendations** | Vibe 搜索 + 协同推荐 | `vibe_service.py`、`vector_store.py`、`spotify_service.py`、`_run_clap_audio.py`、`_run_clap_text.py` |
| **sessions** | 练舞会话 / 时间轴 | `service.py` |
| **profiles** | 用户音乐画像 | `service.py` |
| **stream** | HTTP Range 流播放 + 多轨同步 | `audio_processor.py`、`dj_sequencer.py`、`dj_transition.py`、`model_selection.py` |
| **health** | `/health` 健康检查 | `router.py` |

### 路由汇总

见 [app/modules/router.py](app/modules/router.py)：

| 前缀 | 模块 |
|---|---|
| `/health` | health |
| `/api/auth` | auth |
| `/api/stream` | stream |
| `/api/library` | library |
| `/api/music` | music |
| `/api/users` | users |
| `/api/playlists` | playlists |
| `/api/profiles` | profiles |
| `/api/recommendations` | recommendations |
| `/api/sessions` | sessions |
| `/api/fangpi` | fangpi |

---

## 5. 前端（web/）— 技术栈与组件

### 技术栈

- **React 18 + TypeScript 5**
- **Vite** 构建
- **TailwindCSS 3**
- **Zustand** 状态管理
- 原生 Canvas 2D 绘制波形

### 关键目录

```text
web/src/App.tsx                   根组件（三栏布局）
web/src/api/client.ts             axios/fetch 封装，自动带 JWT
web/src/store/                    Zustand store（用户、当前歌曲、歌单等）
web/src/components/
  ├── LoginPage.tsx               登录/注册
  ├── Sidebar.tsx                 导航 + 歌单 + 新建歌单
  ├── SongList.tsx                曲库列表 + 右键菜单
  ├── SongDetail.tsx              歌曲详情（包裹下面三个）
  │   ├── WaveformPlayer.tsx      波形 + Cue + A-B Loop + BPM Sync
  │   ├── AnalysisPanel.tsx       BPM/Key/Camelot 显示 + Stem 分离按钮
  │   └── StemPlayer.tsx          四轨独立音量控制
  ├── PlaylistImportModal.tsx     歌单导入 6 步流程
  └── PlatformSearch.tsx          在线搜索
```

### 构建与部署

```bash
cd web
npm install
npm run build        # 产物输出到 web/dist/
```

> Jetson 上的 FastAPI 通过 StaticFiles 直接挂载 `web/dist/`，所以**前端发布 = 在 Jetson 上 `git pull` + `npm run build`**。

### 开发模式

```bash
cd web && npx vite --port 5180
```

`vite.config.ts` 已配置 `/api` 代理到 `127.0.0.1:8000`。

---

## 6. 数据库 — 数据模型与表

| 项 | 值 |
|---|---|
| 数据库类型 | PostgreSQL 14 |
| 位置 | Jetson 本地 `127.0.0.1:5432` |
| 数据库名 | `rhythm_prism` |
| 用户 | `harbeat` |
| 数据目录 | `/var/lib/postgresql/14/main/` |
| ORM | SQLAlchemy 2.0 (declarative) |
| 迁移方案 | 无 Alembic；用 `metadata.create_all()` + 自定义 `_migrate_add_missing_columns()` 做"加列不破坏老表"的简易增量迁移。<br>⚠️ 删除列、重命名、改类型都不会自动处理，需手工 `ALTER TABLE`。|

### 主要表（来自各模块的 `models.py`）

| 表名 | 说明 |
|---|---|
| `users` | 账号、密码哈希、舞种偏好等 |
| `library_songs` | 曲库元数据（标题/艺术家/BPM/Key/状态等）|
| `playlists` | 歌单 |
| `playlist_songs` | 歌单-歌曲关联（含顺序、标签）|
| `sessions` | 练舞会话 |
| `song_tags` | 标签 |
| `profiles` | 用户画像 |
| ... | 其他模块各自表 |

```text
查看所有表: \dt
查看表结构: \d library_songs
```

---

## 7. 第三方依赖与凭证

### Spotify Web API

- 用于歌曲搜索、专辑封面、跨平台 ID 匹配
- 凭证：`SPOTIPY_CLIENT_ID` / `SPOTIPY_CLIENT_SECRET`（在 `.env` 中）
- 申请地址：<https://developer.spotify.com/dashboard>

### fangpi.net / kuwo.cn

- 歌曲下载源（爬虫接入），无需账号
- 代码位置：`app/modules/fangpi/`

### CLAP 模型

- `laion/clap-htsat-unfused`
- 首次启动自动从 HuggingFace 下载到 `data/clap_model/`，约 600MB

### Demucs `htdemucs_ft`

- Facebook 开源声轨分离模型
- 首次使用从官方下载，缓存到 `~/.cache/torch/hub/`，约 80MB × 4（4 模型 ensemble）

### Tailscale

- 所有节点共用一个 tailnet，登录账号
- 控制台：<https://login.tailscale.com/admin/machines>

---

## 8. 常见运维场景

### 场景 1：修改后端代码后部署

```bash
# 在 Jetson 上
cd /home/mark/harbeat
git pull
pkill -f "uvicorn app.main:app"
sleep 2
nohup /home/mark/venvs/harbeat/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --workers 1 > uvicorn.log 2>&1 &
sleep 5
tail -30 uvicorn.log
```

### 场景 2：修改前端代码后部署

```bash
cd /home/mark/harbeat/web
git pull              # 如果还没拉
npm install           # 依赖变更时
npm run build
# 不需要重启后端，FastAPI 直接读 dist/
```

### 场景 3：数据库备份

```bash
# 在 Jetson 上
pg_dump -h 127.0.0.1 -U harbeat rhythm_prism | gzip > /home/mark/backups/db_$(date +%F).sql.gz
# 建议加入 crontab 定时执行
```

### 场景 4：查看运行日志

```bash
# Jetson FastAPI
tail -f /home/mark/harbeat/uvicorn.log
# PostgreSQL
sudo journalctl -u postgresql -f
# Redis
sudo journalctl -u redis-server -f
# ECS Nginx
sudo tail -f /var/log/nginx/access.log
```

### 场景 5：Tailscale 链路异常

```bash
# 分别在两台机器上
tailscale status
tailscale ping <对方主机名>
sudo systemctl restart tailscaled
```

### 场景 6：添加新用户访问 Jetson（团队协作）

1. 在 Mac/Win 上安装 Tailscale 并登录 账号
2. Tailscale 控制台 admin 批准设备
3. `ssh mark@100.91.30.53` 即可（需要 `ssh-copy-id` 推过公钥）

---

## 9. 已知问题 & 待改进项

1. **Jetson 上 FastAPI 没有 systemd 服务**，重启机器后需手动 `nohup` 启动。
   建议：写一个 `/etc/systemd/system/harbeat.service`。
2. **PostgreSQL 没有定时备份脚本**，数据只存一份在 Jetson SSD。
   建议：`pg_dump` + 拷贝到 ECS 的 cron 任务。
3. **没有 Alembic 迁移工具**。当前依赖 `metadata.create_all` + 增量加列。如需删列/改类型，必须手工写 SQL。
4. 历史代码与文档中仍残留 RDS 域名（`pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com`），可逐步清理。
5. `cloud_gateway` 用 httpx 转发，长连接 / SSE / WebSocket 暂未优化。
6. **Jetson 内存只有 8GB**（部分机型 16GB），Demucs + CLAP 同时跑会 OOM。代码已用子进程隔离 + Redis 启动锁缓解。
7. Web 前端的 `PlaylistImportModal` 6 步流程偶尔会丢状态，刷新后需重来。
8. 仓库根有大量 `_diag_*` / `_check_*` / `_fix_*` 调试脚本（`scripts/` 下），可整理或归档。

---

## 10. 凭证与密码清单（请单独移交）

> ⚠️ **实际凭证请通过私聊 / 密码管理器交接，不写在本文档。**

- 阿里云账号（`nick6331***`）：
  - 控制台密码
  - ECS root 密码 / SSH key
- Jetson `mark` 账号密码
- PostgreSQL 密码（默认 `Hb12345678`，**建议改**）
- `JWT_SECRET`（`.env` 中，**建议改**）
- Spotify Client ID / Secret
- Tailscale 账号（`@`）登录方式
- 域名（如有）DNS 解析账号

---

## 11. 历史/原型子项目（仓库内，未集成到主服务）

### `FinalReco/` — Streamlit 语义检索原型

- 独立的 Streamlit 应用，使用 CLAP + ChromaDB + Spotify
- [FinalReco/app.py](FinalReco/app.py) 入口，`services/` 下是各类服务
- 与主仓库的 `app/modules/recommendations/` 思路相同，但是独立运行
- 启动：`streamlit run FinalReco/app.py`
- **状态**：不在生产部署，可用于实验

### `Rec0/` — 更早的推荐原型

- 早期 Streamlit + Spotify 推荐系统，主要被 FinalReco 取代
- `ai_engine.py` + `spotify_client.py`
- **状态**：历史代码，可考虑归档

### `GrooveEngine/` — DJ 自动混音引擎

- 独立的 Python 项目，提供"输入歌单 → 输出 DJ 排序 + 过渡方案"的功能
- 关键模块：`analyzer/`、`core/`、`logic/`、`audio/`
- 入口：[GrooveEngine/main.py](GrooveEngine/main.py)（CLI）或 [GrooveEngine/web_app.py](GrooveEngine/web_app.py)（Web）
- ⚠️ `app/modules/playlists/groove_adapter.py` 已经把 GrooveEngine **嵌入到主服务**，主服务排歌时会调用这里的算法
- 如果要改 DJ 排序逻辑，主要改这里

### `SongFormer/` — 第三方音乐结构识别模型

- 来自 ASLP-lab 的开源项目，作为 git submodule 引入
- 用于自动识别歌曲段落（Verse / Chorus / Bridge）
- 目前主服务的 cue point 还没接入它，是潜在升级方向

### `scripts/`

各种调试/迁移/批处理脚本，命名以下划线开头。**生产无关**。

### `web/` `app/`

这两个才是当前线上服务，**其它子项目都不影响线上**。

---

## 12. 联系信息 & 快速求助

| 角色 | 联系人 |
|---|---|
| 上一任负责人 | ____（请填）____ |
| 阿里云账号 owner | ____（请填）____ |
| Tailscale 管理员 | ____（请填）____ |

### 紧急情况下页面打不开的快速排查路径

```bash
# 1. ECS 是否活
curl http://8.136.120.255/

# 2. Tailscale + Jetson 是否活
curl http://8.136.120.255/jetson/health

# 3. uvicorn 进程是否在
ssh mark@100.91.30.53 "ps aux | grep uvicorn"

# 4. 数据库是否在
ssh mark@100.91.30.53 "sudo systemctl status postgresql"

# 5. 看具体报错
tail /home/mark/harbeat/uvicorn.log
```

---

*文档结束*
