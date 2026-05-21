# Manual Flutter Installation Guide (China)

## Option 1: Use Updated Script with China Mirror (Recommended)

The script has been updated to use Gitee mirror for faster download in China.

```powershell
cd d:\工作\DJ机\harbeat_app
.\install_flutter_and_build.ps1
```

If it still fails, try Option 2 below.

---

## Option 2: Manual Download and Install

### Step 1: Download Flutter SDK

**Method A: Direct Download (Fastest)**

Visit one of these mirrors:
- **Tsinghua Mirror**: https://mirrors.tuna.tsinghua.edu.cn/flutter/flutter_infra_release/releases/stable/windows/
- **Official**: https://docs.flutter.dev/get-started/install/windows

Download the latest `flutter_windows_x.x.x-stable.zip`

### Step 2: Extract to C:\flutter

1. Create folder: `C:\flutter`
2. Extract zip contents to `C:\flutter`
3. You should see: `C:\flutter\bin\flutter.bat`

### Step 3: Add to System PATH

**Method A: GUI (Easy)**

1. Right-click "This PC" → Properties
2. Advanced system settings → Environment Variables
3. Under "System variables", find "Path" → Edit
4. Click "New" → Add: `C:\flutter\bin`
5. Click OK on all dialogs
6. **Restart PowerShell**

**Method B: PowerShell Command (Admin required)**

```powershell
# Run as Administrator
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\flutter\bin", [EnvironmentVariableTarget]::Machine)
```

### Step 4: Verify Installation

Open **new** PowerShell window:

```powershell
flutter doctor
```

You should see version info.

### Step 5: Build APK

```powershell
cd d:\工作\DJ机\harbeat_app
.\build_apk_simple.ps1
```

---

## Option 3: Quick Test Without Full Install

If you just want to test quickly, use online build services:

1. **Codemagic**: https://codemagic.io
2. **GitHub Actions**: Configure CI/CD workflow
3. **Ask colleague**: Send project folder to someone with Flutter installed

---

## Troubleshooting Network Issues

### Problem: Git clone fails

**Solution 1: Use proxy**
```powershell
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

**Solution 2: Increase timeout**
```powershell
git config --global http.postBuffer 524288000
git config --global http.lowSpeedLimit 0
git config --global http.lowSpeedTime 999999
```

**Solution 3: Use Gitee mirror**
```powershell
git clone https://gitee.com/mirrors/flutter.git -b stable C:\flutter
```

### Problem: flutter pub get slow

**Solution: Set China mirror**
```powershell
$env:PUB_HOSTED_URL = "https://pub.flutter-io.cn"
$env:FLUTTER_STORAGE_BASE_URL = "https://storage.flutter-io.cn"
flutter pub get
```

---

## Complete Manual Steps Summary

```powershell
# 1. Download Flutter SDK from Tsinghua mirror
#    https://mirrors.tuna.tsinghua.edu.cn/flutter/flutter_infra_release/releases/stable/windows/

# 2. Extract to C:\flutter

# 3. Add C:\flutter\bin to PATH (restart PowerShell)

# 4. Verify
flutter doctor

# 5. Set China mirror (optional but recommended)
$env:PUB_HOSTED_URL = "https://pub.flutter-io.cn"
$env:FLUTTER_STORAGE_BASE_URL = "https://storage.flutter-io.cn"

# 6. Build APK
cd d:\工作\DJ机\harbeat_app
.\build_apk_simple.ps1
```

---

## Expected Time

- **Download Flutter**: 5-10 minutes (with mirror)
- **Extract**: 1-2 minutes
- **Build APK**: 5-15 minutes (first time)
- **Total**: ~15-30 minutes

---

## Need Help?

If you encounter any issues, send me:
1. Error message screenshot
2. Output of `flutter doctor`
3. Your network environment (proxy, VPN, etc.)
