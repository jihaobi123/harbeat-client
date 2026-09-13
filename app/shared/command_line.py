"""Compatibility import; implementation lives in music_analysis/command_line.py."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("music_analysis.command_line")
