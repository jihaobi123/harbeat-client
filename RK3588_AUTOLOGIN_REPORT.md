# RK3588 自动登录和开机自启配置完成报告

## 配置时间
2026-05-27

## 设备信息
- **主机名**: lubancat
- **IP 地址**: 192.168.43.7
- **操作系统**: Ubuntu 22.04.5 LTS
- **用户**: cat
- **网络接口**: wlan0 (WiFi)
- **网关**: 192.168.43.1

## 已完成的配置

### 1. ✅ TTY1 自动登录
- **配置文件**: `/etc/systemd/system/getty@tty1.service.d/autologin.conf`
- **状态**: 已启用并运行
- **效果**: 开机后自动以 `cat` 用户登录到 tty1，无需输入密码

配置内容：
```ini
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin cat --noclear %I $TERM
```

### 2. ✅ 网络服务自动启动
- **NetworkManager**: enabled
- **状态**: 开机自动连接 WiFi (wlan0)
- **IP 分配**: DHCP (当前 192.168.43.7)

### 3. ✅ SSH 服务自动启动
- **服务**: ssh.service
- **状态**: enabled
- **端口**: 22
- **效果**: 开机后可立即通过 SSH 连接

### 4. ✅ Cypher 服务自动启动
所有 Cypher 相关服务已配置为开机自动启动：

| 服务 | 状态 | 说明 |
|------|------|------|
| `cypher.target` | enabled | Cypher 服务组 |
| `cypher-audio-engine.service` | enabled | 音频引擎 |
| `cypher-edge-agent.service` | enabled | Edge Agent (REST API :9000, WebSocket :9001) |
| `cypher-input-daemon.service` | enabled | 输入设备守护进程 |

当前运行状态：
```
cat  942  /home/cat/venvs/edge/bin/python /home/cat/cypher/audio-engine/main.py
cat  944  /home/cat/venvs/edge/bin/python /home/cat/cypher/edge-agent/run.py
cat  945  /home/cat/venvs/edge/bin/python /home/cat/cypher/input-daemon/main.py
```

## 开机流程

现在 RK3588 的开机流程如下：

```
1. 上电
   ↓
2. BIOS/UEFI 启动
   ↓
3. Linux 内核加载
   ↓
4. systemd 初始化
   ↓
5. NetworkManager 启动 → WiFi 自动连接 → 获取 IP (192.168.43.7)
   ↓
6. SSH 服务启动 → 端口 22 开放
   ↓
7. cypher.target 启动
   ├─ cypher-audio-engine.service
   ├─ cypher-edge-agent.service (REST :9000, WebSocket :9001)
   └─ cypher-input-daemon.service
   ↓
8. getty@tty1 启动 → 自动登录用户 cat
   ↓
9. 系统就绪 ✓
```

## 验证测试

### 测试 1: SSH 连接
```bash
ssh cat@192.168.43.7
# 输入密码: temppwd
# 预期: 成功登录
```

### 测试 2: Edge Agent API
```bash
curl http://192.168.43.7:9000/api/edge/info
# 预期: 返回设备信息 JSON
```

### 测试 3: 重启测试
```bash
ssh cat@192.168.43.7
sudo reboot

# 等待 1-2 分钟后
ping 192.168.43.7
# 预期: 网络可达

ssh cat@192.168.43.7
# 预期: 可以 SSH 连接

curl http://192.168.43.7:9000/api/edge/info
# 预期: Edge Agent 已自动启动
```

## 故障排查

### 问题 1: 开机后无法 SSH 连接

**可能原因**:
1. WiFi 未自动连接
2. IP 地址变化（DHCP 分配了新 IP）
3. SSH 服务未启动

**排查步骤**:
```bash
# 1. 扫描网络找到 RK3588
nmap -sn 192.168.43.0/24

# 2. 检查 SSH 端口
nc -zv 192.168.43.7 22

# 3. 如果能物理访问设备，检查 tty1 是否自动登录
# 应该看到自动登录到 cat 用户的终端
```

### 问题 2: Edge Agent 未启动

**排查步骤**:
```bash
ssh cat@192.168.43.7
systemctl status cypher-edge-agent
journalctl -u cypher-edge-agent -n 50
```

### 问题 3: WiFi 未自动连接

**排查步骤**:
```bash
ssh cat@192.168.43.7  # 如果能连接
nmcli connection show
nmcli device status

# 检查 WiFi 配置
cat /etc/NetworkManager/system-connections/*.nmconnection
```

## 安全建议

⚠️ **重要**: 当前配置为了方便开发，使用了自动登录。在生产环境中建议：

1. **禁用 TTY 自动登录**（保留 SSH 和服务自启）
2. **更改默认密码** `temppwd` 为强密码
3. **配置 SSH 密钥认证**，禁用密码登录
4. **配置防火墙**，限制 SSH 访问来源

## 下一步

现在 RK3588 已经配置完成，可以：

1. ✅ 开机自动登录（无需输入密码）
2. ✅ 开机自动连接网络
3. ✅ 开机自动启动 SSH 服务
4. ✅ 开机自动启动 Edge Agent 服务

**你可以直接拔掉电源再上电测试，RK3588 会自动启动所有服务，无需任何手动操作。**

## 相关文件

- 自动登录配置: `/etc/systemd/system/getty@tty1.service.d/autologin.conf`
- Cypher 服务: `/etc/systemd/system/cypher*.service`
- Edge Agent: `/home/cat/cypher/edge-agent/`
- 网络配置: `/etc/NetworkManager/system-connections/`

## 联系信息

- RK3588 SSH: `ssh cat@192.168.43.7` (密码: temppwd)
- Edge Agent API: `http://192.168.43.7:9000`
- WebSocket: `ws://192.168.43.7:9001`
