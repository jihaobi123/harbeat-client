class PlaylistSummary {
  PlaylistSummary({
    required this.id,
    required this.userId,
    required this.playlistName,
    required this.sourceType,
    required this.songCount,
  });

  final int id;
  final int userId;
  final String playlistName;
  final String sourceType;
  final int songCount;

  factory PlaylistSummary.fromJson(Map<String, dynamic> json) {
    return PlaylistSummary(
      id: json['id'] as int? ?? 0,
      userId: json['user_id'] as int? ?? 0,
      playlistName: json['playlist_name'] as String? ?? '',
      sourceType: json['source_type'] as String? ?? '',
      songCount: json['song_count'] as int? ?? 0,
    );
  }
}

class PlaylistSong {
  PlaylistSong({
    required this.songId,
    required this.title,
    required this.artist,
    this.audioUrl,
    this.duration,
    this.bpm,
    required this.tags,
    required this.orderIndex,
  });

  final int songId;
  final String title;
  final String artist;
  final String? audioUrl;
  final double? duration;
  final int? bpm;
  final List<String> tags;
  final int orderIndex;

  factory PlaylistSong.fromJson(Map<String, dynamic> json) {
    return PlaylistSong(
      songId: json['song_id'] as int? ?? 0,
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      audioUrl: json['audio_url'] as String?,
      duration: (json['duration'] as num?)?.toDouble(),
      bpm: json['bpm'] as int?,
      tags: (json['tags'] as List<dynamic>? ?? []).cast<String>(),
      orderIndex: json['order_index'] as int? ?? 0,
    );
  }
}

class PlaylistDetail {
  PlaylistDetail({
    required this.id,
    required this.userId,
    required this.playlistName,
    required this.sourceType,
    required this.songs,
  });

  final int id;
  final int userId;
  final String playlistName;
  final String sourceType;
  final List<PlaylistSong> songs;

  factory PlaylistDetail.fromJson(Map<String, dynamic> json) {
    return PlaylistDetail(
      id: json['id'] as int? ?? 0,
      userId: json['user_id'] as int? ?? 0,
      playlistName: json['playlist_name'] as String? ?? '',
      sourceType: json['source_type'] as String? ?? '',
      songs: (json['songs'] as List<dynamic>? ?? [])
          .map((item) => PlaylistSong.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class PlaylistImportResult {
  PlaylistImportResult({
    required this.playlistId,
    required this.importCount,
    required this.pendingAnalysisCount,
  });

  final int playlistId;
  final int importCount;
  final int pendingAnalysisCount;

  factory PlaylistImportResult.fromJson(Map<String, dynamic> json) {
    return PlaylistImportResult(
      playlistId: json['playlist_id'] as int? ?? 0,
      importCount: json['import_count'] as int? ?? 0,
      pendingAnalysisCount: json['pending_analysis_count'] as int? ?? 0,
    );
  }
}
