"""Source-bound acoustic phrase candidates, using existing measurements only.

All times are source seconds. This experimental 4/4 policy merges activity gaps
up to 300 ms, protects another 80 ms after activity, and requires a quiet margin
of min(250 ms, half a beat) before an observed complete-bar boundary. A boundary
may be at most one observed bar after the protected tail. These control values
are not estimates of lyrical semantics or calibrated vocal-detection accuracy.
"""
import bisect
import math


SCHEMA = 'harbeat.phrase_alignment.v1'
GRID_TOLERANCE = .04
BREATH_GAP = .3
TAIL_PAD = .08
NEXT_VOICE_PAD = .08
EPSILON = 1e-6
LIMITATIONS = [
    '声学活动候选未经人工或歌词语义确认；静音证据不能证明语义乐句结束。',
    '实验参数：短换气合并 300ms、尾音保护 80ms、下一人声前留 80ms；退出前静音至少为 250ms 与半拍中的较小值。',
    '只使用实际观测到的四拍小节；网格容差 40ms，退出最多延后一个小节，不反向吸附。',
    'VAD 与分离人声 RMS 取保守并集；伴唱、气声和分离泄漏仍需试听，时长一致不证明没有固定延迟。',
    '频段 RMS 为已有滤波器的数字满刻度测量；null 保持未知或低于测量底限，不能当成 0 dBFS。',
]


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _identity(track, signals):
    provenance = track.get('provenance') or {}
    source = {'reportId': track.get('reportId'), **{key: provenance.get(key) for key in
              ('reportSha256', 'masterSha256', 'vocalSha256')}}
    _require(all(isinstance(value, str) and value for value in source.values()), '来源身份不完整')
    evidence = track.get('preprocessing') or {}
    for key in ('reportId', 'reportSha256', 'masterSha256'):
        _require(evidence.get(key) == source[key], '预处理快照来源不匹配：' + key)
    checks = evidence.get('bindingChecks')
    _require(isinstance(checks, dict) and checks.get('reportHash') is True and
             checks.get('masterHash') is True and all(value is True for value in checks.values()),
             '预处理快照未通过来源校验')
    _require(signals.get('audio_sha256') == source['masterSha256'], 'RMS 原曲指纹不匹配')
    for key in ('reportId', 'reportSha256'):
        if key in signals:
            _require(signals[key] == source[key], 'RMS 报告来源不匹配：' + key)
    vocals = signals.get('vocals') or {}
    asset = vocals.get('asset') or {}
    _require(asset.get('verified_sha256') == source['vocalSha256'] and
             asset.get('declared_sha256') == source['vocalSha256'], '分离人声缺少匹配的声明与实测指纹')
    hashes = [asset[key] for key in ('verified_sha256', 'declared_sha256', 'sha256') if key in asset]
    _require(hashes and all(value == source['vocalSha256'] for value in hashes), '分离人声指纹缺失或不匹配')
    vad_evidence = evidence.get('vocalActivity') or {}
    vad_hash = (vad_evidence.get('source') or {}).get('vocal_sha256')
    _require(vad_hash == source['vocalSha256'], '原始 VAD 人声指纹缺失或不匹配')
    _require(vad_evidence.get('status') == 'ready' and vad_evidence.get('time_origin') == 'master_audio_start',
             '原始 VAD 未就绪或时间原点不匹配')
    return source


def _intervals(rows, duration, kind):
    _require(isinstance(rows, list), kind + '区间缺失')
    result = []
    for index, row in enumerate(rows):
        if kind == 'VAD':
            _require(isinstance(row, (list, tuple)) and len(row) == 2, 'VAD 区间格式错误')
            start, end = row
        else:
            _require(isinstance(row, dict), kind + '区间格式错误')
            start, end = row.get('start'), row.get('end')
        _require(_number(start) and _number(end) and 0 <= start < end <= duration + EPSILON,
                 kind + '区间时间无效或超出原始音频')
        _require(not result or start >= result[-1]['start'], kind + '区间未按时间排序')
        result.append({'start': start, 'end': end, 'row': index + 1})
    return result


def _frames(rows, duration, kind, frame_sec=None):
    _require(isinstance(rows, list) and rows, kind + '逐帧测量缺失')
    previous = 0.
    for row in rows:
        _require(isinstance(row, dict), kind + '逐帧测量格式错误')
        start, end = row.get('start'), row.get('end')
        _require(_number(start) and _number(end) and 0 <= start < end and
                 abs(start - previous) <= EPSILON, kind + '逐帧时间不完整或不连续')
        _require('rms_dbfs' in row and (row['rms_dbfs'] is None or _number(row['rms_dbfs'])),
                 kind + 'RMS 值缺失或不是有限数值')
        if frame_sec is not None:
            _require(end - start <= frame_sec + EPSILON, kind + '逐帧宽度超过声明值')
        previous = end
    _require(previous >= duration - EPSILON, kind + '逐帧测量未覆盖播放时长')
    return rows


def _merge(intervals, gap=0):
    output = []
    for row in sorted(intervals, key=lambda value: (value['start'], value['end'])):
        if output and row['start'] - output[-1]['end'] <= gap + EPSILON:
            output[-1]['end'] = max(output[-1]['end'], row['end'])
            output[-1]['vad'].update(row.get('vad', ()))
            output[-1]['rms'].update(row.get('rms', ()))
        else:
            output.append({'start': row['start'], 'end': row['end'],
                           'vad': set(row.get('vad', ())), 'rms': set(row.get('rms', ()))})
    return output


def _vocal_evidence(track, signals, duration):
    source_duration = signals.get('duration')
    _require(_number(source_duration) and source_duration >= duration - EPSILON, 'RMS 来源时长缺失或短于播放素材')
    _require(signals.get('time_origin') == 'master_audio_start', 'RMS 时间原点不是原曲起点')
    vad = _intervals(track.get('vocals'), source_duration, 'VAD')
    raw_vad = track['preprocessing']['vocalActivity'].get('intervals')
    _require(isinstance(raw_vad, list) and len(raw_vad) == len(vad), '运行时 VAD 与来源快照区间数不匹配')
    for row, raw in zip(vad, raw_vad):
        _require(isinstance(raw, dict) and _number(raw.get('start_ms')) and _number(raw.get('end_ms')) and
                 abs(row['start'] - raw['start_ms'] / 1000) <= EPSILON and
                 abs(row['end'] - raw['end_ms'] / 1000) <= EPSILON, '运行时 VAD 与来源快照时间不匹配')
    vocals = signals.get('vocals') or {}
    _require(vocals.get('status') == 'candidate' and vocals.get('source') == 'separated_vocal_rms_hysteresis_v1',
             '分离人声 RMS 算法来源不可用')
    coverage = vocals.get('coverage_sec')
    _require(_number(coverage) and coverage >= duration - EPSILON and
             abs(coverage - source_duration) <= .05 + EPSILON, '分离人声 RMS 覆盖时长不完整')
    parameters = vocals.get('parameters') or {}
    required = ('enter_dbfs', 'exit_dbfs', 'frame_sec', 'min_active_sec', 'merge_gap_sec')
    _require(all(_number(parameters.get(key)) for key in required), 'RMS 滞回参数缺失或无效')
    enter, leave = parameters['enter_dbfs'], parameters['exit_dbfs']
    frame_sec, minimum, merge_gap = (parameters[key] for key in required[2:])
    _require(leave < enter <= 0 and 0 < frame_sec <= .1 and minimum >= 0 and merge_gap >= 0,
             'RMS 滞回参数范围无效')
    rows = _frames(vocals.get('points'), duration, '人声', frame_sec)
    _require(abs(rows[-1]['end'] - coverage) <= EPSILON, '人声逐帧测量与来源时长不匹配')
    declared = _intervals(vocals.get('intervals'), coverage, 'RMS')
    active = False
    active_frames = []
    for index, row in enumerate(rows):
        level = row['rms_dbfs']
        active = level is not None and level > (leave if active else enter)
        if active:
            active_frames.append({'start': row['start'], 'end': row['end'], 'rms': {index + 1}})
    # Replay the published RMS hysteresis algorithm, including its 100 ms
    # coalescing and minimum activity (source parameters, not new thresholds).
    replay = [row for row in _merge(active_frames, merge_gap)
              if row['end'] - row['start'] >= minimum - .0001]
    _require(len(declared) == len(replay) and all(
        abs(a['start'] - b['start']) <= EPSILON and abs(a['end'] - b['end']) <= EPSILON
        for a, b in zip(declared, replay)), 'RMS 活动区间与逐帧滞回重算不一致')
    vad_clipped = [{'start': row['start'], 'end': min(duration, row['end']), 'vad': {row['row']}}
                   for row in vad if row['start'] < duration]
    rms_clipped = [{'start': row['start'], 'end': min(duration, row['end']), 'rms': {index for index in row['rms'] if rows[index - 1]['start'] < duration}}
                   for row in replay if row['start'] < duration]
    return vad_clipped, rms_clipped


def _difference(left, right, code):
    """Keep disagreements visible while union activity remains protective."""
    result = []
    right = _merge(right)
    for row in _merge(left):
        cursor = row['start']
        for other in right:
            if other['end'] <= cursor:
                continue
            if other['start'] >= row['end']:
                break
            if other['start'] > cursor + EPSILON:
                result.append({'code': code, 'start': cursor, 'end': min(other['start'], row['end'])})
            cursor = max(cursor, other['end'])
            if cursor >= row['end']:
                break
        if cursor < row['end'] - EPSILON:
            result.append({'code': code, 'start': cursor, 'end': row['end']})
    return result


def _bars(track, duration):
    grid = track['preprocessing'].get('beatGrid') or {}
    arrays = []
    for name, minimum in (('beats_ms', 5), ('bars_ms', 2)):
        values = grid.get(name)
        _require(isinstance(values, list) and len(values) >= minimum and all(_number(value) and value >= 0 for value in values),
                 '实际拍网格缺失或包含无效时间：' + name)
        _require(all(a < b for a, b in zip(values, values[1:])), '实际拍网格必须严格递增：' + name)
        arrays.append([value / 1000 for value in values])
    beats, boundaries = arrays
    bars, errors = [], {}

    def nearest(value):
        position = bisect.bisect_left(beats, value)
        candidates = [index for index in (position - 1, position) if 0 <= index < len(beats)]
        index = min(candidates, key=lambda i: abs(beats[i] - value))
        return index if abs(beats[index] - value) <= GRID_TOLERANCE + EPSILON else None

    for index, (raw_start, raw_end) in enumerate(zip(boundaries, boundaries[1:])):
        first, following = nearest(raw_start), nearest(raw_end)
        start = beats[first] if first is not None else raw_start
        end = beats[following] if following is not None else raw_end
        if start >= duration or end > duration + EPSILON:
            continue
        lower = first if first is not None else bisect.bisect_left(beats, raw_start)
        upper = following if following is not None else bisect.bisect_left(beats, raw_end)
        observed = beats[lower:upper]
        error = max(abs(start - raw_start), abs(end - raw_end))
        reason = 'four_observed_beats'
        if first is None or following is None:
            reason = 'bar_anchor_not_observed_beat'
        elif len(observed) != 4:
            reason = 'missing_or_extra_observed_beats'
        else:
            step = (end - start) / 4
            error = max(error, max(abs(value - (start + beat * step)) for beat, value in enumerate(observed)))
            if error > GRID_TOLERANCE + EPSILON:
                reason = 'irregular_beat_spacing'
        valid = reason == 'four_observed_beats'
        bars.append({'index': index, 'start': start, 'lastBeat': observed[-1] if observed else None,
                     'end': end, 'beats': observed, 'valid': valid, 'reason': reason})
        errors[index] = error
    _require(any(row['valid'] for row in bars), '播放范围内没有完整的实际四拍小节')
    return bars, errors


def _sections(track, duration, source_duration):
    rows = _intervals(track.get('sections'), source_duration, '模型段落')
    return [{'start': row['start'], 'end': row['end'], 'index': row['row'] - 1}
            for row in rows if row['start'] < duration]


def _band_frames(signals, duration):
    rows = _frames(signals.get('rms_points'), duration, '原曲')
    _require(abs(rows[-1]['end'] - signals['duration']) <= EPSILON, '原曲逐帧测量与来源时长不匹配')
    result = []
    for row in rows:
        if row['start'] >= duration:
            break
        bands = row.get('bands_dbfs') or {}
        _require(isinstance(bands, dict), '频段 RMS 格式错误')
        _require(all(key in bands for key in ('low', 'mid', 'high')), '频段 RMS 缺字段，不能作为静音')
        values = {key: bands[key] for key in ('low', 'mid', 'high')}
        _require(all(value is None or _number(value) for value in values.values()), '频段 RMS 包含非有限数值')
        result.append({'start': row['start'], 'end': min(duration, row['end']),
                       'rmsDbfs': row['rms_dbfs'], **values})
    return result


def _exit(bar, error, phrase, section_end=None):
    return {'id': 'exit-' + phrase['id'] + '-' + str(bar['index']), 'cut': bar['end'],
            'phraseId': phrase['id'], 'voiceEnd': phrase['end'], 'tailEnd': phrase['tailEnd'],
            'nextVoiceStart': phrase['nextStart'], 'sectionEnd': section_end,
            'sectionAligned': section_end is not None, 'lastBeat': bar['lastBeat'],
            'barStart': bar['start'], 'gridError': error,
            'reason': '模型段尾之后，声学尾音保护已完成的实际小节末端' if section_end is not None
                      else '声学尾音保护已完成的实际小节末端；语义乐句未经确认'}


def analyze_alignment(track, signals):
    """Return JSON-ready candidates; invalid evidence returns unavailable/no exits.

    The caller must verify the report file hash when extracting ``signals``.
    Existing dj_signals records contain audio/stem identities but no report hash;
    report identity is checked against the frozen preprocessing snapshot here.
    ``sourceRows`` uses one-based original VAD and vocal RMS point row numbers.
    """
    provenance = track.get('provenance') or {}
    source_values = {'reportId': track.get('reportId'), **{
        key: provenance.get(key) for key in ('reportSha256', 'masterSha256', 'vocalSha256')}}
    result = {'schema': SCHEMA, 'source': {key: value if isinstance(value, str) else None
                                        for key, value in source_values.items()},
        'status': 'unavailable', 'limitations': LIMITATIONS.copy(), 'bars': [], 'phrases': [],
        'exits': [], 'conflicts': [], 'bandFrames': [],
        'parameters': {'breathGapSec': BREATH_GAP, 'tailPadSec': TAIL_PAD, 'nextVoicePadSec': NEXT_VOICE_PAD},
        'energyDefinitions': signals.get('definitions', {}) if isinstance(signals, dict) else {}}
    try:
        result['source'] = _identity(track, signals)
        duration = track.get('duration')
        _require(_number(duration) and duration > 0, '播放时长无效')
        vad, rms = _vocal_evidence(track, signals, duration)
        bars, grid_errors = _bars(track, duration)
        sections = _sections(track, duration, signals['duration'])
        frames = _band_frames(signals, duration)
        conflicts = _difference(vad, rms, 'vad_without_rms_activity') + _difference(rms, vad, 'rms_without_vad_activity')
        phrases = []
        for index, row in enumerate(_merge(vad + rms, BREATH_GAP)):
            section_index = next((section['index'] for section in sections
                                  if section['start'] <= row['start'] < section['end']), -1)
            phrases.append({'id': 'phrase-' + str(index), 'start': row['start'], 'end': row['end'],
                            'tailEnd': min(duration, row['end'] + TAIL_PAD), 'nextStart': None,
                            'sectionIndex': section_index, 'sourceRows': {'vad': sorted(row['vad']), 'rms': sorted(row['rms'])},
                            'semanticStatus': 'unverified'})
        exits = []
        for index, phrase in enumerate(phrases):
            next_start = phrases[index + 1]['start'] if index + 1 < len(phrases) else None
            phrase['nextStart'] = next_start
            for section in sections:
                if phrase['start'] < section['end'] < phrase['end']:
                    conflicts.append({'code': 'phrase_spans_section_boundary', 'phraseId': phrase['id'],
                                      'sectionIndex': section['index'], 'sectionEnd': section['end'],
                                      'start': phrase['start'], 'end': phrase['end']})
            for bar in bars:
                if not bar['valid']:
                    continue
                cut = bar['end']
                bar_duration = cut - bar['start']
                quiet_margin = min(.25, bar_duration / 8)
                if cut < phrase['tailEnd'] + quiet_margin - EPSILON or cut - phrase['tailEnd'] > bar_duration + EPSILON:
                    continue
                if next_start is not None and cut > next_start - NEXT_VOICE_PAD + EPSILON:
                    continue
                aligned = [section['end'] for section in sections
                           if phrase['start'] <= section['end'] <= cut and cut - section['end'] <= bar_duration + EPSILON]
                exits.append(_exit(bar, grid_errors[bar['index']], phrase, max(aligned) if aligned else None))
        if not phrases:
            instrumental = {'id': 'instrumental', 'end': 0, 'tailEnd': 0, 'nextStart': None}
            for section in sections:
                bar = next((bar for bar in bars if bar['valid'] and section['end'] <= bar['end'] and
                            bar['end'] - section['end'] <= bar['end'] - bar['start'] + EPSILON), None)
                if bar:
                    candidate = _exit(bar, grid_errors[bar['index']], instrumental, section['end'])
                    if not any(row['cut'] == candidate['cut'] for row in exits):
                        exits.append(candidate)
        result.update(status='candidate', bars=bars, phrases=phrases, exits=exits,
                      conflicts=conflicts, bandFrames=frames)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        result['limitations'].append('无法生成可执行边界：' + str(error))
    return result
