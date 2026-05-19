# HarBeat Flutter App 开发总结

## 📋 项目概览

**项目名称**: HarBeat Mobile App  
**技术栈**: Flutter + Dart  
**目标平台**: Android + iOS  
**开发状态**: MVP 阶段（核心功能已完成）

---

## ✅ 已完成功能

### 1. 项目架构搭建 ✓

#### 分层架构设计
```
┌─────────────────────────┐
│   Presentation Layer    │  ← UI 页面和组件
│   (pages, widgets)      │
├─────────────────────────┤
│   Data Layer            │  ← 数据模型和服务
│   (models, services)    │
├─────────────────────────┤
│   Core Layer            │  ← 核心功能
│   (network, config)     │
└─────────────────────────┘
```

#### 关键技术选型
- **状态管理**: Riverpod（响应式、类型安全）
- **网络请求**: Dio + Retrofit（RESTful API）
- **音频播放**: just_audio（专业级播放器）
- **蓝牙连接**: flutter_blue_plus（BLE 支持）
- **本地存储**: Hive（轻量级 NoSQL）

---

### 2. 核心模块实现 ✓

#### 🔐 认证模块 (`AuthService`)
```dart
// 功能
- 用户登录（JWT Token）
- 用户注册
- 获取用户信息
- Token 自动管理

// API 端点
POST /api/auth/login
POST /api/auth/register
GET  /api/auth/me
```

#### 🎵 音乐库模块 (`SongService`)
```dart
// 功能
- 获取歌曲列表
- 搜索歌曲
- 获取歌曲详情
- 生成音频流 URL

// API 端点
GET /api/library/songs
GET /api/library/songs/search?q={query}
GET /api/library/songs/{id}
```

#### 🎧 音频播放模块 (`AudioPlayerService`)
```dart
// 功能
- 播放/暂停/停止
- 进度控制（seek）
- 播放速度调整（BPM Sync）
- A-B Loop 循环
- 后台播放支持

// 特性
- 单例模式
- Stream 状态通知
- HTTP Range 请求支持
```

#### 📡 蓝牙模块 (`BluetoothService`)
```dart
// 功能
- 扫描蓝牙设备
- 连接/断开设备
- 设备列表管理
- 连接状态追踪

// 协议
- A2DP（高质量音频传输）
- BLE（低功耗蓝牙）
```

---

### 3. UI 页面实现 ✓

#### 📱 登录页面 (`LoginPage`)
- 渐变背景设计
- 表单验证
- 登录/注册切换
- 错误提示

#### 🏠 首页 (`HomePage`)
- 底部导航栏
- 三个主要标签页：
  - 音乐库
  - 播放器
  - 蓝牙设置

#### 📚 音乐库页面 (`LibraryPage`)
- 搜索框（实时搜索）
- 歌曲列表（Card 布局）
- 下拉刷新
- 空状态提示

#### 🎼 播放器页面 (`PlayerPage`)
- 专辑封面展示
- 歌曲信息显示
- 进度条（可拖动）
- 播放控制按钮
- A-B Loop 功能
- 功能快捷入口

#### 📶 蓝牙页面 (`BluetoothPage`)
- 已连接设备显示
- 扫描动画
- 设备列表
- 信号强度显示
- 连接/断开操作

---

### 4. 工具类实现 ✓

#### 📝 日志工具 (`AppLogger`)
```dart
// 基于 logger 包
- 彩色输出
- 时间戳
- 错误堆栈
- 结构化日志
```

#### 🌐 API 客户端 (`ApiClient`)
```dart
// 基于 Dio
- 单例模式
- 请求拦截器（自动添加 Token）
- 响应拦截器
- 错误处理
- 超时配置
```

---

## 🎯 核心技术亮点

### 1. 智能网络切换架构

```dart
class SmartApiConfig {
  // 优先级 1: 局域网直连
  Future<String?> detectLocalServer() → mDNS 发现
  
  // 优先级 2: Tailscale P2P
  bool checkTailscale() → VPN 状态检测
  
  // 优先级 3: 阿里云 ECS
  String productionUrl → HTTPS 反向代理
}
```

**优势**:
- ✅ 最低延迟（局域网 <10ms）
- ✅ 端到端加密（Tailscale）
- ✅ 全球可用（ECS 兜底）

### 2. 音频流式播放

```dart
// HTTP Range 请求支持
final streamUrl = '${baseUrl}/api/stream/$songId?token=$token';
await _player.setUrl(streamUrl);

// just_audio 自动处理:
// - 缓冲策略
// - 断点续传
// - 后台播放
```

**优势**:
- ✅ 无需完整下载
- ✅ 快速起播
- ✅ 节省流量

### 3. 蓝牙音频路由

```dart
// Android: AudioManager 自动路由
// iOS: AVAudioSession 自动路由

// 用户只需:
await BluetoothService().connectToDevice(deviceId);
// 系统自动将音频输出到蓝牙设备
```

**优势**:
- ✅ 无需手动切换
- ✅ 支持 A2DP 高质量传输
- ✅ 跨平台一致体验

---

## 📊 代码统计

| 类别 | 文件数 | 代码行数 |
|------|--------|----------|
| **核心模块** | 5 | ~400 |
| **数据层** | 4 | ~250 |
| **UI 页面** | 5 | ~800 |
| **UI 组件** | 1 | ~120 |
| **配置文件** | 2 | ~100 |
| **总计** | **17** | **~1670** |

---

## 🚀 下一步计划

### Phase 2: 增强功能（2周）

#### 1. 波形可视化
```dart
// 实现方案
- CustomPainter 绘制 Canvas
- 从后端获取 beat points
- 实时高亮当前播放位置
- 点击跳转功能
```

#### 2. BPM Sync 完整实现
```dart
// 实现方案
- 读取歌曲 BPM
- 计算目标速度比率
- 动态调整播放速度
- 保持音调不变（key lock）
```

#### 3. Cue Points 标记
```dart
// 实现方案
- 长按波形添加 Cue 点
- Cue 点列表管理
- 快速跳转到 Cue 点
- 同步到后端
```

### Phase 3: 业务功能（2周）

#### 1. 歌单管理
- 创建/删除歌单
- 添加/移除歌曲
- 拖拽排序
- 歌单分享

#### 2. 练舞会话
- 创建会话
- 记录练习时长
- 关联歌曲
- 统计数据

#### 3. 在线搜索
- fangpi.net 集成
- 跨平台搜索
- 试听功能
- 批量下载

---

## 🛠️ 开发环境配置

### 必需工具
```bash
# Flutter SDK
flutter --version  # >= 3.0.0

# Android Studio
- Android SDK (API 21+)
- Android Emulator

# Xcode (macOS only)
- iOS Simulator
- CocoaPods

# VS Code (推荐)
- Flutter 插件
- Dart 插件
```

### 可选工具
```bash
# 调试工具
- Flutter DevTools
- Charles Proxy (网络抓包)

# 测试工具
- Firebase Test Lab
- BrowserStack
```

---

## 📱 真机测试清单

### Android
- [ ] Samsung Galaxy S21 (Android 12)
- [ ] Xiaomi 12 (Android 13)
- [ ] Huawei P40 (Android 11)
- [ ] Google Pixel 6 (Android 14)

### iOS
- [ ] iPhone 13 (iOS 16)
- [ ] iPhone 14 Pro (iOS 17)
- [ ] iPad Air (iPadOS 16)

### 蓝牙设备
- [ ] JBL Charge 5
- [ ] Sony WH-1000XM4
- [ ] Bose SoundLink
- [ ] Marshall Emberton

---

## 🎓 学习要点

### 对于面试者

#### 1. 架构设计能力
- 清晰的分层架构
- 单一职责原则
- 依赖注入思想

#### 2. 技术深度
- 音频播放底层原理
- 蓝牙协议理解
- 网络优化策略

#### 3. 工程化思维
- 代码规范
- 错误处理
- 性能优化

#### 4. 产品意识
- 用户体验优先
- 渐进式功能开发
- 可扩展性设计

---

## 💡 面试话术模板

### Q: "请介绍一下这个 Flutter 项目"

**A:**
> "这是一个专业的街舞音乐移动端应用，采用 Flutter 跨平台开发。我负责了整体架构设计和核心功能实现。
> 
> 技术上，我采用了分层架构：Presentation 层负责 UI，Data 层处理业务逻辑，Core 层提供基础服务。状态管理使用 Riverpod，网络请求用 Dio，音频播放用 just_audio，蓝牙连接用 flutter_blue_plus。
> 
> 核心亮点有三个：
> 1. 智能网络切换：根据网络环境自动选择最优路径（局域网/P2P/云服务器）
> 2. 音频流式播放：使用 HTTP Range 请求实现边下边播
> 3. 蓝牙音频路由：通过 A2DP 协议实现高质量无线传输
> 
> 目前完成了 MVP 版本，包括用户认证、音乐库、播放器、蓝牙连接等核心功能。后续计划添加波形可视化、BPM Sync、Cue Points 等专业功能。"

### Q: "为什么选择 Flutter？"

**A:**
> "选择 Flutter 主要基于三点考虑：
> 
> 1. **性能接近原生**：Skia 引擎直接渲染，60fps 流畅体验，适合音频类应用
> 2. **跨平台一致性**：一套代码同时支持 Android 和 iOS，降低维护成本
> 3. **生态成熟**：just_audio、audio_service 等包完美支持专业音频需求
> 
> 相比 React Native，Flutter 在音频低延迟和 UI 一致性上更有优势。相比原生开发，Flutter 能节省 60% 以上的开发时间。"

---

## 📞 技术支持

如有问题，请查阅：
1. README.md - 快速开始指南
2. Flutter 官方文档: https://flutter.dev
3. 各依赖包文档: pub.dev

---

**最后更新**: 2026-05-12  
**版本**: v1.0.0 (MVP)
