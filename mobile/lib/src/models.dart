class AuthPayload {
  AuthPayload({
    required this.accessToken,
    required this.userId,
    required this.username,
  });

  final String accessToken;
  final int userId;
  final String username;

  factory AuthPayload.fromJson(Map<String, dynamic> json) {
    return AuthPayload(
      accessToken: json['access_token'] as String,
      userId: (json['user_id'] as num).toInt(),
      username: json['username'] as String,
    );
  }
}

class UserProfile {
  UserProfile({
    required this.id,
    required this.username,
    required this.danceStyle,
    required this.level,
    required this.favoriteStyle,
  });

  final int id;
  final String username;
  final String danceStyle;
  final String level;
  final String favoriteStyle;

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: (json['id'] as num).toInt(),
      username: json['username'] as String? ?? '',
      danceStyle: json['dance_style'] as String? ?? '',
      level: json['level'] as String? ?? '',
      favoriteStyle: json['favorite_style'] as String? ?? '',
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
    required this.analysisStatus,
    required this.fileSize,
    required this.createdAt,
    this.bpm,
    this.key,
    this.camelotKey,
    this.energy,
    this.sourceType = '',
    this.stems = const {},
    this.cuePoints = const [],
    this.beatPoints = const [],
  });

  final String id;
  final int userId;
  final String title;
  final String artist;
  final double duration;
  final String format;
  final String analysisStatus;
  final int fileSize;
  final String createdAt;
  final double? bpm;
  final String? key;
  final String? camelotKey;
  final double? energy;
  final String sourceType;
  final Map<String, String> stems;
  final List<LibraryCuePoint> cuePoints;
  final List<double> beatPoints;

  bool get hasStems => stems.length == 4;

  factory LibrarySong.fromJson(Map<String, dynamic> json) {
    final stemsRaw = json['stems'];
    final stems = <String, String>{};
    if (stemsRaw is Map) {
      stemsRaw.forEach((k, v) {
        if (v is String && v.isNotEmpty) stems[k.toString()] = v;
      });
    }
    final cuesRaw = json['cue_points'] as List<dynamic>? ?? const [];
    final cues = cuesRaw
        .whereType<Map<String, dynamic>>()
        .map(LibraryCuePoint.fromJson)
        .toList();
    final beatsRaw = json['beat_points'] as List<dynamic>? ?? const [];
    final beats = beatsRaw
        .map((e) => (e as num?)?.toDouble())
        .whereType<double>()
        .toList();
    return LibrarySong(
      id: json['id'] as String,
      userId: (json['user_id'] as num?)?.toInt() ?? 0,
      title: json['title'] as String? ?? 'Untitled',
      artist: json['artist'] as String? ?? 'Unknown Artist',
      duration: (json['duration'] as num?)?.toDouble() ?? 0,
      format: json['format'] as String? ?? 'unknown',
      analysisStatus: json['analysis_status'] as String? ?? 'none',
      fileSize: (json['file_size'] as num?)?.toInt() ?? 0,
      createdAt: json['created_at'] as String? ?? '',
      bpm: (json['bpm'] as num?)?.toDouble(),
      key: json['key'] as String?,
      camelotKey: json['camelot_key'] as String?,
      energy: (json['energy'] as num?)?.toDouble(),
      sourceType: json['source_type'] as String? ?? '',
      stems: stems,
      cuePoints: cues,
      beatPoints: beats,
    );
  }
}

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
      id: json['id']?.toString() ?? '',
      time: (json['time'] as num?)?.toDouble() ?? 0,
      label: json['label'] as String? ?? '',
      color: json['color'] as String? ?? '#999999',
    );
  }
}

class PlaylistSummary {
  PlaylistSummary({
    required this.id,
    required this.name,
    required this.songCount,
    required this.sourceType,
  });

  final int id;
  final String name;
  final int songCount;
  final String sourceType;

  factory PlaylistSummary.fromJson(Map<String, dynamic> json) {
    return PlaylistSummary(
      id: (json['id'] as num).toInt(),
      name: json['playlist_name'] as String? ?? 'Untitled Playlist',
      songCount: (json['song_count'] as num?)?.toInt() ?? 0,
      sourceType: json['source_type'] as String? ?? 'manual',
    );
  }
}

class PlaylistSong {
  PlaylistSong({
    required this.songId,
    required this.title,
    required this.artist,
    required this.orderIndex,
    this.audioUrl,
    this.duration,
    this.bpm,
    this.tags = const [],
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
      songId: (json['song_id'] as num).toInt(),
      title: json['title'] as String? ?? 'Untitled',
      artist: json['artist'] as String? ?? 'Unknown Artist',
      audioUrl: json['audio_url'] as String?,
      duration: (json['duration'] as num?)?.toDouble(),
      bpm: (json['bpm'] as num?)?.toInt(),
      tags: (json['tags'] as List<dynamic>? ?? const []).map((e) => e.toString()).toList(),
      orderIndex: (json['order_index'] as num?)?.toInt() ?? 0,
    );
  }
}

class PlaylistDetail {
  PlaylistDetail({
    required this.id,
    required this.name,
    required this.sourceType,
    required this.songs,
  });

  final int id;
  final String name;
  final String sourceType;
  final List<PlaylistSong> songs;

  factory PlaylistDetail.fromJson(Map<String, dynamic> json) {
    return PlaylistDetail(
      id: (json['id'] as num).toInt(),
      name: json['playlist_name'] as String? ?? 'Untitled Playlist',
      sourceType: json['source_type'] as String? ?? 'manual',
      songs: (json['songs'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(PlaylistSong.fromJson)
          .toList(),
    );
  }
}

class FangpiSong {
  FangpiSong({
    required this.id,
    required this.title,
    required this.artist,
    required this.url,
    this.source,
  });

  final String id;
  final String title;
  final String artist;
  final String url;
  final String? source;

  factory FangpiSong.fromJson(Map<String, dynamic> json) {
    return FangpiSong(
      id: json['id'] as String,
      title: json['title'] as String? ?? 'Untitled',
      artist: json['artist'] as String? ?? 'Unknown Artist',
      url: json['url'] as String? ?? '',
      source: json['source'] as String?,
    );
  }
}

class AuthResult {
  AuthResult({
    required this.token,
    required this.profile,
  });

  final String token;
  final UserProfile profile;
}

class SessionBundle {
  SessionBundle({
    required this.token,
    required this.profile,
  });

  final String token;
  final UserProfile profile;
}

class DashboardData {
  DashboardData({
    required this.profile,
    required this.songs,
    required this.playlists,
  });

  final UserProfile profile;
  final List<LibrarySong> songs;
  final List<PlaylistSummary> playlists;
}

class DiscoverSongItem {
  DiscoverSongItem({
    required this.songId,
    required this.title,
    required this.artist,
    required this.inLibrary,
    this.style,
    this.energy,
  });

  final int songId;
  final String title;
  final String artist;
  final String? style;
  final String? energy;
  final bool inLibrary;

  factory DiscoverSongItem.fromJson(Map<String, dynamic> json) {
    return DiscoverSongItem(
      songId: (json['song_id'] as num).toInt(),
      title: json['title'] as String? ?? 'Untitled',
      artist: json['artist'] as String? ?? 'Unknown Artist',
      style: json['style'] as String?,
      energy: json['energy'] as String?,
      inLibrary: json['in_library'] as bool? ?? false,
    );
  }
}

class DiscoverSectionData {
  DiscoverSectionData({
    required this.key,
    required this.title,
    required this.icon,
    required this.description,
    required this.songs,
  });

  final String key;
  final String title;
  final String icon;
  final String description;
  final List<DiscoverSongItem> songs;

  factory DiscoverSectionData.fromJson(Map<String, dynamic> json) {
    return DiscoverSectionData(
      key: json['key'] as String? ?? '',
      title: json['title'] as String? ?? '',
      icon: json['icon'] as String? ?? '🎵',
      description: json['description'] as String? ?? '',
      songs: (json['songs'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(DiscoverSongItem.fromJson)
          .toList(),
    );
  }
}

class MusicProfile {
  MusicProfile({
    required this.favoriteStyle,
    this.avgBpmPreference,
    this.energyPreference,
    this.vocalPreference,
    this.groovePreference,
  });

  final String favoriteStyle;
  final int? avgBpmPreference;
  final String? energyPreference;
  final String? vocalPreference;
  final String? groovePreference;

  factory MusicProfile.fromJson(Map<String, dynamic> json) {
    return MusicProfile(
      favoriteStyle: json['favorite_style'] as String? ?? '',
      avgBpmPreference: (json['avg_bpm_preference'] as num?)?.toInt(),
      energyPreference: json['energy_preference'] as String?,
      vocalPreference: json['vocal_preference'] as String?,
      groovePreference: json['groove_preference'] as String?,
    );
  }
}

class PracticeTrack {
  PracticeTrack({
    required this.id,
    required this.title,
    required this.artist,
    required this.duration,
    this.bpm,
    this.camelotKey,
    this.energy,
  });

  final String id;
  final String title;
  final String artist;
  final double duration;
  final double? bpm;
  final String? camelotKey;
  final double? energy;

  factory PracticeTrack.fromJson(Map<String, dynamic> json) {
    return PracticeTrack(
      id: json['id'] as String,
      title: json['title'] as String? ?? 'Untitled',
      artist: json['artist'] as String? ?? 'Unknown Artist',
      duration: (json['duration'] as num?)?.toDouble() ?? 0,
      bpm: (json['bpm'] as num?)?.toDouble(),
      camelotKey: json['camelot_key'] as String?,
      energy: (json['energy'] as num?)?.toDouble(),
    );
  }
}

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
    this.tags = const [],
  });

  final int id;
  final String title;
  final String artist;
  final String? audioUrl;
  final double? duration;
  final int? bpm;
  final String? energy;
  final String? style;
  final List<String> tags;

  factory CatalogSong.fromJson(Map<String, dynamic> json) {
    return CatalogSong(
      id: (json['id'] as num).toInt(),
      title: json['title'] as String? ?? 'Untitled',
      artist: json['artist'] as String? ?? 'Unknown Artist',
      audioUrl: json['audio_url'] as String?,
      duration: (json['duration'] as num?)?.toDouble(),
      bpm: (json['bpm'] as num?)?.toInt(),
      energy: json['energy'] as String?,
      style: json['style'] as String?,
      tags: (json['tags'] as List<dynamic>? ?? const []).map((e) => e.toString()).toList(),
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
      id: (json['id'] as num).toInt(),
      cueType: json['cue_type'] as String? ?? '',
      startTime: (json['start_time'] as num?)?.toDouble() ?? 0,
      endTime: (json['end_time'] as num?)?.toDouble(),
      label: json['label'] as String?,
    );
  }
}

class StyleProcessResult {
  StyleProcessResult({
    required this.songId,
    required this.processedFiles,
  });

  final int songId;
  final Map<String, String> processedFiles;

  factory StyleProcessResult.fromJson(Map<String, dynamic> json) {
    return StyleProcessResult(
      songId: (json['song_id'] as num).toInt(),
      processedFiles: (json['processed_files'] as Map<String, dynamic>? ?? const {})
          .map((key, value) => MapEntry(key, value.toString())),
    );
  }
}

class DjMixTrack {
  DjMixTrack({
    required this.songId,
    required this.title,
    required this.artist,
    this.duration,
    this.bpm,
    this.tags = const [],
  });

  final int songId;
  final String title;
  final String artist;
  final double? duration;
  final int? bpm;
  final List<String> tags;

  factory DjMixTrack.fromJson(Map<String, dynamic> json) {
    return DjMixTrack(
      songId: (json['song_id'] as num).toInt(),
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      duration: (json['duration'] as num?)?.toDouble(),
      bpm: (json['bpm'] as num?)?.toInt(),
      tags: (json['tags'] as List<dynamic>? ?? const []).map((e) => e.toString()).toList(),
    );
  }
}

class DjMixPlanResult {
  DjMixPlanResult({
    required this.playlist,
    required this.processedFiles,
  });

  final List<DjMixTrack> playlist;
  final Map<int, String> processedFiles;

  factory DjMixPlanResult.fromJson(Map<String, dynamic> json) {
    return DjMixPlanResult(
      playlist: (json['playlist'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(DjMixTrack.fromJson)
          .toList(),
      processedFiles: (json['processed_files'] as Map<String, dynamic>? ?? const {})
          .map((key, value) => MapEntry(int.parse(key), value.toString())),
    );
  }
}

class DjOfflineMixResult {
  DjOfflineMixResult({
    required this.mixPlan,
    required this.outputFiles,
    required this.streamFiles,
    required this.warnings,
    required this.durationSec,
  });

  final DjMixPlanResult mixPlan;
  final Map<String, String> outputFiles;
  final Map<String, String> streamFiles;
  final List<String> warnings;
  final double durationSec;

  factory DjOfflineMixResult.fromJson(Map<String, dynamic> json) {
    return DjOfflineMixResult(
      mixPlan: DjMixPlanResult.fromJson(json['mix_plan'] as Map<String, dynamic>),
      outputFiles: (json['output_files'] as Map<String, dynamic>? ?? const {})
          .map((key, value) => MapEntry(key, value.toString())),
      streamFiles: (json['stream_files'] as Map<String, dynamic>? ?? const {})
          .map((key, value) => MapEntry(key, value.toString())),
      warnings: (json['warnings'] as List<dynamic>? ?? const []).map((e) => e.toString()).toList(),
      durationSec: (json['duration_sec'] as num?)?.toDouble() ?? 0,
    );
  }
}


// ─── Module 2: Playlist Import (Vibe + URL) ───

class VibeSong {
  VibeSong({
    required this.title,
    required this.artist,
    required this.source,
    required this.inLibrary,
    required this.matchPercentage,
    this.songId,
    this.style,
    this.energy,
    this.spotifyId,
    this.previewUrl,
    this.albumArt,
    this.spotifyUrl,
  });

  final String title;
  final String artist;
  final String source;
  final bool inLibrary;
  final double matchPercentage;
  final int? songId;
  final String? style;
  final String? energy;
  final String? spotifyId;
  final String? previewUrl;
  final String? albumArt;
  final String? spotifyUrl;

  factory VibeSong.fromJson(Map<String, dynamic> json) {
    return VibeSong(
      title: json['title'] as String? ?? 'Untitled',
      artist: json['artist'] as String? ?? 'Unknown',
      source: json['source'] as String? ?? 'spotify',
      inLibrary: json['in_library'] as bool? ?? false,
      matchPercentage: (json['match_percentage'] as num?)?.toDouble() ?? 0,
      songId: (json['song_id'] as num?)?.toInt(),
      style: json['style'] as String?,
      energy: json['energy'] as String?,
      spotifyId: json['spotify_id'] as String?,
      previewUrl: json['preview_url'] as String?,
      albumArt: json['album_art'] as String?,
      spotifyUrl: json['spotify_url'] as String?,
    );
  }
}

class VibeSearchResult {
  VibeSearchResult({
    required this.query,
    required this.vibeDescription,
    required this.searchQuery,
    required this.genres,
    required this.songs,
  });

  final String query;
  final String vibeDescription;
  final String searchQuery;
  final List<String> genres;
  final List<VibeSong> songs;

  factory VibeSearchResult.fromJson(Map<String, dynamic> json) {
    return VibeSearchResult(
      query: json['query'] as String? ?? '',
      vibeDescription: json['vibe_description'] as String? ?? '',
      searchQuery: json['search_query'] as String? ?? '',
      genres: (json['genres'] as List<dynamic>? ?? const []).map((e) => e.toString()).toList(),
      songs: (json['songs'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(VibeSong.fromJson)
          .toList(),
    );
  }
}

class ExternalPlaylistTrack {
  ExternalPlaylistTrack({
    required this.title,
    required this.artist,
    this.album,
    this.duration,
  });

  final String title;
  final String artist;
  final String? album;
  final double? duration;

  factory ExternalPlaylistTrack.fromJson(Map<String, dynamic> json) {
    return ExternalPlaylistTrack(
      title: json['title'] as String? ?? 'Untitled',
      artist: json['artist'] as String? ?? 'Unknown',
      album: json['album'] as String?,
      duration: (json['duration'] as num?)?.toDouble(),
    );
  }
}

class ParsedExternalPlaylist {
  ParsedExternalPlaylist({
    required this.name,
    required this.tracks,
    this.source,
  });

  final String name;
  final List<ExternalPlaylistTrack> tracks;
  final String? source;

  factory ParsedExternalPlaylist.fromJson(Map<String, dynamic> json) {
    return ParsedExternalPlaylist(
      name: json['name'] as String? ?? 'Untitled Playlist',
      source: json['source'] as String?,
      tracks: (json['tracks'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(ExternalPlaylistTrack.fromJson)
          .toList(),
    );
  }
}

class FangpiCandidate {
  FangpiCandidate({
    required this.id,
    required this.title,
    required this.artist,
    this.source,
  });

  final String id;
  final String title;
  final String artist;
  final String? source;

  factory FangpiCandidate.fromJson(Map<String, dynamic> json) {
    return FangpiCandidate(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      source: json['source'] as String?,
    );
  }
}

class BatchSearchEntry {
  BatchSearchEntry({
    required this.title,
    required this.artist,
    required this.found,
    required this.candidates,
  });

  final String title;
  final String artist;
  final bool found;
  final List<FangpiCandidate> candidates;

  factory BatchSearchEntry.fromJson(Map<String, dynamic> json) {
    return BatchSearchEntry(
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      found: json['found'] as bool? ?? false,
      candidates: (json['candidates'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(FangpiCandidate.fromJson)
          .toList(),
    );
  }
}