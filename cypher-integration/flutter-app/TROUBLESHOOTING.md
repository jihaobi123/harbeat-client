# HarBeat 移动端 - 常见问题解答

## 📱 问题 1: Chrome 中出现 "DioException [connection timeout]"

### 原因
- API 服务器（`https://8.136.120.255`）未运行或无法访问
- 默认超时时间为 10 秒，对于网络较慢的情况不够

### 解决方案

#### ✅ 方案 A：切换 API 地址（推荐）

1. **打开应用**
2. **点击底部导航栏的"设置"图标** ⚙️
3. **选择 API 服务器：**
   - **生产环境**: `https://8.136.120.255`（需要服务器运行）
   - **开发环境**: `http://192.168.1.100:8000`（本地 RK3588）
   - **本地测试**: `http://localhost:8000`（Windows 本机）

4. **超时时间已自动增加到 30 秒**

#### ✅ 方案 B：暂时忽略错误

- 应用仍然可以正常运行
- 只是无法加载远程数据（音乐库、用户信息等）
- 可以使用离线功能（如果已实现）

#### ✅ 方案 C：启动本地 API 服务器

如果你有后端代码，可以在本地启动：

```bash
cd d:\工作\DJ机\harbeat-client-dj-mix
docker-compose up -d
```

然后切换到"本地测试"环境。

---

## 📦 问题 2: APK 构建为什么这么慢？

### 正常构建时间

| 构建类型 | 首次构建 | 后续构建 |
|---------|---------|---------|
| Debug   | 3-5 分钟 | 1-2 分钟 |
| Release | 5-15 分钟 | 2-5 分钟 |

### 为什么慢？

1. **Gradle 下载** (首次) - 100-200 MB
2. **Dart 编译** - 将所有 Dart 代码编译为 ARM64 原生代码
3. **资源打包** - 图片、字体、音频文件
4. **代码优化** - Release 模式会进行树摇和压缩
5. **APK 签名** - 加密处理

### 加速方法

#### 方法 1: 使用 ABI 分割（推荐）

```bash
flutter build apk --release --split-per-abi
```

这会生成三个更小的 APK：
- `app-armeabi-v7a-release.apk` (约 15 MB)
- `app-arm64-v8a-release.apk` (约 18 MB)
- `app-x86_64-release.apk` (约 20 MB)

#### 方法 2: 清理后重新构建

```bash
flutter clean
flutter build apk --release
```

#### 方法 3: 只构建调试版本（快速测试）

```bash
flutter build apk --debug
```

⚠️ **注意**: Debug 版本不能发布到应用商店，但可以快速测试功能。

### 查看构建进度

```bash
# 在另一个终端窗口查看
tail -f /tmp/apk_build.log
```

### APK 输出位置

构建完成后，APK 文件位于：

```
d:\工作\DJ机\harbeat_app\build\app\outputs\flutter-apk\
├── app-release.apk              # 通用 APK (约 40-50 MB)
└── app-arm64-v8a-release.apk    # ARM64 专用 (如果使用 --split-per-abi)
```

---

## 🔧 其他常见问题

### Q: 如何热重载应用？

在 Chrome 中运行时：
- 按键盘 `r` - 热重载（保持状态）
- 按键盘 `R` - 热重启（重置状态）

### Q: 如何停止应用？

在终端中按 `q` 键退出。

### Q: 如何重新运行应用？

```bash
cd "/d/工作/DJ机/harbeat_app"
flutter run -d chrome
```

### Q: 构建失败怎么办？

1. 清理项目：
   ```bash
   flutter clean
   flutter pub get
   ```

2. 重新构建：
   ```bash
   flutter build apk --release
   ```

3. 查看详细错误：
   ```bash
   flutter build apk --release --verbose
   ```

---

## 📞 需要帮助？

如果遇到问题，请检查：

1. ✅ Flutter 版本是否正确：`flutter --version`
2. ✅ 依赖是否安装：`flutter pub get`
3. ✅ 代码是否有错误：`flutter analyze`
4. ✅ Android SDK 是否配置：`flutter doctor -v`

---

**最后更新**: 2026-05-13
