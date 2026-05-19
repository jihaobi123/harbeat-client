import 'dart:convert';
import 'package:dio/dio.dart';
import '../utils/logger.dart';

class JetsonClient {
  late final Dio _dio;
  String? _token;

  JetsonClient({String? baseUrl, Duration? timeout}) {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl ?? 'http://100.87.142.21:8000',
      connectTimeout: timeout ?? const Duration(seconds: 3),
      receiveTimeout: const Duration(seconds: 30),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    ));

    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        AppLogger.info('📤 Jetson Request: ${options.method} ${options.uri}');
        if (_token != null) {
          options.headers['Authorization'] = 'Bearer $_token';
        }
        return handler.next(options);
      },
      onError: (error, handler) {
        AppLogger.error('❌ Jetson Error: ${error.message}', error: error);
        return handler.next(error);
      },
    ));
  }

  void setToken(String token) {
    _token = token;
  }

  void clearToken() {
    _token = null;
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    final response = await _dio.post('/api/users/login', data: {
      'username': username,
      'password': password,
    });
    return _unwrapResponse(response);
  }

  Future<Map<String, dynamic>> getLibrarySongs({
    bool onlyReady = true,
    String? query,
  }) async {
    final response = await _dio.get('/api/library/songs', queryParameters: {
      'only_ready': onlyReady,
      if (query != null && query.isNotEmpty) 'q': query,
    });
    return _unwrapResponse(response);
  }

  Future<Map<String, dynamic>> getSongStatus(String songId) async {
    final response = await _dio.get('/api/library/songs/$songId/status');
    return _unwrapResponse(response);
  }

  Future<Map<String, dynamic>> uploadSong(String filePath) async {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(filePath),
    });
    final response = await _dio.post('/api/library/songs/upload', data: formData);
    return _unwrapResponse(response);
  }

  Future<List<Map<String, dynamic>>> getPlaylists() async {
    final response = await _dio.get('/api/playlists');
    final data = _unwrapResponse(response);
    return List<Map<String, dynamic>>.from(data['playlists'] ?? []);
  }

  Future<Map<String, dynamic>> createPlaylist(String name) async {
    final response = await _dio.post('/api/playlists/create-empty', data: {
      'name': name,
    });
    return _unwrapResponse(response);
  }

  Future<Map<String, dynamic>> addSongsToPlaylist(
    int playlistId,
    List<String> librarySongIds,
  ) async {
    final response = await _dio.post(
      '/api/playlists/$playlistId/add-library-songs',
      data: {'library_song_ids': librarySongIds},
    );
    return _unwrapResponse(response);
  }

  Stream<Map<String, dynamic>> streamMixPlan(int playlistId) async* {
    final response = await _dio.post(
      '/api/playlists/$playlistId/dj-mix-stream',
      options: Options(responseType: ResponseType.stream),
    );

    String buffer = '';
    await for (final chunk in response.data.stream) {
      buffer += String.fromCharCodes(chunk);
      final lines = buffer.split('\n\n');
      buffer = lines.last;

      for (int i = 0; i < lines.length - 1; i++) {
        final line = lines[i];
        if (line.startsWith('event:') || line.startsWith('data:')) {
          final parts = line.split('\n');
          if (parts.length >= 2 && parts[1].startsWith('data:')) {
            final jsonStr = parts[1].substring(5).trim();
            if (jsonStr.isNotEmpty) {
              try {
                final data = jsonDecode(jsonStr);
                yield data;
              } catch (e) {
                AppLogger.error('SSE解析失败: $e');
              }
            }
          }
        }
      }
    }
  }

  Future<Map<String, dynamic>> getManifest(int playlistId, {String? planId}) async {
    final response = await _dio.get(
      '/api/playlists/$playlistId/manifest',
      queryParameters: planId != null ? {'plan_id': planId} : null,
    );
    return _unwrapResponse(response);
  }

  Future<Map<String, dynamic>> getSessionEvents(String sessionId) async {
    final response = await _dio.get('/api/sessions/$sessionId/events');
    return _unwrapResponse(response);
  }

  Future<void> uploadSessionEvents(
    String sessionId,
    List<Map<String, dynamic>> events,
  ) async {
    await _dio.post('/api/sessions/event', data: {
      'session_id': sessionId,
      'events': events,
    });
  }

  Future<Map<String, dynamic>> register(String username, String password) async {
    final response = await _dio.post('/api/users/register', data: {
      'username': username,
      'password': password,
    });
    return _unwrapResponse(response);
  }

  Future<Map<String, dynamic>> getCurrentUser() async {
    final response = await _dio.get('/api/users/me');
    return _unwrapResponse(response);
  }

  Map<String, dynamic> _unwrapResponse(Response response) {
    if (response.data is Map<String, dynamic>) {
      return response.data;
    }
    return {'data': response.data};
  }
}
