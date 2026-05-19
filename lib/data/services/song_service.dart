import 'package:dio/dio.dart';
import '../models/song.dart';
import '../../core/network/api_client.dart';
import '../../core/config/api_config.dart';
import '../../core/utils/logger.dart';

/// 歌曲服务
class SongService {
  final ApiClient _client = ApiClient();
  
  /// 是否启用离线模式（Web 环境默认为 true）
  static bool offlineMode = true;  // 改为默认启用
  
  /// Mock 数据 - 用于离线测试
  static final List<Song> _mockSongs = [
    const Song(
      id: 1,
      title: 'Breaking Beat',
      artist: 'DJ Moonfish',
      audioUrl: null,
      duration: 180.5,
      bpm: 120,
      key: 'C Major',
      energy: 'high',
      style: 'breaking',
      tags: ['hiphop', 'dance'],
      createdAt: null,
    ),
    const Song(
      id: 2,
      title: 'Popping Groove',
      artist: 'Funk Master',
      audioUrl: null,
      duration: 210.0,
      bpm: 110,
      key: 'D Minor',
      energy: 'medium',
      style: 'popping',
      tags: ['funk', 'groove'],
      createdAt: null,
    ),
    const Song(
      id: 3,
      title: 'Locking Party',
      artist: 'Street Dancer',
      audioUrl: null,
      duration: 195.3,
      bpm: 125,
      key: 'G Major',
      energy: 'high',
      style: 'locking',
      tags: ['party', 'dance'],
      createdAt: null,
    ),
    const Song(
      id: 4,
      title: 'HipHop Flow',
      artist: 'MC Rhythm',
      audioUrl: null,
      duration: 240.0,
      bpm: 95,
      key: 'A Minor',
      energy: 'medium',
      style: 'hiphop',
      tags: ['rap', 'flow'],
      createdAt: null,
    ),
    const Song(
      id: 5,
      title: 'Freestyle Battle',
      artist: 'Battle King',
      audioUrl: null,
      duration: 165.8,
      bpm: 130,
      key: 'E Major',
      energy: 'high',
      style: 'freestyle',
      tags: ['battle', 'competition'],
      createdAt: null,
    ),
  ];
  
  /// 获取歌曲列表
  Future<List<Song>> getSongs() async {
    // 如果处于离线模式，返回 Mock 数据
    if (offlineMode) {
      AppLogger.info('Using offline mode - returning mock data');
      await Future.delayed(const Duration(milliseconds: 500)); // 模拟网络延迟
      return _mockSongs;
    }
    
    try {
      final response = await _client.dio.get('${ApiConfig.library}/songs');
      final data = response.data['data'] as Map<String, dynamic>;
      final songsList = data['songs'] as List;
      
      return songsList.map((json) => Song.fromJson(json)).toList();
    } on DioException catch (e) {
      AppLogger.error('Get songs failed, switching to offline mode', error: e);
      offlineMode = true;
      // 自动切换到离线模式
      return _mockSongs;
    }
  }
  
  /// 搜索歌曲
  Future<List<Song>> searchSongs(String query) async {
    // 如果处于离线模式，从 Mock 数据中搜索
    if (offlineMode) {
      AppLogger.info('Searching in offline mode');
      await Future.delayed(const Duration(milliseconds: 300));
      
      final lowerQuery = query.toLowerCase();
      return _mockSongs.where((song) {
        return song.title.toLowerCase().contains(lowerQuery) ||
               song.artist.toLowerCase().contains(lowerQuery) ||
               (song.style?.toLowerCase().contains(lowerQuery) ?? false);
      }).toList();
    }
    
    try {
      final response = await _client.dio.get(
        '${ApiConfig.library}/songs/search',
        queryParameters: {'q': query},
      );
      
      final data = response.data['data'] as Map<String, dynamic>;
      final songsList = data['songs'] as List;
      
      return songsList.map((json) => Song.fromJson(json)).toList();
    } on DioException catch (e) {
      AppLogger.error('Search songs failed, using offline search', error: e);
      offlineMode = true;
      
      final lowerQuery = query.toLowerCase();
      return _mockSongs.where((song) {
        return song.title.toLowerCase().contains(lowerQuery) ||
               song.artist.toLowerCase().contains(lowerQuery);
      }).toList();
    }
  }
  
  /// 获取歌曲详情
  Future<Song> getSongDetail(int songId) async {
    if (offlineMode) {
      final song = _mockSongs.firstWhere(
        (s) => s.id == songId,
        orElse: () => throw Exception('Song not found'),
      );
      return song;
    }
    
    try {
      final response = await _client.dio.get('${ApiConfig.library}/songs/$songId');
      final data = response.data['data'];
      return Song.fromJson(data);
    } on DioException catch (e) {
      AppLogger.error('Get song detail failed, using offline mode', error: e);
      offlineMode = true;
      
      final song = _mockSongs.firstWhere(
        (s) => s.id == songId,
        orElse: () => throw Exception('Song not found'),
      );
      return song;
    }
  }
  
  /// 获取音频流 URL
  String getStreamUrl(int songId, String token) {
    return '${ApiConfig.baseUrl}${ApiConfig.stream}/$songId?token=$token';
  }
  
  /// 重置为在线模式
  void resetToOnline() {
    offlineMode = false;
    AppLogger.info('Reset to online mode');
  }
}
