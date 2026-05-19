# APK Build Scripts Guide

## Two Script Options

### Option 1: Auto-Install Flutter + Build APK (Recommended for first time)

**Use this if Flutter is NOT installed on your computer**

```powershell
cd d:\工作\DJ机\harbeat_app
.\install_flutter_and_build.ps1
```

**What it does:**
1. Checks if Flutter is installed
2. If not, downloads and installs Flutter (~500MB)
3. Installs project dependencies
4. Generates code
5. Builds Release APK
6. Shows APK location

**Time required:** 10-15 minutes (including Flutter download)

---

### Option 2: Simple Build (If Flutter already installed)

**Use this if Flutter IS already installed**

```powershell
cd d:\工作\DJ机\harbeat_app
.\build_apk_simple.ps1
```

**What it does:**
1. Checks Flutter installation
2. Cleans old build
3. Installs dependencies
4. Builds Release APK
5. Opens APK folder

**Time required:** 5-10 minutes

---

## After Build Completes

APK will be located at:
```
d:\工作\DJ机\harbeat_app\build\app\outputs\flutter-apk\app-release.apk
```

Size: ~30-50 MB

---

## Install APK to Phone

### Method 1: USB Direct Install (Fastest)

```powershell
# Connect phone via USB
# Enable USB Debugging on phone
# Then run:
flutter install
```

### Method 2: WeChat/QQ Transfer

1. Find APK file in folder
2. Drag to WeChat "File Transfer"
3. Receive on phone and install

### Method 3: Local HTTP Server

```powershell
# Start HTTP server
cd build\app\outputs\flutter-apk
python -m http.server 8080

# On phone browser, visit:
http://YOUR_COMPUTER_IP:8080/app-release.apk
```

---

## Troubleshooting

### Error: "Flutter is not installed"

**Solution:** Use `install_flutter_and_build.ps1` instead, or manually install Flutter from https://docs.flutter.dev

### Error: "Git is required but not installed"

**Solution:** Download Git from https://git-scm.com/download/win

### Error: "Build failed"

**Solution:** 
```powershell
# View detailed error
flutter build apk --release -v

# Common fixes
flutter clean
flutter pub get
flutter build apk --release
```

### Error: PowerShell execution policy

**Solution:** Run as Administrator:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## Quick Start Summary

**First time user:**
```powershell
cd d:\工作\DJ机\harbeat_app
.\install_flutter_and_build.ps1
```

**Already have Flutter:**
```powershell
cd d:\工作\DJ机\harbeat_app
.\build_apk_simple.ps1
```

That's it! 🚀
