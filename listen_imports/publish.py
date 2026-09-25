"""Incremental pairing and atomic releases. Existing sessions keep their snapshot."""
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from analysis_platform.media import MediaRegistry
from analysis_platform.store import Store
from scripts.build_continuous_library import Renderer, atomic_json, build_track, file_sha, library_index, recipe_key, variant_recipe
from scripts.package_continuous_site import build_bundle

ROOT = Path(os.environ.get('LISTEN_SITE_ROOT', '/srv/harbeat-listen'))


def inventory(root):
    path = root/'imports/inventory.json'
    if path.exists():
        return json.loads(path.read_text())
    import ijson
    original = root/'deploy-20260924/prepared-jobs.json'
    with original.open('rb') as stream:
        items = list(ijson.items(stream, 'items.item', use_float=True))
    jobs = []
    with original.open('rb') as stream:
        for job in ijson.items(stream, 'jobs.item', use_float=True):
            track = job['track']
            jobs.append({'source':job['source'], 'track':{k:track[k] for k in ('id','bpm')}})
    data = {'items':items,'jobs':jobs,'audit':{}}
    atomic_json(path,data)
    return data


def existing_track(sha):
    data = inventory(ROOT)
    item = next((x for x in data['items'] if x.get('input_sha256') == sha), None)
    if item:
        index = json.loads((ROOT/'current/library.json').read_text())
        return next((x for x in index['tracks'] if x['id'] == item['track_id']), None)


def extend_incoming(track, new, bpms):
    recipes, assignments = [], []
    for window in track['windows']:
        if new['id'] in window['variants']:
            continue
        recipe = variant_recipe(track['provenance']['masterSha256'], window, new['bpm'])
        if recipe is None:
            continue
        equivalent = next((v for identifier,v in window['variants'].items() if bpms.get(identifier) == new['bpm']), None)
        if equivalent:
            window['variants'][new['id']] = copy.deepcopy(equivalent)
        else:
            recipes.append(recipe)
            assignments.append((window, recipe, window['bars']*240/new['bpm']))
    return recipes, assignments


def link_media(assets, media):
    media = Path(media)
    media.mkdir(parents=True, exist_ok=True)
    media.chmod(0o755)
    for asset in assets:
        if not re.fullmatch(r'[a-f0-9]{64}', asset['sha256']):
            raise ValueError('invalid checksum')
        target = media/(asset['sha256']+'.flac')
        source = Path(asset['source'])
        if target.exists():
            # Previously verified content-addressed audio is immutable.
            if target.stat().st_size != asset['bytes']:
                raise ValueError('existing audio size differs')
            target.chmod(0o644)
            continue
        if source.stat().st_size != asset['bytes'] or file_sha(source) != asset['sha256']:
            raise ValueError('new audio checksum mismatch')
        os.link(source, target)
        target.chmod(0o644)


def activate(root, package, version):
    root, package = Path(root), Path(package)
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', version):
        raise ValueError('invalid release name')
    with (root/'release.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = (root/'current').resolve()
        release = root/'releases'/version
        if release.exists():
            raise ValueError('release already exists')
        # Hardlink immutable old snapshots and frontend assets; replace changed
        # files via rename so rollback and active clients keep their old bytes.
        shutil.copytree(previous, release, copy_function=os.link)
        catalog = release/'catalog'/version
        shutil.copytree(package, catalog, copy_function=os.link)
        for path in (package/'evidence').glob('*'):
            destination = release/'evidence'/path.name
            destination.parent.mkdir(exist_ok=True)
            temp = destination.with_name(destination.name+'.next')
            shutil.copyfile(path, temp)
            os.replace(temp, destination)
        index = json.loads((catalog/'library.json').read_text())
        for row in index['tracks']:
            row['detailUrl'] = 'catalog/'+version+'/details/'+row['id']+'.json'
        atomic_json(release/'library.json', index, compressed=True)
        # The worker uses a private umask. Only this already-validated public
        # release and the content-addressed audio are made readable by Nginx.
        release.chmod(0o755)
        for path in release.rglob('*'):
            path.chmod(0o755 if path.is_dir() else 0o644)
        link = root/'current.next'
        link.unlink(missing_ok=True)
        link.symlink_to(release)
        os.replace(link, root/'current')
        return release


def publish(result, evidence_root, progress):
    from .worker import HOST, command
    root = ROOT
    corpus = root/'library'
    jobs_path = root/'imports/inventory.json'
    data = inventory(root)
    item, job = result['item'], result['job']
    new = copy.deepcopy(job['track'])
    existing = existing_track(item['input_sha256'])
    if existing:
        return existing
    # A restart may happen after inventory commit but before public activation.
    previous_index = json.loads((root/'current/library.json').read_text())
    active_ids = {row['id'] for row in previous_index['tracks']}
    base_jobs = [j for j in data['jobs'] if j['track']['id'] in active_ids and j['track']['id'] != new['id']]
    tracks = {row['id']:{**row,'style':row.get('style') or 'unknown:'+row['id']} for row in previous_index['tracks']}
    registry = MediaRegistry(Store(root/'registry'), [root])
    renderer = Renderer(corpus, registry, batch=12)
    def reserve():
        if shutil.disk_usage(root).free < 5*1024**3:
            raise ValueError('服务器音乐存储空间不足；分析结果已保存，请扩容后重试发布。')
    def fetch_source(path, destination, sha):
        source = Path(path)
        if '..' in source.parts or not source.is_relative_to('/mnt/nas/harbeat/preprocess'):
            raise ValueError('invalid analyzed source root')
        command(['rsync', '-a', '--protect-args', '-e', 'ssh -o BatchMode=yes -o StrictHostKeyChecking=yes',
                 HOST+':'+str(source), str(destination)], timeout=600)
        if file_sha(destination) != sha:
            raise ValueError('analyzed master checksum mismatch')
    reserve()
    with tempfile.TemporaryDirectory(dir=corpus/'scratch', prefix='import-') as temp:
        source = Path(temp)/'source'
        fetch_source(job['source'], source, new['provenance']['masterSha256'])
        new, _ = build_track(new, source, [*tracks.values(), new], renderer, corpus)
        if job['track']['mixStatus'] == 'ready' and new['mixStatus'] != 'ready':
            raise ValueError('新歌衔接素材生成失败，已保存分析，请重试。')
        bpms = {t['id']: t['bpm'] for t in tracks.values()}
        for i, old_job in enumerate(base_jobs):
            old_id = old_job['track']['id']
            if tracks[old_id]['mixStatus'] != 'ready' or new['mixStatus'] != 'ready':
                continue
            old = json.loads((corpus/'details'/(old_id+'.json')).read_text())['track']
            reserve()
            progress(f'正在准备新歌的双向衔接：{i+1}/{len(data["jobs"])}')
            recipes, assignments = extend_incoming(old, new, bpms)
            if recipes:
                fetch_source(old_job['source'], source, old['provenance']['masterSha256'])
                assets = renderer.render(source, recipes)
                for window, recipe, duration in assignments:
                    asset = assets[recipe_key(recipe)]
                    if abs(asset['duration']-duration) > .00003:
                        raise ValueError('entry variant duration mismatch')
                    window['variants'][new['id']] = {**{k:v for k,v in asset.items() if k!='recipe'},
                                                    'rate': (window['end']-window['start'])/duration}
            atomic_json(corpus/'details'/(old['id']+'.json'), {'track': old}, compressed=True)
    tracks[new['id']] = new
    (corpus/'evidence').mkdir(exist_ok=True)
    for path in (Path(evidence_root)/'evidence').glob('*'):
        shutil.copyfile(path, corpus/'evidence'/path.name)
    items = [*[x for x in data['items'] if x['track_id'] in active_ids and x['track_id'] != item['track_id']], item]
    index = library_index(items, tracks, {}, '/listen/details/')
    atomic_json(corpus/'library-index.json', index, compressed=True)
    audit = {**data['audit'], 'sourceMixReady': index['coverage']['mixReady'], 'failures': {}, 'coverage': index['coverage']}
    atomic_json(corpus/'corpus-audit.json', audit)
    progress('正在核验音频并更新实时曲库')
    version = 'import-'+str(time.time_ns())
    package = root/'imports/packages'/version
    manifest = build_bundle(corpus, root/'registry', package, root, expected=len(items))
    link_media(manifest['assets'], root/'media')
    # Persist the source inventory before activation, with an idempotent resume:
    # existing_track also requires the item to be in the ACTIVE public catalog.
    if not any(x['track_id']==item['track_id'] for x in data['items']):
        data['items'].append(item)
        data['jobs'].append({'source':job['source'],'track':{k:new[k] for k in ('id','bpm')}})
    data['audit'] = audit
    atomic_json(jobs_path, data, compressed=True)
    activate(root, package, version)
    return new
