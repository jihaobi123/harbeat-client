import '../../core/network/api_client.dart';
import '../library/models.dart';
import 'models.dart';

class FangpiService {
  FangpiService({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<List<FangpiSong>> search(String query) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/fangpi/search',
      body: {'query': query},
      parser: (json) => json as Map<String, dynamic>,
    );
    return (data['songs'] as List<dynamic>? ?? [])
        .map((item) => FangpiSong.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<LibrarySong> download(Map<String, dynamic> payload) {
    return _client.post<LibrarySong>(
      '/api/fangpi/download',
      body: payload,
      parser: (json) => LibrarySong.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<ParsedPlaylist> parsePlaylistUrl(String url) {
    return _client.post<ParsedPlaylist>(
      '/api/fangpi/parse-playlist',
      body: {'url': url},
      parser: (json) => ParsedPlaylist.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<List<BatchSearchResultItem>> batchSearch(List<Map<String, String>> songs) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/fangpi/batch-search',
      body: {'songs': songs},
      parser: (json) => json as Map<String, dynamic>,
    );
    return (data['results'] as List<dynamic>? ?? [])
        .map((item) => BatchSearchResultItem.fromJson(item as Map<String, dynamic>))
        .toList();
  }
}
