import '../../core/network/api_client.dart';
import 'models.dart';

class RecommendationsService {
  RecommendationsService({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<List<RecommendedSong>> getRecommendations({
    required int userId,
    required String mode,
    int? currentSongId,
    String? targetEnergy,
    String source = 'library',
  }) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/recommendations/for-user',
      body: {
        'user_id': userId,
        'mode': mode,
        'current_song_id': currentSongId,
        'target_energy': targetEnergy,
        'source': source,
      },
      parser: (json) => json as Map<String, dynamic>,
    );
    return (data['songs'] as List<dynamic>? ?? [])
        .map((item) => RecommendedSong.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<List<DiscoverSectionModel>> discoverSongs(int userId) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/recommendations/discover',
      body: {'user_id': userId},
      parser: (json) => json as Map<String, dynamic>,
    );
    return (data['sections'] as List<dynamic>? ?? [])
        .map((item) => DiscoverSectionModel.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<AddToLibraryResult> addSongToLibrary(int userId, int songId) {
    return _client.post<AddToLibraryResult>(
      '/api/recommendations/add-to-library',
      body: {'user_id': userId, 'song_id': songId},
      parser: (json) => AddToLibraryResult.fromJson(json as Map<String, dynamic>),
    );
  }
}
