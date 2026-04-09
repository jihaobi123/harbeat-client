import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart';
import 'package:http/http.dart' as http;

import 'models.dart';

class HarBeatApiClient {
  HarBeatApiClient({required String baseUrl}) : baseUrl = _normalizeBaseUrl(baseUrl);

  final String baseUrl;

  static String _normalizeBaseUrl(String raw) => raw.trim().replaceFirst(RegExp(r'/$'), '');

  Uri _uri(String path, [Map<String, String>? queryParameters]) {
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$baseUrl$normalizedPath').replace(queryParameters: queryParameters);
  }

  Future<AuthPayload> login({
    required String username,
    required String password,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/auth/login',
      body: {'username': username, 'password': password},
    );
    return AuthPayload.fromJson(data);
  }

  Future<AuthPayload> register({
    required String username,
    required String password,
    required String danceStyle,
    required String level,
    required String favoriteStyle,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/auth/register',
      body: {
        'username': username,
        'password': password,
        'dance_style': danceStyle,
        'level': level,
        'favorite_style': favoriteStyle,
      },
    );
    return AuthPayload.fromJson(data);
  }

  Future<UserProfile> getMe(String token) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/auth/me',
      token: token,
    );
    return UserProfile.fromJson(data);
  }

  Future<List<LibrarySong>> getLibrarySongs(String token) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/library/songs',
      token: token,
    );
    final songs = (data['songs'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return songs.map(LibrarySong.fromJson).toList();
  }

  Future<List<LibrarySong>> searchLibrarySongs({
    required String token,
    required String query,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/library/songs/search',
      token: token,
      queryParameters: {'q': query},
    );
    final songs = (data['songs'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return songs.map(LibrarySong.fromJson).toList();
  }

  Future<List<PlaylistSummary>> getPlaylists({
    required String token,
    required int userId,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/playlists',
      token: token,
      queryParameters: {'user_id': '$userId'},
    );
    final playlists = (data['playlists'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return playlists.map(PlaylistSummary.fromJson).toList();
  }

  Future<PlaylistDetail> getPlaylistDetail({
    required String token,
    required int playlistId,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/playlists/$playlistId',
      token: token,
    );
    return PlaylistDetail.fromJson(data);
  }

  Future<List<FangpiSong>> searchFangpi({
    required String token,
    required String query,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/fangpi/search',
      token: token,
      body: {'query': query},
    );
    final songs = (data['songs'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return songs.map(FangpiSong.fromJson).toList();
  }

  Future<LibrarySong> downloadFangpi({
    required String token,
    required FangpiSong song,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/fangpi/download',
      token: token,
      body: {
        'music_id': song.id,
        'title': song.title,
        'artist': song.artist,
        'source': song.source ?? 'fangpi',
      },
    );
    return LibrarySong.fromJson(data);
  }

  Future<LibrarySong> analyzeSong({
    required String token,
    required String songId,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/library/songs/$songId/analyze',
      token: token,
    );
    return LibrarySong.fromJson(data);
  }

  Future<List<DiscoverSectionData>> discoverSongs({
    required int userId,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/recommendations/discover',
      body: {'user_id': userId},
    );
    return (data['sections'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(DiscoverSectionData.fromJson)
        .toList();
  }

  Future<void> addSongToLibrary({
    required int userId,
    required int songId,
  }) async {
    await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/recommendations/add-to-library',
      body: {'user_id': userId, 'song_id': songId},
    );
  }

  Future<MusicProfile> getProfile(int userId) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/profiles/$userId',
    );
    return MusicProfile.fromJson(data);
  }

  Future<MusicProfile> generateProfile(int userId) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/profiles/generate',
      body: {'user_id': userId},
    );
    return MusicProfile.fromJson(data);
  }

  Future<int> startSession({
    required int userId,
    required String mode,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/sessions/start',
      body: {'user_id': userId, 'mode': mode},
    );
    return (data['session_id'] as num).toInt();
  }

  Future<void> logSessionEvent({
    required int sessionId,
    required String eventType,
    String? eventValue,
  }) async {
    await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/sessions/event',
      body: {
        'session_id': sessionId,
        'event_type': eventType,
        'event_value': eventValue,
        'timestamp': DateTime.now().toIso8601String(),
      },
    );
  }

  Future<void> endSession(int sessionId) async {
    await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/sessions/end',
      body: {'session_id': sessionId},
    );
  }

  Future<List<PracticeTrack>> generatePracticeList({
    required int userId,
    required int targetDuration,
    String? danceStyle,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/sessions/generate-practice-list',
      body: {
        'user_id': userId,
        'target_duration': targetDuration,
        'dance_style': danceStyle,
      },
    );
    return (data['tracks'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(PracticeTrack.fromJson)
        .toList();
  }

  Future<List<CatalogSong>> getCatalogSongs() async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/music/songs',
    );
    return (data['songs'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(CatalogSong.fromJson)
        .toList();
  }

  Future<List<SongCue>> getCues({
    required int songId,
    required int userId,
  }) async {
    final data = await _request<List<dynamic>>(
      method: 'GET',
      path: '/api/music/songs/$songId/cues',
      queryParameters: {'user_id': '$userId'},
    );
    return data.cast<Map<String, dynamic>>().map(SongCue.fromJson).toList();
  }

  Future<SongCue> createCue({
    required int songId,
    required int userId,
    required String cueType,
    required double startTime,
    double? endTime,
    String? label,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/music/songs/$songId/cues',
      body: {
        'user_id': userId,
        'song_id': songId,
        'cue_type': cueType,
        'start_time': startTime,
        'end_time': endTime,
        'label': label,
      },
    );
    return SongCue.fromJson(data);
  }

  Future<StyleProcessResult> processSongStyle({
    required int songId,
    required List<String> styles,
    String qualityMode = 'balanced',
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/music/songs/$songId/process-style',
      body: {
        'styles': styles,
        'quality_mode': qualityMode,
      },
    );
    return StyleProcessResult.fromJson(data);
  }

  Future<DjMixPlanResult> generateDjMixPlan({
    required String style,
    required int durationMinutes,
    int? playlistId,
    String qualityMode = 'balanced',
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/playlists/generate-dj-mix-plan',
      body: {
        'style': style,
        'duration_minutes': durationMinutes,
        'playlist_id': playlistId,
        'quality_mode': qualityMode,
      },
    );
    return DjMixPlanResult.fromJson(data);
  }

  Future<DjOfflineMixResult> generateDjOfflineMix({
    required String style,
    required int durationMinutes,
    int? playlistId,
    String qualityMode = 'balanced',
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/playlists/generate-dj-offline-mix',
      body: {
        'style': style,
        'duration_minutes': durationMinutes,
        'playlist_id': playlistId,
        'quality_mode': qualityMode,
        'output_format': 'both',
      },
    );
    return DjOfflineMixResult.fromJson(data);
  }

  Future<void> deleteSong({
    required String token,
    required String songId,
  }) async {
    await _request<Map<String, dynamic>>(
      method: 'DELETE',
      path: '/api/library/songs/$songId',
      token: token,
    );
  }

  Future<LibrarySong> uploadSong({
    required String token,
    required File file,
    required String title,
    required String artist,
  }) async {
    final request = MultipartRequest('POST', _uri('/api/library/upload'));
    request.headers['Authorization'] = 'Bearer $token';
    request.fields['title'] = title;
    request.fields['artist'] = artist;
    request.files.add(await MultipartFile.fromPath('file', file.path));
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    if (response.statusCode < 200 || response.statusCode >= 300 || payload['code'] != 0) {
      throw Exception(payload['message']?.toString() ?? '上传失败');
    }
    return LibrarySong.fromJson(payload['data'] as Map<String, dynamic>);
  }

  String streamUrl({
    required String token,
    required String songId,
  }) {
    return '$baseUrl/api/stream/$songId?token=$token';
  }

  String processedStreamUrl({
    required String token,
    required String filePath,
  }) {
    final filename = filePath.split('/').last;
    return '$baseUrl/api/stream/processed/${Uri.encodeComponent(filename)}?token=$token';
  }

  String mixStreamUrl({
    required String token,
    required String filename,
  }) {
    return '$baseUrl/api/stream/mixes/${Uri.encodeComponent(filename)}?token=$token';
  }

  Future<DashboardData> loadDashboard({
    required String token,
    required int userId,
  }) async {
    final profile = await getMe(token);
    final songs = await getLibrarySongs(token);
    final playlists = await getPlaylists(token: token, userId: userId);
    return DashboardData(profile: profile, songs: songs, playlists: playlists);
  }

  Future<T> _request<T>({
    required String method,
    required String path,
    String? token,
    Object? body,
    Map<String, String>? queryParameters,
  }) async {
    final headers = <String, String>{'Accept': 'application/json'};
    if (body != null) {
      headers['Content-Type'] = 'application/json';
    }
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }

    final uri = _uri(path, queryParameters);
    late final http.Response response;

    try {
      switch (method) {
        case 'GET':
          response = await http.get(uri, headers: headers);
          break;
        case 'POST':
          response = await http.post(uri, headers: headers, body: jsonEncode(body));
          break;
        case 'DELETE':
          response = await http.delete(uri, headers: headers);
          break;
        default:
          throw Exception('Unsupported method: $method');
      }
    } catch (error) {
      throw Exception('网络请求失败，请检查服务地址或服务器状态: $error');
    }

    dynamic payload;
    try {
      payload = jsonDecode(response.body);
    } catch (_) {
      throw Exception('服务返回了无法解析的响应');
    }

    if (payload is! Map<String, dynamic>) {
      throw Exception('服务返回格式不正确');
    }

    if (response.statusCode < 200 || response.statusCode >= 300 || payload['code'] != 0) {
      throw Exception(payload['message']?.toString() ?? '请求失败');
    }

    return payload['data'] as T;
  }
}
