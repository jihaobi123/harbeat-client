# AudioLab — 音频导入解析与平台内曲库搜索

> Electron + React + TypeScript 桌面端音频曲库管理与分析工具

![Electron](https://img.shields.io/badge/Electron-28-47848F?logo=electron&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.3-3178C6?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?logo=tailwindcss&logoColor=white)

---

## 功能概览

| 功能 | 说明 |
|------|------|
| 🎵 **本地音频导入** | 支持 MP3/AAC/M4A/WAV/FLAC/OGG/WMA/AIFF/APE/OPUS 等 ~20 种格式 |
| 🔐 **NCM 解密** | 自动识别并解密网易云 `.ncm` 加密文件 |
| 📊 **波形可视化** | Canvas 自绘波形条，支持点击/拖拽跳转播放位置 |
| ▶️ **音频播放** | 播放/暂停、快进/快退 5 秒、音量调节、静音 |
| 🔍 **在线搜索** | 接入 fangpi.net 平台，实时搜索歌曲 |
| ⬇️ **在线下载** | 一键下载搜索到的歌曲到本地曲库，支持播放与分析 |
| 📈 **专业音频分析** | FFmpeg 解码 → Spectral Flux → Cooley-Tukey FFT → 自相关节拍估计 → DP Beat Tracking (Ellis 2007) |
| 🎯 **BPM / Beat / Cue** | 精确 BPM 检测、逐拍定位、自动段落识别（Cue Points） |
| 💾 **持久化曲库** | 本地 JSON 数据库，关闭应用后歌曲信息与分析结果不丢失 |
| 🌙 **深色主题** | DAW 风格暗色 UI |

---

## 快速开始

### 环境要求

- **Node.js** ≥ 18
- **npm** ≥ 9
- **Windows** (已测试)

### 安装与运行

```bash
# 克隆仓库
git clone https://github.com/wwwxxx0501/music_demo_xyw.git
cd music_demo_xyw

# 安装依赖
npm install

# 国内用户如遇 Electron 下载慢，设置镜像：
# Windows CMD:
#   set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
# PowerShell:
#   $env:ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"

# 启动开发模式
npm run dev

# 生产构建
npm run build
```

启动后会自动打开桌面窗口，即可开始使用。

---

## 使用说明

### 1. 导入本地音频

1. 点击左侧边栏的 **「导入音频」** 按钮
2. 在弹出的系统文件对话框中选择一个或多个音频文件
3. 支持的格式：MP3、AAC、M4A、WAV、FLAC、OGG、WMA、AIFF、APE、OPUS、NCM 等
4. 选中的文件会自动出现在 **「我的曲库」** 列表中
5. 如果选择了 `.ncm` 文件，系统会自动解密并转换为可播放的 MP3

### 2. 播放音频

1. 在歌曲列表中点击任意一首歌曲，右侧会展示歌曲详情
2. **波形区域**：显示整首歌曲的波形图，可点击任意位置跳转播放
3. **播放控制**：
   - ▶️ / ⏸ — 播放 / 暂停
   - ⏪ / ⏩ — 快退 / 快进 5 秒
   - 🔊 — 音量滑块调节
   - 🔇 — 点击静音/取消静音

### 3. 搜索在线歌曲

1. 点击左侧边栏切换到 **「平台曲库」** 视图
2. 在顶部搜索框输入歌曲名或歌手名（如「周杰伦」「七里香」）
3. 系统会自动搜索 fangpi.net 并展示搜索结果列表
4. 点击搜索结果中的歌曲可查看详情

### 4. 下载在线歌曲

1. 在平台曲库搜索结果中，点击歌曲右侧的 **⬇️ 下载按钮**
2. 系统会自动获取音频源并下载到本地 `database/music-files/` 目录
3. 下载完成后，歌曲将同时出现在 **「我的曲库」** 中
4. 下载过的歌曲会显示 **「已下载」** 标识，避免重复下载

### 5. 音频分析（BPM / Beat / Cue）

1. 在歌曲详情页，点击 **「分析」** 按钮
2. 系统使用 FFmpeg 解码音频，然后执行以下分析流程：
   - **STFT 短时傅里叶变换** — 将音频转换到频域
   - **Spectral Flux** — 计算频谱差异检测节拍起始点
   - **自相关估计** — 从频谱变化推算 BPM
   - **DP Beat Tracking** — 基于 Ellis 2007 算法精确定位每一个节拍
   - **段落识别** — 自动检测歌曲各段（前奏、主歌、副歌等）的起始 Cue Point
3. 分析完成后，详情页将展示：
   - **BPM** — 每分钟节拍数
   - **Beat Points** — 节拍时间戳列表
   - **Cue Points** — 段落标记点及其时间
4. 分析结果会自动保存到本地数据库，下次打开无需重新分析
5. **本地导入的歌曲和在线下载的歌曲都可以进行分析**

### 6. 管理曲库

- **我的曲库**：显示所有本地导入和已下载的歌曲
- **平台曲库**：搜索在线歌曲，空搜索框时显示已收藏的歌曲
- 歌曲信息、分析结果等数据持久化存储在项目的 `database/` 目录下

---

## 技术架构

```
┌──────────────────────────────────────────────────────┐
│                    Electron Main                      │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ File Dialog   │  │ HTTP Audio   │  │ FFmpeg Audio │ │
│  │ IPC Handlers  │  │ Server       │  │ Analyzer     │ │
│  │ NCM Decrypt   │  │ (127.0.0.1)  │  │ (DSP/BPM)   │ │
│  └──────────────┘  └──────────────┘  └─────────────┘ │
│  ┌──────────────┐  ┌──────────────────────────────┐   │
│  │ fangpi.net   │  │ Platform Library (JSON DB)   │   │
│  │ Search & DL   │  │ database/platform-library.json│  │
│  └──────────────┘  └──────────────────────────────┘   │
├──────────────────────────────────────────────────────┤
│               contextBridge (Preload)                 │
├──────────────────────────────────────────────────────┤
│                   Renderer (React)                    │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────────┐ │
│  │ Sidebar   │ │ SongList │ │ SongDetail            │ │
│  │ (导航)    │ │ (列表)    │ │ ├ WaveformPlayer     │ │
│  │           │ │          │ │ └ AnalysisPanel       │ │
│  └──────────┘ └──────────┘ └───────────────────────┘ │
│                  Zustand Store                        │
└──────────────────────────────────────────────────────┘
```

---

## 项目结构

```
music_demo_xyw/
├── electron/
│   ├── main.ts              # 主进程：窗口、IPC、HTTP 音频服务
│   ├── preload.ts           # 预加载脚本：contextBridge API
│   ├── audioAnalyzer.ts     # 音频分析：FFmpeg + Spectral Flux + DP Beat Tracking
│   ├── fangpiService.ts     # fangpi.net 搜索、音频 URL 获取、下载
│   ├── ncmDecrypt.ts        # 网易云 NCM 文件解密
│   └── platformLibrary.ts   # 持久化 JSON 曲库数据库
├── src/
│   ├── components/
│   │   ├── Sidebar.tsx       # 左侧导航 + 导入按钮
│   │   ├── SongList.tsx      # 歌曲列表（支持下载状态图标）
│   │   ├── SongDetail.tsx    # 歌曲详情卡片（下载/分析入口）
│   │   ├── WaveformPlayer.tsx# Canvas 波形 + Audio 播放器
│   │   ├── AnalysisPanel.tsx # BPM / Beat / Cue 分析面板
│   │   ├── SearchBar.tsx     # 搜索输入框（500ms 防抖）
│   │   └── ErrorBoundary.tsx # 错误边界
│   ├── store/
│   │   └── useMusicStore.ts  # Zustand 状态管理
│   ├── types/
│   │   └── index.ts          # TypeScript 类型定义
│   ├── utils/
│   │   └── format.ts         # 格式化工具函数
│   ├── styles/
│   │   └── global.css        # 全局样式 + Tailwind
│   ├── App.tsx               # 根组件（三栏布局）
│   └── main.tsx              # React 入口
├── database/                  # 运行时生成，已 gitignore
│   ├── platform-library.json  # 曲库数据库
│   └── music-files/           # 下载的音频文件
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
└── README.md
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
