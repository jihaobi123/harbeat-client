# HarBeat — DJ 音频曲库管理与分析工具

> Electron + React + TypeScript 桌面端 + FastAPI 后端

![Electron](https://img.shields.io/badge/Electron-28-47848F?logo=electron&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.3-3178C6?logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?logo=tailwindcss&logoColor=white)

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
| 📋 **歌单管理** | 链接导入歌单（网易云等）、添加到曲库 |
| 💾 **持久化** | 本地 JSON 数据库 + PostgreSQL 后端 |

---

## 环境要求

| 工具 | 最低版本 | 说明 |
|------|---------|------|
| **Python** | 3.10+ | 后端 + 声轨分离 |
| **Node.js** | 18+ | 前端 + Electron |
| **npm** | 9+ | 包管理 |
| **Git** | 任意 | 克隆仓库 |

> 仅需安装 Python 和 Node.js，其余依赖由脚本自动安装。

---

## 一键启动

```powershell
# 1. 克隆仓库
git clone <repo-url>
cd harbeat-client

# 2. 一键启动（首次会自动安装所有依赖）
.\start.ps1

# 3. 停止所有服务
.\stop.ps1
```

### `start.ps1` 做了什么？

| 步骤 | 说明 |
|------|------|
| ① 检查环境 | 确认 Python、Node.js 已安装 |
| ② 配置 .env | 从 `.env.example` 自动创建 |
| ③ Python 虚拟环境 | 自动创建 `.venv/`，安装 FastAPI、demucs、PyTorch 等 |
| ④ Node 依赖 | 自动运行 `npm install` |
| ⑤ 启动后端 | FastAPI on http://localhost:8000 |
| ⑥ 启动前端 | Electron 桌面窗口自动弹出 |

> 首次运行需要下载 PyTorch (~200MB) 和 npm 包，请确保网络畅通。
> 国内用户 Electron 下载慢时，脚本已自动设置 npmmirror 镜像。

---

## 使用说明

### 1. 导入本地音频
点击侧边栏 **「导入音频」** → 选择音频文件 → 自动出现在曲库中。支持 `.ncm` 自动解密。

### 2. 链接导入歌单
点击侧边栏 **「导入歌单」** → 粘贴网易云歌单链接 → 解析后一键导入 → 自动搜索并下载全部歌曲。

### 3. 搜索与下载
切换到 **「平台曲库」** → 搜索歌曲 → 点击 ⬇️ 下载到本地曲库。

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

### 7. 添加到曲库
在歌单视图中，点击歌曲右侧 📚 按钮可将歌曲添加到主曲库，歌单删除后歌曲仍保留。

---

## 技术架构

```
┌────────────────────────────────────────────────────────────┐
│                     Electron Main Process                   │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ File Dialog  │ │ HTTP Audio   │ │ FFmpeg Audio         │ │
│  │ IPC Handlers │ │ Server       │ │ Analyzer (DSP/BPM/   │ │
│  │ NCM Decrypt  │ │ (127.0.0.1)  │ │ Key Detection)       │ │
│  └─────────────┘ └──────────────┘ └──────────────────────┘ │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ fangpi.net  │ │ Platform     │ │ Demucs Stem          │ │
│  │ Search & DL │ │ Library JSON │ │ Separation (.venv)   │ │
│  └─────────────┘ └──────────────┘ └──────────────────────┘ │
├────────────────────────────────────────────────────────────┤
│                 contextBridge (Preload)                      │
├────────────────────────────────────────────────────────────┤
│                   Renderer (React + Zustand)                │
│  ┌──────────┐ ┌──────────┐ ┌────────────────────────────┐  │
│  │ Sidebar   │ │ SongList │ │ SongDetail                 │  │
│  │ (Nav)     │ │ (List)   │ │ ├ WaveformPlayer (A-B/Cue) │  │
│  │           │ │          │ │ ├ AnalysisPanel (BPM/Key)  │  │
│  │           │ │          │ │ └ StemPlayer (4-track)      │  │
│  └──────────┘ └──────────┘ └────────────────────────────┘  │
├────────────────────────────────────────────────────────────┤
│               FastAPI Backend (port 8000)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────┐    │
│  │ Users API │ │Playlists │ │ PostgreSQL (Aliyun RDS)  │    │
│  └──────────┘ └──────────┘ └──────────────────────────┘    │
└────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
harbeat-client/
├── start.ps1                # 一键启动脚本（配置环境 + 启动服务）
├── stop.ps1                 # 一键停止脚本
├── requirements.txt         # Python 依赖（FastAPI + demucs + torch）
├── package.json             # Node.js 依赖
├── .env.example             # 环境变量模板
│
├── app/                     # FastAPI 后端
│   ├── main.py              # 应用入口 + CORS + 异常处理
│   ├── shared/              # 数据库连接、配置、响应格式
│   └── modules/             # 业务模块
│       ├── users/           # 用户 CRUD
│       └── playlists/       # 歌单导入、管理
│
├── electron/                # Electron 主进程
│   ├── main.ts              # 窗口管理、IPC handlers、音频服务
│   ├── preload.ts           # contextBridge API
│   ├── audioAnalyzer.ts     # BPM/Key/Beat/Cue 分析 (FFmpeg + DSP)
│   ├── fangpiService.ts     # fangpi.net 搜索与下载
│   ├── ncmDecrypt.ts        # 网易云 NCM 解密
│   ├── platformLibrary.ts   # 本地 JSON 曲库
│   ├── playlistParser.ts    # 歌单链接解析
│   └── playlistStore.ts     # 歌单本地存储
│
├── src/                     # React 前端
│   ├── App.tsx              # 根组件（三栏布局）
│   ├── components/          # UI 组件
│   │   ├── Sidebar.tsx      # 导航 + 导入
│   │   ├── SongList.tsx     # 歌曲列表
│   │   ├── SongDetail.tsx   # 歌曲详情
│   │   ├── WaveformPlayer.tsx # 波形 + Cue + A-B Loop + BPM Sync + Fade
│   │   ├── AnalysisPanel.tsx  # 分析面板 + 声轨分离
│   │   └── PlaylistImportModal.tsx # 歌单导入弹窗
│   ├── store/               # Zustand 状态管理
│   ├── services/            # API 调用层
│   └── types/               # TypeScript 类型
│
├── database/                # 运行时数据（gitignore）
│   ├── platform-library.json
│   ├── music-files/
│   └── stems/
│
├── vite.config.ts
├── tsconfig.json
└── tailwind.config.js
```

---

## 安全设计

- **contextIsolation**: 渲染进程与 Node.js 完全隔离
- **allowedPaths**: 只有用户选择或下载的文件才能被 HTTP 服务访问
- **CSP**: Content-Security-Policy 限制资源来源
- **本地回环**: 音频 HTTP 服务仅监听 `127.0.0.1`
- **无 Referer**: 下载请求不携带 Referer 头，避免 CDN 拒绝

---

## 许可

MIT
