import 'dart:convert';

import 'package:http/http.dart' as http;

import 'live_models.dart';

class EdgeAgentClient {
  EdgeAgentClient({
    required String baseUrl,
    this.edgeToken,
  }) : baseUrl = normalizeBaseUrl(baseUrl);

  final String baseUrl;
  final String? edgeToken;

  static String normalizeBaseUrl(String raw) {
    var s = raw.trim();
    while (s.startsWith('http://http://')) {
      s = s.substring('http://'.length);
    }
    while (s.startsWith('https://https://')) {
      s = s.substring('https://'.length);
    }
    if (!RegExp(r'^[a-zA-Z][a-zA-Z0-9+.-]*://').hasMatch(s)) {
      s = 'http://$s';
    }
    var uri = Uri.parse(s);
    if (!uri.hasPort && uri.host.isNotEmpty) {
      uri = uri.replace(port: 9000);
    }
    return uri.toString().replaceFirst(RegExp(r'/$'), '');
  }

  Uri _uri(String path, [Map<String, String>? queryParameters]) {
    final normalizedPath = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$baseUrl$normalizedPath')
        .replace(queryParameters: queryParameters);
  }

  // ── State ────────────────────────────────────────────────────────

  Future<LivePlaybackState> getState() async {
    try {
      final data = await _request(method: 'GET', path: '/state');
      return LivePlaybackState.fromJson(data);
    } catch (e) {
      return LivePlaybackState(
        playing: false,
        positionSec: 0,
        durationSec: 0,
        error: 'RK unreachable: $e',
      );
    }
  }

  // ── Live Control ─────────────────────────────────────────────────

  Future<LiveOverrideResponse> liveOverride(LiveOverrideRequest req) async {
    final data = await _request(
      method: 'POST',
      path: '/live/override',
      body: req.toJson(),
    );
    return LiveOverrideResponse.fromJson(data);
  }

  Future<LiveIntentResponse> liveIntent(LiveIntentRequest req) async {
    final data = await _request(
      method: 'POST',
      path: '/live/intent',
      body: req.toJson(),
    );
    return LiveIntentResponse.fromJson(data);
  }

  // ── Transport ────────────────────────────────────────────────────

  Future<Map<String, dynamic>> play({String? songId, double? startAtSec}) async {
    final body = <String, dynamic>{};
    if (songId != null) body['song_id'] = songId;
    if (startAtSec != null) body['start_at_sec'] = startAtSec;
    return _request(method: 'POST', path: '/play', body: body);
  }

  Future<Map<String, dynamic>> pause() async {
    return _request(method: 'POST', path: '/pause');
  }

  Future<Map<String, dynamic>> resume() async {
    return _request(method: 'POST', path: '/resume');
  }

  /// 跳到指定秒数。RK edge-agent /seek 不会重新加载文件，比重发 /play 快得多。
  Future<Map<String, dynamic>> seek(double sec) async {
    return _request(method: 'POST', path: '/seek', body: {'sec': sec});
  }

  /// 切到 stem 单轨独奏。stem ∈ {vocals,drums,bass,other}，传 null 取消独奏（恢复完整曲）。
  /// RK edge-agent 在 audio engine 已加载的当前曲上即时切换，不重新加载文件，毫秒级响应。
  Future<Map<String, dynamic>> stemSolo(String? stem) async {
    return _request(method: 'POST', path: '/stem_solo', body: {'stem': stem});
  }

  /// [toSongId] accepts an int (catalog Song.id) or a String (LibrarySong UUID).
  /// RK accepts both via `int | str`; UUID is preferred because the sync
  /// worker caches wavs under `~/cypher/cache/{UUID}/original.wav`.
  /// [tempoRatio] = tempo_A / tempo_B; when within ±6%, RK swaps in a
  /// pre-rendered rubberband-stretched wav so the new track plays at A's BPM.
  /// [stemCurves] is a {prev:{stem:curve}, next:{stem:curve}} dict; when
  /// present and both decks have 4 stems loaded, RK mixes per-stem instead
  /// of single-buffer fade (Phase 3.2).
  Future<Map<String, dynamic>> xfade({
    required Object toSongId,
    double fadeSec = 8.0,
    double toAtSec = 0.0,
    String style = 'blend',
    double? tempoRatio,
    Map<String, dynamic>? stemCurves,
  }) async {
    final body = <String, dynamic>{
      'to_song_id': toSongId,
      'fade_sec': fadeSec,
      'to_at_sec': toAtSec,
      'style': style,
    };
    if (tempoRatio != null) body['tempo_ratio'] = tempoRatio;
    if (stemCurves != null) body['stem_curves'] = stemCurves;
    return _request(method: 'POST', path: '/xfade', body: body);
  }

  /// Phase 2: kick a background rubberband render so a future /xfade with
  /// the same [tempoRatio] doesn't block on it.
  Future<Map<String, dynamic>> prewarmBeatmatch({
    required Object songId,
    required double tempoRatio,
  }) async {
    return _request(method: 'POST', path: '/prewarm_beatmatch', body: {
      'song_id': songId,
      'tempo_ratio': tempoRatio,
    });
  }

  /// Decode wav + 4 stems for [songIds] into audio-engine's in-memory cache
  /// so the next /xfade lands instantly (no 300ms-2s file IO inside deck.load).
  /// Idempotent — songs already in cache are skipped. Best called once per
  /// upcoming song, well before the actual transition window.
  Future<Map<String, dynamic>> prefetch({
    required List<Object> songIds,
  }) async {
    return _request(method: 'POST', path: '/prefetch', body: {
      'song_ids': songIds,
    });
  }

  /// Phase 2.5 — schedule per-beat sample triggers across [startSec, endSec].
  /// Use right before /xfade when the planner flagged the prev or next song
  /// as rhythmically weak. [pattern] ∈ {all, half, backbeat}; [sampleKey] 1-5
  /// (4 = snare_crack is the typical reinforcement pick).
  Future<Map<String, dynamic>> beatReinforce({
    required double startSec,
    required double endSec,
    required List<double> beats,
    int sampleKey = 4,
    double gain = 1.0,
    String pattern = 'all',
  }) async {
    return _request(method: 'POST', path: '/beat_reinforce', body: {
      'start_sec': startSec,
      'end_sec': endSec,
      'beats': beats,
      'sample_key': sampleKey,
      'gain': gain,
      'pattern': pattern,
    });
  }

  Future<Map<String, dynamic>> trigger(int key) async {
    return _request(method: 'POST', path: '/trigger', body: {'key': key});
  }

  // ── Internal ─────────────────────────────────────────────────────

  Future<Map<String, dynamic>> _request({
    required String method,
    required String path,
    Object? body,
    Map<String, String>? queryParameters,
  }) async {
    final headers = <String, String>{
      'Accept': 'application/json',
    };
    if (body != null) {
      headers['Content-Type'] = 'application/json';
    }
    if (edgeToken != null && edgeToken!.isNotEmpty) {
      headers['X-Edge-Token'] = edgeToken!;
    }

    final uri = _uri(path, queryParameters);
    late final http.Response response;

    try {
      switch (method) {
        case 'GET':
          response = await http
              .get(uri, headers: headers)
              .timeout(const Duration(seconds: 5));
          break;
        case 'POST':
          response = await http
              .post(uri, headers: headers, body: jsonEncode(body))
              .timeout(const Duration(seconds: 10));
          break;
        default:
          throw Exception('Unsupported method: $method');
      }
    } catch (e) {
      throw Exception('RK connection failed: $e');
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('RK returned ${response.statusCode}: ${response.body}');
    }

    final payload = jsonDecode(response.body);
    if (payload is! Map<String, dynamic>) {
      throw Exception('RK returned unexpected response format');
    }

    return payload;
  }
}
