"""Measure actual separated files without loading whole multichannel songs."""
import numpy as np
import soundfile as sf
import json
from .report import digest


def cache_path(store, assets):
    key = digest({'method':'separated_audio_rms_p95', 'measurement_version':2, 'window_sec':2.0,
                  'assets':{k:assets.get(k,{}).get('id') for k in ('vocals','drums','bass','other')}})
    root = store.root/'stem-cache'
    root.mkdir(exist_ok=True)
    return root/(key+'.json')


def attach_cached(store, documents, assets):
    path=cache_path(store,assets)
    if path.is_file():
        documents['separated_stem_activity']=json.loads(path.read_text())


def measure_stems(assets, registry, window_sec=2.0, on_progress=None):
    rows, measured, problems = {}, {}, {}
    for name in ('vocals', 'drums', 'bass', 'other'):
        asset = assets.get(name)
        if not asset or not asset.get('id'):
            problems[name] = (asset or {}).get('reason', '未找到已登记的分轨文件')
            continue
        if on_progress:
            on_progress(name)
        try:
            path = registry.resolve(asset['id'])
            info = sf.info(path)
            blocksize = max(1, round(window_sec*info.samplerate))
            raw = []
            for block in sf.blocks(path, blocksize=blocksize, dtype='float32', always_2d=True):
                raw.append(float(np.sqrt(np.mean(block.astype(np.float64)**2))))
            reference = float(np.percentile(raw, 95)) if raw else 0
            for i, rms in enumerate(raw):
                row = rows.setdefault(i, {'start': i*window_sec, 'end': min((i+1)*window_sec, info.duration)})
                row[name] = min(1., rms/reference) if reference > 1e-8 else 0.
                row[name+'_rms'] = rms
                row[name+'_dbfs'] = 20*np.log10(max(rms, 1e-9))
            measured[name] = {'asset_id': asset['id'], 'reference_rms_p95': reference,
                              'duration': info.duration, 'sample_rate': info.samplerate,
                              'channels': info.channels}
        except (OSError, ValueError, RuntimeError) as exc:
            problems[name] = str(exc)
    if not measured:
        raise ValueError('没有可读取的真实分轨：' + '; '.join(problems.values()))
    durations=[v['duration'] for v in measured.values()]
    warnings=['分轨时长相差超过 0.1 秒，请检查音轨对齐'] if max(durations)-min(durations)>.1 else []
    return {'method': 'separated_audio_rms_p95', 'measurement_version':2, 'window_sec': window_sec,
            'definition': '真实分轨每窗所有声道均方根 / 该轨整曲 RMS 的第95百分位；非存在概率，也不可跨轨比较绝对响度',
            'warnings':warnings,
            'stem_activity_windows': [rows[i] for i in sorted(rows)],
            'measured_assets': measured, 'missing_stems': problems}
