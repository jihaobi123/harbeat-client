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
  }) async {
    final body = <String, dynamic>{
      'plan_id': planId ?? 'mobile-${DateTime.now().millisecondsSinceEpoch}',
      'tracks': tracks,
    };
    final resp = await http
        .post(
          _u('/sync'),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 10));
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception('sync-worker /sync ${resp.statusCode}: ${resp.body}');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  Future<SyncStatus> getStatus() async {
    final resp =
        await http.get(_u('/status')).timeout(const Duration(seconds: 5));
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception('sync-worker /status ${resp.statusCode}: ${resp.body}');
    }
    return SyncStatus.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
  }

  /// 询问 sync-worker：某首歌的 original.{mp3,wav,...} 是否已落盘。
  /// 用来在快路径里轮询：文件一存在就立刻让 RK 出声，不用等整个 sync 标 done。
  Future<bool> cacheExists(String songId) async {
    try {
      final resp = await http
          .get(_u('/cache/check?song_id=${Uri.encodeQueryComponent(songId)}'))
          .timeout(const Duration(seconds: 2));
      if (resp.statusCode != 200) return false;
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      return body['exists'] == true;
    } catch (_) {
      return false;
    }
  }

  /// 健康探测：返回 true 表示 sync-worker 可达。
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
    void Function(SyncStatus status)? onProgress,
  }) async {
    await startSync(tracks: tracks, planId: planId);
    final deadline = DateTime.now().add(timeout);
    SyncStatus last = SyncStatus.empty();
    while (DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(pollInterval);
      try {
        last = await getStatus();
        onProgress?.call(last);
        if (!last.running) {
          if (last.errors.isNotEmpty) {
            throw Exception('sync 失败: ${last.errors.join('; ')}');
          }
          return last;
        }
      } on Exception catch (e) {
        final msg = e.toString();
        if (msg.contains('sync 失败')) rethrow;
        // Transient poll failure (network hiccup) — keep retrying.
      }
    }
    throw TimeoutException('sync 超时');
  }
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
      errors: (json['errors'] as List<dynamic>? ?? const [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}
