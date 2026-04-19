"""Patch transformers 5.5.4 for Jetson PyTorch compatibility.

Problem: transformers doesn't recognize '2.4.0a0+3bcc3cddb5.nv24.7' as >= 2.4.0
because packaging.version treats 'a0' as alpha pre-release (< 2.4.0).

Fix: Patch is_torch_available() to strip pre-release & local from version before comparing.
"""
import os
import sys

SITE = "/home/mark/venvs/harbeat/lib/python3.10/site-packages"
TARGET = os.path.join(SITE, "transformers/utils/import_utils.py")

with open(TARGET, "r") as f:
    content = f.read()

# Original code (lines 146-150):
#     is_available, torch_version = _is_package_available("torch", return_version=True)
#     parsed_version = version.parse(torch_version)
#     if is_available and parsed_version < version.parse("2.4.0"):
OLD = '        parsed_version = version.parse(torch_version)\n        if is_available and parsed_version < version.parse("2.4.0"):'
NEW = '        parsed_version = version.parse(torch_version)\n        # Jetson patch: strip pre-release tag so 2.4.0a0+nv is recognized as >= 2.4.0\n        _base_ver = version.parse(f"{parsed_version.major}.{parsed_version.minor}.{parsed_version.micro}")\n        if is_available and _base_ver < version.parse("2.4.0"):'

if OLD in content:
    content = content.replace(OLD, NEW)
    # Also fix the return statement on line 150
    OLD2 = 'return is_available and version.parse(torch_version) >= version.parse("2.4.0")'
    NEW2 = 'return is_available and _base_ver >= version.parse("2.4.0")'
    content = content.replace(OLD2, NEW2)
    with open(TARGET, "w") as f:
        f.write(content)
    print(f"OK: Patched {TARGET}")
elif "Jetson patch" in content:
    print("SKIP: Already patched")
else:
    print("ERROR: Could not find target code to patch")
    # Show context
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "parsed_version" in line and "2.4" in line:
            for j in range(max(0, i-2), min(len(lines), i+3)):
                print(f"  {j+1}: {lines[j]}")
    sys.exit(1)
