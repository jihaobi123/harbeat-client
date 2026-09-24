#!/usr/bin/env python3
"""Append source-verified songs to frozen V3.1; preserve every existing input.

Selection uses only tempo, vocal coverage and the original top-style eligibility.
No cross-track transition is rendered, and no experiment score is consulted.
"""
import argparse
import copy
import gzip
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis_platform.phrase_alignment import analyze_alignment
from scripts.build_decision_evidence import attach


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def ordinary_windows(track):
    """The unchanged ordinary V3 recipe from build_v31_corpus.py."""
    bars = track['bars']
    starts = {0}
    for section in track['sections']:
        index = min(range(len(bars)), key=lambda i: abs(bars[i] - section['start']))
        if bars[index] < 90:
            starts.add(index)
    return [dict(id=f'w{i}-{n}', start=bars[i], end=bars[i+n], bars=n,
                 role=next((s['label'] for s in track['sections'] if s['start'] <= bars[i] < s['end']), 'unclassified'),
                 energy=0, variants={})
            for i in sorted(starts)[:4] for n in [2, 4]
            if i+n < len(bars) and bars[i+n]+12 <= track['duration']]


def select_new(rows, frozen_rows, count):
    chosen = list(frozen_rows)
    additions = []
    while len(additions) < count:
        hashes = {r['sha'] for r in chosen}
        ids = {r['track_id'] for r in chosen}
        titles = {r['title'].casefold().strip() for r in chosen}
        rest = [r for r in rows if r.get('eligible') and r['sha'] not in hashes
                and r['track_id'] not in ids and r['title'].casefold().strip() not in titles]
        if not rest:
            break
        def distance(row):
            measured = min(abs(row['bpm']-old['bpm'])/80
                           + abs(row['vocalCoverage']-old['vocalCoverage']) for old in chosen)
            novelty = .2 if row['style'][0]['style'] not in {x['style'][0]['style'] for x in chosen} else 0
            return measured + novelty
        selected = min(rest, key=lambda r: (-distance(r), r['track_id']))
        chosen.append(selected)
        additions.append(selected)
    return additions


def assert_original_preserved(originals, expanded, new_ids):
    by_id = {t['id']: t for t in expanded}
    for original in originals:
        projected = copy.deepcopy(by_id[original['id']])
        for window in projected['windows']:
            window['variants'] = {key: value for key, value in window['variants'].items() if key not in new_ids}
        assert projected == original, 'Frozen original changed: ' + original['id']


def preview_duration(master_ms, measured):
    duration = min(150, master_ms / 1000)
    # Contract milliseconds can round up beyond the measured final audio frame.
    # Only repair that sub-millisecond representation difference, not missing data.
    if isinstance(measured, (int, float)) and abs(duration-measured) <= .001:
        duration = min(duration, measured)
    return duration


def prepare(raw, report, nas):
    core = report['documents']['core']
    analysis = core.get('analysis')
    assert isinstance(analysis, dict), 'canonical preprocessing core analysis unavailable'
    master = core['assets']['master']
    vad = report['documents']['vocal_activity']
    signals = report['extensions']['dj_signals']['data']
    genre = report['extensions']['genre']['data']
    top = genre['top'][0]
    assert top['parent'] == 'Hip Hop' or top['style'] in ('Trap', 'Grime'), 'top style outside original scope'
    assert genre['audio_sha256'] == master['sha256'], 'genre audio binding mismatch'
    assert vad['status'] == 'ready', 'vocal activity not ready'
    assert vad['source']['track_id'] == core['track_id'], 'vocal track binding mismatch'
    assert vad['source']['analysis_run_id'] == core['analysis_run_id'], 'vocal analysis run mismatch'
    assert vad['source']['vocal_sha256'] == core['assets']['stems']['vocals']['sha256'], 'vocal stem binding mismatch'
    duration = preview_duration(master['duration_ms'], signals.get('duration'))
    bars = [x/1000 for x in analysis['beat_grid']['bars_ms'] if x/1000 < duration]
    bpm = analysis['tempo']['bpm']
    assert len(bars) > 4, 'insufficient observed bars'
    assert abs(240/statistics.median([y-x for x,y in zip(bars,bars[1:])])/bpm-1) < .05, 'beat grid and tempo disagree'
    source = (nas / master['storage_key']).resolve()
    assert source.is_relative_to(nas.resolve()) and source.is_file(), 'published source missing'
    assert sha(source) == master['sha256'], 'published source SHA mismatch'
    track = dict(id=core['track_id'], title=report['title'], bpm=bpm, duration=duration,
        style=top['style'], styleScore=top['score'], native={}, bars=bars,
        sections=[dict(start=x['start_ms']/1000, end=x['end_ms']/1000, label=x['label']) for x in analysis['sections']['items']],
        vocals=[[x['start_ms']/1000, x['end_ms']/1000] for x in vad['intervals']],
        energy=[dict(start=x['start_ms']/1000, end=x['end_ms']/1000, value=x['value']) for x in analysis['energy']['curve']],
        windows=[], warnings=['模型段落、拍网格均非人工真值'] + (['BPM 待确认'] if analysis['tempo'].get('needs_review') else []),
        reportId=report['id'], provenance=dict(masterSha256=master['sha256'], reportSha256=hashlib.sha256(raw).hexdigest(),
            runId=core['analysis_run_id'], sectionSource=analysis['sections']['source'], vocalSha256=core['assets']['stems']['vocals']['sha256']))
    track['windows'] = ordinary_windows(track)
    assert track['windows'], 'no ordinary V3 windows'
    for window in track['windows']:
        weights = [(max(0, min(min(duration, window['end']+16), item['end'])-max(window['end'], item['start'])), item['value']) for item in track['energy']]
        denominator = sum(length for length, value in weights)
        window['energy'] = sum(length*value for length,value in weights)/denominator if denominator else 0
    return track, source, signals


def main():
    parser = argparse.ArgumentParser()
    for flag in ('frozen', 'index', 'reports', 'nas', 'out', 'static'):
        parser.add_argument('--'+flag, type=Path, required=True)
    parser.add_argument('--count', type=int, default=12)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    assert args.frozen.resolve() != (args.out/'catalog.json').resolve(), 'output must not replace the frozen catalog'
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/'media').mkdir(exist_ok=True)
    public = '/analysis-lab-static/' + args.out.name + '/'
    frozen = json.loads(args.frozen.read_text())
    old = frozen['tracks']
    latest = {}
    index_raw = args.index.read_bytes()
    index = json.loads(index_raw)
    for row in sorted(index.values(), key=lambda x: (x['created_at'], x['id'])):
        latest[row['audio'].get('sha256') or ('unknown:'+row['id'])] = row
    frozen_rows = [dict(track_id=t['id'], title=t['title'], sha=t['provenance']['masterSha256'], bpm=t['bpm'],
        vocalCoverage=t['preprocessing']['vocalActivity']['coverage_ratio'], style=[{'style':t['style']}]) for t in old]
    old_hashes = {t['sha'] for t in frozen_rows}
    rows, prepared, reports, sources = [], {}, {}, {}
    for entry in sorted(latest.values(), key=lambda e:e['id']):
        row = dict(reportId=entry['id'], title=entry['title'], sha=entry['audio'].get('sha256'), eligible=False, exclusion=None)
        rows.append(row)
        if row['sha'] in old_hashes:
            row['exclusion'] = 'already in frozen 20'; continue
        try:
            raw = (args.reports/(entry['id']+'.json')).read_bytes()
            report = json.loads(raw)
            assert report['id'] == entry['id'], 'report identity mismatch'
            genre = (report.get('extensions',{}).get('genre') or {}).get('data') or {}
            row['style'] = genre.get('top',[])[:3]
            assert row['style'] and (row['style'][0]['parent']=='Hip Hop' or row['style'][0]['style'] in ('Trap','Grime')), 'top style outside original scope'
            track, source, signals = prepare(raw, report, args.nas)
            assert track['provenance']['masterSha256'] == row['sha'], 'index source identity mismatch'
            row.update(track_id=track['id'], bpm=track['bpm'], vocalCoverage=report['documents']['vocal_activity']['coverage_ratio'])
            # Reuse the existing whitelisted evidence builder, then require valid EQ alignment.
            track['native'] = {'url': public+'pending.flac'}
            temp = args.out/'candidate-input.json'
            temp.write_text(json.dumps({'tracks':[track]}))
            attached = attach(temp, {report['id']:(raw,report)}, args.out, public, public+'evidence/')['tracks'][0]
            attached['alignment'] = analyze_alignment(attached, signals)
            assert attached['alignment']['status']=='candidate', '; '.join(attached['alignment']['limitations'][-1:])
            assert attached['alignment']['bandFrames'], 'dynamic EQ band evidence missing'
            prepared[track['id']] = attached
            sources[track['id']] = source
            reports[report['id']] = (raw, report)
            row['eligible'] = True
        except (KeyError, TypeError, ValueError, AssertionError, OSError) as error:
            row['exclusion'] = str(error) or type(error).__name__
    chosen = select_new(rows, frozen_rows, args.count)
    new_ids = {row['track_id'] for row in chosen}
    for row in rows:
        row['selected'] = row.get('track_id') in new_ids
    audit = dict(schema='harbeat.vocal-overlap-corpus-audit.v1', frozenCatalogSha256=sha(args.frozen),
        sourceIndexSha256=hashlib.sha256(index_raw).hexdigest(),
        selection='原 V3 顶层风格条件；按 BPM、人声覆盖率、风格差异确定性补充；不使用实验得分或成功率',
        requestedNewCount=args.count, selectedNewCount=len(chosen), originalCount=len(old),
        sourceInventoryCount=len(rows), reportSnapshotCount=len(index),
        uniqueIdentifiedSourceCount=len({r['sha'] for r in rows if r['sha']}),
        missingIdentityEntries=sum(not r['sha'] for r in rows), originalTracks=frozen_rows, newTracks=chosen, rows=rows,
        previewLimitSec=150, ordinaryV3Windows=True, originalPreservation='原曲目所有字段保持；只允许旧窗口新增面向新 A 曲目的变速素材')
    (args.out/'corpus-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print('PLAN',json.dumps([(r['title'],r['bpm'],r['vocalCoverage']) for r in chosen],ensure_ascii=False),flush=True)
    if args.plan_only:
        return
    tracks = copy.deepcopy(old) + [prepared[row['track_id']] for row in chosen]
    # Frozen reports identify the exact masters for additive new-A variants.
    for track in old:
        raw = (args.reports/(track['reportId']+'.json')).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==track['provenance']['reportSha256'], 'frozen report changed'
        report = json.loads(raw)
        source = (args.nas/report['documents']['core']['assets']['master']['storage_key']).resolve()
        assert source.is_relative_to(args.nas.resolve()) and sha(source)==track['provenance']['masterSha256'], 'frozen source changed'
        sources[track['id']] = source
    commands = []
    def encode(track, filt):
        recipe = dict(sourceSha256=track['provenance']['masterSha256'], filter=filt, format='flac-s16-stereo-44100-frame4096-v1')
        key = hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
        dest = args.out/'media'/(key+'.flac'); meta=dest.with_suffix('.json')
        if dest.exists() and meta.exists():
            cached=json.loads(meta.read_text())
            if cached.get('recipe')==recipe and sha(dest)==cached['sha256']:
                return cached
        assert shutil.disk_usage(args.out).free > 900*1024*1024, 'less than 900 MB free'
        tmp = dest.with_suffix('.part.flac')
        subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(sources[track['id']]),'-vn','-af',filt,
            '-ar','44100','-ac','2','-c:a','flac','-sample_fmt','s16','-frame_size','4096',str(tmp)],check=True,timeout=180)
        tmp.replace(dest)
        duration=float(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(dest)]))['format']['duration'])
        asset=dict(url=public+'media/'+dest.name,sha256=sha(dest),duration=duration,bytes=dest.stat().st_size,recipe=recipe)
        meta.write_text(json.dumps(asset)); commands.append(recipe)
        return asset
    for track in tracks:
        if track['id'] in new_ids:
            track['native']=encode(track,f'atrim=end={track["duration"]:.6f},asetpts=PTS-STARTPTS')
            track['duration']=track['native']['duration']
        else:
            native=args.static/track['native']['url'].removeprefix('/analysis-lab-static/')
            assert sha(native)==track['native']['sha256'], 'frozen native changed'
        for window in track['windows']:
            for a in tracks:
                if a['id']==track['id'] or a['id'] in window['variants']:
                    continue
                # Never fill old-to-old gaps; only additions involving a new song are in scope.
                if track['id'] not in new_ids and a['id'] not in new_ids:
                    continue
                duration=window['bars']*240/a['bpm']; rate=(window['end']-window['start'])/duration
                if not .8 <= rate <= 1.2:
                    continue
                filt=f'atrim=start={window["start"]:.6f}:end={window["end"]:.6f},asetpts=PTS-STARTPTS,atempo={rate:.9f},apad=whole_dur={duration:.9f},atrim=end={duration:.9f}'
                asset=encode(track,filt)
                assert abs(asset['duration']-duration)<.00003, 'rendered duration mismatch'
                window['variants'][a['id']]=dict(asset,rate=rate)
        print('BUILT',track['title'],len(commands),flush=True)
    assert_original_preserved(old,tracks,new_ids)
    catalog=copy.deepcopy(frozen)
    catalog.update(schema='harbeat.vocal-overlap-corpus.v1',tracks=tracks,
        corpus=dict(frozenCatalogSha256=sha(args.frozen), originalTrackIds=[t['id'] for t in old],newTrackIds=sorted(new_ids)))
    data=json.dumps(catalog,ensure_ascii=False,separators=(',',':')).encode()
    (args.out/'catalog.json').write_bytes(data)
    (args.out/'catalog.json.gz').write_bytes(gzip.compress(data,mtime=0))
    audit.update(originalProjectionUnchanged=True, totalTracks=len(tracks), totalWindows=sum(len(t['windows']) for t in tracks),
        newlyRenderedAssets=len(commands), catalogSha256=hashlib.sha256(data).hexdigest())
    (args.out/'corpus-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    (args.out/'asset-build.json').write_text(json.dumps(dict(singleSongOnly=True,newRecipes=commands,
        ffmpeg=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]),indent=2))
    print('DONE',len(tracks),'tracks',len(commands),'new assets',flush=True)


if __name__ == '__main__':
    main()
