# HarBeat 服务器迁移指南

## 从阿里云 (x86) → Jetson Orin (ARM64)

---

## 一、迁移概览

### 1.1 源服务器（阿里云）

| 项目 | 值 |
|------|-----|
| IP | `8.136.120.255` |
| 用户 | `root` |
| 密码 | `Harbeat.1` |
| 架构 | x86_64 |
| 内存 | 7.1 GB |
| Docker Compose | `docker-compose.yml` |
| Dockerfile | `Dockerfile` |

### 1.2 目标服务器（Jetson Orin）

| 项目 | 值 |
|------|-----|
| 架构 | ARM64 (aarch64) |
| GPU | NVIDIA Ampere (CUDA 11.4+) |
| 基础镜像 | `nvcr.io/nvidia/l4t-pytorch:r36.4.0-pth2.5-py3` |
| Docker Compose | `docker-compose.jetson.yml` |
| Dockerfile | `Dockerfile.jetson` |
| Requirements | `requirements.jetson.txt` |

### 1.3 已打包数据（在阿里云 `/root/` 下）

| 文件 | 大小 | 内容 |
|------|------|------|
| `/root/music-files.tar.gz` | **4.4 GB** | 所有歌曲 mp3 + demucs stems wav |
| `/root/clap_model.tar.gz` | **538 MB** | CLAP 语音语义模型 (laion/clap-htsat-unfused) |
| `/root/chroma_onnx.tar.gz` | **159 MB** | ChromaDB ONNX 向量模型 (all-MiniLM-L6-v2) |
| `/root/chroma_db.tar.gz` | **257 KB** | ChromaDB 向量数据库 |
| `/root/harbeat.env` | **203 B** | 环境变量配置 |
| **总计** | **~5.1 GB** | |

### 1.4 无需迁移的部分

| 项目 | 原因 |
|------|------|
| PostgreSQL 数据库 | 存储在阿里云 RDS 远程，Jetson 直接连接即可 |
| Redis 数据 | 仅用于分析锁，无持久化数据 |
| 代码 | Git 仓库，直接 clone |

---

## 二、Jetson 基础环境配置

### 2.1 系统要求

```
JetPack 6.x (基于 Ubuntu 22.04)
CUDA >= 11.4 (JetPack 自带)
cuDNN >= 8.6 (JetPack 自带)
存储 >= 128GB（推荐 NVMe SSD）
```

### 2.2 验证 JetPack 版本

```bash
# 查看 JetPack 和系统信息
jetson_release
# 或
cat /etc/nv_tegra_release
```

### 2.3 安装基础工具

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
    git curl wget htop \
    build-essential cmake \
    libsndfile1 ffmpeg rubberband-cli \
    libblas-dev liblapack-dev libopenblas-dev gfortran \
    python3-pip python3-dev
```

### 2.4 安装 Docker（如果未预装）

```bash
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    sudo systemctl enable docker && sudo systemctl start docker
fi
```

### 2.5 配置 NVIDIA Container Runtime

```bash
# 验证是否已安装
dpkg -l | grep nvidia-container

# 如果没有，安装：
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 验证 GPU 在 Docker 中可用：
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

### 2.6 设置 Docker daemon 配置

编辑 `/etc/docker/daemon.json`：

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

---

## 三、从阿里云传输数据到 Jetson

### 3.1 方法 A：Jetson 直接从阿里云拉取（推荐）

在 Jetson 上执行：

```bash
# 创建临时目录
mkdir -p ~/harbeat-migration
cd ~/harbeat-migration

# 下载所有打包文件（密码 Harbeat.1）
scp root@8.136.120.255:/root/music-files.tar.gz ./
scp root@8.136.120.255:/root/clap_model.tar.gz ./
scp root@8.136.120.255:/root/chroma_onnx.tar.gz ./
scp root@8.136.120.255:/root/chroma_db.tar.gz ./
scp root@8.136.120.255:/root/harbeat.env ./

# 验证文件完整性
ls -lh ~/harbeat-migration/
# 预期：
# music-files.tar.gz   4.4G
# clap_model.tar.gz    538M
# chroma_onnx.tar.gz   159M
# chroma_db.tar.gz     257K
# harbeat.env          203B
```

### 3.2 方法 B：通过本地电脑中转

如果 Jetson 无法直接 SSH 到阿里云：

```powershell
# 在 Windows 电脑上，先从阿里云下载
scp root@8.136.120.255:/root/music-files.tar.gz D:\work\harbeat-migration\
scp root@8.136.120.255:/root/clap_model.tar.gz D:\work\harbeat-migration\
scp root@8.136.120.255:/root/chroma_onnx.tar.gz D:\work\harbeat-migration\
scp root@8.136.120.255:/root/chroma_db.tar.gz D:\work\harbeat-migration\
scp root@8.136.120.255:/root/harbeat.env D:\work\harbeat-migration\

# 再从电脑传到 Jetson
scp D:\work\harbeat-migration\* <jetson-user>@<jetson-ip>:~/harbeat-migration/
```

---

## 四、部署到 Jetson

### 4.1 拉取代码

```bash
cd /opt
sudo git clone https://github.com/jihaobi123/harbeat-client.git harbeat
cd harbeat
git checkout feature/superpowered-player
```

### 4.2 配置环境变量

```bash
# 方式 1：使用迁移过来的 .env
cp ~/harbeat-migration/harbeat.env /opt/harbeat/.env

# 方式 2：手动创建（如需修改密钥）
cat > /opt/harbeat/.env << 'EOF'
APP_ENV=production
JWT_SECRET=hb-prod-secret-2026-xyw-dj-platform
REDIS_URL=redis://redis:6379/0
SPOTIPY_CLIENT_ID=ea17a2d5e2b24926ae4a80adadd73435
SPOTIPY_CLIENT_SECRET=7ebce881d23248518566c2bdd1f7835a
EOF
```

> **注意**：更换 `JWT_SECRET` 会导致所有旧 token 失效，用户需重新登录。

### 4.3 构建并启动容器

```bash
cd /opt/harbeat

# 使用 Jetson 专用配置构建（首次需要拉取 l4t-pytorch 镜像 ~6GB）
docker compose -f docker-compose.jetson.yml up -d --build
```

**构建时间预估**：
- 拉取 `nvcr.io/nvidia/l4t-pytorch:r36.4.0-pth2.5-py3`：~10-30 分钟（取决于网速）
- pip install 依赖：~5-10 分钟
- 前端构建：~2-3 分钟

**如果拉取 NGC 镜像很慢**，可配置代理或提前手动拉取：
```bash
docker pull nvcr.io/nvidia/l4t-pytorch:r36.4.0-pth2.5-py3
```

### 4.4 验证容器启动

```bash
# 检查容器状态
docker compose -f docker-compose.jetson.yml ps

# 预期输出：3 个容器都是 Up 状态
# harbeat-api     Up
# harbeat-redis   Up
# harbeat-nginx   Up

# 检查日志
docker logs harbeat-api --tail 20
```

---

## 五、还原数据

### 5.1 还原音乐文件 + Stems

```bash
# 复制到容器
docker cp ~/harbeat-migration/music-files.tar.gz harbeat-api:/tmp/

# 解压到 /app/data/（覆盖默认空目录）
docker exec harbeat-api tar xzf /tmp/music-files.tar.gz -C /app/data

# 清理临时文件
docker exec harbeat-api rm /tmp/music-files.tar.gz

# 验证
docker exec harbeat-api ls /app/data/music-files/shared/ | head -5
docker exec harbeat-api ls /app/data/music-files/stems/htdemucs/ | head -5
```

### 5.2 还原 CLAP 模型

```bash
docker cp ~/harbeat-migration/clap_model.tar.gz harbeat-api:/tmp/
docker exec harbeat-api tar xzf /tmp/clap_model.tar.gz -C /app/data
docker exec harbeat-api rm /tmp/clap_model.tar.gz

# 验证（应包含 config.json, pytorch_model.bin 等文件）
docker exec harbeat-api ls -lh /app/data/clap_model/
```

预期文件清单：
```
clap_model/
├── config.json              (5.6 KB)
├── merges.txt               (506 KB)
├── preprocessor_config.json (563 B)
├── pytorch_model.bin        (587 MB)   ← 模型权重
├── special_tokens_map.json  (295 B)
├── tokenizer.json           (2.2 MB)
├── tokenizer_config.json    (400 B)
└── vocab.json               (798 KB)
```

### 5.3 还原 ChromaDB 向量数据库

```bash
docker cp ~/harbeat-migration/chroma_db.tar.gz harbeat-api:/tmp/
docker exec harbeat-api tar xzf /tmp/chroma_db.tar.gz -C /app/data
docker exec harbeat-api rm /tmp/chroma_db.tar.gz

# 验证
docker exec harbeat-api ls -lh /app/data/chroma_db/
```

### 5.4 还原 ChromaDB ONNX 模型

```bash
docker cp ~/harbeat-migration/chroma_onnx.tar.gz harbeat-api:/tmp/
docker exec harbeat-api mkdir -p /root/.cache/chroma
docker exec harbeat-api tar xzf /tmp/chroma_onnx.tar.gz -C /root/.cache/chroma
docker exec harbeat-api rm /tmp/chroma_onnx.tar.gz

# 验证
docker exec harbeat-api ls /root/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/
```

### 5.5 重启容器使所有数据生效

```bash
cd /opt/harbeat
docker compose -f docker-compose.jetson.yml restart
```

---

## 六、数据库连接配置

### 6.1 当前数据库

| 项目 | 值 |
|------|-----|
| 类型 | PostgreSQL (阿里云 RDS) |
| 地址 | `pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com` |
| 端口 | `5432` |
| 用户 | `harbeat` |
| 密码 | `Hb12345678` |
| 数据库名 | `rhythm_prism` |
| 连接串 | `postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism` |

### 6.2 添加 RDS 白名单（必须）

1. 登录阿里云控制台：https://rdsnext.console.aliyun.com/
2. 找到实例 `pgm-wz99am1godb1u59s3o`
3. 左侧菜单 → **数据安全性** → **白名单设置**
4. 添加 Jetson 的**公网 IP** 到白名单

获取 Jetson 公网 IP：
```bash
curl -s ifconfig.me
```

### 6.3 验证数据库连通性

```bash
# 在 Jetson 上测试（需要安装 postgresql-client）
sudo apt-get install -y postgresql-client
psql "postgresql://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism" -c "SELECT count(*) FROM library_songs;"
```

### 6.4 （可选）本地部署 PostgreSQL

如果不想依赖远程 RDS，可以在 Jetson 本地跑 PostgreSQL。

#### 6.4.1 修改 docker-compose.jetson.yml

在 `services:` 下添加：

```yaml
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
```

在 `volumes:` 下添加：
```yaml
  postgres_data:
```

#### 6.4.2 修改 .env

```bash
# 注释掉远程 RDS 行，添加本地连接：
# DATABASE_URL=postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism
DATABASE_URL=postgresql+psycopg2://harbeat:Hb12345678@postgres:5432/rhythm_prism
```

#### 6.4.3 导出远程数据 → 导入本地

```bash
# 在能连接 RDS 的机器上导出
pg_dump "postgresql://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism" > /tmp/harbeat_dump.sql

# 传到 Jetson
scp /tmp/harbeat_dump.sql <jetson-user>@<jetson-ip>:~/

# 在 Jetson 上导入
docker exec -i harbeat-postgres psql -U harbeat -d rhythm_prism < ~/harbeat_dump.sql
```

---

## 七、最终验证

### 7.1 健康检查

```bash
# API 健康
curl http://localhost/api/health

# 歌曲列表
curl -s http://localhost/api/library/songs | python3 -m json.tool | head -30

# Vibe 搜索
curl -s -X POST http://localhost/api/recommendations/vibe-search \
  -H 'Content-Type: application/json' \
  -d '{"query": "chill hip hop vibes", "top_k": 3}' | python3 -m json.tool
```

### 7.2 内存和 GPU 检查

```bash
# 容器内存
docker stats --no-stream

# GPU 使用
tegrastats  # Jetson 专用
# 或
docker exec harbeat-api python3 -c "import torch; print('CUDA:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
```

### 7.3 前端访问

浏览器打开：`http://<jetson-ip>`

---

## 八、Jetson vs 阿里云 对比

| 项目 | 阿里云 (x86) | Jetson Orin (ARM64) |
|------|-------------|---------------------|
| Dockerfile | `Dockerfile` | `Dockerfile.jetson` |
| Compose 文件 | `docker-compose.yml` | `docker-compose.jetson.yml` |
| 基础镜像 | `python:3.12-slim` | `nvcr.io/nvidia/l4t-pytorch:r36.4.0-pth2.5-py3` |
| Requirements | `requirements.txt` | `requirements.jetson.txt` |
| GPU | 无 | CUDA 加速 (demucs / CLAP) |
| 内存模型 | CPU 独立 RAM | **CPU/GPU 共享内存** |
| demucs 速度 | ~60-350s/首 (CPU) | **~15-60s/首 (GPU)** |
| CLAP 推理 | ~20s (CPU) | **~5s (GPU)** |
| 容器内存限制 | 5 GB | 6 GB |

---

## 九、故障排除

### 9.1 容器启动失败

```bash
# 查看详细日志
docker logs harbeat-api

# 常见原因：
# - 数据库连不上 → 检查 RDS 白名单
# - NVIDIA runtime 未配置 → 检查 daemon.json
# - 镜像拉取失败 → 配置 Docker 镜像加速器
```

### 9.2 数据库连接超时

```bash
# 测试网络连通性
telnet pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com 5432

# 如果不通：
# 1. 检查 RDS 白名单是否添加了 Jetson 公网 IP
# 2. 检查 Jetson 防火墙是否放行出站 5432
```

### 9.3 GPU 不可用

```bash
# 检查 NVIDIA runtime
docker info | grep -i runtime

# 测试 GPU
docker run --rm --runtime=nvidia nvcr.io/nvidia/l4t-pytorch:r36.4.0-pth2.5-py3 \
    python3 -c "import torch; print(torch.cuda.is_available())"

# 如果返回 False：
# 1. 确认 JetPack 版本正确
# 2. 确认 daemon.json 中 default-runtime 为 nvidia
# 3. sudo systemctl restart docker
```

### 9.4 内存不足 (OOM)

```bash
# Jetson 内存 CPU/GPU 共享，注意总用量
free -h
tegrastats

# 如果 OOM：
# 1. 减少 docker-compose 中 memory limit
# 2. 不要同时运行其他 GPU 程序
# 3. demucs 已配置 --segment 4 减少峰值内存
```

---

## 十、迁移后清理

### 10.1 清理 Jetson 上的临时文件

```bash
rm -rf ~/harbeat-migration/
```

### 10.2 清理阿里云上的打包文件

```bash
ssh root@8.136.120.255 "rm -f /root/music-files.tar.gz /root/clap_model.tar.gz /root/chroma_db.tar.gz /root/chroma_onnx.tar.gz /root/harbeat.env"
```

### 10.3 停止阿里云服务（确认 Jetson 运行正常后）

```bash
ssh root@8.136.120.255 "cd /root/harbeat-client && docker compose down"
```

---

## 附录：完整命令一键脚本

### A. Jetson 端一键部署脚本

```bash
#!/bin/bash
# deploy_jetson.sh — 在 Jetson 上运行

set -e
ALIYUN_IP="8.136.120.255"
ALIYUN_USER="root"
HARBEAT_DIR="/opt/harbeat"

echo "=== Step 1: Download data from Aliyun ==="
mkdir -p ~/harbeat-migration && cd ~/harbeat-migration
for f in music-files.tar.gz clap_model.tar.gz chroma_onnx.tar.gz chroma_db.tar.gz harbeat.env; do
    echo "Downloading $f..."
    scp ${ALIYUN_USER}@${ALIYUN_IP}:/root/$f ./
done

echo "=== Step 2: Clone and configure ==="
sudo git clone https://github.com/jihaobi123/harbeat-client.git ${HARBEAT_DIR} 2>/dev/null || true
cd ${HARBEAT_DIR}
git checkout feature/superpowered-player
cp ~/harbeat-migration/harbeat.env ${HARBEAT_DIR}/.env

echo "=== Step 3: Build containers ==="
docker compose -f docker-compose.jetson.yml up -d --build

echo "=== Step 4: Restore data ==="
echo "Restoring music files..."
docker cp ~/harbeat-migration/music-files.tar.gz harbeat-api:/tmp/
docker exec harbeat-api tar xzf /tmp/music-files.tar.gz -C /app/data
docker exec harbeat-api rm /tmp/music-files.tar.gz

echo "Restoring CLAP model..."
docker cp ~/harbeat-migration/clap_model.tar.gz harbeat-api:/tmp/
docker exec harbeat-api tar xzf /tmp/clap_model.tar.gz -C /app/data
docker exec harbeat-api rm /tmp/clap_model.tar.gz

echo "Restoring ChromaDB..."
docker cp ~/harbeat-migration/chroma_db.tar.gz harbeat-api:/tmp/
docker exec harbeat-api tar xzf /tmp/chroma_db.tar.gz -C /app/data
docker exec harbeat-api rm /tmp/chroma_db.tar.gz

echo "Restoring ONNX model..."
docker cp ~/harbeat-migration/chroma_onnx.tar.gz harbeat-api:/tmp/
docker exec harbeat-api mkdir -p /root/.cache/chroma
docker exec harbeat-api tar xzf /tmp/chroma_onnx.tar.gz -C /root/.cache/chroma
docker exec harbeat-api rm /tmp/chroma_onnx.tar.gz

echo "=== Step 5: Restart ==="
docker compose -f docker-compose.jetson.yml restart

echo "=== Step 6: Verify ==="
sleep 5
curl -s http://localhost/api/health && echo " ✓ API OK" || echo " ✗ API FAILED"
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"

echo ""
echo "=== Migration Complete ==="
echo "Remember: Add Jetson public IP to Aliyun RDS whitelist!"
echo "  RDS Console: https://rdsnext.console.aliyun.com/"
echo "  Instance: pgm-wz99am1godb1u59s3o"
echo "  Jetson Public IP: $(curl -s ifconfig.me)"
```

使用方式：
```bash
chmod +x deploy_jetson.sh
./deploy_jetson.sh
```
