import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/audio/audio_player_service.dart';
import '../core/network/api_repository.dart';

class CuePoint {
  final Duration position;
  final String remark;

  CuePoint({required this.position, required this.remark});
}

class PracticeState {
  final int userId;
  final int? sessionId;
  final Duration? pointA;
  final Duration? pointB;
  final List<CuePoint> cuePoints;
  final bool isPlaying;

  PracticeState({
    this.userId = 1,
    this.sessionId,
    this.pointA,
    this.pointB,
    this.cuePoints = const [],
    this.isPlaying = false,
  });

  PracticeState copyWith({
    int? userId,
    int? sessionId,
    Duration? pointA,
    Duration? pointB,
    List<CuePoint>? cuePoints,
    bool? isPlaying,
  }) {
    return PracticeState(
      userId: userId ?? this.userId,
      sessionId: sessionId ?? this.sessionId,
      pointA: pointA ?? this.pointA,
      pointB: pointB ?? this.pointB,
      cuePoints: cuePoints ?? this.cuePoints,
      isPlaying: isPlaying ?? this.isPlaying,
    );
  }
}

class PracticeSessionNotifier extends Notifier<PracticeState> {
  @override
  PracticeState build() => PracticeState();

  Future<void> initialize({
    required int userId,
    required int trackId,
    required String mode,
  }) async {
    final api = ref.read(apiRepoProvider);
    final sessionId = await api.startSession(userId: userId, mode: mode);
    final storedCues = await api.fetchCuePoints(userId: userId, trackId: trackId);

    state = state.copyWith(
      userId: userId,
      sessionId: sessionId,
      cuePoints: storedCues
          .map((cue) => CuePoint(
                position: Duration(milliseconds: (cue.startTime * 1000).round()),
                remark: cue.name ?? cue.cueType,
              ))
          .toList(),
    );
  }

  void setPointA(Duration position) {
    ref.read(audioPlayerProvider).setPointA(position);
    state = state.copyWith(pointA: position);

    final sessionId = state.sessionId;
    if (sessionId != null) {
      ref.read(apiRepoProvider).reportEvent(sessionId, 'set_A_visual', 'time=${position.inSeconds}');
    }
  }

  void setPointB(Duration position, int trackId) {
    ref.read(audioPlayerProvider).setPointB(position);
    state = state.copyWith(pointB: position);

    final sessionId = state.sessionId;
    if (sessionId != null) {
      ref.read(apiRepoProvider).reportEvent(sessionId, 'set_B_visual', 'time=${position.inSeconds}');
    }

    if (state.pointA != null) {
      ref.read(apiRepoProvider).saveCuePoint(
        userId: state.userId,
        trackId: trackId,
        cueType: 'ab_loop',
        startTime: state.pointA!.inMilliseconds / 1000.0,
        endTime: position.inMilliseconds / 1000.0,
        name: 'A-B loop',
      );
    }
  }

  void addCuePoint(Duration position, String remark, int trackId) {
    final newCue = CuePoint(position: position, remark: remark);
    final newCues = List<CuePoint>.from(state.cuePoints)..add(newCue);
    state = state.copyWith(cuePoints: newCues);

    final sessionId = state.sessionId;
    if (sessionId != null) {
      ref.read(apiRepoProvider).reportEvent(
        sessionId,
        'mark_cue_visual',
        'time=${position.inSeconds},remark=$remark',
      );
    }

    ref.read(apiRepoProvider).saveCuePoint(
      userId: state.userId,
      trackId: trackId,
      cueType: 'cue',
      startTime: position.inMilliseconds / 1000.0,
      name: remark,
    );
  }
}

final practiceProvider = NotifierProvider<PracticeSessionNotifier, PracticeState>(() {
  return PracticeSessionNotifier();
});
