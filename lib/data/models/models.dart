/// 歌曲数据模型
class Song {
  final int id;
  final String title;
  final String artist;
  final String? album;
  final int? duration; // 秒
  final String? coverUrl;
  final String? sourcePath;
  final List<String>? tags;
  final double? bpm;
  final String? key;

  Song({
    required this.id,
    required this.title,
    required this.artist,
    this.album,
    this.duration,
    this.coverUrl,
    this.sourcePath,
    this.tags,
    this.bpm,
    this.key,
  });

  factory Song.fromJson(Map<String, dynamic> json) {
    return Song(
      id: json['id'] ?? 0,
      title: json['title'] ?? '',
      artist: json['artist'] ?? '',
      album: json['album'],
      duration: json['duration'],
      coverUrl: json['cover_url'],
      sourcePath: json['source_path'],
      tags: json['tags'] != null ? List<String>.from(json['tags']) : null,
      bpm: json['bpm']?.toDouble(),
      key: json['key'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'artist': artist,
      'album': album,
      'duration': duration,
      'cover_url': coverUrl,
      'source_path': sourcePath,
      'tags': tags,
      'bpm': bpm,
      'key': key,
    };
  }

  /// 格式化时长
  String get formattedDuration {
    if (duration == null) return '--:--';
    final minutes = duration! ~/ 60;
    final seconds = duration! % 60;
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
}

/// 歌单数据模型
class Playlist {
  final int id;
  final String name;
  final String? description;
  final String? coverUrl;
  final List<Song>? songs;
  final int? songCount;
  final String? type; // 官方歌单类型

  Playlist({
    required this.id,
    required this.name,
    this.description,
    this.coverUrl,
    this.songs,
    this.songCount,
    this.type,
  });

  factory Playlist.fromJson(Map<String, dynamic> json) {
    return Playlist(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      description: json['description'],
      coverUrl: json['cover_url'],
      songs: json['songs'] != null 
          ? (json['songs'] as List).map((s) => Song.fromJson(s)).toList()
          : null,
      songCount: json['song_count'],
      type: json['type'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'description': description,
      'cover_url': coverUrl,
      'songs': songs?.map((s) => s.toJson()).toList(),
      'song_count': songCount,
      'type': type,
    };
  }
}

/// 会话数据模型
class Session {
  final int id;
  final int userId;
  final String mode; // practice, performance
  final DateTime startTime;
  final DateTime? endTime;
  final bool isActive;

  Session({
    required this.id,
    required this.userId,
    required this.mode,
    required this.startTime,
    this.endTime,
    this.isActive = true,
  });

  factory Session.fromJson(Map<String, dynamic> json) {
    return Session(
      id: json['id'] ?? 0,
      userId: json['user_id'] ?? 0,
      mode: json['mode'] ?? 'practice',
      startTime: DateTime.parse(json['start_time']),
      endTime: json['end_time'] != null ? DateTime.parse(json['end_time']) : null,
      isActive: json['is_active'] ?? true,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'user_id': userId,
      'mode': mode,
      'start_time': startTime.toIso8601String(),
      'end_time': endTime?.toIso8601String(),
      'is_active': isActive,
    };
  }
}

/// 用户数据模型
class User {
  final int id;
  final String username;
  final String? email;
  final String? avatar;
  final String? role;

  User({
    required this.id,
    required this.username,
    this.email,
    this.avatar,
    this.role,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] ?? 0,
      username: json['username'] ?? '',
      email: json['email'],
      avatar: json['avatar'],
      role: json['role'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'username': username,
      'email': email,
      'avatar': avatar,
      'role': role,
    };
  }
}
