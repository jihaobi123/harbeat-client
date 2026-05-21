# 🚀 立即获取 HarBeat APK

## ⚡ 最快的方法（10分钟）

### 一键完成所有步骤

```powershell
# 打开 PowerShell，复制粘贴以下命令：
cd d:\工作\DJ机\harbeat_app
.\install_flutter_and_build.ps1
```

**脚本会自动：**
1. ✅ 检测是否已安装 Flutter
2. ✅ 如果未安装，自动下载并安装 Flutter
3. ✅ 安装项目依赖
4. ✅ 生成必要代码
5. ✅ 构建 Release APK
6. ✅ 显示 APK 位置

---

## 📱 APK 最终位置

构建成功后，APK 文件在这里：

```
d:\工作\DJ机\harbeat_app\build\app\outputs\flutter-apk\app-release.apk
```

**文件大小**: 约 30-50 MB

---

## 🎯 三种安装到手机的方法

### 方法1：USB 直接安装（最快）

```powershell
# 1. USB 连接手机和电脑
# 2. 手机开启 USB 调试
# 3. 运行：
cd d:\工作\DJ机\harbeat_app
flutter install
```

### 方法2：微信/QQ 发送

```
1. 电脑上找到 APK 文件
2. 拖入微信"文件传输助手"
3. 手机上接收并安装
```

### 方法3：局域网下载

```powershell
# 在电脑上启动 HTTP 服务器
cd d:\工作\DJ机\harbeat_app\build\app\outputs\flutter-apk
python -m http.server 8080

# 手机浏览器访问（替换为你的电脑IP）
http://192.168.1.100:8080/app-release.apk
```

---

## ❓ 如果遇到问题

### 问题1：PowerShell 无法运行脚本

**解决**:
```powershell
# 以管理员身份运行 PowerShell，执行：
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 问题2：Git 未安装

**解决**:
```
下载: https://git-scm.com/download/win
安装后重新运行脚本
```

### 问题3：网络太慢

**解决**: 使用国内镜像
```powershell
$env:PUB_HOSTED_URL="https://pub.flutter-io.cn"
$env:FLUTTER_STORAGE_BASE_URL="https://storage.flutter-io.cn"
.\install_flutter_and_build.ps1
```

---

## 💡 不想自己构建？

如果你现在就要 APK，可以：

1. **找有 Flutter 环境的同事帮忙构建**
   - 把 `d:\工作\DJ机\harbeat_app` 文件夹打包发给他
   - 让他运行 `flutter build apk --release`
   - 把生成的 APK 发回给你

2. **使用在线构建服务**（需要配置 CI/CD）
   - GitHub Actions
   - Codemagic
   - Bitrise

---

## 📞 需要帮助？

查看详细指南：
- [BUILD_APK_GUIDE.md](BUILD_APK_GUIDE.md) - 完整构建指南
- [INSTALL_GUIDE.md](INSTALL_GUIDE.md) - 手机安装指南
- [README.md](README.md) - 项目文档

---

**准备好了吗？现在就运行脚本吧！** 🚀

```powershell
cd d:\工作\DJ机\harbeat_app
.\install_flutter_and_build.ps1
```
