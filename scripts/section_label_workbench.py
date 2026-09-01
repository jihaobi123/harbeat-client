#!/usr/bin/env python3
"""Local, dependency-free browser workbench for section-label review."""

from __future__ import annotations

import argparse
import copy
import gzip
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_relabel_dataset import (
    DatasetValidationError,
    TRACK_EXCLUSION_REASON,
    validate_annotation,
    validate_annotation_patch,
    validate_dataset,
)
from app.modules.library.section_annotation_partitions import (
    annotation_is_reviewed,
    ensure_annotation_partition,
    partition_summary,
    resolve_access,
    track_is_excluded,
)


LABELS = (
    "intro",
    "verse",
    "chorus",
    "bridge",
    "instrumental",
    "outro",
    "silence",
    "pre-chorus",
)


class AnnotationConflictError(RuntimeError):
    """Raised when a browser attempts to overwrite a newer annotation."""

HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>HarBeat 双人段落标注</title><style>
*{box-sizing:border-box}body{margin:0;font:14px system-ui;background:#0b1020;color:#e8edf7}
header{position:sticky;top:0;z-index:3;padding:12px 18px;background:#11182b;border-bottom:1px solid #27314c;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
main{display:grid;grid-template-columns:320px 1fr;min-height:calc(100vh - 65px)}aside{border-right:1px solid #27314c;padding:12px;overflow:auto;height:calc(100vh - 65px)}
#content{padding:18px;max-width:1200px}.track{padding:9px;border-radius:8px;margin:4px 0;cursor:pointer}.track:hover,.track.active{background:#202b47}
.done{color:#65d69e}.pending{color:#f3bd55}.readonly{color:#8fc5ff}.warning{color:#ff9f9f}.muted{color:#94a2bd}
.segment{border:1px solid #2a3655;border-radius:10px;padding:12px;margin:10px 0;background:#121a2e}.segment.selected{border-color:#66a2ff}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.label{padding:7px 10px;border:1px solid #3b4b72;border-radius:8px;background:#18213a;color:#e8edf7;cursor:pointer}.label:hover{border-color:#66a2ff}.label.current{background:#255a9b}.label.human{background:#246a4a}.label.draft{background:#8a5b18;border-color:#f3bd55}.label:disabled,select:disabled,textarea:disabled{cursor:not-allowed;opacity:.65}
.submit-bar{position:sticky;top:62px;z-index:2;padding:10px;margin:10px 0;background:#18213a;border:1px solid #344260;border-radius:10px}.submit-track{background:#246a4a;font-weight:700}
audio{width:min(760px,100%)}.prob{font-family:ui-monospace,monospace}textarea{width:100%;min-height:44px;background:#0c1325;color:#e8edf7;border:1px solid #344260;border-radius:7px;padding:7px}select{background:#10182b;color:#e8edf7;border:1px solid #344260;padding:6px;border-radius:6px}
@media(max-width:800px){main{display:block}aside{height:240px;border-right:0;border-bottom:1px solid #27314c}}
</style></head><body>
<header><b>HarBeat 双人段落标注</b><span id="scope"></span><span id="progress"></span><span class="muted">每 5 秒同步 · A=接受 · 1–8=改标签 · U=不确定 · B=边界问题 · 空格=播放</span></header>
<main><aside><div class="row"><select id="split"><option value="all">全部</option><option value="development">开发集</option><option value="test">测试集</option></select><select id="status"><option value="all">全部状态</option><option value="pending">未完成</option><option value="done">已完成</option></select></div><div id="tracks"></div></aside><section id="content"><p>正在验证访问链接……</p></section></main>
<script>
const LABELS=['intro','verse','chorus','bridge','instrumental','outro','silence','pre-chorus'];
const ZH={intro:'前奏',verse:'主歌',chorus:'副歌',bridge:'桥段',instrumental:'器乐段',outro:'尾奏',silence:'静音','pre-chorus':'预副歌'};
const targetLabel=l=>l;
const accessKey=new URLSearchParams(location.search).get('key')||'';
const sameOrigin=location.protocol+'//'+location.host;
let data=null,track=null,selected=0,stopTimer=null,loading=false,drafts={};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const annotationDone=s=>{const a=s.annotation||{};return !!a.human_label||a.uncertain||a.boundary_ok===false};
const trackExcluded=t=>t?.annotation_exclusion?.excluded===true;
const trackDone=t=>trackExcluded(t)||(t.segments.length>0&&t.segments.every(annotationDone));
const segmentEditable=s=>!data.access.review_mode||annotationDone(s);
function refreshProgress(){const g=data.annotation_progress.global,own=data.annotation_progress.partitions[data.access.scope];document.querySelector('#scope').innerHTML=data.access.review_mode?'<span class="readonly">全部结果 · 可复核修正</span>':`<span class="done">${esc(data.access.scope)} · 初标可编辑</span>`;document.querySelector('#progress').textContent=`总进度 ${g.reviewed_segments}/${g.segments} 段，${g.completed_tracks}/${g.tracks} 首 · 已排除 ${g.excluded_tracks||0} 首${own?` · 本分片 ${own.reviewed_segments}/${own.segments} 段`:''}`}
function renderTracks(){if(!data)return;const split=document.querySelector('#split').value,status=document.querySelector('#status').value;let html='';for(const t of data.tracks){const done=trackDone(t),excluded=trackExcluded(t);if(split!=='all'&&t.split!==split)continue;if(status==='done'&&!done)continue;if(status==='pending'&&done)continue;html+=`<div class="track ${track&&track.track_id===t.track_id?'active':''}" data-id="${esc(t.track_id)}"><div>${esc(t.display_name)}</div><small class="${excluded?'warning':(done?'done':'pending')}">${esc(t.style)} · ${t.segments.length}段 · ${excluded?'已排除，不参与':(done?'已标注':'待标注')}${data.access.review_mode?` · ${esc(t.annotation_partition_id)}`:''}</small></div>`}document.querySelector('#tracks').innerHTML=html||'<p class="muted">没有符合条件的歌曲。</p>';document.querySelectorAll('.track').forEach(el=>el.onclick=()=>selectTrack(el.dataset.id));refreshProgress()}
function selectTrack(id){track=data.tracks.find(t=>t.track_id===id)||null;selected=0;renderTracks();renderContent()}
function probs(s){const p=s.structure_label_probabilities||{};return Object.entries(p).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`${ZH[k]||k} ${(100*v).toFixed(1)}%`).join('　')}
function baseAnnotation(s){const a=s.annotation||{};if(annotationDone(s))return {human_label:a.human_label||'',human_confidence:a.human_confidence||'',boundary_ok:a.boundary_ok!==false,uncertain:!!a.uncertain,notes:a.notes||''};return {human_label:targetLabel(s.structure_label_candidate),human_confidence:'high',boundary_ok:true,uncertain:false,notes:''}}
function hasDraft(i){return !!(track&&drafts[track.track_id]&&drafts[track.track_id][i])}
function effectiveAnnotation(i){return hasDraft(i)?drafts[track.track_id][i]:baseAnnotation(track.segments[i])}
function choiceText(i){const s=track.segments[i],a=effectiveAnnotation(i),pending=hasDraft(i);if(!pending&&!annotationDone(s))return `<span class="muted">当前沿用原标签：<b>${ZH[a.human_label]||a.human_label}</b></span>`;if(a.uncertain)return `<span class="${pending?'pending':'warning'}">${pending?'待提交：':''}不确定</span>`;if(a.boundary_ok===false)return `<span class="${pending?'pending':'warning'}">${pending?'待提交：':''}边界有问题</span>`;if(a.human_label)return `<span class="${pending?'pending':'done'}">${pending?'待提交':'人工标签'}：<b>${ZH[a.human_label]||a.human_label}</b></span>`;return '<span class="muted">未选择</span>'}
function renderContent(){if(!track){document.querySelector('#content').innerHTML='<p>请选择歌曲。</p>';return}if(trackExcluded(track)){document.querySelector('#content').innerHTML=`<h2>${esc(track.display_name)}</h2><p class="warning">这首歌已标记为“结构太混乱”，不参与标注、训练和测试评估。</p><audio id="audio" controls preload="metadata" src="/audio/${encodeURIComponent(track.track_id)}"></audio><div class="submit-bar row"><button class="label restore-track">恢复参与</button><span class="muted">歌曲和已有标注均未物理删除，可随时恢复。</span></div>`;document.querySelector('.restore-track').onclick=()=>setTrackExcluded(false);return}const cards=track.segments.map((s,i)=>{const a=effectiveAnnotation(i),pending=hasDraft(i),human=a.human_label||'',disabled=segmentEditable(s)?'':'disabled';const buttons=LABELS.map((l,j)=>`<button ${disabled} class="label ${l===targetLabel(s.structure_label_candidate)?'current':''} ${l===human?(pending?'draft':(annotationDone(s)?'human':'')):''}" data-i="${i}" data-label="${l}">${j+1}.${ZH[l]}</button>`).join('');return `<article class="segment ${i===selected?'selected':''}" data-seg="${i}"><div class="row"><b>段 ${i+1}</b><button class="label play" data-i="${i}">▶ ${s.start.toFixed(2)}–${s.end.toFixed(2)}s</button><span>SongFormer：<b>${ZH[s.structure_label_candidate]||s.structure_label_candidate}</b></span><span data-choice="${i}">${choiceText(i)}</span>${!annotationDone(s)&&!pending?'<span class="muted">未修改，提交时采用原标签</span>':''}${data.access.review_mode&&!annotationDone(s)?'<span class="muted">等待初标后才能复核</span>':''}</div><p class="prob muted">${esc(probs(s))}</p><div class="row">${buttons}<button ${disabled} class="label accept" data-i="${i}">A.采用原标签</button><button ${disabled} class="label uncertain" data-i="${i}">U.不确定</button><button ${disabled} class="label boundary" data-i="${i}">B.边界问题</button><select ${disabled} class="confidence" data-i="${i}"><option value="high" ${a.human_confidence==='high'?'selected':''}>高信心</option><option value="medium" ${a.human_confidence==='medium'?'selected':''}>中信心</option><option value="low" ${a.human_confidence==='low'?'selected':''}>低信心</option></select></div><textarea ${disabled} data-note="${i}" placeholder="可选备注">${esc(a.notes||'')}</textarea></article>`}).join('');document.querySelector('#content').innerHTML=`<h2>${esc(track.display_name)}</h2><p class="muted">${esc(track.style)} · ${track.split==='test'?'锁定测试集':'开发集'} · ${data.access.review_mode?'复核模式：已初标段落可修改':'整首歌确认后一次提交'}</p><div class="row"><button class="label play-full">▶ 从头播放整首</button><span class="muted">下方播放器可暂停、拖动和继续播放</span></div><audio id="audio" controls preload="metadata" src="/audio/${encodeURIComponent(track.track_id)}"></audio><div class="submit-bar row"><button class="label submit-track">提交本首歌曲</button><button class="label exclude-track warning">结构太混乱，不参与</button><span class="muted submit-message">选择标签不会自动跳段；未修改段落将保存原标签</span></div>${cards}`;bind()}
function selectSegment(i){selected=i;document.querySelectorAll('.segment').forEach((el,j)=>el.classList.toggle('selected',j===i))}
function paintDraft(i){const card=document.querySelector(`[data-seg="${i}"]`),a=effectiveAnnotation(i),source=targetLabel(track.segments[i].structure_label_candidate);if(!card)return;card.querySelectorAll('[data-label]').forEach(button=>{button.classList.toggle('current',button.dataset.label===source);button.classList.toggle('human',false);button.classList.toggle('draft',button.dataset.label===a.human_label)});card.querySelector(`[data-choice="${i}"]`).innerHTML=choiceText(i);selectSegment(i);document.querySelector('.submit-message').textContent='有未提交修改；确认整首歌后点击“提交本首歌曲”'}
function setDraft(i,patch){const s=track.segments[i];if(!segmentEditable(s))return;const bucket=drafts[track.track_id]||(drafts[track.track_id]={}),next={...effectiveAnnotation(i),...patch};if(next.human_label){next.human_confidence=next.human_confidence||document.querySelector(`.confidence[data-i="${i}"]`)?.value||'high';next.uncertain=false;next.boundary_ok=true}else if(next.uncertain||next.boundary_ok===false){next.human_confidence='';if(next.uncertain)next.boundary_ok=true;if(next.boundary_ok===false)next.uncertain=false}bucket[i]=next;paintDraft(i)}
function bind(){document.querySelectorAll('[data-seg]').forEach(el=>el.onclick=e=>{if(!e.target.closest('button,textarea,select'))selectSegment(+el.dataset.seg)});document.querySelectorAll('.play').forEach(b=>b.onclick=()=>play(+b.dataset.i));document.querySelector('.play-full').onclick=playFull;document.querySelector('.submit-track').onclick=submitTrack;document.querySelector('.exclude-track').onclick=()=>setTrackExcluded(true);document.querySelector('#audio').onpointerdown=cancelSegmentStop;document.querySelectorAll('[data-label]').forEach(b=>b.onclick=()=>setDraft(+b.dataset.i,{human_label:b.dataset.label,uncertain:false,boundary_ok:true}));document.querySelectorAll('.accept').forEach(b=>b.onclick=()=>{const s=track.segments[+b.dataset.i];setDraft(+b.dataset.i,{human_label:targetLabel(s.structure_label_candidate),uncertain:false,boundary_ok:true})});document.querySelectorAll('.uncertain').forEach(b=>b.onclick=()=>setDraft(+b.dataset.i,{human_label:'',human_confidence:'',uncertain:true,boundary_ok:true}));document.querySelectorAll('.boundary').forEach(b=>b.onclick=()=>setDraft(+b.dataset.i,{human_label:'',human_confidence:'',uncertain:false,boundary_ok:false}));document.querySelectorAll('[data-note]').forEach(t=>t.oninput=()=>setDraft(+t.dataset.note,{notes:t.value}));document.querySelectorAll('.confidence').forEach(s=>s.onchange=()=>setDraft(+s.dataset.i,{human_confidence:s.value}))}
function cancelSegmentStop(){clearTimeout(stopTimer);stopTimer=null;const a=document.querySelector('#audio');if(a)a.dataset.segmentMode='0'}
function playFull(){const a=document.querySelector('#audio');cancelSegmentStop();a.currentTime=0;a.play()}
function play(i){selectSegment(i);const s=track.segments[i],a=document.querySelector('#audio');cancelSegmentStop();a.dataset.segmentMode='1';a.currentTime=s.start;a.play();stopTimer=setTimeout(()=>{a.pause();a.dataset.segmentMode='0';stopTimer=null},Math.max(200,(s.end-s.start)*1000))}
async function submitTrack(){if(!track)return;const id=track.track_id,button=document.querySelector('.submit-track'),message=document.querySelector('.submit-message');button.disabled=true;message.textContent='正在校验并提交整首歌曲……';const submissions=track.segments.map((s,i)=>({segment_index:i,expected_revision:s.annotation_revision||0,annotation:effectiveAnnotation(i)})).filter((_,i)=>segmentEditable(track.segments[i]));try{const r=await fetch(sameOrigin+'/api/track-submit',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({access_key:accessKey,track_id:id,submissions})});if(!r.ok)throw new Error((await r.json()).error||'提交失败');delete drafts[id];while(loading)await new Promise(resolve=>setTimeout(resolve,50));await loadData(true,false)}catch(e){message.textContent='提交失败';alert(`${e.message}\n为避免覆盖他人的修改，请刷新后重新确认。`)}finally{button.disabled=false}}
async function setTrackExcluded(excluded){if(!track)return;if(excluded&&!confirm('确认这首歌结构太混乱，不参与标注和训练吗？\n歌曲和历史标注不会物理删除。'))return;const id=track.track_id,revision=track.annotation_exclusion?.revision||0;try{const r=await fetch(sameOrigin+'/api/track-exclusion',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({access_key:accessKey,track_id:id,excluded,expected_revision:revision})});if(!r.ok)throw new Error((await r.json()).error||'操作失败');delete drafts[id];while(loading)await new Promise(resolve=>setTimeout(resolve,50));await loadData(true,false)}catch(e){alert(e.message)}}
async function fetchDataset(){const endpoint=sameOrigin+'/api/dataset?key='+encodeURIComponent(accessKey);let lastError=null;for(let attempt=0;attempt<3;attempt++){try{const r=await fetch(endpoint,{cache:'no-store'});if(!r.ok){const body=await r.json();throw new Error(body.error||'访问链接无效')}return await r.json()}catch(e){lastError=e;if(attempt<2)await new Promise(resolve=>setTimeout(resolve,500*(attempt+1)))}}throw lastError}
async function loadData(preserve=true,background=false){if(loading)return;loading=true;const current=preserve&&track?track.track_id:null,visibleTrack=track;try{const nextData=await fetchDataset(),progressChanged=!data||JSON.stringify(nextData.annotation_progress)!==JSON.stringify(data.annotation_progress);data=nextData;track=background&&visibleTrack?visibleTrack:(current?data.tracks.find(t=>t.track_id===current)||null:null);if(!track&&data.tracks.length)track=data.tracks[0];if(!background||progressChanged)renderTracks();if(!background)renderContent()}catch(e){if(!background||!data){document.querySelector('#content').innerHTML=`<h2 class="warning">无法打开标注数据</h2><p>${esc(e.message)}</p><p class="muted">网络可能暂时不稳定，请刷新重试；页面不会覆盖已经提交的标签。</p>`}else{console.warn('后台同步暂时失败，稍后自动重试',e)}}finally{loading=false}}
document.addEventListener('keydown',e=>{if(!track||['TEXTAREA','SELECT'].includes(e.target.tagName))return;if(e.code==='Space'){e.preventDefault();play(selected);return}const s=track.segments[selected];if(!segmentEditable(s))return;if(e.key.toLowerCase()==='a')setDraft(selected,{human_label:targetLabel(s.structure_label_candidate),uncertain:false,boundary_ok:true});else if(e.key.toLowerCase()==='u')setDraft(selected,{human_label:'',human_confidence:'',uncertain:true,boundary_ok:true});else if(e.key.toLowerCase()==='b')setDraft(selected,{human_label:'',human_confidence:'',uncertain:false,boundary_ok:false});else if(/^[1-8]$/.test(e.key))setDraft(selected,{human_label:LABELS[+e.key-1],uncertain:false,boundary_ok:true})});
document.querySelector('#split').onchange=renderTracks;document.querySelector('#status').onchange=renderTracks;loadData(false);setInterval(()=>{if(!['TEXTAREA','SELECT'].includes(document.activeElement.tagName))loadData(true,true)},15000);
</script></body></html>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--partition-count", type=int, default=2)
    parser.add_argument("--no-open", action="store_true")
    return parser.parse_args()


class Store:
    def __init__(self, path: Path, *, partition_count: int = 2):
        self.path = path.expanduser().resolve()
        self.backup_path = self.path.with_name(
            f"{self.path.stem}.backup{self.path.suffix}"
        )
        self.lock = threading.Lock()
        self.payload = json.loads(self.path.read_text(encoding="utf-8"))
        validate_dataset(self.payload, require_audio=True)
        if ensure_annotation_partition(
            self.payload, partition_count=partition_count
        ):
            self._persist_locked()

    def _persist_locked(self) -> None:
        self.payload["validation_summary"] = validate_dataset(
            self.payload, require_audio=True
        )
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        backup_temporary = self.backup_path.with_suffix(
            self.backup_path.suffix + ".tmp"
        )
        if self.path.is_file():
            shutil.copy2(self.path, backup_temporary)
            backup_temporary.replace(self.backup_path)
        with temporary.open("w", encoding="utf-8") as destination:
            json.dump(self.payload, destination, ensure_ascii=False, indent=2)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        temporary.replace(self.path)

    def public_payload(self, access_key: str) -> dict[str, Any]:
        with self.lock:
            scope, review_mode = resolve_access(self.payload, access_key)
            result = copy.deepcopy(self.payload)
            partition = result.pop("annotation_partition")
            review_state = result.pop("annotation_review", {})
            revisions = review_state.get("segment_revisions") or {}
            assignments = partition["assignments"]
            for track in result.get("tracks") or []:
                track["annotation_partition_id"] = assignments[track["track_id"]]
                for index, segment in enumerate(track.get("segments") or []):
                    segment["annotation_revision"] = int(
                        revisions.get(f"{track['track_id']}:{index}", 0)
                    )
            if scope != "all":
                result["tracks"] = [
                    track
                    for track in result.get("tracks") or []
                    if track["annotation_partition_id"] == scope
                ]
            result["access"] = {
                "scope": scope,
                "review_mode": review_mode,
                "read_only": False,
            }
            result["annotation_progress"] = partition_summary(self.payload)
            return result

    def track(self, track_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in self.payload.get("tracks") or [] if item.get("track_id") == track_id),
            None,
        )

    def update_annotation(
        self,
        access_key: str,
        track_id: str,
        index: int,
        patch: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        with self.lock:
            scope, review_mode = resolve_access(self.payload, access_key)
            assignments = self.payload["annotation_partition"]["assignments"]
            if not review_mode and assignments.get(track_id) != scope:
                raise PermissionError(
                    f"{track_id} belongs to {assignments.get(track_id)}, not {scope}"
                )
            track = self.track(track_id)
            if track is None or not 0 <= index < len(track.get("segments") or []):
                raise KeyError("unknown track or segment")
            if track_is_excluded(track):
                raise PermissionError("excluded tracks cannot receive annotations")
            previous_annotation = dict(
                track["segments"][index].get("annotation") or {}
            )
            if review_mode and not annotation_is_reviewed(previous_annotation):
                raise PermissionError(
                    "review mode can only correct a segment after its initial annotation"
                )
            review_state = self.payload.get("annotation_review") or {}
            revision_key = f"{track_id}:{index}"
            current_revision = int(
                (review_state.get("segment_revisions") or {}).get(revision_key, 0)
            )
            if expected_revision != current_revision:
                raise AnnotationConflictError(
                    f"annotation changed from revision {expected_revision} to "
                    f"{current_revision}; reload before saving"
                )
            validated_patch = validate_annotation_patch(patch)
            annotation = dict(previous_annotation)
            annotation.update(validated_patch)
            normalized = validate_annotation(
                annotation,
                location=f"{track_id}.segments[{index}].annotation",
            )
            if normalized == previous_annotation:
                return {"ok": True, "revision": current_revision, "changed": False}
            previous_payload = copy.deepcopy(self.payload)
            try:
                track["segments"][index]["annotation"] = normalized
                new_revision = current_revision + 1
                review_state = self.payload.setdefault(
                    "annotation_review",
                    {
                        "schema_version": "harbeat_annotation_review_v1",
                        "segment_revisions": {},
                        "audit_log": [],
                    },
                )
                review_state["segment_revisions"][revision_key] = new_revision
                review_state["audit_log"].append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "actor": "review" if review_mode else scope,
                        "track_id": track_id,
                        "segment_index": index,
                        "revision": new_revision,
                        "before": previous_annotation,
                        "after": normalized,
                    }
                )
                self._persist_locked()
            except Exception:
                self.payload = previous_payload
                raise
            return {"ok": True, "revision": new_revision, "changed": True}

    def submit_track_annotations(
        self,
        access_key: str,
        track_id: str,
        submissions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Validate and atomically save one complete song's draft labels."""
        with self.lock:
            scope, review_mode = resolve_access(self.payload, access_key)
            assignments = self.payload["annotation_partition"]["assignments"]
            if not review_mode and assignments.get(track_id) != scope:
                raise PermissionError(
                    f"{track_id} belongs to {assignments.get(track_id)}, not {scope}"
                )
            track = self.track(track_id)
            if track is None:
                raise KeyError("unknown track")
            if track_is_excluded(track):
                raise PermissionError("excluded tracks cannot receive annotations")
            segments = list(track.get("segments") or [])
            indexed: dict[int, dict[str, Any]] = {}
            for raw in submissions:
                if not isinstance(raw, dict):
                    raise TypeError("each submitted annotation must be an object")
                index = int(raw["segment_index"])
                if not 0 <= index < len(segments) or index in indexed:
                    raise ValueError("invalid or duplicated segment_index")
                indexed[index] = raw

            required_indices = (
                {
                    index
                    for index, segment in enumerate(segments)
                    if annotation_is_reviewed(dict(segment.get("annotation") or {}))
                }
                if review_mode
                else set(range(len(segments)))
            )
            if set(indexed) != required_indices:
                raise ValueError(
                    "song submission must include every editable segment exactly once"
                )

            review_state = self.payload.get("annotation_review") or {}
            current_revisions = review_state.get("segment_revisions") or {}
            validated: list[tuple[int, dict[str, Any], dict[str, Any], int]] = []
            for index in sorted(indexed):
                raw = indexed[index]
                previous = dict(segments[index].get("annotation") or {})
                if review_mode and not annotation_is_reviewed(previous):
                    raise PermissionError(
                        "review mode can only correct a segment after its initial annotation"
                    )
                revision_key = f"{track_id}:{index}"
                current_revision = int(current_revisions.get(revision_key, 0))
                expected_revision = int(raw["expected_revision"])
                if expected_revision != current_revision:
                    raise AnnotationConflictError(
                        f"segment {index + 1} changed from revision "
                        f"{expected_revision} to {current_revision}; reload before saving"
                    )
                normalized = validate_annotation(
                    raw.get("annotation"),
                    location=f"{track_id}.segments[{index}].annotation",
                )
                validated.append((index, previous, normalized, current_revision))

            changes = [item for item in validated if item[1] != item[2]]
            if not changes:
                return {"ok": True, "changed_count": 0}
            previous_payload = copy.deepcopy(self.payload)
            try:
                review_state = self.payload.setdefault(
                    "annotation_review",
                    {
                        "schema_version": "harbeat_annotation_review_v1",
                        "segment_revisions": {},
                        "audit_log": [],
                    },
                )
                timestamp = datetime.now(timezone.utc).isoformat()
                for index, previous, normalized, current_revision in changes:
                    segments[index]["annotation"] = normalized
                    revision_key = f"{track_id}:{index}"
                    new_revision = current_revision + 1
                    review_state["segment_revisions"][revision_key] = new_revision
                    review_state["audit_log"].append(
                        {
                            "timestamp": timestamp,
                            "actor": "review" if review_mode else scope,
                            "action": "submit_track",
                            "track_id": track_id,
                            "segment_index": index,
                            "revision": new_revision,
                            "before": previous,
                            "after": normalized,
                        }
                    )
                self._persist_locked()
            except Exception:
                self.payload = previous_payload
                raise
            return {"ok": True, "changed_count": len(changes)}

    def set_track_excluded(
        self,
        access_key: str,
        track_id: str,
        *,
        excluded: bool,
        expected_revision: int,
    ) -> dict[str, Any]:
        """Exclude or restore a song without deleting its source or annotations."""
        with self.lock:
            scope, review_mode = resolve_access(self.payload, access_key)
            assignments = self.payload["annotation_partition"]["assignments"]
            if not review_mode and assignments.get(track_id) != scope:
                raise PermissionError(
                    f"{track_id} belongs to {assignments.get(track_id)}, not {scope}"
                )
            track = self.track(track_id)
            if track is None:
                raise KeyError("unknown track")
            previous = copy.deepcopy(track.get("annotation_exclusion"))
            current_revision = int(
                previous.get("revision", 0) if isinstance(previous, dict) else 0
            )
            if expected_revision != current_revision:
                raise AnnotationConflictError(
                    f"track exclusion changed from revision {expected_revision} "
                    f"to {current_revision}; reload before saving"
                )
            if bool(previous and previous.get("excluded")) == excluded:
                return {
                    "ok": True,
                    "changed": False,
                    "revision": current_revision,
                }
            timestamp = datetime.now(timezone.utc).isoformat()
            normalized = {
                "excluded": excluded,
                "reason": TRACK_EXCLUSION_REASON,
                "actor": "review" if review_mode else scope,
                "updated_at": timestamp,
                "revision": current_revision + 1,
            }
            previous_payload = copy.deepcopy(self.payload)
            try:
                track["annotation_exclusion"] = normalized
                review_state = self.payload.setdefault(
                    "annotation_review",
                    {
                        "schema_version": "harbeat_annotation_review_v1",
                        "segment_revisions": {},
                        "audit_log": [],
                    },
                )
                review_state["audit_log"].append(
                    {
                        "timestamp": timestamp,
                        "actor": "review" if review_mode else scope,
                        "action": "exclude_track" if excluded else "restore_track",
                        "track_id": track_id,
                        "before": previous,
                        "after": normalized,
                    }
                )
                self._persist_locked()
            except Exception:
                self.payload = previous_payload
                raise
            return {
                "ok": True,
                "changed": True,
                "revision": current_revision + 1,
                "excluded": excluded,
            }

    def share_links(self, base_url: str) -> list[tuple[str, str]]:
        partition = self.payload["annotation_partition"]
        links = [
            (
                str(item["id"]),
                f"{base_url}?key={quote(str(item['access_key']))}",
            )
            for item in partition["partitions"]
        ]
        links.append(
            (
                "all-results-review",
                f"{base_url}?key={quote(str(partition['review_access_key']))}",
            )
        )
        return links


def handler_factory(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            use_gzip = "gzip" in self.headers.get("Accept-Encoding", "").lower()
            if use_gzip:
                body = gzip.compress(body, compresslevel=6)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Vary", "Accept-Encoding")
            if use_gzip:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/dataset":
                try:
                    key = parse_qs(parsed.query).get("key", [""])[0]
                    self.send_json(store.public_payload(key))
                except PermissionError as exc:
                    self.send_json({"error": str(exc)}, 403)
                return
            if path.startswith("/audio/"):
                track = store.track(unquote(path[len("/audio/") :]))
                if track is None:
                    self.send_error(404)
                    return
                self.send_audio(Path(track["audio_path"]))
                return
            self.send_error(404)

        def send_audio(self, path: Path) -> None:
            if not path.is_file():
                self.send_error(404)
                return
            size = path.stat().st_size
            start, end = 0, size - 1
            range_header = self.headers.get("Range", "")
            match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            partial = match is not None
            if match:
                if match.group(1):
                    start = min(int(match.group(1)), size - 1)
                if match.group(2):
                    end = min(int(match.group(2)), size - 1)
            length = max(0, end - start + 1)
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "audio/mpeg")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with path.open("rb") as source:
                    source.seek(start)
                    remaining = length
                    while remaining:
                        chunk = source.read(min(1024 * 256, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                # Browsers routinely cancel an old range request when the user
                # seeks or switches segments.  The next request continues from
                # the requested byte, so this is not an annotation error.
                return

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in (
                "/api/annotation",
                "/api/track-submit",
                "/api/track-exclusion",
            ):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                if path == "/api/track-exclusion":
                    excluded = payload.get("excluded")
                    if not isinstance(excluded, bool):
                        raise ValueError("excluded must be boolean")
                    result = store.set_track_excluded(
                        str(payload.get("access_key") or ""),
                        str(payload["track_id"]),
                        excluded=excluded,
                        expected_revision=int(payload["expected_revision"]),
                    )
                    self.send_json(result)
                    return
                if path == "/api/track-submit":
                    submissions = list(payload.get("submissions") or [])
                    result = store.submit_track_annotations(
                        str(payload.get("access_key") or ""),
                        str(payload["track_id"]),
                        submissions,
                    )
                    self.send_json(result)
                    return
                patch = dict(payload.get("patch") or {})
                label = patch.get("human_label")
                if label not in (None, "", *LABELS):
                    raise ValueError("invalid human label")
                if patch.get("human_confidence") not in (None, "", "high", "medium", "low"):
                    raise ValueError("invalid confidence")
                result = store.update_annotation(
                    str(payload.get("access_key") or ""),
                    str(payload["track_id"]),
                    int(payload["segment_index"]),
                    patch,
                    int(payload["expected_revision"]),
                )
            except AnnotationConflictError as exc:
                self.send_json({"error": str(exc)}, 409)
                return
            except (
                DatasetValidationError,
                KeyError,
                PermissionError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                self.send_json({"error": str(exc)}, 400)
                return
            self.send_json(result)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def main() -> int:
    args = parse_args()
    store = Store(args.dataset, partition_count=args.partition_count)
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(store))
    display_host = args.host
    if args.host == "0.0.0.0":
        display_host = ""
        for interface in ("en0", "en1"):
            try:
                result = subprocess.run(
                    ["ipconfig", "getifaddr", interface],
                    capture_output=True,
                    check=False,
                    text=True,
                )
            except OSError:
                break
            candidate = result.stdout.strip()
            if candidate:
                display_host = candidate
                break
        if not display_host:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                    probe.connect(("8.8.8.8", 80))
                    display_host = str(probe.getsockname()[0])
            except OSError:
                display_host = "<本机局域网IP>"
    url = f"http://{display_host}:{args.port}/"
    print("双人标注链接：")
    for name, link in store.share_links(url):
        print(f"  {name}: {link}")
    print(f"标注会实时保存到：{store.path}")
    if not args.no_open:
        first_link = store.share_links(url)[0][1]
        threading.Timer(0.5, lambda: webbrowser.open(first_link)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
