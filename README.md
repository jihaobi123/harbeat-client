# HARIBEAT - 专业街舞音乐与 DJ 混音平台

[![Flutter](https://img.shields.io/badge/Flutter-3.x-blue.svg)](https://flutter.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

HARIBEAT 是一个专为街舞爱好者、MC 主持人和派对控场人员设计的专业音乐播放和现场控场应用。通过结合移动端便捷操作和后端强大的音频处理能力，实现一键式现场音乐控制。

## 📱 应用截图

![设备连接页](assets/screenshots/device_connection.png)
![歌单选择页](assets/screenshots/playlist_selection.png)
![MC 主控台](assets/screenshots/mc_control.png)

## ✨ 核心特性

### 🎯 三大核心页面
1. **设备连接页** - 蓝牙音响一键配对，自动搜索附近设备
2. **歌单选择页** - 5 种场景化官方歌单，口语化命名，傻瓜式操作
3. **MC 主控台** - 8 个超大功能按钮，远距离可见，单手盲操作

### 🔊 硬件控制能力
- **音量远程控制** - 通过 API 调节 RK3588 音响音量
- **蓝牙设备管理** - 扫描、连接、断开蓝牙音响
- **音频输出切换** - 支持多音频设备切换

### 🎵 智能音乐功能
- **流式播放** - HTTP Range 请求，边下边播
- **后台播放** - 锁屏控制，通知栏操作
- **会话追踪** - 记录用户操作，分析使用习惯

### 🎨 街头嘻哈风格
- **深色主题** - 防反光设计，户外强光可用
- **高饱和撞色** - 青绿、橙色、电光蓝点缀
- **超大按钮** - 适合手大、慌乱点击、不易误触

## 🚀 快速开始

### 前置要求

- Flutter SDK 3.0+
- Dart SDK 3.0+
- Android Studio / VS Code
- 一台运行 FastAPI 后端的服务器（RK3588 或云服务器）

### 安装步骤

1. **克隆项目**
   ```bash
   git clone https://github.com/jihaobi123/harbeat-client.git
   cd harbeat_app
   ```

2. **安装依赖**
   ```bash
   flutter pub get
   ```

3. **配置 API 地址**
   
   编辑 `lib/core/config/api_config.dart`:
   ```dart
   // 开发环境（本地 RK3588）
   static const String developmentUrl = 'http://192.168.1.100:8000';
   
   // 生产环境（阿里云 ECS）
   static const String productionUrl = 'https://8.136.120.255';
   
   // 切换环境
   static String baseUrl = developmentUrl; // 或 productionUrl
   ```

4. **运行应用**
   ```bash
   flutter run
   ```

### 构建 APK

```bash
# 调试版本
flutter build apk --debug

# 发布版本
flutter build apk --release
```

## 🏗️ 项目架构

```
harbeat_app/
├── lib/
│   ├── core/              # 核心模块
│   │   ├── config/        # 配置文件
│   │   ├── network/       # 网络请求
│   │   ├── services/      # 服务层
│   │   └── utils/         # 工具类
│   ├── data/              # 数据层
│   │   ├── models/        # 数据模型
│   │   └── services/      # 数据服务
│   ├── presentation/      # 表现层
│   │   ├── pages/         # 页面
│   │   └── widgets/       # 组件
│   └── main.dart          # 应用入口
├── assets/                # 资源文件
│   ├── images/            # 图片资源
│   ├── icons/             # 图标资源
│   └── fonts/             # 字体资源
└── pubspec.yaml           # 项目配置
```

## 🔧 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **框架** | Flutter 3.x | 跨平台 UI 框架 |
| **状态管理** | Riverpod | 响应式状态管理 |
| **网络** | Dio | HTTP 客户端 |
| **音频** | just_audio | 专业音频播放器 |
| **后台播放** | audio_service | 锁屏控制、通知栏 |
| **蓝牙** | flutter_blue_plus | BLE 蓝牙支持 |
| **本地存储** | Hive | 轻量级 NoSQL 数据库 |
| **日志** | logger | 结构化日志输出 |

## 📡 API 接口

### 认证相关
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/register` - 用户注册

### 音乐相关
- `GET /api/music/songs` - 获取歌曲列表
- `GET /api/music/songs/{id}` - 获取单曲详情
- `GET /api/stream/{song_id}` - 音频流式播放

### 歌单相关
- `GET /api/playlists` - 获取歌单列表
- `GET /api/playlists/{id}` - 获取歌单详情
- `POST /api/playlists` - 创建歌单

### 硬件控制（新增）
- `POST /api/hardware/volume` - 设置音量
- `GET /api/hardware/volume` - 获取当前音量
- `GET /api/hardware/bluetooth/devices` - 列出蓝牙设备
- `POST /api/hardware/bluetooth/scan` - 扫描蓝牙设备
- `POST /api/hardware/bluetooth/connect` - 连接蓝牙设备
- `POST /api/hardware/bluetooth/disconnect` - 断开蓝牙设备

详细 API 文档请参考：[HARDWARE_API.md](../harbeat-client-dj-mix/HARDWARE_API.md)

## 🎨 设计规范

### 色号规范

| 用途 | 色号 | 说明 |
|------|------|------|
| 主背景色 | `#666363` | 深灰，防反光 |
| 辅助背景色 | `#888888` | 浅灰，卡片背景 |
| 文字深色 | `#010101` | 纯黑，高对比度 |
| 文字浅色 | `#FFFFFF` | 白色，次要文字 |
| 青绿色（选中态） | `#2B756C` | 核心操作按钮 |
| 橙色（强调行动） | `#FF7D00` | "炸一点"等强氛围按钮 |
| 红色（警示） | `#FF3B30` | 连接失败、异常提示 |
| 绿色（成功） | `#34C759` | 设备已连接、播放正常 |

### 素材使用

1. **黑胶唱片** (`assets/images/vinyl_record.jpg`)
   - App Logo 图标
   - 歌单默认封面
   - 加载动画元素

2. **街舞男孩剪影** (`assets/images/street_dancer.jpg`)
   - 练舞歌单专属封面
   - 背景装饰（透明度 20%）
   - 开屏启动页主视觉

3. **泼墨笔刷** (`assets/images/ink_brush.jpg`)
   - 页面分隔线
   - 按钮底纹装饰
   - 标题背景元素

## 🐛 常见问题

### Q1: 编译时报错 "MissingPluginException"

**解决**: 确保已运行 `flutter pub get` 并重新构建项目。

### Q2: 蓝牙扫描不到设备

**解决**: 
- Android: 检查位置权限是否授予
- iOS: 确保 Info.plist 中添加了蓝牙权限描述
- 确认蓝牙设备处于配对模式

### Q3: 后台播放不工作

**解决**:
- Android: 检查 Foreground Service 配置
- iOS: 确认 Background Modes 中启用了 audio
- 测试真机而非模拟器

### Q4: 无法控制 RK3588 音量

**解决**:
- 确认后端服务正在运行
- 检查网络连接是否正常
- 查看后端日志确认 amixer 命令是否执行成功
- 确认 RK3588 上安装了 alsa-utils

## 📝 开发计划

### Phase 1: MVP (已完成 ✅)
- [x] 基础架构搭建
- [x] 三大核心页面实现
- [x] 硬件控制 API 集成
- [x] 蓝牙连接功能
- [x] 歌单选择功能
- [x] MC 控台按钮功能

### Phase 2: 增强功能 (进行中 🚧)
- [ ] 波形可视化
- [ ] A-B Loop 功能
- [ ] BPM Sync
- [ ] Cue Points 标记

### Phase 3: 优化与上架 (计划中 📋)
- [ ] 性能优化
- [ ] 多语言支持
- [ ] 应用商店素材准备
- [ ] 提交审核

## 📄 许可证

MIT License

## 👥 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 联系方式

- GitHub: https://github.com/jihaobi123/harbeat-client
- Email: your-email@example.com

## 🙏 致谢

感谢所有为 HARIBEAT 项目做出贡献的开发者和设计师！
