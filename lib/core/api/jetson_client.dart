import 'dart:convert';
import 'package:dio/dio.dart';
import '../utils/logger.dart';

class JetsonClient {
  late final Dio _dio;
  String? _token;
  bool _mockMode = false;

  JetsonClient({String? baseUrl, Duration? timeout}) {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl ?? 'http://8.136.120.255',
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
  
  void setMockMode(bool enabled) {
    _mockMode = enabled;
  }

  void setToken(String token) {
    _token = token;
  }

  void clearToken() {
    _token = null;
  }

  // 模拟歌曲数据
  final List<Map<String, dynamic>> _mockSongs = [
    {
      'song_id': 'song-001',
      'title': 'Hip Hop Anthem',
      'artist': 'DJ Master',
      'duration_sec': 185.5,
      'bpm': 120.0,
      'analysis_status': 'ready',
      'has_stems': true,
    },
    {
      'song_id': 'song-002',
      'title': 'Urban Beats',
      'artist': 'Beat Producer',
      'duration_sec': 210.0,
      'bpm': 105.0,
      'analysis_status': 'ready',
      'has_stems': true,
    },
    {
      'song_id': 'song-003',
      'title': 'Street Sounds',
      'artist': 'Rhyme King',
      'duration_sec': 195.0,
      'bpm': 115.0,
      'analysis_status': 'ready',
      'has_stems': true,
    },
    {
      'song_id': 'song-004',
      'title': 'Night Groove',
      'artist': 'Base Line',
      'duration_sec': 225.0,
      'bpm': 95.0,
      'analysis_status': 'ready',
      'has_stems': true,
    },
    {
      'song_id': 'song-005',
      'title': 'City Vibe',
      'artist': 'Smooth Player',
      'duration_sec': 178.0,
      'bpm': 110.0,
      'analysis_status': 'ready',
      'has_stems': true,
    },
  ];

  // 模拟歌单数据
  final List<Map<String, dynamic>> _mockPlaylists = [
    {
      'playlist_id': 1,
      'name': 'Hip Hop Mix',
      'songs': [],
    },
    {
      'playlist_id': 2,
      'name': 'Dance Party',
      'songs': [],
    },
  ];

  Future<Map<String, dynamic>> login(String username, String password) async {
    if (_mockMode) {
      await Future.delayed(const Duration(milliseconds: 500));
      return {
        'access_token': 'mock-token-${DateTime.now().millisecondsSinceEpoch}',
        'user_id': 1,
        'username': username,
      };
    }
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
    if (_mockMode) {
      await Future.delayed(const Duration(milliseconds: 300));
      var filteredSongs = _mockSongs;
      if (query != null && query.isNotEmpty) {
        filteredSongs = _mockSongs
            .where((song) =>
                song['title'].toLowerCase().contains(query.toLowerCase()) ||
                song['artist'].toLowerCase().contains(query.toLowerCase()))
            .toList();
      }
      return {'data': filteredSongs};
    }
    final response = await _dio.get('/api/library/songs', queryParameters: {
      'only_ready': onlyReady,
      if (query != null && query.isNotEmpty) 'q': query,
    });
    return _unwrapResponse(response);
  }

  Future<Map<String, dynamic>> getSongStatus(String songId) async {
    if (_mockMode) {
      await Future.delayed(const Duration(milliseconds: 300));
      final song = _mockSongs.firstWhere((s) => s['song_id'] == songId);
      return {'data': song};
    }
    final response = await _dio.get('/api/library/songs/$songId');
    return _unwrapResponse(response);
  }

  Future<Map<String, dynamic>> uploadSong(String filePath) async {
    if (_mockMode) {
      await Future.delayed(const Duration(milliseconds: 500));
      final newSongId = 'song-${DateTime.now().millisecondsSinceEpoch}';
      final newSong = {
        'song_id': newSongId,
        'title': 'New Song',
        'artist': 'Unknown',
        'duration_sec': 180.0,
        'bpm': 120.0,
        'analysis_status': 'analyzing',
        'has_stems': false,
      };
      _mockSongs.add(newSong);
      return {'data': newSong};
    }
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(filePath),
    });
    final response = await _dio.post('/api/library/upload', data: formData);
    return _unwrapResponse(response);
  }

  Future<List<Map<String, dynamic>>> getPlaylists() async {
    if (_mockMode) {
      await Future.delayed(const Duration(milliseconds: 300));
      // 为模拟歌单添加一些歌曲
      _mockPlaylists[0]['songs'] = _mockSongs.take(3).toList();
      _mockPlaylists[1]['songs'] = _mockSongs.skip(2).toList();
      return _mockPlaylists;
    }
    final response = await _dio.get('/api/playlists');
    final data = _unwrapResponse(response);
    return List<Map<String, dynamic>>.from(data['playlists'] ?? []);
  }

  Future<Map<String, dynamic>> createPlaylist(String name) async {
    if (_mockMode) {
      await Future.delayed(const Duration(milliseconds: 300));
      final newPlaylist = {
        'playlist_id': _mockPlaylists.length + 1,
        'name': name,
        'songs': [],
      };
      _mockPlaylists.add(newPlaylist);
      return {'data': newPlaylist};
    }
    final response = await _dio.post('/api/playlists/create-empty', data: {
      'name': name,
    });
    return _unwrapResponse(response);
  }

  Future<Map<String, dynamic>> addSongsToPlaylist(
    int playlistId,
    List<String> librarySongIds,
  ) async {
    if (_mockMode) {
      await Future.delayed(const Duration(milliseconds: 300));
      final playlist = _mockPlaylists.firstWhere(
        (p) => p['playlist_id'] == playlistId,
      );
      final songsToAdd = _mockSongs
          .where((s) => librarySongIds.contains(s['song_id']))
          .toList();
      playlist['songs'] = (playlist['songs'] as List)..addAll(songsToAdd);
      return {'data': playlist};
    }
    final response = await _dio.post(
      '/api/playlists/$playlistId/add-library-songs',
      data: {'library_song_ids': librarySongIds},
    );
    return _unwrapResponse(response);
  }

  Stream<Map<String, dynamic>> streamMixPlan(int playlistId) async* {
    if (_mockMode) {
      await Future.delayed(const Duration(milliseconds: 500));
      yield {'event': 'plan_started', 'playlist_id': playlistId, 'cache_hit': true};
      
      await Future.delayed(const Duration(milliseconds: 1000));
      final playlistSongs = _mockPlaylists.firstWhere(
        (p) => p['playlist_id'] == playlistId,
        orElse: () => {'songs': _mockSongs},
      )['songs'] as List;
      
      final tracks = List.generate(playlistSongs.length, (i) => {
        'song_id': playlistSongs[i]['song_id'],
        'order': i,
        'start_at_sec': 0.0,
        'play_duration_sec': playlistSongs[i]['duration_sec'] ?? 180.0,
      });
      
      final transitions = List.generate(
        playlistSongs.length - 1,
        (i) => {
          'from_song': playlistSongs[i]['song_id'],
          'to_song': playlistSongs[i + 1]['song_id'],
          'from_at_sec': (playlistSongs[i]['duration_sec'] ?? 180.0) - 30.0,
          'to_at_sec': 0.0,
          'fade_sec': 8.0,
          'fade_curve': 'equal_power',
        },
      );
      
      yield {
        'event': 'plan_final',
        'playlist_id': playlistId,
        'result': {
          'plan_id': 'mock-plan-${DateTime.now().millisecondsSinceEpoch}',
          'playlist_id': playlistId,
          'generated_at': DateTime.now().toIso8601String(),
          'tracks': tracks,
          'transitions': transitions,
        },
      };
      return;
    }

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
    if (_mockMode) {
      await Future.delayed(const Duration(milliseconds: 500));
      final playlistSongs = _mockPlaylists.firstWhere(
        (p) => p['playlist_id'] == playlistId,
        orElse: () => _mockPlaylists[0],
      )['songs'] as List;
      
      return {
        'data': {
          'plan_id': planId ?? 'mock-plan-$playlistId',
          'playlist_id': playlistId,
          'tracks': playlistSongs.asMap().entries.map((entry) {
            final index = entry.key;
            final song = entry.value;
            return {
              'song_id': index + 1,
              'library_song_id': song['song_id'],
              'title': song['title'],
              'artist': song['artist'],
              'duration_sec': song['duration_sec'],
              'bpm': song['bpm'],
              'key': 'A',
              'files': {
                'original': {
                  'url': '/api/stream/${song['song_id']}',
                  'size': 5000000,
                  'sha256': 'mock-sha256-${song['song_id']}',
                  'format': 'mp3',
                },
                'stems': {
                  'vocals': {
                    'url': '/api/stream/${song['song_id']}/stem/vocals',
                    'size': 1000000,
                    'sha256': 'mock-stem-vocals-${song['song_id']}',
                  },
                  'drums': {
                    'url': '/api/stream/${song['song_id']}/stem/drums',
                    'size': 800000,
                    'sha256': 'mock-stem-drums-${song['song_id']}',
                  },
                  'bass': {
                    'url': '/api/stream/${song['song_id']}/stem/bass',
                    'size': 600000,
                    'sha256': 'mock-stem-bass-${song['song_id']}',
                  },
                  'other': {
                    'url': '/api/stream/${song['song_id']}/stem/other',
                    'size': 700000,
                    'sha256': 'mock-stem-other-${song['song_id']}',
                  },
                },
              },
            };
          }).toList(),
        },
      };
    }
    
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
    await _dio.post('/api/sessions/rk/$sessionId/events', data: {
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
