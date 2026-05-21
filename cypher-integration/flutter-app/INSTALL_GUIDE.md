# 📱 HarBeat App 手机安装完全指南

## 🚀 快速开始（推荐新手）

### Android 手机 - 3步安装法

```bash
# 第1步：运行构建脚本
cd d:\工作\DJ机\harbeat_app
.\build_apk.ps1

# 第2步：选择"2. 安装到已连接设备"
# 确保手机已通过 USB 连接并开启调试模式

# 第3步：在手机上打开应用
```

---

## 📋 详细安装方法

### 方法一：USB 调试安装（开发最快）⭐

#### ✅ 优点
- 无需生成 APK 文件
- 一键安装并运行
- 支持热重载调试

#### ❌ 缺点
- 需要保持 USB 连接
- 每次重新安装会覆盖旧版本

#### 📝 操作步骤

**Android:**

1. **开启开发者模式**
   ```
   设置 → 关于手机 → 连续点击"版本号"7次
   返回 → 系统/更多设置 → 开发者选项
   ```

2. **启用 USB 调试**
   ```
   开发者选项 → 找到"USB 调试" → 开启
   ```

3. **连接电脑**
   - 用 USB 线连接手机和电脑
   - 手机弹出"允许 USB 调试？" → 点击"允许"
   - 勾选"始终允许这台计算机"

4. **验证连接**
   ```bash
   flutter devices
   # 应该看到类似输出:
   # 1 connected device:
   # • XXXX (mobile) • android-arm64 • Android XX (API XX)
   ```

5. **安装运行**
   ```bash
   cd d:\工作\DJ机\harbeat_app
   flutter run
   ```

**iOS (需要 Mac):**

1. **安装 Xcode**
   - Mac App Store 下载 Xcode
   - 首次打开需同意协议

2. **配置开发者账号**
   ```
   Xcode → Preferences → Accounts → + → Apple ID
   ```

3. **信任电脑**
   - USB 连接 iPhone 和 Mac
   - 手机弹出"信任此电脑？" → 点击"信任"

4. **安装运行**
   ```bash
   flutter devices
   flutter run -d <device_id>
   ```

---

### 方法二：APK 手动安装（最稳定）✅

#### ✅ 优点
- 无需 USB 连接
- 可分享给他人测试
- 离线安装

#### ❌ 缺点
- 需要手动传输文件
- 无法实时调试

#### 📝 操作步骤

**第1步：构建 APK**
```bash
cd d:\工作\DJ机\harbeat_app
flutter build apk --release
```

**第2步：找到 APK 文件**
```
位置: d:\工作\DJ机\harbeat_app\build\app\outputs\flutter-apk\app-release.apk
大小: 约 30-50 MB
```

**第3步：传输到手机**

**方式 A：USB 拷贝**
```
1. USB 连接手机和电脑
2. 手机选择"文件传输"模式
3. 将 APK 复制到手机存储（如 Download 文件夹）
```

**方式 B：微信/QQ 发送**
```
1. 电脑上打开微信/QQ
2. 将 APK 拖入"文件传输助手"
3. 手机上接收文件
```

**方式 C：局域网 HTTP 服务器**
```bash
# 在电脑上启动 HTTP 服务器
cd d:\工作\DJ机\harbeat_app\build\app\outputs\flutter-apk
python -m http.server 8080

# 查看电脑 IP 地址
ipconfig
# 找到 IPv4 地址，例如: 192.168.1.100

# 手机浏览器访问
http://192.168.1.100:8080/app-release.apk
```

**方式 D：云盘分享**
```
上传到百度网盘/阿里云盘 → 生成分享链接 → 手机下载
```

**第4步：手机安装**

1. **打开文件管理器**
   ```
   找到下载的 APK 文件
   ```

2. **点击安装**
   ```
   如果提示"禁止安装未知来源应用":
   
   Android 8+:
   设置 → 应用 → 特殊应用权限 → 安装未知应用 → 允许
   
   Android 7-:
   设置 → 安全 → 未知来源 → 允许
   ```

3. **完成安装**
   ```
   等待安装完成 → 点击"打开"
   ```

---

### 方法三：无线调试安装（Android 11+）🚀

#### ✅ 优点
- 无需 USB 线
- 方便快捷

#### ❌ 缺点
- 仅支持 Android 11+
- 首次配对较复杂

#### 📝 操作步骤

**1. 开启无线调试**
```
设置 → 开发者选项 → 无线调试 → 开启
```

**2. 配对设备**
```
无线调试 → 使用配对码配对设备
记下 IP 地址、端口和配对码
```

**3. 电脑配对**
```bash
# 安装 ADB（如果未安装）
# https://developer.android.com/studio/releases/platform-tools

# 配对
adb pair 192.168.1.XXX:XXXXX
# 输入配对码

# 连接
adb connect 192.168.1.XXX:XXXXX
```

**4. 安装应用**
```bash
flutter run
```

---

## 🔧 常见问题解决

### ❌ 问题1：找不到设备

**症状**: `flutter devices` 显示 "No devices found"

**解决**:
```bash
# Android
1. 检查 USB 线是否连接正常
2. 确认已开启 USB 调试
3. 手机上授权了 USB 调试
4. 尝试更换 USB 线或 USB 口
5. 重启 ADB 服务:
   adb kill-server
   adb start-server

# iOS
1. 确认 Xcode 已安装
2. 确认已信任电脑
3. 解锁 iPhone 屏幕
4. 重启 Xcode
```

---

### ❌ 问题2：安装失败

**症状**: `flutter install` 报错

**解决**:
```bash
# 方法1：清理后重新构建
flutter clean
flutter pub get
flutter build apk --release

# 方法2：卸载旧版本
adb uninstall com.harbeat

# 方法3：手动安装 APK
adb install build/app/outputs/flutter-apk/app-release.apk
```

---

### ❌ 问题3：应用闪退

**症状**: 安装成功但打开即崩溃

**解决**:
```bash
# 查看日志
flutter logs

# 常见原因:
1. API 地址配置错误
   → 检查 lib/core/config/api_config.dart

2. 缺少权限
   → 检查 AndroidManifest.xml / Info.plist

3. 依赖包版本冲突
   → flutter clean && flutter pub get
```

---

### ❌ 问题4：蓝牙无法连接

**症状**: 扫描不到设备或连接失败

**解决**:
```
Android:
1. 确认已授予位置权限
   设置 → 应用 → HarBeat → 权限 → 位置 → 允许

2. 确认蓝牙已开启
   下拉通知栏 → 开启蓝牙

3. 确认设备处于配对模式

iOS:
1. 确认 Info.plist 中有蓝牙权限描述
2. 重启蓝牙
3. 忘记设备后重新配对
```

---

### ❌ 问题5：音频无法播放

**症状**: 点击播放无声音

**解决**:
```
1. 检查网络连接
   → 确认能访问 API 服务器

2. 检查音量
   → 媒体音量是否调大

3. 检查蓝牙路由
   → 如果连接了蓝牙，音频会输出到蓝牙设备

4. 查看日志
   flutter logs | grep -i audio
```

---

## 📊 不同场景推荐方案

| 场景 | 推荐方法 | 原因 |
|------|---------|------|
| **日常开发调试** | USB 调试 (`flutter run`) | 支持热重载，快速迭代 |
| **给同事测试** | APK 手动安装 | 无需连接电脑，方便分发 |
| **远程用户测试** | 构建 APK + 云盘分享 | 不受地域限制 |
| **正式发布前** | Release APK 真机测试 | 模拟真实环境 |
| **iOS 测试** | TestFlight | 苹果官方分发渠道 |

---

## 🎯 完整测试清单

### Android 测试

- [ ] USB 调试安装成功
- [ ] APK 手动安装成功
- [ ] 应用正常启动
- [ ] 登录/注册功能正常
- [ ] 音乐库加载正常
- [ ] 音频播放正常
- [ ] 后台播放正常
- [ ] 蓝牙扫描正常
- [ ] 蓝牙连接正常
- [ ] 蓝牙音频输出正常
- [ ] 横竖屏切换正常
- [ ] 低电量模式正常

### iOS 测试（需要 Mac）

- [ ] Xcode 编译成功
- [ ] 真机安装成功
- [ ] 所有功能正常
- [ ] 后台播放正常
- [ ] 锁屏控制正常
- [ ] 蓝牙连接正常

---

## 💡 高级技巧

### 1. 批量安装到多个设备
```bash
# 获取所有设备 ID
flutter devices

# 依次安装
flutter run -d device1
flutter run -d device2
```

### 2. 生成带签名的 APK
```bash
# 创建密钥库
keytool -genkey -v -keystore harbeat.jks -keyalg RSA -keysize 2048 -validity 10000 -alias harbeat

# 配置签名
# android/key.properties
storePassword=your_password
keyPassword=your_password
keyAlias=harbeat
storeFile=../harbeat.jks

# 构建签名 APK
flutter build apk --release
```

### 3. 监控安装过程
```bash
# 实时查看日志
flutter logs

# 过滤特定日志
flutter logs | grep -i error
flutter logs | grep -i audio
```

### 4. 性能分析
```bash
# 启用性能监控
flutter run --profile

# 查看帧率
DevTools → Performance
```

---

## 📞 需要帮助？

1. 查看日志: `flutter logs`
2. 查阅文档: [README.md](README.md)
3. Flutter 社区: https://flutter.dev/community
4. 提交 Issue: GitHub Issues

---

**祝你安装顺利！** 🎉

如有问题，请提供:
- 手机型号和系统版本
- 错误日志截图
- 具体操作步骤
