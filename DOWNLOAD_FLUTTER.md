# 🚀 Flutter SDK 下载和安装指南

## ⚡ 最快的方法（一键脚本）

### 方法1：使用 PowerShell 脚本（推荐）

```powershell
cd d:\工作\DJ机\harbeat_app
.\download_flutter.ps1
```

**脚本会自动：**
1. ✅ 检查 D:\flutter 是否已存在
2. ✅ 从清华镜像克隆 Flutter SDK（约 500MB）
3. ✅ 自动打开环境变量设置窗口
4. ✅ 显示下一步操作说明

**预计时间**: 5-15 分钟（取决于网速）

---

### 方法2：使用批处理脚本

```cmd
cd d:\工作\DJ机\harbeat_app
download_flutter.bat
```

---

## 📋 手动操作步骤

如果脚本无法运行，可以手动执行：

### 第1步：克隆 Flutter SDK

打开 **Git Bash** 或 **PowerShell**，执行：

```bash
# 切换到 D 盘根目录
cd D:\

# 从清华镜像克隆（稳定版）
git clone -b stable https://mirrors.tuna.tsinghua.edu.cn/git/flutter-sdk.git flutter
```

**或者使用 Git Bash：**
```bash
cd /d/
git clone -b stable https://mirrors.tuna.tsinghua.edu.cn/git/flutter-sdk.git flutter
```

---

### 第2步：等待下载完成

下载过程会显示进度：
```
Cloning into 'flutter'...
remote: Enumerating objects: 1126830, done.
remote: Counting objects: 100% (20110/20110), done.
...
Receiving objects: 100% (1126830/1126830), 498.33 MiB | 3.05 MiB/s, done.
```

**预计时间**: 
- 10Mbps 宽带：约 7 分钟
- 50Mbps 宽带：约 2 分钟
- 100Mbps 宽带：约 1 分钟

---

### 第3步：添加环境变量

#### 方法A：图形界面

1. 右键"此电脑" → 属性
2. 高级系统设置 → 环境变量
3. **系统变量**中找到 `Path` → 编辑
4. 点击"新建" → 输入：`D:\flutter\bin`
5. 确定 → 确定 → 确定
6. **关闭所有 PowerShell/CMD 窗口**
7. **重新打开**

#### 方法B：PowerShell 命令（管理员）

以**管理员身份**运行 PowerShell：
```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";D:\flutter\bin", [EnvironmentVariableTarget]::Machine)
```

然后**重启终端**

---

### 第4步：验证安装

打开**新的** PowerShell 窗口：

```powershell
flutter --version
```

应该看到类似输出：
```
Flutter 3.x.x • channel stable • https://github.com/flutter/flutter.git
Framework • revision xxxxx • 202x-xx-xx
Engine • revision xxxxx
Tools • Dart 3.x.x • DevTools 2.x.x
```

---

### 第5步：配置国内镜像（可选但推荐）

```powershell
# 永久设置
[Environment]::SetEnvironmentVariable("PUB_HOSTED_URL", "https://pub.flutter-io.cn", [EnvironmentVariableTarget]::User)
[Environment]::SetEnvironmentVariable("FLUTTER_STORAGE_BASE_URL", "https://storage.flutter-io.cn", [EnvironmentVariableTarget]::User)
```

---

### 第6步：检查环境

```powershell
flutter doctor
```

这会检查你的开发环境。如果有红色 ❌，按照提示安装缺失组件。

---

## 🔧 常见问题

### Q1: Git 未安装

**错误信息**: `'git' is not recognized as an internal or external command`

**解决**:
1. 下载 Git: https://git-scm.com/download/win
2. 安装时勾选"Add Git to PATH"
3. 重启终端后重试

---

### Q2: 克隆失败/网络超时

**错误信息**: `error: RPC failed; curl 28 Failed to connect`

**解决**:

**方案1**: 增加 Git 缓冲区
```bash
git config --global http.postBuffer 524288000
git config --global http.lowSpeedLimit 0
git config --global http.lowSpeedTime 999999
```

**方案2**: 使用代理（如果有）
```bash
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

**方案3**: 稍后重试（网络波动）

---

### Q3: D 盘空间不足

**检查空间**:
```powershell
Get-PSDrive D | Select-Object Used,Free
```

**清理空间**:
- 删除临时文件
- 清空回收站
- 卸载不用的软件

**需要空间**: 至少 5GB（Flutter SDK + 缓存）

---

### Q4: flutter 命令找不到

**原因**: 环境变量未生效

**解决**:
1. 确认 `D:\flutter\bin\flutter.bat` 文件存在
2. 确认已添加到 PATH
3. **必须重启终端窗口**
4. 运行 `echo $env:Path` 检查是否包含 `D:\flutter\bin`

---

### Q5: 下载速度太慢

**清华镜像应该很快**（10MB/s+），如果还是很慢：

1. 检查网络连接
2. 尝试其他时间段
3. 使用下载工具（如迅雷）加速 Git
4. 或使用手机热点（有时更快）

---

## ✅ 验证清单

下载完成后，确保：

- [ ] `D:\flutter` 文件夹存在
- [ ] `D:\flutter\bin\flutter.bat` 文件存在
- [ ] `D:\flutter\bin\dart.exe` 文件存在
- [ ] 已将 `D:\flutter\bin` 添加到系统 PATH
- [ ] 已重启终端窗口
- [ ] `flutter --version` 显示版本号
- [ ] `flutter doctor` 无严重错误

---

## 📊 下载文件大小

| 项目 | 大小 |
|------|------|
| Flutter SDK (Git) | ~500 MB |
| 首次运行下载组件 | ~1-2 GB |
| 总计需要空间 | ~3-5 GB |

---

## 🎯 下一步

Flutter 安装完成后：

1. **配置 USB 调试**（Android 手机）
   ```
   设置 → 关于手机 → 点击版本号7次 → 开发者选项 → USB 调试
   ```

2. **连接手机**
   - USB 连接手机和电脑
   - 手机上授权 USB 调试

3. **运行应用**
   ```powershell
   cd d:\工作\DJ机\harbeat_app
   flutter run
   ```

---

## 💡 提示

- **清华镜像速度**: 通常 5-10 MB/s
- **预计总时间**: 下载 5-15 分钟 + 配置 2 分钟
- **磁盘要求**: D 盘至少 5GB 可用空间
- **内存要求**: 建议 8GB+ RAM

---

**准备好了吗？开始吧！** 🚀

```powershell
cd d:\工作\DJ机\harbeat_app
.\download_flutter.ps1
```
