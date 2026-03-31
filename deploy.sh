#!/bin/bash
# HarBeat Full-Stack Deployment Script
# Run this on your server (the desktop PC)

set -e

echo "🎵 HarBeat 部署脚本"
echo "==================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "📋 未找到 .env 文件，从模板创建..."
    cp deploy/.env.example .env
    echo "⚠️  请编辑 .env 文件修改 JWT_SECRET 等配置"
    echo "   nano .env"
    exit 1
fi

# Build and start
echo "🔨 构建并启动服务..."
docker compose up -d --build

echo ""
echo "✅ 部署完成！"
echo ""

# Show local IP
echo "📡 局域网访问地址:"
if command -v hostname &> /dev/null; then
    hostname -I 2>/dev/null | awk '{for(i=1;i<=NF;i++) print "   http://" $i}'
fi
echo "   http://localhost"
echo ""
echo "📊 API 文档: http://localhost/docs"
echo ""
echo "📝 常用命令:"
echo "   查看日志:   docker compose logs -f app"
echo "   停止服务:   docker compose down"
echo "   重启服务:   docker compose restart"
