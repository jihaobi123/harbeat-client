# HarBeat Full-Stack Deployment Script (Windows)
# Run this on your server (the desktop PC)

Write-Host "🎵 HarBeat 部署脚本" -ForegroundColor Cyan
Write-Host "===================" -ForegroundColor Cyan

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "📋 未找到 .env 文件，从模板创建..." -ForegroundColor Yellow
    Copy-Item "deploy\.env.example" ".env"
    Write-Host "⚠️  请编辑 .env 文件修改 JWT_SECRET 等配置" -ForegroundColor Red
    Write-Host "   notepad .env"
    exit 1
}

# Build and start
Write-Host "🔨 构建并启动服务..." -ForegroundColor Green
docker compose up -d --build

Write-Host ""
Write-Host "✅ 部署完成！" -ForegroundColor Green
Write-Host ""

# Show local IP
Write-Host "📡 局域网访问地址:" -ForegroundColor Cyan
$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback" -and $_.IPAddress -ne "127.0.0.1" }
foreach ($ip in $ips) {
    Write-Host "   http://$($ip.IPAddress)" -ForegroundColor White
}
Write-Host "   http://localhost" -ForegroundColor White
Write-Host ""
Write-Host "📊 API 文档: http://localhost/docs" -ForegroundColor White
Write-Host ""
Write-Host "📝 常用命令:" -ForegroundColor Yellow
Write-Host "   查看日志:   docker compose logs -f app"
Write-Host "   停止服务:   docker compose down"
Write-Host "   重启服务:   docker compose restart"
