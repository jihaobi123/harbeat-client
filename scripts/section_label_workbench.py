#!/usr/bin/env python3
"""Local, dependency-free browser workbench for section-label review."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


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

HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>HarBeat 段落标签标注</title>
<style>
*{box-sizing:border-box}body{margin:0;font:14px system-ui;background:#0b1020;color:#e8edf7}
header{position:sticky;top:0;z-index:3;padding:12px 18px;background:#11182b;border-bottom:1px solid #27314c;display:flex;gap:18px;align-items:center}
main{display:grid;grid-template-columns:310px 1fr;min-height:calc(100vh - 65px)}
aside{border-right:1px solid #27314c;padding:12px;overflow:auto;height:calc(100vh - 65px)}
#content{padding:18px;max-width:1200px}.track{padding:9px;border-radius:8px;margin:4px 0;cursor:pointer}.track:hover,.track.active{background:#202b47}
.done{color:#65d69e}.pending{color:#f3bd55}.segment{border:1px solid #2a3655;border-radius:10px;padding:12px;margin:10px 0;background:#121a2e}.segment.selected{border-color:#66a2ff}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.label{padding:7px 10px;border:1px solid #3b4b72;border-radius:8px;background:#18213a;color:#e8edf7;cursor:pointer}.label:hover{border-color:#66a2ff}.label.current{background:#255a9b}.label.human{background:#246a4a}
button{cursor:pointer}audio{width:min(760px,100%)}.muted{color:#94a2bd}.prob{font-family:ui-monospace,monospace}.warning{color:#ff9f9f}
textarea{width:100%;min-height:44px;background:#0c1325;color:#e8edf7;border:1px solid #344260;border-radius:7px;padding:7px}
select{background:#10182b;color:#e8edf7;border:1px solid #344260;padding:6px;border-radius:6px}
@media(max-width:800px){main{display:block}aside{height:240px;border-right:0;border-bottom:1px solid #27314c}}
</style></head><body>
<header><b>HarBeat 段落标签标注</b><span id="progress"></span><span class="muted">A=接受　1–8=改标签　U=不确定　B=边界问题　空格=播放</span></header>
<main><aside><div class="row"><select id="split"><option value="all">全部</option><option value="development">65首开发集</option><option value="test">8首测试集</option></select><select id="status"><option value="all">全部状态</option><option value="pending">未完成</option><option value="done">已完成</option></select></div><div id="tracks"></div></aside>
<section id="content"><p>请选择歌曲。</p></section></main>
<script>
const LABELS=['intro','verse','chorus','bridge','instrumental','outro','silence','pre-chorus'];
const ZH={intro:'前奏',verse:'主歌',chorus:'副歌',bridge:'桥段',instrumental:'器乐段',outro:'尾奏',silence:'静音','pre-chorus':'预副歌'};
let data,track,selected=0,stopTimer=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function annotationDone(s){const a=s.annotation||{};return !!a.human_label||a.uncertain||a.boundary_ok===false}
function trackDone(t){return t.segments.length>0&&t.segments.every(annotationDone)}
function refreshProgress(){const all=data.tracks.flatMap(t=>t.segments),n=all.filter(annotationDone).length;document.querySelector('#progress').textContent=`${n}/${all.length} 段已确认`}
function renderTracks(){const split=document.querySelector('#split').value,status=document.querySelector('#status').value;let html='';for(const t of data.tracks){const done=trackDone(t);if(split!=='all'&&t.split!==split)continue;if(status==='done'&&!done)continue;if(status==='pending'&&done)continue;html+=`<div class="track ${track===t?'active':''}" data-id="${esc(t.track_id)}"><div>${esc(t.display_name)}</div><small class="${done?'done':'pending'}">${esc(t.style)} · ${t.segments.length}段 · ${done?'已完成':'待确认'}</small></div>`}document.querySelector('#tracks').innerHTML=html;document.querySelectorAll('.track').forEach(el=>el.onclick=()=>selectTrack(el.dataset.id));refreshProgress()}
function selectTrack(id){track=data.tracks.find(t=>t.track_id===id);selected=0;renderTracks();renderContent()}
function probs(s){const p=s.structure_label_probabilities||{};return Object.entries(p).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`${ZH[k]||k} ${(100*v).toFixed(1)}%`).join('　')}
function renderContent(){if(!track)return;const cards=track.segments.map((s,i)=>{const a=s.annotation||{},human=a.human_label||'';const buttons=LABELS.map((l,j)=>`<button class="label ${l===s.structure_label_candidate?'current':''} ${l===human?'human':''}" data-i="${i}" data-label="${l}">${j+1}.${ZH[l]}</button>`).join('');return `<article class="segment ${i===selected?'selected':''}" data-seg="${i}"><div class="row"><b>段 ${i+1}</b><button class="label play" data-i="${i}">▶ ${s.start.toFixed(2)}–${s.end.toFixed(2)}s</button><span>SongFormer：<b>${ZH[s.structure_label_candidate]||s.structure_label_candidate}</b></span>${a.boundary_ok===false?'<span class="warning">边界有问题</span>':''}${a.uncertain?'<span class="warning">不确定</span>':''}</div><p class="prob muted">${esc(probs(s))}</p><div class="row">${buttons}<button class="label accept" data-i="${i}">A.接受原标签</button><button class="label uncertain" data-i="${i}">U.不确定</button><button class="label boundary" data-i="${i}">B.边界问题</button><select class="confidence" data-i="${i}"><option value="high" ${a.human_confidence==='high'?'selected':''}>高信心</option><option value="medium" ${a.human_confidence==='medium'?'selected':''}>中信心</option><option value="low" ${a.human_confidence==='low'?'selected':''}>低信心</option></select></div><textarea data-note="${i}" placeholder="可选备注">${esc(a.notes||'')}</textarea></article>`}).join('');document.querySelector('#content').innerHTML=`<h2>${esc(track.display_name)}</h2><p class="muted">${esc(track.style)} · ${track.split==='test'?'锁定测试集':'开发集'} · ${track.songformer_status}</p><audio id="audio" controls preload="metadata" src="/audio/${encodeURIComponent(track.track_id)}"></audio>${cards}`;bind();scrollSelected(false)}
function bind(){document.querySelectorAll('[data-seg]').forEach(el=>el.onclick=e=>{if(!e.target.closest('button,textarea,select')){selected=+el.dataset.seg;renderContent()}});document.querySelectorAll('.play').forEach(b=>b.onclick=()=>play(+b.dataset.i));document.querySelectorAll('[data-label]').forEach(b=>b.onclick=()=>save(+b.dataset.i,{human_label:b.dataset.label,uncertain:false,boundary_ok:true}));document.querySelectorAll('.accept').forEach(b=>b.onclick=()=>{const s=track.segments[+b.dataset.i];save(+b.dataset.i,{human_label:s.structure_label_candidate,uncertain:false,boundary_ok:true})});document.querySelectorAll('.uncertain').forEach(b=>b.onclick=()=>save(+b.dataset.i,{human_label:'',uncertain:true}));document.querySelectorAll('.boundary').forEach(b=>b.onclick=()=>save(+b.dataset.i,{human_label:'',boundary_ok:false}));document.querySelectorAll('[data-note]').forEach(t=>t.onchange=()=>save(+t.dataset.note,{notes:t.value},false));document.querySelectorAll('.confidence').forEach(s=>s.onchange=()=>save(+s.dataset.i,{human_confidence:s.value},false))}
function play(i){selected=i;const s=track.segments[i],a=document.querySelector('#audio');a.currentTime=s.start;a.play();clearTimeout(stopTimer);stopTimer=setTimeout(()=>a.pause(),Math.max(200,(s.end-s.start)*1000));document.querySelectorAll('.segment').forEach((e,j)=>e.classList.toggle('selected',j===i));scrollSelected(false)}
async function save(i,patch,advance=true){selected=i;const s=track.segments[i],confidence=document.querySelector(`.confidence[data-i="${i}"]`)?.value||'high';patch.human_confidence=patch.human_confidence||confidence;const r=await fetch('/api/annotation',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({track_id:track.track_id,segment_index:i,patch})});if(!r.ok){alert(await r.text());return}s.annotation={...(s.annotation||{}),...patch};if(advance&&i+1<track.segments.length)selected=i+1;renderTracks();renderContent()}
function scrollSelected(smooth=true){document.querySelector('.segment.selected')?.scrollIntoView({block:'center',behavior:smooth?'smooth':'auto'})}
document.addEventListener('keydown',e=>{if(!track||['TEXTAREA','SELECT'].includes(e.target.tagName))return;if(e.code==='Space'){e.preventDefault();play(selected)}else if(e.key.toLowerCase()==='a'){const s=track.segments[selected];save(selected,{human_label:s.structure_label_candidate,uncertain:false,boundary_ok:true})}else if(e.key.toLowerCase()==='u')save(selected,{human_label:'',uncertain:true});else if(e.key.toLowerCase()==='b')save(selected,{human_label:'',boundary_ok:false});else if(/^[1-8]$/.test(e.key))save(selected,{human_label:LABELS[+e.key-1],uncertain:false,boundary_ok:true})});
document.querySelector('#split').onchange=renderTracks;document.querySelector('#status').onchange=renderTracks;
fetch('/api/dataset').then(r=>r.json()).then(d=>{data=d;renderTracks();if(d.tracks.length)selectTrack(d.tracks[0].track_id)});
</script></body></html>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    return parser.parse_args()


class Store:
    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
        self.lock = threading.Lock()
        self.payload = json.loads(self.path.read_text(encoding="utf-8"))

    def public_payload(self) -> dict[str, Any]:
        return self.payload

    def track(self, track_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in self.payload.get("tracks") or [] if item.get("track_id") == track_id),
            None,
        )

    def update_annotation(self, track_id: str, index: int, patch: dict[str, Any]) -> None:
        with self.lock:
            track = self.track(track_id)
            if track is None or not 0 <= index < len(track.get("segments") or []):
                raise KeyError("unknown track or segment")
            annotation = track["segments"][index].setdefault("annotation", {})
            annotation.update(patch)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(self.payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)


def handler_factory(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/dataset":
                self.send_json(store.public_payload())
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
            if urlparse(self.path).path != "/api/annotation":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                patch = dict(payload.get("patch") or {})
                label = patch.get("human_label")
                if label not in (None, "", *LABELS):
                    raise ValueError("invalid human label")
                if patch.get("human_confidence") not in (None, "", "high", "medium", "low"):
                    raise ValueError("invalid confidence")
                store.update_annotation(
                    str(payload["track_id"]), int(payload["segment_index"]), patch
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, 400)
                return
            self.send_json({"ok": True})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def main() -> int:
    args = parse_args()
    store = Store(args.dataset)
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(store))
    url = f"http://{args.host}:{args.port}/"
    print(f"标注页面：{url}")
    print(f"标注会实时保存到：{store.path}")
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
