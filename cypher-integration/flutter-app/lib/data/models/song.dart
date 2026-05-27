/// 简单的歌曲模型
class Song {
  /// 数字 song_id（Jetson 端的全局歌曲编号；旧字段，保留兼容）
  final int id;

  /// library_song_id（UUID 字符串，用户曲库行的主键，AssetManifest 用它）
  final String? libraryId;
  final String title;
  final String artist;
  final String? audioUrl;
  final double? duration; // 秒
  final int? bpm;
  final String? key; // Camelot notation (e.g., "8A")
  final String? energy; // low/medium/high
  final String? style; // hiphop/breaking/popping
  final List<String>? tags;
  final DateTime? createdAt;

  const Song({
    required this.id,
    this.libraryId,
    required this.title,
    required this.artist,
    this.audioUrl,
    this.duration,
    this.bpm,
    this.key,
    this.energy,
    this.style,
    this.tags,
    this.createdAt,
  });

  factory Song.fromJson(Map<String, dynamic> json) {
    // Jetson 同时返回 `id`(UUID string) 和 `song_id`(int)。
    // 早期/mock 数据可能 `id` 就是 int。两种都兼容。
    final rawId = json['id'];
    final songIdNum = json['song_id'];
    final int songIdInt;
    if (songIdNum is int) {
      songIdInt = songIdNum;
    } else if (songIdNum is num) {
      songIdInt = songIdNum.toInt();
    } else if (rawId is int) {
      songIdInt = rawId;
    } else if (rawId is num) {
      songIdInt = rawId.toInt();
    } else {
      songIdInt = 0;
    }
    final libId = (rawId is String) ? rawId : null;

    final bpmRaw = json['bpm'];
    final int? bpmInt = bpmRaw is int
        ? bpmRaw
        : (bpmRaw is num ? bpmRaw.round() : null);

    return Song(
      id: songIdInt,
      libraryId: libId,
      title: json['title'] ?? '',
      artist: json['artist'] ?? '',
      audioUrl: json['audio_url'],
      duration: (json['duration'] as num?)?.toDouble(),
      bpm: bpmInt,
      key: json['key'] ?? json['camelot_key'],
      energy: _energyToString(json['energy']),
      style: json['style'],
      tags: (json['tags'] as List?)?.map((e) => e.toString()).toList(),
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'].toString())
          : null,
    );
  }

  static String? _energyToString(dynamic v) {
    if (v == null) return null;
    if (v is String) return v;
    if (v is num) {
      if (v < 0.4) return 'low';
      if (v < 0.7) return 'medium';
      return 'high';
    }
    return null;
  }
  
  /// 格式化时长显示 (mm:ss)
  String get formattedDuration {
    if (duration == null) return '--:--';
    final minutes = duration! ~/ 60;
    final seconds = (duration! % 60).toInt();
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
  
  /// BPM 显示
  String get bpmDisplay => bpm != null ? '${bpm} BPM' : '-- BPM';
}
