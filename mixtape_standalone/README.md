# Mixtape Standalone Frontend

这是一个可直接迁移、可独立运行的 Mixtape 前端项目。

## 功能

- 方式 A：导入现有歌单到待混音列表
- 方式 B：按舞种/风格推荐
- 方式 C：按 vibe 语义排序推荐
- 登录
- 第 4 区块乐段选择
- 转场预览
- 混音导出
- 加入待混音列表
- 打标签相关接口调用

## 目录

```text
mixtape_standalone/
  index.html
  config.example.js
  README.md
```

## 使用方式

### 1. 准备配置

将 `config.example.js` 复制为 `config.js`，并根据你的后端地址修改：

- `apiBase`
- `previewBase`
- `spotifyRedirectUri`
- `spotifyClientId`

### 2. 启动静态服务器

```powershell
cd MixtapeStandaloneFolder
python -m http.server 5500
```

然后打开：

```text
http://127.0.0.1:5500/
```

### 3. 启动后端

该前端依赖后端 API，至少需要支持以下接口：

- `POST /api/auth/login`
- `POST /api/fangpi/parse-playlist`
- `POST /api/fangpi/search`
- `POST /api/fangpi/download`
- `POST /api/fangpi/vibe-search`
- `POST /api/library/reanalyze-all`
- `POST /api/playlists/create`
- `POST /api/playlists/{playlistId}/add-songs`
- `POST /api/playlists/generate-dj-offline-mix`
- `POST /api/fangpi/spotify/exchange-code`

此外，转场预览音频默认从后端的 `/Preview_mu` 提供。

## 上传 GitHub 前注意

- 不要提交真实 token、密码、密钥
- 建议把 `config.js` 当作本地文件，不要把真实凭证写死到仓库
- 如果你希望他人直接使用，请在 README 中明确后端启动方式和依赖环境

## 建议的 GitHub 使用方式

1. 用户 clone 仓库
2. 复制 `config.example.js` 为 `config.js`
3. 修改后端地址和相关配置
4. 启动后端
5. 启动静态服务
6. 打开网页即可使用
