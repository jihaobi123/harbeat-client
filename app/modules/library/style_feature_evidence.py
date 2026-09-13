"""Compatibility import; implementation lives in preprocessing/engines/style_feature_evidence.py."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("preprocessing.engines.style_feature_evidence")
