"""Render compact audio and HTML artifacts for manual feature review."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
from typing import Any

import librosa
import numpy as np
import soundfile as sf


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return value[:100] or "review"


def _load_clip(path: str, start: float, end: float, target_sr: int = 22050) -> np.ndarray:
    duration = max(0.1, end - start)
    audio, _ = librosa.load(path, sr=target_sr, mono=True, offset=max(0.0, start), duration=duration)
    expected = int(round(duration * target_sr))
    if len(audio) < expected:
        audio = np.pad(audio, (0, expected - len(audio)))
    audio = np.asarray(audio[:expected], dtype=np.float32)
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 1e-6:
        audio = audio * min(1.0, 0.92 / peak)
    fade = min(len(audio) // 2, int(0.02 * target_sr))
    if fade > 1:
        envelope = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        audio[:fade] *= envelope
        audio[-fade:] *= envelope[::-1]
    return audio


def _focus_path(group_name: str, assets: dict[str, str]) -> str | None:
    if group_name == "low_frequency":
        return assets.get("bass")
    if group_name in {"percussion_timbre", "rhythm_grammar"}:
        return assets.get("drums")
    if group_name == "vocal_delivery":
        return assets.get("vocals")
    return assets.get("other")


def render_review_clips(
    queue: dict[str, Any],
    track_assets: dict[str, dict[str, str]],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    rendered_items = []
    expected_clip_names: set[str] = set()
    for item in queue.get("review_items", []):
        assets = track_assets.get(item["track_id"], {})
        source_path = assets.get("source")
        focus_path = _focus_path(item["group"], assets)
        time_range = item["time_range"]
        start, end = float(time_range["start"]), float(time_range["end"])
        slug = _safe_name(item["review_id"])
        rendered = dict(item)
        rendered["audio"] = {}
        if source_path and Path(source_path).is_file():
            context_name = f"{slug}__context.wav"
            sf.write(clips_dir / context_name, _load_clip(source_path, start, end), 22050, subtype="PCM_16")
            expected_clip_names.add(context_name)
            rendered["audio"]["context"] = f"clips/{context_name}"
        if focus_path and Path(focus_path).is_file():
            focus_name = f"{slug}__focus.wav"
            sf.write(clips_dir / focus_name, _load_clip(focus_path, start, end), 22050, subtype="PCM_16")
            expected_clip_names.add(focus_name)
            rendered["audio"]["focus"] = f"clips/{focus_name}"
        rendered_items.append(rendered)
    for stale_clip in clips_dir.glob("*.wav"):
        if stale_clip.name not in expected_clip_names:
            stale_clip.unlink()
    result = {**queue, "review_items": rendered_items}
    (output_dir / "review_queue.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return result


def render_review_html(queue: dict[str, Any], output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for index, item in enumerate(queue.get("review_items", []), start=1):
        audio = item.get("audio") or {}
        context = (
            f'<label>原曲上下文</label><audio controls preload="metadata" src="{escape(audio["context"])}"></audio>'
            if audio.get("context") else "<em>原曲片段不可用</em>"
        )
        focus = (
            f'<label>分轨重点</label><audio controls preload="metadata" src="{escape(audio["focus"])}"></audio>'
            if audio.get("focus") else "<em>分轨片段不可用</em>"
        )
        options = "".join(
            f'<label class="choice"><input type="radio" name="{escape(item["review_id"])}" '
            f'value="{escape(option)}">{escape(option)}</label>'
            for option in item.get("options", [])
        )
        reasons = "、".join(item.get("reasons", []))
        start, end = item["time_range"]["start"], item["time_range"]["end"]
        cards.append(f"""
        <section class="card" data-review-id="{escape(item['review_id'])}">
          <header><span class="number">{index}</span><div><h2>{escape(item['title'])}</h2>
          <p>{escape(item['group'])} / <strong>{escape(item['feature'])}</strong> · {start:.2f}s–{end:.2f}s</p></div></header>
          <div class="metrics">预测={str(item['predicted']).lower()}　score={item['score']:.3f}　confidence={item['confidence']:.3f}　来源={escape(item['source_type'])}</div>
          <div class="reason">需要复核：{escape(reasons)}</div>
          <div class="players">{context}{focus}</div>
          <div class="choices">{options}</div>
          <textarea placeholder="可选备注"></textarea>
        </section>
        """)
    payload = json.dumps(queue, ensure_ascii=False).replace("</", "<\\/")
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HarBeat 最小人工复核</title>
<style>
:root{{--bg:#f4f6f8;--card:#fff;--text:#17202a;--muted:#667085;--accent:#1565c0}}
body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:28px 18px 80px}}h1{{margin-bottom:4px}}.lead{{color:var(--muted)}}
.toolbar{{position:sticky;top:0;z-index:3;background:rgba(244,246,248,.94);padding:12px 0;display:flex;gap:12px;align-items:center}}
button{{border:0;border-radius:8px;background:var(--accent);color:white;padding:10px 16px;font-weight:650;cursor:pointer}}
.card{{background:var(--card);border-radius:14px;padding:20px;margin:16px 0;box-shadow:0 2px 12px #102a4312}}
header{{display:flex;gap:14px;align-items:flex-start}}h2{{font-size:18px;margin:0}}header p{{margin:3px 0;color:var(--muted)}}
.number{{display:grid;place-items:center;background:#e3f2fd;color:#0d47a1;border-radius:50%;width:34px;height:34px;font-weight:700}}
.metrics,.reason{{margin:10px 0;padding:9px 12px;border-radius:8px;background:#f7f9fc}}.reason{{background:#fff6e5;color:#7a4b00}}
.players{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:14px 0}}audio{{width:100%;display:block;margin-top:4px}}
.choices{{display:flex;flex-wrap:wrap;gap:8px}}.choice{{border:1px solid #d0d5dd;border-radius:999px;padding:7px 11px;cursor:pointer}}
textarea{{width:100%;box-sizing:border-box;margin-top:12px;min-height:54px;border:1px solid #d0d5dd;border-radius:8px;padding:8px}}
@media(max-width:700px){{.players{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>HarBeat 最小人工复核</h1><p class="lead">这里只包含自动系统无法安全裁决、且会影响验收结论的片段。先听原曲，再听分轨，选择最符合的一项。</p>
<div class="toolbar"><button onclick="exportReview()">导出审核结果 JSON</button><span id="progress">0 / {len(cards)}</span></div>
{''.join(cards) if cards else '<p>没有需要人工复核的项目。</p>'}
</main><script>
const queue={payload};
function collect(){{return [...document.querySelectorAll('.card')].map(card=>{{
 const id=card.dataset.reviewId; const selected=card.querySelector('input:checked');
 return {{review_id:id,label:selected?selected.value:null,note:card.querySelector('textarea').value}};
}})}}
function refresh(){{const done=collect().filter(x=>x.label).length;document.getElementById('progress').textContent=`${{done}} / {len(cards)}`;localStorage.setItem('harbeat_review',JSON.stringify(collect()));}}
document.addEventListener('change',refresh);document.addEventListener('input',refresh);
const saved=JSON.parse(localStorage.getItem('harbeat_review')||'[]');saved.forEach(x=>{{const card=document.querySelector(`[data-review-id="${{CSS.escape(x.review_id)}}"]`);if(!card)return;const radio=[...card.querySelectorAll('input')].find(i=>i.value===x.label);if(radio)radio.checked=true;card.querySelector('textarea').value=x.note||'';}});refresh();
function exportReview(){{const result={{version:'pre_style_human_review_v1',created_at:new Date().toISOString(),answers:collect()}};const blob=new Blob([JSON.stringify(result,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='harbeat-human-review.json';a.click();URL.revokeObjectURL(a.href);}}
</script></body></html>"""
    path = output_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
