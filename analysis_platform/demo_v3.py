"""Replay the colleague's frozen decisions with their unmodified render functions.

Planner dependencies were not delivered. This deliberately does not invent them,
rerank the songs, or substitute V2 DSP. Attribution and hashes remain in the plan.
"""
import ast
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

RENDERER_SHA256='8cf342e72a688ccde658cf402866f63f3cc7fe8eafd7fc70857cc32d6185069a'
PLAN_SHA256='686ab054ceac986d508c85271aef2fb7934c95bfa168fe9c1423793ee1e0a14b'
FUNCTIONS={'_run','_ffmpeg','_ffprobe','probe_audio','audio_duration_seconds','_atempo_chain','_part_chain','render_segment','render_crossfaded_mix','render_snippets'}
CONSTANTS={'SAMPLE_RATE','RENDER_GAIN','FINAL_FADE_SECONDS'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_renderer(path,commands=None):
    """Only load hash-pinned rendering definitions, skipping absent planner imports."""
    path=Path(path)
    if sha256(path)!=RENDERER_SHA256:raise ValueError('colleague renderer checksum mismatch')
    tree=ast.parse(path.read_text())
    selected=[n for n in tree.body if (isinstance(n,ast.ImportFrom) and n.module=='__future__') or (isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS) or
              (isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in CONSTANTS)]
    found={n.name for n in selected if isinstance(n,ast.FunctionDef)}
    if found!=FUNCTIONS:raise ValueError('incomplete rendering definitions')
    namespace={'Path':Path,'json':json,'subprocess':subprocess,'shutil':shutil}
    # Function bodies and literal constants are unchanged from the delivered file.
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),namespace)
    if commands is not None:
        original=namespace['_run']
        def recorded(cmd):
            commands.append(list(cmd))
            original(cmd)
        namespace['_run']=recorded
    return namespace


def compile_plan(peer,sources):
    tracks=peer['tracks'];transitions=peer['transitions']
    if len(tracks)!=6 or len(transitions)!=5:raise ValueError('expected delivered six-song plan')
    if peer['policy']['render_gain']!=.76:raise ValueError('unexpected colleague gain')
    mapped=[];compiled=[]
    for i,row in enumerate(tracks):
        matches=[s for s in sources if s['title']==row['title']]
        if len(matches)!=1:raise ValueError('missing or ambiguous source: '+row['title'])
        source=matches[0]
        if row['track_id']!='track-'+source['audio_sha256'][:20]:raise ValueError('source identity mismatch')
        if sha256(source['path'])!=source['audio_sha256']:raise ValueError('source checksum mismatch')
        if i:
            edge=transitions[i-1];rate=row['incoming_rate']
            if not math.isclose(rate,tracks[i-1]['bpm']/row['bpm'],abs_tol=1e-10):raise ValueError('inconsistent incoming rate')
            if row['incoming_mid_duck']!=edge['both_vocal_detected']:raise ValueError('inconsistent vocal decision')
            if row['render_entry_ms']!=edge['b_entry_ms']:raise ValueError('inconsistent incoming cue')
            overlap=edge['incoming_source_overlap_ms']/1000/rate
            compiled.append({**edge,'delivered_rounded_overlap_seconds':edge['overlap_seconds'],
                             'overlap_seconds':overlap,'full_precision_rate':rate,
                             'restore_half_bar_seconds':120/tracks[i-1]['bpm']})
        mapped.append({**row,'source_path':source['path'],'audio_sha256':source['audio_sha256']})
    for i,row in enumerate(mapped):
        incoming=compiled[i-1] if i else None;outgoing=compiled[i] if i<5 else None
        if outgoing and row['render_exit_ms']!=outgoing['a_out_point_first_chorus_end_ms']:raise ValueError('inconsistent exit cue')
        row['render']={'entry_ms':row['render_entry_ms'],'exit_ms':row['render_exit_ms'],
                       'incoming_source_overlap_ms':incoming['incoming_source_overlap_ms'] if incoming else 0,
                       'incoming_rate':row['incoming_rate'],'outgoing_overlap_seconds':outgoing['overlap_seconds'] if outgoing else 0.,
                       'mid_duck':row['incoming_mid_duck'],'restore_half_bar_seconds':incoming['restore_half_bar_seconds'] if incoming else 0.,
                       'final_track':i==5}
    return {'schema':'harbeat.colleague_plan_replay.v3','version':'3.0-reproduction','tracks':mapped,'transitions':compiled,
            'policy':peer['policy'],'ranking_recomputed':False,'human_confirmed':False,
            'renderer_sha256':RENDERER_SHA256,'source_plan_sha256':PLAN_SHA256,
            'attribution':'Original rendering functions and selected decisions: colleague algorithm_demo_transition_logic_1_0.py / mix_plan.json. HarBeat adapter adds source binding, execution records and review page only.',
            'limitations':['Original planner dependencies and raw scoring snapshots absent: replaying delivered decisions, not rerunning the route search.',
                          'Original section boundaries and degraded/needs_review flags retained without acoustic correction.',
                          'Different FFmpeg/MP3 encoder environments may produce different samples; decoded comparison is reported separately.']}
