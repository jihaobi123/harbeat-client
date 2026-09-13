"""Compatibility import. Implementation: preprocessing/publisher.py."""
import sys
from importlib import import_module

sys.modules[__name__] = import_module("preprocessing.publisher")
