#!/bin/bash
set -e
if [[ "$(id -u)" -ne 0 ]]; then
  echo "请使用 sudo 运行"
  exit 1
fi
systemctl stop cypher.target 2>/dev/null || true
systemctl disable cypher.target cypher-audio-engine cypher-edge-agent cypher-input-daemon 2>/dev/null || true
rm -f /etc/systemd/system/cypher.target \
      /etc/systemd/system/cypher-audio-engine.service \
      /etc/systemd/system/cypher-edge-agent.service \
      /etc/systemd/system/cypher-input-daemon.service
systemctl daemon-reload
echo "已卸载 Cypher systemd 单元"
