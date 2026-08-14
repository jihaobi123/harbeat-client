import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// 与 RK3588 上的 sync-worker（端口 9100）通信的客户端。
/// 负责把曲目从 Jetson 同步到 RK 本地缓存。
class SyncWorkerClient {
  SyncWorkerClient({required this.baseUrl});

  /// e.g. http://192.168.43.7:9100
  final String baseUrl;

  /// 从 rkBaseUrl（形如 "192.168.43.7:9000" 或 "http://host:9000"）
  /// 推导出 sync-worker URL（替换/追加 :9100）。
  static String deriveFromRkBaseUrl(String rkBaseUrl) {
    var s = rkBaseUrl.trim();
    while (s.startsWith('http://http://')) {
      s = s.substring('http://'.length);
    }
    while (s.startsWith('https://https://')) {
      s = s.substring('https://'.length);
    }
    if (!RegExp(r'^[a-zA-Z][a-zA-Z0-9+.-]*://').hasMatch(s)) {
      s = 'http://$s';
    }
    final uri = Uri.parse(s);
    final host = uri.host.isNotEmpty ? uri.host : rkBaseUrl;
    return 'http://$host:9100';
  }

  Uri _u(String path) => Uri.parse('$baseUrl$path');

  /// 触发同步。
  /// [tracks] 每项形如：
  /// `{"song_id": "...", "files": {"original": {"url": "...", "format": "mp3"}}}`
  Future<Map<String, dynamic>> startSync({
    required List<Map<String, dynamic>> tracks,
    String? planId,
    bool audioOnly = false,
    bool priority = false,
    bool waitForCompletion = false,
    Duration? requestTimeout,
    List<Map<String, dynamic>> defaultMixPairs = const <Map<String, dynamic>>[],
  }) async {
    final syncTracks = audioOnly ? _audioOnlyTracks(tracks) : tracks;
    final body = <String, dynamic>{
      'plan_id': planId ?? 'mobile-${DateTime.now().millisecondsSinceEpoch}',
      'tracks': syncTracks,
      if (priority) 'priority': true,
      if (waitForCompletion) 'wait': true,
      if (defaultMixPairs.isNotEmpty) 'default_mix_pairs': defaultMixPairs,
    };
    final resp = await http
        .post(
          _u('/sync'),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(
          requestTimeout ?? Duration(seconds: waitForCompletion ? 11 : 10),
        );
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception('sync-worker /sync ${resp.statusCode}: ${resp.body}');
    }
    final payload = jsonDecode(resp.body) as Map<String, dynamic>;
    if (payload['ok'] == false) {
      throw Exception('sync-worker busy: ${payload['error'] ?? resp.body}');
    }
    return payload;
  }

  Future<SyncStatus> getStatus({
    Duration timeout = const Duration(seconds: 5),
  }) async {
    final resp = await http.get(_u('/status')).timeout(timeout);
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception('sync-worker /status ${resp.statusCode}: ${resp.body}');
    }
    return SyncStatus.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
  }

  /// 询问 sync-worker：某首歌的 original.{mp3,wav,...} 是否已落盘。
  /// 用来在快路径里轮询：文件一存在就立刻让 RK 出声，不用等整个 sync 标 done。
  Future<bool> cacheExists(
    String songId, {
    String kind = 'original',
    String? format,
  }) async {
    try {
      final formatQuery =
          format == null ? '' : '&format=${Uri.encodeQueryComponent(format)}';
      final resp = await http
          .get(
            _u(
              '/cache/check?song_id=${Uri.encodeQueryComponent(songId)}'
              '&kind=${Uri.encodeQueryComponent(kind)}$formatQuery',
            ),
          )
          .timeout(const Duration(seconds: 2));
      if (resp.statusCode != 200) return false;
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return body['exists'] == true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> defaultMixPairExists(String pairId) async {
    if (pairId.trim().isEmpty) return false;
    try {
      final resp = await http
          .get(_u('/cache/check?pair_id=${Uri.encodeQueryComponent(pairId)}'))
          .timeout(const Duration(seconds: 2));
      if (resp.statusCode != 200) return false;
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return body['exists'] == true;
    } catch (_) {
      return false;
    }
  }

  /// Stop a lower-priority sync so a user-triggered fast cut can upload its
  /// render package before the live cut window expires. The worker endpoint is
  /// idempotent: false only means there was nothing running to interrupt.
  Future<bool> cancelSync() async {
    try {
      final resp = await http
          .post(_u('/sync/cancel'))
          .timeout(const Duration(seconds: 2));
      if (resp.statusCode < 200 || resp.statusCode >= 300) return false;
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return body['cancelled'] == true;
    } catch (_) {
      return false;
    }
  }

  /// 健康探测：返回 true 表示 sync-worker 可达。
  Future<Map<String, dynamic>> deleteSongCache(String songId) async {
    final resp = await http
        .delete(_u('/cache/song/${Uri.encodeComponent(songId)}'))
        .timeout(const Duration(seconds: 10));
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception(
        'sync-worker delete cache ${resp.statusCode}: ${resp.body}',
      );
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  Future<bool> ping() async {
    try {
      await getStatus();
      return true;
    } catch (_) {
      return false;
    }
  }

  /// 触发并等待同步完成。
  /// [onProgress] 回调 percent (0..100)。
  /// 内部以 1s 间隔轮询。
  Future<SyncStatus> syncAndWait({
    required List<Map<String, dynamic>> tracks,
    String? planId,
    Duration timeout = const Duration(minutes: 3),
    Duration pollInterval = const Duration(seconds: 1),
    Duration statusRequestTimeout = const Duration(seconds: 5),
    Duration startRequestTimeout = const Duration(seconds: 10),
    bool priority = false,
    bool waitForCompletion = false,
    void Function(SyncStatus status)? onProgress,
    bool audioOnly = false,
    List<Map<String, dynamic>> defaultMixPairs = const <Map<String, dynamic>>[],
  }) async {
    final syncTracks = audioOnly ? _audioOnlyTracks(tracks) : tracks;
    final expectedPlanId =
        planId ?? 'mobile-${DateTime.now().millisecondsSinceEpoch}';
    final deadline = DateTime.now().add(timeout);
    SyncStatus last = SyncStatus.empty();
    Future<SyncStatus?> completedFromCache() async {
      var total = 0;
      for (final track in syncTracks) {
        final songId =
            track['song_id'] ??
            track['library_song_id'] ??
            track['songId'] ??
            track['id'];
        if (songId == null) continue;
        total += 1;
        if (!await cacheExists(songId.toString())) return null;
      }
      for (final pair in defaultMixPairs) {
        final pairId = pair['pair_id'] ?? pair['id'];
        if (pairId == null) continue;
        total += 2;
        if (!await defaultMixPairExists(pairId.toString())) return null;
      }
      return SyncStatus(
        running: false,
        total: total,
        downloaded: total,
        completed: total,
        percent: 100,
        planId: expectedPlanId,
      );
    }

    var started = false;
    while (!started && DateTime.now().isBefore(deadline)) {
      try {
        final startPayload = await startSync(
          tracks: syncTracks,
          planId: expectedPlanId,
          priority: priority,
          waitForCompletion: waitForCompletion,
          requestTimeout: startRequestTimeout,
          defaultMixPairs: defaultMixPairs,
        );
        final startStatus = startPayload['status'];
        if (startStatus is Map) {
          last = SyncStatus.fromJson(Map<String, dynamic>.from(startStatus));
          onProgress?.call(last);
          if (last.matchesPlan(expectedPlanId) && !last.running) {
            if (last.errors.isNotEmpty) {
              throw Exception('sync 失败: ${last.errors.join('; ')}');
            }
            if (!last.completedAll) {
              throw SyncIncompleteException(
                completed: last.completed,
                total: last.total,
              );
            }
            return last;
          }
        }
        started = true;
        final cached = await completedFromCache();
        if (cached != null) {
          onProgress?.call(cached);
          return cached;
        }
      } on Exception catch (e) {
        final msg = e.toString();
        final busy = msg.contains('sync-worker busy');
        final ambiguousStart =
            e is TimeoutException || e is http.ClientException;
        if (!busy && !ambiguousStart) rethrow;

        // A timed-out POST may already have started the RK task. Resolve that
        // ambiguity with the same plan id before submitting another transfer.
        if (ambiguousStart) {
          try {
            last = await getStatus(timeout: statusRequestTimeout);
            onProgress?.call(last);
            if (last.matchesPlan(expectedPlanId)) {
              started = true;
              if (!last.running) {
                if (last.errors.isNotEmpty) {
                  throw Exception('sync failed: ${last.errors.join('; ')}');
                }
                if (!last.completedAll) {
                  throw SyncIncompleteException(
                    completed: last.completed,
                    total: last.total,
                  );
                }
                return last;
              }
              break;
            }
          } on Exception catch (statusError) {
            if (statusError is SyncIncompleteException ||
                statusError.toString().contains('sync failed:')) {
              rethrow;
            }
          }
          final cached = await completedFromCache();
          if (cached != null) {
            onProgress?.call(cached);
            return cached;
          }
          await Future<void>.delayed(pollInterval);
          continue;
        }

        while (DateTime.now().isBefore(deadline)) {
          await Future<void>.delayed(pollInterval);
          try {
            last = await getStatus(timeout: statusRequestTimeout);
            onProgress?.call(last);
            if (!last.running) {
              if (last.matchesPlan(expectedPlanId)) {
                if (last.errors.isNotEmpty) {
                  throw Exception('sync 失败: ${last.errors.join('; ')}');
                }
                if (!last.completedAll) {
                  throw SyncIncompleteException(
                    completed: last.completed,
                    total: last.total,
                  );
                }
                return last;
              }
              break;
            }
          } on Exception catch (pollError) {
            if (pollError is SyncIncompleteException ||
                pollError.toString().contains('sync 失败')) {
              rethrow;
            }
            final cached = await completedFromCache();
            if (cached != null) {
              onProgress?.call(cached);
              return cached;
            }
            // Keep waiting through transient status failures.
          }
        }
      }
    }
    if (!started) throw TimeoutException('sync-worker busy timeout');
    while (DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(pollInterval);
      try {
        last = await getStatus(timeout: statusRequestTimeout);
        onProgress?.call(last);
        if (!last.matchesPlan(expectedPlanId)) {
          continue;
        }
        if (!last.running) {
          if (last.errors.isNotEmpty) {
            throw Exception('sync 失败: ${last.errors.join('; ')}');
          }
          if (!last.completedAll) {
            throw SyncIncompleteException(
              completed: last.completed,
              total: last.total,
            );
          }
          return last;
        }
      } on Exception catch (e) {
        final msg = e.toString();
        if (e is SyncIncompleteException || msg.contains('sync 失败')) {
          rethrow;
        }
        final cached = await completedFromCache();
        if (cached != null) {
          onProgress?.call(cached);
          return cached;
        }
        // Transient poll failure (network hiccup) – keep retrying.
      }
      final cached = await completedFromCache();
      if (cached != null) {
        onProgress?.call(cached);
        return cached;
      }
    }
    throw TimeoutException('sync 超时');
  }

  List<Map<String, dynamic>> _audioOnlyTracks(
    List<Map<String, dynamic>> tracks,
  ) {
    return tracks
        .map((track) {
          final out = Map<String, dynamic>.from(track);
          final files = track['files'];
          final original = files is Map ? files['original'] : null;
          out['files'] = <String, dynamic>{
            if (original is Map)
              'original': Map<String, dynamic>.from(original)
            else if (original != null)
              'original': original,
          };
          final qualityFlags = out['qualityFlags'];
          if (qualityFlags is Map) {
            out['qualityFlags'] = <String, dynamic>{
              ...Map<String, dynamic>.from(qualityFlags),
              'has_stems': false,
              'stem_model': null,
            };
          }
          out['stemStatus'] = 'not_requested';
          return out;
        })
        .toList(growable: false);
  }
}

class SyncIncompleteException implements Exception {
  SyncIncompleteException({required this.completed, required this.total});

  final int completed;
  final int total;

  @override
  String toString() => 'sync incomplete: $completed/$total';
}

class SyncStatus {
  SyncStatus({
    required this.running,
    required this.total,
    required this.downloaded,
    required this.completed,
    required this.percent,
    this.planId,
    this.currentFile,
    this.errors = const [],
  });

  final bool running;
  final int total;
  final int downloaded;
  final int completed;
  final double percent;
  final String? planId;
  final String? currentFile;
  final List<String> errors;

  bool matchesPlan(String? expectedPlanId) =>
      expectedPlanId == null || planId == expectedPlanId;

  bool get completedAll => total == 0 || completed >= total;

  factory SyncStatus.empty() => SyncStatus(
    running: false,
    total: 0,
    downloaded: 0,
    completed: 0,
    percent: 0,
  );

  factory SyncStatus.fromJson(Map<String, dynamic> json) {
    return SyncStatus(
      running: json['running'] as bool? ?? false,
      total: (json['total'] as num?)?.toInt() ?? 0,
      downloaded: (json['downloaded'] as num?)?.toInt() ?? 0,
      completed: (json['completed'] as num?)?.toInt() ?? 0,
      percent: (json['percent'] as num?)?.toDouble() ?? 0,
      planId: json['plan_id']?.toString(),
      currentFile: json['current_file']?.toString(),
      errors:
          (json['errors'] as List<dynamic>? ?? const [])
              .map((e) => e.toString())
              .toList(),
    );
  }
}
