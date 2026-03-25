import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/audio/audio_player_service.dart';
import '../core/network/api_repository.dart';

class CuePoint {
  final Duration position;
  final String remark;
  CuePoint({required this.position, required this.remark});
}

class PracticeState {
  final Duration? pointA;
  final Duration? pointB;
  final List<CuePoint> cuePoints;
  PracticeState({this.pointA, this.pointB, this.cuePoints = const []});

  PracticeState copyWith({Duration? pointA, Duration? pointB, List<CuePoint>? cuePoints}) {
    return PracticeState(
      pointA: pointA ?? this.pointA,
      pointB: pointB ?? this.pointB,
      cuePoints: cuePoints ?? this.cuePoints,
    );
  }
}

class PracticeSessionNotifier extends Notifier<PracticeState> {
  @override
  PracticeState build() => PracticeState();

  void setPointA(Duration position) {
    ref.read(audioPlayerProvider).setPointA(position);
    state = state.copyWith(pointA: position);
  }

  void setPointB(Duration position, int trackId) {
    ref.read(audioPlayerProvider).setPointB(position);
    state = state.copyWith(pointB: position);
    if (state.pointA != null) {
      ref.read(apiRepoProvider).saveCuePoint(
        userId: 1,
        trackId: trackId,
        cueType: "ab_loop",
        startTime: state.pointA!.inMilliseconds / 1000.0,
        endTime: position.inMilliseconds / 1000.0,
        name: "A-B段", // 这里对应刚才 API 里的 name
      );
    }
  }

  void addCuePoint(Duration position, String remark, int trackId) {
    final newCues = List<CuePoint>.from(state.cuePoints)..add(CuePoint(position: position, remark: remark));
    state = state.copyWith(cuePoints: newCues);
    ref.read(apiRepoProvider).saveCuePoint(
      userId: 1,
      trackId: trackId,
      cueType: "cue",
      startTime: position.inMilliseconds / 1000.0,
      name: remark, // 这里对应刚才 API 里的 name
    );
  }
}

final practiceProvider = NotifierProvider<PracticeSessionNotifier, PracticeState>(() => PracticeSessionNotifier());