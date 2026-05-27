import 'dart:async';
import 'package:dio/dio.dart';
import '../../core/api/jetson_client.dart';
import '../../core/utils/logger.dart';

/// 一站式：把 Jetson 上的歌缓存到 RK3588 边缘节点 (sync-worker @ :9100)
///
/// 流水线：
/// 1) 在 Jetson 上创建临时 playlist
/// 2) 把指定的 library_song_ids 加入 playlist
/// 3) 拉取 playlist 的 AssetManifest（含 url + sha256 + size）
/// 4) POST 给 RK3588 sync-worker /sync 触发下载
/// 5) 轮询 /status 报告进度
class RkSyncService {
  final JetsonClient _jetson;
  late Dio _rkDio;
  String _rkBaseUrl;

  RkSyncService({
    required JetsonClient jetson,
    String rkBaseUrl = 'http://192.168.43.7:9100',
  })  : _jetson = jetson,
        _rkBaseUrl = rkBaseUrl {
    _rkDio = Dio(BaseOptions(
      baseUrl: _rkBaseUrl,
      connectTimeout: const Duration(seconds: 5),
      // sync-worker /status 在并发下载大 stem 时偶尔 >15s，给到 60s 避免误判。
      receiveTimeout: const Duration(seconds: 60),
      sendTimeout: const Duration(seconds: 60),
    ));
  }

  String get rkBaseUrl => _rkBaseUrl;

  void setRkBaseUrl(String url) {
    _rkBaseUrl = url;
    _rkDio.options.baseUrl = url;
  }

  // 本进程内记录已同步过的 library_song_id，避免 /xfade 每次都重走
  // Jetson 创 playlist + manifest + /sync + 800ms /status 轮询这一整套。
  // RK 重启后 App 不会自动同步后台状态；重装 App 会清零。
  final Set<String> _synced = <String>{};

  bool isSynced(String songId) => _synced.contains(songId);

  void markSynced(Iterable<String> songIds) {
    _synced.addAll(songIds);
  }

  void clearSyncedCache() {
    _synced.clear();
  }

  /// 仅查询 RK3588 sync-worker 当前状态
  Future<Map<String, dynamic>> getStatus() async {
    final resp = await _rkDio.get('/status');
    return Map<String, dynamic>.from(resp.data as Map);
  }

  /// 已经有 manifest 时，直接触发同步
  Future<Map<String, dynamic>> startSync(Map<String, dynamic> manifest) async {
    final resp = await _rkDio.post('/sync', data: manifest);
    return Map<String, dynamic>.from(resp.data as Map);
  }

  /// 端到端：把指定的 library_song_ids 缓存到 RK3588。
  /// 返回一个进度 Stream（百分比 0~100），最后一帧 `{'done': true, 'errors': [...]}`。
  Stream<Map<String, dynamic>> cacheSongs({
    required List<String> librarySongIds,
    String playlistName = 'auto-cache',
  }) async* {
    if (librarySongIds.isEmpty) {
      yield {'done': true, 'errors': <String>[], 'percent': 100.0};
      return;
    }

    try {
      yield {'stage': 'create_playlist', 'percent': 0.0};
      final created = await _jetson.createPlaylist(
        '$playlistName-${DateTime.now().millisecondsSinceEpoch}',
      );
      final createdData = _asMap(created['data']) ?? created;
      final playlistId = (createdData['id'] ?? createdData['playlist_id']) as int;
      AppLogger.info('Created temp playlist $playlistId');

      yield {'stage': 'add_songs', 'percent': 5.0, 'playlist_id': playlistId};
      try {
        await _jetson.addSongsToPlaylist(playlistId, librarySongIds);
      } on DioException catch (e) {
        // 部分歌曲在 Jetson library 不存在 / 重复 → 后端返回 409。
        // 不中断整条流水线：用 manifest 里实际命中的曲目继续同步。
        final code = e.response?.statusCode;
        final body = e.response?.data;
        AppLogger.warning('add-library-songs $code: $body — 继续走 manifest');
        yield {
          'stage': 'add_songs_partial',
          'percent': 8.0,
          'note': 'add-songs $code',
        };
      }

      yield {'stage': 'manifest', 'percent': 10.0};
      Map<String, dynamic> manifest;
      try {
        final manifestResp = await _jetson.getManifest(playlistId);
        manifest = _asMap(manifestResp['data']) ?? manifestResp;
      } on DioException catch (e) {
        // 409 = 整个 playlist 都没有可播曲目（后端 detail.skipped 列出原因）。
        // 注意：后端现在对"只缺 stems"的情况会成功返回 manifest（仅含 original），
        // 只有当 song 完全没有源文件 / library 缺失时才会 409 整条拒绝。
        if (e.response?.statusCode == 409) {
          final body = e.response?.data;
          final detail = body is Map ? body['detail'] : null;
          final skipped =
              (detail is Map ? (detail['skipped'] ?? detail['tracks']) : null)
                  as List?;
          final names = (skipped ?? const [])
              .map((t) {
                final m = t is Map ? t : const {};
                final title = m['title'] ?? m['song_id'] ?? '?';
                final reason = m['reason'] ?? m['status'] ?? '?';
                return '$title($reason)';
              })
              .join('、');
          AppLogger.warning('manifest 409: 无可播曲目 -> $names');
          yield {
            'done': true,
            'errors': <String>[
              if (names.isEmpty)
                'Jetson 拒绝生成 manifest (409)：当前 playlist 没有任何可播曲目'
              else
                'Jetson 拒绝生成 manifest (409)：没有可播曲目，原因：$names',
            ],
            'percent': 0.0,
            'manifest_not_ready': skipped,
          };
          return;
        }
        rethrow;
      }
      final tracks = (manifest['tracks'] as List?) ?? const [];
      final manifestSkipped = (manifest['skipped'] as List?) ?? const [];
      AppLogger.info(
        'Got manifest with ${tracks.length} tracks, ${manifestSkipped.length} skipped',
      );
      if (manifestSkipped.isNotEmpty) {
        final names = manifestSkipped
            .map((t) {
              final m = t is Map ? t : const {};
              final title = m['title'] ?? m['song_id'] ?? '?';
              final reason = m['reason'] ?? m['status'] ?? '?';
              return '$title($reason)';
            })
            .join('、');
        AppLogger.warning('manifest 跳过 ${manifestSkipped.length} 首：$names');
      }
      if (tracks.isEmpty) {
        yield {
          'done': true,
          'errors': <String>[
            '空 manifest：Jetson library 中没有这些 library_song_id（或都已 409 拒绝）',
          ],
          'percent': 0.0,
        };
        return;
      }

      yield {'stage': 'start_sync', 'percent': 15.0};
      final start = await startSync(manifest);
      if (start['ok'] != true) {
        yield {
          'done': true,
          'errors': <String>['sync-worker rejected: ${start['error']}'],
          'percent': 0.0,
        };
        return;
      }

      // 轮询进度
      while (true) {
        await Future.delayed(const Duration(milliseconds: 800));
        Map<String, dynamic> status;
        try {
          status = await getStatus();
        } catch (e) {
          yield {
            'done': true,
            'errors': <String>['status poll failed: $e'],
            'percent': 0.0,
          };
          return;
        }

        final percent = ((status['percent'] as num?)?.toDouble() ?? 0.0)
            .clamp(0.0, 100.0);
        // 进度条把前 15% 留给准备阶段
        final mapped = 15.0 + percent * 0.85;
        yield {
          'stage': 'downloading',
          'percent': mapped,
          'total': status['total'],
          'completed': status['completed'],
          'current_file': status['current_file'],
        };

        if (status['running'] == false) {
          final errs = (status['errors'] as List?)?.cast<dynamic>() ?? const [];
          if (errs.isEmpty) {
            // 成功同步 → 记下该 song_id，下次 xfadeTo 可跳过整个 sync 流水线
            markSynced(librarySongIds);
          }
          yield {
            'done': true,
            'errors': errs.map((e) => e.toString()).toList(),
            'percent': errs.isEmpty ? 100.0 : mapped,
            'total': status['total'],
            'completed': status['completed'],
          };
          return;
        }
      }
    } on DioException catch (e) {
      AppLogger.error('cacheSongs failed', error: e);
      yield {
        'done': true,
        'errors': <String>['${e.message ?? e}'],
        'percent': 0.0,
      };
    } catch (e) {
      AppLogger.error('cacheSongs failed', error: e);
      yield {
        'done': true,
        'errors': <String>['$e'],
        'percent': 0.0,
      };
    }
  }

  Map<String, dynamic>? _asMap(dynamic v) =>
      v is Map ? Map<String, dynamic>.from(v) : null;
}
