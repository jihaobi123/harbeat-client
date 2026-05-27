import 'dart:convert';

import 'package:http/http.dart' as http;

import 'live_models.dart';

class EdgeAgentClient {
  EdgeAgentClient({
    required this.baseUrl,
    this.edgeToken,
  });

  final String baseUrl;
  final String? edgeToken;

  static String normalizeBaseUrl(String raw) =>
      raw.trim().replaceFirst(RegExp(r'/$'), '');

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

  /// [toSongId] accepts an int (catalog Song.id) or a String (LibrarySong UUID).
  /// RK accepts both via `int | str`; UUID is preferred because the sync
  /// worker caches wavs under `~/cypher/cache/{UUID}/original.wav`.
  Future<Map<String, dynamic>> xfade({
    required Object toSongId,
    double fadeSec = 8.0,
    double toAtSec = 0.0,
    String style = 'blend',
  }) async {
    return _request(method: 'POST', path: '/xfade', body: {
      'to_song_id': toSongId,
      'fade_sec': fadeSec,
      'to_at_sec': toAtSec,
      'style': style,
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
