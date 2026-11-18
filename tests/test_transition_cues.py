from analysis_platform.transition_cues import build_cues, read_cues, write_cues
from analysis_platform.transition_cue_import import netease_lyrics
from analysis_platform.transition_policy import incoming_phrase, propose_pair
from analysis_platform.transition_policy_review import review


def track():
    vocal = {'status': 'ready', 'time_origin': 'master_audio_start',
             'source': {'track_id': 'b', 'analysis_run_id': 'run', 'vocal_sha256': 'voice'},
             'intervals': [{'start_ms': 10000, 'end_ms': 12100},
                           {'start_ms': 12300, 'end_ms': 15000}]}
    return {'id': 'b', 'duration': 30,
            'provenance': {'masterSha256': 'master', 'reportSha256': 'report',
                           'runId': 'run', 'vocalSha256': 'voice', 'sectionSource': 'songformer'},
            'sections': [{'start': 0, 'end': 9.9, 'label': 'intro'},
                         {'start': 9.9, 'end': 12.2, 'label': 'verse'},
                         {'start': 12.2, 'end': 20, 'label': 'chorus'},
                         {'start': 20, 'end': 30, 'label': 'outro'}],
            'preprocessing': {'vocalActivity': vocal},
            'alignment': {'status': 'candidate', 'source': {
                'masterSha256': 'master', 'reportSha256': 'report', 'vocalSha256': 'voice'},
                'phrases': [{'start': 10, 'tailEnd': 15.08, 'nextStart': None}],
                'bars': [], 'exits': [{'cut': 12.2}, {'cut': 16}, {'cut': 21}]}}


def test_track_cues_keep_lyrics_private_and_protect_tail_over_section_boundary(tmp_path):
    song = track()
    lyrics = {'masterSha256': 'master', 'lrc': '[00:10]歌詞原文\n[00:13]第二句'}
    data = write_cues(tmp_path, song, lyrics)
    assert data['entries'][0] == {'startMs': 10000, 'endMs': 12100, 'basis': 'lyric-and-vocal'}
    assert [row['time'] for row in data['exits']] == [16, 21]
    assert data['sections'][2]['label'] == 'chorus'
    assert '歌詞原文' not in (tmp_path / 'transition-cues.json').read_text()
    assert read_cues(tmp_path, song) == data
    song['provenance']['runId'] = 'new-run'
    assert read_cues(tmp_path, song) is None


def test_lyrics_without_matching_recording_cannot_override_acoustic_vocal():
    song = track()
    data = build_cues(song, {'masterSha256': 'another-master', 'lrc': '[00:10]一段詞'})
    assert data['lyricStatus'] == 'source_mismatch'
    assert data['entries'][0]['basis'] == 'acoustic'
    assert not any(row['time'] == 12.2 for row in data['exits'])
    assert incoming_phrase(data, 12.2)['kind'] == 'inside_vocal'
    assert incoming_phrase(data, 12.2)['onsetMs'] == 10000


def test_planner_uses_preprocessed_evidence_for_a_mid_sentence_entry():
    incoming = track()
    outgoing = {**track(), 'id': 'a'}
    outgoing['preprocessing']['vocalActivity']['source']['track_id'] = 'a'
    lyrics = {'masterSha256': 'master', 'lrc': '[00:10]第一句\n[00:13]下一句'}
    result = propose_pair(outgoing, incoming, None, b_entry=10.4,
                          b_cues=build_cues(incoming, lyrics))
    assert result['entryFinding'] == {'kind': 'mid_line', 'onsetMs': 10000, 'markMs': 10000}
    assert all(row['bStart'] < 10 for row in result['candidates'])


def test_provider_lookup_rejects_unbound_version_before_network():
    identity = 'a' * 64
    song = {**track(), 'id': 'track-' + identity[:20]}
    candidate = {'id': '42', 'source': 'netease', 'duration': 27}
    assert netease_lyrics({'kind': 'download', 'sha256': identity, 'candidate': candidate}, song) is None
    assert netease_lyrics({'kind': 'upload', 'sha256': identity,
                           'candidate': {**candidate, 'duration': 30}}, song) is None


def test_pair_without_a_candidate_returns_the_original_fallback():
    a, b = ({'job': {'track': {'id': name}}} for name in ('a', 'b'))
    empty = {'from': 'a', 'to': 'b', 'candidates': [], 'reason': 'incoming_vocal_unverified'}
    assert review(a, b, empty, None, None)['winner']['method'] == 'original-player-fallback'
