#!/bin/bash
# RK3588 Tailscale 安装和配置脚本
# 在 RK3588 上以 root 或 sudo 权限执行

echo "=========================================="
echo "RK3588 Tailscale 配置脚本"
echo "=========================================="

# 1. 检查当前网络配置
echo -e "\n[1/6] 检查当前网络配置..."
hostname
ip addr show | grep "inet "

# 2. 安装 Tailscale
echo -e "\n[2/6] 安装 Tailscale..."
if ! command -v tailscale &> /dev/null; then
    echo "正在下载并安装 Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
else
    echo "Tailscale 已安装"
fi

# 3. 启动 Tailscale
echo -e "\n[3/6] 启动 Tailscale..."
sudo tailscale up

# 4. 获取 Tailscale IP
echo -e "\n[4/6] 获取 Tailscale IP..."
TAILSCALE_IP=$(tailscale ip -4)
echo "Tailscale IP: $TAILSCALE_IP"

# 5. 配置 edge-agent .env
echo -e "\n[5/6] 配置 edge-agent..."
EDGE_AGENT_DIR="$HOME/cypher-rk3588/edge-agent"
if [ -d "$EDGE_AGENT_DIR" ]; then
    cd "$EDGE_AGENT_DIR"

    # 创建 .env 文件
    cat > .env << EOF
# RK3588 Edge Agent Configuration
RK_ID=rk-001
JETSON_BASE_URL=http://100.87.142.21:8000
JWT_TOKEN=
HARBEAT_RK_TOKEN=
EDGE_TOKEN=
SYNC_WORKER_URL=http://127.0.0.1:9100
AUDIO_SOCKET=/tmp/cypher-audio.sock
CYPHER_HOME=/home/cat/cypher
EVENT_FLUSH_INTERVAL_SEC=5
EVENT_FLUSH_BATCH_SIZE=50
REST_HOST=0.0.0.0
REST_PORT=9000
WS_HOST=0.0.0.0
WS_PORT=9001

# Tailscale URL (自动填充)
TAILSCALE_URL=http://${TAILSCALE_IP}:9000
GATEWAY_URL=http://8.136.120.255
EOF

    echo "✓ .env 文件已创建"
    cat .env
else
    echo "⚠ edge-agent 目录不存在: $EDGE_AGENT_DIR"
fi

# 6. 测试 Jetson 连接
echo -e "\n[6/6] 测试 Jetson 连接..."
curl -s --connect-timeout 5 http://100.87.142.21:8000/health && echo -e "\n✓ Jetson 连接成功" || echo -e "\n✗ Jetson 连接失败"

echo -e "\n=========================================="
echo "配置完成！"
echo "=========================================="
echo "Tailscale IP: $TAILSCALE_IP"
echo "RK3588 局域网 IP: $(ip addr show | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | cut -d/ -f1 | head -1)"
echo ""
echo "下一步："
echo "1. 启动 edge-agent: cd $EDGE_AGENT_DIR && python main.py"
echo "2. 在 Flutter App 中扫描设备"
echo "=========================================="
