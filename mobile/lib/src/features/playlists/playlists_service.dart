import '../../core/network/api_client.dart';
import 'models.dart';

class PlaylistsService {
  PlaylistsService({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<List<PlaylistSummary>> getPlaylists(int userId) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/api/playlists',
      query: {'user_id': '$userId'},
      parser: (json) => json as Map<String, dynamic>,
    );
    return (data['playlists'] as List<dynamic>? ?? [])
        .map((item) => PlaylistSummary.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<PlaylistDetail> getPlaylistDetail(int playlistId) {
    return _client.get<PlaylistDetail>(
      '/api/playlists/$playlistId',
      parser: (json) => PlaylistDetail.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<PlaylistImportResult> importPlaylist({
    required int userId,
    required String playlistName,
    required List<Map<String, dynamic>> songs,
    String sourceType = 'manual',
  }) {
    return _client.post<PlaylistImportResult>(
      '/api/playlists/import',
      body: {
        'user_id': userId,
        'playlist_name': playlistName,
        'source_type': sourceType,
        'songs': songs,
      },
      parser: (json) => PlaylistImportResult.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<bool> deletePlaylist(int playlistId) async {
    final data = await _client.delete<Map<String, dynamic>>(
      '/api/playlists/$playlistId',
      parser: (json) => json as Map<String, dynamic>,
    );
    return data['success'] as bool? ?? false;
  }

  Future<bool> updatePlaylistSongTags(int playlistId, int songId, List<String> tags) async {
    final data = await _client.patch<Map<String, dynamic>>(
      '/api/playlists/$playlistId/songs/$songId/tags',
      body: {'tags': tags},
      parser: (json) => json as Map<String, dynamic>,
    );
    return data['success'] as bool? ?? false;
  }

  Future<bool> reorderPlaylistSongs(
    int playlistId,
    List<PlaylistSong> songs,
  ) async {
    final data = await _client.patch<Map<String, dynamic>>(
      '/api/playlists/$playlistId/reorder',
      body: {
        'songs': songs
            .asMap()
            .entries
            .map(
              (entry) => {
                'song_id': entry.value.songId,
                'order_index': entry.key,
              },
            )
            .toList(),
      },
      parser: (json) => json as Map<String, dynamic>,
    );
    return data['success'] as bool? ?? false;
  }

  Future<Map<String, dynamic>> createPlaylist(String name) {
    return _client.post<Map<String, dynamic>>(
      '/api/playlists/create',
      body: {'name': name},
      parser: (json) => json as Map<String, dynamic>,
    );
  }

  Future<int> addSongsToPlaylist(int playlistId, List<String> librarySongIds) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/playlists/$playlistId/add-songs',
      body: {'library_song_ids': librarySongIds},
      parser: (json) => json as Map<String, dynamic>,
    );
    return data['added'] as int? ?? 0;
  }
}
