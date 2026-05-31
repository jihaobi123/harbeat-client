#!/bin/bash
# 安装并启用 Cypher systemd 服务（需 sudo）
set -e

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="/etc/systemd/system"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请使用 sudo 运行: sudo bash $0"
  exit 1
fi

for unit in cypher.target cypher-audio-engine.service cypher-edge-agent.service cypher-input-daemon.service cypher-sync-worker.service; do
  install -m 644 "$DEPLOY_DIR/$unit" "$UNIT_DIR/$unit"
  echo "installed $UNIT_DIR/$unit"
done

# 兼容旧文件名（若曾安装过）
for old in edge-agent audio-engine input-daemon; do
  rm -f "$UNIT_DIR/${old}.service" 2>/dev/null || true
done

systemctl daemon-reload
systemctl enable cypher.target
systemctl enable cypher-audio-engine.service cypher-edge-agent.service cypher-input-daemon.service cypher-sync-worker.service

echo ""
echo "已 enable。启动: systemctl start cypher.target"
echo "状态:   systemctl status cypher.target"
echo "日志:   journalctl -u cypher-audio -u cypher-edge -u cypher-input -u cypher-sync -f"
