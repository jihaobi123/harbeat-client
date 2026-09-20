"""Append-only human calibration, bound to audio and exact preprocessing inputs."""
import fcntl
import json
from datetime import datetime,timezone
from .dj_contract import source_fingerprint,number,ANCHORS
from .report import digest


class Conflict(ValueError):pass


def path(store,report):
    root=store.root/'dj-reviews';root.mkdir(exist_ok=True)
    return root/(digest({'audio_sha256':report['audio'].get('sha256'),'asset':None if report['audio'].get('sha256') else report['audio'].get('assets',{}).get('master',{}).get('id'),'unbound_report':report['id'] if not report['audio'].get('sha256') and not report['audio'].get('assets',{}).get('master',{}).get('id') else None})+'.json')


def load(store,report):
    p=path(store,report)
    return json.loads(p.read_text()) if p.is_file() else {'revision':0,'current':None,'history':[]}


def save(store,report,payload):
    if not isinstance(payload,dict):raise ValueError('需要校准对象')
    revision=payload.get('expected_revision')
    if type(revision) is not int or revision<0:raise ValueError('缺少校准版本号')
    fingerprint=source_fingerprint(report)
    if payload.get('source_fingerprint')!=fingerprint:raise Conflict('分析输入已改变，请重新加载后校准')
    duration=report['summary'].get('duration') or 0
    anchors=payload.get('anchors') or {};checks=payload.get('confirmations') or {};g=payload.get('grid')
    if not isinstance(anchors,dict) or any(k not in ANCHORS or not number(v) or not 0<=v<=duration for k,v in anchors.items()):
        raise ValueError('边界必须是原曲时长内的秒数')
    if not isinstance(checks,dict) or any(k not in ('structure','grid','vocals') or type(v) is not bool for k,v in checks.items()):
        raise ValueError('确认项必须是段落、拍网格、人声的布尔值')
    if g is not None:
        if not isinstance(g,dict) or set(g)!={'beats','downbeats','numerator','denominator'} or g['numerator']!=4 or g['denominator']!=4:
            raise ValueError('拍网格需要 beats、downbeats、numerator=4、denominator=4')
        for key in ('beats','downbeats'):
            values=g[key]
            if not isinstance(values,list) or not 2<=len(values)<=100000 or any(not number(v) or not 0<=v<=duration for v in values) or any(a>=b for a,b in zip(values,values[1:])):
                raise ValueError('拍点必须是时长内严格递增的秒数数组')
    vi=payload.get('vocal_intervals')
    if vi is not None:
        if not isinstance(vi,list) or len(vi)>20000:raise ValueError('人声区间需为数组')
        previous=0
        for x in vi:
            if not isinstance(x,dict) or not number(x.get('start')) or not number(x.get('end')) or not previous<=x['start']<x['end']<=duration:
                raise ValueError('人声区间必须按时间排列，不重叠且在原曲时长内')
            previous=x['end']
    note=payload.get('note','')
    if not isinstance(note,str) or len(note)>2000:raise ValueError('备注最多 2000 字符')
    p=path(store,report)
    with (p.parent/'reviews.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        old=load(store,report)
        if revision!=old['revision']:raise Conflict('另一页面已保存校准，请刷新后重试')
        item={'revision':revision+1,'report_id':report['id'],'source_fingerprint':fingerprint,
              'anchors':anchors,'confirmations':checks,'note':note,'created_at':datetime.now(timezone.utc).isoformat()}
        if g is not None:item['grid']=g
        if vi is not None:item['vocal_intervals']=vi
        result={'revision':revision+1,'current':item,'history':[*old['history'],item]}
        store.write(p,result);return result
