import 'dart:async';

import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import 'api_client.dart';
import 'models.dart';

// =========================================================================== //
// DJ Control 5-step wizard (mobile)
//   1) 选歌 — 导入歌单（可勾选子集）/ Vibe 搜索（+时长自动选满）/ 舞种+时长
//   2) 排歌 — 街舞场景能量曲线（贪心分配）
//   3) 混音 — 7+11 现有方案 + BPM 差衔接提示 + ▶ 开始混音播放
//   4) 切歌 — 实时播放中：快切 / 升能量切 / 降能量切（POST /api/dj/cut/plan）
//   5) 加花 — 实时播放中：街舞 DJ FX Pad（叠在主混音之上）
// =========================================================================== //

class DjControlPage extends StatefulWidget {
  const DjControlPage({
    super.key,
    required this.apiClient,
    required this.token,
    required this.userId,
    required this.librarySongs,
  });

  final HarBeatApiClient apiClient;
  final String token;
  final int userId;
  final List<LibrarySong> librarySongs;

  @override
  State<DjControlPage> createState() => _DjControlPageState();
}

class _DjControlPageState extends State<DjControlPage> {
  int _step = 0; // 0..4

  // Selection state
  final List<LibrarySong> _picked = [];

  // Sequence state
  List<Map<String, dynamic>> _presets = const [];
  String _preset = 'battle_4rounds';
  List<Map<String, dynamic>> _sequence = const [];
  bool _seqLoading = false;
  String? _seqError;

  // Mix rules + FX catalog
  Map<String, dynamic>? _rules;
  List<Map<String, dynamic>> _fxItems = const [];

  // Playlists for import
  List<PlaylistSummary> _playlists = const [];

  // ---- Live mix player state ----
  final AudioPlayer _mainPlayer = AudioPlayer();
  final AudioPlayer _fxPlayer = AudioPlayer();
  bool _liveStarted = false;
  int _liveIdx = 0;
  bool _isPlaying = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  String? _cutInfo;
  StreamSubscription<Duration>? _posSub;
  StreamSubscription<Duration?>? _durSub;
  StreamSubscription<PlayerState>? _stateSub;

  @override
  void initState() {
    super.initState();
    _loadCatalogs();
    _posSub = _mainPlayer.positionStream.listen((p) {
      if (mounted) setState(() => _position = p);
    });
    _durSub = _mainPlayer.durationStream.listen((d) {
      if (mounted) setState(() => _duration = d ?? Duration.zero);
    });
    _stateSub = _mainPlayer.playerStateStream.listen((s) {
      if (!mounted) return;
      setState(() => _isPlaying = s.playing);
      if (s.processingState == ProcessingState.completed) {
        _advanceLive();
      }
    });
  }

  Future<void> _loadCatalogs() async {
    try {
      final futures = await Future.wait([
        widget.apiClient.djSequencePresetsMeta(token: widget.token),
        widget.apiClient.djListTransitionRules(token: widget.token),
        widget.apiClient.djListFx(token: widget.token),
        widget.apiClient.getPlaylists(token: widget.token, userId: widget.userId)
            .catchError((_) => <PlaylistSummary>[]),
      ]);
      if (!mounted) return;
      setState(() {
        _presets = (futures[0] as List).cast<Map<String, dynamic>>();
        if (_presets.isNotEmpty) _preset = _presets.first['key'] as String;
        _rules = futures[1] as Map<String, dynamic>;
        _fxItems = (futures[2] as List).cast<Map<String, dynamic>>();
        _playlists = (futures[3] as List).cast<PlaylistSummary>();
      });
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('加载目录失败: $e')),
      );
    }
  }

  @override
  void dispose() {
    _posSub?.cancel();
    _durSub?.cancel();
    _stateSub?.cancel();
    _mainPlayer.dispose();
    _fxPlayer.dispose();
    super.dispose();
  }

  // ---------------- Selection helpers ---------------- //
  void _addSongs(Iterable<LibrarySong> songs) {
    final ids = {for (final s in _picked) s.id};
    final added = <LibrarySong>[];
    for (final s in songs) {
      if (!ids.contains(s.id)) {
        ids.add(s.id);
        added.add(s);
      }
    }
    if (added.isEmpty) return;
    setState(() {
      _picked.addAll(added);
      _sequence = const [];
    });
  }

  void _removeSong(String id) {
    setState(() {
      _picked.removeWhere((s) => s.id == id);
      _sequence = const [];
    });
  }

  // ---------------- Sequence ---------------- //
  Future<void> _runSequence() async {
    if (_picked.length < 2) {
      setState(() => _seqError = '至少选 2 首才能排序');
      return;
    }
    setState(() {
      _seqLoading = true;
      _seqError = null;
      _sequence = const [];
    });
    try {
      final r = await widget.apiClient.djSequence(
        token: widget.token,
        songIds: _picked.map((s) => s.id).toList(),
        preset: _preset,
      );
      setState(() => _sequence = r);
    } catch (e) {
      setState(() => _seqError = e.toString());
    } finally {
      if (mounted) setState(() => _seqLoading = false);
    }
  }

  // ---------------- Live mix ---------------- //
  List<LibrarySong> _orderedSongs() {
    final byId = {for (final s in _picked) s.id: s};
    if (_sequence.isEmpty) return List.of(_picked);
    return _sequence
        .map((e) => byId[e['song_id']?.toString()])
        .whereType<LibrarySong>()
        .toList();
  }

  Future<void> _startLiveMix() async {
    final ordered = _orderedSongs();
    if (ordered.isEmpty) return;
    setState(() {
      _liveStarted = true;
      _liveIdx = 0;
      _step = 3; // jump to Step 4 (切歌)
    });
    await _loadAndPlay(ordered[0]);
  }

  Future<void> _loadAndPlay(LibrarySong song) async {
    try {
      final url = widget.apiClient.streamUrl(songId: song.id, token: widget.token);
      await _mainPlayer.setUrl(url);
      await _mainPlayer.play();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('播放失败: $e')),
      );
    }
  }

  Future<void> _advanceLive() async {
    final ordered = _orderedSongs();
    final next = _liveIdx + 1;
    if (next >= ordered.length) {
      await _mainPlayer.stop();
      setState(() => _isPlaying = false);
      return;
    }
    setState(() {
      _liveIdx = next;
      _cutInfo = null;
    });
    await _loadAndPlay(ordered[next]);
  }

  Future<void> _togglePlay() async {
    if (_isPlaying) {
      await _mainPlayer.pause();
    } else {
      await _mainPlayer.play();
    }
  }

  Future<void> _doCut(String strategy) async {
    final ordered = _orderedSongs();
    if (ordered.isEmpty) return;
    final current = ordered[_liveIdx];
    final queue = ordered.map((s) => s.id).toList();
    final pool = _picked.map((s) => s.id).toList();
    try {
      final plan = await widget.apiClient.djPlanCut(
        token: widget.token,
        strategy: strategy,
        currentSongId: current.id,
        cursorSec: _position.inMilliseconds / 1000.0,
        queueSongIds: queue,
        currentIndex: _liveIdx,
        poolSongIds: pool,
      );
      final chosenId = plan['chosen_song_id']?.toString();
      final switchAt = (plan['switch_at_sec'] as num?)?.toDouble();
      if (chosenId != null) {
        final hit = ordered.indexWhere((s) => s.id == chosenId);
        setState(() {
          _cutInfo = '⏭ $strategy → ${hit >= 0 ? '队列 #${hit + 1}' : chosenId} '
              '${switchAt != null ? '@${switchAt.toStringAsFixed(2)}s' : ''}';
        });
        if (hit >= 0) {
          setState(() => _liveIdx = hit);
          await _loadAndPlay(ordered[hit]);
        } else {
          final byId = {for (final s in _picked) s.id: s};
          final pick = byId[chosenId];
          if (pick != null) {
            setState(() {
              _picked.removeWhere((s) => s.id == pick.id);
              _picked.insert(0, pick);
              _liveIdx = 0;
            });
            await _loadAndPlay(pick);
          }
        }
      } else {
        setState(() => _cutInfo = '⏭ $strategy → 无可换曲');
      }
    } catch (e) {
      setState(() => _cutInfo = '切歌失败: $e');
    }
  }

  Future<void> _playFx(String key) async {
    try {
      await _fxPlayer.stop();
      await _fxPlayer.setUrl(widget.apiClient.djFxAudioUrl(key));
      await _fxPlayer.play();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('FX 失败: $e')),
      );
    }
  }

  // ---------------- Build ---------------- //
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _StepHeader(
          step: _step,
          pickedCount: _picked.length,
          sequencedCount: _sequence.length,
          liveStarted: _liveStarted,
          onJump: (i) => setState(() => _step = i),
        ),
        if (_liveStarted) _LiveMixBar(
          ordered: _orderedSongs(),
          idx: _liveIdx,
          isPlaying: _isPlaying,
          position: _position,
          duration: _duration,
          onPlayPause: _togglePlay,
          onNext: _advanceLive,
          cutInfo: _cutInfo,
        ),
        Expanded(child: _buildStepBody()),
        _StepFooter(
          step: _step,
          canPrev: _step > 0,
          canNext: _canGoNext(),
          onPrev: () => setState(() => _step = _step - 1),
          onNext: _onNext,
        ),
      ],
    );
  }

  bool _canGoNext() {
    if (_step == 0) return _picked.length >= 2;
    if (_step == 1) return _sequence.isNotEmpty;
    if (_step == 2) return true; // Step 3 → start live + go to Step 4
    if (_step == 3) return true; // Step 4 → Step 5
    return false; // Step 5 last
  }

  Future<void> _onNext() async {
    if (_step == 2) {
      // From "混音" to "切歌" → start live mix
      if (!_liveStarted) await _startLiveMix();
      else setState(() => _step = 3);
      return;
    }
    setState(() => _step = _step + 1);
  }

  Widget _buildStepBody() {
    switch (_step) {
      case 0:
        return _Step1Pick(
          api: widget.apiClient,
          token: widget.token,
          library: widget.librarySongs,
          playlists: _playlists,
          picked: _picked,
          onAdd: _addSongs,
          onRemove: _removeSong,
          onClear: () => setState(() {
            _picked.clear();
            _sequence = const [];
          }),
        );
      case 1:
        return _Step2Sequence(
          presets: _presets,
          selected: _preset,
          loading: _seqLoading,
          error: _seqError,
          picked: _picked,
          sequence: _sequence,
          onPickPreset: (k) => setState(() => _preset = k),
          onRun: _runSequence,
        );
      case 2:
        return _Step3Mix(
          rules: _rules,
          picked: _picked,
          sequence: _sequence,
          canStart: _sequence.isNotEmpty,
          onStart: _startLiveMix,
        );
      case 3:
        return _Step4Cut(
          ordered: _orderedSongs(),
          idx: _liveIdx,
          isPlaying: _isPlaying,
          liveStarted: _liveStarted,
          onCut: _doCut,
        );
      case 4:
        return _Step5Fx(
          items: _fxItems,
          liveStarted: _liveStarted,
          onPlayFx: _playFx,
        );
    }
    return const SizedBox.shrink();
  }
}

// =========================================================================== //
// Stepper header
// =========================================================================== //
class _StepHeader extends StatelessWidget {
  const _StepHeader({
    required this.step,
    required this.pickedCount,
    required this.sequencedCount,
    required this.liveStarted,
    required this.onJump,
  });
  final int step;
  final int pickedCount;
  final int sequencedCount;
  final bool liveStarted;
  final ValueChanged<int> onJump;

  static const _labels = ['选歌', '排歌', '混音', '切歌', '加花'];
  static const _icons = ['🎯', '📈', '🎚️', '✂️', '🔊'];

  bool _reachable(int i) {
    if (i == 0) return true;
    if (i == 1) return pickedCount >= 2;
    if (i == 2) return sequencedCount > 0;
    if (i >= 3) return liveStarted || sequencedCount > 0;
    return false;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Theme.of(context).colorScheme.surface,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: List.generate(5, (i) {
            final active = i == step;
            final done = i < step;
            final reachable = _reachable(i);
            return GestureDetector(
              onTap: reachable ? () => onJump(i) : null,
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 3),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: active
                      ? Colors.amber
                      : done
                          ? Colors.amber.withOpacity(0.35)
                          : reachable
                              ? Colors.white12
                              : Colors.white10,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  '${_icons[i]} ${i + 1}·${_labels[i]}',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: active ? Colors.black : Colors.white,
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}

class _StepFooter extends StatelessWidget {
  const _StepFooter({
    required this.step,
    required this.canPrev,
    required this.canNext,
    required this.onPrev,
    required this.onNext,
  });
  final int step;
  final bool canPrev;
  final bool canNext;
  final VoidCallback onPrev;
  final VoidCallback onNext;

  @override
  Widget build(BuildContext context) {
    final nextLabel = step == 2 ? '开始混音 ▶' : (step == 4 ? '完成' : '下一步 →');
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          OutlinedButton(
            onPressed: canPrev ? onPrev : null,
            child: const Text('← 上一步'),
          ),
          ElevatedButton(
            onPressed: canNext && step < 4 ? onNext : null,
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.amber,
              foregroundColor: Colors.black,
            ),
            child: Text(nextLabel),
          ),
        ],
      ),
    );
  }
}

class _LiveMixBar extends StatelessWidget {
  const _LiveMixBar({
    required this.ordered,
    required this.idx,
    required this.isPlaying,
    required this.position,
    required this.duration,
    required this.onPlayPause,
    required this.onNext,
    required this.cutInfo,
  });
  final List<LibrarySong> ordered;
  final int idx;
  final bool isPlaying;
  final Duration position;
  final Duration duration;
  final VoidCallback onPlayPause;
  final VoidCallback onNext;
  final String? cutInfo;

  String _fmt(Duration d) {
    final s = d.inSeconds;
    return '${(s ~/ 60).toString().padLeft(2, '0')}:${(s % 60).toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final current = idx < ordered.length ? ordered[idx] : null;
    final next = idx + 1 < ordered.length ? ordered[idx + 1] : null;
    final pct = duration.inMilliseconds == 0
        ? 0.0
        : (position.inMilliseconds / duration.inMilliseconds).clamp(0.0, 1.0);
    return Container(
      color: Colors.black.withOpacity(0.55),
      padding: const EdgeInsets.fromLTRB(10, 6, 10, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              IconButton(
                icon: Icon(isPlaying ? Icons.pause_circle_filled : Icons.play_circle_fill, size: 28, color: Colors.amber),
                onPressed: onPlayPause,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 30, minHeight: 30),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '#${idx + 1}/${ordered.length} ${current?.title ?? '—'}',
                      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.white),
                      maxLines: 1, overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      '下一首：${next?.title ?? '—'}',
                      style: const TextStyle(fontSize: 10, color: Colors.white70),
                      maxLines: 1, overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              Text('${_fmt(position)}/${_fmt(duration)}',
                  style: const TextStyle(fontSize: 11, color: Colors.white)),
              IconButton(
                icon: const Icon(Icons.skip_next, size: 24, color: Colors.white),
                onPressed: onNext,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 30, minHeight: 30),
              ),
            ],
          ),
          const SizedBox(height: 4),
          LinearProgressIndicator(
            value: pct,
            backgroundColor: Colors.white12,
            valueColor: const AlwaysStoppedAnimation(Colors.amber),
            minHeight: 3,
          ),
          if (cutInfo != null) Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(cutInfo!, style: const TextStyle(fontSize: 10, color: Colors.amberAccent)),
          ),
        ],
      ),
    );
  }
}

// =========================================================================== //
// Step 1 — 选歌
// =========================================================================== //
class _Step1Pick extends StatefulWidget {
  const _Step1Pick({
    required this.api,
    required this.token,
    required this.library,
    required this.playlists,
    required this.picked,
    required this.onAdd,
    required this.onRemove,
    required this.onClear,
  });
  final HarBeatApiClient api;
  final String token;
  final List<LibrarySong> library;
  final List<PlaylistSummary> playlists;
  final List<LibrarySong> picked;
  final void Function(Iterable<LibrarySong>) onAdd;
  final void Function(String id) onRemove;
  final VoidCallback onClear;

  @override
  State<_Step1Pick> createState() => _Step1PickState();
}

class _Step1PickState extends State<_Step1Pick> {
  int _mode = 2; // 0=import, 1=vibe, 2=style

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        const Text(
          '把候选歌曲加入「已选池」。三种来源可叠加。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            _modeBtn(0, '📥 导入'),
            const SizedBox(width: 4),
            _modeBtn(1, '🔍 Vibe'),
            const SizedBox(width: 4),
            _modeBtn(2, '🎭 舞种+时长'),
          ],
        ),
        const SizedBox(height: 8),
        if (_mode == 0) _ImportSource(
          api: widget.api, token: widget.token,
          playlists: widget.playlists, library: widget.library,
          onAdd: widget.onAdd,
        ),
        if (_mode == 1) _VibeSource(
          library: widget.library, onAdd: widget.onAdd,
        ),
        if (_mode == 2) _StyleSource(
          api: widget.api, token: widget.token,
          library: widget.library, onAdd: widget.onAdd,
        ),
        const SizedBox(height: 10),
        _PickedPool(picked: widget.picked, onRemove: widget.onRemove, onClear: widget.onClear),
      ],
    );
  }

  Widget _modeBtn(int i, String label) {
    final active = _mode == i;
    return Expanded(
      child: ElevatedButton(
        onPressed: () => setState(() => _mode = i),
        style: ElevatedButton.styleFrom(
          backgroundColor: active ? Colors.amber : Colors.white10,
          foregroundColor: active ? Colors.black : Colors.white,
          padding: const EdgeInsets.symmetric(vertical: 8),
          minimumSize: const Size(0, 0),
        ),
        child: Text(label, style: const TextStyle(fontSize: 11)),
      ),
    );
  }
}

class _PickedPool extends StatelessWidget {
  const _PickedPool({required this.picked, required this.onRemove, required this.onClear});
  final List<LibrarySong> picked;
  final void Function(String) onRemove;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final totalSec = picked.fold<double>(0.0, (a, s) => a + s.duration);
    return Card(
      color: Colors.white10,
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(child: Text('已选池（${picked.length} · ${(totalSec / 60).toStringAsFixed(1)} 分钟）',
                    style: const TextStyle(fontWeight: FontWeight.bold))),
                if (picked.isNotEmpty) TextButton(onPressed: onClear, child: const Text('清空')),
              ],
            ),
            if (picked.isEmpty) const Padding(
              padding: EdgeInsets.symmetric(vertical: 6),
              child: Text('还没选歌', style: TextStyle(fontSize: 11, color: Colors.grey)),
            ),
            ...picked.asMap().entries.map((e) {
              final i = e.key, s = e.value;
              return Container(
                padding: const EdgeInsets.symmetric(vertical: 3),
                decoration: const BoxDecoration(
                  border: Border(top: BorderSide(color: Colors.white12)),
                ),
                child: Row(
                  children: [
                    SizedBox(width: 26, child: Text('#${i + 1}', style: const TextStyle(fontSize: 10, color: Colors.grey))),
                    Expanded(child: Text('${s.title}  ·  ${s.artist}',
                        maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12))),
                    Text(s.bpm != null ? '${s.bpm!.toStringAsFixed(0)}BPM' : '-',
                        style: const TextStyle(fontSize: 10, color: Colors.grey)),
                    IconButton(
                      icon: const Icon(Icons.close, size: 16, color: Colors.redAccent),
                      onPressed: () => onRemove(s.id),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

// ---- Import Source: pick playlist → checkbox subset ---- //
class _ImportSource extends StatefulWidget {
  const _ImportSource({
    required this.api, required this.token,
    required this.playlists, required this.library, required this.onAdd,
  });
  final HarBeatApiClient api;
  final String token;
  final List<PlaylistSummary> playlists;
  final List<LibrarySong> library;
  final void Function(Iterable<LibrarySong>) onAdd;

  @override
  State<_ImportSource> createState() => _ImportSourceState();
}

class _ImportSourceState extends State<_ImportSource> {
  int? _pid;
  bool _loading = false;
  String? _msg;
  /// matched library songs in playlist order
  List<LibrarySong> _matched = const [];
  final Set<String> _sel = {};

  Future<void> _loadDetail() async {
    if (_pid == null) return;
    setState(() { _loading = true; _msg = null; _matched = const []; _sel.clear(); });
    try {
      final detail = await widget.api.getPlaylistDetail(token: widget.token, playlistId: _pid!);
      final libKey = <String, LibrarySong>{};
      for (final s in widget.library) {
        libKey['${s.title.toLowerCase()}|${s.artist.toLowerCase()}'] = s;
      }
      final hits = <LibrarySong>[];
      for (final ps in detail.songs) {
        final hit = libKey['${ps.title.toLowerCase()}|${ps.artist.toLowerCase()}'];
        if (hit != null) hits.add(hit);
      }
      setState(() {
        _matched = hits;
        _sel.addAll(hits.map((s) => s.id)); // default: all
        _msg = '匹配 ${hits.length}/${detail.songs.length} 首';
      });
    } catch (e) {
      setState(() => _msg = '错误: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _commit() {
    final picks = _matched.where((s) => _sel.contains(s.id));
    widget.onAdd(picks);
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('加入 ${picks.length} 首'), duration: const Duration(seconds: 1)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.white10,
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('导入歌单后勾选要加入的歌（默认全选）。',
                style: TextStyle(fontSize: 11, color: Colors.grey)),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: DropdownButton<int>(
                    isExpanded: true,
                    value: _pid,
                    hint: const Text('— 选择歌单 —'),
                    items: widget.playlists.map((p) => DropdownMenuItem(
                      value: p.id,
                      child: Text('${p.name}（${p.songCount}）', overflow: TextOverflow.ellipsis),
                    )).toList(),
                    onChanged: (v) {
                      setState(() => _pid = v);
                      _loadDetail();
                    },
                  ),
                ),
              ],
            ),
            if (_msg != null) Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(_msg!, style: const TextStyle(fontSize: 11, color: Colors.grey)),
            ),
            if (_loading) const LinearProgressIndicator(minHeight: 2),
            if (_matched.isNotEmpty) ...[
              const SizedBox(height: 6),
              Row(
                children: [
                  TextButton(onPressed: () => setState(() {
                    _sel..clear()..addAll(_matched.map((s) => s.id));
                  }), child: const Text('全选')),
                  TextButton(onPressed: () => setState(() => _sel.clear()), child: const Text('全不选')),
                  const Spacer(),
                  ElevatedButton(
                    onPressed: _sel.isEmpty ? null : _commit,
                    style: ElevatedButton.styleFrom(backgroundColor: Colors.amber, foregroundColor: Colors.black),
                    child: Text('加入 ${_sel.length}'),
                  ),
                ],
              ),
              SizedBox(
                height: 260,
                child: ListView.builder(
                  itemCount: _matched.length,
                  itemBuilder: (_, i) {
                    final s = _matched[i];
                    final on = _sel.contains(s.id);
                    return CheckboxListTile(
                      dense: true,
                      value: on,
                      title: Text(s.title, maxLines: 1, overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 12)),
                      subtitle: Text(
                        '${s.artist} · ${s.bpm?.toStringAsFixed(0) ?? '-'} BPM · ${(s.duration / 60).toStringAsFixed(1)}m',
                        style: const TextStyle(fontSize: 10),
                      ),
                      onChanged: (v) => setState(() {
                        if (v == true) _sel.add(s.id); else _sel.remove(s.id);
                      }),
                    );
                  },
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ---- Vibe Source: keyword search + duration auto-fill ---- //
class _VibeSource extends StatefulWidget {
  const _VibeSource({required this.library, required this.onAdd});
  final List<LibrarySong> library;
  final void Function(Iterable<LibrarySong>) onAdd;

  @override
  State<_VibeSource> createState() => _VibeSourceState();
}

class _VibeSourceState extends State<_VibeSource> {
  final _ctrl = TextEditingController();
  final Set<String> _sel = {};
  double _minutes = 15;

  List<LibrarySong> get _matched {
    final q = _ctrl.text.trim().toLowerCase();
    if (q.isEmpty) return const [];
    final kws = q.split(RegExp(r'\s+')).where((s) => s.isNotEmpty).toList();
    return widget.library.where((s) {
      final hay = '${s.title} ${s.artist}'.toLowerCase();
      return kws.every(hay.contains);
    }).toList();
  }

  void _autoFillByDuration() {
    final target = _minutes * 60;
    final list = _matched.toList();
    if (list.isEmpty) return;
    // sort by bpm asc for predictability; fallback to title
    list.sort((a, b) {
      final ab = a.bpm ?? 0;
      final bb = b.bpm ?? 0;
      return ab.compareTo(bb);
    });
    double acc = 0;
    final chosen = <String>{};
    for (final s in list) {
      if (acc >= target) break;
      chosen.add(s.id);
      acc += s.duration > 0 ? s.duration : 180;
    }
    setState(() {
      _sel..clear()..addAll(chosen);
    });
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final matched = _matched;
    final selDur = matched.where((s) => _sel.contains(s.id)).fold<double>(0, (a, s) => a + (s.duration > 0 ? s.duration : 180));
    return Card(
      color: Colors.white10,
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('关键词在曲库内搜（标题+艺人，多词 AND 命中）。可点「按时长自动选满」。',
                style: TextStyle(fontSize: 11, color: Colors.grey)),
            const SizedBox(height: 6),
            TextField(
              controller: _ctrl,
              decoration: const InputDecoration(
                isDense: true,
                hintText: '例如：boom bap dark',
                border: OutlineInputBorder(),
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                const Text('目标时长', style: TextStyle(fontSize: 11)),
                Expanded(
                  child: Slider(
                    value: _minutes,
                    min: 1, max: 60, divisions: 59,
                    label: '${_minutes.toInt()} 分',
                    onChanged: (v) => setState(() => _minutes = v),
                  ),
                ),
                Text('${_minutes.toInt()} 分', style: const TextStyle(fontSize: 11)),
              ],
            ),
            Row(
              children: [
                TextButton(onPressed: matched.isEmpty ? null : _autoFillByDuration,
                    child: const Text('按时长自动选满')),
                TextButton(onPressed: () => setState(() => _sel.clear()), child: const Text('全不选')),
                const Spacer(),
                Text('已选 ${_sel.length} · ${(selDur / 60).toStringAsFixed(1)} 分',
                    style: const TextStyle(fontSize: 11)),
                const SizedBox(width: 4),
                ElevatedButton(
                  onPressed: _sel.isEmpty ? null : () {
                    final picks = matched.where((s) => _sel.contains(s.id));
                    widget.onAdd(picks);
                    if (mounted) ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text('加入 ${picks.length} 首'), duration: const Duration(seconds: 1)),
                    );
                  },
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.amber, foregroundColor: Colors.black),
                  child: Text('加入 ${_sel.length}'),
                ),
              ],
            ),
            if (_ctrl.text.isNotEmpty && matched.isEmpty) const Padding(
              padding: EdgeInsets.symmetric(vertical: 6),
              child: Text('无命中', style: TextStyle(fontSize: 11, color: Colors.grey)),
            ),
            if (matched.isNotEmpty) SizedBox(
              height: 240,
              child: ListView.builder(
                itemCount: matched.length,
                itemBuilder: (_, i) {
                  final s = matched[i];
                  final on = _sel.contains(s.id);
                  return CheckboxListTile(
                    dense: true,
                    value: on,
                    title: Text(s.title, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12)),
                    subtitle: Text(
                      '${s.artist} · ${s.bpm?.toStringAsFixed(0) ?? '-'} BPM · ${(s.duration / 60).toStringAsFixed(1)}m',
                      style: const TextStyle(fontSize: 10),
                    ),
                    onChanged: (v) => setState(() {
                      if (v == true) _sel.add(s.id); else _sel.remove(s.id);
                    }),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---- Style Source ---- //
class _StyleSource extends StatefulWidget {
  const _StyleSource({required this.api, required this.token, required this.library, required this.onAdd});
  final HarBeatApiClient api;
  final String token;
  final List<LibrarySong> library;
  final void Function(Iterable<LibrarySong>) onAdd;

  @override
  State<_StyleSource> createState() => _StyleSourceState();
}

class _StyleSourceState extends State<_StyleSource> {
  List<Map<String, dynamic>> _styles = const [];
  String? _style;
  double _minutes = 10;
  bool _loading = false;
  String? _error;
  List<Map<String, dynamic>> _result = const [];

  @override
  void initState() {
    super.initState();
    widget.api.djListStyles(token: widget.token).then((s) {
      if (!mounted) return;
      setState(() {
        _styles = s;
        if (s.isNotEmpty) _style = s.first['key'] as String;
      });
    }).catchError((e) {
      if (mounted) setState(() => _error = e.toString());
    });
  }

  Future<void> _run() async {
    if (_style == null) return;
    setState(() { _loading = true; _error = null; _result = const []; });
    try {
      final r = await widget.api.djPickByStyle(
        token: widget.token, style: _style!, targetDurationSec: _minutes * 60,
      );
      setState(() => _result = (r['songs'] as List).cast<Map<String, dynamic>>());
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.white10,
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('按舞种 + 目标时长自动出歌（BPM/Phrase/Energy 匹配）。',
                style: TextStyle(fontSize: 11, color: Colors.grey)),
            DropdownButton<String>(
              isExpanded: true,
              value: _style,
              hint: const Text('选择舞种'),
              items: _styles.map((s) {
                final r = (s['bpm_range'] as List).cast<num>();
                return DropdownMenuItem<String>(
                  value: s['key'] as String,
                  child: Text('${s['label_zh']} (${r[0].toInt()}–${r[1].toInt()} BPM)'),
                );
              }).toList(),
              onChanged: (v) => setState(() => _style = v),
            ),
            Row(
              children: [
                const Text('目标时长', style: TextStyle(fontSize: 11)),
                Expanded(
                  child: Slider(
                    value: _minutes, min: 1, max: 60, divisions: 59,
                    label: '${_minutes.toInt()} 分',
                    onChanged: (v) => setState(() => _minutes = v),
                  ),
                ),
                Text('${_minutes.toInt()} 分', style: const TextStyle(fontSize: 11)),
              ],
            ),
            Row(
              children: [
                ElevatedButton(
                  onPressed: _loading || _style == null ? null : _run,
                  child: Text(_loading ? '生成中...' : '生成候选'),
                ),
                const SizedBox(width: 6),
                if (_result.isNotEmpty) ElevatedButton(
                  onPressed: () {
                    final ids = _result.map((e) => e['song_id'].toString()).toSet();
                    final byId = {for (final s in widget.library) s.id: s};
                    final picks = ids.map((id) => byId[id]).whereType<LibrarySong>();
                    widget.onAdd(picks);
                  },
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.amber, foregroundColor: Colors.black),
                  child: Text('全部加入 (${_result.length})'),
                ),
              ],
            ),
            if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red, fontSize: 11)),
            if (_result.isNotEmpty) SizedBox(
              height: 220,
              child: ListView(
                children: _result.asMap().entries.map((entry) {
                  final i = entry.key, s = entry.value;
                  final score = ((s['score'] as num).toDouble() * 100).toInt();
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(
                      children: [
                        SizedBox(width: 24, child: Text('#${i + 1}', style: const TextStyle(fontSize: 10, color: Colors.grey))),
                        Expanded(child: Text('${s['title']} · ${s['artist']}',
                            maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12))),
                        Text('${(s['bpm'] as num?)?.toStringAsFixed(0) ?? '-'}BPM ·$score',
                            style: const TextStyle(fontSize: 10, color: Colors.grey)),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// =========================================================================== //
// Step 2 — 排歌
// =========================================================================== //
class _Step2Sequence extends StatelessWidget {
  const _Step2Sequence({
    required this.presets, required this.selected, required this.loading, required this.error,
    required this.picked, required this.sequence,
    required this.onPickPreset, required this.onRun,
  });
  final List<Map<String, dynamic>> presets;
  final String selected;
  final bool loading;
  final String? error;
  final List<LibrarySong> picked;
  final List<Map<String, dynamic>> sequence;
  final ValueChanged<String> onPickPreset;
  final VoidCallback onRun;

  String _sceneIcon(String scene) => {
    'battle': '🥊', 'cypher': '🌀', 'class': '🎓', 'showcase': '🎬',
  }[scene] ?? '🎵';

  @override
  Widget build(BuildContext context) {
    final byId = {for (final s in picked) s.id: s};
    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        const Text(
          '按街舞场景能量曲线贪心分配每一首歌位置。混音方案保持 7+11 不变。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 6),
        GridView.count(
          crossAxisCount: 2,
          mainAxisSpacing: 6,
          crossAxisSpacing: 6,
          childAspectRatio: 2.2,
          physics: const NeverScrollableScrollPhysics(),
          shrinkWrap: true,
          children: presets.map((p) {
            final active = p['key'] == selected;
            return GestureDetector(
              onTap: () => onPickPreset(p['key'] as String),
              child: Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: active ? Colors.amber : Colors.white10,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${_sceneIcon(p['scene'] as String? ?? 'generic')} ${p['label_zh']}',
                        style: TextStyle(
                          fontSize: 11, fontWeight: FontWeight.bold,
                          color: active ? Colors.black : Colors.white,
                        )),
                    const SizedBox(height: 2),
                    Expanded(
                      child: Text(
                        p['desc_zh'] as String? ?? '',
                        style: TextStyle(
                          fontSize: 9,
                          color: active ? Colors.black87 : Colors.grey,
                        ),
                        maxLines: 3, overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            ElevatedButton(
              onPressed: loading || picked.length < 2 ? null : onRun,
              style: ElevatedButton.styleFrom(backgroundColor: Colors.amber, foregroundColor: Colors.black),
              child: Text(loading ? '排序中...' : '按曲线排序 ${picked.length} 首'),
            ),
          ],
        ),
        if (error != null) Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(error!, style: const TextStyle(color: Colors.red, fontSize: 11)),
        ),
        if (sequence.isNotEmpty) Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Card(
            color: Colors.white10,
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('排序结果 — 目标/实际能量', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  ...sequence.map((entry) {
                    final id = entry['song_id'].toString();
                    final song = byId[id];
                    final act = ((entry['actual_energy'] as num).toDouble() * 100).round();
                    final tgt = ((entry['target_energy'] as num).toDouble() * 100).round();
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Row(
                            children: [
                              Expanded(child: Text(
                                '#${(entry['position'] as int) + 1} ${song?.title ?? id}',
                                style: const TextStyle(fontSize: 11),
                                maxLines: 1, overflow: TextOverflow.ellipsis,
                              )),
                              Text('tgt $tgt·act $act', style: const TextStyle(fontSize: 10, color: Colors.grey)),
                            ],
                          ),
                          const SizedBox(height: 2),
                          Stack(children: [
                            Container(height: 5, color: Colors.black26),
                            FractionallySizedBox(
                              widthFactor: act / 100.0,
                              child: Container(height: 5, color: Colors.amber),
                            ),
                            Positioned(
                              left: (tgt / 100.0) * MediaQuery.of(context).size.width * 0.8,
                              child: Container(width: 2, height: 8, color: Colors.white),
                            ),
                          ]),
                        ],
                      ),
                    );
                  }),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// =========================================================================== //
// Step 3 — 混音 (rules + bpm-diff hints + start live mix)
// =========================================================================== //
class _Step3Mix extends StatelessWidget {
  const _Step3Mix({
    required this.rules, required this.picked, required this.sequence,
    required this.canStart, required this.onStart,
  });
  final Map<String, dynamic>? rules;
  final List<LibrarySong> picked;
  final List<Map<String, dynamic>> sequence;
  final bool canStart;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    final byId = {for (final s in picked) s.id: s};
    final analyzed = ((rules?['analyzed'] as List?) ?? const []).cast<Map<String, dynamic>>();
    final raw = ((rules?['raw'] as List?) ?? const []).cast<Map<String, dynamic>>();
    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        const Text(
          '混音采用现有 7 原生 + 11 分析型方案。点 ▶ 开始混音播放后即进入实时切歌 / 加花。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 8),
        Center(
          child: ElevatedButton.icon(
            onPressed: canStart ? onStart : null,
            icon: const Icon(Icons.play_arrow),
            label: Text(canStart ? '▶ 开始混音播放（${sequence.length} 首）' : '需要先在 Step 2 排序'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.amber, foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
              textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
            ),
          ),
        ),
        if (sequence.length >= 2) ...[
          const SizedBox(height: 10),
          Card(
            color: Colors.white10,
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('相邻过渡（${sequence.length - 1} 段）', style: const TextStyle(fontWeight: FontWeight.bold)),
                  ...List.generate(sequence.length - 1, (i) {
                    final a = byId[sequence[i]['song_id'].toString()];
                    final b = byId[sequence[i + 1]['song_id'].toString()];
                    final diff = (a?.bpm != null && b?.bpm != null) ? (a!.bpm! - b!.bpm!).abs() : null;
                    final tag = diff == null ? '—'
                        : diff <= 3 ? '完美吻合'
                            : diff <= 8 ? '可拉伸混'
                                : diff <= 16 ? '建议加 FX 衔接' : '建议硬切 / Rewind';
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Row(
                        children: [
                          SizedBox(width: 38, child: Text('#${i + 1}→#${i + 2}',
                              style: const TextStyle(fontSize: 10, color: Colors.grey))),
                          Expanded(child: Text('${a?.title ?? '-'} → ${b?.title ?? '-'}',
                              style: const TextStyle(fontSize: 11),
                              maxLines: 1, overflow: TextOverflow.ellipsis)),
                          Text('Δ${diff?.toStringAsFixed(1) ?? '?'} · $tag',
                              style: const TextStyle(fontSize: 10, color: Colors.amberAccent)),
                        ],
                      ),
                    );
                  }),
                ],
              ),
            ),
          ),
        ],
        const SizedBox(height: 10),
        if (rules != null) ...[
          Text('分析型过渡（${analyzed.length}）', style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Wrap(spacing: 6, runSpacing: 6,
              children: analyzed.map((r) => _ruleChip(r, Colors.deepPurple)).toList()),
          const SizedBox(height: 10),
          Text('原生过渡（${raw.length}）', style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Wrap(spacing: 6, runSpacing: 6,
              children: raw.map((r) => _ruleChip(r, Colors.indigo)).toList()),
        ],
      ],
    );
  }

  Widget _ruleChip(Map<String, dynamic> r, Color base) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
    decoration: BoxDecoration(color: base.withOpacity(0.25), borderRadius: BorderRadius.circular(5)),
    child: Text(r['label_zh']?.toString() ?? '', style: const TextStyle(fontSize: 11)),
  );
}

// =========================================================================== //
// Step 4 — 切歌（实时）
// =========================================================================== //
class _Step4Cut extends StatelessWidget {
  const _Step4Cut({
    required this.ordered, required this.idx, required this.isPlaying,
    required this.liveStarted, required this.onCut,
  });
  final List<LibrarySong> ordered;
  final int idx;
  final bool isPlaying;
  final bool liveStarted;
  final Future<void> Function(String strategy) onCut;

  @override
  Widget build(BuildContext context) {
    if (!liveStarted) return const Center(
      child: Padding(
        padding: EdgeInsets.all(20),
        child: Text('请先回到 Step 3 点 ▶ 开始混音播放', style: TextStyle(color: Colors.grey)),
      ),
    );
    final current = idx < ordered.length ? ordered[idx] : null;
    final next = idx + 1 < ordered.length ? ordered[idx + 1] : null;
    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        const Text(
          '现场切歌（实时）— 由后端按 BPM/Beat/Phrase 找下一个边界。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 8),
        Card(
          color: Colors.white10,
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('当前 #${idx + 1} · ${current?.title ?? '-'}',
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold)),
                Text(current?.artist ?? '', style: const TextStyle(fontSize: 11, color: Colors.grey)),
                const SizedBox(height: 6),
                Text('下一首：${next?.title ?? '— 队尾 —'}',
                    style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 10),
        _cutBtn('⚡ 快切 fast_cut', '5 秒内寻找下一个 downbeat/beat/小节边界，硬切到下一首。', 'fast_cut'),
        _cutBtn('🔥 升能量切 energy_up_cut', '从已选池挑能量更高的歌替换后切。冲峰 / 喊大招用。', 'energy_up_cut'),
        _cutBtn('❄️ 降能量切 energy_down_cut', '挑能量更低的歌，让 cypher 喘口气。', 'energy_down_cut'),
      ],
    );
  }

  Widget _cutBtn(String title, String desc, String strategy) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: ElevatedButton(
        onPressed: () => onCut(strategy),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.white10,
          foregroundColor: Colors.white,
          alignment: Alignment.centerLeft,
          padding: const EdgeInsets.all(10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold)),
            const SizedBox(height: 2),
            Text(desc, style: const TextStyle(fontSize: 10, color: Colors.grey)),
          ],
        ),
      ),
    );
  }
}

// =========================================================================== //
// Step 5 — 加花（实时 FX）
// =========================================================================== //
class _Step5Fx extends StatelessWidget {
  const _Step5Fx({required this.items, required this.liveStarted, required this.onPlayFx});
  final List<Map<String, dynamic>> items;
  final bool liveStarted;
  final Future<void> Function(String key) onPlayFx;

  static const _groupOrder = ['hype', 'drop', 'scratch', 'drum', 'accent'];
  static const _groupTitle = {
    'hype': '🚨 喊场 / 起势',
    'drop': '💥 Drop / Build',
    'scratch': '🎚️ 搓碟 Scratch',
    'drum': '🥁 鼓点 Stab',
    'accent': '⚡ 单点强调',
  };

  String _iconFor(String key) => const {
    'air_horn': '📯', 'air_horn_burst': '📯', 'siren': '🚨', 'reload_cock': '🔫',
    'mc_hype': '🎤', 'scratch_chirp': '🎚️', 'scratch_transformer': '🤖',
    'scratch_baby': '👶', 'snare_crack': '🥁', 'kick_roll': '🦶',
    'beat_juggle_stutter': '🎛️', 'bass_drop': '💣', 'reverse_cymbal': '🌊',
    'cymbal_swell': '💥', 'rewind_zip': '⏪', 'vinyl_stop': '🛑', 'laser_zap': '⚡',
  }[key] ?? '🔊';

  @override
  Widget build(BuildContext context) {
    final groups = <String, List<Map<String, dynamic>>>{};
    for (final it in items) {
      final g = (it['category'] as String?) ?? 'accent';
      groups.putIfAbsent(g, () => []).add(it);
    }
    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        if (!liveStarted) const Padding(
          padding: EdgeInsets.symmetric(vertical: 4),
          child: Text('提示：建议先从 Step 3 启动混音播放，再叠加 FX。',
              style: TextStyle(fontSize: 11, color: Colors.amberAccent)),
        ),
        const Text(
          '街舞 DJ 现场音效，全部由后端 numpy 实时合成 WAV，叠在主混音之上播放。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 6),
        ..._groupOrder.where((k) => groups[k]?.isNotEmpty == true).map((g) {
          final list = groups[g]!;
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(_groupTitle[g]!, style: const TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                GridView.count(
                  crossAxisCount: 3,
                  mainAxisSpacing: 6,
                  crossAxisSpacing: 6,
                  childAspectRatio: 1.4,
                  physics: const NeverScrollableScrollPhysics(),
                  shrinkWrap: true,
                  children: list.map((fx) {
                    final k = fx['key'] as String;
                    return GestureDetector(
                      onTap: () => onPlayFx(k),
                      child: Container(
                        padding: const EdgeInsets.all(6),
                        decoration: BoxDecoration(
                          color: Colors.white10,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(_iconFor(k), style: const TextStyle(fontSize: 20)),
                            const SizedBox(height: 2),
                            Text(fx['label_zh'] as String? ?? k,
                                style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold),
                                maxLines: 1, overflow: TextOverflow.ellipsis),
                            Text('${(fx['default_duration'] as num).toStringAsFixed(2)}s',
                                style: const TextStyle(fontSize: 9, color: Colors.grey)),
                          ],
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ],
            ),
          );
        }),
      ],
    );
  }
}
