"""Patch transformers to work with Jetson PyTorch (2.4.0a0+nv24.7).

Fixes:
1. Version check: transformers 5.5.4 doesn't recognize '2.4.0a0+...' as >= 2.4
2. nn.Module: accelerate.py uses nn.Module without importing torch.nn
"""
import os
import re

SITE = "/home/mark/venvs/harbeat/lib/python3.10/site-packages"

# --- Fix 1: PyTorch version detection ---
import_utils = os.path.join(SITE, "transformers/utils/import_utils.py")
with open(import_utils, "r") as f:
    content = f.read()

# Find the line that disables PyTorch and check the logic
lines = content.split("\n")
patched = False
for i, line in enumerate(lines):
    if "Disabling PyTorch" in line:
        print(f"Found version check at line {i+1}: {line.strip()}")
        # Look backwards for the condition
        for j in range(i-1, max(i-10, 0), -1):
            print(f"  Line {j+1}: {lines[j].strip()}")

if not patched:
    # Alternative: force _torch_available = True after the check
    # Find where _torch_available is set
    for i, line in enumerate(lines):
        if "_torch_available" in line and "False" in line and "Disabling" not in line:
            print(f"  _torch_available=False at line {i+1}: {line.strip()}")

# --- Fix 2: nn.Module in accelerate.py ---
accel = os.path.join(SITE, "transformers/integrations/accelerate.py")
with open(accel, "r") as f:
    acontent = f.read()

for i, line in enumerate(acontent.split("\n")):
    if "nn.Module" in line and i < 70:
        print(f"\nacclarate.py line {i+1}: {line.strip()}")

# Look for existing nn import
for i, line in enumerate(acontent.split("\n")[:30]):
    if "import" in line:
        print(f"  import at line {i+1}: {line.strip()}")
