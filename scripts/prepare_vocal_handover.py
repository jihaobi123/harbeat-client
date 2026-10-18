"""Package the individually frozen vocal-handover cases and retain rejections."""
import argparse
import copy
import hashlib
import json
import pathlib
import shutil
from scripts.report_vocal_endpoints import verified_analysis
from scripts.prepare_vocal_endpoint_pack import validate_handover_sources


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def choose_candidates(selection, analysis, limit=2):
    chosen, audit = [], []
    for original in selection['cases']:
        c = copy.deepcopy(original)
        a = next((x for x in analysis['contexts'] if x['id'] == c['plan']['from']), None)
        b = next((x for x in analysis['contexts'] if x['id'] == c['plan']['to']), None)
        row = dict(id=c['id'], aTitle=c['aTitle'], bTitle=c['bTitle'], plan=c['plan'], eligible=False, accepted=False)
        if a is None or b is None:
            row.update(reasonCode='missing-validated-context', reason='来源音频或观察范围不完整，本轮跳过')
            audit.append(row)
            continue
        c['sourceVerification'] = {'a': a['source'], 'b': b['source']}
        try:
            validate_handover_sources(c, a, b)
            row['eligible'] = True
            row['accepted'] = len(chosen) < limit
            row['reason'] = '尾音、空隙和来源核验通过，待试听' if row['accepted'] else '核验通过；按预定顺序，本轮先听前两组新来源'
            row['reasonCode'] = 'selected-for-listening' if row['accepted'] else 'passing-outside-round-limit'
            if row['accepted']:
                chosen.append(c)
        except ValueError as e:
            row['reasonCode'] = str(e)
            if 'incoming' in str(e):
                row['reason'] = '下一首的固定进入区间有人声活动或观察不足'
            elif not a['selected']:
                row['reason'] = '固定退出位置没有通过尾音与后方空隙检查'
            else:
                row['reason'] = '来源、接点或观察范围核验未通过'
        audit.append(row)
    return chosen, audit


def validate_rendered_selection(expected, rendered):
    if len(expected) != len(rendered):
        raise ValueError('rendered case count differs from frozen selection')
    fields = ['id','plan','planSha256','relay','timing','pre','post','baselineBass']
    if any(a.get(k) != b.get(k) for a, b in zip(expected, rendered) for k in fields):
        raise ValueError('rendered case differs from frozen plan or treatment inputs')


def audit_selection(root):
    selection = json.loads((root/'selection.json').read_text())
    analysis = verified_analysis(root)
    chosen, audit = choose_candidates(selection, analysis)
    ids = {c['plan'][side] for c in chosen for side in ['from', 'to']}
    render = dict(selection, cases=chosen, tracks=[t for t in selection['tracks'] if t['id'] in ids])
    dest = root/'accepted'
    dest.mkdir(exist_ok=True)
    (dest/'selection.json').write_text(json.dumps(render, ensure_ascii=False, indent=2)+'\n')
    (root/'candidate-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(audit, ensure_ascii=False, default=str))


def bound_anchor(anchor_root, reference):
    source = anchor_root/'pack.json'
    if sha(source) != reference['sourcePackSha256']:
        raise ValueError('historical anchor pack changed')
    anchor = json.loads(source.read_text())['cases'][0]
    if anchor != reference['case']:
        raise ValueError('historical anchor differs from frozen reference')
    return anchor


def prepare(root, anchor_root, web):
    analysis = verified_analysis(root)
    selection = json.loads((root/'selection.json').read_text())
    chosen, audit = choose_candidates(selection, analysis)
    rendered = json.loads((root/'accepted/audio/vocal-bed-data.json').read_text())
    validate_rendered_selection(chosen, rendered['cases'])
    # Rebuild anchor evidence rather than trusting a stale historical pack.
    anchor_analysis = verified_analysis(anchor_root/'probe-talgo')
    reference = json.loads((root/'anchor-reference.json').read_text())
    anchor = bound_anchor(anchor_root, reference)
    inputs = [(anchor, anchor_analysis, anchor_root/'probe-talgo/audio', anchor_root/'probe-talgo')]
    inputs += [(c, analysis, root/'accepted/audio', root) for c in rendered['cases']]
    out = web/'vocal-handover-audio'
    out.mkdir(exist_ok=True)
    cases = []
    for index, (original, report, audio, context_root) in enumerate(inputs):
        c = copy.deepcopy(original)
        a = next(x for x in report['contexts'] if x['id'] == c['plan']['from'])
        b = next(x for x in report['contexts'] if x['id'] == c['plan']['to'])
        validate_handover_sources(c, a, b)
        e, p = a['selected'], c['plan']
        c['frozenCandidateId'] = c['id']
        c['id'] = 'vocal-handover-'+str(index+1).zfill(2)
        c['anchor'] = index == 0
        c['endpoint'] = {k: round(e[k]-p['start'], 9) for k in ['tailEnd','nextOnset','fadeStart','fadeEnd']}
        if len(c['assets']) != 9 or any('Echo' in key for key in c['assets']):
            raise ValueError('only the nine original source layers are permitted')
        for key, asset in c['assets'].items():
            src = audio/pathlib.Path(asset['url']).name
            if sha(src) != asset['sha256']:
                raise ValueError('rendered asset changed')
            target = out/(c['id']+'-'+key+src.suffix)
            shutil.copy2(src, target)
            asset['url'] = '/vocal-handover-audio/'+target.name
        context = context_root/(a['id']+'.wav')
        if sha(context) != a['contextSha256']:
            raise ValueError('review context changed')
        target = out/(c['id']+'-review.wav')
        shutil.copy2(context, target)
        c['evidence'] = dict(selected=e, contextStart=a['start'], contextUrl='/vocal-handover-audio/'+target.name, contextSha256=a['contextSha256'], analysis=a, control=b)
        cases.append(c)
    audit.insert(0, dict(aTitle=anchor['aTitle'], bTitle=anchor['bTitle'], accepted=True, eligible=True, reason='复用已核验片段，本轮改用原方案作为对照', reasonCode='anchor-rebased'))
    pack = dict(schema='harbeat.vocal-handover-pack.v1', cases=cases, audit=dict(candidates=audit, selectionRule=selection['audit']['rule'], frozenAt=selection['frozenAt'], selectionSha256=sha(root/'selection.json'), analysisSha256=sha(root/'analysis.json'), anchorReferenceSha256=sha(root/'anchor-reference.json')),
                rendering='Shared nine phase-aligned master/bass/vocal clips; natural original reference versus protected vocal handover; no effects.',
                limitation='Activity endpoints are provisional and do not certify complete lyrics. New pairs are exploratory with original-policy cues frozen before model observation. No per-arm normalization, no production change.')
    pack['selectionSha256'] = hashlib.sha256(json.dumps(pack, sort_keys=True).encode()).hexdigest()
    text = json.dumps(pack, ensure_ascii=False, indent=2)+'\n'
    (root/'pack.json').write_text(text)
    (web/'vocal-handover-data.json').write_text(text)
    print('pack', [(c['aTitle'],c['bTitle']) for c in cases])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['audit','pack'])
    parser.add_argument('root', type=pathlib.Path)
    parser.add_argument('--anchor-root', type=pathlib.Path)
    parser.add_argument('--web', type=pathlib.Path)
    args = parser.parse_args()
    if args.mode == 'audit':
        audit_selection(args.root)
    else:
        prepare(args.root, args.anchor_root, args.web)
