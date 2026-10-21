"""Data-only strategy from precomputed source evidence. No audio rendering.

The browser validates source bounds again and may choose another non-stale cue.
This planner cannot certify rendered peak/jump statistics, and says so explicitly.
"""
import hashlib
import json
from analysis_platform.execution_profiles import VERSION, compare_profiles, local_pair_evidence
from .prepare import validated_plan
from .policy import choose_method


def strategy(a,b,window_id,start,profile_a,profile_b):
    for track,profile in [(a,profile_a),(b,profile_b)]:
        provenance=track.get('provenance') or {}
        expected={'schema':VERSION,'trackId':track['id'],'runId':provenance.get('runId'),
                  'sourceSha256':provenance.get('masterSha256'),'reportSha256':provenance.get('reportSha256')}
        if any(profile.get(k)!=v for k,v in expected.items()):
            raise ValueError('execution profile source/report binding mismatch')
    plan=validated_plan(a,b,window_id,start)
    metrics=compare_profiles(profile_a,profile_b,plan['start'],plan['bStart'],plan['duration'],plan['rate'])
    decision=choose_method(metrics)
    # Keep the old waveform-based vocal guard authoritative. Coarse summary frames
    # are not a replacement for its 50 ms tail / B-vocal quiet checks.
    result={'schema':'harbeat.execution-strategy.v1','version':'source-profiles-v1',
            'sourceProof':{'a':{k:profile_a[k] for k in ['trackId','sourceSha256','reportSha256','runId']},
                           'b':{k:profile_b[k] for k in ['trackId','sourceSha256','reportSha256','runId']}},
            'plan':plan,'metrics':metrics,'decision':decision,
            'localPairEvidence':local_pair_evidence(profile_a,profile_b,plan['start'],plan['bStart'],plan['duration'],plan['rate']),
            'execution':{'basis':'master plus signed source-stem corrections','commonGain':.6,
                         'pitchPreservingRequired':abs(plan['rate']-1)>1e-10,
                         'afterTakeover':'native-rate','sampleClock':'device audio clock',
                         'peakProtectionRequired':True},
            'renderedOutputStats':None,
            'limitations':['Profile rules are provisional and not calibrated listening probabilities.',
                           'No pair audio was rendered; output peaks and discontinuities must be checked by the device.',
                           'Vocal handover requires the existing fine-grained waveform guard; profile-only planning disables it.']}
    result['planId']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return result
