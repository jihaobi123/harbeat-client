"""Compatibility import; implementation lives in preprocessing/engines/feature_calibration.py."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("preprocessing.engines.feature_calibration")
