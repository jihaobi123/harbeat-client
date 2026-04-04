class LibraryCuePoint {
  LibraryCuePoint({
    required this.id,
    required this.time,
    required this.label,
    required this.color,
  });

  final String id;
  final double time;
  final String label;
  final String color;

  factory LibraryCuePoint.fromJson(Map<String, dynamic> json) {
    return LibraryCuePoint(
      id: json['id'] as String? ?? '',
      time: (json['time'] as num?)?.toDouble() ?? 0,
      label: json['label'] as String? ?? '',
      color: json['color'] as String? ?? '#ffffff',
    );
  }
}

class LibrarySong {
  LibrarySong({
    required this.id,
    required this.userId,
    required this.title,
    required this.artist,
    required this.duration,
    required this.format,
    required this.fileSize,
    required this.sourceType,
    required this.sourcePath,
    this.platformId,
    this.platformUrl,
    this.bpm,
    this.keySignature,
    this.camelotKey,
    this.energy,
    required this.analysisStatus,
    required this.beatPoints,
    required this.cuePoints,
    this.stems,
    this.songId,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final int userId;
  final String title;
  final String artist;
  final double duration;
  final String format;
  final int fileSize;
  final String sourceType;
  final String sourcePath;
  final String? platformId;
  final String? platformUrl;
  final double? bpm;
  final String? keySignature;
  final String? camelotKey;
  final double? energy;
  final String analysisStatus;
  final List<double> beatPoints;
  final List<LibraryCuePoint> cuePoints;
  final Map<String, dynamic>? stems;
  final int? songId;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  factory LibrarySong.fromJson(Map<String, dynamic> json) {
    return LibrarySong(
      id: json['id'] as String? ?? '',
      userId: json['user_id'] as int? ?? 0,
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      duration: (json['duration'] as num?)?.toDouble() ?? 0,
      format: json['format'] as String? ?? '',
      fileSize: json['file_size'] as int? ?? 0,
      sourceType: json['source_type'] as String? ?? '',
      sourcePath: json['source_path'] as String? ?? '',
      platformId: json['platform_id'] as String?,
      platformUrl: json['platform_url'] as String?,
      bpm: (json['bpm'] as num?)?.toDouble(),
      keySignature: json['key'] as String?,
      camelotKey: json['camelot_key'] as String?,
      energy: (json['energy'] as num?)?.toDouble(),
      analysisStatus: json['analysis_status'] as String? ?? 'none',
      beatPoints: (json['beat_points'] as List<dynamic>? ?? [])
          .map((item) => (item as num).toDouble())
          .toList(),
      cuePoints: (json['cue_points'] as List<dynamic>? ?? [])
          .map((item) => LibraryCuePoint.fromJson(item as Map<String, dynamic>))
          .toList(),
      stems: json['stems'] as Map<String, dynamic>?,
      songId: json['song_id'] as int?,
      createdAt: json['created_at'] == null ? null : DateTime.tryParse(json['created_at'] as String),
      updatedAt: json['updated_at'] == null ? null : DateTime.tryParse(json['updated_at'] as String),
    );
  }
}
