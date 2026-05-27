class TransitionDetail {
  TransitionDetail({
    required this.toSongId,
    required this.style,
    required this.startsInSec,
    required this.confidence,
    this.tags = const [],
  });

  final String toSongId;
  final String style;
  final double startsInSec;
  final double confidence;
  final List<String> tags;

  factory TransitionDetail.fromJson(Map<String, dynamic> json) {
    return TransitionDetail(
      toSongId: (json['to_song_id'] as num?)?.toString() ?? '',
      style: json['style'] as String? ?? 'blend',
      startsInSec: (json['starts_in_sec'] as num?)?.toDouble() ?? 0,
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      tags: (json['tags'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}

class LivePlaybackState {
  LivePlaybackState({
    required this.playing,
    this.currentSongId,
    required this.positionSec,
    required this.durationSec,
    this.nextSongId,
    this.nextTransitionInSec,
    this.playbackTier,
    this.currentSection,
    this.currentEnergy,
    this.nextTransition,
    this.deckA,
    this.deckB,
    this.error,
  });

  final bool playing;
  final String? currentSongId;
  final double positionSec;
  final double durationSec;
  final String? nextSongId;
  final double? nextTransitionInSec;
  final String? playbackTier;
  final String? currentSection;
  final double? currentEnergy;
  final TransitionDetail? nextTransition;
  final Map<String, dynamic>? deckA;
  final Map<String, dynamic>? deckB;
  final String? error;

  factory LivePlaybackState.fromJson(Map<String, dynamic> json) {
    String? _idToStr(dynamic v) {
      if (v == null) return null;
      if (v is String) return v;
      if (v is num) return v.toString();
      return v.toString();
    }
    return LivePlaybackState(
      playing: json['playing'] as bool? ?? false,
      currentSongId: _idToStr(json['current_song_id']),
      positionSec: (json['position_sec'] as num?)?.toDouble() ?? 0,
      durationSec: (json['duration_sec'] as num?)?.toDouble() ?? 0,
      nextSongId: _idToStr(json['next_song_id']),
      nextTransitionInSec:
          (json['next_transition_in_sec'] as num?)?.toDouble(),
      playbackTier: json['playback_tier'] as String?,
      currentSection: json['current_section'] as String?,
      currentEnergy: (json['current_energy'] as num?)?.toDouble(),
      nextTransition: json['next_transition'] is Map
          ? TransitionDetail.fromJson(json['next_transition'])
          : null,
      deckA: json['deck_a'] as Map<String, dynamic>?,
      deckB: json['deck_b'] as Map<String, dynamic>?,
    );
  }
}

class LiveOverrideRequest {
  LiveOverrideRequest({
    this.nextSongId,
    this.style,
    this.fadeSec,
    required this.execute,
  });

  final String? nextSongId;
  final String? style;
  final double? fadeSec;
  final String execute;

  Map<String, dynamic> toJson() {
    final body = <String, dynamic>{'execute': execute};
    if (nextSongId != null) body['next_song_id'] = nextSongId;
    if (style != null) body['style'] = style;
    if (fadeSec != null) body['fade_sec'] = fadeSec;
    return body;
  }
}

class LiveOverrideResponse {
  LiveOverrideResponse({
    required this.ok,
    required this.transition,
    this.warnings = const [],
  });

  final bool ok;
  final TransitionDetail transition;
  final List<String> warnings;

  factory LiveOverrideResponse.fromJson(Map<String, dynamic> json) {
    return LiveOverrideResponse(
      ok: json['ok'] as bool? ?? false,
      transition: TransitionDetail.fromJson(
          json['transition'] as Map<String, dynamic>? ?? {}),
      warnings: (json['warnings'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}

class LiveIntentRequest {
  LiveIntentRequest({
    required this.intent,
    this.scope = 'next_transition',
    this.maxRisk = 0.45,
  });

  final String intent;
  final String scope;
  final double maxRisk;

  Map<String, dynamic> toJson() {
    return {
      'intent': intent,
      'scope': scope,
      'max_risk': maxRisk,
    };
  }
}

class LiveIntentResponse {
  LiveIntentResponse({
    required this.ok,
    this.updatedPlan,
    this.explanation,
    this.warnings = const [],
  });

  final bool ok;
  final Map<String, dynamic>? updatedPlan;
  final String? explanation;
  final List<String> warnings;

  factory LiveIntentResponse.fromJson(Map<String, dynamic> json) {
    return LiveIntentResponse(
      ok: json['ok'] as bool? ?? false,
      updatedPlan: json['updated_plan'] as Map<String, dynamic>?,
      explanation: json['explanation'] as String?,
      warnings: (json['warnings'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}
