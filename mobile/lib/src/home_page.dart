import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import 'api_client.dart';
import 'edge_agent_client.dart';
import 'dj_control_page.dart';
import 'import/playlist_import_page.dart';
import 'library/song_detail_page.dart';
import 'models.dart';
import 'sync_worker_client.dart';

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.apiClient,
    required this.session,
    required this.rkBaseUrl,
    required this.onRkBaseUrlChanged,
    required this.apiBaseUrl,
    required this.onApiBaseUrlChanged,
    required this.data,
    required this.loading,
    required this.error,
    required this.onRefresh,
    required this.onLogout,
  });

  final HarBeatApiClient apiClient;
  final SessionBundle session;
  final String rkBaseUrl;
  final Future<void> Function(String url) onRkBaseUrlChanged;
  final String apiBaseUrl;
  final Future<void> Function(String url) onApiBaseUrlChanged;
  final DashboardData? data;
  final bool loading;
  final String? error;
  final Future<void> Function() onRefresh;
  final Future<void> Function() onLogout;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late EdgeAgentClient _edgeClient;
  late SyncWorkerClient _syncWorker;
  final AudioPlayer _player = AudioPlayer();
  final TextEditingController _librarySearchController = TextEditingController();

  DashboardData? _data;
  List<LibrarySong> _displaySongs = const [];
  PlaylistDetail? _selectedPlaylist;
  LibrarySong? _currentSong;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  // RK 远端播放状态（用于 MiniPlayer 显示）
  bool _rkPlaying = false;
  // 同步缓存进度 0..100；非空时显示 prefetch 提示
  double? _prefetchPercent;
  String? _prefetchMessage;
  // 拖动 seek 后的"防回弹"截止时间：在此之前忽略 RK /state 轮询返回的 position，
  // 避免轮询返回旧 position 把进度条拽回。
  DateTime? _seekGuardUntil;

  bool _librarySearching = false;
  bool _uploading = false;
  bool _playlistLoading = false;
  bool _testing = false;
  String? _localError;
  int _selectedIndex = 1;

  StreamSubscription<Duration>? _positionSub;
  StreamSubscription<Duration?>? _durationSub;
  Timer? _analysisWatcher;
  Timer? _rkStateTimer;

  @override
  void initState() {
    super.initState();
    _edgeClient = EdgeAgentClient(
      baseUrl: 'http://${widget.rkBaseUrl}',
    );
    _syncWorker = SyncWorkerClient(
      baseUrl: SyncWorkerClient.deriveFromRkBaseUrl(widget.rkBaseUrl),
    );
    _syncFromWidget();
    _positionSub = _player.positionStream.listen((value) {
      if (mounted) setState(() => _position = value);
    });
    _durationSub = _player.durationStream.listen((value) {
      if (mounted) setState(() => _duration = value ?? Duration.zero);
    });
    _startAnalysisWatcher();
  }

  void _startAnalysisWatcher() {
    _analysisWatcher?.cancel();
    _analysisWatcher = Timer.periodic(const Duration(seconds: 8), (_) async {
      final songs = _data?.songs ?? const <LibrarySong>[];
      final hasPending = songs.any((s) {
        final st = s.analysisStatus.toLowerCase();
        return st == 'pending' ||
            st == 'queued' ||
            st == 'running' ||
            st == 'processing';
      });
      if (hasPending) {
        // 后台静默刷新，让列表里的状态自动跟上后端
        try {
          await widget.onRefresh();
          if (!mounted) return;
          _syncFromWidget();
          setState(() {});
        } catch (_) {
          // 静默失败，下个周期重试
        }
      }
    });
  }

  @override
  void didUpdateWidget(covariant HomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.data != widget.data || oldWidget.error != widget.error) {
      _syncFromWidget();
    }
    if (oldWidget.rkBaseUrl != widget.rkBaseUrl) {
      _edgeClient = EdgeAgentClient(
        baseUrl: 'http://${widget.rkBaseUrl}',
      );
      _syncWorker = SyncWorkerClient(
        baseUrl: SyncWorkerClient.deriveFromRkBaseUrl(widget.rkBaseUrl),
      );
    }
  }

  void _syncFromWidget() {
    _data = widget.data;
    _displaySongs = widget.data?.songs ?? const [];
    _localError = widget.error;
  }

  @override
  void dispose() {
    _analysisWatcher?.cancel();
    _rkStateTimer?.cancel();
    _positionSub?.cancel();
    _durationSub?.cancel();
    _player.dispose();
    _librarySearchController.dispose();
    super.dispose();
  }

  Future<void> _refreshAll() async {
    await widget.onRefresh();
    _syncFromWidget();
    if (mounted) setState(() {});
  }

  Future<void> _showSettingsDialog() async {
    final apiCtrl = TextEditingController(text: widget.apiBaseUrl);
    final rkCtrl = TextEditingController(text: widget.rkBaseUrl);
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('服务地址'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: apiCtrl,
              decoration: const InputDecoration(
                labelText: 'API 服务器',
                hintText: 'http://8.136.120.255',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: rkCtrl,
              decoration: const InputDecoration(
                labelText: 'RK3588 Edge-Agent',
                hintText: '192.168.43.7:9000',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (result == true) {
      final api = apiCtrl.text.trim();
      final rk = rkCtrl.text.trim();
      if (api.isNotEmpty && api != widget.apiBaseUrl) {
        await widget.onApiBaseUrlChanged(api);
      }
      if (rk.isNotEmpty && rk != widget.rkBaseUrl) {
        await widget.onRkBaseUrlChanged(rk);
        _edgeClient = EdgeAgentClient(baseUrl: 'http://$rk');
      }
    }
  }

  /// 仅探活 RK3588 Edge-Agent，不播放任何音频。
  Future<void> _runRkPingTest() async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _testing = true);
    String msg;
    Color bg = Colors.green.shade700;
    try {
      final state = await _edgeClient.getState();
      if (state.error != null) {
        msg = 'RK 不可达: ${state.error}  (地址=${widget.rkBaseUrl})';
        bg = Colors.red.shade700;
      } else {
        msg = 'RK OK · playing=${state.playing} · pos=${state.positionSec.toStringAsFixed(1)}s · 地址=${widget.rkBaseUrl}';
      }
    } catch (e) {
      msg = 'RK 不可达: $e  (地址=${widget.rkBaseUrl})';
      bg = Colors.red.shade700;
    } finally {
      if (mounted) setState(() => _testing = false);
    }
    messenger.showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: bg,
      duration: const Duration(seconds: 6),
    ));
  }

  /// 随机选一首歌 + 随机段落 + 随机音轨，在手机上试听 5 秒
  /// 同时探活 RK3588 Edge-Agent。
  Future<void> _runRkRandomTest() async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() {
      _testing = true;
      _localError = null;
    });
    final rand = Random();
    String? rkStatus;

    // 1) 探活 RK3588
    try {
      final state = await _edgeClient.getState();
      rkStatus = state.error != null
          ? 'RK 不可达: ${state.error}'
          : 'RK OK (playing=${state.playing}, pos=${state.positionSec.toStringAsFixed(1)}s)';
    } catch (e) {
      rkStatus = 'RK 不可达: $e';
    }

    // 2) 拿曲库
    final songs = _data?.songs ?? const <LibrarySong>[];
    if (songs.isEmpty) {
      messenger.showSnackBar(SnackBar(
        content: Text('曲库为空，无法试听。$rkStatus'),
      ));
      if (mounted) setState(() => _testing = false);
      return;
    }
    final song = songs[rand.nextInt(songs.length)];

    // 3) 拉最新详情以获取 cue/stems
    LibrarySong detail = song;
    try {
      detail = await widget.apiClient.getLibrarySong(
        token: widget.session.token,
        songId: song.id,
      );
    } catch (_) {/* 使用列表里的原始数据 */}

    // 4) 随机选段落
    double startSec = 0;
    String segLabel = '开头';
    if (detail.cuePoints.isNotEmpty) {
      final cue = detail.cuePoints[rand.nextInt(detail.cuePoints.length)];
      startSec = cue.time;
      segLabel = cue.label.isEmpty ? 'Cue@${cue.time.toStringAsFixed(1)}s' : cue.label;
    } else if (detail.duration > 10) {
      // 没有 cue 就随机丢到前 70%
      startSec = rand.nextDouble() * (detail.duration * 0.7);
      segLabel = '随机@${startSec.toStringAsFixed(1)}s';
    }

    // 5) 随机选音轨
    String stemKey = 'full';
    if (detail.hasStems) {
      final stemNames = const ['vocals', 'drums', 'bass', 'other'];
      stemKey = stemNames[rand.nextInt(stemNames.length)];
    }

    final url = stemKey == 'full'
        ? widget.apiClient.streamUrl(
            token: widget.session.token,
            songId: detail.id,
          )
        : widget.apiClient.stemStreamUrl(
            token: widget.session.token,
            songId: detail.id,
            stemName: stemKey,
          );

    // 停手机本地播放，避免和 RK 重叠
    try {
      await _player.stop();
    } catch (_) {}

    try {
      // 主路：通过 RK3588 出声（带起播位置）
      final res = await _edgeClient.play(
        songId: detail.id,
        startAtSec: startSec,
      );
      final ok = res['ok'] == true ||
          (res['result'] is Map && (res['result'] as Map)['ok'] == true);
      setState(() => _currentSong = detail);

      messenger.showSnackBar(SnackBar(
        duration: const Duration(seconds: 4),
        backgroundColor: ok ? null : Colors.orange.shade700,
        content: Text(
          ok
              ? '🔊 RK 试听「${detail.title} - ${detail.artist}」·段落:$segLabel · $rkStatus'
              : 'RK 拒绝: $res （URL: $url）',
        ),
      ));

      // 5 秒后让 RK 暂停
      await Future<void>.delayed(const Duration(seconds: 5));
      if (!mounted) return;
      try {
        await _edgeClient.pause();
      } catch (_) {}
    } catch (e) {
      final msg = e.toString();
      final hint = msg.contains('original.wav') || msg.contains('缺少')
          ? ' (该曲未同步到 RK 缓存)'
          : '';
      messenger.showSnackBar(SnackBar(
        backgroundColor: Colors.red.shade700,
        duration: const Duration(seconds: 6),
        content: Text('RK 试听失败: $msg$hint'),
      ));
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  Future<void> _searchLibrary(String value) async {
    if (value.trim().isEmpty) {
      setState(() {
        _displaySongs = _data?.songs ?? const [];
        _librarySearching = false;
      });
      return;
    }

    setState(() => _librarySearching = true);
    try {
      final result = await widget.apiClient.searchLibrarySongs(
        token: widget.session.token,
        query: value.trim(),
      );
      setState(() {
        _displaySongs = result;
        _librarySearching = false;
      });
    } catch (error) {
      setState(() {
        _localError = error.toString();
        _librarySearching = false;
      });
    }
  }

  Future<void> _pickAndUpload() async {
    final result = await FilePicker.platform.pickFiles(
      allowMultiple: true,
      type: FileType.custom,
      allowedExtensions: ['mp3', 'flac', 'wav', 'ogg', 'aac', 'm4a', 'opus', 'ncm'],
    );
    if (result == null || result.files.isEmpty) return;

    setState(() {
      _uploading = true;
      _localError = null;
    });

    try {
      final uploaded = <LibrarySong>[];
      for (final file in result.files) {
        if (file.path == null) continue;
        final parsed = _guessTitleArtist(file.name);
        final song = await widget.apiClient.uploadSong(
          token: widget.session.token,
          file: File(file.path!),
          title: parsed.$1,
          artist: parsed.$2,
        );
        uploaded.add(song);
      }
      final songs = [...uploaded, ...?_data?.songs];
      setState(() {
        _data = DashboardData(
          profile: _data?.profile ?? widget.session.profile,
          songs: songs,
          playlists: _data?.playlists ?? const [],
        );
        _displaySongs = songs;
        _uploading = false;
      });
    } catch (error) {
      setState(() {
        _uploading = false;
        _localError = error.toString();
      });
    }
  }

  (String, String) _guessTitleArtist(String filename) {
    final raw = filename.replaceFirst(RegExp(r'\.[^.]+$'), '');
    if (raw.contains(' - ')) {
      final parts = raw.split(' - ');
      return (parts.skip(1).join(' - ').trim(), parts.first.trim());
    }
    return (raw, 'Unknown Artist');
  }

  Future<void> _openPlaylist(PlaylistSummary playlist) async {
    setState(() {
      _playlistLoading = true;
      _selectedPlaylist = null;
    });
    try {
      final detail = await widget.apiClient.getPlaylistDetail(
        token: widget.session.token,
        playlistId: playlist.id,
      );
      setState(() {
        _selectedPlaylist = detail;
        _playlistLoading = false;
      });
      if (!mounted) return;
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        builder: (context) => PlaylistDetailSheet(
          playlist: detail,
          librarySongs: _data?.songs ?? const [],
          onPlayPlaylistSong: _playPlaylistSong,
        ),
      );
    } catch (error) {
      setState(() {
        _playlistLoading = false;
        _localError = error.toString();
      });
    }
  }

  Future<void> _openSongDetail(LibrarySong song) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => SongDetailPage(
          apiClient: widget.apiClient,
          session: widget.session,
          song: song,
        ),
      ),
    );
    // 返回时同步一次列表，确保状态/分析结果是最新的
    if (mounted) {
      await _refreshAll();
    }
  }

  Future<void> _playSong(LibrarySong song) async {
    final messenger = ScaffoldMessenger.of(context);
    // 停掉手机本地播放器（避免双声源）
    try {
      await _player.stop();
    } catch (_) {}
    setState(() {
      _currentSong = song;
      _localError = null;
      _position = Duration.zero;
      // 用 Library 元数据时长作为初始 _duration（RK /state 目前不返回 duration_sec）
      _duration = song.duration > 0
          ? Duration(milliseconds: (song.duration * 1000).round())
          : Duration.zero;
      _rkPlaying = false;
      _prefetchPercent = null;
      _prefetchMessage = null;
    });
    _stopRkStatePolling();

    // 1) 先试直接 /play；RK 缓存命中则立刻出声。
    final firstTry = await _tryDirectPlay(song);
    if (firstTry) {
      _onRkPlaybackStarted(song, messenger);
      return;
    }

    // 2) 未命中：触发 sync（不等它跑完），同时 200ms 轮询 sync-worker /cache/check，
    //    文件一落盘就立刻 /play。这样首播延迟 ≈ "下载完单文件 + 200ms"。
    final fastOk = await _fastPlayWhenCached(song, messenger);
    if (fastOk) {
      _onRkPlaybackStarted(song, messenger);
      return;
    }

    // 3) 快路径超时（典型：mp3 较大或网络慢）→ 回退到老的 syncAndWait 全量等待
    final prefetchOk = await _prefetchToRkCache(song, messenger);
    if (!prefetchOk) return;

    final secondTry = await _tryDirectPlay(song);
    if (secondTry) {
      _onRkPlaybackStarted(song, messenger);
    } else {
      if (!mounted) return;
      setState(() {
        _localError = 'RK 播放失败，请检查边缘服务';
        _prefetchPercent = null;
        _prefetchMessage = null;
      });
      messenger.showSnackBar(SnackBar(
        backgroundColor: Colors.red.shade700,
        content: const Text('RK 播放失败'),
      ));
    }
  }

  /// 触发后台 sync，同时以 200ms 频率轮询 RK 缓存：
  ///   - 文件落盘 → 立刻 /play 出声，返回 true。
  ///   - 8 秒内未落盘 → 返回 false，让上层回退到 syncAndWait 等到底。
  Future<bool> _fastPlayWhenCached(
    LibrarySong song,
    ScaffoldMessengerState messenger,
  ) async {
    setState(() {
      _prefetchPercent = 0;
      _prefetchMessage = '请求 RK 缓存…';
    });

    final tracks = [
      <String, dynamic>{
        'song_id': song.id,
        'files': <String, dynamic>{
          'original': <String, dynamic>{
            'url': _buildJetsonStreamUrl(song.id),
            'format': 'mp3',
          },
        },
      }
    ];

    // 启动 sync（不等它跑完），失败也不致命：可能是已经在跑
    unawaited(() async {
      try {
        await _syncWorker.startSync(
          tracks: tracks,
          planId: 'mobile-${song.id}',
        );
      } catch (_) {/* already running 也算成功 */}
    }());

    final deadline = DateTime.now().add(const Duration(seconds: 8));
    while (DateTime.now().isBefore(deadline)) {
      if (!mounted) return false;
      // 调 sync-worker /cache/check 看 original.* 是否落盘
      if (await _syncWorker.cacheExists(song.id)) {
        // 命中 → 立刻 /play
        if (await _tryDirectPlay(song)) {
          if (mounted) {
            setState(() {
              _prefetchPercent = null;
              _prefetchMessage = null;
            });
          }
          return true;
        }
      }
      // 同时刷一下 sync-worker 进度，在 UI 上反馈
      try {
        final st = await _syncWorker.getStatus();
        if (mounted) {
          setState(() {
            _prefetchPercent = st.percent;
            _prefetchMessage =
                '正在拉取到 RK 缓存 ${st.percent.toStringAsFixed(0)}%';
          });
        }
      } catch (_) {}
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    return false;
  }

  /// 试一次 /play；任何异常/ok=false 都返回 false，交给上层走 prefetch 分支。
  Future<bool> _tryDirectPlay(LibrarySong song) async {
    try {
      final res = await _edgeClient.play(songId: song.id);
      return res['ok'] == true ||
          (res['result'] is Map && (res['result'] as Map)['ok'] == true);
    } catch (_) {
      return false;
    }
  }

  /// 调 sync-worker 拉取该曲（包含 stem 如果已分离）。返回是否成功落盘。
  Future<bool> _prefetchToRkCache(
    LibrarySong song,
    ScaffoldMessengerState messenger,
  ) async {
    setState(() {
      _prefetchPercent = 0;
      _prefetchMessage = '正在拉取到 RK 缓存 0%';
    });
    final tracks = [
      <String, dynamic>{
        'song_id': song.id,
        'files': <String, dynamic>{
          'original': <String, dynamic>{
            'url': _buildJetsonStreamUrl(song.id),
            'format': 'mp3',
          },
        },
      }
    ];
    try {
      await _syncWorker.syncAndWait(
        tracks: tracks,
        planId: 'mobile-${song.id}',
        timeout: const Duration(minutes: 2),
        onProgress: (st) {
          if (!mounted) return;
          setState(() {
            _prefetchPercent = st.percent;
            _prefetchMessage =
                '正在拉取到 RK 缓存 ${st.percent.toStringAsFixed(0)}%';
          });
        },
      );
      if (!mounted) return false;
      setState(() {
        _prefetchPercent = 100;
        _prefetchMessage = '缓存完成';
      });
      return true;
    } catch (e) {
      if (!mounted) return false;
      setState(() {
        _localError = '拉取到 RK 失败: $e';
        _prefetchPercent = null;
        _prefetchMessage = null;
      });
      messenger.showSnackBar(SnackBar(
        backgroundColor: Colors.red.shade700,
        duration: const Duration(seconds: 6),
        content: Text('拉取到 RK 失败: $e'),
      ));
      return false;
    }
  }

  String _buildJetsonStreamUrl(String songId) {
    return widget.apiClient.streamUrl(
      token: widget.session.token,
      songId: songId,
    );
  }

  void _onRkPlaybackStarted(
    LibrarySong song,
    ScaffoldMessengerState messenger,
  ) {
    if (!mounted) return;
    setState(() {
      _rkPlaying = true;
      _prefetchPercent = null;
      _prefetchMessage = null;
    });
    messenger.showSnackBar(SnackBar(
      content: Text('🔊 RK3588 播放: ${song.title} - ${song.artist}'),
      duration: const Duration(seconds: 3),
    ));
    _startRkStatePolling();
  }

  void _startRkStatePolling() {
    _rkStateTimer?.cancel();
    _rkStateTimer = Timer.periodic(const Duration(seconds: 1), (_) async {
      try {
        final st = await _edgeClient.getState();
        if (!mounted) return;
        if (st.error != null) return;
        // 如果 RK 当前曲与本地 _currentSong 不一致，仍然跟随 RK
        setState(() {
          _rkPlaying = st.playing;
          // 拖动结束后短暂窗口内忽略 position（防止 RK 回报旧值把进度条拽回）
          final guard = _seekGuardUntil;
          final inGuard = guard != null && DateTime.now().isBefore(guard);
          if (!inGuard) {
            _position =
                Duration(milliseconds: (st.positionSec * 1000).round());
          }
          // 只有 RK 真的返回了 duration_sec>0 才覆盖；否则保留来自 Library 元数据的时长
          if (st.durationSec > 0) {
            _duration = Duration(milliseconds: (st.durationSec * 1000).round());
          } else if (_currentSong != null &&
              _duration == Duration.zero &&
              _currentSong!.duration > 0) {
            _duration = Duration(
                milliseconds: (_currentSong!.duration * 1000).round());
          }
        });
      } catch (_) {
        // 各种网络抖动均静默，下轮重试
      }
    });
  }

  void _stopRkStatePolling() {
    _rkStateTimer?.cancel();
    _rkStateTimer = null;
  }

  Future<void> _playPlaylistSong(PlaylistSong playlistSong) async {
    for (final item in _data?.songs ?? const <LibrarySong>[]) {
      if (item.title.toLowerCase() == playlistSong.title.toLowerCase() &&
          item.artist.toLowerCase() == playlistSong.artist.toLowerCase()) {
        await _playSong(item);
        return;
      }
    }
    setState(() => _localError = '当前歌单歌曲没有对应的本地曲库文件，暂时无法播放');
  }

  Future<void> _togglePlayback() async {
    // 优先控制 RK（现在播放主路由在 RK）
    if (_currentSong != null) {
      try {
        if (_rkPlaying) {
          await _edgeClient.pause();
          if (mounted) setState(() => _rkPlaying = false);
        } else {
          await _edgeClient.resume();
          if (mounted) setState(() => _rkPlaying = true);
          _startRkStatePolling();
        }
        return;
      } catch (e) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          backgroundColor: Colors.red.shade700,
          content: Text('RK 控制失败: $e'),
        ));
        return;
      }
    }
    if (_player.playing) {
      await _player.pause();
    } else {
      await _player.play();
    }
    if (mounted) setState(() {});
  }

  Future<void> _seek(double value) async {
    if (_currentSong != null) {
      // 乐观更新本地 position，开 1 秒防回弹窗，等 RK /state 在下一次轮询追上
      setState(() {
        _position = Duration(milliseconds: (value * 1000).round());
        _seekGuardUntil =
            DateTime.now().add(const Duration(milliseconds: 1000));
      });
      try {
        // 走 RK /seek，比重发 /play 快得多（不重新加载文件）
        await _edgeClient.seek(value);
      } catch (e) {
        // /seek 失败兜底走 /play start_at_sec（旧路径），避免完全失灵
        try {
          await _edgeClient.play(
            songId: _currentSong!.id,
            startAtSec: value,
          );
        } catch (_) {}
      }
      return;
    }
    await _player.seek(Duration(seconds: value.round()));
  }

  Future<void> _analyzeSong(LibrarySong song) async {
    try {
      final updated = await widget.apiClient.analyzeSong(
        token: widget.session.token,
        songId: song.id,
      );
      final songs = (_data?.songs ?? const <LibrarySong>[])
          .map((item) => item.id == song.id ? updated : item)
          .toList();
      setState(() {
        _data = DashboardData(
          profile: _data?.profile ?? widget.session.profile,
          songs: songs,
          playlists: _data?.playlists ?? const [],
        );
        _displaySongs = songs;
        if (_currentSong?.id == song.id) {
          _currentSong = updated;
        }
      });
    } catch (error) {
      setState(() => _localError = error.toString());
    }
  }

  Future<void> _deleteSong(LibrarySong song) async {
    try {
      await widget.apiClient.deleteSong(token: widget.session.token, songId: song.id);
      final songs = (_data?.songs ?? const <LibrarySong>[])
          .where((item) => item.id != song.id)
          .toList();
      if (_currentSong?.id == song.id) {
        await _player.stop();
      }
      setState(() {
        _data = DashboardData(
          profile: _data?.profile ?? widget.session.profile,
          songs: songs,
          playlists: _data?.playlists ?? const [],
        );
        _displaySongs = songs;
        if (_currentSong?.id == song.id) {
          _currentSong = null;
          _position = Duration.zero;
          _duration = Duration.zero;
        }
      });
    } catch (error) {
      setState(() => _localError = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final songs = _data?.songs ?? const <LibrarySong>[];
    final playlists = _data?.playlists ?? const <PlaylistSummary>[];

    return Scaffold(
      appBar: AppBar(
        title: Text(_titleForTab(_selectedIndex)),
        actions: [
          if (_selectedIndex == 0)
            IconButton(
              tooltip: '上传歌曲',
              onPressed: _uploading ? null : _pickAndUpload,
              icon: _uploading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.upload_file),
            ),
          IconButton(
            tooltip: 'RK3588 连接测试',
            onPressed: _testing ? null : _runRkPingTest,
            icon: const Icon(Icons.wifi_tethering),
          ),
          IconButton(
            tooltip: 'RK3588 + 手机随机试听',
            onPressed: _testing ? null : _runRkRandomTest,
            icon: _testing
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.science_outlined),
          ),
          IconButton(
            tooltip: '设置',
            onPressed: _showSettingsDialog,
            icon: const Icon(Icons.settings_outlined),
          ),
          IconButton(
            tooltip: '刷新',
            onPressed: () => _refreshAll(),
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: '退出登录',
            onPressed: () => widget.onLogout(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (_localError != null)
              MaterialBanner(
                content: Text(_localError!),
                actions: [
                  TextButton(
                    onPressed: () => setState(() => _localError = null),
                    child: const Text('关闭'),
                  ),
                ],
              ),
            Expanded(
              child: IndexedStack(
                index: _selectedIndex,
                children: [
                  LibraryTab(
                    controller: _librarySearchController,
                    songs: _displaySongs,
                    searching: _librarySearching,
                    onSearchChanged: _searchLibrary,
                    onPlay: _playSong,
                    onAnalyze: _analyzeSong,
                    onDelete: _deleteSong,
                    onDetails: _openSongDetail,
                  ),
                  PlaylistsTab(
                    playlists: playlists,
                    loading: _playlistLoading,
                    onOpen: _openPlaylist,
                    selectedPlaylist: _selectedPlaylist,
                    onImportPressed: () async {
                      await Navigator.of(context).push<void>(
                        MaterialPageRoute(
                          builder: (_) => PlaylistImportPage(
                            apiClient: widget.apiClient,
                            token: widget.session.token,
                            userId: widget.session.profile.id,
                            onImported: _refreshAll,
                          ),
                        ),
                      );
                    },
                  ),
                  DjControlPage(
                    apiClient: widget.apiClient,
                    edgeClient: _edgeClient,
                    token: widget.session.token,
                    userId: widget.session.profile.id,
                    librarySongs: songs,
                  ),
                ],
              ),
            ),
            if (_currentSong != null)
              MiniPlayer(
                song: _currentSong!,
                isPlaying: _rkPlaying || _player.playing,
                position: _position,
                duration: _duration,
                onToggle: _togglePlayback,
                onSeek: _seek,
                prefetchPercent: _prefetchPercent,
                prefetchMessage: _prefetchMessage,
              ),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (value) => setState(() => _selectedIndex = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.library_music_outlined), label: '曲库'),
          NavigationDestination(icon: Icon(Icons.queue_music_outlined), label: '歌单'),
          NavigationDestination(icon: Icon(Icons.graphic_eq_outlined), label: 'DJ Control'),
        ],
      ),
    );
  }

  String _titleForTab(int index) {
    switch (index) {
      case 0:
        return '曲库';
      case 1:
        return '歌单';
      case 2:
        return 'DJ Control';
      default:
        return 'HarBeat';
    }
  }
}

class OverviewTab extends StatelessWidget {
  const OverviewTab({
    super.key,
    required this.profile,
    required this.songs,
    required this.playlists,
    required this.loading,
  });

  final UserProfile profile;
  final List<LibrarySong> songs;
  final List<PlaylistSummary> playlists;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final analyzed = songs.where((item) => item.analysisStatus == 'completed').length;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: ListTile(
            leading: CircleAvatar(child: Text(profile.username.isEmpty ? '?' : profile.username[0].toUpperCase())),
            title: Text(profile.username),
            subtitle: Text('${profile.danceStyle} · ${profile.level} · 喜欢 ${profile.favoriteStyle}'),
          ),
        ),
        const SizedBox(height: 12),
        GridView.count(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisCount: 2,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          childAspectRatio: 1.6,
          children: [
            StatCard(label: '歌曲', value: '${songs.length}'),
            StatCard(label: '歌单', value: '${playlists.length}'),
            StatCard(label: '已分析', value: '$analyzed'),
            StatCard(label: '状态', value: loading ? '同步中' : '就绪'),
          ],
        ),
        const SizedBox(height: 16),
        SectionCard(
          title: '最近歌曲',
          child: Column(
            children: songs.take(5).map((song) => SongSummaryTile(song: song)).toList(),
          ),
        ),
      ],
    );
  }
}

class LibraryTab extends StatelessWidget {
  const LibraryTab({
    super.key,
    required this.controller,
    required this.songs,
    required this.searching,
    required this.onSearchChanged,
    required this.onPlay,
    required this.onAnalyze,
    required this.onDelete,
    required this.onDetails,
  });

  final TextEditingController controller;
  final List<LibrarySong> songs;
  final bool searching;
  final ValueChanged<String> onSearchChanged;
  final Future<void> Function(LibrarySong song) onPlay;
  final Future<void> Function(LibrarySong song) onAnalyze;
  final Future<void> Function(LibrarySong song) onDelete;
  final Future<void> Function(LibrarySong song) onDetails;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: TextField(
            controller: controller,
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search),
              suffixIcon: searching
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                    )
                  : null,
              hintText: '搜索曲库中的歌曲或艺人',
              border: const OutlineInputBorder(),
            ),
            onChanged: onSearchChanged,
          ),
        ),
        Expanded(
          child: songs.isEmpty
              ? const Center(child: Text('曲库为空，先上传或下载歌曲'))
              : ListView.separated(
                  itemCount: songs.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final song = songs[index];
                    return ListTile(
                      leading: const CircleAvatar(child: Icon(Icons.music_note)),
                      title: Text(song.title),
                      subtitle: Text([
                        song.artist,
                        if (song.bpm != null) '${song.bpm!.toStringAsFixed(0)} BPM',
                        song.analysisStatus,
                      ].join(' · ')),
                      onTap: () => _showSongActions(context, song),
                    );
                  },
                ),
        ),
      ],
    );
  }

  void _showSongActions(BuildContext context, LibrarySong song) {
    showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      builder: (context) => Wrap(
        children: [
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('详情'),
            onTap: () async {
              Navigator.pop(context);
              await onDetails(song);
            },
          ),
          ListTile(
            leading: const Icon(Icons.play_arrow),
            title: const Text('播放'),
            onTap: () async {
              Navigator.pop(context);
              await onPlay(song);
            },
          ),
          ListTile(
            leading: const Icon(Icons.analytics_outlined),
            title: const Text('分析 BPM / Key'),
            onTap: () async {
              Navigator.pop(context);
              await onAnalyze(song);
            },
          ),
          ListTile(
            leading: const Icon(Icons.delete_outline),
            title: const Text('删除'),
            onTap: () async {
              Navigator.pop(context);
              await onDelete(song);
            },
          ),
        ],
      ),
    );
  }
}


class PlaylistsTab extends StatelessWidget {
  const PlaylistsTab({
    super.key,
    required this.playlists,
    required this.loading,
    required this.onOpen,
    required this.selectedPlaylist,
    this.onImportPressed,
  });

  final List<PlaylistSummary> playlists;
  final bool loading;
  final Future<void> Function(PlaylistSummary playlist) onOpen;
  final PlaylistDetail? selectedPlaylist;
  final Future<void> Function()? onImportPressed;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        if (loading)
          const Center(child: CircularProgressIndicator())
        else
          ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 88),
            itemCount: playlists.length,
            separatorBuilder: (_, _) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final playlist = playlists[index];
              final selected = selectedPlaylist?.id == playlist.id;
              return Card(
                color: selected ? Theme.of(context).colorScheme.primaryContainer : null,
                child: ListTile(
                  leading: const CircleAvatar(child: Icon(Icons.queue_music)),
                  title: Text(playlist.name),
                  subtitle: Text('${playlist.songCount} 首歌 · ${playlist.sourceType}'),
                  onTap: () => onOpen(playlist),
                ),
              );
            },
          ),
        if (onImportPressed != null)
          Positioned(
            right: 16,
            bottom: 16,
            child: FloatingActionButton.extended(
              heroTag: 'playlist_import_fab',
              onPressed: onImportPressed,
              icon: const Icon(Icons.add),
              label: const Text('导入歌单'),
            ),
          ),
      ],
    );
  }
}

class PlaylistDetailSheet extends StatelessWidget {
  const PlaylistDetailSheet({
    super.key,
    required this.playlist,
    required this.librarySongs,
    required this.onPlayPlaylistSong,
  });

  final PlaylistDetail playlist;
  final List<LibrarySong> librarySongs;
  final Future<void> Function(PlaylistSong song) onPlayPlaylistSong;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(playlist.name)),
      body: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: playlist.songs.length,
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final song = playlist.songs[index];
          final playable = librarySongs.any(
            (item) =>
                item.title.toLowerCase() == song.title.toLowerCase() &&
                item.artist.toLowerCase() == song.artist.toLowerCase(),
          );
          return ListTile(
            leading: CircleAvatar(child: Text('${song.orderIndex + 1}')),
            title: Text(song.title),
            subtitle: Text([
              song.artist,
              if (song.bpm != null) '${song.bpm} BPM',
              if (song.tags.isNotEmpty) song.tags.join(', '),
            ].join(' · ')),
            trailing: playable ? const Icon(Icons.play_circle_outline) : null,
            onTap: playable ? () => onPlayPlaylistSong(song) : null,
          );
        },
      ),
    );
  }
}

class MiniPlayer extends StatefulWidget {
  const MiniPlayer({
    super.key,
    required this.song,
    required this.isPlaying,
    required this.position,
    required this.duration,
    required this.onToggle,
    required this.onSeek,
    this.prefetchPercent,
    this.prefetchMessage,
  });

  final LibrarySong song;
  final bool isPlaying;
  final Duration position;
  final Duration duration;
  final Future<void> Function() onToggle;
  final Future<void> Function(double value) onSeek;
  final double? prefetchPercent;
  final String? prefetchMessage;

  @override
  State<MiniPlayer> createState() => _MiniPlayerState();
}

class _MiniPlayerState extends State<MiniPlayer> {
  // 非空表示用户正在拖动，使用本地值显示，停止下发 seek。
  // 松手后保留一段时间（直到外部 position 追上 _latchTarget），
  // 防止外部 1Hz 轮询把 UI 拽回旧位置。
  double? _dragValue;
  double? _latchTarget;
  DateTime? _latchUntil;

  @override
  Widget build(BuildContext context) {
    final song = widget.song;
    final duration = widget.duration;
    final position = widget.position;
    final isPlaying = widget.isPlaying;
    final onToggle = widget.onToggle;
    final onSeek = widget.onSeek;
    final prefetchPercent = widget.prefetchPercent;
    final prefetchMessage = widget.prefetchMessage;

    final maxSeconds = duration.inSeconds > 0
        ? duration.inSeconds.toDouble()
        : (song.duration > 0 ? song.duration.toDouble() : 1.0);
    final livePosition =
        position.inMilliseconds.clamp(0, (maxSeconds * 1000).toInt()) / 1000.0;
    // 松手后的"latch"：在 _latchUntil 截止前 OR 直到 livePosition 追上 _latchTarget，
    // 优先用 _latchTarget 显示，避免被旧的 RK position 拽回去。
    double sliderValue;
    if (_dragValue != null) {
      sliderValue = _dragValue!;
    } else if (_latchTarget != null) {
      final until = _latchUntil;
      final expired = until != null && DateTime.now().isAfter(until);
      final caughtUp = (livePosition - _latchTarget!).abs() < 1.0;
      if (expired || caughtUp) {
        _latchTarget = null;
        _latchUntil = null;
        sliderValue = livePosition;
      } else {
        sliderValue = _latchTarget!;
      }
    } else {
      sliderValue = livePosition;
    }
    final currentSeconds = sliderValue.clamp(0.0, maxSeconds);
    final prefetching = prefetchPercent != null;
    final displayedPosition = Duration(
      milliseconds: (currentSeconds * 1000).round(),
    );
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  const CircleAvatar(child: Icon(Icons.graphic_eq)),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(song.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                        Text(song.artist, style: Theme.of(context).textTheme.bodySmall),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: prefetching ? null : onToggle,
                    icon: Icon(isPlaying ? Icons.pause_circle_filled : Icons.play_circle_fill),
                  ),
                ],
              ),
              if (prefetching) ...[
                const SizedBox(height: 4),
                LinearProgressIndicator(
                  value: (prefetchPercent! / 100).clamp(0.0, 1.0),
                ),
                const SizedBox(height: 4),
                Text(
                  prefetchMessage ?? '正在拉取到 RK',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ] else ...[
                Slider(
                  value: currentSeconds,
                  max: maxSeconds,
                  onChangeStart: (value) {
                    setState(() {
                      _dragValue = value;
                      _latchTarget = null;
                      _latchUntil = null;
                    });
                  },
                  onChanged: (value) {
                    setState(() => _dragValue = value);
                  },
                  onChangeEnd: (value) {
                    setState(() {
                      _dragValue = null;
                      // 松手后短暂锁住 UI 显示在 value，直到 RK 轮询追上
                      _latchTarget = value;
                      _latchUntil =
                          DateTime.now().add(const Duration(milliseconds: 1500));
                    });
                    onSeek(value);
                  },
                ),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(_formatDuration(displayedPosition)),
                    Text(_formatDuration(duration)),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _formatDuration(Duration value) {
    final total = value.inSeconds;
    final minutes = total ~/ 60;
    final seconds = total % 60;
    return '$minutes:${seconds.toString().padLeft(2, '0')}';
  }
}

class StatCard extends StatelessWidget {
  const StatCard({super.key, required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label),
            const SizedBox(height: 8),
            Text(value, style: Theme.of(context).textTheme.headlineSmall),
          ],
        ),
      ),
    );
  }
}

class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}

class SongSummaryTile extends StatelessWidget {
  const SongSummaryTile({super.key, required this.song});

  final LibrarySong song;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const CircleAvatar(child: Icon(Icons.music_note)),
      title: Text(song.title),
      subtitle: Text([song.artist, song.analysisStatus].join(' · ')),
    );
  }
}
