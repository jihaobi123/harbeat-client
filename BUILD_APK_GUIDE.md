# 📱 HarBeat APK 构建完全指南

## ⚡ 快速开始（10分钟搞定）

### 第1步：安装 Flutter（5分钟）

#### Windows 系统

**方法 A：使用 Git 安装（推荐）**

```powershell
# 1. 打开 PowerShell（管理员权限）

# 2. 克隆 Flutter SDK
cd C:\
git clone https://github.com/flutter/flutter.git -b stable

# 3. 添加环境变量
# 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
# 在"系统变量"中找到 Path → 编辑 → 新建
# 添加: C:\flutter\bin

# 4. 重启 PowerShell，验证安装
flutter doctor
```

**方法 B：下载压缩包安装**

```
1. 访问: https://docs.flutter.dev/get-started/install/windows
2. 下载 flutter_windows_x.x.x-stable.zip
3. 解压到 C:\flutter
4. 添加 C:\flutter\bin 到系统环境变量 Path
5. 重启终端，运行 flutter doctor
```

#### 验证安装成功

```powershell
flutter doctor
```

应该看到类似输出：
```
Doctor summary (to see all details, run flutter doctor -v):
[✓] Flutter (Channel stable, 3.x.x, on Microsoft Windows ...)
[✓] Android toolchain - develop for Android devices
[✓] Chrome - develop for the web
[!] Visual Studio - develop Windows apps
[✓] Android Studio (version 202x.x)
[✓] Connected device (1 available)
[✓] Network resources
```

> ⚠️ **注意**: Android toolchain 显示 ✓ 即可，其他可选

---

### 第2步：配置 Android 开发环境（3分钟）

#### 安装 Android Studio

```
1. 下载: https://developer.android.com/studio
2. 安装时勾选 "Android SDK" 和 "Android Virtual Device"
3. 首次启动会下载 SDK 组件（需要几分钟）
```

#### 接受 Android 许可证

```powershell
flutter doctor --android-licenses
# 全部输入 y 接受
```

#### 再次验证

```powershell
flutter doctor
# 确保 Android toolchain 显示 ✓
```

---

### 第3步：构建 APK（2分钟）

```powershell
# 进入项目目录
cd d:\工作\DJ机\harbeat_app

# 安装依赖
flutter pub get

# 生成代码
flutter pub run build_runner build --delete-conflicting-outputs

# 构建 Release APK
flutter build apk --release
```

**APK 位置**:
```
d:\工作\DJ机\harbeat_app\build\app\outputs\flutter-apk\app-release.apk
```

---

## 🚀 一键构建脚本（推荐）

我已经为你准备好了自动化脚本，只需运行：

```powershell
cd d:\工作\DJ机\harbeat_app
.\build_apk.ps1
```

脚本会自动：
1. ✅ 检查 Flutter 环境
2. ✅ 清理旧构建
3. ✅ 安装依赖
4. ✅ 生成代码
5. ✅ 构建 APK
6. ✅ 显示 APK 位置和大小

---

## 📦 APK 文件大小预估

| 类型 | 大小 | 说明 |
|------|------|------|
| **Debug APK** | ~80 MB | 包含调试信息，体积大 |
| **Release APK** | ~30-50 MB | 优化后，适合发布 |
| **Split APKs** | ~20-30 MB | 按架构分离，更小 |

---

## 🔧 常见问题解决

### ❌ 问题1：flutter 命令找不到

**原因**: 环境变量未配置

**解决**:
```powershell
# 临时添加（当前会话有效）
$env:Path += ";C:\flutter\bin"

# 永久添加（推荐）
# 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
# Path → 新建 → C:\flutter\bin
# 重启 PowerShell
```

---

### ❌ 问题2：Android licenses not accepted

**解决**:
```powershell
flutter doctor --android-licenses
# 全部输入 y
```

---

### ❌ 问题3：Gradle 构建失败

**原因**: 网络问题或 Gradle 版本不兼容

**解决**:
```powershell
# 清理缓存
flutter clean

# 重新获取依赖
flutter pub get

# 重试构建
flutter build apk --release
```

如果仍然失败，修改 `android/build.gradle`:
```gradle
buildscript {
    repositories {
        google()
        mavenCentral()
        // 添加阿里云镜像加速
        maven { url 'https://maven.aliyun.com/repository/google' }
        maven { url 'https://maven.aliyun.com/repository/jcenter' }
    }
}
```

---

### ❌ 问题4：内存不足

**症状**: OutOfMemoryError

**解决**:
```powershell
# 增加 Gradle 内存
# 编辑 android/gradle.properties
org.gradle.jvmargs=-Xmx4g -XX:MaxPermSize=512m
```

---

## 💡 加速构建技巧

### 1. 使用国内镜像（中国大陆用户必备）

```powershell
# 设置 Flutter 镜像
export PUB_HOSTED_URL=https://pub.flutter-io.cn
export FLUTTER_STORAGE_BASE_URL=https://storage.flutter-io.cn

# Windows PowerShell
$env:PUB_HOSTED_URL="https://pub.flutter-io.cn"
$env:FLUTTER_STORAGE_BASE_URL="https://storage.flutter-io.cn"
```

### 2. 只构建 ARM64 架构（现代手机）

```powershell
flutter build apk --release --target-platform android-arm64
```

### 3. 分割 APK（更小体积）

```powershell
flutter build apk --release --split-per-abi
# 会生成:
# app-armeabi-v7a-release.apk  (ARM 32位)
# app-arm64-v8a-release.apk    (ARM 64位) ← 推荐
# app-x86_64-release.apk       (x86 64位)
```

---

## 📊 构建时间参考

| 阶段 | 首次构建 | 后续构建 |
|------|---------|---------|
| 依赖下载 | 2-5 分钟 | < 10 秒 |
| 代码生成 | 30-60 秒 | 10-20 秒 |
| Gradle 编译 | 3-8 分钟 | 1-3 分钟 |
| **总计** | **5-15 分钟** | **1-5 分钟** |

---

## ✅ 验证 APK 有效性

### 方法1：查看 APK 信息

```powershell
# 使用 aapt 工具（Android SDK 自带）
aapt dump badging build/app/outputs/flutter-apk/app-release.apk
```

### 方法2：直接安装测试

```powershell
# USB 连接手机后
adb install build/app/outputs/flutter-apk/app-release.apk
```

### 方法3：在线验证工具

上传到 [APK Analyzer](https://www.apkanalyzer.io/) 查看详细信息

---

## 🎯 完整操作流程总结

```powershell
# 1. 安装 Flutter
cd C:\
git clone https://github.com/flutter/flutter.git -b stable
# 添加 C:\flutter\bin 到环境变量

# 2. 验证安装
flutter doctor

# 3. 进入项目
cd d:\工作\DJ机\harbeat_app

# 4. 一键构建
.\build_apk.ps1

# 5. 找到 APK
# build\app\outputs\flutter-apk\app-release.apk
```

---

## 📞 需要帮助？

如果遇到问题：

1. **查看详细日志**:
   ```powershell
   flutter build apk --release -v
   ```

2. **查看 Flutter 社区**:
   - https://flutter.dev/community
   - https://stackoverflow.com/questions/tagged/flutter

3. **检查系统要求**:
   - Windows 10+ (64-bit)
   - 至少 4GB RAM（推荐 8GB）
   - 至少 10GB 磁盘空间

---

**准备好了吗？开始吧！** 🚀

预计总时间：**10-15 分钟**（含 Flutter 安装）
