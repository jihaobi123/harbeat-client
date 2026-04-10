# HarBeat — 街舞音乐曲库管理与分析平台

> FastAPI + React + TypeScript Web 前端 + Docker 部署

![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.3-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?logo=tailwindcss&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

---

## 功能概览

| 功能 | 说明 |
|------|------|
| 🎵 **本地音频导入** | 支持 MP3/AAC/M4A/WAV/FLAC/OGG/WMA/AIFF/APE/OPUS/NCM 等 ~20 种格式 |
| 🔐 **NCM 解密** | 自动识别并解密网易云 `.ncm` 加密文件 |
| 📊 **波形可视化** | Canvas 自绘波形条，支持点击/拖拽跳转 |
| ▶️ **音频播放** | 播放/暂停、快进/快退、音量调节 |
| 🔍 **在线搜索** | 接入 fangpi.net 平台，实时搜索歌曲 |
| ⬇️ **在线下载** | 一键下载在线歌曲到本地曲库 |
| 📈 **BPM / Key 分析** | FFmpeg 解码 → Spectral Flux → DP Beat Tracking → Krumhansl-Schmuckler 调性检测 |
| 🎯 **Cue Points** | 自动段落识别 + 手动标记/删除 Cue 点 |
| 🔁 **A-B Loop** | 标记 A/B 点循环播放片段 |
| 🎚️ **BPM Sync** | 调整播放速率匹配目标 BPM |
| 🎛️ **DJ Fade** | Fade In / Fade Out 渐入渐出 |
| 🎼 **声轨分离** | 基于 Demucs 的人声/鼓/贝斯/其他四轨分离 |
| 📋 **歌单管理** | 网易云/QQ音乐链接导入歌单，选曲 → 搜索 → 打标签 → 下载 |
| ➕ **歌单操作** | 新建歌单、右键添加歌曲到歌单、删除歌曲/歌单 |
| 💾 **持久化** | PostgreSQL 数据库 + 磁盘音频文件存储 |

---

## 环境要求

| 工具 | 最低版本 | 说明 |
|------|---------|------|
| **Python** | 3.10+ | 后端 API + 音频分析 + 声轨分离 |
| **Node.js** | 18+ | 前端构建 |
| **PostgreSQL** | 14+ | 数据存储（或使用 Docker） |
| **Redis** | 6+ | 缓存（可选） |
| **Docker** | 20+ | 一键部署（推荐） |

---

## 部署方式

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆仓库
git clone <repo-url>
cd harbeat-client

# 2. 创建环境变量文件
cat > .env << EOF
DATABASE_URL=postgresql+psycopg2://harbeat:Hb12345678@postgres:5432/rhythm_prism
REDIS_URL=redis://redis:6379/0
JWT_SECRET=your-production-secret-key-change-this
UPLOAD_DIR=/app/data/music-files
EOF

# 3. 一键启动
docker-compose up -d --build

# 4. 访问
# http://服务器IP        → Web 界面
# http://服务器IP/docs   → API 文档（Swagger UI）
```

**容器组成：**

| 容器 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `harbeat-api` | 自构建 (Python 3.12 + Node 20) | 8000 | FastAPI 后端 + Web 前端 |
| `harbeat-postgres` | postgres:16 | 5432 | PostgreSQL 数据库 |
| `harbeat-redis` | redis:7 | 6379 | Redis 缓存 |
| `harbeat-nginx` | nginx:1.27 | **80** | 反向代理入口 |

**Docker 数据持久化：**

| Volume | 路径 | 内容 |
|--------|------|------|
| `postgres_data` | /var/lib/postgresql/data | 数据库文件 |
| `music_data` | /app/data/music-files | 音频文件 |

```bash
# 常用运维命令
docker-compose logs -f app       # 查看后端日志
docker-compose restart app       # 重启后端
docker-compose down              # 停止所有服务
docker-compose down -v           # 停止并删除数据（慎用）
```

### 方式二：本地开发运行

```powershell
# 1. 创建 Python 虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. 安装前端依赖
cd web && npm install && cd ..

# 3. 配置 .env（可选，不配则使用默认远程数据库）
# 复制 .env.example 为 .env 并编辑

# 4. 启动后端（端口 8000）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5. 启动前端开发服务器（端口 5180）
cd web && npx vite --port 5180

# 6. 浏览器访问 http://localhost:5180
```

> **提示**：后端启动时会自动执行 `Base.metadata.create_all()` 建表，无需手动初始化数据库。

### 方式三：一键脚本（开发 + Electron 桌面端）

```powershell
.\start.ps1      # 自动检查环境、安装依赖、启动后端 + Electron
.\stop.ps1       # 停止所有服务
```

---

## 使用说明

> 必看文档：`docs/grooveengine-dj-roadmap.md`
>
> 该文档说明了本仓库内 `experimental/GrooveEngine` 当前对标真实 DJ 排歌/选歌能力的完成度、核心缺口与后续优先级，接手此方向前请先阅读。

### 1. 注册 & 登录
首次打开进入登录页 → 点击「注册」→ 输入用户名、密码，可选填舞种、水平、偏好风格 → 注册成功自动登录。

### 2. 上传音乐
在「我的音乐库」页面，点击上传按钮 → 选择音频文件（MP3/FLAC/WAV/NCM 等）→ 自动入库。`.ncm` 文件会自动解密。

### 3. 导入歌单
点击侧边栏 **「导入歌单」** → 粘贴网易云/QQ 音乐歌单链接 → 解析歌曲列表 → **勾选需要的歌曲** → 自动在 fangpi.net 搜索资源 → **打舞种标签** → 批量下载到曲库。

### 4. 在线搜索
切换到 **「在线搜索」** → 搜索歌曲 → 点击下载到本地曲库。

### 4. 音频分析
选中歌曲后在右侧详情页点击 **「分析」**，自动检测：
- **BPM** — 节拍速度
- **Key** — 调性 + Camelot 编号
- **Beat Points** — 逐拍时间戳
- **Cue Points** — 段落标记（可手动添加/删除）

### 5. DJ 工具
- **A-B Loop** — 标记循环片段
- **BPM Sync** — 调整播放速率匹配目标 BPM
- **DJ Fade** — 渐入/渐出

### 6. 声轨分离
分析面板中点击 **「Separate Stems」**，使用 Demucs 分离为人声/鼓/贝斯/其他四轨。
首次使用会下载 htdemucs 模型 (~80MB)，CPU 模式下处理一首歌约需几分钟。

### 7. 歌单管理
- **新建歌单**：侧边栏歌单区域点击 **「+」** 按钮 → 输入名称 → 回车创建
- **添加歌曲**：在曲库中右键歌曲 → 选择目标歌单，或点击行尾的 **「+」** 按钮
- **删除歌曲**：右键歌曲 → 点击「🗑 删除歌曲」（会同时删除磁盘文件，不可恢复）
- **删除歌单**：鼠标悬停歌单名称 → 点击 **「×」**

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                    用户浏览器 (React SPA)                     │
│  ┌──────────┐ ┌──────────┐ ┌────────────────────────────┐   │
│  │ Sidebar   │ │ SongList │ │ SongDetail                 │   │
│  │ (导航/歌单)│ │ (曲库列表)│ │ ├ WaveformPlayer (波形/Cue) │   │
│  │           │ │          │ │ ├ AnalysisPanel (BPM/Key)  │   │
│  │           │ │          │ │ └ StemPlayer (四轨分离)      │   │
│  └──────────┘ └──────────┘ └────────────────────────────┘   │
│  Zustand 状态管理  │  TailwindCSS 样式  │  Vite 构建          │
├─────────────────────────────────────────────────────────────┤
│                    Nginx 反向代理 (:80)                       │
├─────────────────────────────────────────────────────────────┤
│                  FastAPI 后端 (:8000)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Auth     │ │ Library  │ │ Playlists│ │ Fangpi       │   │
│  │ 注册/登录 │ │ 曲库CRUD │ │ 歌单管理  │ │ 搜索/下载    │   │
│  ├──────────┤ ├──────────┤ ├──────────┤ ├──────────────┤   │
│  │ Users    │ │ Music    │ │ Sessions │ │ Profiles     │   │
│  │ 用户管理  │ │ 音频分析  │ │ 练舞会话  │ │ 音乐画像    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  PostgreSQL (数据持久化)  │  Redis (缓存)  │  磁盘 (音频文件)  │
└─────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
harbeat-client/
├── docker-compose.yml       # Docker 编排（app + postgres + redis + nginx）
├── Dockerfile               # 两阶段构建（Node 构建前端 → Python 运行后端）
├── requirements.txt         # Python 依赖
├── start.ps1 / stop.ps1     # 本地开发一键启停脚本
├── deploy/
│   └── nginx.conf           # Nginx 反代配置
│
├── app/                     # FastAPI 后端
│   ├── main.py              # 应用入口（CORS、静态文件挂载、自动建表）
│   ├── shared/              # 公共模块
│   │   ├── config.py        # 配置（数据库URL、JWT密钥、上传目录等）
│   │   ├── database.py      # SQLAlchemy 引擎 + Session
│   │   └── responses.py     # 统一响应格式
│   └── modules/             # 业务模块（每个模块含 router/service/models/schemas）
│       ├── auth/            # 注册、登录、JWT 认证
│       ├── users/           # 用户 CRUD
│       ├── library/         # 曲库管理（上传、删除、分析、Stem 分离）
│       ├── playlists/       # 歌单（导入、创建、添加歌曲、标签）
│       ├── fangpi/          # fangpi.net 搜索、下载、歌单解析
│       ├── music/           # 音频分析（BPM、Key、Beat Points）
│       ├── sessions/        # 练舞会话
│       ├── profiles/        # 音乐画像
│       ├── recommendations/ # 智能推荐
│       └── health/          # 健康检查
│
├── web/                     # React 前端（Vite 构建）
│   ├── src/
│   │   ├── App.tsx          # 根组件（三栏布局）
│   │   ├── components/      # UI 组件
│   │   │   ├── Sidebar.tsx            # 导航 + 歌单列表 + 新建歌单
│   │   │   ├── SongList.tsx           # 曲库列表 + 右键菜单（添加/删除）
│   │   │   ├── SongDetail.tsx         # 歌曲详情
│   │   │   ├── WaveformPlayer.tsx     # 波形 + Cue + A-B Loop + BPM Sync
│   │   │   ├── AnalysisPanel.tsx      # 分析面板 + 声轨分离
│   │   │   ├── PlaylistImportModal.tsx # 歌单导入（6步流程）
│   │   │   ├── PlatformSearch.tsx     # 在线搜索
│   │   │   └── LoginPage.tsx          # 登录/注册
│   │   ├── api/client.ts    # API 请求封装
│   │   ├── store/           # Zustand 状态管理
│   │   ├── types/           # TypeScript 类型定义
│   │   └── styles/          # TailwindCSS 样式
│   └── dist/                # 构建产物（自动生成）
│
├── data/                    # 运行时数据（gitignore）
│   ├── music-files/         # 上传和下载的音频文件
│   └── stems/               # 声轨分离输出
│
└── electron/                # Electron 桌面端（可选）
    ├── main.ts              # 窗口管理
    └── preload.ts           # contextBridge API
```

---

## 数据存储

| 数据类型 | 存储位置 | 说明 |
|---------|---------|------|
| **用户账号** | PostgreSQL `users` 表 | 用户名、bcrypt 加密密码、舞种、水平、偏好风格 |
| **曲库元数据** | PostgreSQL `library_songs` 表 | 标题、艺术家、BPM、Key、Camelot、能量值、分析状态、节拍时间戳、Cue Points |
| **歌单** | PostgreSQL `playlists` + `playlist_songs` 表 | 歌单名称、来源、歌曲关联、顺序、舞种标签 |
| **音频文件** | 磁盘 `./data/music-files/` | 上传和下载的原始音频文件 |
| **Stems 文件** | 磁盘 `./data/stems/` | Demucs 分离后的人声/鼓/贝斯/其他四轨 |
| **JWT Token** | 浏览器内存（localStorage） | 登录后签发，7 天有效期 |

### 环境变量配置（`.env`）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DATABASE_URL` | `postgresql+psycopg2://harbeat:...@aliyun-rds/rhythm_prism` | PostgreSQL 连接串 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `JWT_SECRET` | `change-me` | **生产环境必须修改** |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `10080`（7天） | Token 有效期 |
| `UPLOAD_DIR` | `./data/music-files` | 音频上传目录 |

---

## API 概览

所有 API 文档可在 `/docs`（Swagger UI）或 `/redoc` 查看。

| 模块 | 前缀 | 主要端点 |
|------|------|---------|
| **Auth** | `/api/auth` | `POST /register` `POST /login` `GET /me` |
| **Library** | `/api/library` | `GET /songs` `POST /upload` `DELETE /songs/{id}` `POST /songs/{id}/analyze` `POST /songs/{id}/separate-stems` |
| **Playlists** | `/api/playlists` | `POST /create` `POST /import` `GET /` `POST /{id}/add-songs` `DELETE /{id}` |
| **Fangpi** | `/api/fangpi` | `POST /search` `POST /batch-search` `POST /download` `POST /parse-playlist` |
| **Music** | `/api/music` | 音频分析相关 |
| **Sessions** | `/api/sessions` | 练舞会话管理 |
| **Profiles** | `/api/profiles` | 音乐画像 |
| **Recommendations** | `/api/recommendations` | 智能推荐 |

---

## 安全设计

- **密码加密**：bcrypt 哈希存储，不保存明文
- **JWT 认证**：HS256 签名，7 天有效期
- **权限校验**：删除歌曲/歌单时校验 `user_id` 所有权
- **文件清理**：删除歌曲时同时清理磁盘音频文件和 stems
- **CORS**：开发模式允许所有来源，生产环境建议限制
- **上传限制**：Nginx 限制 `client_max_body_size 200m`
- **无 Referer**: 下载请求不携带 Referer 头，避免 CDN 拒绝

---

## 许可

MIT
