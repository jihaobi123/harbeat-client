"""Pure coverage accounting for full-library analysis snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .version_gate import validate_dj_structure_v2


@dataclass(frozen=True, slots=True)
class CoverageReport:
  total: int
  ready: int
  missing: tuple[str, ...]
  invalid: tuple[str, ...]

  @property
  def complete(self) -> bool:
    return self.total == self.ready and not self.missing and not self.invalid


def inspect_payloads(rows: Iterable[tuple[str, Mapping[str, Any] | None]]) -> CoverageReport:
  total = ready = 0
  missing = []
  invalid = []
  for song_id, payload in rows:
    total += 1
    if not isinstance(payload, Mapping):
      missing.append(song_id)
      continue
    try:
      validate_dj_structure_v2(payload)
    except ValueError:
      invalid.append(song_id)
    else:
      ready += 1
  return CoverageReport(total, ready, tuple(missing), tuple(invalid))
