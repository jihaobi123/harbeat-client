# Fix Disk Space and Reinstall Flutter Guide

## Problem Summary

Your C: drive is full, causing Flutter installation to fail.

**Error messages:**
- "磁盘空间不足" (Disk space insufficient)
- "另一个程序正在使用此文件" (File in use by another process)

---

## Solution: Install Flutter on D: Drive

### Step 1: Clean Up Failed Installation

```powershell
# Delete incomplete Flutter folder from C:
Remove-Item -Path "C:\flutter" -Recurse -Force -ErrorAction SilentlyContinue

# Clear temporary files
Remove-Item -Path "$env:TEMP\flutter*" -Recurse -Force -ErrorAction SilentlyContinue
```

### Step 2: Free Up Disk Space on C:

You need at least **5GB free space** on C: drive.

**Quick cleanup:**
```powershell
# Clear Windows temp files
Remove-Item -Path "$env:TEMP\*" -Recurse -Force -ErrorAction SilentlyContinue

# Clear Recycle Bin
Clear-RecycleBin -Force

# Run Disk Cleanup
cleanmgr
```

**Or manually delete:**
- Downloaded files in `C:\Users\YourName\Downloads`
- Temporary files
- Old software installers

### Step 3: Download Flutter SDK Manually

**Use Tsinghua Mirror (Fast in China):**

Visit: https://mirrors.tuna.tsinghua.edu.cn/flutter/flutter_infra_release/releases/stable/windows/

Download the latest: `flutter_windows_x.x.x-stable.zip` (about 500MB)

### Step 4: Extract to D:\flutter

1. Create folder: `D:\flutter`
2. Extract zip contents to `D:\flutter`
3. Verify: `D:\flutter\bin\flutter.bat` exists

### Step 5: Add to System PATH

**Method A: GUI (Recommended)**

1. Right-click "This PC" → Properties
2. Advanced system settings → Environment Variables
3. Under "System variables", find "Path" → Edit
4. Click "New" → Add: `D:\flutter\bin`
5. Click OK on all dialogs
6. **Restart PowerShell**

**Method B: PowerShell (Admin required)**

```powershell
# Run as Administrator
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";D:\flutter\bin", [EnvironmentVariableTarget]::Machine)
```

### Step 6: Verify Installation

Open **NEW** PowerShell window:

```powershell
flutter doctor
```

Should show version info without errors.

### Step 7: Build APK

```powershell
cd d:\工作\DJ机\harbeat_app
.\build_apk_fixed.ps1
```

---

## Alternative: Use Existing Flutter on Another Computer

If you have access to another computer with Flutter installed:

1. Copy entire project folder: `d:\工作\DJ机\harbeat_app`
2. On other computer:
   ```powershell
   cd harbeat_app
   flutter build apk --release
   ```
3. Copy back the APK file:
   ```
   build\app\outputs\flutter-apk\app-release.apk
   ```

---

## Quick Checklist

Before building APK, ensure:

- [ ] C: drive has at least 5GB free space
- [ ] Flutter installed to D:\flutter (not C:\flutter)
- [ ] D:\flutter\bin added to PATH
- [ ] New PowerShell window opened after PATH change
- [ ] `flutter doctor` runs successfully
- [ ] Project path is correct: `d:\工作\DJ机\harbeat_app`

---

## Expected Disk Usage

| Component | Size |
|-----------|------|
| Flutter SDK | ~500 MB |
| Flutter cache | ~2-3 GB |
| Project dependencies | ~200 MB |
| Build artifacts | ~500 MB |
| **Total** | **~3-4 GB** |

---

## If Still Having Issues

### Problem: Not enough space on C:

**Solution:** Move pagefile.sys to D: drive
1. System Properties → Advanced → Performance Settings
2. Advanced → Virtual Memory → Change
3. Uncheck "Automatically manage"
4. Set C: to "No paging file"
5. Set D: to "System managed size"
6. Restart computer

### Problem: Download keeps failing

**Solution:** Use offline installation
1. Download Flutter SDK zip manually
2. Extract to D:\flutter
3. No network needed for extraction

### Problem: Path encoding issues

**Solution:** Use short path names
```powershell
# Instead of Chinese path, create symlink
New-Item -ItemType SymbolicLink -Path "D:\harbeat" -Target "d:\工作\DJ机\harbeat_app"
cd D:\harbeat
.\build_apk_fixed.ps1
```

---

## Summary Commands

```powershell
# 1. Clean old installation
Remove-Item -Path "C:\flutter" -Recurse -Force

# 2. Free up space on C:
cleanmgr

# 3. Download Flutter manually from Tsinghua mirror
#    https://mirrors.tuna.tsinghua.edu.cn/flutter/flutter_infra_release/releases/stable/windows/

# 4. Extract to D:\flutter

# 5. Add D:\flutter\bin to PATH (restart PowerShell)

# 6. Verify
flutter doctor

# 7. Build APK
cd d:\工作\DJ机\harbeat_app
.\build_apk_fixed.ps1
```

---

**Good luck!** 🚀
