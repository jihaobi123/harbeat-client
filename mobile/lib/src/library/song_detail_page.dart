import 'dart:async';

import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import '../api_client.dart';
import '../models.dart';

/// 详情页：展示歌曲基本信息、分析状态、段落、音轨；
/// 自动后台轮询直到分析完成。
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
  final AudioPlayer _player = AudioPlayer();
  StreamSubscription<Duration>? _posSub;
  StreamSubscription<Duration?>? _durSub;
  StreamSubscription<PlayerState>? _stateSub;

  Timer? _poller;
  bool _busy = false;
  String? _error;

  /// 'full' | 'vocals' | 'drums' | 'bass' | 'other'
  String _activeSource = 'full';
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  bool _playing = false;

  @override
  void initState() {
    super.initState();
    _song = widget.song;
    _posSub = _player.positionStream.listen((v) {
      if (mounted) setState(() => _position = v);
    });
    _durSub = _player.durationStream.listen((v) {
      if (mounted) setState(() => _duration = v ?? Duration.zero);
    });
    _stateSub = _player.playerStateStream.listen((s) {
      if (mounted) setState(() => _playing = s.playing);
    });
    // 立刻拉一次最新详情（避免列表里是旧数据），并按需启动轮询
    _refreshDetail();
  }

  @override
  void dispose() {
    _poller?.cancel();
    _posSub?.cancel();
    _durSub?.cancel();
    _stateSub?.cancel();
    _player.dispose();
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
      // 分轨是后台任务，刷新一下；后续若状态变化由 _ensurePoller 处理
      await _refreshDetail();
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '分轨失败: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _switchSource(String which) async {
    if (which == _activeSource && _player.audioSource != null) return;
    final wasPlaying = _player.playing;
    final keepPos = _position;
    final url = which == 'full'
        ? widget.apiClient.streamUrl(
            token: widget.session.token,
            songId: _song.id,
          )
        : widget.apiClient.stemStreamUrl(
            token: widget.session.token,
            songId: _song.id,
            stemName: which,
          );
    try {
      setState(() {
        _activeSource = which;
        _error = null;
      });
      await _player.setUrl(url);
      // 切换不同源时尽量保持当前进度，提供 stems 对齐的播放体验
      if (keepPos > Duration.zero) {
        await _player.seek(keepPos);
      }
      if (wasPlaying) {
        await _player.play();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '切换音轨失败: $e');
    }
  }

  Future<void> _togglePlay() async {
    try {
      if (_player.audioSource == null) {
        await _switchSource(_activeSource);
      }
      if (_player.playing) {
        await _player.pause();
      } else {
        await _player.play();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '播放失败: $e');
    }
  }

  Future<void> _seekTo(Duration target) async {
    try {
      if (_player.audioSource == null) {
        await _switchSource(_activeSource);
      }
      await _player.seek(target);
      if (!_player.playing) {
        await _player.play();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '跳转失败: $e');
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
    Widget? leading;
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
          if (leading != null) ...[leading, const SizedBox(width: 6)],
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
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Slider(
              value: value,
              onChanged: (v) {
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
                  onPressed: _togglePlay,
                  icon: Icon(_playing ? Icons.pause_circle : Icons.play_circle),
                ),
              ],
            ),
            Text(
              '当前音源: ${_sourceLabel(_activeSource)}',
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
