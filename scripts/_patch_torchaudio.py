"""Patch torchaudio _extension/__init__.py to gracefully handle C extension load failure."""
import os

path = "/home/mark/venvs/harbeat/lib/python3.10/site-packages/torchaudio/_extension/__init__.py"

with open(path, "r") as f:
    content = f.read()

# The original block that crashes on Jetson
old = """if _IS_TORCHAUDIO_EXT_AVAILABLE:
    _load_lib("libtorchaudio")

    import torchaudio.lib._torchaudio  # noqa

    _check_cuda_version()
    _IS_RIR_AVAILABLE = torchaudio.lib._torchaudio.is_rir_available()
    _IS_ALIGN_AVAILABLE = torchaudio.lib._torchaudio.is_align_available()"""

# Wrapped in try/except to gracefully degrade
new = """if _IS_TORCHAUDIO_EXT_AVAILABLE:
    try:
        _load_lib("libtorchaudio")
        import torchaudio.lib._torchaudio  # noqa
        _check_cuda_version()
        _IS_RIR_AVAILABLE = torchaudio.lib._torchaudio.is_rir_available()
        _IS_ALIGN_AVAILABLE = torchaudio.lib._torchaudio.is_align_available()
    except (OSError, ImportError) as _e:
        _LG.warning("Failed to load torchaudio C extension: %s. Falling back to pure Python.", _e)
        _IS_TORCHAUDIO_EXT_AVAILABLE = False"""

if old in content:
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print("PATCHED OK")
else:
    print("PATCH TARGET NOT FOUND")
    for i, line in enumerate(content.split("\n")):
        if "_IS_TORCHAUDIO_EXT" in line or "_load_lib" in line:
            print(f"  L{i+1}: {line}")
