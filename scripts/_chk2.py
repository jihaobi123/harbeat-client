import collections, collections.abc
for a in ("MutableSequence","MutableMapping","MutableSet","Mapping","Sequence","Iterable","Iterator"):
    if not hasattr(collections,a) and hasattr(collections.abc,a):
        setattr(collections,a,getattr(collections.abc,a))
import numpy as np
for alias, real in (("float", np.float64), ("int", np.int_), ("complex", np.complex128), ("object", np.object_), ("bool", np.bool_), ("str", np.str_)):
    if not hasattr(np, alias):
        setattr(np, alias, real)

try:
    import madmom
    print("madmom OK:", madmom.__version__)
except Exception as e:
    print("madmom FAILED:", e)
try:
    from BeatNet.BeatNet import BeatNet
    print("BeatNet OK")
except Exception as e:
    print("BeatNet FAILED:", e)
try:
    import essentia
    print("essentia OK:", essentia.__version__)
except Exception as e:
    print("essentia FAILED:", e)
