"""Compatibility import; implementation lives in preprocessing/engines/bass_feature_analysis.py."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("preprocessing.engines.bass_feature_analysis")
