# HarBeat App 快速启动脚本 (Windows PowerShell)

Write-Host "🎵 HarBeat Mobile App - 快速启动" -ForegroundColor Cyan
Write-Host ""

# 检查 Flutter 是否安装
Write-Host "📱 检查 Flutter 环境..." -ForegroundColor Yellow
$flutterVersion = flutter --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Flutter 未安装或未添加到 PATH" -ForegroundColor Red
    Write-Host "请先安装 Flutter: https://flutter.dev/docs/get-started/install" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Flutter 已安装" -ForegroundColor Green
Write-Host ""

# 安装依赖
Write-Host "📦 安装依赖包..." -ForegroundColor Yellow
flutter pub get
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 依赖安装失败" -ForegroundColor Red
    exit 1
}
Write-Host "✅ 依赖安装完成" -ForegroundColor Green
Write-Host ""

# 生成代码
Write-Host "🔨 生成序列化代码..." -ForegroundColor Yellow
flutter pub run build_runner build --delete-conflicting-outputs
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  代码生成失败（可忽略，稍后手动运行）" -ForegroundColor Yellow
} else {
    Write-Host "✅ 代码生成完成" -ForegroundColor Green
}
Write-Host ""

# 检查设备
Write-Host "📱 检测可用设备..." -ForegroundColor Yellow
$devices = flutter devices 2>&1
Write-Host $devices
Write-Host ""

# 选择运行方式
Write-Host "请选择运行方式:" -ForegroundColor Cyan
Write-Host "1. 运行在默认设备" -ForegroundColor White
Write-Host "2. 运行在 Android 模拟器" -ForegroundColor White
Write-Host "3. 运行在 iOS 模拟器" -ForegroundColor White
Write-Host "4. 列出所有设备" -ForegroundColor White
Write-Host ""

$choice = Read-Host "请输入选项 (1-4)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "🚀 启动应用..." -ForegroundColor Green
        flutter run
    }
    "2" {
        Write-Host ""
        Write-Host "🚀 启动 Android 应用..." -ForegroundColor Green
        flutter run -d android
    }
    "3" {
        Write-Host ""
        Write-Host "🚀 启动 iOS 应用..." -ForegroundColor Green
        flutter run -d ios
    }
    "4" {
        flutter devices
        $deviceId = Read-Host "请输入设备 ID"
        flutter run -d $deviceId
    }
    default {
        Write-Host "❌ 无效选项" -ForegroundColor Red
    }
}
