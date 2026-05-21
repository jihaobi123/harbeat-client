class PlaybackState {
  final int ts;
  final bool playing;
  final bool paused;
  final int? currentSongId;
  final double positionSec;
  final int? nextSongId;
  final double? nextTransitionInSec;
  final List<int> activeLoops;
  final String? activeStemFx;

  PlaybackState({
    required this.ts,
    required this.playing,
    required this.paused,
    this.currentSongId,
    required this.positionSec,
    this.nextSongId,
    this.nextTransitionInSec,
    this.activeLoops = const [],
    this.activeStemFx,
  });

  factory PlaybackState.fromJson(Map<String, dynamic> json) {
    return PlaybackState(
      ts: json['ts'] ?? DateTime.now().millisecondsSinceEpoch,
      playing: json['playing'] ?? false,
      paused: json['paused'] ?? !json['playing'],
      currentSongId: json['current_song_id'],
      positionSec: (json['position_sec'] as num?)?.toDouble() ?? 0.0,
      nextSongId: json['next_song_id'],
      nextTransitionInSec:
          (json['next_transition_in_sec'] as num?)?.toDouble(),
      activeLoops: List<int>.from(json['active_loops'] ?? []),
      activeStemFx: json['active_stem_fx'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'type': 'playback_state',
      'ts': ts,
      'playing': playing,
      'paused': paused,
      'current_song_id': currentSongId,
      'position_sec': positionSec,
      'next_song_id': nextSongId,
      'next_transition_in_sec': nextTransitionInSec,
      'active_loops': activeLoops,
      'active_stem_fx': activeStemFx,
    };
  }

  bool isLoopActive(int key) => activeLoops.contains(key);
  bool get hasActiveStemFx => activeStemFx != null;
}
