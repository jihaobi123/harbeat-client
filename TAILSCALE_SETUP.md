# Tailscale 连接配置指南

本文档说明如何配置 RK3588 和 Jetson 通过 Tailscale VPN 进行连接。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                    连接拓扑                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 路径 1: 局域网直连（最快）                               │  │
│  │                                                          │  │
│  │  Flutter App ◄──── LAN ────► RK3588                     │  │
│  │  (手机)                       192.168.1.101:9000        │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 路径 2: Tailscale VPN（备用）                            │  │
│  │                                                          │  │
│  │  Flutter App ◄── Tailscale ──► RK3588                   │  │
│  │  100.x.x.x                      100.x.x.x:9000          │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 路径 3: 云网关（远程访问）                               │  │
│  │                                                          │  │
│  │  Flutter App ◄── Internet ──► Gateway ──► RK3588        │  │
│  │                                8.136.120.255             │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ RK3588 ◄── Tailscale ──► Jetson                         │  │
│  │                           100.87.142.21:8000             │  │
│  │                                                          │  │
│  │ - 健康检查（每 5 秒）                                    │  │
│  │ - SessionEvent 上报（每 5 秒，批量 50 条）               │  │
│  │ - 音乐清单下载                                           │  │
│  │ - 音乐文件流式传输                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 1. Tailscale 安装

### 1.1 在 RK3588 上安装 Tailscale

```bash
# 方法 1: 使用官方安装脚本
curl -fsSL https://tailscale.com/install.sh | sh

# 方法 2: 手动安装（ARM64）
wget https://pkgs.tailscale.com/stable/tailscale_1.62.0_arm64.tgz
tar xzf tailscale_1.62.0_arm64.tgz
sudo cp tailscale_1.62.0_arm64/tailscale* /usr/bin/
sudo tailscaled --state=/var/lib/tailscale/tailscaled.state &

# 启动 Tailscale
sudo tailscale up

# 查看 Tailscale IP
tailscale ip -4
# 输出示例: 100.101.102.103
```

### 1.2 在 Jetson 上安装 Tailscale

```bash
# 使用官方安装脚本
curl -fsSL https://tailscale.com/install.sh | sh

# 启动 Tailscale
sudo tailscale up

# 查看 Tailscale IP（应该是 100.87.142.21）
tailscale ip -4
```

### 1.3 在 Flutter App（手机）上安装 Tailscale

- **iOS**: 从 App Store 下载 Tailscale
- **Android**: 从 Google Play 下载 Tailscale

安装后登录同一个 Tailscale 账号，所有设备会自动组网。

## 2. 配置 RK3588 Edge Agent

### 2.1 编辑 `.env` 文件

在 `edge-agent/.env` 中配置：

```bash
# RK 设备 ID
RK_ID=rk-001

# Jetson Tailscale IP（后端 API）
JETSON_BASE_URL=http://100.87.142.21:8000

# RK3588 的 Tailscale URL（填写 RK3588 的 Tailscale IP）
# 运行 `tailscale ip -4` 获取
TAILSCALE_URL=http://100.101.102.103:9000

# 云网关地址
GATEWAY_URL=http://8.136.120.255

# JWT Token（从 App 登录后获取）
JWT_TOKEN=your_jwt_token_here

# 可选的 RK Token
HARBEAT_RK_TOKEN=

# Edge Token（保护 API，可选）
EDGE_TOKEN=
```

### 2.2 启动 Edge Agent

```bash
cd edge-agent
python main.py
```

Edge Agent 会：
- 监听 `:9000` (REST API)
- 监听 `:9001` (WebSocket)
- 每 5 秒检查 Jetson 健康状态
- 每 5 秒上报 SessionEvent 到 Jetson

## 3. 验证连接

### 3.1 验证 RK3588 → Jetson 连接

```bash
# 在 RK3588 上测试
curl http://100.87.142.21:8000/health

# 预期输出
{"status":"ok","version":"..."}
```

### 3.2 验证 Flutter App → RK3588 连接

```bash
# 在手机上（通过 Tailscale）测试
curl http://100.101.102.103:9000/api/edge/info

# 预期输出（包含 tailscale_url 和 gateway_url）
{
  "ok": true,
  "audio_ready": true,
  "device_id": "rk-001",
  "name": "Cypher Edge (rk-001)",
  "tailscale_url": "http://100.101.102.103:9000",
  "gateway_url": "http://8.136.120.255",
  ...
}
```

## 4. Flutter App 连接优先级

Flutter App 会按以下顺序尝试连接 RK3588：

1. **局域网直连** (`192.168.1.101:9000`) - 最快，延迟 < 10ms
2. **Tailscale VPN** (`100.x.x.x:9000`) - 备用，延迟 20-50ms
3. **云网关** (`8.136.120.255`) - 远程访问，延迟 > 100ms

代码位置：[hardware_service.dart:268-289](d:\work\harbeat-app\lib\core\services\hardware_service.dart#L268-L289)

```dart
Future<String?> getBestConnectionUrl(RK3588DeviceInfo device) async {
  final List<String> urls = [];
  
  urls.add(device.localUrl);  // 优先局域网
  
  if (device.tailscaleUrl != null) {
    urls.add(device.tailscaleUrl!);  // 备用 Tailscale
  }
  
  if (device.gatewayUrl != null) {
    urls.add(device.gatewayUrl!);  // 最后云网关
  }
  
  for (final url in urls) {
    if (await testConnection(url)) {
      return url;  // 返回第一个可达的 URL
    }
  }
  
  return null;
}
```

## 5. 故障排查

### 5.1 RK3588 无法连接 Jetson

**症状**: Edge Agent 日志显示 `SessionEvent flush failed`

**排查步骤**:

```bash
# 1. 检查 Tailscale 状态
tailscale status

# 2. 检查 Jetson 是否可达
ping 100.87.142.21

# 3. 检查 Jetson API
curl http://100.87.142.21:8000/health

# 4. 检查防火墙
sudo ufw status
sudo ufw allow 8000/tcp
```

### 5.2 Flutter App 无法连接 RK3588

**症状**: App 显示 "设备不可达"

**排查步骤**:

```bash
# 1. 检查 RK3588 Tailscale 状态
tailscale status

# 2. 检查手机是否在 Tailscale 网络中
# 在手机 Tailscale App 中查看设备列表，确认 RK3588 在线

# 3. 在手机浏览器中访问
http://100.x.x.x:9000/api/edge/info

# 4. 检查 RK3588 防火墙
sudo ufw allow 9000/tcp
sudo ufw allow 9001/tcp
```

### 5.3 Tailscale IP 变化

Tailscale IP 通常是固定的，但如果设备重新加入网络，IP 可能会变化。

**解决方案**:

1. 在 Tailscale 管理后台设置固定 IP
2. 或使用 Tailscale 的 MagicDNS（设备名代替 IP）

```bash
# 使用 MagicDNS（需在 Tailscale 后台启用）
JETSON_BASE_URL=http://jetson-orin:8000
TAILSCALE_URL=http://rk3588-edge:9000
```

## 6. 性能优化

### 6.1 Tailscale 直连模式

Tailscale 默认会尝试 P2P 直连，如果失败会通过 DERP 中继。

```bash
# 检查连接模式
tailscale status

# 输出示例
# 100.87.142.21  jetson-orin          user@   linux   active; direct 192.168.1.100:41641
#                                                      ^^^^^^ 直连模式（最快）

# 如果显示 "relay"，说明使用中继（较慢）
# 100.87.142.21  jetson-orin          user@   linux   active; relay "tok"
```

**优化建议**:
- 确保设备在同一局域网或公网 IP 可达
- 开放 UDP 41641 端口（Tailscale 默认端口）
- 配置 UPnP 或手动端口转发

### 6.2 减少健康检查频率

如果 Tailscale 连接稳定，可以降低健康检查频率：

```bash
# 在 .env 中调整
EVENT_FLUSH_INTERVAL_SEC=10  # 从 5 秒改为 10 秒
```

## 7. 安全建议

1. **启用 Edge Token**: 在 `.env` 中设置 `EDGE_TOKEN`，保护 RK3588 API
2. **使用 JWT Token**: 确保 `JWT_TOKEN` 配置正确，用于 Jetson API 认证
3. **Tailscale ACL**: 在 Tailscale 管理后台配置访问控制列表，限制设备间访问
4. **定期更新**: 保持 Tailscale 客户端最新版本

## 8. 相关文件

- RK3588 配置: [edge-agent/config.py](edge-agent/edge_agent/config.py)
- RK3588 API: [edge-agent/main.py](edge-agent/main.py)
- Flutter 连接逻辑: [hardware_service.dart](d:\work\harbeat-app\lib\core\services\hardware_service.dart)
- API 配置: [api_config.dart](d:\work\harbeat-app\lib\core\config\api_config.dart)
- 部署配置: [cypher.env.example](deploy/cypher.env.example)

## 9. 常见问题

**Q: Tailscale 会增加多少延迟？**

A: 
- 直连模式: +5-10ms
- 中继模式: +50-200ms（取决于 DERP 服务器位置）

**Q: 是否必须使用 Tailscale？**

A: 不是必须的。如果设备在同一局域网，可以只使用局域网直连。Tailscale 主要用于：
- 设备不在同一局域网
- 需要远程访问
- 避免配置复杂的端口转发

**Q: 如何在生产环境部署？**

A: 
1. 在 Tailscale 后台为设备设置固定 IP 或启用 MagicDNS
2. 配置 Tailscale 开机自启: `sudo systemctl enable tailscaled`
3. 使用 systemd 管理 edge-agent 服务
4. 配置日志轮转和监控

**Q: 多个 RK3588 设备如何配置？**

A: 每个 RK3588 设备：
1. 使用不同的 `RK_ID`（如 rk-001, rk-002）
2. 加入同一个 Tailscale 网络
3. 获取各自的 Tailscale IP
4. 在 `.env` 中配置各自的 `TAILSCALE_URL`

## 10. 下一步

- [ ] 在 RK3588 上安装并启动 Tailscale
- [ ] 在 Jetson 上安装并启动 Tailscale（如果尚未安装）
- [ ] 配置 RK3588 的 `.env` 文件
- [ ] 启动 Edge Agent 并验证连接
- [ ] 在 Flutter App 中测试多路径连接
