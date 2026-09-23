"""Behavioral coverage for report-bound conservative acoustic phrase candidates."""
import copy
import importlib.util

import pytest


def analyze(track, signals):
    assert importlib.util.find_spec('analysis_platform.phrase_alignment'), 'phrase alignment implementation is missing'
    from analysis_platform.phrase_alignment import analyze_alignment
    return analyze_alignment(track, signals)


def fixture(vad=((1, 3.8),), active=None, duration=12):
    """50 ms source measurements with declared RMS hysteresis intervals."""
    active = list(vad if active is None else active)
    points = []
    for index in range(round(duration / .05)):
        start, end = round(index * .05, 8), round((index + 1) * .05, 8)
        level = -20 if any(end > lo and start < hi for lo, hi in active) else -80
        points.append({'start': start, 'end': end, 'rms_dbfs': level})
    track = {
        'duration': duration, 'reportId': 'report-1',
        'provenance': {'masterSha256': 'a' * 64, 'reportSha256': 'b' * 64, 'vocalSha256': 'c' * 64},
        'preprocessing': {
            'reportId': 'report-1', 'reportSha256': 'b' * 64, 'masterSha256': 'a' * 64,
            'bindingChecks': {'reportHash': True, 'masterHash': True},
            'beatGrid': {'beats_ms': [index * 500 for index in range(int(duration * 2) + 1)],
                         'bars_ms': [index * 2000 for index in range(int(duration / 2) + 1)]},
            'vocalActivity': {'status': 'ready', 'time_origin': 'master_audio_start',
                              'intervals': [{'start_ms': lo * 1000, 'end_ms': hi * 1000} for lo, hi in vad],
                              'source': {'vocal_sha256': 'c' * 64}},
        },
        'vocals': [list(interval) for interval in vad],
        'sections': [{'start': 0, 'end': 4, 'label': 'verse'}, {'start': 4, 'end': duration, 'label': 'chorus'}],
    }
    signals = {
        'audio_sha256': 'a' * 64, 'duration': duration, 'time_origin': 'master_audio_start',
        'rms_points': [{'start': 0, 'end': duration, 'rms_dbfs': -18,
                        'bands_dbfs': {'low': -21, 'mid': -24, 'high': None}}],
        'vocals': {'status': 'candidate', 'source': 'separated_vocal_rms_hysteresis_v1',
                   'asset': {'verified_sha256': 'c' * 64, 'declared_sha256': 'c' * 64},
                   'coverage_sec': duration, 'intervals': [{'start': lo, 'end': hi} for lo, hi in active],
                   'parameters': {'enter_dbfs': -35, 'exit_dbfs': -41, 'frame_sec': .05,
                                  'min_active_sec': .1, 'merge_gap_sec': .1}, 'points': points},
    }
    return track, signals


def test_tail_crossing_bar_waits_until_next_actual_complete_bar():
    track, signals = fixture(vad=((1, 4.1),))
    original = copy.deepcopy((track, signals))
    result = analyze(track, signals)
    assert result['schema'] == 'harbeat.phrase_alignment.v1'
    assert result['status'] == 'candidate'
    assert result['source'] == {'reportId': 'report-1', **track['provenance']}
    assert (track, signals) == original
    phrase = result['phrases'][0]
    assert phrase['semanticStatus'] == 'unverified'
    assert phrase['tailEnd'] == pytest.approx(4.18)
    assert phrase['sourceRows']['vad'] == [1]
    assert phrase['sourceRows']['rms']
    assert [exit['cut'] for exit in result['exits']] == [6]
    exit = result['exits'][0]
    assert exit['lastBeat'] == 5.5
    assert exit['barStart'] == 4
    assert exit['sectionEnd'] == 4
    assert exit['sectionAligned'] is True
    assert exit['gridError'] == 0
    assert any(row['code'] == 'phrase_spans_section_boundary' for row in result['conflicts'])


def test_short_breaths_are_merged_and_do_not_create_an_exit():
    track, signals = fixture(vad=((1, 1.8), (2.05, 3.3)), active=((1, 1.8), (2.05, 3.3)))
    result = analyze(track, signals)
    assert len(result['phrases']) == 1
    assert result['phrases'][0]['start'] == 1
    assert result['phrases'][0]['end'] == pytest.approx(3.3)
    assert result['phrases'][0]['sourceRows']['vad'] == [1, 2]
    assert [exit['cut'] for exit in result['exits']] == [4]


def test_next_phrase_prevents_exit_and_model_boundary_from_becoming_section_aligned():
    track, signals = fixture(vad=((1, 3.1), (3.6, 5.1)))
    result = analyze(track, signals)
    assert result['phrases'][0]['nextStart'] == 3.6
    assert all(exit['phraseId'] != result['phrases'][0]['id'] for exit in result['exits'])
    assert [exit['cut'] for exit in result['exits']] == [6]
    assert result['exits'][0]['sectionAligned'] is True
    track['sections'][0]['end'] = 3.5
    track['sections'][1]['start'] = 3.5
    result = analyze(track, signals)
    assert result['exits'][0]['sectionAligned'] is False
    assert result['exits'][0]['sectionEnd'] is None


def test_missing_beat_makes_affected_bar_invalid_without_inventing_a_beat():
    track, signals = fixture(vad=((1, 4.1),))
    track['preprocessing']['beatGrid']['beats_ms'].remove(5000)
    result = analyze(track, signals)
    bar = result['bars'][2]
    assert bar['valid'] is False
    assert bar['beats'] == [4, 4.5, 5.5]
    assert result['exits'] == []


@pytest.mark.parametrize('field,value', [
    ('beats_ms', [0, 500, 1000, 900, 1500, 2000]),
    ('bars_ms', [0, 2000, 1000, 4000]),
    ('beats_ms', []),
    ('beats_ms', [0, 500, float('nan'), 1500, 2000]),
])
def test_missing_or_nonmonotonic_grid_is_unavailable(field, value):
    track, signals = fixture()
    track['preprocessing']['beatGrid'][field] = value
    result = analyze(track, signals)
    assert result['status'] == 'unavailable'
    assert result['exits'] == []


@pytest.mark.parametrize('mutation', [
    lambda t, s: s.update(audio_sha256='stale'),
    lambda t, s: s['vocals']['asset'].update(verified_sha256='stale'),
    lambda t, s: s['vocals']['asset'].update(declared_sha256='stale'),
    lambda t, s: t['preprocessing'].update(reportSha256='stale'),
    lambda t, s: t['preprocessing']['bindingChecks'].update(masterHash=False),
    lambda t, s: t['preprocessing']['vocalActivity']['source'].update(vocal_sha256='stale'),
    lambda t, s: t['provenance'].pop('vocalSha256'),
    lambda t, s: t.pop('preprocessing'),
])
def test_missing_or_different_source_binding_is_unavailable(mutation):
    track, signals = fixture()
    mutation(track, signals)
    result = analyze(track, signals)
    assert result['status'] == 'unavailable'
    assert result['exits'] == []
    assert result['limitations']


def test_explicit_zero_power_bands_remain_null_in_storage():
    track, signals = fixture()
    signals['rms_points'][0]['bands_dbfs'] = {'low': None, 'mid': -24, 'high': None}
    result = analyze(track, signals)
    assert result['bandFrames'] == [{'start': 0, 'end': 12, 'rmsDbfs': -18, 'low': None, 'mid': -24, 'high': None}]


def test_raw_vad_extending_beyond_rms_quiet_remains_protected_with_conflict():
    track, signals = fixture(vad=((1, 4.1),), active=((1, 3.5),))
    result = analyze(track, signals)
    assert result['phrases'][0]['end'] == pytest.approx(4.1)
    assert [exit['cut'] for exit in result['exits']] == [6]
    assert any(row['code'] == 'vad_without_rms_activity' and row['end'] == pytest.approx(4.1)
               for row in result['conflicts'])


def test_rms_extending_beyond_vad_is_also_protected():
    track, signals = fixture(vad=((1, 3.5),), active=((1, 4.1),))
    result = analyze(track, signals)
    assert result['phrases'][0]['end'] == pytest.approx(4.1)
    assert [exit['cut'] for exit in result['exits']] == [6]
    assert any(row['code'] == 'rms_without_vad_activity' for row in result['conflicts'])


@pytest.mark.parametrize('mutation', [
    lambda t, s: t.update(vocals=None),
    lambda t, s: t.update(vocals=[[1, float('inf')]]),
    lambda t, s: s['vocals']['points'].pop(50),
    lambda t, s: s['vocals']['points'][50].update(rms_dbfs=float('nan')),
    lambda t, s: s['vocals'].update(intervals=None),
    lambda t, s: s['vocals'].update(intervals=[]),
    lambda t, s: s['vocals'].update(coverage_sec=6),
    lambda t, s: s['vocals']['parameters'].update(frame_sec=None),
    lambda t, s: s.update(time_origin='unknown'),
])
def test_incomplete_or_invalid_vocal_evidence_is_unavailable(mutation):
    track, signals = fixture()
    mutation(track, signals)
    result = analyze(track, signals)
    assert result['status'] == 'unavailable'
    assert result['exits'] == []


def test_validated_instrumental_evidence_can_exit_at_section_end():
    track, signals = fixture(vad=(), active=())
    result = analyze(track, signals)
    assert result['status'] == 'candidate'
    assert result['phrases'] == []
    assert result['exits'][0]['cut'] == 4
    assert result['exits'][0]['phraseId'] == 'instrumental'
    assert result['exits'][0]['voiceEnd'] == 0
    assert result['exits'][0]['tailEnd'] == 0
    assert result['exits'][0]['nextVoiceStart'] is None
    assert result['exits'][0]['sectionAligned'] is True


def test_analysis_is_bounded_to_playable_track_duration():
    track, signals = fixture(vad=((1, 3.5), (8, 9)))
    track['duration'] = 6
    result = analyze(track, signals)
    assert result['status'] == 'candidate'
    assert len(result['phrases']) == 1
    assert all(row['end'] <= 6 for row in result['bars'] + result['bandFrames'])
    assert all(exit['cut'] <= 6 for exit in result['exits'])


def test_beat_tolerance_uses_observed_times_and_does_not_snap_backward():
    track, signals = fixture(vad=((1, 3.8),))
    track['preprocessing']['beatGrid']['beats_ms'] = [x + 10 for x in track['preprocessing']['beatGrid']['beats_ms']]
    result = analyze(track, signals)
    assert result['bars'][0]['beats'] == [.01, .51, 1.01, 1.51]
    assert result['bars'][0]['end'] == 2.01
    assert not any(exit['cut'] < result['phrases'][0]['tailEnd'] + .25 for exit in result['exits'])


def test_outputs_can_be_serialized_as_strict_json():
    import json
    result = analyze(*fixture())
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('mutation', [
    lambda t, s: s['vocals']['asset'].pop('verified_sha256'),
    lambda t, s: s['vocals']['asset'].pop('declared_sha256'),
    lambda t, s: t['preprocessing']['vocalActivity']['source'].pop('vocal_sha256'),
    lambda t, s: t['preprocessing']['vocalActivity'].update(status='unavailable'),
    lambda t, s: t['preprocessing']['vocalActivity'].update(time_origin='stem_start'),
    lambda t, s: t['preprocessing']['vocalActivity'].update(intervals=[]),
])
def test_raw_vad_and_verified_stem_bindings_are_required(mutation):
    track, signals = fixture()
    mutation(track, signals)
    result = analyze(track, signals)
    assert result['status'] == 'unavailable'
    assert result['exits'] == []


@pytest.mark.parametrize('target', ['vocals', 'master'])
def test_measured_frames_cannot_extend_past_declared_source_duration(target):
    track, signals = fixture()
    if target == 'vocals':
        signals['vocals']['points'].append({'start': 12, 'end': 12.05, 'rms_dbfs': -80})
    else:
        signals['rms_points'][0]['end'] = 13
    result = analyze(track, signals)
    assert result['status'] == 'unavailable'
    assert result['exits'] == []


def test_clipped_phrase_does_not_reference_rms_rows_after_playable_duration():
    track, signals = fixture(vad=((1, 5),))
    track['duration'] = 3
    result = analyze(track, signals)
    phrase = result['phrases'][0]
    assert phrase['end'] == phrase['tailEnd'] == 3
    assert all(signals['vocals']['points'][row - 1]['start'] < 3 for row in phrase['sourceRows']['rms'])


def test_invalid_source_identity_still_returns_strict_json():
    import json
    track, signals = fixture()
    track['provenance']['reportSha256'] = float('nan')
    result = analyze(track, signals)
    assert result['status'] == 'unavailable'
    assert result['source']['reportSha256'] is None
    json.dumps(result, allow_nan=False)


def test_missing_band_field_is_not_silent_power():
    track, signals = fixture()
    del signals['rms_points'][0]['bands_dbfs']['mid']
    result = analyze(track, signals)
    assert result['status'] == 'unavailable'
    assert not result['exits']
