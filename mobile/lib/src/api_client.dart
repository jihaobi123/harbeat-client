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

  // ─── Module 2: Playlist Import (Vibe + URL) ───

  Future<VibeSearchResult> vibeSearch({
    String? token,
    required String query,
    int? userId,
    int topK = 12,
  }) async {
    final body = <String, dynamic>{'query': query, 'top_k': topK};
    if (userId != null) body['user_id'] = userId;
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/recommendations/vibe-search',
      token: token,
      body: body,
      // CLAP subprocess 冷启动 + Spotify API + reranker 实测 17-18s，留 60% 余量。
      timeout: const Duration(seconds: 30),
    );
    return VibeSearchResult.fromJson(data);
  }

  Future<Map<String, dynamic>> importFromVibe({
    String? token,
    required int userId,
    required String vibeDescription,
    int topK = 5,
    bool autoImport = true,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/recommendations/import-from-vibe',
      token: token,
      body: {
        'user_id': userId,
        'vibe_description': vibeDescription,
        'top_k': topK,
        'auto_import': autoImport,
      },
      // import 链路含 yt-dlp 下载 + 特征提取 + 入 ChromaDB，比 vibeSearch 还慢，给 30s。
      timeout: const Duration(seconds: 30),
    );
    return data;
  }

  Future<ParsedExternalPlaylist> parseExternalPlaylist({
    required String token,
    required String url,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/fangpi/parse-playlist',
      token: token,
      body: {'url': url},
      // NetEase API can be slow under load; default 15s isn't enough for cold path.
      timeout: const Duration(seconds: 45),
    );
    return ParsedExternalPlaylist.fromJson(data);
  }

  Future<List<BatchSearchEntry>> batchSearchExternal({
    required String token,
    required List<ExternalPlaylistTrack> tracks,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/fangpi/batch-search',
      token: token,
      body: {
        'songs': tracks
            .map((t) => {'title': t.title, 'artist': t.artist})
            .toList(),
      },
      // Backend now runs concurrent (8-way) with 18s per-song cap. Worst case
      // for 30+ song playlists is ~30s; allow plenty of headroom.
      timeout: const Duration(seconds: 90),
    );
    return (data['results'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(BatchSearchEntry.fromJson)
        .toList();
  }

  Future<LibrarySong> downloadFangpiCandidate({
    required String token,
    required FangpiCandidate candidate,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/fangpi/download',
      token: token,
      body: {
        'music_id': candidate.id,
        'title': candidate.title,
        'artist': candidate.artist,
        'source': candidate.source ?? 'fangpi',
      },
      // Single-song download fetches audio + writes file; can run 30-60s.
      timeout: const Duration(seconds: 90),
    );
    return LibrarySong.fromJson(data);
  }

  Future<LibrarySong> getLibrarySong({
    required String token,
    required String songId,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/library/songs/$songId',
      token: token,
    );
    return LibrarySong.fromJson(data);
  }

  Future<int> createPlaylist({
    required String token,
    required String name,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/playlists/create',
      token: token,
      body: {'name': name},
    );
    return (data['id'] as num).toInt();
  }

  Future<int> addSongsToPlaylist({
    required String token,
    required int playlistId,
    required List<String> librarySongIds,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/playlists/$playlistId/add-songs',
      token: token,
      body: {'library_song_ids': librarySongIds},
    );
    return (data['added'] as num?)?.toInt() ?? 0;
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

  Future<Map<String, dynamic>> getSongManifest({
    required String token,
    required String songId,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/manifest/song/$songId',
      token: token,
    );
    return Map<String, dynamic>.from(data['manifest'] as Map);
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

  String stemStreamUrl({
    required String token,
    required String songId,
    required String stemName,
  }) {
    return '$baseUrl/api/stream/$songId/stem/$stemName?token=$token';
  }

  Future<Map<String, dynamic>> separateStems({
    required String token,
    required String songId,
  }) async {
    return _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/library/songs/$songId/separate-stems',
      token: token,
    );
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
    // 并发三段而不是串行，单段 stall 不会拖累整体；HarBeatApiClient._request
    // 自带 1 次重试覆盖偶发链路抖动。
    final results = await Future.wait([
      getMe(token),
      getLibrarySongs(token),
      getPlaylists(token: token, userId: userId),
    ]);
    return DashboardData(
      profile: results[0] as UserProfile,
      songs: results[1] as List<LibrarySong>,
      playlists: results[2] as List<PlaylistSummary>,
    );
  }

  Future<T> _request<T>({
    required String method,
    required String path,
    String? token,
    Object? body,
    Map<String, String>? queryParameters,
    Duration? timeout,
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
    final reqTimeout = timeout ?? const Duration(seconds: 15);

    try {
      switch (method) {
        case 'GET':
          response = await http.get(uri, headers: headers).timeout(reqTimeout);
          break;
        case 'POST':
          response = await http
              .post(uri, headers: headers, body: jsonEncode(body))
              .timeout(reqTimeout);
          break;
        case 'DELETE':
          response = await http.delete(uri, headers: headers).timeout(reqTimeout);
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

  // ---------------- DJ Control ----------------
  Future<List<Map<String, dynamic>>> djListStyles({required String token}) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET', path: '/api/dj/styles', token: token,
    );
    return (data['styles'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> djPickByStyle({
    required String token,
    required String style,
    required double targetDurationSec,
    double minScore = 0.35,
  }) async {
    return await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/dj/styles/pick',
      token: token,
      body: {
        'style': style,
        'target_duration_sec': targetDurationSec,
        'min_score': minScore,
      },
    );
  }

  Future<List<String>> djSequencePresets({required String token}) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET', path: '/api/dj/sequence/presets', token: token,
    );
    return (data['presets'] as List<dynamic>? ?? const []).cast<String>();
  }

  /// Returns [{key, label_zh, desc_zh, scene}, ...] when backend supplies meta.
  Future<List<Map<String, dynamic>>> djSequencePresetsMeta({required String token}) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET', path: '/api/dj/sequence/presets', token: token,
    );
    final meta = data['meta'];
    if (meta is List) return meta.cast<Map<String, dynamic>>();
    return (data['presets'] as List<dynamic>? ?? const [])
        .cast<String>()
        .map((k) => <String, dynamic>{'key': k, 'label_zh': k, 'desc_zh': '', 'scene': 'generic'})
        .toList();
  }

  /// Live cut planning. Returns plan map: {chosen_song_id, switch_at_sec, ...}.
  Future<Map<String, dynamic>> djPlanCut({
    required String token,
    required String strategy,
    required String currentSongId,
    required double cursorSec,
    required List<String> queueSongIds,
    required int currentIndex,
    required List<String> poolSongIds,
    double maxWaitSec = 5.0,
  }) async {
    return await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/dj/cut/plan',
      token: token,
      body: {
        'strategy': strategy,
        'current_song_id': currentSongId,
        'cursor_sec': cursorSec,
        'queue_song_ids': queueSongIds,
        'current_index': currentIndex,
        'pool_song_ids': poolSongIds,
        'max_wait_sec': maxWaitSec,
      },
    );
  }

  Future<List<Map<String, dynamic>>> djSequence({
    required String token,
    required List<String> songIds,
    required String preset,
  }) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/dj/sequence',
      token: token,
      body: {'song_ids': songIds, 'preset': preset},
    );
    return (data['sequence'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();
  }

  /// Auto-generate up to N candidate DJ sets from the picked songs.
  /// Each set is a full {tracks, narrative_arc, energy_curve, transitions,
  /// purposes, plans, quality, score, adjusted_score, template, set_id}.
  /// User picks one of the returned sets — no manual preset choice needed.
  Future<Map<String, dynamic>> djSetGenerate({
    required String token,
    required List<String> songIds,
    List<String>? templateNames,
    bool dropFailed = false,
  }) async {
    return await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/dj/set/generate',
      token: token,
      body: {
        'song_ids': songIds,
        if (templateNames != null) 'template_names': templateNames,
        'drop_failed': dropFailed,
      },
      // Pipeline does pairwise edge analysis + beam search across 5 templates;
      // for 30 songs this can take 20-40s on Jetson.
      timeout: const Duration(seconds: 90),
    );
  }

  /// 5-bucket schema for energy chips/colors (cold/warm/mid/high/peak).
  /// Returns [{key, label_zh, color, lo, hi}, ...].
  Future<List<Map<String, dynamic>>> djListEnergyBuckets({required String token}) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET', path: '/api/dj/energy/buckets', token: token,
    );
    return (data['buckets'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();
  }

  /// v2 street-dance energy for a single song. Pass a `style` key from
  /// {breaking, hiphop, popping, locking, house, krump, waacking, generic}
  /// to get style-aware ranking; omit it for v1 legacy parity.
  /// Returns the StreetEnergy as a map (total/bucket/bucket_color/factors/...).
  Future<Map<String, dynamic>> djSongEnergyV2({
    required String token,
    required String songId,
    String? style,
  }) async {
    final qs = (style != null && style.isNotEmpty) ? '?style=$style' : '';
    return await _request<Map<String, dynamic>>(
      method: 'GET',
      path: '/api/dj/songs/$songId/energy$qs',
      token: token,
    );
  }

  Future<Map<String, dynamic>> djListTransitionRules({required String token}) async {
    return await _request<Map<String, dynamic>>(
      method: 'GET', path: '/api/dj/transitions/rules', token: token,
    );
  }

  Future<List<Map<String, dynamic>>> djListFx({required String token}) async {
    final data = await _request<Map<String, dynamic>>(
      method: 'GET', path: '/api/dj/fx', token: token,
    );
    return (data['fx'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();
  }

  String djFxAudioUrl(String key, {double? duration}) {
    final q = duration != null ? '?duration=$duration' : '';
    return '$baseUrl/api/dj/fx/$key.wav$q';
  }

  /// Vibe search: free-form text description → ranked songs.
  /// When [fillDuration] is true, server greedily fills to [targetDurationSec].
  Future<Map<String, dynamic>> djVibeSearch({
    required String token,
    required String query,
    double? targetDurationSec,
    bool fillDuration = false,
    int limit = 50,
  }) async {
    return await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/dj/vibe/search',
      token: token,
      body: {
        'query': query,
        if (targetDurationSec != null) 'target_duration_sec': targetDurationSec,
        'fill_duration': fillDuration,
        'limit': limit,
      },
    );
  }

  /// Build a transition spec between two songs: {rule_key, fade_sec, ...}.
  Future<Map<String, dynamic>> djPlanTransition({
    required String token,
    required String prevSongId,
    required String nextSongId,
    required double cursorSec,
    String? ruleKey,
  }) async {
    return await _request<Map<String, dynamic>>(
      method: 'POST',
      path: '/api/dj/transitions/plan',
      token: token,
      body: {
        'prev_song_id': prevSongId,
        'next_song_id': nextSongId,
        'cursor_sec': cursorSec,
        if (ruleKey != null) 'rule_key': ruleKey,
      },
    );
  }
}
