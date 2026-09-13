"""Compatibility import. Implementation: preprocessing/vocal_activity.py."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("preprocessing.vocal_activity")
