enum ManualCutIntent { fast, energy, style }

extension ManualCutIntentWire on ManualCutIntent {
  String get trigger => switch (this) {
    ManualCutIntent.fast => 'fast_cut',
    ManualCutIntent.energy => 'energy_cut',
    ManualCutIntent.style => 'style_cut',
  };

  bool get insertsTargetAsNext => this != ManualCutIntent.fast;
}

enum ManualTransitionState {
  accepted,
  syncing,
  cacheReady,
  prewarmed,
  prepared,
  scheduled,
  executed,
  expired,
  failed,
  cancelled,
}

const _allowedStateChanges =
    <ManualTransitionState, Set<ManualTransitionState>>{
      ManualTransitionState.accepted: {
        ManualTransitionState.syncing,
        ManualTransitionState.cacheReady,
        ManualTransitionState.prewarmed,
        ManualTransitionState.failed,
        ManualTransitionState.expired,
        ManualTransitionState.cancelled,
      },
      ManualTransitionState.syncing: {
        ManualTransitionState.cacheReady,
        ManualTransitionState.failed,
        ManualTransitionState.expired,
        ManualTransitionState.cancelled,
      },
      ManualTransitionState.cacheReady: {
        ManualTransitionState.prepared,
        ManualTransitionState.prewarmed,
        ManualTransitionState.failed,
        ManualTransitionState.expired,
        ManualTransitionState.cancelled,
      },
      ManualTransitionState.prepared: {
        ManualTransitionState.scheduled,
        ManualTransitionState.failed,
        ManualTransitionState.expired,
        ManualTransitionState.cancelled,
      },
      ManualTransitionState.scheduled: {ManualTransitionState.executed},
      ManualTransitionState.prewarmed: {},
      ManualTransitionState.executed: {},
      ManualTransitionState.expired: {},
      ManualTransitionState.failed: {},
      ManualTransitionState.cancelled: {},
    };

class ManualTransitionTask {
  const ManualTransitionTask({
    required this.transitionId,
    required this.pairId,
    required this.state,
    this.acceptedPositionSec,
    this.plannedFromAtSec,
    this.deadlineInSec,
    this.timings = const {},
    this.result,
    this.error,
  });

  final String transitionId;
  final String pairId;
  final ManualTransitionState state;
  final double? acceptedPositionSec;
  final double? plannedFromAtSec;
  final double? deadlineInSec;
  final Map<String, double> timings;
  final Map<String, dynamic>? result;
  final Map<String, dynamic>? error;

  bool get isTerminal => switch (state) {
    ManualTransitionState.executed ||
    ManualTransitionState.prewarmed ||
    ManualTransitionState.expired ||
    ManualTransitionState.failed ||
    ManualTransitionState.cancelled => true,
    _ => false,
  };

  bool get isCommitted =>
      state == ManualTransitionState.scheduled ||
      state == ManualTransitionState.executed;

  factory ManualTransitionTask.fromJson(Map<String, dynamic> json) {
    final rawState = json['state']?.toString();
    final state = switch (rawState) {
      'accepted' => ManualTransitionState.accepted,
      'syncing' => ManualTransitionState.syncing,
      'cache_ready' => ManualTransitionState.cacheReady,
      'prewarmed' => ManualTransitionState.prewarmed,
      'prepared' => ManualTransitionState.prepared,
      'scheduled' => ManualTransitionState.scheduled,
      'executed' => ManualTransitionState.executed,
      'expired' => ManualTransitionState.expired,
      'failed' => ManualTransitionState.failed,
      'cancelled' => ManualTransitionState.cancelled,
      _ => throw FormatException('Unknown manual transition state: $rawState'),
    };
    final timings = <String, double>{};
    final rawTimings = json['timings'];
    if (rawTimings is Map) {
      for (final entry in rawTimings.entries) {
        if (entry.value is num) {
          timings[entry.key.toString()] = (entry.value as num).toDouble();
        }
      }
    }
    Map<String, dynamic>? map(Object? value) =>
        value is Map ? Map<String, dynamic>.from(value) : null;
    return ManualTransitionTask(
      transitionId: json['transition_id']?.toString() ?? '',
      pairId: json['pair_id']?.toString() ?? '',
      state: state,
      acceptedPositionSec: (json['accepted_position_sec'] as num?)?.toDouble(),
      plannedFromAtSec: (json['planned_from_at_sec'] as num?)?.toDouble(),
      deadlineInSec: (json['deadline_in_sec'] as num?)?.toDouble(),
      timings: timings,
      result: map(json['result']),
      error: map(json['error']),
    );
  }
}

class PlaybackSnapshot {
  const PlaybackSnapshot({
    required this.playing,
    this.currentSongId,
    this.lastTransition,
  });

  final bool playing;
  final String? currentSongId;
  final Map<String, dynamic>? lastTransition;

  factory PlaybackSnapshot.fromJson(Map<String, dynamic> json) =>
      PlaybackSnapshot(
        playing: json['playing'] == true,
        currentSongId: json['current_song_id']?.toString(),
        lastTransition:
            json['last_transition'] is Map
                ? Map<String, dynamic>.from(json['last_transition'] as Map)
                : null,
      );
}

bool playbackConfirmsManualTransition(
  PlaybackSnapshot state, {
  required String transitionId,
  String? targetSongId,
}) {
  final reported = state.lastTransition?['transition_id']?.toString();
  return reported == transitionId ||
      (targetSongId != null && state.currentSongId == targetSongId);
}

Map<String, dynamic> buildManualCutRequest({
  required ManualCutIntent intent,
  required String transitionId,
  required Object fromSongId,
  required Object targetSongId,
  required Map<String, dynamic> transitionPlan,
  required Map<String, dynamic> pairManifest,
  double minLeadSec = 1.5,
  String mode = 'schedule',
}) {
  if (transitionId.length < 8) {
    throw ArgumentError.value(transitionId, 'transitionId');
  }
  if (fromSongId.toString().isEmpty || targetSongId.toString().isEmpty) {
    throw ArgumentError('source and target song IDs are required');
  }
  if (transitionPlan['pair_id']?.toString() !=
      pairManifest['pair_id']?.toString()) {
    throw ArgumentError('plan and manifest pair_id must match');
  }
  return {
    'transition_id': transitionId,
    'trigger': intent.trigger,
    'mode': mode,
    'from_song_id': fromSongId,
    'to_song_id': targetSongId,
    'transition_plan': Map<String, dynamic>.from(transitionPlan),
    'default_mix_pair_manifest': Map<String, dynamic>.from(pairManifest),
    'min_lead_sec': minLeadSec,
  };
}

class PendingManualTransition {
  const PendingManualTransition({
    required this.transitionId,
    required this.intent,
    required this.fromSongId,
    required this.targetSongId,
    required this.createdAtMs,
  });

  final String transitionId;
  final ManualCutIntent intent;
  final String fromSongId;
  final String targetSongId;
  final int createdAtMs;

  bool isExpired(int nowMs, {int ttlMs = 120000}) {
    if (ttlMs <= 0) throw ArgumentError.value(ttlMs, 'ttlMs');
    return nowMs >= createdAtMs + ttlMs;
  }

  Map<String, dynamic> toJson() => {
    'version': 1,
    'transition_id': transitionId,
    'trigger': intent.trigger,
    'from_song_id': fromSongId,
    'target_song_id': targetSongId,
    'created_at_ms': createdAtMs,
  };
}

class ManualTransitionLifecycle {
  ManualTransitionLifecycle(this.pending);

  final PendingManualTransition pending;
  ManualTransitionTask? _task;

  ManualTransitionTask? get task => _task;

  void accept(ManualTransitionTask next, {required int nowMs}) {
    if (pending.isExpired(nowMs)) {
      throw StateError('pending manual transition has expired');
    }
    if (next.transitionId != pending.transitionId) {
      throw StateError('task belongs to another transition');
    }
    final current = _task;
    if (current != null) {
      if (next.pairId != current.pairId) {
        throw StateError('task pair changed during one transition');
      }
      if (next.state != current.state &&
          !_allowedStateChanges[current.state]!.contains(next.state)) {
        throw StateError(
          'invalid task state change: ${current.state.name} -> ${next.state.name}',
        );
      }
    }
    _task = next;
  }

  bool confirmsPlayback(PlaybackSnapshot playback) =>
      playbackConfirmsManualTransition(
        playback,
        transitionId: pending.transitionId,
        targetSongId: pending.targetSongId,
      );
}
