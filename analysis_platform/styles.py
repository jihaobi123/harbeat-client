"""Provenance-separated style evidence and revision-checked human reviews."""
from datetime import datetime, timezone
import fcntl
import json
import re
from .report import digest


class ReviewConflict(ValueError): pass


def identity(report):
    audio = report.get('audio') or {}
    # Content identity survives a library/NAS import and report reruns.
    return digest({'audio': audio.get('sha256') or audio.get('assets',{}).get('master',{}).get('id') or report['id']})


def evidence(report):
    result = {'rules': [], 'manual': [], 'dance': [], 'fine_rules': [], 'metadata': [],
              'model': report.get('extensions', {}).get('genre', {'status':'not_run'}),
              'selection_enabled': False}
    for name, original in report['documents'].items():
        if not isinstance(original, dict) or original.get('status') == 'reference_only' or name in ('unverified_sidecars','historical_annotations','source_binding_notes'):
            continue
        doc = original.get('analysis', original)
        if not isinstance(doc, dict): continue
        profile = doc.get('genre_profile') or {}
        if isinstance(profile, dict) and profile:
            entries = profile.get('genres') or []
            manual = (profile.get('method') == 'manual' or profile.get('manual_primary_style') or
                      any(isinstance(x,dict) and x.get('source') == 'manual' for x in entries))
            item = {'path':name+'.genre_profile', 'raw':profile}
            if manual:
                label = profile.get('manual_primary_style') or profile.get('primary_style') or profile.get('primary_genre')
                item['labels'] = [label] if label else [x['name'] for x in entries if isinstance(x,dict) and x.get('source')=='manual' and x.get('name')]
                result['manual'].append(item)
            elif profile.get('method') in ('spotify','spotify_api','spotify_audio_merged','metadata'):
                result['metadata'].append(item)
            else:
                item['score_definition'] = '规则相对匹配分，最高候选可能固定为 1；不是准确率'
                result['rules'].append(item)
        scores = doc.get('dance_style_scores')
        if isinstance(scores, dict) and scores:
            result['dance'].append({'path':name+'.dance_style_scores', 'raw':scores,
                                    'status':doc.get('dance_style_status'),'definition':'舞种适配评分；不与模型分数平均'})
        features=doc.get('music_features') or {}
        if isinstance(features,dict) and features.get('high_frequency_styles'):
            result['fine_rules'].append({'path':name+'.music_features.high_frequency_styles','raw':features['high_frequency_styles']})
    return result


def resolved_identity(store, report):
    key=identity(report)
    path=store.root/'style-reviews'/'aliases.json'
    aliases=json.loads(path.read_text()) if path.is_file() else {}
    for _ in range(16):
        if key not in aliases:return key
        key=aliases[key]
    raise ValueError('invalid review identity aliases')


def review(store, report):
    path = store.root/'style-reviews'/(resolved_identity(store,report)+'.json')
    return json.loads(path.read_text()) if path.is_file() else {'revision':0,'current':None,'history':[]}


def save_review(store, report, payload):
    if not isinstance(payload,dict): raise ValueError('expected review object')
    labels = payload.get('labels')
    status = payload.get('status')
    note = payload.get('note','')
    revision = payload.get('expected_revision')
    if type(revision) is not int or revision < 0: raise ValueError('缺少有效版本号，请刷新后重试')
    if status not in ('confirmed','needs_review'): raise ValueError('invalid review status')
    if not isinstance(labels,list) or len(labels)>20 or any(not isinstance(x,str) or not x.strip() or len(x)>80 for x in labels):
        raise ValueError('标签最多 20 个，每个 1–80 字符')
    if status == 'confirmed' and not labels: raise ValueError('确认前请填写至少一个人工标签')
    if not isinstance(note,str) or len(note)>1000: raise ValueError('备注最多 1000 字符')
    root=store.root/'style-reviews'; root.mkdir(exist_ok=True)
    with (root/'reviews.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous=review(store,report)
        if previous['revision'] != revision: raise ReviewConflict('其他页面已更新人工标签，请刷新后重新确认')
        item={'revision':revision+1,'report_id':report['id'],'labels':list(dict.fromkeys(x.strip() for x in labels)),
              'status':status,'note':note.strip(),'created_at':datetime.now(timezone.utc).isoformat(),
              'source':'human_review','model_used_for_selection':False}
        result={'revision':revision+1,'current':item,'history':[*previous['history'],item]}
        store.write(root/(resolved_identity(store,report)+'.json'),result)
        return result


def bind_review_identity(store, source_report, verified_audio):
    """Alias earlier unbound/asset-only reviews after successful audio verification."""
    source_sha=source_report.get('audio',{}).get('sha256')
    if source_sha and source_sha != verified_audio.get('sha256'):
        raise ValueError('cannot rebind reviews to a different recording')
    destination={**source_report,'audio':verified_audio}
    root=store.root/'style-reviews';root.mkdir(exist_ok=True)
    with (root/'reviews.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        old=resolved_identity(store,source_report);new=resolved_identity(store,destination)
        bindings_path=root/'bindings.json'
        bindings=json.loads(bindings_path.read_text()) if bindings_path.is_file() else {}
        for key in (identity(source_report),old,new):
            if bindings.get(key) and bindings[key] != verified_audio.get('sha256'):
                raise ValueError('这份原报告已绑定另一段音频，不能迁移人工标注')
        if old==new:return
        previous=review(store,source_report);target=review(store,destination)
        if previous['revision'] and target['revision'] and previous != target:
            raise ReviewConflict('同一音频已有另一份人工确认；两份原记录均保留，请先核对标注')
        if previous['revision'] and not target['revision']:
            store.write(root/(new+'.json'),previous)
        path=root/'aliases.json';aliases=json.loads(path.read_text()) if path.is_file() else {}
        aliases[old]=new
        for key in (identity(source_report),old,new):bindings[key]=verified_audio['sha256']
        store.write(bindings_path,bindings)
        store.write(path,aliases)


ALIASES = {'hiphop':'hiphop','hip-hop':'hiphop','hip hop':'hiphop'}


def norm(label):
    value = label.strip().casefold()
    return ALIASES.get(value,value)


def matches(label, candidate):
    target = norm(label)
    parts = candidate.split('---')
    return target in (norm(candidate), norm(parts[0]), norm(parts[-1]))


def comparison_row(report, e, saved):
    current=saved.get('current')
    human=current['labels'] if current and current['status']=='confirmed' else ([] if current else list(dict.fromkeys(x for item in e['manual'] for x in item['labels'])))
    model=e['model']; data=model.get('data') or {}; classes=data.get('classes',[])
    eligible=[label for label in human if any(matches(label,c) for c in classes)]
    top=[x['label'] for x in data.get('top',[])]
    rule_labels=[]
    for rule in e['rules']:
        raw=rule['raw']; rule_labels += [x.get('name','') for x in raw.get('genres',[]) if isinstance(x,dict)]
        if not rule_labels and raw.get('primary_genre'):rule_labels.append(raw['primary_genre'])
    return {'report_id':report['id'],'title':report['title'], 'human':human,
            'human_source':'review' if current else 'original_manual', 'model_status':model.get('status'),
            'model_top':top, 'rules':rule_labels, 'eligible_labels':eligible,
            'uncovered_labels':[label for label in human if label not in eligible] if classes else [],
            'top1_agrees': any(matches(h,c) for h in eligible for c in top[:1]) if eligible else None,
            'top5_agrees': any(matches(h,c) for h in eligible for c in top[:5]) if eligible else None}


def audit(store):
    counts={name:0 for name in ('tracks','rules','manual','dance','fine_rules','metadata','model_ready','reviewed')}
    rows=[];seen=set()
    catalog_seen=set()
    items=store.reports()
    formal=any(item.get('audio',{}).get('catalog_track_id') for item in items)
    for item in items:
        catalog_id=(item.get('audio') or {}).get('catalog_track_id')
        if formal and not catalog_id:continue
        if catalog_id and catalog_id in catalog_seen:continue
        if catalog_id:catalog_seen.add(catalog_id)
        r=store.get_report(item['id'])
        key=resolved_identity(store,r)
        if key in seen:continue
        seen.add(key)
        e=evidence(r);saved=review(store,r)
        counts['tracks']+=1
        for name in ('rules','manual','dance','fine_rules','metadata'):counts[name]+=bool(e[name])
        counts['model_ready']+=e['model'].get('status')=='ready'
        counts['reviewed']+=bool(saved['current'] and saved['current']['status']=='confirmed')
        rows.append(comparison_row(r,e,saved))
    eligible=[r for r in rows if r['top1_agrees'] is not None]
    return {'created_at':datetime.now(timezone.utc).isoformat(),'coverage':counts,'rows':rows,'scope':'current formal catalog only' if formal else 'imported reports',
            'comparison':{'eligible':len(eligible),'top1_agreements':sum(r['top1_agrees'] for r in eligible),
                          'top5_agreements':sum(r['top5_agrees'] for r in eligible),
                          'definition':'与已有人工标签的一致性；并非盲测准确率。只比较可映射标签，人工标签覆盖规则输出时没有独立规则结果可比。',
                          'mapping':ALIASES,'matching':'exact label, exact parent or exact substyle after explicit aliases; any eligible human label'},
            'deployment':{'rules':'原生产服务：genre_classifier 音频规则；人工优先，外部平台标签为可选来源',
                          'dance':'原生产服务：dance_style 舞种适配规则；记录缺失时不补造分数',
                          'fine_rules':'21 类高频风格规则已见于独立本地工作副本；本次未部署该副本。以每首实际字段为准。',
                          'model':'独立 Jetson Analysis Lab：Discogs400 + EffNet，尚不参与自动选歌'}}
