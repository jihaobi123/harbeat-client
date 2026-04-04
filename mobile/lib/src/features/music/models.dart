class CatalogSong {
  CatalogSong({
    required this.id,
    required this.title,
    required this.artist,
    this.audioUrl,
    this.duration,
    this.bpm,
    this.energy,
    this.style,
    this.vocalType,
    this.eraTag,
    this.grooveTag,
    this.difficultyFit,
    required this.tags,
  });

  final int id;
  final String title;
  final String artist;
  final String? audioUrl;
  final double? duration;
  final int? bpm;
  final String? energy;
  final String? style;
  final String? vocalType;
  final String? eraTag;
  final String? grooveTag;
  final String? difficultyFit;
  final List<String> tags;

  factory CatalogSong.fromJson(Map<String, dynamic> json) {
    return CatalogSong(
      id: json['id'] as int? ?? 0,
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      audioUrl: json['audio_url'] as String?,
      duration: (json['duration'] as num?)?.toDouble(),
      bpm: json['bpm'] as int?,
      energy: json['energy'] as String?,
      style: json['style'] as String?,
      vocalType: json['vocal_type'] as String?,
      eraTag: json['era_tag'] as String?,
      grooveTag: json['groove_tag'] as String?,
      difficultyFit: json['difficulty_fit'] as String?,
      tags: (json['tags'] as List<dynamic>? ?? []).cast<String>(),
    );
  }
}

class SongCue {
  SongCue({
    required this.id,
    required this.cueType,
    required this.startTime,
    this.endTime,
    this.label,
  });

  final int id;
  final String cueType;
  final double startTime;
  final double? endTime;
  final String? label;

  factory SongCue.fromJson(Map<String, dynamic> json) {
    return SongCue(
      id: json['id'] as int? ?? 0,
      cueType: json['cue_type'] as String? ?? '',
      startTime: (json['start_time'] as num?)?.toDouble() ?? 0,
      endTime: (json['end_time'] as num?)?.toDouble(),
      label: json['label'] as String?,
    );
  }
}
