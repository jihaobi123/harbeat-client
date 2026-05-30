import 'dart:async';

import 'package:flutter/material.dart';

import '../api_client.dart';
import '../edge_agent_client.dart';
import '../models.dart';
import '../sync_worker_client.dart';

/// 详情页：展示歌曲基本信息、分析状态、段落、音轨；
/// 自动后台轮询直到分析完成。
///
/// 播放路由：所有声音都从 RK3588 出，不走手机本地。
///   - 完整曲/段落：edge-agent /play + /seek
///   - 音轨切换：edge-agent /stem_solo（在已加载文件上即时独奏）
///   - 进度：edge-agent /state 1s 轮询
class SongDetailPage extends StatefulWidget {
  const SongDetailPage({
    super.key,
    required this.apiClient,
    required this.session,
    required this.song,
  });

  final HarBeatApiClient apiClient;
  final SessionBundle session;
  final LibrarySong song;

  @override
  State<SongDetailPage> createState() => _SongDetailPageState();
}

class _SongDetailPageState extends State<SongDetailPage> {
  late LibrarySong _song;
  late EdgeAgentClient _edge;
  late SyncWorkerClient _sync;

  Timer? _poller;
  Timer? _statePoller;
  bool _busy = false;
  String? _error;

  // 缓存拉取进度提示
  double? _prefetchPercent;
  String? _prefetchMessage;

  // 防止 /state 轮询在拖动后把进度条拽回
  DateTime? _seekGuardUntil;

  /// 'full' | 'vocals' | 'drums' | 'bass' | 'other'
  String _activeSource = 'full';
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  bool _playing = false;
  bool _loaded = false; // RK 是否已加载本曲（决定 stem_solo / seek 能否直接打）

  @override
  void initState() {
    super.initState();
    _song = widget.song;
    // 复用 main.dart 注入的服务地址；这里用环境默认值 + 局域网 IP，跟 home_page 保持一致。
    // 上层页面已经在 widget.session 里传了 token，但 RK base url 由用户在主页设置里改，
    // 这里直接用代码里默认 192.168.43.7:9000，并支持后续从 inheritedWidget/参数覆盖。
    _edge = EdgeAgentClient(baseUrl: 'http://192.168.43.7:9000');
    _sync = SyncWorkerClient(baseUrl: 'http://192.168.43.7:9100');
    _refreshDetail();
  }

  @override
  void dispose() {
    _poller?.cancel();
    _statePoller?.cancel();
    super.dispose();
  }

  bool get _isPendingLike {
    final s = _song.analysisStatus.toLowerCase();
    return s == 'pending' || s == 'running' || s == 'processing' || s == 'queued';
  }

  void _ensurePoller() {
    if (_isPendingLike) {
      _poller ??= Timer.periodic(const Duration(seconds: 4), (_) => _refreshDetail());
    } else {
      _poller?.cancel();
      _poller = null;
    }
  }

  Future<void> _refreshDetail() async {
    try {
      final fresh = await widget.apiClient.getLibrarySong(
        token: widget.session.token,
        songId: _song.id,
      );
      if (!mounted) return;
      setState(() => _song = fresh);
      _ensurePoller();
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '刷新失败: $e');
    }
  }

  Future<void> _analyzeAgain() async {
    setState(() => _busy = true);
    try {
      final updated = await widget.apiClient.analyzeSong(
        token: widget.session.token,
        songId: _song.id,
      );
      if (!mounted) return;
      setState(() => _song = updated);
      _ensurePoller();
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '分析失败: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _separateStems() async {
    setState(() => _busy = true);
    try {
      await widget.apiClient.separateStems(
        token: widget.session.token,
        songId: _song.id,
      );
      await _refreshDetail();
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '分轨失败: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  // ── RK 播放快路径 ────────────────────────────────────────────────

  /// 试一次直接 /play；命中返回 true。
  Future<bool> _tryDirectPlay({double startAtSec = 0.0}) async {
    try {
      final res = await _edge.play(
        songId: _song.id,
        startAtSec: startAtSec,
      );
      return res['ok'] == true ||
          (res['result'] is Map && (res['result'] as Map)['ok'] == true);
    } catch (_) {
      return false;
    }
  }

  /// 让 RK 加载本曲：缓存命中立即 /play；否则触发 sync 并 200ms 轮询 /cache/check，
  /// 文件一落盘就 /play。最多等 8 秒，仍未命中再回退到 syncAndWait（兼容慢网/大文件）。
  /// 仅同步 original mp3——stem 由 [_ensureStemCached] 单独拉取，避免大 stem 文件
  /// 拖慢首播出声。
  /// 返回是否成功开始播放（出声）。
  Future<bool> _ensureLoaded({double startAtSec = 0.0}) async {
    // 1) 直接试 /play
    if (await _tryDirectPlay(startAtSec: startAtSec)) {
      _loaded = true;
      _startStatePolling();
      return true;
    }

    // 2) 触发 sync + 轮询 cache 落盘
    setState(() {
      _prefetchPercent = 0;
      _prefetchMessage = '请求 RK 缓存…';
    });
    final tracks = [
      <String, dynamic>{
        'song_id': _song.id,
        'files': <String, dynamic>{
          'original': <String, dynamic>{
            'url': widget.apiClient.streamUrl(
              token: widget.session.token,
              songId: _song.id,
            ),
            'format': 'mp3',
          },
        },
      }
    ];
    unawaited(() async {
      try {
        await _sync.startSync(
          tracks: tracks,
          planId: 'detail-${_song.id}',
        );
      } catch (_) {/* already running 也算成功 */}
    }());

    final deadline = DateTime.now().add(const Duration(seconds: 8));
    while (DateTime.now().isBefore(deadline)) {
      if (!mounted) return false;
      if (await _sync.cacheExists(_song.id)) {
        if (await _tryDirectPlay(startAtSec: startAtSec)) {
          _loaded = true;
          if (mounted) {
            setState(() {
              _prefetchPercent = null;
              _prefetchMessage = null;
            });
          }
          _startStatePolling();
          return true;
        }
      }
      try {
        final st = await _sync.getStatus();
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

    // 3) 兜底：syncAndWait 等到底
    try {
      await _sync.syncAndWait(
        tracks: tracks,
        planId: 'detail-${_song.id}',
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
    } catch (e) {
      if (!mounted) return false;
      setState(() {
        _error = '拉取到 RK 失败: $e';
        _prefetchPercent = null;
        _prefetchMessage = null;
      });
      return false;
    }

    if (await _tryDirectPlay(startAtSec: startAtSec)) {
      _loaded = true;
      if (mounted) {
        setState(() {
          _prefetchPercent = null;
          _prefetchMessage = null;
        });
      }
      _startStatePolling();
      return true;
    }
    if (mounted) {
      setState(() {
        _error = 'RK 播放失败';
        _prefetchPercent = null;
        _prefetchMessage = null;
      });
    }
    return false;
  }

  void _startStatePolling() {
    _statePoller?.cancel();
    _statePoller = Timer.periodic(const Duration(seconds: 1), (_) async {
      try {
        final st = await _edge.getState();
        if (!mounted) return;
        if (st.error != null) return;
        setState(() {
          _playing = st.playing;
          final guard = _seekGuardUntil;
          final inGuard = guard != null && DateTime.now().isBefore(guard);
          if (!inGuard) {
            _position =
                Duration(milliseconds: (st.positionSec * 1000).round());
          }
          if (st.durationSec > 0) {
            _duration =
                Duration(milliseconds: (st.durationSec * 1000).round());
          } else if (_duration == Duration.zero && _song.duration > 0) {
            _duration =
                Duration(milliseconds: (_song.duration * 1000).round());
          }
        });
      } catch (_) {/* 静默 */}
    });
  }

  // ── UI 行为 ────────────────────────────────────────────────────────

  /// 切音轨：如果 RK 还没加载本曲，先 _ensureLoaded；之后只发 /stem_solo。
  /// 关键：调用 /stem_solo 之前必须保证目标 stem 的 .mp3 已经落盘到 RK，
  /// 否则 audio-engine 会抛 409（stem 未加载）。
  Future<void> _switchSource(String which) async {
    if (which == _activeSource && _loaded) return;
    setState(() {
      _activeSource = which;
      _error = null;
    });
    if (!_loaded) {
      // 首次加载：先把 original mp3 拉到 RK 让出声，stem 异步等。
      final ok = await _ensureLoaded(startAtSec: 0.0);
      if (!ok) return;
    }
    // 任何切到 stem 的情况都要确保 stem 文件已落盘
    if (which != 'full') {
      final stemReady = await _ensureStemCached(which);
      if (!stemReady) return;
    }
    try {
      await _edge.stemSolo(which == 'full' ? null : which);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '切换音轨失败: $e');
    }
  }

  /// 拉取指定 stem 到 RK 缓存；返回是否最终落盘。
  /// 命中已有文件秒返回。
  Future<bool> _ensureStemCached(String stem) async {
    // 已经在缓存里 → 跳过
    final preCheck =
        await _checkStemFile(stem); // 通过 sync-worker /cache/check 不够，因为它只看 original
    if (preCheck) return true;

    setState(() {
      _prefetchPercent = 0;
      _prefetchMessage = '正在拉取 ${_sourceLabel(stem)} 到 RK 缓存…';
    });
    final tracks = [
      <String, dynamic>{
        'song_id': _song.id,
        'files': <String, dynamic>{
          'stems': <String, dynamic>{
            stem: <String, dynamic>{
              'url': widget.apiClient.stemStreamUrl(
                token: widget.session.token,
                songId: _song.id,
                stemName: stem,
              ),
              'format': 'mp3',
            },
          },
        },
      }
    ];
    try {
      await _sync.syncAndWait(
        tracks: tracks,
        planId: 'detail-${_song.id}-$stem',
        timeout: const Duration(minutes: 2),
        onProgress: (st) {
          if (!mounted) return;
          setState(() {
            _prefetchPercent = st.percent;
            _prefetchMessage =
                '正在拉取 ${_sourceLabel(stem)} ${st.percent.toStringAsFixed(0)}%';
          });
        },
      );
      if (mounted) {
        setState(() {
          _prefetchPercent = null;
          _prefetchMessage = null;
        });
      }
      return true;
    } catch (e) {
      if (!mounted) return false;
      setState(() {
        _error = '拉取分轨失败: $e';
        _prefetchPercent = null;
        _prefetchMessage = null;
      });
      return false;
    }
  }

  /// sync-worker 的 /cache/check 当前只看 original.*。我们在 stem 是否已落盘上
  /// 简单复用 syncAndWait 的"命中跳过"逻辑——syncAndWait 内部见 sha256/size 一致
  /// 会直接 mark_done 并返回，不会重下载。所以这里直接返回 false 让上层去 syncAndWait
  /// （第一次拉取会真下，后续命中会秒返回）。
  Future<bool> _checkStemFile(String stem) async => false;

  Future<void> _togglePlay() async {
    try {
      if (!_loaded) {
        await _ensureLoaded(startAtSec: 0.0);
        return;
      }
      if (_playing) {
        await _edge.pause();
        if (mounted) setState(() => _playing = false);
      } else {
        await _edge.resume();
        if (mounted) setState(() => _playing = true);
        _startStatePolling();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '播放失败: $e');
    }
  }

  /// 跳到 [target]。如果 RK 还没加载本曲，直接以 startAtSec 启动播放。
  Future<void> _seekTo(Duration target) async {
    final sec = target.inMilliseconds / 1000.0;
    if (!_loaded) {
      await _ensureLoaded(startAtSec: sec);
      return;
    }
    setState(() {
      _position = target;
      _seekGuardUntil =
          DateTime.now().add(const Duration(milliseconds: 1000));
    });
    try {
      await _edge.seek(sec);
    } catch (_) {
      try {
        await _edge.play(songId: _song.id, startAtSec: sec);
      } catch (e) {
        if (!mounted) return;
        setState(() => _error = '跳转失败: $e');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(_song.title, overflow: TextOverflow.ellipsis),
        actions: [
          IconButton(
            tooltip: '刷新',
            onPressed: _busy ? null : _refreshDetail,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _buildHeaderCard(theme),
          const SizedBox(height: 12),
          _buildPlayerCard(theme),
          const SizedBox(height: 12),
          _buildStemsCard(theme),
          const SizedBox(height: 12),
          _buildSegmentsCard(theme),
          const SizedBox(height: 12),
          _buildInfoCard(theme),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Card(
              color: theme.colorScheme.errorContainer,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(_error!,
                    style: TextStyle(color: theme.colorScheme.onErrorContainer)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildHeaderCard(ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_song.title, style: theme.textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(_song.artist, style: theme.textTheme.bodyMedium),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _statusChip(theme),
                if (_song.bpm != null)
                  _infoChip(Icons.speed, '${_song.bpm!.toStringAsFixed(1)} BPM'),
                if ((_song.key ?? '').isNotEmpty)
                  _infoChip(Icons.music_note, '${_song.key}'),
                if ((_song.camelotKey ?? '').isNotEmpty)
                  _infoChip(Icons.label_outline, _song.camelotKey!),
                if (_song.duration > 0)
                  _infoChip(Icons.schedule, _formatDuration(_song.duration)),
                if (_song.energy != null)
                  _infoChip(Icons.bolt, '能量 ${_song.energy!.toStringAsFixed(2)}'),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: _busy ? null : _analyzeAgain,
                  icon: const Icon(Icons.analytics_outlined, size: 18),
                  label: const Text('重新分析'),
                ),
                if (!_song.hasStems)
                  OutlinedButton.icon(
                    onPressed: _busy ? null : _separateStems,
                    icon: const Icon(Icons.graphic_eq, size: 18),
                    label: const Text('分离音轨'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _statusChip(ThemeData theme) {
    final s = _song.analysisStatus.toLowerCase();
    Color bg;
    Color fg;
    String label;
    Widget leading;
    switch (s) {
      case 'completed':
      case 'done':
      case 'success':
        bg = Colors.green.shade50;
        fg = Colors.green.shade800;
        label = '已完成';
        leading = const Icon(Icons.check_circle, size: 16, color: Colors.green);
        break;
      case 'failed':
      case 'error':
        bg = Colors.red.shade50;
        fg = Colors.red.shade800;
        label = '分析失败';
        leading = const Icon(Icons.error_outline, size: 16, color: Colors.red);
        break;
      case 'pending':
      case 'queued':
      case 'running':
      case 'processing':
        bg = Colors.orange.shade50;
        fg = Colors.orange.shade900;
        label = s == 'pending' || s == 'queued' ? '等待分析' : '分析中…';
        leading = const SizedBox(
          width: 14,
          height: 14,
          child: CircularProgressIndicator(strokeWidth: 2),
        );
        break;
      default:
        bg = theme.colorScheme.surfaceContainerHighest;
        fg = theme.colorScheme.onSurfaceVariant;
        label = '未分析';
        leading = const Icon(Icons.help_outline, size: 16);
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          leading,
          const SizedBox(width: 6),
          Text(label, style: TextStyle(color: fg, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Widget _infoChip(IconData icon, String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.grey.shade100,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: Colors.grey.shade700),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(color: Colors.grey.shade800)),
        ],
      ),
    );
  }

  Widget _buildPlayerCard(ThemeData theme) {
    final total = _duration.inMilliseconds <= 0
        ? Duration(seconds: _song.duration.toInt())
        : _duration;
    final value = total.inMilliseconds == 0
        ? 0.0
        : (_position.inMilliseconds / total.inMilliseconds).clamp(0.0, 1.0);
    final prefetching = _prefetchPercent != null;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Slider(
              value: value,
              onChanged: (v) {
                if (total.inMilliseconds > 0) {
                  setState(() {
                    _position = Duration(
                        milliseconds: (v * total.inMilliseconds).toInt());
                  });
                }
              },
              onChangeEnd: (v) {
                if (total.inMilliseconds > 0) {
                  _seekTo(Duration(
                      milliseconds: (v * total.inMilliseconds).toInt()));
                }
              },
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_formatPosition(_position)),
                Text(_formatPosition(total)),
              ],
            ),
            const SizedBox(height: 4),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                IconButton(
                  iconSize: 36,
                  onPressed: prefetching ? null : _togglePlay,
                  icon: Icon(_playing ? Icons.pause_circle : Icons.play_circle),
                ),
              ],
            ),
            if (prefetching) ...[
              const SizedBox(height: 4),
              LinearProgressIndicator(
                value: (_prefetchPercent! / 100).clamp(0.0, 1.0),
              ),
              const SizedBox(height: 4),
              Text(
                _prefetchMessage ?? '正在拉取到 RK',
                style: theme.textTheme.bodySmall,
              ),
            ],
            Text(
              '当前音源: ${_sourceLabel(_activeSource)} · 播放: RK3588',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }

  String _sourceLabel(String key) {
    switch (key) {
      case 'vocals':
        return '人声';
      case 'drums':
        return '鼓组';
      case 'bass':
        return '贝斯';
      case 'other':
        return '其他';
      default:
        return '完整曲';
    }
  }

  Widget _buildStemsCard(ThemeData theme) {
    final available = _song.hasStems;
    final sources = ['full', 'vocals', 'drums', 'bass', 'other'];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.graphic_eq, size: 18),
                const SizedBox(width: 6),
                Text('音轨切换', style: theme.textTheme.titleMedium),
                const Spacer(),
                if (!available)
                  Text('未分轨', style: theme.textTheme.bodySmall),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final s in sources)
                  ChoiceChip(
                    label: Text(_sourceLabel(s)),
                    selected: _activeSource == s,
                    onSelected: (s == 'full' || available)
                        ? (_) => _switchSource(s)
                        : null,
                  ),
              ],
            ),
            if (!available) ...[
              const SizedBox(height: 8),
              Text(
                '尚未生成分轨。点击上方「分离音轨」开始（后台执行，完成后会自动刷新）。',
                style: theme.textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildSegmentsCard(ThemeData theme) {
    final cues = _song.cuePoints;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.flag_outlined, size: 18),
                const SizedBox(width: 6),
                Text('段落 / Cue', style: theme.textTheme.titleMedium),
                const Spacer(),
                Text('${cues.length} 个', style: theme.textTheme.bodySmall),
              ],
            ),
            const SizedBox(height: 12),
            if (cues.isEmpty)
              Text(
                _isPendingLike
                    ? '正在分析，完成后将自动显示段落…'
                    : '尚无段落标记。可点击「重新分析」生成。',
                style: theme.textTheme.bodySmall,
              )
            else
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final cue in cues)
                    ActionChip(
                      avatar: const Icon(Icons.play_arrow, size: 16),
                      label: Text(
                        '${cue.label.isEmpty ? "Cue" : cue.label}  ${_formatDuration(cue.time)}',
                      ),
                      onPressed: () =>
                          _seekTo(Duration(milliseconds: (cue.time * 1000).toInt())),
                    ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoCard(ThemeData theme) {
    final mb = (_song.fileSize / 1024 / 1024).toStringAsFixed(2);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('基本信息', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            _kv('格式', _song.format),
            _kv('大小', '$mb MB'),
            if (_song.sourceType.isNotEmpty) _kv('来源', _song.sourceType),
            _kv('Beat 数', '${_song.beatPoints.length}'),
            _kv('入库时间', _song.createdAt),
            _kv('歌曲 ID', _song.id, mono: true),
          ],
        ),
      ),
    );
  }

  Widget _kv(String k, String v, {bool mono = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 80,
            child: Text(k, style: TextStyle(color: Colors.grey.shade600)),
          ),
          Expanded(
            child: Text(
              v,
              style: TextStyle(
                fontFamily: mono ? 'monospace' : null,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _formatDuration(double seconds) {
    final total = seconds.round();
    final m = (total ~/ 60).toString().padLeft(2, '0');
    final s = (total % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  String _formatPosition(Duration d) {
    final m = (d.inMinutes).toString().padLeft(2, '0');
    final s = (d.inSeconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }
}
