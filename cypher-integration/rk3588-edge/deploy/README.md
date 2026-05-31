# Cypher systemd 部署

## 安装（一次性）

```bash
sudo bash ~/cypher/deploy/install-systemd.sh
```

## 启停

```bash
# 启动全部
sudo systemctl start cypher.target

# 停止全部
sudo systemctl stop cypher.target

# 开机自启（install 脚本已 enable）
sudo systemctl enable cypher.target
```

## 状态与日志

```bash
systemctl status cypher.target
systemctl status cypher-audio-engine cypher-edge-agent cypher-input-daemon

journalctl -u cypher-audio -f
journalctl -u cypher-edge -f
journalctl -u cypher-input -f
```

## 配置

编辑 `~/cypher/deploy/cypher.env` 后：

```bash
sudo systemctl restart cypher.target
```

## 服务顺序

1. `cypher-audio-engine` — Unix socket 播放
2. `cypher-edge-agent` — HTTP :9000 / WS :9001
3. `cypher-input-daemon` — 九键（需 `input` 组，服务里已 `SupplementaryGroups=input`）
4. `cypher-sync-worker` — Jetson manifest 下载与 sha256 校验（本机 `:9100`）

## 验证

```bash
curl -s http://127.0.0.1:9000/health
```
