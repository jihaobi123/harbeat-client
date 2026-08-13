"""Versioned HarBeat offline audio preprocessing."""

from .coverage import CoverageReport, inspect_payloads
from .dj_structure_v2 import VERSION, apply_dj_structure_analysis, analyze_song_dj_structure
from .service import AnalysisRepository, PreprocessResult, PreprocessService
from .version_gate import AnalysisGateError, validate_dj_structure_v2

__all__ = [
  "AnalysisGateError",
  "AnalysisRepository",
  "CoverageReport",
  "VERSION",
  "PreprocessResult",
  "PreprocessService",
  "analyze_song_dj_structure",
  "apply_dj_structure_analysis",
  "inspect_payloads",
  "validate_dj_structure_v2",
]
