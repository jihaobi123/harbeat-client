"""Original colleague planning functions with an explicit raw-bar adapter.

Unlike V3's reference replay, new songs need cue selection. The colleague's
phrase_mix helper was absent. Only that hook is replaced with nearest recorded
bar lookup; it never extrapolates a V2 grid. Other helpers come from the earlier
user-supplied HarBeat V4 package, and their exact source hashes are exposed.
"""
import ast,dataclasses,itertools,math,sys,types
from pathlib import Path
from .demo_v3 import sha256,RENDERER_SHA256
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'mixing/vendor/colleague_demo_v1/algorithm_demo_transition_logic_1_0.py'
PACKAGE=ROOT/'mixing/vendor/harbeat_v4'
NAMES={'_label','_sections','_bar_count','_snap_ms','first_intro_window','first_chorus_block','_merge_intervals','vocal_overlap_ms','vocal_ratio','vocal_present','transition_for_pair','order_tracks'}
CONSTANTS={'VOCAL_PAD_MS','VOCAL_PRESENT_MIN_MS','VOCAL_PRESENT_MIN_RATIO','CASE_3_A_CHORUS_BARS','CHORUS_LABELS','INTRO_LABELS'}


def load_policy(grids):
    if sha256(SOURCE)!=RENDERER_SHA256:raise ValueError('colleague source checksum mismatch')
    if str(PACKAGE) not in sys.path:sys.path.insert(0,str(PACKAGE))
    from harbeat.cue_points import bar_duration_seconds
    from harbeat.drums import drum_overlap_score
    from harbeat.key_compatibility import harmonic_compatibility_score
    from harbeat.preprocess_reader import manifest_to_track_profile
    def snap_to_bar(track,time_seconds,mode='nearest'):
        bars=grids.get(track.id,[])
        if not bars or any(not math.isfinite(v) or v<0 for v in bars):raise ValueError('missing or invalid raw bar grid')
        if mode=='floor':eligible=[x for x in bars if x<=time_seconds]
        elif mode=='ceil':eligible=[x for x in bars if x>=time_seconds]
        elif mode=='nearest':eligible=bars
        else:raise ValueError('invalid snap mode')
        if not eligible:raise ValueError('no recorded bar in requested direction')
        return min(eligible,key=lambda x:(abs(x-time_seconds),x))
    module=types.ModuleType('_harbeat_colleague_planner_replay');sys.modules[module.__name__]=module
    ns=module.__dict__;ns.update(dataclass=dataclasses.dataclass,permutations=itertools.permutations,
        bar_duration_seconds=bar_duration_seconds,drum_overlap_score=drum_overlap_score,
        harmonic_compatibility_score=harmonic_compatibility_score,snap_to_bar=snap_to_bar)
    tree=ast.parse(SOURCE.read_text())
    nodes=[n for n in tree.body if (isinstance(n,ast.ImportFrom) and n.module=='__future__') or
           (isinstance(n,ast.FunctionDef) and n.name in NAMES) or
           (isinstance(n,ast.ClassDef) and n.name in ('SegmentWindow','DemoTransition')) or
           (isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in CONSTANTS)]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),ns)
    ns['manifest_to_track_profile']=manifest_to_track_profile
    ns['provenance']={'colleague_source_sha256':RENDERER_SHA256,'snap_adapter':'nearest/floor/ceil actual published bars_ms, no extrapolation or V2 fit',
        'helpers_from':'user-supplied harbeat_mixing_algorithm_vocal_v4_20260913',
        'helper_hashes':{name:sha256(PACKAGE/'harbeat'/name) for name in ['cue_points.py','drums.py','key_compatibility.py','preprocess_reader.py','models.py']},
        'limitation':'The original colleague phrase_mix helper/version was not included; this explicit raw-grid adapter and earlier supplied helpers are not claimed byte-identical to the missing planner environment. Rendering functions remain the verified V3 functions.'}
    return ns
