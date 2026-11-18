"""Persist version-bound structure, voice protection, and optional lyric timing."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from .lyric_timing import build_lyric_timeline

SCHEMA = 'harbeat.transition-cues.v1'
IDENTITY = ('masterSha256', 'reportSha256', 'vocalSha256', 'runId')


def binding(track):
    proof = track['provenance']
    return {'trackId': track['id'], **{key: proof[key] for key in IDENTITY}}


def bound_vocals(track):
    proof = track.get('provenance') or {}
    vocal = track.get('preprocessing', {}).get('vocalActivity') or {}
    source = vocal.get('source') or {}
    if (vocal.get('status') != 'ready' or vocal.get('time_origin') != 'master_audio_start'
            or not all(proof.get(key) for key in IDENTITY)
            or source.get('track_id') != track.get('id')
            or source.get('analysis_run_id') != proof['runId']
            or source.get('vocal_sha256') != proof['vocalSha256']):
        return None
    return vocal.get('intervals')


def section_at(sections, seconds):
    return next((row['label'] for row in sections if row['start'] <= seconds < row['end']), None)


def build_cues(track, lyric_record=None):
    source = binding(track)
    duration = round(track['duration'] * 1000)
    sections = track.get('sections', [])
    vocal = bound_vocals(track)
    alignment = track.get('alignment') or {}
    aligned = alignment.get('status') == 'candidate' and all(
        alignment.get('source', {}).get(key) == source[key] for key in IDENTITY[:3])
    phrases = [{'startMs': round(row['start'] * 1000), 'endMs': round(row['tailEnd'] * 1000)}
               for row in alignment.get('phrases', [])] if aligned and vocal is not None else []
    entries = sorted(({'startMs': row['start_ms'], 'endMs': row['end_ms'], 'basis': 'acoustic'}
                      for row in vocal or []), key=lambda row: row['startMs'])
    lyric_status = 'unavailable'
    if lyric_record and lyric_record.get('masterSha256') != source['masterSha256']:
        lyric_status = 'source_mismatch'
    elif vocal is not None and lyric_record and isinstance(lyric_record.get('lrc'), str):
        lyrics = build_lyric_timeline(lyric_record['lrc'], duration, vocal)
        supported = {row['acousticOnsetMs']: {'startMs': row['startMs'],
                     'endMs': min(row['vocalSpanEndMs'], row['nextMarkMs']), 'basis': 'lyric-and-vocal'}
                     for row in lyrics['lines'] if row['evidence'] == 'onset_supported'}
        entries = [{**supported[row['startMs']],
                    **({'onsetMs': row['startMs']} if row['startMs'] != supported[row['startMs']]['startMs'] else {})}
                   if row['startMs'] in supported else row for row in entries]
        lyric_status = 'supported' if supported else 'unverified'
    exits = []
    for row in alignment.get('exits', []) if aligned and vocal is not None else []:
        cut = row['cut']
        if any(span['startMs'] <= cut * 1000 <= span['endMs'] for span in phrases):
            continue
        exits.append({'time': cut, 'tailEnd': row.get('tailEnd'), 'section': section_at(sections, cut),
                      'sectionAligned': row.get('sectionAligned', False)})
    return {'schema': SCHEMA, 'source': source, 'timeOrigin': 'master_audio_start',
            'sectionSource': track['provenance'].get('sectionSource'), 'sections': sections,
            'vocalStatus': 'ready' if aligned and vocal is not None else 'unavailable',
            'lyricStatus': lyric_status, 'entries': entries, 'protectedPhrases': phrases, 'exits': exits}


def matching_cues(data, track):
    return (isinstance(data, dict) and data.get('schema') == SCHEMA
            and data.get('timeOrigin') == 'master_audio_start' and data.get('source') == binding(track))


def read_cues(folder, track):
    try:
        data = json.loads((Path(folder) / 'transition-cues.json').read_bytes())
    except (OSError, ValueError):
        return None
    return data if matching_cues(data, track) else None


def write_cues(folder, track, lyric_record=None):
    data = build_cues(track, lyric_record)
    destination = Path(folder) / 'transition-cues.json'
    with NamedTemporaryFile(dir=folder, prefix='.transition-cues-', delete=False) as temporary:
        path = Path(temporary.name)
        try:
            temporary.write(json.dumps(data, ensure_ascii=False, allow_nan=False).encode())
            temporary.close()
            path.replace(destination)
        finally:
            path.unlink(missing_ok=True)
    return data


def main():
    import argparse
    from .transition_policy_cli import load_track

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    parser.add_argument('--lyrics', type=Path)
    args = parser.parse_args()
    lyrics = json.loads(args.lyrics.read_bytes()) if args.lyrics else None
    data = write_cues(args.result.parent, load_track(args.result), lyrics)
    print(json.dumps({'source': data['source'], 'sections': len(data['sections']),
                      'vocalStatus': data['vocalStatus'], 'lyricStatus': data['lyricStatus'],
                      'entries': len(data['entries']), 'exits': len(data['exits'])}))


if __name__ == '__main__':
    main()
