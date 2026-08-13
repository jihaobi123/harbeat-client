import '../lib/mobile_dj_control.dart';

void expect(bool value, String message) {
  if (!value) throw StateError(message);
}

void main() {
  final plan = <String, dynamic>{'pair_id': 'pair-a-b', 'from_at_sec': 14.5};
  final manifest = <String, dynamic>{'pair_id': 'pair-a-b', 'files': {}};
  final requests =
      ManualCutIntent.values
          .map(
            (intent) => buildManualCutRequest(
              intent: intent,
              transitionId: 'manual-${intent.name}',
              fromSongId: 'a',
              targetSongId:
                  intent == ManualCutIntent.fast ? 'queue-next' : 'selected',
              transitionPlan: plan,
              pairManifest: manifest,
            ),
          )
          .toList();

  for (final request in requests) {
    expect(
      request.keys.toSet().length == requests.first.keys.toSet().length,
      'all intents must use one request shape',
    );
    expect(
      request['transition_plan']['pair_id'] == 'pair-a-b',
      'all intents must use the shared prepared plan',
    );
  }
  expect(requests[0]['trigger'] == 'fast_cut', 'fast trigger');
  expect(requests[1]['trigger'] == 'energy_cut', 'energy trigger');
  expect(requests[2]['trigger'] == 'style_cut', 'style trigger');
  expect(!ManualCutIntent.fast.insertsTargetAsNext, 'queue next is retained');
  expect(
    ManualCutIntent.energy.insertsTargetAsNext,
    'energy target is inserted',
  );
  expect(ManualCutIntent.style.insertsTargetAsNext, 'style target is inserted');

  final scheduled = ManualTransitionTask.fromJson({
    'transition_id': 'manual-1',
    'pair_id': 'pair-a-b',
    'state': 'scheduled',
    'timings': {'rk_sync_sec': 1.25},
  });
  final failed = ManualTransitionTask.fromJson({
    'transition_id': 'manual-2',
    'pair_id': 'pair-a-b',
    'state': 'failed',
    'error': {'code': 'sync_failed'},
  });
  expect(scheduled.isCommitted && !scheduled.isTerminal, 'scheduled task');
  expect(failed.isTerminal && !failed.isCommitted, 'failed task');

  expect(
    playbackConfirmsManualTransition(
      PlaybackSnapshot.fromJson({
        'playing': true,
        'current_song_id': 'render',
        'last_transition': {'transition_id': 'manual-1'},
      }),
      transitionId: 'manual-1',
      targetSongId: 'b',
    ),
    'render playback must confirm by operation id',
  );
  expect(
    playbackConfirmsManualTransition(
      const PlaybackSnapshot(playing: true, currentSongId: 'b'),
      transitionId: 'manual-1',
      targetSongId: 'b',
    ),
    'resume must confirm by target song',
  );

  final pending =
      PendingManualTransition(
        transitionId: 'manual-1',
        intent: ManualCutIntent.energy,
        fromSongId: 'a',
        targetSongId: 'b',
        createdAtMs: 1,
      ).toJson();
  expect(
    pending['trigger'] == 'energy_cut',
    'pending context uses wire intent',
  );

  final context = PendingManualTransition(
    transitionId: 'manual-life',
    intent: ManualCutIntent.style,
    fromSongId: 'a',
    targetSongId: 'b',
    createdAtMs: 1000,
  );
  final lifecycle = ManualTransitionLifecycle(context);
  lifecycle.accept(
    ManualTransitionTask.fromJson({
      'transition_id': 'manual-life',
      'pair_id': 'pair-a-b',
      'state': 'accepted',
    }),
    nowMs: 1100,
  );
  lifecycle.accept(
    ManualTransitionTask.fromJson({
      'transition_id': 'manual-life',
      'pair_id': 'pair-a-b',
      'state': 'syncing',
    }),
    nowMs: 1200,
  );
  expect(
    lifecycle.task?.state == ManualTransitionState.syncing,
    'valid lifecycle',
  );

  var rejectedOtherTask = false;
  try {
    lifecycle.accept(
      ManualTransitionTask.fromJson({
        'transition_id': 'other-task',
        'pair_id': 'pair-a-b',
        'state': 'cache_ready',
      }),
      nowMs: 1300,
    );
  } on StateError {
    rejectedOtherTask = true;
  }
  expect(rejectedOtherTask, 'another transition must not overwrite state');
  expect(context.isExpired(121000), 'pending TTL is explicit');
  expect(
    lifecycle.confirmsPlayback(
      const PlaybackSnapshot(playing: true, currentSongId: 'b'),
    ),
    'lifecycle confirms target playback',
  );
  print('mobile-dj-control: 11 passed');
}
