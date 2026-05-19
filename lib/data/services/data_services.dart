import '../../core/network/api_client.dart';
import '../models/models.dart';
import '../../core/utils/logger.dart';

/// 音乐库服务
class MusicService {
  static final MusicService _instance = MusicService._internal();
  factory MusicService() => _instance;
  MusicService._internal();

  final _dio = ApiClient().dio;

  /// 获取所有歌曲
  Future<List<Song>> getAllSongs() async {
    try {
      final response = await _dio.get('/api/music/songs');
      final songs = response.data['data']?['songs'];
      
      if (songs == null) return [];
      
      return (songs as List)
          .map((s) => Song.fromJson(s))
          .toList();
    } catch (e) {
      AppLogger.error('获取歌曲列表异常: $e');
      return [];
    }
  }

  /// 搜索歌曲
  Future<List<Song>> searchSongs(String query) async {
    try {
      final response = await _dio.get(
        '/api/music/songs/search',
        queryParameters: {'q': query},
      );
      
      final songs = response.data['data']?['songs'];
      if (songs == null) return [];
      
      return (songs as List)
          .map((s) => Song.fromJson(s))
          .toList();
    } catch (e) {
      AppLogger.error('搜索歌曲异常: $e');
      return [];
    }
  }

  /// 获取单曲详情
  Future<Song?> getSongById(int id) async {
    try {
      final response = await _dio.get('/api/music/songs/$id');
      final songData = response.data['data'];
      
      if (songData == null) return null;
      
      return Song.fromJson(songData);
    } catch (e) {
      AppLogger.error('获取歌曲详情异常: $e');
      return null;
    }
  }
}

/// 歌单服务
class PlaylistService {
  static final PlaylistService _instance = PlaylistService._internal();
  factory PlaylistService() => _instance;
  PlaylistService._internal();

  final _dio = ApiClient().dio;

  /// 获取所有歌单
  Future<List<Playlist>> getAllPlaylists() async {
    try {
      final response = await _dio.get('/api/playlists');
      final playlists = response.data['data']?['playlists'];
      
      if (playlists == null) return [];
      
      return (playlists as List)
          .map((p) => Playlist.fromJson(p))
          .toList();
    } catch (e) {
      AppLogger.error('获取歌单列表异常: $e');
      return [];
    }
  }

  /// 获取官方歌单（按场景分类）
  Future<List<Playlist>> getOfficialPlaylists() async {
    try {
      final response = await _dio.get(
        '/api/playlists',
        queryParameters: {'type': 'official'},
      );
      
      final playlists = response.data['data']?['playlists'];
      if (playlists == null) return [];
      
      return (playlists as List)
          .map((p) => Playlist.fromJson(p))
          .toList();
    } catch (e) {
      AppLogger.error('获取官方歌单异常: $e');
      return [];
    }
  }

  /// 获取歌单详情（包含歌曲列表）
  Future<Playlist?> getPlaylistById(int id) async {
    try {
      final response = await _dio.get('/api/playlists/$id');
      final playlistData = response.data['data'];
      
      if (playlistData == null) return null;
      
      return Playlist.fromJson(playlistData);
    } catch (e) {
      AppLogger.error('获取歌单详情异常: $e');
      return null;
    }
  }

  /// 创建歌单
  Future<Playlist?> createPlaylist({
    required String name,
    String? description,
    List<int>? songIds,
  }) async {
    try {
      final response = await _dio.post(
        '/api/playlists',
        data: {
          'name': name,
          'description': description,
          'song_ids': songIds,
        },
      );
      
      final playlistData = response.data['data'];
      if (playlistData == null) return null;
      
      return Playlist.fromJson(playlistData);
    } catch (e) {
      AppLogger.error('创建歌单异常: $e');
      return null;
    }
  }

  /// 添加歌曲到歌单
  Future<bool> addSongsToPlaylist(int playlistId, List<int> songIds) async {
    try {
      await _dio.post(
        '/api/playlists/$playlistId/songs',
        data: {'song_ids': songIds},
      );
      return true;
    } catch (e) {
      AppLogger.error('添加歌曲到歌单异常: $e');
      return false;
    }
  }
}

/// 会话服务
class SessionService {
  static final SessionService _instance = SessionService._internal();
  factory SessionService() => _instance;
  SessionService._internal();

  final _dio = ApiClient().dio;

  /// 开始会话
  Future<Session?> startSession({
    required int userId,
    String mode = 'practice',
  }) async {
    try {
      final response = await _dio.post(
        '/api/sessions/start',
        data: {
          'user_id': userId,
          'mode': mode,
        },
      );
      
      final sessionData = response.data['data'];
      if (sessionData == null) return null;
      
      return Session.fromJson(sessionData);
    } catch (e) {
      AppLogger.error('开始会话异常: $e');
      return null;
    }
  }

  /// 结束会话
  Future<bool> endSession(int sessionId) async {
    try {
      await _dio.post(
        '/api/sessions/end',
        data: {'session_id': sessionId},
      );
      return true;
    } catch (e) {
      AppLogger.error('结束会话异常: $e');
      return false;
    }
  }

  /// 记录会话事件
  Future<bool> logEvent({
    required int sessionId,
    required String eventType,
    dynamic eventValue,
  }) async {
    try {
      await _dio.post(
        '/api/sessions/event',
        data: {
          'session_id': sessionId,
          'event_type': eventType,
          'event_value': eventValue,
          'timestamp': DateTime.now().toIso8601String(),
        },
      );
      return true;
    } catch (e) {
      AppLogger.error('记录会话事件异常: $e');
      return false;
    }
  }
}
