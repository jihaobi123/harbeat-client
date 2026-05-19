class MixPlan {
  final String planId;
  final int playlistId;
  final DateTime generatedAt;
  final List<MixTrack> tracks;
  final List<MixTransition> transitions;

  MixPlan({
    required this.planId,
    required this.playlistId,
    required this.generatedAt,
    required this.tracks,
    required this.transitions,
  });

  factory MixPlan.fromJson(Map<String, dynamic> json) {
    return MixPlan(
      planId: json['plan_id'] ?? '',
      playlistId: json['playlist_id'] ?? 0,
      generatedAt: json['generated_at'] != null
          ? DateTime.parse(json['generated_at'])
          : DateTime.now(),
      tracks: (json['tracks'] as List?)
              ?.map((t) => MixTrack.fromJson(t))
              .toList() ??
          [],
      transitions: (json['transitions'] as List?)
              ?.map((t) => MixTransition.fromJson(t))
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'plan_id': planId,
      'playlist_id': playlistId,
      'generated_at': generatedAt.toIso8601String(),
      'tracks': tracks.map((t) => t.toJson()).toList(),
      'transitions': transitions.map((t) => t.toJson()).toList(),
    };
  }
}

class MixTrack {
  final String songId;
  final int order;
  final double startAtSec;
  final double playDurationSec;

  MixTrack({
    required this.songId,
    required this.order,
    required this.startAtSec,
    required this.playDurationSec,
  });

  factory MixTrack.fromJson(Map<String, dynamic> json) {
    return MixTrack(
      songId: json['song_id'] ?? '',
      order: json['order'] ?? 0,
      startAtSec: (json['start_at_sec'] as num?)?.toDouble() ?? 0.0,
      playDurationSec: (json['play_duration_sec'] as num?)?.toDouble() ?? 0.0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'song_id': songId,
      'order': order,
      'start_at_sec': startAtSec,
      'play_duration_sec': playDurationSec,
    };
  }
}

class MixTransition {
  final String fromSong;
  final String toSong;
  final double fromAtSec;
  final double toAtSec;
  final double fadeSec;
  final String fadeCurve;

  MixTransition({
    required this.fromSong,
    required this.toSong,
    required this.fromAtSec,
    required this.toAtSec,
    required this.fadeSec,
    required this.fadeCurve,
  });

  factory MixTransition.fromJson(Map<String, dynamic> json) {
    return MixTransition(
      fromSong: json['from_song'] ?? '',
      toSong: json['to_song'] ?? '',
      fromAtSec: (json['from_at_sec'] as num?)?.toDouble() ?? 0.0,
      toAtSec: (json['to_at_sec'] as num?)?.toDouble() ?? 0.0,
      fadeSec: (json['fade_sec'] as num?)?.toDouble() ?? 0.0,
      fadeCurve: json['fade_curve'] ?? 'equal_power',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'from_song': fromSong,
      'to_song': toSong,
      'from_at_sec': fromAtSec,
      'to_at_sec': toAtSec,
      'fade_sec': fadeSec,
      'fade_curve': fadeCurve,
    };
  }
}
