# 🚀 HarBeat App 快速开始指南

## ⚡ 5分钟上手

### 1️⃣ 检查环境
```bash
flutter doctor
```

确保所有勾选都是 ✅

### 2️⃣ 安装依赖
```bash
cd harbeat_app
flutter pub get
```

### 3️⃣ 生成代码
```bash
flutter pub run build_runner build --delete-conflicting-outputs
```

### 4️⃣ 运行应用
```bash
# Windows 一键启动
.\start.ps1

# 或手动运行
flutter run
```

---

## 📁 重要文件速查

| 文件 | 用途 |
|------|------|
| `lib/main.dart` | 应用入口 |
| `lib/core/config/api_config.dart` | API 地址配置 |
| `lib/core/services/audio_player_service.dart` | 音频播放核心 |
| `lib/core/services/bluetooth_service.dart` | 蓝牙连接核心 |
| `lib/presentation/pages/player_page.dart` | 播放器页面 |

---

## 🔧 常用命令

```bash
# 清理构建缓存
flutter clean
flutter pub get

# 查看设备列表
flutter devices

# 运行在指定设备
flutter run -d <device_id>

# 热重载（开发中）
# 按 r 键

# 热重启（开发中）
# 按 R 键

# 构建 APK
flutter build apk --release

# 查看日志
flutter logs
```

---

## 🐛 常见问题速解

### ❌ Flutter 未找到
```bash
# 添加 Flutter 到 PATH
# Windows: 系统环境变量 → Path → 添加 flutter/bin
# macOS: echo 'export PATH="$PATH:/path/to/flutter/bin"' >> ~/.zshrc
```

### ❌ 依赖冲突
```bash
flutter clean
flutter pub get
flutter pub run build_runner build --delete-conflicting-outputs
```

### ❌ 无法连接设备
```bash
# Android: 开启 USB 调试
# iOS: 信任电脑并解锁屏幕

flutter devices  # 检查是否识别
```

### ❌ 编译错误
```bash
# 清除缓存
flutter clean

# 重新获取依赖
flutter pub get

# 重新构建
flutter pub run build_runner build --delete-conflicting-outputs
```

---

## 📱 真机测试

### Android
1. 开启开发者模式
2. 启用 USB 调试
3. 连接电脑
4. 允许 USB 调试授权

### iOS
1. 连接 Mac
2. 信任电脑
3. Xcode 配置签名
4. 选择真机运行

---

## 🎯 下一步

✅ 已完成：基础架构、认证、音乐库、播放器、蓝牙  
🚧 待完成：波形可视化、BPM Sync、Cue Points、歌单管理

查看详细计划：[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)

---

**需要帮助？** 查看 [README.md](README.md)
