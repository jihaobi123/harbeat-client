import 'package:flutter/material.dart';
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
  final bool isPlaying;

  PracticeState({this.pointA, this.pointB, this.cuePoints = const [], this.isPlaying = false});

  PracticeState copyWith({Duration? pointA, Duration? pointB, List<CuePoint>? cuePoints, bool? isPlaying}) {
    return PracticeState(
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

  void setPointA(Duration position) {
    ref.read(audioPlayerProvider).setPointA(position);
    state = state.copyWith(pointA: position);
    ref.read(apiRepoProvider).reportEvent(1, "set_A_visual", "time=${position.inSeconds}");
  }

  void setPointB(Duration position, int trackId) {
    ref.read(audioPlayerProvider).setPointB(position);
    state = state.copyWith(pointB: position);
    ref.read(apiRepoProvider).reportEvent(1, "set_B_visual", "time=${position.inSeconds}");
    
    if (state.pointA != null) {
      // 修正 saveCuePoint 的调用方式
      ref.read(apiRepoProvider).saveCuePoint(
        userId: 1,
        trackId: trackId,
        cueType: "ab_loop",
        startTime: state.pointA!.inMilliseconds / 1000.0,
        endTime: position.inMilliseconds / 1000.0,
        name: "A-B段",
      );
    }
  }

  void addCuePoint(Duration position, String remark, int trackId) {
    final newCue = CuePoint(position: position, remark: remark);
    final newCues = List<CuePoint>.from(state.cuePoints)..add(newCue);
    state = state.copyWith(cuePoints: newCues);

    ref.read(apiRepoProvider).reportEvent(1, "mark_cue_visual", "time=${position.inSeconds},remark=$remark");
    ref.read(apiRepoProvider).saveCuePoint(
      userId: 1,
      trackId: trackId,
      cueType: "cue",
      startTime: position.inMilliseconds / 1000.0,
      name: remark, // 修正注释：这里将备注存为名称
    );
  }
}

final practiceProvider = NotifierProvider<PracticeSessionNotifier, PracticeState>(() {
  return PracticeSessionNotifier();
});