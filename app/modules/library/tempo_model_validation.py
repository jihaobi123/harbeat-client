"""Compatibility import; implementation lives in preprocessing/engines/tempo_model_validation.py."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("preprocessing.engines.tempo_model_validation")
