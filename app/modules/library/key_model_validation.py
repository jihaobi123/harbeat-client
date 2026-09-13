"""Compatibility import; implementation lives in preprocessing/engines/key_model_validation.py."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("preprocessing.engines.key_model_validation")
