"""Check available beat engines."""
import collections
import collections.abc
import numpy as np

# Python 3.10+ compatibility patch (madmom needs this)
for _attr in ("MutableSequence", "MutableMapping", "MutableSet",
              "Mapping", "Sequence", "Iterable", "Iterator"):
    if not hasattr(collections, _attr) and hasattr(collections.abc, _attr):
        setattr(collections, _attr, getattr(collections.abc, _attr))

# NumPy 1.24+ removed deprecated aliases used by madmom 0.16.1.
for _alias, _real in (("float", np.float64), ("int", np.int_),
                       ("complex", np.complex128), ("object", np.object_),
                       ("bool", np.bool_), ("str", np.str_)):
    if not hasattr(np, _alias):
        setattr(np, _alias, _real)

try:
    import madmom
    print(f"madmom: OK (v{madmom.__version__})")
except ImportError as e:
    print(f"madmom: MISSING ({e})")

try:
    from BeatNet.BeatNet import BeatNet
    print("BeatNet: OK")
except ImportError as e:
    print(f"BeatNet: MISSING ({e})")

try:
    import librosa
    print(f"librosa: OK (v{librosa.__version__})")
except ImportError as e:
    print(f"librosa: MISSING ({e})")

# Test the beat_engine module itself
import sys
sys.path.insert(0, "/app")
try:
    from app.modules.library.beat_engine import _check_madmom, _check_beatnet
    _check_madmom()
    _check_beatnet()
    from app.modules.library import beat_engine
    print(f"\nbeat_engine._HAS_MADMOM = {beat_engine._HAS_MADMOM}")
    print(f"beat_engine._HAS_BEATNET = {beat_engine._HAS_BEATNET}")
except Exception as e:
    print(f"beat_engine import error: {e}")
