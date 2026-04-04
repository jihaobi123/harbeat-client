import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../../core/config/app_config.dart';
import '../../core/models/api_response.dart';
import '../../core/network/api_client.dart';
import '../../core/storage/token_storage.dart';
import 'models.dart';

class LibraryService {
  LibraryService({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  String getStreamUrl(String songId, String token) {
    return _client.buildUrl('/api/stream/$songId', query: {'token': token});
  }

  String getStemStreamUrl(String songId, String stemName, String token) {
    return _client.buildUrl(
      '/api/stream/$songId/stem/$stemName',
      query: {'token': token},
    );
  }

  Map<String, String> buildStemUrls(LibrarySong song, String token) {
    final urls = <String, String>{};
    for (final stem in const ['vocals', 'drums', 'bass', 'other']) {
      if ((song.stems ?? {}).containsKey(stem)) {
        urls[stem] = getStemStreamUrl(song.id, stem, token);
      }
    }
    return urls;
  }

  Future<LibrarySong?> findExactLibrarySong({
    required String title,
    required String artist,
  }) async {
    final results = await searchLibrarySongs(title);
    for (final item in results) {
      if (item.title.trim().toLowerCase() == title.trim().toLowerCase() &&
          item.artist.trim().toLowerCase() == artist.trim().toLowerCase()) {
        return item;
      }
    }
    return null;
  }

  Future<List<LibrarySong>> getLibrarySongs() async {
    final data = await _client.get<Map<String, dynamic>>(
      '/api/library/songs',
      parser: (json) => json as Map<String, dynamic>,
    );
    final songs = data['songs'] as List<dynamic>? ?? [];
    return songs
        .map((item) => LibrarySong.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<LibrarySong> getLibrarySong(String songId) {
    return _client.get<LibrarySong>(
      '/api/library/songs/$songId',
      parser: (json) => LibrarySong.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<List<LibrarySong>> searchLibrarySongs(String query) async {
    final data = await _client.get<Map<String, dynamic>>(
      '/api/library/songs/search',
      query: {'q': query},
      parser: (json) => json as Map<String, dynamic>,
    );
    final songs = data['songs'] as List<dynamic>? ?? [];
    return songs
        .map((item) => LibrarySong.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<LibrarySong> analyzeSong(String songId) {
    return _client.post<LibrarySong>(
      '/api/library/songs/$songId/analyze',
      parser: (json) => LibrarySong.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<Map<String, dynamic>> separateStems(String songId) {
    return _client.post<Map<String, dynamic>>(
      '/api/library/songs/$songId/separate-stems',
      parser: (json) => json as Map<String, dynamic>,
    );
  }

  Future<bool> deleteSong(String songId) async {
    final data = await _client.delete<Map<String, dynamic>>(
      '/api/library/songs/$songId',
      parser: (json) => json as Map<String, dynamic>,
    );
    return data['success'] as bool? ?? false;
  }

  Future<LibrarySong> uploadSong({
    required File file,
    String? title,
    String? artist,
  }) async {
    final token = await TokenStorage.readToken();
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/api/library/upload');
    final request = http.MultipartRequest('POST', uri);

    if (token != null && token.isNotEmpty) {
      request.headers['Authorization'] = 'Bearer $token';
    }
    if (title != null && title.isNotEmpty) request.fields['title'] = title;
    if (artist != null && artist.isNotEmpty) request.fields['artist'] = artist;

    request.files.add(await http.MultipartFile.fromPath('file', file.path));

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    final decoded = ApiResponse<LibrarySong>.fromJson(
      Map<String, dynamic>.from(jsonDecode(response.body) as Map),
      (json) => LibrarySong.fromJson(json as Map<String, dynamic>),
    );

    if (response.statusCode < 200 || response.statusCode >= 300 || decoded.code != 0) {
      throw Exception(decoded.message);
    }

    return decoded.data;
  }
}
