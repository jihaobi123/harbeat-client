"""Lossless source envelope; normalized views are never written back to sources."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from . import VERSION


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def scalar(value):
    if isinstance(value, dict):
        return value.get('value', value.get('name', value.get('overall')))
    return value


def intervals(items):
    if isinstance(items, dict):
        items = items.get('items', [])
    result = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        start = item.get('start', item.get('start_sec', item.get('start_ms', 0) / 1000))
        end = item.get('end', item.get('end_sec', item.get('end_ms', 0) / 1000))
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and 0 <= start < end:
            result.append({**item, 'start': start, 'end': end,
                           'label': item.get('label', item.get('name', 'unknown'))})
    return result


def build_report(documents: dict, extensions: dict | None = None, audio: dict | None = None) -> dict:
    if not isinstance(documents, dict) or not documents or not all(isinstance(v, dict) for v in documents.values()):
        raise ValueError('documents must contain named analysis objects')
    if extensions is not None and (not isinstance(extensions, dict) or not all(isinstance(v, dict) for v in extensions.values())):
        raise ValueError('extensions must be named module objects')
    if audio is not None and not isinstance(audio, dict):
        raise ValueError('audio must be an object')
    # JSON round-trip also rejects non-finite numbers and detaches every nested object.
    docs = json.loads(canonical(documents))
    extensions = json.loads(canonical(extensions or {}))
    audio = json.loads(canonical(audio or {}))
    bindings = {v.get('audio_sha256') or (v.get('audio') or {}).get('audio_sha256') for v in docs.values()}
    bindings.discard(None)
    if audio.get('sha256'):
        bindings.add(audio['sha256'])
    if len(bindings) > 1:
        raise ValueError('source documents refer to different audio SHA256 values')
    if bindings:
        audio['sha256'] = next(iter(bindings))
    source_name = 'core' if 'core' in docs else sorted(docs)[0]
    doc = docs[source_name]
    core = doc.get('analysis', doc)
    if not isinstance(core, dict):
        core = doc
    grid = core.get('beat_grid') or {}
    timeline = doc.get('timeline') or {}
    summary = doc.get('track_summary') or core
    src = doc.get('source') or {}
    source_cores = {name: value.get('analysis', value) for name, value in docs.items()}
    stem_source = next((name for name in ['separated_stem_activity', source_name, *docs]
                        if isinstance(source_cores.get(name), dict) and source_cores[name].get('stem_activity_windows')), source_name)
    duration = audio.get('duration') or (doc.get('audio') or {}).get('duration_sec') or doc.get('duration') or doc.get('duration_sec') or src.get('duration_ms', 0) / 1000
    sections = intervals(core.get('sections', core.get('phrase_map', [])))
    beats = core.get('beat_points', timeline.get('beat_times_sec', [v / 1000 for v in grid.get('beats_ms', [])]))
    downbeats = core.get('downbeats', timeline.get('downbeat_times_sec', [v / 1000 for v in grid.get('downbeats_ms', [])]))
    summary_view = {
        'bpm': scalar(summary.get('bpm', (core.get('tempo') or {}).get('bpm'))),
        'key': scalar(summary.get('key')),
        'camelot': core.get('camelot_key', (core.get('key') or {}).get('camelot') if isinstance(core.get('key'), dict) else None),
        'energy': scalar(summary.get('energy_normalized', summary.get('energy'))),
        'duration': duration,
    }
    section_end = max((s['end'] for s in sections), default=0)
    warnings = []
    if sections and duration and section_end < duration - max(5, duration * .05):
        warnings.append(f'原始段落最晚到 {section_end:.2f} 秒，音频为 {duration:.2f} 秒；后续区间没有段落记录，请检查是否只分析了片段。')
    identity = {'documents': docs, 'extensions': extensions, 'audio': audio, 'version': VERSION}
    return {
        'schema': 'harbeat.analysis_report', 'version': VERSION,
        'id': digest(identity), 'created_at': datetime.now(timezone.utc).isoformat(),
        'title': doc.get('title') or src.get('title') or audio.get('name') or '未命名分析',
        'diagnostics': {'section_end_sec': section_end, 'audio_duration_sec': duration, 'warnings': warnings},
        'audio': audio, 'documents': docs, 'source_hashes': {k: digest(v) for k, v in docs.items()},
        'primary_source': source_name, 'summary': summary_view,
        'view_sources': {'stems': stem_source, 'sections': source_name, 'energy': source_name},
        'timeline': {'unit': 'seconds', 'beats': beats, 'downbeats': downbeats, 'sections': sections,
                     'energy': core.get('energy_curve', (core.get('energy') or {}).get('curve', []) if isinstance(core.get('energy'), dict) else []),
                     'bpm': core.get('bpm_curve', []), 'stems': source_cores.get(stem_source, {}).get('stem_activity_windows', []),
                     'transitions': core.get('transition_windows', [])},
        'extensions': extensions,
        'evaluation': {'status': 'not_evaluated', 'reason': '没有同曲人工标注或盲听结果'},
        'policy': {'source_preserved': True, 'extensions_override_core': False, 'experimental': list(extensions)},
    }


def validate_report(report: dict) -> dict:
    if report.get('schema') != 'harbeat.analysis_report' or report.get('version') != VERSION:
        raise ValueError('unsupported report schema/version')
    rebuilt = build_report(report['documents'], report.get('extensions'), report.get('audio'))
    if rebuilt['id'] != report.get('id') or rebuilt['source_hashes'] != report.get('source_hashes'):
        raise ValueError('report content hash mismatch')
    # Normalized views are re-derived; imported display fields cannot contradict sources.
    rebuilt['created_at'] = report.get('created_at', rebuilt['created_at'])
    return rebuilt
