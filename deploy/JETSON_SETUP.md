# HarBeat — Jetson Orin NX 部署配置文档

## 一、硬件信息

- **设备**: NVIDIA Jetson Orin NX
- **架构**: ARM64 (aarch64)
- **GPU**: NVIDIA Ampere (CUDA 11.4+)
- **内存**: 8GB/16GB（共享 CPU/GPU）
- **存储**: 建议 >= 128GB NVMe SSD

## 二、项目概述

HarBeat 是一个 DJ 音乐管理平台，包含以下核心功能：

| 功能 | 技术栈 | 资源需求 |
|------|--------|----------|
| Web API | FastAPI + Uvicorn | CPU, 低内存 |
| 前端 | React + Vite (编译产物) | 仅静态文件 |
| 音频分析（BPM/Key/结构） | librosa + madmom (RNN) | CPU, ~1.5GB RAM |
| 音源分离（4轨） | Demucs v4 (htdemucs_ft) + PyTorch | **GPU 加速**, ~2GB VRAM |
| 语义搜索 | CLAP (laion/clap-htsat-unfused) + ChromaDB | **GPU 加速**, ~1.5GB 模型 |
| Spotify 匹配 | spotipy (Spotify Web API) | 网络 |
| 音乐下载 | fangpi.net / kuwo.cn | 网络 |
| 流媒体播放 | HTTP Range 流式传输 | 磁盘 IO |
| 缓存 | Redis 7 | 64MB RAM |
| 反向代理 | Nginx 1.27 | 64MB RAM |
| 数据库 | PostgreSQL (远程 Aliyun RDS) | 外部服务 |

## 三、系统基础环境

### 3.1 操作系统要求

```
JetPack 6.x (基于 Ubuntu 22.04)
CUDA >= 11.4 (JetPack 自带)
cuDNN >= 8.6 (JetPack 自带)
```

### 3.2 基础软件安装

```bash
# 更新系统
sudo apt-get update && sudo apt-get upgrade -y

# 安装基础工具
sudo apt-get install -y \
    git curl wget htop \
    build-essential cmake \
    libsndfile1 ffmpeg rubberband-cli \
    libblas-dev liblapack-dev libopenblas-dev gfortran \
    python3-pip python3-dev

# 安装 Docker（如果 JetPack 未预装）
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    sudo systemctl enable docker && sudo systemctl start docker
fi

# 验证 Docker + NVIDIA runtime
docker info | grep -i runtime
# 应看到 nvidia runtime
```

### 3.3 配置 NVIDIA Container Runtime

Jetson 需要 `nvidia-container-runtime` 让 Docker 容器访问 GPU：

```bash
# JetPack 6 通常已预装，验证：
dpkg -l | grep nvidia-container

# 如果没有：
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 验证 GPU 在 Docker 中可用：
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

设置默认 runtime 为 nvidia（在 `/etc/docker/daemon.json`）：

```json
{
    "default-runtime": "nvidia",
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "registry-mirrors": [
        "https://docker.1ms.run",
        "https://docker.m.daocloud.io"
    ]
}
```

```bash
sudo systemctl restart docker
```

## 四、Docker 容器架构

### 4.1 服务拓扑

```
┌─────────────────────────────────────────────────┐
│  Jetson Orin NX                                 │
│                                                 │
│  ┌──────────┐  ┌──────────────────────────────┐ │
│  │  Nginx   │──│  HarBeat API (FastAPI)       │ │
│  │  :80     │  │  :8000                       │ │
│  └──────────┘  │  ┌─────────────────────────┐ │ │
│                │  │ 子进程: 音频分析 (CPU)    │ │ │
│                │  │ 子进程: CLAP 嵌入 (GPU)  │ │ │
│                │  │ 子进程: Demucs 分离 (GPU) │ │ │
│                │  └─────────────────────────┘ │ │
│                └──────────────────────────────┘ │
│  ┌──────────┐                                   │
│  │  Redis   │  内存缓存 + 分析锁              │
│  │  :6379   │                                   │
│  └──────────┘                                   │
│                                                 │
│  ┌────────────────────────────────────────────┐ │
│  │  持久卷                                     │ │
│  │  /data/music-files/  ← 音频文件            │ │
│  │  /data/clap_model/   ← CLAP 模型 (~600MB) │ │
│  │  /data/chroma_db/    ← 向量索引            │ │
│  └────────────────────────────────────────────┘ │
│                    │                             │
│                    ▼ (远程连接)                   │
│   PostgreSQL @ Aliyun RDS                        │
│   pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com   │
└─────────────────────────────────────────────────┘
```

### 4.2 Jetson 专用 Dockerfile

创建 `Dockerfile.jetson`：

```dockerfile
# ---- Stage 1: Build web frontend ----
FROM node:20-slim AS web-builder
WORKDIR /web
RUN npm config set registry https://registry.npmmirror.com
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ .
RUN npm run build

# ---- Stage 2: Python API (Jetson ARM64 + CUDA) ----
# 使用 NVIDIA L4T PyTorch 基础镜像（预装 CUDA + PyTorch for Jetson）
FROM nvcr.io/nvidia/l4t-pytorch:r36.4.0-pth2.5-py3

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg rubberband-cli \
    libblas-dev liblapack-dev libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（torch 已在基础镜像中）
COPY requirements.jetson.txt .
RUN pip install --no-cache-dir --timeout 300 \
    -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    -r requirements.jetson.txt

# Optional: madmom (可能因编译问题跳过)
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    cython madmom 2>/dev/null || echo "madmom install failed, will use librosa fallback"

# 复制项目代码
COPY . .

# 复制前端构建产物
COPY --from=web-builder /web/dist /app/web/dist

# 创建数据目录
RUN mkdir -p /app/data/music-files /app/data/clap_model /app/data/chroma_db

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

### 4.3 Jetson 专用 requirements

创建 `requirements.jetson.txt`（去掉 torch/torchaudio，因基础镜像已包含）：

```
# === Backend (FastAPI) ===
fastapi==0.116.1
uvicorn[standard]==0.35.0
sqlalchemy==2.0.43
psycopg2-binary==2.9.11
redis==6.4.0
pydantic-settings==2.10.1
email-validator==2.2.0
PyJWT==2.9.0
python-multipart==0.0.20
httpx==0.28.1

# === Audio Analysis ===
librosa==0.10.2.post1
numpy<2
pyloudnorm
pedalboard
pyrubberband
soundfile==0.13.1

# === Stem Separation (demucs) ===
# torch/torchaudio 已在 l4t-pytorch 基础镜像中
sympy==1.13.1
networkx
filelock
jinja2
fsspec
demucs==4.0.1

# === NCM Decryption ===
pycryptodome==3.23.0

# === Semantic Search ===
chromadb>=0.5.0
transformers>=4.30.0

# === Spotify API ===
spotipy>=2.24.0
```

### 4.4 Jetson 专用 docker-compose

创建 `docker-compose.jetson.yml`：

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile.jetson
    container_name: harbeat-api
    restart: unless-stopped
    runtime: nvidia           # Jetson GPU 访问
    env_file:
      - .env
    ports:
      - "8000:8000"
    depends_on:
      - redis
    volumes:
      - music_data:/app/data/music-files
      - clap_model:/app/data/clap_model
      - chroma_data:/app/data/chroma_db
    deploy:
      resources:
        limits:
          memory: 6G          # Jetson 共享内存，给更多
        reservations:
          memory: 1G
    environment:
      - MALLOC_ARENA_MAX=2
      - PYTHONDONTWRITEBYTECODE=1
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility

  redis:
    image: redis:7
    container_name: harbeat-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
    deploy:
      resources:
        limits:
          memory: 128M
    command: redis-server --maxmemory 64mb --maxmemory-policy allkeys-lru

  nginx:
    image: nginx:1.27
    container_name: harbeat-nginx
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - app
    volumes:
      - ./deploy/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    deploy:
      resources:
        limits:
          memory: 64M

volumes:
  music_data:
  clap_model:
  chroma_data:
  redis_data:
```

## 五、环境变量配置

创建 `/opt/harbeat/.env`：

```bash
# === 应用 ===
APP_NAME=HarBeat DJ Platform
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000

# === 数据库（Aliyun RDS，确保 Jetson 能访问外网） ===
DATABASE_URL=postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism

# === Redis（容器内部） ===
REDIS_URL=redis://redis:6379/0

# === JWT ===
JWT_SECRET=<用 openssl rand -hex 32 生成>
JWT_ALGORITHM=HS256

# === Spotify API ===
SPOTIPY_CLIENT_ID=<你的 Spotify Client ID>
SPOTIPY_CLIENT_SECRET=<你的 Spotify Client Secret>
```

**注意**：Spotify 密钥不要提交到 git，只放在 `.env` 文件中。

## 六、CLAP 模型部署

CLAP 模型约 600MB，需要手动下载（服务器可能无法访问 HuggingFace）：

### 方案 A：本地下载后传到 Jetson

```bash
# 在能访问 HuggingFace 的电脑上
git lfs install
git clone https://huggingface.co/laion/clap-htsat-unfused /tmp/clap-model

# 传到 Jetson
scp -r /tmp/clap-model/* jetson:/opt/harbeat-clap/

# 在 Jetson 上复制到 Docker 卷
docker cp /opt/harbeat-clap/. harbeat-api:/app/data/clap_model/
```

### 方案 B：使用 HF Mirror

```bash
# 在 Jetson 上（如果能翻墙或用镜像）
export HF_ENDPOINT=https://hf-mirror.com
pip install huggingface_hub
huggingface-cli download laion/clap-htsat-unfused --local-dir /opt/harbeat-clap/
```

### 必需文件清单

```
clap_model/
├── config.json              # 模型配置
├── preprocessor_config.json # 预处理器配置
├── pytorch_model.bin        # 权重 (~587MB)
├── tokenizer.json           # 分词器
├── tokenizer_config.json    # 分词器配置
├── special_tokens_map.json  # 特殊 token
├── vocab.json               # 词表
└── merges.txt               # BPE 合并规则
```

## 七、GPU 加速改造点

Jetson 有 GPU，当前代码在这些地方用 CPU，可改为 GPU：

### 7.1 Demucs 音源分离

文件：`app/modules/music/audio_processor.py`

当前：`device="cpu"` 硬编码
改为：

```python
import torch
device = "cuda" if torch.cuda.is_available() else "cpu"
```

### 7.2 CLAP 语义嵌入

文件：`app/modules/recommendations/_run_clap_text.py` 和 `_run_clap_audio.py`

当前：默认 CPU
改为：

```python
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
```

### 7.3 内存管理（重要）

Jetson 的 CPU 和 GPU **共享内存**，必须控制总用量：

- PyTorch GPU 模型加载后，用完及时 `del model; torch.cuda.empty_cache()`
- 同时只运行一个重任务（已有 Redis 锁机制）
- docker-compose 内存限制设为 6GB（保留 2GB 给系统 + GPU driver）

## 八、网络配置

### 8.1 Jetson 局域网访问

如果 Jetson 在本地局域网：

```bash
# 查看 Jetson IP
ip addr show | grep inet

# 其他设备通过 http://<jetson-ip> 访问
```

### 8.2 外网穿透（可选）

如果需要从外网访问 Jetson：

**方案 A：FRP 内网穿透**
```bash
# 在 Jetson 上运行 frpc，连接到你的云服务器
# frpc.toml:
[harbeat]
type = tcp
local_ip = 127.0.0.1
local_port = 80
remote_port = 8080
```

**方案 B：Tailscale / ZeroTier VPN**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### 8.3 数据库连接

当前使用 Aliyun RDS PostgreSQL（外网地址）。确保：
- Jetson 能访问 `pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432`
- RDS 安全组/白名单中添加 Jetson 的公网 IP

如果未来想本地部署 PostgreSQL：

```yaml
# 在 docker-compose.jetson.yml 中添加：
  postgres:
    image: postgres:16
    container_name: harbeat-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: harbeat
      POSTGRES_PASSWORD: Hb12345678
      POSTGRES_DB: rhythm_prism
    volumes:
      - postgres_data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 256M

# volumes 中添加：
  postgres_data:

# .env 中改为：
# DATABASE_URL=postgresql+psycopg2://harbeat:Hb12345678@postgres:5432/rhythm_prism
```

## 九、部署步骤总结

```bash
# 1. 克隆项目
cd /opt
git clone https://github.com/jihaobi123/harbeat-client.git harbeat
cd harbeat

# 2. 配置环境变量
cp deploy/.env.example .env
# 编辑 .env，填入 JWT_SECRET 和 Spotify 密钥

# 3. 部署 CLAP 模型（从外部复制进来）
mkdir -p /opt/harbeat-clap
# ... 将模型文件放到 /opt/harbeat-clap/ ...

# 4. 构建并启动（使用 Jetson 专用配置）
docker compose -f docker-compose.jetson.yml up -d --build

# 5. 复制 CLAP 模型到容器卷
docker cp /opt/harbeat-clap/. harbeat-api:/app/data/clap_model/

# 6. 验证
docker compose -f docker-compose.jetson.yml ps
docker logs harbeat-api --tail 20
curl http://localhost/health
```

## 十、性能预估

| 任务 | 阿里云 ECS (4 vCPU x86) | Jetson Orin NX (GPU) |
|------|--------------------------|----------------------|
| API 响应 | ~50ms | ~50ms |
| 音频分析 (3min 歌) | ~30s | ~25s |
| Demucs 分离 | ~3-5min (CPU) | **~30-60s (GPU)** |
| CLAP 音频嵌入 | ~10s (CPU) | **~2-3s (GPU)** |
| CLAP 文本嵌入 | ~3s (CPU) | **~1s (GPU)** |
| Vibe Search (10首) | ~30s (CPU rerank) | **~10s (GPU rerank)** |

GPU 加速主要提升 Demucs 分离（5-10x）和 CLAP 嵌入（3-5x）。

## 十一、潜在问题与解决方案

| 问题 | 影响 | 解决方案 |
|------|------|----------|
| l4t-pytorch 基础镜像版本 | torch 版本需与 demucs 兼容 | 检查 demucs 4.0.1 支持的 torch 版本范围 |
| pedalboard ARM64 wheel | 可能没有预编译 wheel | `pip install pedalboard` 会自动编译，需要 Rust 工具链 |
| madmom 编译 | C 扩展可能失败 | 跳过即可，librosa 自动 fallback |
| psycopg2-binary ARM64 | 可能需要编译 | 改用 `psycopg2-binary` 或安装 `libpq-dev` |
| 共享内存不足 | GPU + CPU 争抢 | 一次只跑一个重任务（Redis 锁已实现） |
| HuggingFace 访问 | 中国网络限制 | 提前下载 CLAP 模型，手动复制 |
| Spotify API 访问 | 需要外网 | 确保 Jetson 能访问 api.spotify.com |
| 数据库延迟 | Aliyun RDS 在远端 | 考虑本地部署 PostgreSQL（见第八章） |

## 十二、未来扩展准备

### 12.1 本地大模型推理（LLM）

如果未来要跑本地 LLM（如 Llama）做智能歌曲推荐：
- Jetson Orin NX 16GB 可运行 7B 量化模型
- 使用 `llama.cpp` 或 `ollama` 的 Jetson 版本
- 预留 GPU 内存：优先级设为 LLM < CLAP < Demucs

### 12.2 实时音频处理

如果未来要做实时 DJ 混音/效果：
- Jetson 的低延迟 GPU 适合实时 DSP
- 需要 ALSA/PulseAudio 配置
- Docker 需挂载 `/dev/snd` 音频设备

### 12.3 多用户并发

当前单 worker 设计，如果需要多用户：
- uvicorn workers 增加到 2-4
- 注意 GPU 内存共享问题
- 考虑用 CUDA MPS (Multi-Process Service)
