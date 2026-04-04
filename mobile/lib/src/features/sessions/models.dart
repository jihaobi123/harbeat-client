class PracticeTrack {
  PracticeTrack({
    required this.id,
    required this.title,
    required this.artist,
    this.bpm,
    this.camelotKey,
    this.energy,
    required this.duration,
  });

  final String id;
  final String title;
  final String artist;
  final double? bpm;
  final String? camelotKey;
  final double? energy;
  final double duration;

  factory PracticeTrack.fromJson(Map<String, dynamic> json) {
    return PracticeTrack(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      bpm: (json['bpm'] as num?)?.toDouble(),
      camelotKey: json['camelot_key'] as String?,
      energy: (json['energy'] as num?)?.toDouble(),
      duration: (json['duration'] as num?)?.toDouble() ?? 0,
    );
  }
}
