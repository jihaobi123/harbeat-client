# 🤖 Android SDK 安装指南

## ⚠️ 当前问题

```
[!] No Android SDK found. Try setting the ANDROID_HOME environment variable.
```

你需要安装 Android SDK 才能构建 Android APK。

---

## ✅ 最简单的安装方法（推荐）

### 第1步：下载 Android Studio

访问官网下载：
```
https://developer.android.com/studio
```

**下载 Windows 版本**（约 1GB）

---

### 第2步：安装 Android Studio

1. 运行安装程序
2. 选择安装组件时，确保勾选：
   - ✅ Android SDK
   - ✅ Android SDK Platform
   - ✅ Android Virtual Device（可选）
3. 记住 SDK 安装路径（默认：`C:\Users\你的用户名\AppData\Local\Android\Sdk`）
4. 完成安装

---

### 第3步：首次启动配置

1. 打开 Android Studio
2. 首次启动会引导你完成设置
3. 在 "SDK Components Setup" 页面，确保安装：
   - ✅ Android SDK Platform（最新稳定版，如 Android 14/API 34）
   - ✅ Android SDK Build-Tools
   - ✅ Android SDK Command-line Tools
   - ✅ Android Emulator（可选）
4. 点击 "Finish" 开始下载（需要几分钟）

---

### 第4步：接受许可证

打开 **PowerShell**（管理员），执行：

```powershell
# 找到 SDK 路径（通常是）
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"

# 接受所有许可证
& "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat" --licenses

# 全部输入 y 接受
```

---

### 第5步：验证安装

```powershell
flutter doctor
```

应该看到：
```
[✓] Android toolchain - develop for Android devices (Android SDK version XX.X)
```

---

## 🔧 手动配置（如果自动检测失败）

### 方法1：设置环境变量

```powershell
# 永久设置（管理员权限）
[Environment]::SetEnvironmentVariable("ANDROID_HOME", "$env:LOCALAPPDATA\Android\Sdk", [EnvironmentVariableTarget]::Machine)
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$env:LOCALAPPDATA\Android\Sdk\platform-tools", [EnvironmentVariableTarget]::Machine)
```

然后重启 PowerShell。

---

### 方法2：Flutter 配置命令

```powershell
# 告诉 Flutter SDK 位置
flutter config --android-sdk C:\Users\你的用户名\AppData\Local\Android\Sdk
```

---

## 📋 快速检查清单

安装完成后，确保：

- [ ] Android Studio 已安装
- [ ] Android SDK Platform 已下载（至少一个版本）
- [ ] Android SDK Build-Tools 已安装
- [ ] 已接受所有许可证
- [ ] `flutter doctor` 显示 Android toolchain ✓
- [ ] ANDROID_HOME 环境变量已设置

---

## 💡 常见问题

### Q1: SDK 下载很慢

**解决**: 
- 使用国内镜像（在 Android Studio 设置中配置）
- 或者使用迅雷等工具加速下载

### Q2: 许可证接受失败

**解决**:
```powershell
# 以管理员身份运行 PowerShell
sdkmanager --licenses
# 逐个输入 y
```

### Q3: flutter doctor 仍然显示错误

**解决**:
```powershell
# 清除缓存后重试
flutter clean
flutter doctor
```

---

## 🚀 安装完成后

回到项目目录，运行：

```powershell
cd d:\工作\DJ机\harbeat_app

# 重新安装依赖
flutter pub get

# 生成代码
flutter pub run build_runner build --delete-conflicting-outputs

# 构建 APK
flutter build apk --release
```

---

## ⏱️ 预计时间

| 步骤 | 时间 |
|------|------|
| 下载 Android Studio | 5-10 分钟 |
| 安装 Android Studio | 5 分钟 |
| 下载 SDK 组件 | 10-20 分钟 |
| 接受许可证 | 2 分钟 |
| **总计** | **20-40 分钟** |

---

**准备好了吗？从第1步开始吧！** 🚀
