"""Prepare immutable single-track PCM using the user's unmodified v4 renderer.

Never renders a mixtape. All gain/atempo/head-tail processing comes from v4.
"""
import hashlib
import json
import os
from pathlib import Path
import wave
from realtime import BASE, load_catalog


def source_time(asset, playback):
    head = asset['head_output_frames'] / 44100
    if head > 0 and playback < head:
        return asset['entry_sec'] + playback / head * (asset['head_end_sec'] - asset['entry_sec'])
    return asset['head_end_sec'] + max(0, playback - head)


def playback_time(asset, source):
    head = asset['head_output_frames'] / 44100
    if head > 0 and source < asset['head_end_sec']:
        return max(0, source - asset['entry_sec']) / (asset['head_end_sec'] - asset['entry_sec']) * head
    return head + max(0, source - asset['head_end_sec'])


def build():
    catalog, v4 = load_catalog()
    from harbeat.models import TransitionConfig
    from harbeat.transition import build_transition_plan
    config = TransitionConfig(mini_set_size=len(catalog))
    order = [b.track.id for b in v4.order_tracks([r['bundle'] for r in catalog.values()],
              vocal_reports={t:r['intervals'] for t,r in catalog.items()})]
    root = BASE/'tempo-assets-v1'
    root.mkdir(exist_ok=True)
    assets, pairs, starts = {}, {}, {}
    for a in [None] + order:
        for b in order:
            if a == b:
                continue
            row = catalog[b]
            plan = build_transition_plan(catalog[a]['bundle'].track,row['bundle'].track,config) if a else None
            fade = v4.overlap_seconds(plan.method.value,catalog[a]['bundle'].track.bpm,row['bundle'].track.bpm) if a else 0
            rate = plan.bpm_plan.playback_rate if plan else 1.0
            entry = v4.choose_entry_cue(row['manifest'],first_track=a is None,
                       vocal_intervals=row['intervals'],incoming_overlap_ms=int(fade*1000) or v4.DEFAULT_OVERLAP_MS).time_ms
            end = row['manifest']['source']['duration_ms'] - 250
            spec = dict(track_id=b,entry_ms=entry,end_ms=end,rate=rate,fade=fade,
                        manifest_sha256=row['manifest_sha256'],renderer_sha256=hashlib.sha256(Path(v4.__file__).read_bytes()).hexdigest(),version=1)
            key = hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()[:24]
            sid = 'rtv2-'+key
            path = root/(sid+'.wav')
            meta = root/(sid+'.json')
            if not meta.exists():
                stage = root/(sid+'.staged.wav')
                source = BASE/'data/edm_8_bundle'/row['bundle'].assets['master'].storage_key
                v4.render_segment(ffmpeg=v4._ffmpeg(),source_path=source,output_path=stage,
                    entry_ms=entry,exit_ms=end,end_ms=end,entry_rate=rate,
                    incoming_overlap_seconds=fade,final_track=False)
                with wave.open(str(stage)) as wav:
                    assert wav.getframerate()==44100 and wav.getnchannels()==2 and wav.getsampwidth()==2
                    frames = wav.getnframes()
                head_end = entry/1000
                head_frames = 0
                if abs(rate-1)>0.002 and fade>0.1:
                    head_end = float(f'{entry/1000 + min(max(0.05,(end-entry)/1000-0.1),fade*rate):.3f}')
                    tail_frames = round(end/1000*44100) - round(head_end*44100)
                    head_frames = frames-tail_frames
                    assert head_frames>0
                record=dict(spec,song_id=sid,path=str(path),entry_sec=entry/1000,head_end_sec=head_end,
                    head_output_frames=head_frames,frames=frames,sha256=hashlib.sha256(stage.read_bytes()).hexdigest(),
                    renderer='unmodified_vocal_v4_render_segment',gain=v4.RENDER_GAIN)
                os.replace(stage,path)
                temp=meta.with_suffix('.tmp')
                temp.write_text(json.dumps(record,indent=2))
                os.replace(temp,meta)
            record=json.loads(meta.read_text())
            assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
            alias=Path('/home/cat/cypher/cache')/sid
            alias.mkdir(exist_ok=True)
            link=alias/'original.wav'
            if link.is_symlink():
                assert link.resolve()==path.resolve()
            elif link.exists():
                raise RuntimeError('Refuse existing non-symlink asset '+str(link))
            else:
                link.symlink_to(path)
            assets[sid]=record
            if a is None:
                starts[b]=sid
            else:
                pairs[a+'|'+b]=dict(song_id=sid,rate=rate,fade_sec=fade,method=plan.method.value,
                    tempo_relation=plan.bpm_plan.tempo_relation.value,restore_mode='v4_head_then_original_tail',
                    planned_restore_bars=plan.bpm_plan.restore_bars)
            print(json.dumps(dict(from_track=a,to_track=b,song_id=sid,rate=rate,fade_sec=fade)),flush=True)
    index=dict(version='vocal_v4_tempo_assets_v1',order=order,assets=assets,pairs=pairs,starts=starts,
               manifests={t:r['manifest_sha256'] for t,r in catalog.items()})
    target=BASE/'reports/tempo_assets_v1.json'
    temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps(index,indent=2))
    os.replace(temp,target)
    print('READY',len(assets),'variants')


if __name__=='__main__':
    build()
