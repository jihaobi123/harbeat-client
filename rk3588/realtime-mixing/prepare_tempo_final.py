"""Prepare the original v4 final-track crop and eight-second fade, per entrance."""
import hashlib
import json
import os
from pathlib import Path
import wave
from realtime import BASE, load_catalog


def build():
    catalog,v4=load_catalog()
    target=BASE/'reports/tempo_assets_v1.json'
    index=json.loads(target.read_text())
    root=BASE/'tempo-assets-v1'
    for pair in index['pairs'].values():
        original=index['assets'][pair['song_id']]
        row=catalog[original['track_id']]
        entry=original['entry_ms']
        exit_ms=v4.choose_exit_cue(row['manifest'],entry,vocal_intervals=row['intervals'],outgoing_overlap_ms=10000).time_ms
        end=min(row['manifest']['source']['duration_ms']-250,exit_ms+10000)
        sid='rtv2-'+hashlib.sha256((pair['song_id']+'|final-v4|'+str(end)).encode()).hexdigest()[:24]
        path=root/(sid+'.wav'); meta=root/(sid+'.json')
        if not meta.exists():
            stage=root/(sid+'.staged.wav')
            v4.render_segment(ffmpeg=v4._ffmpeg(),
                source_path=BASE/'data/edm_8_bundle'/row['bundle'].assets['master'].storage_key,
                output_path=stage,entry_ms=entry,exit_ms=exit_ms,end_ms=end,
                entry_rate=pair['rate'],incoming_overlap_seconds=pair['fade_sec'],final_track=True)
            with wave.open(str(stage)) as w:
                frames=w.getnframes()
            head_end=entry/1000; head_frames=0
            if abs(pair['rate']-1)>0.002 and pair['fade_sec']>0.1:
                head_end=float(f'{entry/1000+min(max(0.05,(end-entry)/1000-0.1),pair["fade_sec"]*pair["rate"]):.3f}')
                head_frames=frames-(round(end/1000*44100)-round(head_end*44100))
                assert head_frames>0
            record=dict(original,song_id=sid,path=str(path),end_ms=end,final_track=True,
                        exit_ms=exit_ms,frames=frames,head_end_sec=head_end,head_output_frames=head_frames,
                        sha256=hashlib.sha256(stage.read_bytes()).hexdigest())
            os.replace(stage,path)
            tmp=meta.with_suffix('.tmp'); tmp.write_text(json.dumps(record,indent=2)); os.replace(tmp,meta)
        record=json.loads(meta.read_text())
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
        alias=Path('/home/cat/cypher/cache')/sid
        alias.mkdir(exist_ok=True)
        link=alias/'original.wav'
        if link.is_symlink():
            assert link.resolve()==path.resolve()
        elif link.exists():
            raise RuntimeError('Refuse overwrite '+str(link))
        else:
            link.symlink_to(path)
        pair['final_song_id']=sid
        index['assets'][sid]=record
        print(sid,flush=True)
    tmp=target.with_suffix('.tmp'); tmp.write_text(json.dumps(index,indent=2)); os.replace(tmp,target)
    print('READY',len(index['assets']),'including final variants')


if __name__=='__main__':
    build()
