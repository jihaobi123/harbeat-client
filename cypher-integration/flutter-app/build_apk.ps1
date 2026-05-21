# HarBeat App - Android APK 构建脚本
Write-Host "🎵 HarBeat - 构建 Android APK" -ForegroundColor Cyan
Write-Host ""

# 检查 Flutter
Write-Host "📱 检查 Flutter 环境..." -ForegroundColor Yellow
$flutterVersion = flutter --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Flutter 未安装" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Flutter 已安装" -ForegroundColor Green
Write-Host ""

# 清理旧构建
Write-Host "🧹 清理旧构建..." -ForegroundColor Yellow
flutter clean
Write-Host "✅ 清理完成" -ForegroundColor Green
Write-Host ""

# 安装依赖
Write-Host "📦 安装依赖..." -ForegroundColor Yellow
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
    Write-Host "⚠️  代码生成警告（可忽略）" -ForegroundColor Yellow
} else {
    Write-Host "✅ 代码生成完成" -ForegroundColor Green
}
Write-Host ""

# 构建 APK
Write-Host "🏗️  构建 Release APK..." -ForegroundColor Yellow
Write-Host "这可能需要几分钟时间，请耐心等待..." -ForegroundColor Gray
flutter build apk --release

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ APK 构建失败" -ForegroundColor Red
    exit 1
}

Write-Host "✅ APK 构建成功！" -ForegroundColor Green
Write-Host ""

# 显示 APK 路径
$apkPath = "build\app\outputs\flutter-apk\app-release.apk"
if (Test-Path $apkPath) {
    $apkSize = (Get-Item $apkPath).Length / 1MB
    Write-Host "📍 APK 位置: $apkPath" -ForegroundColor Cyan
    Write-Host "📊 APK 大小: $([math]::Round($apkSize, 2)) MB" -ForegroundColor Cyan
    Write-Host ""
    
    # 询问是否安装到连接的设备
    Write-Host "请选择操作:" -ForegroundColor Yellow
    Write-Host "1. 查看已连接设备" -ForegroundColor White
    Write-Host "2. 安装到已连接设备" -ForegroundColor White
    Write-Host "3. 仅显示 APK 路径" -ForegroundColor White
    Write-Host ""
    
    $choice = Read-Host "请输入选项 (1-3)"
    
    switch ($choice) {
        "1" {
            Write-Host ""
            flutter devices
        }
        "2" {
            Write-Host ""
            Write-Host "📲 正在安装到设备..." -ForegroundColor Green
            flutter install
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ 安装成功！请在手机上打开 HarBeat" -ForegroundColor Green
            } else {
                Write-Host "❌ 安装失败，请检查设备连接" -ForegroundColor Red
                Write-Host ""
                Write-Host "💡 提示: 也可以手动安装 APK" -ForegroundColor Yellow
                Write-Host "   1. 将 APK 复制到手机" -ForegroundColor Gray
                Write-Host "   2. 在手机文件管理器中找到 APK" -ForegroundColor Gray
                Write-Host "   3. 点击安装" -ForegroundColor Gray
            }
        }
        "3" {
            Write-Host ""
            Write-Host "💡 手动安装方法:" -ForegroundColor Yellow
            Write-Host "   1. 将 APK 通过微信/QQ 发送到手机" -ForegroundColor Gray
            Write-Host "   2. 或在手机浏览器下载: http://<电脑IP>:8080/app-release.apk" -ForegroundColor Gray
            Write-Host "   3. 在手机文件管理器中点击 APK 安装" -ForegroundColor Gray
        }
        default {
            Write-Host "❌ 无效选项" -ForegroundColor Red
        }
    }
} else {
    Write-Host "❌ 找不到 APK 文件" -ForegroundColor Red
}

Write-Host ""
Write-Host "🎉 完成！" -ForegroundColor Green
