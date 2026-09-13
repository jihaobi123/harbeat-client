"""Compatibility import; implementation lives in preprocessing/engines/acoustic_measurement_analysis.py."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("preprocessing.engines.acoustic_measurement_analysis")
