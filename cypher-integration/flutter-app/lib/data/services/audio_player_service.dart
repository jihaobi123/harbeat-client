import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/rk_client.dart';
import '../../core/utils/logger.dart';
import 'rk_sync_service.dart';

/// 全局远程播放器：所有命令路由到 RK3588 边缘节点。
/// 手机 = 控制端 + 进度显示；RK3588 = 播放端（出声）。
///
/// 数据流：
///   play()  → 1) edge-agent /play（先试一次）
///           → 2) 若 cache miss，sync-worker 缓存
///           → 3) 重试 /play + 启动 /state 轮询
///   pause/resume/seek → edge-agent
class AudioPlaybackState {
  /// 当前曲目 library_song_id（UUID 字符串），UI 高亮用
  final String? songId;
  /// RK3588 端使用的 int song_id
  final int? rkSongId;
  final String? title;
  final String? artist;
  final Duration position;
  final Duration duration;
  final bool playing;
  final bool loading;
  final bool caching;
  final double cachePercent; // 0~100
  final String? cacheStage;
  final String? errorMessage;
  /// 仅保留以兼容旧 UI（RK3588 端目前不支持单轨预览）
  final String? stemName;

  const AudioPlaybackState({
    this.songId,
    this.rkSongId,
    this.title,
    this.artist,
    this.position = Duration.zero,
    this.duration = Duration.zero,
    this.playing = false,
    this.loading = false,
    this.caching = false,
    this.cachePercent = 0.0,
    this.cacheStage,
    this.errorMessage,
    this.stemName,
  });

  AudioPlaybackState copyWith({
    String? songId,
    int? rkSongId,
    String? title,
    String? artist,
    Duration? position,
    Duration? duration,
    bool? playing,
    bool? loading,
    bool? caching,
    double? cachePercent,
    String? cacheStage,
    String? errorMessage,
    String? stemName,
    bool clearTrack = false,
    bool clearError = false,
    bool clearStage = false,
    bool clearStem = false,
  }) {
    return AudioPlaybackState(
      songId: clearTrack ? null : (songId ?? this.songId),
      rkSongId: clearTrack ? null : (rkSongId ?? this.rkSongId),
      title: clearTrack ? null : (title ?? this.title),
      artist: clearTrack ? null : (artist ?? this.artist),
      position: position ?? this.position,
      duration: duration ?? this.duration,
      playing: playing ?? this.playing,
      loading: loading ?? this.loading,
      caching: caching ?? this.caching,
      cachePercent: cachePercent ?? this.cachePercent,
      cacheStage: clearStage ? null : (cacheStage ?? this.cacheStage),
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      stemName: clearStem ? null : (stemName ?? this.stemName),
    );
  }
}

class AudioPlayerNotifier extends Notifier<AudioPlaybackState> {
  late Dio _rkDio;
  String _rkBaseUrl = 'http://192.168.43.7:9000';
  Timer? _pollTimer;
  StreamSubscription? _wsPlaybackSub;
  StreamSubscription? _cacheSub;
  RkClient? _rk;
  RkSyncService? _sync;
  String? _jetsonToken; // 保留以兼容 setAuth 旧签名

  @override
  AudioPlaybackState build() {
    _rkDio = Dio(BaseOptions(
      baseUrl: _rkBaseUrl,
      connectTimeout: const Duration(seconds: 3),
      receiveTimeout: const Duration(seconds: 5),
      sendTimeout: const Duration(seconds: 5),
    ));
    ref.onDispose(() {
      _pollTimer?.cancel();
      _wsPlaybackSub?.cancel();
      _cacheSub?.cancel();
    });
    return const AudioPlaybackState();
  }

  /// 绑定 RkClient（用于 WS 实时回放状态）+ sync-worker
  void attach({required RkClient rk, required RkSyncService sync}) {
    _rk = rk;
    _sync = sync;
    _wsPlaybackSub?.cancel();
    _wsPlaybackSub = rk.playbackStream.listen(_onRkPlayback);
  }

  void setRkBaseUrl(String url) {
    _rkBaseUrl = url;
    _rkDio.options.baseUrl = url;
  }

  String get rkBaseUrl => _rkBaseUrl;

  /// 兼容旧调用：providers.dart AuthNotifier 会传 token；这里不再使用，仅保留接口。
  void setAuth({required String token, String? baseUrl}) {
    _jetsonToken = token;
  }

  String? get token => _jetsonToken;

  void _onRkPlayback(Map<String, dynamic> data) {
    final st = (data['state'] ?? '').toString();
    final pos = (data['current_position_sec'] as num?)?.toDouble() ?? 0.0;
    final rkSid = data['current_song_id'];
    state = state.copyWith(
      playing: st == 'playing',
      position: Duration(milliseconds: (pos * 1000).round()),
      rkSongId: rkSid is int
          ? rkSid
          : (rkSid is num ? rkSid.toInt() : state.rkSongId),
    );
  }

  /// 播放某首歌。
  /// - [songId] = library_song_id（UUID）
  /// - [rkSongId] = manifest 里的 int song_id，优先用这个发给 RK3588
  /// - [stemName] 当前 RK3588 端不支持单轨预览，传入将被忽略并记录到 state（UI 高亮）。
  ///
  /// 流程（v2，2026-05）：
  ///   1) **总是**先调用 sync-worker 同步该曲目（manifest 里的 sha256 决定要不要重下，命中则秒回）
  ///      ——避免 RK 缓存里同 song_id 复用旧文件导致放错歌。
  ///   2) sync 完成后再调 /play。
  ///   3) 若 sync 失败但 RK 上已有缓存，做兜底 /play 尝试。
  Future<void> play({
    required String songId,
    int? rkSongId,
    String? title,
    String? artist,
    String? stemName,
    double? durationSec,
  }) async {
    state = state.copyWith(
      songId: songId,
      rkSongId: rkSongId,
      title: title,
      artist: artist,
      loading: true,
      playing: false,
      position: Duration.zero,
      duration: durationSec != null
          ? Duration(milliseconds: (durationSec * 1000).round())
          : Duration.zero,
      stemName: stemName,
      clearStem: stemName == null,
      clearError: true,
    );

    // 1) 先 sync（命中 sha256 不会重下，约 1-2 秒）；本 session 已同步过的跳过
    bool syncOk = true;
    if (_sync != null && !(_sync?.isSynced(songId) ?? false)) {
      state = state.copyWith(
        caching: true,
        cachePercent: 0.0,
        cacheStage: 'verify',
        loading: false,
      );
      _cacheSub?.cancel();
      final completer = Completer<bool>();
      _cacheSub = _sync!.cacheSongs(librarySongIds: [songId]).listen(
        (ev) {
          final pct = ((ev['percent'] as num?)?.toDouble() ?? 0.0)
              .clamp(0.0, 100.0);
          state = state.copyWith(
            cachePercent: pct,
            cacheStage: (ev['stage'] ?? state.cacheStage)?.toString(),
          );
          if (ev['done'] == true && !completer.isCompleted) {
            final errs = ev['errors'] as List?;
            completer.complete(errs == null || errs.isEmpty);
          }
        },
        onError: (e) {
          AppLogger.warning('play: sync error $e');
          if (!completer.isCompleted) completer.complete(false);
        },
        onDone: () {
          if (!completer.isCompleted) completer.complete(false);
        },
      );
      syncOk = await completer.future;
      state = state.copyWith(caching: false, clearStage: true);
    }

    // 2) 调 RK /play
    state = state.copyWith(loading: true);
    final r1 = await _postPlay(rkSongId, songId);
    if (r1.ok) {
      _startPolling();
      state = state.copyWith(loading: false);
      return;
    }

    // 3) /play 失败：如果之前 sync 也失败，给出最终错误
    if (!syncOk) {
      state = state.copyWith(
        loading: false,
        errorMessage: 'RK3588 同步与播放均失败: ${r1.error}',
      );
      return;
    }

    // 4) sync 成功但 /play 仍失败（少见），重试一次
    final r2 = await _postPlay(rkSongId, songId);
    if (r2.ok) {
      _startPolling();
      state = state.copyWith(loading: false);
    } else {
      state = state.copyWith(
        loading: false,
        errorMessage: 'RK3588 播放失败: ${r2.error}',
      );
    }
  }

  Future<_RkResult> _postPlay(int? rkSongId, String uuidSongId) async {
    final body = <String, dynamic>{
      'song_id': rkSongId ?? uuidSongId,
      'start_at_sec': 0,
    };
    try {
      final resp = await _rkDio.post('/play', data: body);
      if (resp.statusCode != null && resp.statusCode! < 400) {
        return _RkResult(true, null);
      }
      return _RkResult(false, '${resp.statusCode}: ${resp.data}');
    } on DioException catch (e) {
      final code = e.response?.statusCode ?? 0;
      final data = e.response?.data;
      AppLogger.warning('RK /play 失败: $code $data');
      return _RkResult(false, '$code: $data');
    } catch (e) {
      AppLogger.warning('RK /play 异常: $e');
      return _RkResult(false, '$e');
    }
  }

  /// 主动 crossfade 到另一首歌（复刻网页 SeamlessPlayer 的无缝衔接）。
  /// - 若当前 RK 未在播 → 自动回退为硬切 /play。
  /// - 若 RK /xfade 不存在（旧版 edge-agent）→ 自动回退为硬切 /play。
  Future<void> xfadeTo({
    required String songId,
    int? rkSongId,
    String? title,
    String? artist,
    double? durationSec,
    double fadeSec = 4.0,
    double toAtSec = 0.0,
    String style = 'smooth',
  }) async {
    // 当前没有在播 → 直接走 play()
    if (!state.playing || state.songId == null) {
      await play(
        songId: songId,
        rkSongId: rkSongId,
        title: title,
        artist: artist,
        durationSec: durationSec,
      );
      return;
    }

    final prevSongId = state.songId;
    final prevRkSongId = state.rkSongId;

    // 1) 先 sync 目标曲（与 play() 同样的 sha256 校验流程）；已同步过的跳过
    bool syncOk = true;
    if (_sync != null && !(_sync?.isSynced(songId) ?? false)) {
      state = state.copyWith(
        caching: true,
        cachePercent: 0.0,
        cacheStage: 'verify',
      );
      _cacheSub?.cancel();
      final completer = Completer<bool>();
      _cacheSub = _sync!.cacheSongs(librarySongIds: [songId]).listen(
        (ev) {
          final pct = ((ev['percent'] as num?)?.toDouble() ?? 0.0)
              .clamp(0.0, 100.0);
          state = state.copyWith(
            cachePercent: pct,
            cacheStage: (ev['stage'] ?? state.cacheStage)?.toString(),
          );
          if (ev['done'] == true && !completer.isCompleted) {
            final errs = ev['errors'] as List?;
            completer.complete(errs == null || errs.isEmpty);
          }
        },
        onError: (e) {
          AppLogger.warning('xfade: sync error $e');
          if (!completer.isCompleted) completer.complete(false);
        },
        onDone: () {
          if (!completer.isCompleted) completer.complete(false);
        },
      );
      syncOk = await completer.future;
      state = state.copyWith(caching: false, clearStage: true);
    }

    // 2) 先乐观更新 UI（标题等）
    state = state.copyWith(
      songId: songId,
      rkSongId: rkSongId,
      title: title,
      artist: artist,
      duration: durationSec != null
          ? Duration(milliseconds: (durationSec * 1000).round())
          : state.duration,
      clearError: true,
    );

    // 3) POST /xfade
    try {
      await _rkDio.post('/xfade', data: {
        'to_song_id': rkSongId ?? songId,
        'fade_sec': fadeSec,
        'to_at_sec': toAtSec,
        'style': style,
      });
      _startPolling();
      return;
    } on DioException catch (e) {
      final code = e.response?.statusCode ?? 0;
      final data = e.response?.data;
      AppLogger.warning('RK /xfade 失败: $code $data');
      if (code == 404 || code == 405) {
        // edge-agent 旧版没有 /xfade → 硬切回退
        AppLogger.warning('edge-agent 不支持 /xfade，回退 /play');
        await play(
          songId: songId,
          rkSongId: rkSongId,
          title: title,
          artist: artist,
          durationSec: durationSec,
        );
        return;
      }
      // 其他错误：把 UI 还原回上一首并报错
      state = state.copyWith(
        songId: prevSongId,
        rkSongId: prevRkSongId,
        errorMessage: 'RK3588 crossfade 失败: $code: $data${syncOk ? '' : '（同步未完成）'}',
      );
    } catch (e) {
      AppLogger.warning('RK /xfade 异常: $e');
      state = state.copyWith(
        songId: prevSongId,
        rkSongId: prevRkSongId,
        errorMessage: 'RK3588 crossfade 异常: $e',
      );
    }
  }

  Future<void> pause() async {
    try {
      await _rkDio.post('/pause');
      state = state.copyWith(playing: false);
    } catch (e) {
      state = state.copyWith(errorMessage: 'pause 失败: $e');
    }
  }

  Future<void> resume() async {
    try {
      await _rkDio.post('/resume');
      state = state.copyWith(playing: true);
      _startPolling();
    } catch (e) {
      state = state.copyWith(errorMessage: 'resume 失败: $e');
    }
  }

  Future<void> toggle() async {
    if (state.playing) {
      await pause();
    } else if (state.songId != null) {
      await resume();
    }
  }

  Future<void> seek(Duration to) async {
    final sec = to.inMilliseconds / 1000.0;
    state = state.copyWith(position: to);
    try {
      await _rkDio.post('/seek', data: {'sec': sec});
    } catch (e) {
      state = state.copyWith(errorMessage: 'seek 失败: $e');
    }
  }

  Future<void> stop() async {
    _pollTimer?.cancel();
    try {
      await _rkDio.post('/pause');
    } catch (_) {}
    state = state.copyWith(
      clearTrack: true,
      playing: false,
      position: Duration.zero,
      clearStem: true,
    );
  }

  /// 提前把候选歌曲的 PCM+stems 解码到 RK 内存，让按键 /xfade 不再卡顿。
  /// 仅对已经 sync 过的歌做（Jetson 上还没 mirror 到 RK 的会被 edge-agent 忽略）。
  Future<void> prefetch(List<dynamic> rkSongIds) async {
    if (rkSongIds.isEmpty) return;
    try {
      await _rkDio.post('/prefetch', data: {'song_ids': rkSongIds});
    } on DioException catch (e) {
      // 404 = 旧版 edge-agent 还没部署 /prefetch，静默吞掉
      final code = e.response?.statusCode ?? 0;
      if (code != 404 && code != 405) {
        AppLogger.warning('prefetch 失败: $code ${e.response?.data}');
      }
    } catch (e) {
      AppLogger.warning('prefetch 异常: $e');
    }
  }

  /// 设置 stem solo（持久独奏）。传 null 取消。
  /// 在 RK3588 端只播放 vocals/drums/bass/other 中的一轨。
  Future<void> setStemSolo(String? stem) async {
    try {
      await _rkDio.post('/stem_solo', data: {'stem': stem});
      state = state.copyWith(
        stemName: stem,
        clearStem: stem == null,
      );
    } on DioException catch (e) {
      AppLogger.warning('stem_solo 失败: ${e.response?.statusCode} ${e.response?.data}');
      state = state.copyWith(errorMessage: '切换音轨失败: ${e.response?.data ?? e.message}');
    } catch (e) {
      state = state.copyWith(errorMessage: '切换音轨失败: $e');
    }
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(milliseconds: 500), (_) async {
      try {
        final resp = await _rkDio.get('/state');
        final data = resp.data;
        if (data is! Map) return;
        final pos = (data['position_sec'] as num?)?.toDouble() ??
            (data['current_position_sec'] as num?)?.toDouble() ??
            0.0;
        final playing = (data['playing'] as bool?) ??
            ((data['state'] ?? '') == 'playing');
        // active_stem_solo 可能缺省（旧版 edge-agent 不返回）— 只在显式带 key 时同步
        if (data.containsKey('active_stem_solo')) {
          final solo = data['active_stem_solo'] as String?;
          state = state.copyWith(
            position: Duration(milliseconds: (pos * 1000).round()),
            playing: playing,
            stemName: solo,
            clearStem: solo == null,
          );
        } else {
          state = state.copyWith(
            position: Duration(milliseconds: (pos * 1000).round()),
            playing: playing,
          );
        }
      } catch (_) {
        // RK 短暂不可达时静默
      }
    });
  }
}

class _RkResult {
  final bool ok;
  final String? error;
  _RkResult(this.ok, this.error);
}

final audioPlayerProvider =
    NotifierProvider<AudioPlayerNotifier, AudioPlaybackState>(() {
  return AudioPlayerNotifier();
});
