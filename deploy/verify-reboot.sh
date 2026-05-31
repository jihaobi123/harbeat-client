#!/bin/bash
# RK3588 重启后验证脚本

RK_IP="192.168.43.7"

echo "=========================================="
echo "RK3588 重启验证测试"
echo "=========================================="

# 测试 1: 网络连通性
echo -e "\n[测试 1/5] 网络连通性..."
if ping -n 2 -w 2000 $RK_IP 2>&1 | grep -q "TTL="; then
    echo "✓ 网络可达"
else
    echo "✗ 网络不可达"
    exit 1
fi

# 测试 2: SSH 服务
echo -e "\n[测试 2/5] SSH 服务..."
if nc -zv -w 5 $RK_IP 22 2>&1 | grep -q "succeeded"; then
    echo "✓ SSH 端口 22 开放"
else
    echo "✗ SSH 服务未启动"
fi

# 测试 3: Edge Agent REST API
echo -e "\n[测试 3/5] Edge Agent REST API (端口 9000)..."
RESPONSE=$(curl -s --connect-timeout 5 http://$RK_IP:9000/api/edge/info 2>&1)
if echo "$RESPONSE" | grep -q '"ok":true'; then
    echo "✓ Edge Agent API 正常"
    echo "$RESPONSE" | head -3
else
    echo "✗ Edge Agent API 未响应"
fi

# 测试 4: WebSocket 端口
echo -e "\n[测试 4/5] WebSocket 服务 (端口 9001)..."
if nc -zv -w 5 $RK_IP 9001 2>&1 | grep -q "succeeded"; then
    echo "✓ WebSocket 端口 9001 开放"
else
    echo "✗ WebSocket 服务未启动"
fi

# 测试 5: 系统服务状态
echo -e "\n[测试 5/5] Cypher 服务状态..."
ssh -o StrictHostKeyChecking=no cat@$RK_IP "systemctl is-active cypher-edge-agent && systemctl is-active cypher-audio-engine && systemctl is-active cypher-input-daemon" <<< "temppwd" 2>&1 | grep -q "active" && echo "✓ Cypher 服务运行中" || echo "⚠ 部分服务未启动"

echo -e "\n=========================================="
echo "验证完成！"
echo "=========================================="
