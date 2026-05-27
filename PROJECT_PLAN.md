# HarBeat DJ Mixing System - 重构计划

## 项目背景

HarBeat 是一个智能 DJ 混音系统，支持多平台（Web、Flutter App、RK3588 硬件设备）。当前系统功能粗糙，需要完全重构，不依赖现有实现，按照新的需求从零开始构建。

## 技术架构

### 后端
- **框架**: FastAPI + SQLAlchemy ORM
- **认证**: JWT (access_token + refresh_token)
- **数据库**: PostgreSQL/MySQL
- **部署**: Nginx 反向代理 + Uvicorn
- **服务器**: 阿里云 Jetson (8.136.120.255)
- **远程访问**: Tailscale VPN

### 前端
- **Web**: React/Vue (现有)
- **Mobile**: Flutter App (iOS + Android)

### 硬件
- **设备**: RK3588 音频引擎
- **通信**: edge-agent (FastAPI :9000) 协议 P4
- **音频引擎**: 18 种专业 DJ 转场类型
  - 7 种全轨转场: smooth, bass_swap, echo_freeze, filter_sweep, spinback, brake, reverse
  - 11 种 stem-aware 转场: vocal_echo, drum_roll, bass_drop, filter_build, vocal_chop, drum_fill, harmonic_mix, energy_build, breakdown, drop, mashup

## 开发流程

### 模块化实现原则
1. **分模块开发**: 每次只实现一个模块
2. **后端先行**: 先完成后端 API 实现
3. **自主测试**: Claude 作为用户进行完整测试（API + Web + App）
4. **自主调试**: 遇到问题自行 debug，不依赖用户
5. **结果汇报**: 测试通过后，向用户汇报最终效果和实现方式
6. **用户验收**: 用户在手机 App 和 Web 上进行最终验收
7. **下一模块**: 验收通过后进入下一模块

### 测试环境
- **后端 API**: 127.0.0.1:8080 (本地测试)
- **Web 界面**: http://8.136.120.255 (Nginx 代理)
- **SSH 连接**: root@8.136.120.255 (密码: 123456)
- **Tailscale**: 密码 123456

## 分阶段实现计划

### Phase 1: 准备工作（基础设施）

#### Module 1: 用户管理系统 ✅ (已完成)
**功能需求**:
- 用户注册/登录/登出
- Token 刷新机制
- 密码修改
- 用户信息查询
- 账号停用
- 多设备同时登录支持

**API 端点**:
- `POST /api/auth/register` - 注册
- `POST /api/auth/login` - 登录
- `POST /api/auth/refresh` - 刷新 token
- `POST /api/auth/logout` - 登出
- `GET /api/auth/me` - 获取当前用户信息
- `POST /api/auth/change-password` - 修改密码
- `POST /api/auth/deactivate` - 停用账号

**实现状态**: ✅ 后端实现完成，API 测试通过

---

#### Module 2: 曲库管理 (Library Management)
**功能需求**:
- 歌曲上传（支持 MP3/WAV/FLAC）
- 歌曲元数据管理（标题、艺术家、专辑、时长、BPM、调性）
- 歌曲列表查询（分页、搜索、过滤）
- 歌曲删除
- 歌曲状态管理（上传中、分析中、就绪、失败）
- 文件存储管理

**API 端点**:
- `POST /api/library/upload` - 上传歌曲
- `GET /api/library/songs` - 获取歌曲列表
- `GET /api/library/songs/{song_id}` - 获取歌曲详情
- `DELETE /api/library/songs/{song_id}` - 删除歌曲
- `GET /api/library/songs/{song_id}/status` - 查询处理状态

**数据库表**:
```sql
CREATE TABLE library_songs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(255),
    artist VARCHAR(255),
    album VARCHAR(255),
    duration_sec FLOAT,
    bpm FLOAT,
    key VARCHAR(10),
    file_path VARCHAR(512),
    file_size BIGINT,
    file_format VARCHAR(10),
    status VARCHAR(20), -- uploading, analyzing, ready, failed
    uploaded_at TIMESTAMP,
    analyzed_at TIMESTAMP
);
```

---

#### Module 3: 歌单管理 (Playlist Management)
**功能需求**:
- 创建/删除歌单
- 添加/移除歌曲
- 歌单排序（手动拖拽、智能排序）
- 歌单分享
- 歌单导入/导出

**API 端点**:
- `POST /api/playlists/create` - 创建歌单
- `GET /api/playlists` - 获取用户歌单列表
- `GET /api/playlists/{playlist_id}` - 获取歌单详情
- `DELETE /api/playlists/{playlist_id}` - 删除歌单
- `POST /api/playlists/{playlist_id}/add-songs` - 添加歌曲
- `DELETE /api/playlists/{playlist_id}/songs/{song_id}` - 移除歌曲
- `PUT /api/playlists/{playlist_id}/reorder` - 重新排序

**数据库表**:
```sql
CREATE TABLE playlists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE playlist_songs (
    id SERIAL PRIMARY KEY,
    playlist_id INTEGER REFERENCES playlists(id),
    song_id INTEGER REFERENCES library_songs(id),
    position INTEGER,
    added_at TIMESTAMP
);
```

---

#### Module 4: 第三方歌单导入
**功能需求**:
- QQ 音乐歌单导入
- 网易云音乐歌单导入
- 歌曲匹配算法（标题+艺术家）
- 导入进度追踪

**API 端点**:
- `POST /api/import/qq-music` - 导入 QQ 音乐歌单
- `POST /api/import/netease` - 导入网易云歌单
- `GET /api/import/{task_id}/status` - 查询导入进度

---

#### Module 5: 下载管理
**功能需求**:
- 下载队列管理
- 断点续传
- 下载进度追踪
- 并发下载控制
- 失败重试机制

**API 端点**:
- `POST /api/download/start` - 开始下载
- `GET /api/download/queue` - 获取下载队列
- `GET /api/download/{task_id}/progress` - 查询下载进度
- `POST /api/download/{task_id}/pause` - 暂停下载
- `POST /api/download/{task_id}/resume` - 恢复下载
- `DELETE /api/download/{task_id}` - 取消下载

---

#### Module 6: 预处理队列
**功能需求**:
- 音频分析（BPM、调性、能量曲线）
- Stem 分离（vocals, drums, bass, other）
- 节拍检测
- 转场点检测
- 处理队列管理
- 失败重试

**API 端点**:
- `POST /api/preprocessing/analyze` - 提交分析任务
- `GET /api/preprocessing/queue` - 获取处理队列
- `GET /api/preprocessing/{task_id}/status` - 查询处理状态
- `POST /api/preprocessing/{task_id}/retry` - 重试失败任务

**数据库表**:
```sql
CREATE TABLE preprocessing_tasks (
    id SERIAL PRIMARY KEY,
    song_id INTEGER REFERENCES library_songs(id),
    task_type VARCHAR(50), -- analyze, stem_separation, beat_detection
    status VARCHAR(20), -- pending, processing, completed, failed
    progress FLOAT,
    error_message TEXT,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE song_analysis (
    id SERIAL PRIMARY KEY,
    song_id INTEGER REFERENCES library_songs(id),
    bpm FLOAT,
    key VARCHAR(10),
    energy_curve JSONB, -- 能量曲线数据
    beat_grid JSONB, -- 节拍网格
    transition_points JSONB, -- 转场点
    has_stems BOOLEAN,
    analyzed_at TIMESTAMP
);
```

---

#### Module 7: 语义搜索
**功能需求**:
- 基于歌词的语义搜索
- 基于风格的搜索
- 基于情绪的搜索
- 相似歌曲推荐

**API 端点**:
- `POST /api/search/semantic` - 语义搜索
- `GET /api/search/similar/{song_id}` - 相似歌曲推荐

---

### Phase 2: DJ 混音功能（核心功能）

#### Module 8: 能量计算引擎
**功能需求**:
- 实时能量值计算（0-100）
- 能量曲线生成
- 能量特征提取（平均值、峰值、方差）
- 能量区间分类（低能量 0-30、中能量 30-70、高能量 70-100）

**实现方式**:
- 使用 librosa 进行音频分析
- RMS 能量计算
- 频谱能量分析
- 节奏强度分析

---

#### Module 9: 能量曲线编辑器
**功能需求**:
- 预设模板系统:
  - **平稳型**: 能量保持在中等水平，波动小
  - **渐进型**: 能量逐渐上升
  - **一直高**: 全程高能量
  - **单峰型**: 中间达到高峰
  - **双峰型**: 两个高峰
  - **收尾型**: 开始高能量，逐渐降低
- 自定义曲线编辑
- 曲线预览
- 曲线保存/加载

**API 端点**:
- `GET /api/energy/templates` - 获取预设模板
- `POST /api/energy/custom` - 创建自定义曲线
- `GET /api/energy/curves/{curve_id}` - 获取曲线详情
- `PUT /api/energy/curves/{curve_id}` - 更新曲线

---

#### Module 10: 智能混音算法
**功能需求**:
- 根据能量曲线智能排序歌曲
- 自动选择转场类型
- 转场点智能检测
- BPM 匹配和调整
- 调性兼容性检测

**核心算法**:
1. **歌曲排序**:
   - 根据目标能量曲线计算每首歌的最佳位置
   - 考虑 BPM 相似度（避免过大跳变）
   - 考虑调性兼容性
   - 考虑风格连贯性

2. **转场选择**:
   - 能量上升: bass_drop, energy_build, drum_fill
   - 能量下降: breakdown, filter_sweep
   - 能量平稳: smooth, harmonic_mix
   - 高能量段: mashup, vocal_chop
   - 低能量段: vocal_echo, filter_build

3. **转场点检测**:
   - 检测歌曲的 intro/outro/breakdown 段落
   - 检测节拍对齐点
   - 检测能量变化点

**API 端点**:
- `POST /api/mix/generate` - 生成混音计划
- `POST /api/mix/optimize` - 优化现有混音
- `GET /api/mix/{plan_id}` - 获取混音计划详情

---

#### Module 11: 临时跳过功能
**功能需求**:
- 播放中临时跳过 5-10 秒
- 自动寻找合适的转场点
- 实时能量匹配
- 平滑过渡

**实现方式**:
1. 用户触发跳过
2. 系统在当前歌曲的后 5-10 秒内寻找转场点
3. 检测节拍对齐
4. 检测能量匹配度
5. 执行快速转场（2-4 秒）

**API 端点**:
- `POST /api/playback/skip-forward` - 向前跳过
- `POST /api/playback/find-transition` - 查找转场点

---

#### Module 12: 能量调整功能
**功能需求**:
- 仅调整下一首歌曲
- 不影响整体能量曲线
- 实时预览调整效果
- 支持能量升/降/保持

**实现方式**:
1. 用户选择调整方向（升/降/保持）
2. 系统从歌单中筛选符合条件的歌曲
3. 考虑 BPM 和调性兼容性
4. 重新计算转场参数
5. 更新播放队列

**API 端点**:
- `POST /api/playback/adjust-energy` - 调整下一首能量
- `GET /api/playback/energy-options` - 获取可选歌曲

---

#### Module 13: DJ 效果器
**功能需求**:
- **搓碟效果** (Scratch): 模拟黑胶唱片搓碟
- **喇叭效果** (Megaphone): 电话/喇叭音效
- **回声效果** (Echo): 延迟回声
- **滤波器** (Filter): 高通/低通滤波
- **混响** (Reverb): 空间混响
- **失真** (Distortion): 音色失真

**实现方式**:
- 实时音频处理
- 参数可调（强度、速度、深度）
- 支持效果叠加
- 支持效果自动化（随时间变化）

**API 端点**:
- `POST /api/effects/apply` - 应用效果
- `POST /api/effects/remove` - 移除效果
- `PUT /api/effects/{effect_id}/params` - 调整参数

---

## RK3588 集成

### edge-agent API (协议 P4)
RK3588 设备通过 edge-agent 与后端通信，端口 :9000

**核心端点**:
- `GET /health` - 健康检查
- `POST /load_plan` - 加载混音计划
- `POST /play` - 播放
- `POST /pause` - 暂停
- `POST /resume` - 恢复
- `POST /next` - 下一首
- `POST /seek` - 跳转
- `POST /trigger` - 触发按键事件

**WebSocket 实时推送**:
- `playback_state` - 播放状态更新
- `device_info` - 设备信息
- `sync_progress` - 同步进度

### 混音计划格式
```json
{
  "plan_id": "uuid",
  "tracks": ["100", "101", "102"],
  "transitions": [
    {
      "from_track": "100",
      "to_track": "101",
      "style": "bass_drop",
      "duration_sec": 16.0,
      "start_at_sec": 30.0
    }
  ]
}
```

### Manifest 格式
```json
{
  "plan_id": "uuid",
  "tracks": [
    {
      "song_id": 100,
      "library_song_id": "lib-001",
      "title": "Song Title",
      "artist": "Artist Name",
      "files": {
        "original": {
          "url": "/api/stream/lib-001",
          "sha256": "hash",
          "size": 5000000
        },
        "stems": {
          "vocals": {"url": "...", "sha256": "...", "size": 1000000},
          "drums": {"url": "...", "sha256": "...", "size": 800000},
          "bass": {"url": "...", "sha256": "...", "size": 600000},
          "other": {"url": "...", "sha256": "...", "size": 700000}
        }
      }
    }
  ]
}
```

---

## 当前进度

### 已完成
- ✅ Module 1: 用户管理系统（后端 + API 测试）

### 进行中
- 🔄 Module 1: Web 界面测试 + 多设备登录验证

### 待开始
- ⏳ Module 2-7: Phase 1 其他模块
- ⏳ Module 8-13: Phase 2 DJ 功能

---

## 测试清单

### Module 1 测试清单
- [x] 注册新用户
- [x] 登录获取 token
- [x] 使用 token 获取用户信息
- [x] 刷新 token
- [x] 修改密码
- [x] 使用新密码登录
- [ ] Web 界面注册/登录
- [ ] 多设备同时登录
- [ ] Token 过期处理

---

## 注意事项

1. **不依赖现有粗糙实现**: 完全按照新需求重构
2. **模块化开发**: 一次只做一个模块，测试通过再进行下一个
3. **自主测试**: Claude 完成所有测试和调试工作
4. **清理无关代码**: 避免后续混乱
5. **保持代码质量**: 遵循 FastAPI 最佳实践
6. **安全第一**: JWT 认证、SQL 注入防护、XSS 防护
7. **性能优化**: 数据库索引、查询优化、缓存策略
8. **错误处理**: 统一错误响应格式、详细日志记录

---

## API 响应格式

所有 API 统一使用以下响应格式:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    // 实际数据
  }
}
```

错误响应:
```json
{
  "code": 1001,
  "message": "用户名已存在",
  "data": null
}
```

---

## 下一步行动

1. 完成 Module 1 的 Web 界面测试
2. 验收通过后开始 Module 2: 曲库管理
3. 按照模块顺序逐步实现 Phase 1
4. Phase 1 完成后开始 Phase 2 DJ 功能
