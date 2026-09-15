"""v4 processing + original v4 ordering, with interactive future-cue scheduling."""
import json
from realtime import BASE, Controller, rpc, exit_candidates
from prepare_tempo import source_time, playback_time


class TempoController(Controller):
    def __init__(self, catalog, v4, call=rpc, index=None):
        super().__init__(catalog, v4, call)
        self.tempo = index if index is not None else json.loads((BASE/'reports/tempo_assets_v1.json').read_text())
        if self.tempo['manifests'] != {t:r['manifest_sha256'] for t,r in catalog.items()}:
            raise ValueError('tempo_asset_manifest_mismatch')
        self.ids = self.tempo['order'][:]
        self.by_sid = {sid:a['track_id'] for sid,a in self.tempo['assets'].items()}
        for tid,row in catalog.items():
            row['song_id'] = self.tempo['starts'][tid]
        self._start_first = self.ids[0]

    def prepare(self, ids):
        # Warm the default whole queue before starting. Explicit next targets can
        # prepare one different immutable variant while the active deck continues.
        order = [self._start_first] + [t for t in self.ids if t != self._start_first]
        sids = [self.tempo['starts'][order[0]]] + [
            self.tempo['pairs'][a+'|'+b]['final_song_id' if i==len(order)-2 else 'song_id']
            for i,(a,b) in enumerate(zip(order,order[1:]))]
        self.prepare_sids(sids)

    def prepare_sids(self, sids):
        r = self.call(dict(cmd='prefetch',song_ids=sids,wait=True,load_stems=False))
        if not r.get('all_ready'):
            raise ValueError('tempo_assets_not_ready: '+str(r.get('failed')))

    def command(self, msg):
        if msg.get('cmd')=='start' and not self.active:
            self._start_first=msg.get('track_id',self.ids[0])
        return super().command(msg)

    def state(self):
        result = super().state()
        s = result['engine']
        asset = self.tempo['assets'].get(str(s.get('current_song_id')))
        result.update(mode='live_dual_deck_vocal_v4_tempo',
            tempo_processing='ffmpeg_atempo_prepared_per_track',restore_mode='v4_head_then_original_tail',
            source_position_sec=source_time(asset,s['position_sec']) if asset else None,
            active_asset=asset,control_schema='harbeat.control.v1')
        return result

    def schedule(self, request_id, target=None, auto=False):
        s = self.call({'cmd':'state'})
        if s['in_transition']:
            raise ValueError('transition_busy')
        sid = str(s['current_song_id'])
        tid = self.by_sid.get(sid)
        if not self.active or tid is None:
            raise ValueError('session_not_started')
        if self.pending and not self.pending['auto']:
            return dict(ok=True,status='already_scheduled',pending=self.pending)
        candidates = [t for t in self.ids if t not in self.visited and t != tid]
        if not candidates:
            raise ValueError('queue_exhausted')
        nxt = target if target is not None else candidates[0]
        if nxt not in candidates:
            raise ValueError('target_unavailable_or_already_played')
        pair = dict(self.tempo['pairs'][tid+'|'+nxt])
        if len(candidates)==1:
            pair['song_id']=pair['final_song_id']
        incoming = self.tempo['assets'][pair['song_id']]
        self.prepare_sids([pair['song_id']])
        s = self.call({'cmd':'state'})
        if str(s['current_song_id']) != sid or s['in_transition']:
            raise ValueError('playback_changed_during_preparation')
        asset = self.tempo['assets'][sid]
        position = source_time(asset,s['position_sec'])
        row = self.catalog[tid]
        fade = pair['fade_sec']
        points = exit_candidates(row['manifest'],row['bars'],position,fade=fade)
        # Keep the current entrance speed phase intact, and leave real output
        # time for the whole fade even when a non-unit rate shortened the song.
        points = [(p,r) for p,r in points if p>=asset['head_end_sec'] and
                  playback_time(asset,p)>=s['position_sec']+3 and
                  playback_time(asset,p)+fade+0.25<=asset['frames']/44100]
        if not points:
            raise ValueError('no_future_candidate_with_enough_audio')
        if auto:
            preferred = self.v4.choose_exit_cue(row['manifest'],int(asset['entry_sec']*1000),
                vocal_intervals=row['intervals'],outgoing_overlap_ms=int(fade*1000)).time_ms/1000
            cue,reason=min(points,key=lambda p:abs(p[0]-preferred))
        else:
            cue,reason=points[0]
        native_cue=playback_time(asset,cue)
        pending=dict(request_id=request_id,from_track_id=tid,to_track_id=nxt,
            from_at_sec=cue,to_at_sec=incoming['entry_sec'],fade_sec=fade,
            candidate_reason=reason,requested_at_position=position,auto=auto,status='scheduled',
            from_playback_at_sec=native_cue,to_playback_at_sec=0.0,
            entry_rate=pair['rate'],method=pair['method'],tempo_relation=pair['tempo_relation'],
            restore_mode=pair['restore_mode'],head_output_seconds=incoming['head_output_frames']/44100,
            incoming_asset_sha256=incoming['sha256'],incoming_song_id=pair['song_id'])
        plan=dict(plan_id='rtv2-'+request_id,tracks=[sid,pair['song_id']],transitions=[
            dict(from_song_id=sid,to_song_id=pair['song_id'],from_at_sec=native_cue,
                 to_at_sec=0.0,fade_sec=fade,fade_curve='linear',style='smooth',transition_id=request_id)])
        self.call({'cmd':'load_plan','mix_plan':plan})
        self.pending=pending
        self.event('scheduled',**pending)
        return dict(ok=True,status='scheduled',pending=dict(pending))
