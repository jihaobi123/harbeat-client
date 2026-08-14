"""Versioned HarBeat offline audio preprocessing."""

from .coverage import CoverageReport, inspect_payloads
from .base_analysis import analyze_audio_file
from .dj_structure_v2 import VERSION, apply_dj_structure_analysis, analyze_song_dj_structure
from .pipeline import (
  BASE_ANALYSIS_VERSION,
  BaseAnalysisError,
  analyze_audio_for_planning,
  validate_base_analysis,
)
from .service import AnalysisRepository, PreprocessResult, PreprocessService
from .version_gate import AnalysisGateError, validate_dj_structure_v2

__all__ = [
  "AnalysisGateError",
  "AnalysisRepository",
  "BASE_ANALYSIS_VERSION",
  "BaseAnalysisError",
  "CoverageReport",
  "VERSION",
  "PreprocessResult",
  "PreprocessService",
  "analyze_audio_file",
  "analyze_audio_for_planning",
  "analyze_song_dj_structure",
  "apply_dj_structure_analysis",
  "inspect_payloads",
  "validate_base_analysis",
  "validate_dj_structure_v2",
]
