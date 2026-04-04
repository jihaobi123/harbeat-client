import '../../core/network/api_client.dart';
import 'models.dart';

class MusicService {
  MusicService({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<List<CatalogSong>> getCatalogSongs() async {
    final data = await _client.get<Map<String, dynamic>>(
      '/api/music/songs',
      parser: (json) => json as Map<String, dynamic>,
    );
    return (data['songs'] as List<dynamic>? ?? [])
        .map((item) => CatalogSong.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<CatalogSong>> searchCatalogSongs(String query) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/api/music/songs/search',
      query: {'q': query},
      parser: (json) => json as Map<String, dynamic>,
    );
    return (data['songs'] as List<dynamic>? ?? [])
        .map((item) => CatalogSong.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<CatalogSong> getCatalogSong(int songId) {
    return _client.get<CatalogSong>(
      '/api/music/songs/$songId',
      parser: (json) => CatalogSong.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<CatalogSong> updateSongTags(int songId, Map<String, dynamic> payload) {
    return _client.patch<CatalogSong>(
      '/api/music/songs/$songId/tags',
      body: payload,
      parser: (json) => CatalogSong.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<CatalogSong> upsertSong(Map<String, dynamic> payload) {
    return _client.post<CatalogSong>(
      '/api/music/songs/upsert',
      body: payload,
      parser: (json) => CatalogSong.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<SongCue> createCue(int songId, Map<String, dynamic> payload) {
    return _client.post<SongCue>(
      '/api/music/songs/$songId/cues',
      body: payload,
      parser: (json) => SongCue.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<List<SongCue>> getCues(int songId, int userId) async {
    final data = await _client.get<List<dynamic>>(
      '/api/music/songs/$songId/cues',
      query: {'user_id': '$userId'},
      parser: (json) => json as List<dynamic>,
    );
    return data.map((item) => SongCue.fromJson(item as Map<String, dynamic>)).toList();
  }
}
