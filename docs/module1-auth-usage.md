# 模块 1：用户管理（Auth）— 使用与测试说明

## 1. 后端服务

- **公开地址**：`http://8.136.120.255`（阿里云 ECS → nginx → harbeat-gateway → tailscale → Jetson harbeat:8000）
- **进程**：Jetson `mark@100.87.142.21` 上的 systemd 服务 `harbeat.service`
- **代码**：`/home/mark/harbeat/` (分支 `feature/harbeat-full-project`)

### Auth API 端点（Jetson 原生 schema 为准）

| 方法 | 路径 | 请求体 | 鉴权 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | `{username(2-50), password(8-64), dance_style?, level?, favorite_style?}` | 无 |
| POST | `/api/auth/login` | `{username, password}` | 无 |
| POST | `/api/auth/refresh` | `{refresh_token}` | 无 |
| POST | `/api/auth/logout` | _空_ | Bearer |
| POST | `/api/auth/change-password` | `{current_password, new_password(8-64)}` | Bearer |
| POST | `/api/auth/deactivate` | _空_ | Bearer |
| GET  | `/api/auth/me` | – | Bearer |

返回统一信封：`{code:0, message, data}`。`TokenData = {access_token, refresh_token, user_id, username, token_type:"bearer"}`。

## 2. 自动化 API 测试

```powershell
powershell -ExecutionPolicy Bypass -File d:\work\harbeat-client\scripts\test_auth_module.ps1
```

覆盖 10 项：register / login / me / me-401 / refresh / change-password / login-new / login-old-401 / 多设备并行 / logout / 重复注册-409。当前结果：**ALL AUTH TESTS PASSED**。

## 3. Web 网站（PC 浏览器）

- 直接打开：<http://8.136.120.255/>
- 操作：右下 `REGISTER` 切换到注册页 → 填写 username/password/STYLE/LEVEL → 提交 → 自动登录进入主界面。Logout 在左侧栏底部。
- 已验证：注册、登录、`getMe`、token 持久化（刷新页面仍在登录态）、Logout、再登录。
- 测试账号：`qa_web_demo_2026` / `WebDemo2026!`

如需重新部署 Web：

```powershell
cd d:\work\harbeat-client\web
npx vite build
cd dist
tar -czf ..\..\dist.tgz .
# scp 上传到 Jetson /home/mark/harbeat/web/dist/，再 sudo /bin/systemctl restart harbeat
```

## 4. Android 真机（USB 连线）

- 设备序列号：`130ddcca`（Android 12，arm64）
- Flutter：`D:\flutter_install\flutter\bin\flutter.bat`（3.29.3 / Dart 3.7.2）
- adb：`D:\android-sdk\platform-tools\adb.exe`
- JDK：`D:\jdk17\jdk-17.0.13+11`（必须 JDK 11+；系统默认 JDK 8 不行）
- Mobile 源码：`d:\work\harbeat-client\mobile\`
- `mobile/lib/src/app.dart` 默认 baseUrl 已改成 `http://8.136.120.255`，无需 `--dart-define`

### 构建并安装 Debug APK

```powershell
$env:JAVA_HOME = "D:\jdk17\jdk-17.0.13+11"
$env:Path = "$env:JAVA_HOME\bin;D:\flutter_install\flutter\bin;D:\android-sdk\platform-tools;" + $env:Path
cd d:\work\harbeat-client\mobile
flutter pub get
flutter build apk --debug
flutter install -d 130ddcca
```

### 真机操作

1. 打开手机上的 `HarBeat` 应用
2. `Register` → 输入 username / password / STYLE / LEVEL → 提交 → 进入 dashboard
3. 重启 App 验证 token 持久化（SharedPreferences）
4. 退出按钮（profile/设置）→ 重新登录

## 5. 故障排查

- **Jetson 起不来**：`ssh -i ... -J root@8.136.120.255 mark@100.87.142.21 'systemctl status harbeat'`；进程崩溃多半是 import 链脏；可 `cd /home/mark/harbeat && git status` 检查脏文件，必要时 `git stash`。
- **422 `current_password` Field required**：旧的客户端发了 `old_password`。后端唯一接受 `current_password`。
- **手机连不上后端**：手机必须在能访问 8.136.120.255 的网络。`adb shell ping -c 2 8.136.120.255` 验证。

## 6. 测试账号清单

| 账号 | 密码（当前） | 来源 |
| --- | --- | --- |
| `qa_mod1_1779907394` | `Pwd_new_1779907394!` | 脚本生成（API 测试） |
| `qa_web_demo_2026` | `WebDemo2026!` | 浏览器手工注册 |
