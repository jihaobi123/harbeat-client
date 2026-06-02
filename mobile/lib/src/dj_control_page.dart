import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import 'api_client.dart';
import 'edge_agent_client.dart';
import 'models.dart';
import 'sync_worker_client.dart';

// =========================================================================== //
// DJ Control 4-step wizard (mobile) — RK3588 live playback
//   1) 选歌 — 导入歌单 / Vibe 描述搜索 / 舞种+时长
//   2) 排歌 — 街舞场景能量曲线（贪心分配）
//   3) 混音 — 7+11 现有方案 + BPM 差提示 + ▶ 开始混音播放
//   4) 实时操作 — RK3588 播放中的切歌 + 加花 FX Pad，每首之间自动按 7/11 方案 xfade
// =========================================================================== //

class DjControlPage extends StatefulWidget {
  const DjControlPage({
    super.key,
    required this.apiClient,
    required this.edgeClient,
    required this.token,
    required this.userId,
    required this.librarySongs,
  });

  final HarBeatApiClient apiClient;
  final EdgeAgentClient edgeClient;
  final String token;
  final int userId;
  final List<LibrarySong> librarySongs;

  @override
  State<DjControlPage> createState() => _DjControlPageState();
}

class _DjControlPageState extends State<DjControlPage> {
  int _step = 0; // 0..3

  // Selection state
  final List<LibrarySong> _picked = [];

  // Sequence state
  List<Map<String, dynamic>> _presets = const [];
  String _preset = 'battle_4rounds';
  List<Map<String, dynamic>> _sequence = const [];
  bool _seqLoading = false;
  String? _seqError;

  // Auto DJ-Set state — backend picks 5 candidate sets, user二次选择.
  // `_autoSets` is the full backend response's `sets` list (each item has
  // tracks/narrative_arc/energy_curve/transitions/purposes/plans/quality).
  List<Map<String, dynamic>> _autoSets = const [];
  List<Map<String, dynamic>> _activeSetPlans = const [];
  int _selectedSetIdx = -1; // -1 = none chosen yet
  bool _autoSetsLoading = false;
  String? _autoSetsError;

  // v2 energy state — populated after排序，每首歌补一份 StreetEnergy 数据。
  List<Map<String, dynamic>> _energyBuckets = const [];
  // song_id -> v2 energy map: {total, bucket, bucket_color, factors, bpm,
  // explain_zh, style_used, ...}. Filled by [_loadEnergyForSequence].
  Map<String, Map<String, dynamic>> _songEnergyV2 = const {};
  bool _energyLoading = false;

  // Mix rules + FX catalog
  Map<String, dynamic>? _rules;
  List<Map<String, dynamic>> _fxItems = const [];

  // Playlists for import
  List<PlaylistSummary> _playlists = const [];

  // ---- Live mix state (RK3588) ----
  final AudioPlayer _fxPlayer = AudioPlayer(); // local overlay only
  bool _liveStarted = false;
  int _liveIdx = 0;
  bool _isPlaying = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  String? _rkCurrentSongId; // RK-reported current song id (from /state)
  /// Wall-clock time of last successful xfade. Used as a cooldown to keep
  /// transient state hiccups (RK reporting playing=false for one tick during
  /// the deck swap, or position spuriously crossing the trigger threshold)
  /// from cascading more xfades. Cleared on _startLiveMix.
  DateTime? _lastXfadeAt;

  /// fade_sec of the last issued xfade — cooldown must outlast this so we
  /// don't re-fire while the previous fade is still running.
  double _lastXfadeSec = 0.0;

  /// RK song id we just xfaded TO. While RK still reports this song id
  /// (no further user-driven cuts), block additional auto-xfades — the
  /// queue index has already advanced and any further trigger would be
  /// a cascading mistake.
  String? _lastXfadeToSongId;

  /// Smart plan pre-fetched while the current track is within 30s of its
  /// phrase-aligned exit. Lets us trigger the xfade exactly at the planned
  /// outro/break boundary instead of guessing from "remaining ≤ Ns".
  /// Keyed by the prev song id; cleared after the xfade fires or the queue
  /// advances.
  String? _smartPlanForSongId;
  Map<String, dynamic>? _smartPlan;
  bool _smartPlanInFlight = false;
  String? _cutInfo;
  String? _activeRule; // last applied transition rule label
  int _lastXfadeFromIdx = -1; // guards against double-fire of auto-xfade
  bool _xfadeInFlight = false;
  Timer? _rkPoll;

  // Sync-worker: pulls Jetson wav into ~/cypher/cache/<song_id>/ on RK.
  // Without this, edge-agent /play and /xfade return HTTP 409 ('缺少 original.wav').
  late final SyncWorkerClient _sync;
  final Set<String> _prefetched = <String>{};
  final Set<String> _prefetchInFlight = <String>{};

  @override
  void initState() {
    super.initState();
    _sync = SyncWorkerClient(
      baseUrl: SyncWorkerClient.deriveFromRkBaseUrl(widget.edgeClient.baseUrl),
    );
    _loadCatalogs();
  }

  Future<void> _loadCatalogs() async {
    try {
      final futures = await Future.wait([
        widget.apiClient.djSequencePresetsMeta(token: widget.token),
        widget.apiClient.djListTransitionRules(token: widget.token),
        widget.apiClient.djListFx(token: widget.token),
        widget.apiClient
            .getPlaylists(token: widget.token, userId: widget.userId)
            .catchError((_) => <PlaylistSummary>[]),
        widget.apiClient
            .djListEnergyBuckets(token: widget.token)
            .catchError((_) => <Map<String, dynamic>>[]),
      ]);
      if (!mounted) return;
      setState(() {
        _presets = (futures[0] as List).cast<Map<String, dynamic>>();
        if (_presets.isNotEmpty) _preset = _presets.first['key'] as String;
        _rules = futures[1] as Map<String, dynamic>;
        _fxItems = (futures[2] as List).cast<Map<String, dynamic>>();
        _playlists = (futures[3] as List).cast<PlaylistSummary>();
        _energyBuckets = (futures[4] as List).cast<Map<String, dynamic>>();
      });
    } catch (e) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('加载目录失败: $e')));
    }
  }

  @override
  void dispose() {
    _rkPoll?.cancel();
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
      _autoSets = const [];
      _selectedSetIdx = -1;
    });
  }

  void _removeSong(String id) {
    setState(() {
      _picked.removeWhere((s) => s.id == id);
      _sequence = const [];
      _autoSets = const [];
      _activeSetPlans = const [];
      _selectedSetIdx = -1;
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
      _activeSetPlans = const [];
      _songEnergyV2 = const {};
    });
    try {
      final r = await widget.apiClient.djSequence(
        token: widget.token,
        songIds: _picked.map((s) => s.id).toList(),
        preset: _preset,
      );
      setState(() {
        _sequence = r;
        _selectedSetIdx = -1;
      });
      // Fire-and-forget v2 energy enrichment (UI degrades gracefully if it
      // fails — Step 2 still shows v1 actual_energy from the sequencer).
      // ignore: discarded_futures
      _loadEnergyForSequence();
    } catch (e) {
      setState(() => _seqError = e.toString());
    } finally {
      if (mounted) setState(() => _seqLoading = false);
    }
  }

  // ---------------- Auto DJ Sets (new pipeline) ----------------
  // Calls /api/dj/set/generate which runs the full pipeline (Profiler →
  // Section Energy → Roles → Edges → 5 Templates → Optimizer → Purposes →
  // Plans → Quality) and returns 5 candidate sets. User picks one — no manual
  // preset choice needed.
  Future<void> _runAutoSets() async {
    if (_picked.length < 2) {
      setState(() => _autoSetsError = '至少选 2 首才能生成');
      return;
    }
    setState(() {
      _autoSetsLoading = true;
      _autoSetsError = null;
      _autoSets = const [];
      _selectedSetIdx = -1;
      _sequence = const [];
    });
    try {
      final resp = await widget.apiClient.djSetGenerate(
        token: widget.token,
        songIds: _picked.map((s) => s.id).toList(),
      );
      final raw =
          (resp['sets'] as List<dynamic>? ?? const [])
              .cast<Map<String, dynamic>>();
      if (raw.isEmpty) {
        setState(() => _autoSetsError = '后端没有产出可用的 set，可能是歌曲数太少或元数据缺失');
      } else {
        // Auto-pick the highest-scored set so Step 3 unlocks; user can switch.
        setState(() {
          _autoSets = raw;
          _selectedSetIdx = 0;
        });
        _applySetToSequence(raw[0]);
      }
    } catch (e) {
      setState(() => _autoSetsError = 'AI 排歌失败: $e');
    } finally {
      if (mounted) setState(() => _autoSetsLoading = false);
    }
  }

  /// Convert a backend `set` payload into the legacy `_sequence` shape so
  /// downstream Steps 3 & 4 keep working without changes. Each entry needs
  /// {position, song_id, target_energy, actual_energy} — `position` is what
  /// the legacy UI casts via `as int`, so an int is required, not a num.
  void _applySetToSequence(Map<String, dynamic> setPayload) {
    final tracks =
        (setPayload['tracks'] as List<dynamic>? ?? const [])
            .map((e) => e.toString())
            .toList();
    final curve =
        (setPayload['energy_curve'] as List<dynamic>? ?? const [])
            .map((e) => (e as num).toDouble())
            .toList();
    final seq = <Map<String, dynamic>>[];
    for (var i = 0; i < tracks.length; i++) {
      final e = i < curve.length ? curve[i] : 0.5;
      seq.add({
        'position': i, // legacy UI does `entry['position'] as int`
        'song_id': tracks[i],
        'target_energy': e,
        'actual_energy': e,
      });
    }
    final plans = (setPayload['plans'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => e.cast<String, dynamic>())
        .toList(growable: false);
    setState(() {
      _sequence = seq;
      _activeSetPlans = plans;
    });
    // ignore: discarded_futures
    _loadEnergyForSequence();
  }

  void _pickSet(int idx) {
    if (idx < 0 || idx >= _autoSets.length) return;
    setState(() => _selectedSetIdx = idx);
    _applySetToSequence(_autoSets[idx]);
  }

  /// Map a sequencer preset to a v2 street-style key. Falls back to 'generic'
  /// when the preset's `scene` doesn't map to a v2 weight profile.
  String _v2StyleForPreset() {
    final preset = _presets.firstWhere(
      (p) => p['key'] == _preset,
      orElse: () => const <String, dynamic>{},
    );
    final scene = (preset['scene'] as String? ?? 'generic').toLowerCase();
    const sceneToStyle = <String, String>{
      'battle': 'breaking',
      'cypher': 'breaking',
      'class': 'hiphop',
      'showcase': 'popping',
      'generic': 'generic',
    };
    return sceneToStyle[scene] ?? 'generic';
  }

  Future<void> _loadEnergyForSequence() async {
    if (_sequence.isEmpty) return;
    final ids =
        _sequence
            .map((e) => e['song_id']?.toString())
            .whereType<String>()
            .toList();
    if (ids.isEmpty) return;
    setState(() => _energyLoading = true);
    final style = _v2StyleForPreset();
    final out = <String, Map<String, dynamic>>{};
    try {
      final results = await Future.wait(
        ids.map((id) async {
          try {
            final raw = await widget.apiClient.djSongEnergyV2(
              token: widget.token,
              songId: id,
              style: style,
            );
            // Backend wraps v2 result as {data: {version: 'v2', ...fields}}
            // but our _request unwraps to the inner map; either shape is fine.
            if (raw['version'] == 'v2' || raw.containsKey('total')) {
              return MapEntry(id, raw);
            }
            return MapEntry(id, <String, dynamic>{});
          } catch (_) {
            return MapEntry(id, <String, dynamic>{});
          }
        }),
      );
      for (final e in results) {
        if (e.value.isNotEmpty) out[e.key] = e.value;
      }
    } finally {
      if (mounted) {
        setState(() {
          _songEnergyV2 = out;
          _energyLoading = false;
        });
      }
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

  /// Resolve the song_id to send to RK. RK's edge-agent accepts both `int`
  /// (catalog Song.id) and `str` (LibrarySong UUID). The sync worker caches
  /// to `~/cypher/cache/{UUID}/` so the UUID is the safer choice; we fall
  /// back to the numeric catalog id when the LibrarySong came straight from
  /// the catalog (older paths).
  Object _rkIdForXfade(LibrarySong s) =>
      s.id.isNotEmpty ? s.id : (s.songId ?? 0);

  /// Legacy helper kept for the play() entry-point which uses a String body.
  String? _rkPlayId(LibrarySong s) {
    if (s.id.isNotEmpty) return s.id;
    final n = s.songId;
    return n == null ? null : n.toString();
  }

  bool _isMissingCacheError(Object e) {
    final s = e.toString();
    return s.contains(' 409') ||
        s.contains('409:') ||
        s.contains('original.wav') ||
        s.contains('SongCacheError');
  }

  /// edge-agent `XfadeRequest.style` is a strict Literal—any other value
  /// returns HTTP 422. Map backend/UI labels to one of these or fall back
  /// to a safe default.
  static const Set<String> _rkXfadeStyles = {
    'smooth',
    'power',
    'bass_swap',
    'echo_out',
    'filter',
    'cut',
    'slam',
    'fade',
    'rise',
    'blend',
    'wave',
    'melt',
    'vocal_handoff',
    'vocal_ducking',
    'drum_swap',
    'instrumental_only',
    'vocal_solo_intro',
    'echo_freeze',
  };

  /// Map Jetson `mixer_rules.py` 的 7+11 rule_key 到 RK `XfadeRequest.style`。
  /// 注意 RK 的 18 个 preset 只有音量/EQ 包络，没有 reverse/loop/echo FX。
  /// 后端 spin_back/loop_roll/back_to_back_drop 这种"戏剧性"rule 在 RK 上
  /// 真听不到原意，只能映射到"听起来不突兀"的近似 preset，并由 [_minFadeFor]
  /// 把过短的硬切 duration 抬到能软衔接的最小值，避免播出来生硬。
  static const Map<String, String> _ruleKeyToRkStyle = <String, String>{
    // 11 ANALYZED rules
    'harmonic_blend': 'blend',
    'eq_swap_4bar': 'filter',
    'filter_sweep_high': 'filter',
    'drop_swap': 'bass_swap',
    'echo_tail': 'echo_freeze',
    'loop_roll': 'wave', // was 'slam' (sounded like a glitch)
    'spin_back': 'filter', // was 'cut' (1.5s 硬切→现改高通扫频淡出)
    'drum_only_bridge': 'drum_swap',
    'key_lift': 'rise',
    'reverb_throw': 'echo_freeze',
    'back_to_back_drop': 'power', // was 'slam'
    // 7 RAW rules
    'raw_xfade_3s': 'blend',
    'raw_xfade_6s': 'blend',
    'raw_xfade_10s': 'melt',
    'raw_hard_cut': 'cut',
    'raw_fade_out_in': 'fade',
    'raw_echo_drop': 'echo_freeze',
    'raw_lp_swap': 'filter',
    // cross-style strategies
    'echo_out_hard_drop': 'echo_freeze',
    'percussion_bridge': 'drum_swap',
    'stem_strip_rebuild': 'vocal_handoff',
    'auto_bpm_ramp': 'rise',
    'half_time_double_time_pivot': 'drum_swap',
    'neutral_fx_bridge': 'melt',
    'breakdown_reset': 'fade',
    'impact_slam_cut': 'slam',
  };

  /// Per-rule minimum fade in seconds. The backend rule_key authoritatively
  /// describes _intent_; the duration_sec returned by the planner is what
  /// makes physical sense for the FX in the original spec (e.g. spin_back
  /// is 1.5s because that's how long a real reverse_decel is). Without the
  /// reverse FX on RK, those tiny windows produce a hard cut. Raise the
  /// floor for rules that *must* sound like a transition, not a splice.
  static const Map<String, double> _minFadeForRule = <String, double>{
    'spin_back': 5.0,
    'loop_roll': 4.0,
    'drop_swap': 4.0,
    'back_to_back_drop': 4.0,
    'echo_tail': 5.0,
    'reverb_throw': 5.0,
    'raw_hard_cut': 0.05, // legitimate hard cut
    'echo_out_hard_drop': 2.0,
    'percussion_bridge': 4.0,
    'stem_strip_rebuild': 4.0,
    'auto_bpm_ramp': 4.0,
    'half_time_double_time_pivot': 4.0,
    'neutral_fx_bridge': 2.0,
    'breakdown_reset': 2.0,
    'impact_slam_cut': 0.5,
  };

  String _rkStyle(String raw, {String fallback = 'smooth'}) {
    final k = raw.trim();
    if (_rkXfadeStyles.contains(k)) return k;
    final mapped = _ruleKeyToRkStyle[k];
    if (mapped != null && _rkXfadeStyles.contains(mapped)) return mapped;
    // Common aliases coming from backend / UI.
    const alias = <String, String>{
      'hard_cut': 'cut',
      'hardcut': 'cut',
      'instant': 'cut',
      'swap': 'cut',
      'crossfade': 'blend',
      'normal': 'blend',
      'soft': 'smooth',
    };
    final aliased = alias[k.toLowerCase()];
    if (aliased != null && _rkXfadeStyles.contains(aliased)) return aliased;
    return fallback;
  }

  Map<String, dynamic>? _asStringMap(Object? value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return null;
  }

  String _plannedRkStyle(
    Map<String, dynamic> plan,
    String rawRuleKey, {
    String fallback = 'blend',
  }) {
    final direct = plan['rk_style']?.toString();
    if (direct != null && _rkXfadeStyles.contains(direct)) return direct;
    final strategy = _asStringMap(plan['transition_strategy']);
    final strategyStyle = strategy?['rk_style']?.toString();
    if (strategyStyle != null && _rkXfadeStyles.contains(strategyStyle)) {
      return strategyStyle;
    }
    return _rkStyle(rawRuleKey, fallback: fallback);
  }

  String? _xfadeResultHint(Map<String, dynamic>? response) {
    if (response == null) return null;
    final result = _asStringMap(response['result']);
    final actualTier =
        response['actual_tier']?.toString() ??
        result?['playback_tier']?.toString();
    final actualStyle =
        response['actual_style']?.toString() ?? result?['style']?.toString();
    final degraded =
        response['degraded'] == true || result?['degraded'] == true;
    final degradeReason =
        response['degrade_reason']?.toString() ??
        result?['degrade_reason']?.toString();
    final parts = <String>[];
    if (actualTier != null && actualTier.isNotEmpty) {
      parts.add('tier:$actualTier');
    }
    if (actualStyle != null && actualStyle.isNotEmpty) {
      parts.add('style:$actualStyle');
    }
    if (degraded) {
      parts.add(
        degradeReason == null || degradeReason.isEmpty
            ? 'degraded'
            : 'degraded:$degradeReason',
      );
    }
    return parts.isEmpty ? null : parts.join(' / ');
  }

  Map<String, dynamic>? _canonicalPlanFor({
    required int transitionIndex,
    required LibrarySong prev,
    required LibrarySong next,
  }) {
    if (transitionIndex < 0 || transitionIndex >= _activeSetPlans.length) {
      return null;
    }
    final plan = _activeSetPlans[transitionIndex];
    final from = plan['from']?.toString();
    final to = plan['to']?.toString();
    if (from != null && from.isNotEmpty && from != prev.id) return null;
    if (to != null && to.isNotEmpty && to != next.id) return null;

    final spec =
        plan['spec'] is Map
            ? Map<String, dynamic>.from(plan['spec'] as Map)
            : <String, dynamic>{};
    final selected =
        plan['selected'] is Map
            ? Map<String, dynamic>.from(plan['selected'] as Map)
            : <String, dynamic>{};
    final fallback =
        plan['fallback'] is Map
            ? Map<String, dynamic>.from(plan['fallback'] as Map)
            : <String, dynamic>{};

    if (selected['transition_id'] != null) {
      spec['transition_id'] = selected['transition_id'];
    } else if (plan['transition_id'] != null) {
      spec['transition_id'] = plan['transition_id'];
    }
    spec['fallback_style'] ??=
        selected['fallback_style'] ?? fallback['rule_key'];
    spec['phase_anchor_sec'] ??= selected['phase_anchor_sec'];
    final automation = selected['automation'];
    if (automation is Map) {
      spec['stem_curves'] ??= automation['stem_curves'];
      spec['eq_curves'] ??= automation['eq_curves'];
    }
    for (final key in const [
      'rk_style',
      'timeline',
      'transition_strategy',
      'transition_context',
      'strategy_tags',
    ]) {
      spec[key] ??= selected[key] ?? plan[key] ?? fallback[key];
    }
    return spec.isEmpty ? null : spec;
  }

  /// Push the song's WAV from Jetson into RK cache via the sync-worker.
  /// Idempotent. After the sync RPC returns we **also** poll
  /// `sync-worker /cache/check` until `original.*` is actually visible on
  /// RK disk — sync-worker's response can race with the file write, and
  /// edge-agent's `/xfade` will 409 ("缺少 original.*") if it's invoked the
  /// instant the response lands but before fsync completes.
  Future<void> _ensureRkCache(LibrarySong song, {String? statusPrefix}) async {
    final id = song.id.isNotEmpty ? song.id : song.songId?.toString();
    if (id == null || id.isEmpty) {
      throw Exception('song ${song.title} 缺少 song_id，无法同步到 RK');
    }
    if (_prefetched.contains(id)) {
      // Re-verify: cache may have been evicted, partially written, or the
      // earlier "prefetched" mark was set after a sync that never actually
      // wrote `original.*`. Cheap (~50ms) compared to a 409 mid-set.
      if (await _sync.cacheExists(id)) return;
      _prefetched.remove(id);
    }
    if (_prefetchInFlight.contains(id)) {
      while (_prefetchInFlight.contains(id)) {
        await Future<void>.delayed(const Duration(milliseconds: 200));
      }
      if (_prefetched.contains(id) && await _sync.cacheExists(id)) return;
    }
    _prefetchInFlight.add(id);
    try {
      final manifest = await widget.apiClient.getSongManifest(
        token: widget.token,
        songId: song.id,
      );
      Object? lastErr;
      for (var attempt = 0; attempt < 2; attempt++) {
        try {
          await _sync.syncAndWait(
            tracks: [manifest],
            planId: 'dj-${DateTime.now().millisecondsSinceEpoch}-$id',
            timeout: const Duration(minutes: 2),
            onProgress: (st) {
              if (!mounted) return;
              setState(() {
                _cutInfo =
                    '${statusPrefix ?? '同步到 RK'} ${st.percent.toStringAsFixed(0)}%';
              });
            },
          );
          // syncAndWait returned ok — but sync-worker may still be flushing.
          // Poll cacheExists for up to 5s before declaring success.
          final deadline = DateTime.now().add(const Duration(seconds: 5));
          while (DateTime.now().isBefore(deadline)) {
            if (await _sync.cacheExists(id)) {
              _prefetched.add(id);
              return;
            }
            await Future<void>.delayed(const Duration(milliseconds: 200));
          }
          lastErr = Exception('sync 完成但 cache/check 仍未见 original.*');
        } catch (e) {
          lastErr = e;
        }
      }
      throw lastErr ?? Exception('sync 失败（未知原因）');
    } finally {
      _prefetchInFlight.remove(id);
    }
  }

  /// Background prefetch (fire-and-forget) for the next song so xfade is instant.
  ///
  /// Two layers:
  ///   1. sync-worker pulls the wav from Jetson onto RK disk (file IO),
  ///   2. edge-agent /prefetch decodes wav + 4 stems into audio-engine's
  ///      in-memory cache so deck.load() during /xfade hits cache (no IO).
  /// Without (2) every stem-aware rule (drop_swap / drum_only_bridge /
  /// instrumental_bridge) blocks the xfade response 300ms-2s on file IO.
  void _kickPrefetchNext() {
    final ordered = _orderedSongs();
    final i = _liveIdx + 1;
    if (i < 0 || i >= ordered.length) return;
    final s = ordered[i];
    final id = s.id.isNotEmpty ? s.id : s.songId?.toString();
    if (id == null ||
        _prefetched.contains(id) ||
        _prefetchInFlight.contains(id)) {
      return;
    }
    // ignore: discarded_futures
    _ensureRkCache(s, statusPrefix: '预取下一首')
        .then((_) async {
          // Now that the wav is on RK disk, ask audio-engine to decode it +
          // stems into memory so the next xfade is instant.
          try {
            await widget.edgeClient.prefetch(songIds: [_rkIdForXfade(s)]);
          } catch (_) {
            /* best-effort */
          }
        })
        .catchError((_) {});
  }

  /// Live-mix-wide prefetch: while the first song plays, pull every remaining
  /// track's wav onto RK disk **serially** so we don't fight Jetson's egress
  /// bandwidth. This replaces the older "only fetch when remaining ≤ 30s"
  /// path which raced the xfade trigger when a track was short or the user
  /// hit a manual cut. Each track is followed by edge-agent /prefetch so the
  /// audio-engine has the decoded wav + 4 stems in memory before xfade fires.
  ///
  /// Cancellation: when [_liveStarted] flips false (user left live mix) we
  /// stop the loop on the next iteration. Errors per track are logged into
  /// [_cutInfo] but never abort the loop — we still want #3 to be ready even
  /// if #2 failed temporarily.
  Future<void> _warmAllRemainingTracks(int startIdx) async {
    final ordered = _orderedSongs();
    for (var i = startIdx; i < ordered.length; i++) {
      if (!mounted || !_liveStarted) return;
      final s = ordered[i];
      final id = s.id.isNotEmpty ? s.id : s.songId?.toString();
      if (id == null || id.isEmpty) continue;
      if (_prefetched.contains(id) && await _sync.cacheExists(id)) {
        continue;
      }
      try {
        await _ensureRkCache(
          s,
          statusPrefix: '后台预取 ${i + 1}/${ordered.length}',
        );
        try {
          await widget.edgeClient.prefetch(songIds: [_rkIdForXfade(s)]);
        } catch (_) {
          /* best-effort: file is on disk, decode is optional */
        }
      } catch (e) {
        if (mounted) {
          setState(() {
            _cutInfo = '后台预取 #${i + 1} 失败: $e';
          });
        }
        // 继续拉下一首 — 某一首失败不应阻塞队列
      }
    }
    if (mounted && _liveStarted) {
      setState(() => _cutInfo = '✅ 所有曲目已就位');
    }
  }

  Future<void> _startLiveMix() async {
    final ordered = _orderedSongs();
    if (ordered.isEmpty) return;
    final first = ordered.first;
    final rkId = _rkPlayId(first);
    if (rkId == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('首曲缺少 song_id，RK 无法识别')));
      return;
    }
    setState(() {
      _liveStarted = true;
      _liveIdx = 0;
      _lastXfadeFromIdx = -1;
      _lastXfadeAt = null;
      _lastXfadeSec = 0.0;
      _lastXfadeToSongId = null;
      _smartPlan = null;
      _smartPlanForSongId = null;
      _step = 3; // jump to 实时操作
      _cutInfo = '正在同步首曲到 RK…';
    });
    try {
      // 1) Make sure RK has the wav cached. Skips quickly if already cached.
      await _ensureRkCache(first, statusPrefix: '同步首曲到 RK');
      // 2) Tell edge-agent to start playback.
      await widget.edgeClient.play(songId: rkId, startAtSec: 0);
      if (mounted) setState(() => _cutInfo = '▶ ${first.title}');
      // 3) Warm up *every* remaining song serially in the background. Single
      //    pipe to Jetson keeps egress simple; the loop survives per-track
      //    failures so a transient miss on #2 doesn't starve #3+.
      // ignore: discarded_futures
      _warmAllRemainingTracks(1);
    } catch (e) {
      // Last-ditch retry: if play failed with 409 we may have missed the sync.
      if (_isMissingCacheError(e)) {
        try {
          await _ensureRkCache(first, statusPrefix: '同步首曲到 RK');
          await widget.edgeClient.play(songId: rkId, startAtSec: 0);
          if (mounted) setState(() => _cutInfo = '▶ ${first.title}');
          // ignore: discarded_futures
          _warmAllRemainingTracks(1);
        } catch (e2) {
          if (mounted) {
            ScaffoldMessenger.of(
              context,
            ).showSnackBar(SnackBar(content: Text('RK 启动失败: $e2')));
          }
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text('RK 启动失败: $e')));
        }
      }
    }
    _startRkPolling();
  }

  void _startRkPolling() {
    _rkPoll?.cancel();
    _rkPoll = Timer.periodic(const Duration(milliseconds: 600), (_) async {
      if (!mounted) return;
      try {
        final st = await widget.edgeClient.getState();
        if (!mounted) return;
        setState(() {
          _isPlaying = st.playing;
          _position = Duration(milliseconds: (st.positionSec * 1000).round());
          _duration = Duration(milliseconds: (st.durationSec * 1000).round());
          _rkCurrentSongId = st.currentSongId;
        });
        _maybeAutoXfade();
      } catch (_) {
        /* swallow */
      }
    });
  }

  Future<void> _maybeAutoXfade() async {
    if (_xfadeInFlight) return;
    if (_liveIdx == _lastXfadeFromIdx) return;
    final ordered = _orderedSongs();
    if (_liveIdx + 1 >= ordered.length) return;

    // Lockout: while RK still reports the song we just xfaded TO, the previous
    // fade is either still running or just finished — refuse to fire again.
    // Combined with a wall-clock cooldown that outlasts the fade duration,
    // this prevents the cascade where one trigger eats through the queue.
    if (_lastXfadeToSongId != null &&
        _rkCurrentSongId != null &&
        _rkCurrentSongId == _lastXfadeToSongId) {
      final settled = _position.inMilliseconds / 1000.0 > _lastXfadeSec + 4.0;
      if (!settled) return;
    }

    // Cooldown: at least max(8s, fade_sec + 4s) since last xfade.
    final last = _lastXfadeAt;
    if (last != null) {
      final cooldownSec = math.max(8.0, _lastXfadeSec + 4.0);
      if (DateTime.now().difference(last).inMilliseconds < cooldownSec * 1000) {
        return;
      }
    }

    final prev = ordered[_liveIdx];
    final next = ordered[_liveIdx + 1];
    final positionSec = _position.inMilliseconds / 1000.0;
    final durationSec = _duration.inMilliseconds / 1000.0;
    final remainingSec =
        durationSec > 0 ? durationSec - positionSec : double.infinity;

    // --- Smart plan pre-fetch ---
    // When the track is within 30s of its end, fetch the phrase-aligned plan
    // ahead of time so we know exactly when (from_at_sec) and how
    // (to_at_sec / duration_sec / rule) to fire the xfade. Cached per song.
    if (remainingSec <= 30.0 &&
        _smartPlanForSongId != prev.id &&
        !_smartPlanInFlight) {
      _smartPlanInFlight = true;
      try {
        // Prefetch the next song's wav into RK cache while we plan.
        // Then immediately ask audio-engine to decode it + stems into memory
        // so the xfade response isn't blocked on file IO when it fires.
        // ignore: discarded_futures
        _ensureRkCache(next, statusPrefix: '预取下一首')
            .then((_) async {
              try {
                await widget.edgeClient.prefetch(
                  songIds: [_rkIdForXfade(next)],
                );
              } catch (_) {
                /* best-effort */
              }
            })
            .catchError((_) {});
        final plan =
            _canonicalPlanFor(
              transitionIndex: _liveIdx,
              prev: prev,
              next: next,
            ) ??
            await widget.apiClient.djPlanTransition(
              token: widget.token,
              prevSongId: prev.id,
              nextSongId: next.id,
              cursorSec: positionSec,
            );
        if (!mounted) return;
        setState(() {
          _smartPlan = plan;
          _smartPlanForSongId = prev.id;
        });
        // Phase 2: if the plan asks for a tempo align, kick a background
        // rubberband render so xfade isn't blocked on it later.
        final ratio = (plan['tempo_ratio'] as num?)?.toDouble();
        final nextRkId = _rkIdForXfade(next);
        if (ratio != null &&
            (ratio - 1.0).abs() >= 0.005 &&
            (ratio - 1.0).abs() <= 0.06) {
          // ignore: discarded_futures
          widget.edgeClient
              .prewarmBeatmatch(songId: nextRkId, tempoRatio: ratio)
              .catchError((_) => <String, dynamic>{});
        }
      } catch (_) {
        // ignore — fall back to legacy trigger below
      } finally {
        _smartPlanInFlight = false;
      }
    }

    // --- Trigger decision ---
    // If we have a smart plan and the cursor has reached its exit point, fire.
    // Otherwise fall back to the legacy "remaining ≤ 5s" trigger so we never
    // miss a transition when the planner produced no usable exit.
    final smart =
        (_smartPlan != null && _smartPlanForSongId == prev.id)
            ? _smartPlan
            : null;
    final smartExitAt = (smart?['from_at_sec'] as num?)?.toDouble();
    final bool shouldTrigger;
    if (smartExitAt != null && smartExitAt > 0) {
      // Belt-and-suspenders: even if the planner missed the moment (RK
      // duration was reported wrong, polling missed a tick, etc.), force
      // the trigger as soon as we're near the reported end.
      shouldTrigger =
          positionSec >= smartExitAt ||
          (durationSec > 0 && remainingSec <= 1.0) ||
          (!_isPlaying && positionSec > 5.0);
    } else if (durationSec > 0) {
      shouldTrigger = remainingSec <= 5.0 || (!_isPlaying && positionSec > 5.0);
    } else {
      shouldTrigger = !_isPlaying && positionSec > 30.0;
    }
    if (!shouldTrigger) return;

    final nextRkId = _rkIdForXfade(next);

    _xfadeInFlight = true;
    try {
      await _ensureRkCache(next, statusPrefix: '同步下一首到 RK');

      // Use the cached smart plan if we have one; otherwise fetch on the spot
      // (legacy path).
      Map<String, dynamic> plan =
          smart ??
          _canonicalPlanFor(
            transitionIndex: _liveIdx,
            prev: prev,
            next: next,
          ) ??
          await widget.apiClient.djPlanTransition(
            token: widget.token,
            prevSongId: prev.id,
            nextSongId: next.id,
            cursorSec: positionSec,
          );

      final rawRuleKey = plan['rule_key']?.toString() ?? 'blend';
      final ruleKey = _plannedRkStyle(plan, rawRuleKey, fallback: 'blend');
      final ruleLabel = plan['rule_label_zh']?.toString() ?? rawRuleKey;
      final rawDur =
          (plan['duration_sec'] as num?)?.toDouble() ??
          (plan['fade_sec'] as num?)?.toDouble() ??
          6.0;
      final minFade = _minFadeForRule[rawRuleKey] ?? 0.05;
      final fadeSec = math.max(minFade, rawDur).clamp(0.05, 30.0).toDouble();

      // Phase-1: enter next song at the planned point (skips intro silence /
      // build-up). Falls back to 0 when the backend didn't provide one.
      final toAtSec = (plan['to_at_sec'] as num?)?.toDouble() ?? 0.0;
      final exitSection = plan['exit_section']?.toString();
      final skippedIntro =
          (plan['skipped_intro_sec'] as num?)?.toDouble() ?? 0.0;
      // Phase-2: tempo align hint.
      final tempoRatio = (plan['tempo_ratio'] as num?)?.toDouble();
      final alignStrategy = plan['align_strategy']?.toString() ?? 'skip';
      final transitionId = plan['transition_id']?.toString();
      final fallbackStyle = plan['fallback_style']?.toString();
      final phaseAnchorSec = (plan['phase_anchor_sec'] as num?)?.toDouble();

      // Phase 3.1 — surface stem strategy on cutInfo so the operator sees
      // when bass is actually being swapped vs faded. Highlight non-trivial
      // curves only (skip the "all linear" trivial case).
      final stemCurves = plan['stem_curves'];
      final eqCurves = plan['eq_curves'];
      String? stemHint;
      if (stemCurves is Map) {
        final prev = stemCurves['prev'];
        final next = stemCurves['next'];
        final highlights = <String>[];
        if (prev is Map && next is Map) {
          if (prev['bass'] == 'out_at_break' && next['bass'] == 'in_at_break') {
            highlights.add('bass互换');
          }
          if (prev['drums'] == 'hold' || prev['drums'] == 'hold_then_out') {
            highlights.add('鼓桥接');
          }
          if (next['vocals'] == 'in_late') {
            highlights.add('人声后入');
          }
        }
        if (highlights.isNotEmpty) stemHint = highlights.join('+');
      }

      // Phase 2.5 — beat reinforcement. Fire-and-forget BEFORE xfade so the
      // schedule is anchored against active_deck.pos_sec at the moment of
      // crossfade start. RK drops events that slip >100ms past the clock.
      final reinforceTags = <String>[];
      final reinforce = plan['beat_reinforce'];
      if (reinforce is Map) {
        Future<void> _fireSide(String side) async {
          final cfg = reinforce[side];
          if (cfg is! Map) return;
          final beatsRaw = cfg['beats'];
          if (beatsRaw is! List || beatsRaw.isEmpty) return;
          final beats = beatsRaw
              .whereType<num>()
              .map((n) => n.toDouble())
              .toList(growable: false);
          try {
            await widget.edgeClient.beatReinforce(
              startSec: (cfg['start_sec'] as num?)?.toDouble() ?? 0.0,
              endSec: (cfg['end_sec'] as num?)?.toDouble() ?? 0.0,
              beats: beats,
              sampleKey: (cfg['sample_key'] as num?)?.toInt() ?? 4,
              gain: (cfg['gain'] as num?)?.toDouble() ?? 1.0,
              pattern: cfg['pattern']?.toString() ?? 'all',
            );
            reinforceTags.add(
              '${side == "prev" ? "出" : "入"}加鼓×${beats.length}',
            );
          } catch (_) {
            /* swallow — reinforcement is best-effort */
          }
        }

        // Run sequentially so the second call sees up-to-date scheduler state.
        await _fireSide('prev');
        await _fireSide('next');
      }

      Future<Map<String, dynamic>> doXfade() => widget.edgeClient.xfade(
        toSongId: nextRkId,
        fadeSec: fadeSec,
        toAtSec: toAtSec,
        style: ruleKey,
        transitionId: transitionId,
        fallbackStyle:
            fallbackStyle == null
                ? null
                : _rkStyle(fallbackStyle, fallback: 'blend'),
        tempoRatio: tempoRatio,
        stemCurves:
            stemCurves is Map<String, dynamic>
                ? stemCurves
                : (stemCurves is Map
                    ? Map<String, dynamic>.from(stemCurves)
                    : null),
        eqCurves:
            eqCurves is Map<String, dynamic>
                ? eqCurves
                : (eqCurves is Map
                    ? Map<String, dynamic>.from(eqCurves)
                    : null),
        phaseAnchorSec: phaseAnchorSec,
      );
      Map<String, dynamic>? xfadeResponse;
      try {
        xfadeResponse = await doXfade();
      } catch (e) {
        if (_isMissingCacheError(e)) {
          await _ensureRkCache(next, statusPrefix: '同步下一首到 RK');
          xfadeResponse = await doXfade();
        } else {
          rethrow;
        }
      }
      if (!mounted) return;
      setState(() {
        _lastXfadeFromIdx = _liveIdx;
        _liveIdx += 1;
        _activeRule = '$ruleLabel · ${fadeSec.toStringAsFixed(1)}s';
        final tail = <String>[];
        if (exitSection != null && exitSection.isNotEmpty)
          tail.add('出@$exitSection');
        if (skippedIntro >= 0.5)
          tail.add('入+${skippedIntro.toStringAsFixed(1)}s');
        if (tempoRatio != null && alignStrategy != 'skip') {
          tail.add(
            '对速${alignStrategy == "match" ? "" : "(${alignStrategy})"} ×${tempoRatio.toStringAsFixed(3)}',
          );
        }
        if (reinforceTags.isNotEmpty) {
          tail.add(reinforceTags.join('+'));
        }
        if (stemHint != null) {
          tail.add('stem:$stemHint');
        }
        final xfadeHint = _xfadeResultHint(xfadeResponse);
        if (xfadeHint != null) {
          tail.add(xfadeHint);
        }
        final tailStr = tail.isEmpty ? '' : '（${tail.join(' · ')}）';
        _cutInfo = '自动衔接 → #${_liveIdx + 1}：$ruleLabel$tailStr';
        _lastXfadeAt = DateTime.now();
        _lastXfadeSec = fadeSec;
        _lastXfadeToSongId = nextRkId.toString();
        _smartPlan = null;
        _smartPlanForSongId = null;
      });
      _kickPrefetchNext();
    } catch (e) {
      // Failure cooldown: even if xfade failed (409 because the song finished
      // and active deck went away, or 503, etc.), don't hammer at every poll.
      // Hold off for 4s before another attempt; if the failure is transient,
      // RK will recover by then.
      if (mounted) {
        setState(() {
          _cutInfo = '自动衔接失败: $e';
          _lastXfadeAt = DateTime.now();
          _lastXfadeSec = 0.0;
        });
      }
    } finally {
      _xfadeInFlight = false;
    }
  }

  Future<void> _advanceLive() async {
    final ordered = _orderedSongs();
    final next = _liveIdx + 1;
    if (next >= ordered.length) {
      await widget.edgeClient.pause();
      setState(() => _isPlaying = false);
      return;
    }
    final nextSong = ordered[next];
    final nextRk = _rkIdForXfade(nextSong);
    try {
      await _ensureRkCache(nextSong, statusPrefix: '同步下一首到 RK');
      // Hard cut via xfade w/ tiny fade.
      Future<void> doCut() => widget.edgeClient.xfade(
        toSongId: nextRk,
        fadeSec: 0.4,
        toAtSec: 0.0,
        style: 'cut',
      );
      try {
        await doCut();
      } catch (e) {
        if (_isMissingCacheError(e)) {
          await _ensureRkCache(nextSong, statusPrefix: '同步下一首到 RK');
          await doCut();
        } else {
          rethrow;
        }
      }
      setState(() {
        _liveIdx = next;
        _lastXfadeFromIdx = next - 1;
        _lastXfadeAt = DateTime.now();
        _lastXfadeSec = 0.4;
        _lastXfadeToSongId = nextRk.toString();
        _cutInfo = '手动跳到 #${next + 1}';
      });
      _kickPrefetchNext();
    } catch (e) {
      setState(() => _cutInfo = '跳曲失败: $e');
    }
  }

  Future<void> _togglePlay() async {
    try {
      if (_isPlaying) {
        await widget.edgeClient.pause();
      } else {
        await widget.edgeClient.resume();
      }
    } catch (e) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('RK 控制失败: $e')));
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
      final nextId = plan['next_song_id']?.toString();
      final cutAt =
          (plan['cut_at_sec'] as num?)?.toDouble() ??
          _position.inMilliseconds / 1000.0;
      if (nextId == null) {
        setState(() => _cutInfo = '⏭ $strategy → 队尾，无下一首');
        return;
      }
      // Resolve target song.
      final byId = {for (final s in _picked) s.id: s};
      final target =
          byId[nextId] ??
          ordered.firstWhere((s) => s.id == nextId, orElse: () => current);
      final targetRk = _rkIdForXfade(target);
      final inOrderIdx = ordered.indexWhere((s) => s.id == nextId);
      await _ensureRkCache(target, statusPrefix: '同步切换目标到 RK');

      // Use 7+11 transition rules: plan transition from cut point.
      final transition = await widget.apiClient.djPlanTransition(
        token: widget.token,
        prevSongId: current.id,
        nextSongId: nextId,
        cursorSec: cutAt,
      );
      final rawRuleKey = transition['rule_key']?.toString() ?? 'blend';
      final ruleKey = _plannedRkStyle(
        transition,
        rawRuleKey,
        fallback: 'blend',
      );
      final ruleLabel = transition['rule_label_zh']?.toString() ?? rawRuleKey;
      final rawDur =
          (transition['duration_sec'] as num?)?.toDouble() ??
          (transition['fade_sec'] as num?)?.toDouble() ??
          6.0;
      final minFade = _minFadeForRule[rawRuleKey] ?? 0.05;
      final fadeSec = math.max(minFade, rawDur).clamp(0.05, 30.0).toDouble();

      Future<Map<String, dynamic>> doXfade() => widget.edgeClient.xfade(
        toSongId: targetRk,
        fadeSec: fadeSec,
        toAtSec: (transition['to_at_sec'] as num?)?.toDouble() ?? 0.0,
        style: ruleKey,
        transitionId: transition['transition_id']?.toString(),
        fallbackStyle:
            transition['fallback_style'] == null
                ? null
                : _rkStyle(
                  transition['fallback_style'].toString(),
                  fallback: 'blend',
                ),
        tempoRatio: (transition['tempo_ratio'] as num?)?.toDouble(),
        stemCurves:
            transition['stem_curves'] is Map<String, dynamic>
                ? transition['stem_curves'] as Map<String, dynamic>
                : (transition['stem_curves'] is Map
                    ? Map<String, dynamic>.from(
                      transition['stem_curves'] as Map,
                    )
                    : null),
        eqCurves:
            transition['eq_curves'] is Map<String, dynamic>
                ? transition['eq_curves'] as Map<String, dynamic>
                : (transition['eq_curves'] is Map
                    ? Map<String, dynamic>.from(transition['eq_curves'] as Map)
                    : null),
        phaseAnchorSec: (transition['phase_anchor_sec'] as num?)?.toDouble(),
      );
      Map<String, dynamic>? xfadeResponse;
      try {
        xfadeResponse = await doXfade();
      } catch (e) {
        if (_isMissingCacheError(e)) {
          await _ensureRkCache(target, statusPrefix: '同步切换目标到 RK');
          xfadeResponse = await doXfade();
        } else {
          rethrow;
        }
      }
      setState(() {
        if (inOrderIdx > _liveIdx) {
          _liveIdx = inOrderIdx;
        } else {
          _liveIdx = _liveIdx + 1;
        }
        _lastXfadeFromIdx = _liveIdx - 1;
        _lastXfadeAt = DateTime.now();
        _lastXfadeSec = fadeSec;
        _lastXfadeToSongId = targetRk.toString();
        _activeRule = '$ruleLabel · ${fadeSec.toStringAsFixed(1)}s';
        final xfadeHint = _xfadeResultHint(xfadeResponse);
        _cutInfo =
            '⏭ $strategy → ${target.title} · $ruleLabel'
            '${xfadeHint == null ? "" : " · $xfadeHint"}';
      });
      _kickPrefetchNext();
    } catch (e) {
      setState(() => _cutInfo = '切歌失败: $e');
    }
  }

  Future<void> _playFx(String key) async {
    // Prefer triggering on the RK speaker (mixed onto the live audio bus) via
    // /trigger {key:int}. The backend FX catalog now exposes `rk_key`; if it's
    // present we hit RK directly. Fall back to playing the rendered wav on the
    // phone speaker only when RK has no matching sample slot.
    int? rkKey;
    for (final fx in _fxItems) {
      if (fx['key'] == key) {
        final raw = fx['rk_key'];
        if (raw is int) rkKey = raw;
        if (raw is num) rkKey = raw.toInt();
        break;
      }
    }
    if (rkKey != null) {
      try {
        await widget.edgeClient.trigger(rkKey);
        return;
      } catch (e) {
        if (mounted)
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text('RK FX 失败，回退本机: $e')));
      }
    }
    try {
      await _fxPlayer.stop();
      await _fxPlayer.setUrl(widget.apiClient.djFxAudioUrl(key));
      await _fxPlayer.play();
    } catch (e) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('FX 失败: $e')));
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
        if (_liveStarted)
          _LiveMixBar(
            ordered: _orderedSongs(),
            idx: _liveIdx,
            isPlaying: _isPlaying,
            position: _position,
            duration: _duration,
            activeRule: _activeRule,
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
    if (_step == 2) return _sequence.isNotEmpty; // start live
    return false; // step 3 is the last (live)
  }

  Future<void> _onNext() async {
    if (_step == 2) {
      if (!_liveStarted) {
        await _startLiveMix();
      } else {
        setState(() => _step = 3);
      }
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
          userId: widget.userId,
          library: widget.librarySongs,
          playlists: _playlists,
          picked: _picked,
          onAdd: _addSongs,
          onRemove: _removeSong,
          onClear:
              () => setState(() {
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
          buckets: _energyBuckets,
          songEnergy: _songEnergyV2,
          energyLoading: _energyLoading,
          onPickPreset: (k) => setState(() => _preset = k),
          onRun: _runSequence,
          autoSets: _autoSets,
          selectedSetIdx: _selectedSetIdx,
          autoSetsLoading: _autoSetsLoading,
          autoSetsError: _autoSetsError,
          onRunAutoSets: _runAutoSets,
          onPickSet: _pickSet,
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
        return _Step4Live(
          ordered: _orderedSongs(),
          idx: _liveIdx,
          liveStarted: _liveStarted,
          fxItems: _fxItems,
          onCut: _doCut,
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

  static const _labels = ['选歌', '排歌', '混音', '实时操作'];
  static const _icons = ['🎯', '📈', '🎚️', '🎛️'];

  bool _reachable(int i) {
    if (i == 0) return true;
    if (i == 1) return pickedCount >= 2;
    if (i == 2) return sequencedCount > 0;
    if (i == 3) return liveStarted || sequencedCount > 0;
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
          children: List.generate(4, (i) {
            final active = i == step;
            final done = i < step;
            final reachable = _reachable(i);
            return GestureDetector(
              onTap: reachable ? () => onJump(i) : null,
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 3),
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color:
                      active
                          ? const Color(0xFFE85A2A)
                          : done
                          ? const Color(0xFFE85A2A).withOpacity(0.35)
                          : reachable
                          ? const Color(0x08000000)
                          : const Color(0x0A000000),
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
    String nextLabel;
    if (step == 2) {
      nextLabel = '开始混音 ▶';
    } else if (step == 3) {
      nextLabel = '已到最后';
    } else {
      nextLabel = '下一步 →';
    }
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
            onPressed: canNext && step < 3 ? onNext : null,
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFE85A2A),
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
    required this.activeRule,
    required this.onPlayPause,
    required this.onNext,
    required this.cutInfo,
  });
  final List<LibrarySong> ordered;
  final int idx;
  final bool isPlaying;
  final Duration position;
  final Duration duration;
  final String? activeRule;
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
    final pct =
        duration.inMilliseconds == 0
            ? 0.0
            : (position.inMilliseconds / duration.inMilliseconds).clamp(
              0.0,
              1.0,
            );
    return Container(
      color: const Color(0xFF1A1A1A),
      padding: const EdgeInsets.fromLTRB(10, 6, 10, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              IconButton(
                icon: Icon(
                  isPlaying
                      ? Icons.pause_circle_filled
                      : Icons.play_circle_fill,
                  size: 28,
                  color: const Color(0xFFE85A2A),
                ),
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
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF1A1A1A),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      '下一首：${next?.title ?? '—'}',
                      style: const TextStyle(
                        fontSize: 10,
                        color: const Color(0xFF555555),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              Text(
                '${_fmt(position)}/${_fmt(duration)}',
                style: const TextStyle(fontSize: 11, color: Color(0xFF1A1A1A)),
              ),
              IconButton(
                icon: const Icon(
                  Icons.skip_next,
                  size: 24,
                  color: Color(0xFF1A1A1A),
                ),
                onPressed: onNext,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 30, minHeight: 30),
              ),
            ],
          ),
          const SizedBox(height: 4),
          LinearProgressIndicator(
            value: pct,
            backgroundColor: const Color(0x08000000),
            valueColor: const AlwaysStoppedAnimation(const Color(0xFFE85A2A)),
            minHeight: 3,
          ),
          if (cutInfo != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                cutInfo!,
                style: const TextStyle(
                  fontSize: 10,
                  color: const Color(0xFFE85A2A),
                ),
              ),
            ),
          if (activeRule != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                '当前过渡：$activeRule',
                style: const TextStyle(fontSize: 10, color: Color(0xFF2E7D32)),
              ),
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
    required this.userId,
    required this.library,
    required this.playlists,
    required this.picked,
    required this.onAdd,
    required this.onRemove,
    required this.onClear,
  });
  final HarBeatApiClient api;
  final String token;
  final int userId;
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
        if (_mode == 0)
          _ImportSource(
            api: widget.api,
            token: widget.token,
            playlists: widget.playlists,
            library: widget.library,
            onAdd: widget.onAdd,
          ),
        if (_mode == 1)
          _VibeSource(
            api: widget.api,
            token: widget.token,
            userId: widget.userId,
            library: widget.library,
            onAdd: widget.onAdd,
          ),
        if (_mode == 2)
          _StyleSource(
            api: widget.api,
            token: widget.token,
            library: widget.library,
            onAdd: widget.onAdd,
          ),
        const SizedBox(height: 10),
        _PickedPool(
          picked: widget.picked,
          onRemove: widget.onRemove,
          onClear: widget.onClear,
        ),
      ],
    );
  }

  Widget _modeBtn(int i, String label) {
    final active = _mode == i;
    return Expanded(
      child: ElevatedButton(
        onPressed: () => setState(() => _mode = i),
        style: ElevatedButton.styleFrom(
          backgroundColor:
              active ? const Color(0xFFE85A2A) : const Color(0x0A000000),
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
  const _PickedPool({
    required this.picked,
    required this.onRemove,
    required this.onClear,
  });
  final List<LibrarySong> picked;
  final void Function(String) onRemove;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final totalSec = picked.fold<double>(0.0, (a, s) => a + s.duration);
    return Card(
      color: const Color(0x0A000000),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '已选池（${picked.length} · ${(totalSec / 60).toStringAsFixed(1)} 分钟）',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
                if (picked.isNotEmpty)
                  TextButton(onPressed: onClear, child: const Text('清空')),
              ],
            ),
            if (picked.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 6),
                child: Text(
                  '还没选歌',
                  style: TextStyle(fontSize: 11, color: Colors.grey),
                ),
              ),
            ...picked.asMap().entries.map((e) {
              final i = e.key, s = e.value;
              return Container(
                padding: const EdgeInsets.symmetric(vertical: 3),
                decoration: const BoxDecoration(
                  border: Border(
                    top: BorderSide(color: const Color(0x08000000)),
                  ),
                ),
                child: Row(
                  children: [
                    SizedBox(
                      width: 26,
                      child: Text(
                        '#${i + 1}',
                        style: const TextStyle(
                          fontSize: 10,
                          color: Colors.grey,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Text(
                        '${s.title}  ·  ${s.artist}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12),
                      ),
                    ),
                    Text(
                      s.bpm != null ? '${s.bpm!.toStringAsFixed(0)}BPM' : '-',
                      style: const TextStyle(fontSize: 10, color: Colors.grey),
                    ),
                    IconButton(
                      icon: const Icon(
                        Icons.close,
                        size: 16,
                        color: Colors.redAccent,
                      ),
                      onPressed: () => onRemove(s.id),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(
                        minWidth: 24,
                        minHeight: 24,
                      ),
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
    required this.api,
    required this.token,
    required this.playlists,
    required this.library,
    required this.onAdd,
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
  int _sub = 0; // 0=歌单, 1=链接, 2=曲库

  // --- Playlist sub ---
  int? _pid;
  bool _loading = false;
  String? _msg;
  List<LibrarySong> _matched = const [];
  final Set<String> _sel = {};

  // --- URL import sub ---
  final TextEditingController _urlCtrl = TextEditingController();
  bool _urlLoading = false;
  String? _urlMsg;
  List<ExternalPlaylistTrack> _urlTracks = const [];
  String? _urlPlaylistName;
  final Set<int> _urlSel = {};
  bool _urlDownloading = false;
  String? _urlDownloadMsg;

  // --- Library sub ---
  String _libQuery = '';

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  // ---- Playlist logic ----
  Future<void> _loadDetail() async {
    if (_pid == null) return;
    setState(() {
      _loading = true;
      _msg = null;
      _matched = const [];
      _sel.clear();
    });
    try {
      // pid == -1 is the virtual "曲库（全部）" entry
      if (_pid == -1) {
        setState(() {
          _matched = List.of(widget.library);
          _sel.addAll(widget.library.map((s) => s.id));
          _msg = '曲库全部 ${widget.library.length} 首';
        });
      } else {
        final detail = await widget.api.getPlaylistDetail(
          token: widget.token,
          playlistId: _pid!,
        );
        final libKey = <String, LibrarySong>{};
        for (final s in widget.library) {
          libKey['${s.title.toLowerCase()}|${s.artist.toLowerCase()}'] = s;
        }
        final hits = <LibrarySong>[];
        for (final ps in detail.songs) {
          final hit =
              libKey['${ps.title.toLowerCase()}|${ps.artist.toLowerCase()}'];
          if (hit != null) hits.add(hit);
        }
        setState(() {
          _matched = hits;
          _sel.addAll(hits.map((s) => s.id));
          _msg = '匹配 ${hits.length}/${detail.songs.length} 首';
        });
      }
    } catch (e) {
      setState(() => _msg = '错误: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _commitPlaylist() {
    final picks = _matched.where((s) => _sel.contains(s.id));
    widget.onAdd(picks);
    if (mounted)
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('加入 ${picks.length} 首'),
          duration: const Duration(seconds: 1),
        ),
      );
  }

  // ---- URL import logic ----
  Future<void> _parseUrl() async {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) return;
    setState(() {
      _urlLoading = true;
      _urlMsg = null;
      _urlTracks = const [];
      _urlSel.clear();
      _urlPlaylistName = null;
    });
    try {
      final result = await widget.api.parseExternalPlaylist(
        token: widget.token,
        url: url,
      );
      setState(() {
        _urlPlaylistName = result.name;
        _urlTracks = result.tracks;
        _urlSel.addAll(List.generate(result.tracks.length, (i) => i));
        _urlMsg = '${result.source ?? ''} · ${result.tracks.length} 首';
      });
    } catch (e) {
      setState(() => _urlMsg = '解析失败: $e');
    } finally {
      if (mounted) setState(() => _urlLoading = false);
    }
  }

  Future<void> _downloadUrlTracks() async {
    if (_urlSel.isEmpty) return;
    setState(() {
      _urlDownloading = true;
      _urlDownloadMsg = '搜索中…';
    });
    try {
      final selected = _urlSel.map((i) => _urlTracks[i]).toList();
      final searchResults = await widget.api.batchSearchExternal(
        token: widget.token,
        tracks: selected,
      );
      int downloaded = 0;
      int failed = 0;
      for (int i = 0; i < searchResults.length; i++) {
        final entry = searchResults[i];
        if (entry.candidates.isEmpty) {
          failed++;
          continue;
        }
        final best = entry.candidates.first;
        try {
          setState(
            () => _urlDownloadMsg = '下载 ${i + 1}/${searchResults.length}…',
          );
          await widget.api.downloadFangpiCandidate(
            token: widget.token,
            candidate: best,
          );
          downloaded++;
        } catch (_) {
          failed++;
        }
      }
      setState(
        () =>
            _urlDownloadMsg =
                '完成: 导入 $downloaded 首${failed > 0 ? '，失败 $failed' : ''}',
      );
    } catch (e) {
      setState(() => _urlDownloadMsg = '批量导入失败: $e');
    } finally {
      if (mounted) setState(() => _urlDownloading = false);
    }
  }

  // ---- Library logic ----
  void _commitLibrary(Iterable<LibrarySong> songs) {
    widget.onAdd(songs);
    if (mounted)
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('加入 ${songs.length} 首'),
          duration: const Duration(seconds: 1),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0x0A000000),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                _subBtn(0, '歌单'),
                const SizedBox(width: 4),
                _subBtn(1, '链接'),
                const SizedBox(width: 4),
                _subBtn(2, '曲库'),
              ],
            ),
            const SizedBox(height: 8),
            if (_sub == 0) _buildPlaylistSub(),
            if (_sub == 1) _buildUrlSub(),
            if (_sub == 2) _buildLibrarySub(),
          ],
        ),
      ),
    );
  }

  Widget _subBtn(int i, String label) {
    final active = _sub == i;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _sub = i),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 6),
          decoration: BoxDecoration(
            color: active ? const Color(0xFFE85A2A) : Colors.transparent,
            borderRadius: BorderRadius.circular(4),
            border: Border.all(
              color: active ? const Color(0xFFE85A2A) : const Color(0x18000000),
            ),
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: active ? Colors.black : const Color(0xFF555555),
            ),
          ),
        ),
      ),
    );
  }

  // ---- Playlist sub UI ----
  Widget _buildPlaylistSub() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          '选择歌单或曲库全部歌曲。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 6),
        DropdownButton<int>(
          isExpanded: true,
          value: _pid,
          hint: const Text('— 选择歌单 —'),
          items: [
            DropdownMenuItem(
              value: -1,
              child: Text('曲库（全部 ${widget.library.length} 首）'),
            ),
            ...widget.playlists.map(
              (p) => DropdownMenuItem(
                value: p.id,
                child: Text(
                  '${p.name}（${p.songCount}）',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ),
          ],
          onChanged: (v) {
            setState(() => _pid = v);
            _loadDetail();
          },
        ),
        if (_msg != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              _msg!,
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ),
        if (_loading) const LinearProgressIndicator(minHeight: 2),
        if (_matched.isNotEmpty) ...[
          const SizedBox(height: 6),
          Row(
            children: [
              TextButton(
                onPressed:
                    () => setState(() {
                      _sel
                        ..clear()
                        ..addAll(_matched.map((s) => s.id));
                    }),
                child: const Text('全选'),
              ),
              TextButton(
                onPressed: () => setState(() => _sel.clear()),
                child: const Text('全不选'),
              ),
              const Spacer(),
              ElevatedButton(
                onPressed: _sel.isEmpty ? null : _commitPlaylist,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFE85A2A),
                  foregroundColor: Colors.black,
                ),
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
                  title: Text(
                    s.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12),
                  ),
                  subtitle: Text(
                    '${s.artist} · ${s.bpm?.toStringAsFixed(0) ?? '-'} BPM · ${(s.duration / 60).toStringAsFixed(1)}m',
                    style: const TextStyle(fontSize: 10),
                  ),
                  onChanged:
                      (v) => setState(() {
                        if (v == true)
                          _sel.add(s.id);
                        else
                          _sel.remove(s.id);
                      }),
                );
              },
            ),
          ),
        ],
      ],
    );
  }

  // ---- URL import sub UI ----
  Widget _buildUrlSub() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          '粘贴 QQ 音乐 / 网易云音乐 歌单链接，解析后批量导入到曲库。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _urlCtrl,
                style: const TextStyle(fontSize: 12),
                decoration: const InputDecoration(
                  hintText: '粘贴歌单链接…',
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 8,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 6),
            ElevatedButton(
              onPressed: _urlLoading ? null : _parseUrl,
              child: Text(_urlLoading ? '解析中' : '解析'),
            ),
          ],
        ),
        if (_urlMsg != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              _urlMsg!,
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ),
        if (_urlTracks.isNotEmpty) ...[
          const SizedBox(height: 6),
          Row(
            children: [
              TextButton(
                onPressed:
                    () => setState(() {
                      _urlSel
                        ..clear()
                        ..addAll(List.generate(_urlTracks.length, (i) => i));
                    }),
                child: const Text('全选'),
              ),
              TextButton(
                onPressed: () => setState(() => _urlSel.clear()),
                child: const Text('全不选'),
              ),
              const Spacer(),
              ElevatedButton(
                onPressed:
                    _urlDownloading || _urlSel.isEmpty
                        ? null
                        : _downloadUrlTracks,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFE85A2A),
                  foregroundColor: Colors.black,
                ),
                child: Text(
                  _urlDownloading ? '导入中…' : '导入 ${_urlSel.length} 首',
                ),
              ),
            ],
          ),
          if (_urlDownloadMsg != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                _urlDownloadMsg!,
                style: const TextStyle(fontSize: 11, color: Colors.grey),
              ),
            ),
          SizedBox(
            height: 220,
            child: ListView.builder(
              itemCount: _urlTracks.length,
              itemBuilder: (_, i) {
                final t = _urlTracks[i];
                final on = _urlSel.contains(i);
                return CheckboxListTile(
                  dense: true,
                  value: on,
                  title: Text(
                    t.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12),
                  ),
                  subtitle: Text(
                    t.artist,
                    style: const TextStyle(fontSize: 10),
                  ),
                  onChanged:
                      (v) => setState(() {
                        if (v == true)
                          _urlSel.add(i);
                        else
                          _urlSel.remove(i);
                      }),
                );
              },
            ),
          ),
        ],
      ],
    );
  }

  // ---- Library browse sub UI ----
  Widget _buildLibrarySub() {
    final q = _libQuery.toLowerCase();
    final filtered =
        q.isEmpty
            ? widget.library
            : widget.library
                .where(
                  (s) =>
                      s.title.toLowerCase().contains(q) ||
                      s.artist.toLowerCase().contains(q),
                )
                .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          '从曲库直接选歌加入 DJ 池。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 6),
        TextField(
          style: const TextStyle(fontSize: 12),
          decoration: const InputDecoration(
            hintText: '搜索曲库…',
            isDense: true,
            prefixIcon: Icon(Icons.search, size: 16),
            contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          ),
          onChanged: (v) => setState(() => _libQuery = v),
        ),
        const SizedBox(height: 4),
        Text(
          '${filtered.length} 首可选',
          style: const TextStyle(fontSize: 10, color: Colors.grey),
        ),
        SizedBox(
          height: 300,
          child: ListView.builder(
            itemCount: filtered.length,
            itemBuilder: (_, i) {
              final s = filtered[i];
              return ListTile(
                dense: true,
                title: Text(
                  s.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 12),
                ),
                subtitle: Text(
                  '${s.artist} · ${s.bpm?.toStringAsFixed(0) ?? '-'} BPM · ${(s.duration / 60).toStringAsFixed(1)}m',
                  style: const TextStyle(fontSize: 10),
                ),
                trailing: IconButton(
                  icon: const Icon(Icons.add_circle_outline, size: 20),
                  onPressed: () => _commitLibrary([s]),
                ),
                onTap: () => _commitLibrary([s]),
              );
            },
          ),
        ),
      ],
    );
  }
}

// ---- Vibe Source: server-side description → ranked songs ---- //
class _VibeSource extends StatefulWidget {
  const _VibeSource({
    required this.api,
    required this.token,
    required this.userId,
    required this.library,
    required this.onAdd,
  });
  final HarBeatApiClient api;
  final String token;
  final int userId;
  final List<LibrarySong> library;
  final void Function(Iterable<LibrarySong>) onAdd;

  @override
  State<_VibeSource> createState() => _VibeSourceState();
}

class _VibeSourceState extends State<_VibeSource> {
  final _ctrl = TextEditingController();
  final Set<String> _sel = {};
  bool _loading = false;
  String? _error;
  VibeSearchResult? _result;

  Future<void> _search() async {
    final q = _ctrl.text.trim();
    if (q.isEmpty) {
      setState(() => _error = '请输入描述，例如：深夜地下 boom bap 95bpm');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _result = null;
      _sel.clear();
    });
    try {
      // 复用导入歌单页的 vibe 链路：CLAP(本地曲库) + Spotify(公网) 双路召回
      final res = await widget.api.vibeSearch(
        token: widget.token,
        userId: widget.userId,
        query: q,
        topK: 24,
      );
      setState(() {
        _result = res;
        // 默认勾选所有已在曲库里的命中（DJ 池子里能直接加的就这些）
        for (final s in res.songs) {
          if (s.source == 'local' && s.songId != null) {
            _sel.add(s.songId.toString());
          }
        }
      });
    } catch (e) {
      setState(() => _error = 'Vibe 搜索失败: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hits = _result?.songs ?? const <VibeSong>[];
    // VibeSong.songId 是 int (Jetson catalog Song.id)，需要回查 LibrarySong.songId 一致的项
    final byCatalogId = <int, LibrarySong>{};
    for (final s in widget.library) {
      if (s.songId != null) byCatalogId[s.songId!] = s;
    }
    return Card(
      color: const Color(0x0A000000),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              '一句话描述「我想要的氛围」。后端用 CLAP 跨模态检索本地曲库 + Spotify 公网召回。',
              style: TextStyle(fontSize: 11, color: Colors.grey),
            ),
            const SizedBox(height: 6),
            TextField(
              controller: _ctrl,
              decoration: const InputDecoration(
                isDense: true,
                hintText: '例如：深夜地下 boom bap 95bpm dark',
                border: OutlineInputBorder(),
              ),
              onSubmitted: (_) => _search(),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                ElevatedButton(
                  onPressed: _loading ? null : _search,
                  child: Text(_loading ? '搜索中…(15-25s)' : '🔍 搜索'),
                ),
                const Spacer(),
                Text('已选 ${_sel.length}', style: const TextStyle(fontSize: 11)),
                const SizedBox(width: 4),
                ElevatedButton(
                  onPressed:
                      _sel.isEmpty
                          ? null
                          : () {
                            final picks =
                                _sel
                                    .map(
                                      (id) =>
                                          byCatalogId[int.tryParse(id) ?? -1],
                                    )
                                    .whereType<LibrarySong>();
                            widget.onAdd(picks);
                            if (mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text('加入 ${picks.length} 首'),
                                  duration: const Duration(seconds: 1),
                                ),
                              );
                            }
                          },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFFE85A2A),
                    foregroundColor: Colors.black,
                  ),
                  child: Text('加入 ${_sel.length}'),
                ),
              ],
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  _error!,
                  style: const TextStyle(color: Colors.redAccent, fontSize: 11),
                ),
              ),
            if (_result != null) ...[
              const SizedBox(height: 6),
              if (_result!.vibeDescription.isNotEmpty)
                Text(
                  '🎭 解读: ${_result!.vibeDescription}',
                  style: const TextStyle(fontSize: 10, color: Colors.grey),
                ),
              if (_result!.genres.isNotEmpty)
                Text(
                  'genres: ${_result!.genres.join(", ")}',
                  style: const TextStyle(fontSize: 10, color: Colors.grey),
                ),
            ],
            if (hits.isNotEmpty)
              SizedBox(
                height: 280,
                child: ListView.builder(
                  itemCount: hits.length,
                  itemBuilder: (_, i) {
                    final m = hits[i];
                    final inLibViaCatalog =
                        m.songId != null && byCatalogId.containsKey(m.songId);
                    final selectable = m.source == 'local' && inLibViaCatalog;
                    final id = m.songId?.toString() ?? '';
                    final on = selectable && _sel.contains(id);
                    final pct = m.matchPercentage.round();
                    final tag =
                        m.source == 'local'
                            ? (selectable ? '本地' : '本地·未入库')
                            : 'Spotify';
                    final tagColor =
                        selectable
                            ? Colors.greenAccent
                            : (m.source == 'local'
                                ? Colors.orange
                                : Colors.grey);
                    return CheckboxListTile(
                      dense: true,
                      value: on,
                      onChanged:
                          !selectable
                              ? null
                              : (v) => setState(() {
                                if (v == true) {
                                  _sel.add(id);
                                } else {
                                  _sel.remove(id);
                                }
                              }),
                      title: Text(
                        m.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12),
                      ),
                      subtitle: Text(
                        '${m.artist} · ${m.style ?? '-'} · 匹配 $pct%',
                        style: const TextStyle(fontSize: 10),
                      ),
                      secondary: Text(
                        tag,
                        style: TextStyle(fontSize: 10, color: tagColor),
                      ),
                    );
                  },
                ),
              ),
            if (hits.any((s) => s.source == 'spotify'))
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text(
                  '提示：Spotify 候选需先到「歌单 → 导入歌单 → Vibe」导入到曲库才能加入 DJ 池。',
                  style: TextStyle(fontSize: 10, color: Colors.grey),
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
  const _StyleSource({
    required this.api,
    required this.token,
    required this.library,
    required this.onAdd,
  });
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
    widget.api
        .djListStyles(token: widget.token)
        .then((s) {
          if (!mounted) return;
          setState(() {
            _styles = s;
            if (s.isNotEmpty) _style = s.first['key'] as String;
          });
        })
        .catchError((e) {
          if (mounted) setState(() => _error = e.toString());
        });
  }

  Future<void> _run() async {
    if (_style == null) return;
    setState(() {
      _loading = true;
      _error = null;
      _result = const [];
    });
    try {
      final r = await widget.api.djPickByStyle(
        token: widget.token,
        style: _style!,
        targetDurationSec: _minutes * 60,
      );
      setState(
        () => _result = (r['songs'] as List).cast<Map<String, dynamic>>(),
      );
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0x0A000000),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              '按舞种 + 目标时长自动出歌（BPM/Phrase/Energy 匹配）。',
              style: TextStyle(fontSize: 11, color: Colors.grey),
            ),
            DropdownButton<String>(
              isExpanded: true,
              value: _style,
              hint: const Text('选择舞种'),
              items:
                  _styles.map((s) {
                    final r = (s['bpm_range'] as List).cast<num>();
                    return DropdownMenuItem<String>(
                      value: s['key'] as String,
                      child: Text(
                        '${s['label_zh']} (${r[0].toInt()}–${r[1].toInt()} BPM)',
                      ),
                    );
                  }).toList(),
              onChanged: (v) => setState(() => _style = v),
            ),
            Row(
              children: [
                const Text('目标时长', style: TextStyle(fontSize: 11)),
                Expanded(
                  child: Slider(
                    value: _minutes,
                    min: 1,
                    max: 60,
                    divisions: 59,
                    label: '${_minutes.toInt()} 分',
                    onChanged: (v) => setState(() => _minutes = v),
                  ),
                ),
                Text(
                  '${_minutes.toInt()} 分',
                  style: const TextStyle(fontSize: 11),
                ),
              ],
            ),
            Row(
              children: [
                ElevatedButton(
                  onPressed: _loading || _style == null ? null : _run,
                  child: Text(_loading ? '生成中...' : '生成候选'),
                ),
                const SizedBox(width: 6),
                if (_result.isNotEmpty)
                  ElevatedButton(
                    onPressed: () {
                      final ids =
                          _result.map((e) => e['song_id'].toString()).toSet();
                      final byId = {for (final s in widget.library) s.id: s};
                      final picks =
                          ids.map((id) => byId[id]).whereType<LibrarySong>();
                      widget.onAdd(picks);
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFFE85A2A),
                      foregroundColor: Colors.black,
                    ),
                    child: Text('全部加入 (${_result.length})'),
                  ),
              ],
            ),
            if (_error != null)
              Text(
                _error!,
                style: const TextStyle(color: Colors.red, fontSize: 11),
              ),
            if (_result.isNotEmpty)
              SizedBox(
                height: 220,
                child: ListView(
                  children:
                      _result.asMap().entries.map((entry) {
                        final i = entry.key, s = entry.value;
                        final score =
                            ((s['score'] as num).toDouble() * 100).toInt();
                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 3),
                          child: Row(
                            children: [
                              SizedBox(
                                width: 24,
                                child: Text(
                                  '#${i + 1}',
                                  style: const TextStyle(
                                    fontSize: 10,
                                    color: Colors.grey,
                                  ),
                                ),
                              ),
                              Expanded(
                                child: Text(
                                  '${s['title']} · ${s['artist']}',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(fontSize: 12),
                                ),
                              ),
                              Text(
                                '${(s['bpm'] as num?)?.toStringAsFixed(0) ?? '-'}BPM ·$score',
                                style: const TextStyle(
                                  fontSize: 10,
                                  color: Colors.grey,
                                ),
                              ),
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
    required this.presets,
    required this.selected,
    required this.loading,
    required this.error,
    required this.picked,
    required this.sequence,
    required this.buckets,
    required this.songEnergy,
    required this.energyLoading,
    required this.onPickPreset,
    required this.onRun,
    required this.autoSets,
    required this.selectedSetIdx,
    required this.autoSetsLoading,
    required this.autoSetsError,
    required this.onRunAutoSets,
    required this.onPickSet,
  });
  final List<Map<String, dynamic>> presets;
  final String selected;
  final bool loading;
  final String? error;
  final List<LibrarySong> picked;
  final List<Map<String, dynamic>> sequence;
  final List<Map<String, dynamic>> buckets;
  final Map<String, Map<String, dynamic>> songEnergy;
  final bool energyLoading;
  final ValueChanged<String> onPickPreset;
  final VoidCallback onRun;

  // Auto DJ-Set props (new pipeline)
  final List<Map<String, dynamic>> autoSets;
  final int selectedSetIdx;
  final bool autoSetsLoading;
  final String? autoSetsError;
  final VoidCallback onRunAutoSets;
  final ValueChanged<int> onPickSet;

  String _sceneIcon(String scene) =>
      {
        'battle': '🥊',
        'cypher': '🌀',
        'class': '🎓',
        'showcase': '🎬',
      }[scene] ??
      '🎵';

  /// 把 v2 后端返回的 hex 颜色字符串（如 "#F59E0B"）转成 Flutter Color。
  Color _parseHex(String? hex, {Color fallback = const Color(0xFFE85A2A)}) {
    if (hex == null || hex.isEmpty) return fallback;
    final clean = hex.startsWith('#') ? hex.substring(1) : hex;
    final v = int.tryParse(clean, radix: 16);
    if (v == null) return fallback;
    if (clean.length == 6) return Color(0xFF000000 | v);
    if (clean.length == 8) return Color(v);
    return fallback;
  }

  @override
  Widget build(BuildContext context) {
    final byId = {for (final s in picked) s.id: s};
    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        // ── 能量曲线排序（主路径） ───────────────────────────────────────
        _buildLegacyPresetSection(byId),
        const SizedBox(height: 14),
        // ── 高级：候选 Set 编排 ───────────────────────────────────────
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text(
            '高级：自动生成候选 Set',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: Colors.grey,
            ),
          ),
          children: [_buildAutoSetsSection(byId)],
        ),
      ],
    );
  }

  Widget _buildAutoSetsSection(Map<String, LibrarySong> byId) {
    final hasResults = autoSets.isNotEmpty;
    final btnLabel =
        autoSetsLoading
            ? '生成候选 Set 中…'
            : (hasResults ? '重新生成候选 Set' : '生成候选 Set（${picked.length} 首）');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          '系统按角色、能量曲线和衔接风险产出多个候选 set。适合需要完整 DJ 编排时使用。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed:
                    autoSetsLoading || picked.length < 2 ? null : onRunAutoSets,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFE85A2A),
                  foregroundColor: Colors.black,
                ),
                icon:
                    autoSetsLoading
                        ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(
                            strokeWidth: 1.6,
                            color: Colors.black,
                          ),
                        )
                        : const Icon(Icons.alt_route, size: 16),
                label: Text(
                  btnLabel,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
          ],
        ),
        if (autoSetsError != null)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(
              autoSetsError!,
              style: const TextStyle(color: Colors.red, fontSize: 11),
            ),
          ),
        if (hasResults) ...[
          const SizedBox(height: 10),
          SizedBox(
            height: 168,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: autoSets.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (ctx, i) => _buildSetCard(ctx, i, byId),
            ),
          ),
          const SizedBox(height: 10),
          if (selectedSetIdx >= 0 && selectedSetIdx < autoSets.length)
            _buildSelectedSetDetail(autoSets[selectedSetIdx], byId),
        ],
      ],
    );
  }

  Widget _buildSetCard(
    BuildContext ctx,
    int idx,
    Map<String, LibrarySong> byId,
  ) {
    final s = autoSets[idx];
    final active = idx == selectedSetIdx;
    final tpl = (s['template'] as String? ?? '');
    final score =
        ((s['adjusted_score'] as num?) ?? (s['score'] as num? ?? 0)).toDouble();
    final tracks = (s['tracks'] as List<dynamic>? ?? const []).length;
    final trans = (s['transitions'] as List<dynamic>? ?? const []);
    final risks =
        trans.map((t) => (t as Map)['risk_level']?.toString() ?? '?').toList();
    final hasD = risks.contains('D');
    final hasC = risks.contains('C');
    final tplLabel =
        const {
          'smooth': '🌊 稳态 groove',
          'build': '🔥 渐进爆发',
          'cypher_wave': '🌀 波浪 cypher',
          'battle_peak': '🥊 高能 battle',
          'clean_vocal': '🎙️ 人声主导',
        }[tpl] ??
        tpl;
    return GestureDetector(
      onTap: () => onPickSet(idx),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        width: 200,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: active ? const Color(0xFFE85A2A) : const Color(0x14000000),
          border: Border.all(
            color: active ? const Color(0xFFE85A2A) : const Color(0x22000000),
            width: 1.4,
          ),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              tplLabel,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.bold,
                color: active ? Colors.black : Colors.white,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '$tracks 首 · 评分 ${(score * 100).round()}',
              style: TextStyle(
                fontSize: 11,
                color: active ? Colors.black87 : Colors.grey,
              ),
            ),
            const SizedBox(height: 6),
            // mini energy curve sparkline
            SizedBox(
              height: 36,
              child: CustomPaint(
                size: const Size(double.infinity, 36),
                painter: _CurvePainter(
                  curve:
                      ((s['energy_curve'] as List<dynamic>? ?? const []))
                          .map((e) => (e as num).toDouble())
                          .toList(),
                  color: active ? Colors.black : const Color(0xFFE85A2A),
                ),
              ),
            ),
            const Spacer(),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              children: [
                _riskChip('A', risks.where((r) => r == 'A').length, active),
                _riskChip('B', risks.where((r) => r == 'B').length, active),
                if (hasC)
                  _riskChip('C', risks.where((r) => r == 'C').length, active),
                if (hasD)
                  _riskChip('D', risks.where((r) => r == 'D').length, active),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _riskChip(String level, int n, bool active) {
    if (n <= 0) return const SizedBox.shrink();
    final colors = const {
      'A': Color(0xFF22C55E),
      'B': Color(0xFF3B82F6),
      'C': Color(0xFFF59E0B),
      'D': Color(0xFFEF4444),
    };
    final c = colors[level] ?? Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(
        color: active ? c.withOpacity(0.85) : c.withOpacity(0.18),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Text(
        '$level×$n',
        style: TextStyle(
          fontSize: 10,
          color: active ? Colors.white : c,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  Map<String, dynamic>? _stringMap(Object? value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return null;
  }

  String _shortNum(Object? value, {int digits = 1}) {
    if (value is num) return value.toStringAsFixed(digits);
    return value?.toString() ?? '';
  }

  Widget _buildSelectedSetDetail(
    Map<String, dynamic> s,
    Map<String, LibrarySong> byId,
  ) {
    final tracks =
        (s['tracks'] as List<dynamic>? ?? const [])
            .map((e) => e.toString())
            .toList();
    final arc =
        (s['narrative_arc'] as List<dynamic>? ?? const [])
            .map((e) => e.toString())
            .toList();
    final transitions =
        (s['transitions'] as List<dynamic>? ?? const [])
            .map((e) => (e as Map).cast<String, dynamic>())
            .toList();
    final purposes =
        (s['purposes'] as List<dynamic>? ?? const [])
            .map((e) => (e as Map).cast<String, dynamic>())
            .toList();
    final plans =
        (s['plans'] as List<dynamic>? ?? const [])
            .map((e) => (e as Map).cast<String, dynamic>())
            .toList();
    final mixPlan = _stringMap(s['mix_plan']);
    final planId = s['plan_id']?.toString() ?? mixPlan?['plan_id']?.toString();
    final schema =
        s['schema_version']?.toString() ??
        mixPlan?['schema_version']?.toString();
    return Card(
      color: const Color(0x0A000000),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '已选 set — 顺序与每段衔接方案',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
            ),
            if (planId != null || schema != null)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(
                  [
                    if (schema != null) schema,
                    if (planId != null)
                      'plan:${planId.substring(0, math.min(8, planId.length))}',
                  ].join(' · '),
                  style: const TextStyle(fontSize: 9, color: Colors.grey),
                ),
              ),
            const SizedBox(height: 6),
            for (var i = 0; i < tracks.length; i++) ...[
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Container(
                    width: 22,
                    height: 22,
                    decoration: BoxDecoration(
                      color: const Color(0xFFE85A2A),
                      borderRadius: BorderRadius.circular(11),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      '${i + 1}',
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: Colors.black,
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          byId[tracks[i]]?.title ?? tracks[i],
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        if (i < arc.length)
                          Text(
                            arc[i],
                            style: const TextStyle(
                              fontSize: 10,
                              color: Colors.grey,
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
              if (i < transitions.length)
                Padding(
                  padding: const EdgeInsets.symmetric(
                    vertical: 4,
                    horizontal: 28,
                  ),
                  child: _buildTransitionRow(
                    transitions[i],
                    i < purposes.length ? purposes[i] : null,
                    i < plans.length ? plans[i] : null,
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildTransitionRow(
    Map<String, dynamic> edge,
    Map<String, dynamic>? purpose,
    Map<String, dynamic>? plan,
  ) {
    final risk = edge['risk_level']?.toString() ?? '?';
    final score = ((edge['score'] as num?) ?? 0).toDouble();
    final purposeText = purpose?['purpose']?.toString() ?? '';
    final rule = (plan?['rule'] ?? edge['best_rule'] ?? '').toString();
    final spec =
        plan?['spec'] is Map
            ? (plan!['spec'] as Map).cast<String, dynamic>()
            : const <String, dynamic>{};
    final dur = (spec['duration_sec'] as num?)?.toDouble();
    final ruleLabelZh = (spec['rule_label_zh'] ?? '').toString();
    final strategy = _stringMap(spec['transition_strategy']);
    final context = _stringMap(spec['transition_context']);
    final timeline = spec['timeline'];
    final strategyLabel =
        strategy?['label_zh']?.toString() ?? strategy?['key']?.toString();
    final detailBits = <String>[];
    if (strategyLabel != null && strategyLabel.isNotEmpty) {
      detailBits.add(strategyLabel);
    }
    final rkStyle =
        spec['rk_style']?.toString() ?? strategy?['rk_style']?.toString();
    if (rkStyle != null && rkStyle.isNotEmpty) {
      detailBits.add('RK:$rkStyle');
    }
    if (context != null) {
      final tempo = context['tempoRelation']?.toString();
      final bpmPct = _shortNum(context['bpmDiffRatio'], digits: 2);
      final keyDistance = _shortNum(context['keyDistance'], digits: 0);
      final genreDistance = _shortNum(context['genreDistance'], digits: 2);
      final vocalRisk = _shortNum(context['vocalConflictRisk'], digits: 2);
      final ctxText = [
        if (tempo != null && tempo.isNotEmpty) tempo,
        if (bpmPct.isNotEmpty) 'bpm:$bpmPct',
        if (keyDistance.isNotEmpty) 'key:$keyDistance',
        if (genreDistance.isNotEmpty) 'genre:$genreDistance',
        if (vocalRisk.isNotEmpty) 'vocal:$vocalRisk',
      ].join(' ');
      if (ctxText.isNotEmpty) detailBits.add(ctxText);
    }
    if (timeline is List && timeline.isNotEmpty) {
      detailBits.add('${timeline.length} timeline steps');
    }
    final detailText = detailBits.join(' · ');
    final riskColor =
        const {
          'A': Color(0xFF22C55E),
          'B': Color(0xFF3B82F6),
          'C': Color(0xFFF59E0B),
          'D': Color(0xFFEF4444),
        }[risk] ??
        Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      decoration: BoxDecoration(
        color: riskColor.withOpacity(0.06),
        border: Border(left: BorderSide(color: riskColor, width: 2)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
            decoration: BoxDecoration(
              color: riskColor,
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              risk,
              style: const TextStyle(
                fontSize: 10,
                color: Colors.white,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${ruleLabelZh.isNotEmpty ? ruleLabelZh : rule}'
                  '${purposeText.isNotEmpty ? " · $purposeText" : ""}'
                  '${dur != null ? " · ${dur.toStringAsFixed(1)}s" : ""}'
                  ' · ${(score * 100).round()}/100',
                  style: const TextStyle(fontSize: 10),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                if (detailText.isNotEmpty)
                  Text(
                    detailText,
                    style: const TextStyle(fontSize: 9, color: Colors.grey),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLegacyPresetSection(Map<String, LibrarySong> byId) {
    return Column(
      children: [
        const Text(
          '按街舞场景能量曲线贪心分配每一首歌位置；每行能量条按 v2 五档桶着色。混音方案仍走 7+11。',
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
          children:
              presets.map((p) {
                final active = p['key'] == selected;
                return GestureDetector(
                  onTap: () => onPickPreset(p['key'] as String),
                  child: Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      color:
                          active
                              ? const Color(0xFFE85A2A)
                              : const Color(0x0A000000),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${_sceneIcon(p['scene'] as String? ?? 'generic')} ${p['label_zh']}',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                            color: active ? Colors.black : Colors.white,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Expanded(
                          child: Text(
                            p['desc_zh'] as String? ?? '',
                            style: TextStyle(
                              fontSize: 9,
                              color: active ? Colors.black87 : Colors.grey,
                            ),
                            maxLines: 3,
                            overflow: TextOverflow.ellipsis,
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
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFE85A2A),
                foregroundColor: Colors.black,
              ),
              child: Text(loading ? '排序中...' : '按曲线排序 ${picked.length} 首'),
            ),
            if (energyLoading) ...[
              const SizedBox(width: 8),
              const SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(
                  strokeWidth: 1.6,
                  color: const Color(0xFFE85A2A),
                ),
              ),
              const SizedBox(width: 4),
              const Text(
                '能量分析中…',
                style: TextStyle(fontSize: 10, color: Colors.grey),
              ),
            ],
          ],
        ),
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text(
              error!,
              style: const TextStyle(color: Colors.red, fontSize: 11),
            ),
          ),
        if (buckets.isNotEmpty && sequence.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Wrap(
              spacing: 6,
              runSpacing: 4,
              children:
                  buckets.map((b) {
                    final c = _parseHex(b['color'] as String?);
                    return Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 6,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: c.withValues(alpha: 0.18),
                        border: Border.all(color: c, width: 0.8),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        '${b['label_zh'] ?? b['key']}',
                        style: TextStyle(fontSize: 10, color: c),
                      ),
                    );
                  }).toList(),
            ),
          ),
        if (sequence.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Card(
              color: const Color(0x0A000000),
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      '排序结果 — 目标曲线 vs 实际能量',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 4),
                    ...sequence.map((entry) {
                      final id = entry['song_id'].toString();
                      final song = byId[id];
                      final act =
                          ((entry['actual_energy'] as num).toDouble() * 100)
                              .round();
                      final tgt =
                          ((entry['target_energy'] as num).toDouble() * 100)
                              .round();
                      final v2 = songEnergy[id] ?? const <String, dynamic>{};
                      final hasV2 = v2.isNotEmpty;
                      final v2Total =
                          ((v2['total'] as num?)?.toDouble() ?? 0.0);
                      final v2Pct = (v2Total * 100).round();
                      final bucket = (v2['bucket'] as String? ?? 'cold');
                      final bucketLabel =
                          (v2['bucket_label_zh'] as String? ?? '');
                      final bucketColor = _parseHex(
                        v2['bucket_color'] as String?,
                        fallback: const Color(0xFFE85A2A),
                      );
                      final bpm = ((v2['bpm'] as num?)?.toDouble() ?? 0.0);
                      final styleUsed = (v2['style_used'] as String? ?? '');
                      final explain = (v2['explain_zh'] as String? ?? '');
                      final factors =
                          (v2['factors'] is Map)
                              ? (v2['factors'] as Map).cast<String, dynamic>()
                              : const <String, dynamic>{};
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 6,
                                  height: 22,
                                  decoration: BoxDecoration(
                                    color: bucketColor,
                                    borderRadius: BorderRadius.circular(2),
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Expanded(
                                  child: Text(
                                    '#${(entry['position'] as int) + 1} ${song?.title ?? id}',
                                    style: const TextStyle(fontSize: 11),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                if (hasV2)
                                  Container(
                                    margin: const EdgeInsets.only(left: 4),
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 5,
                                      vertical: 1,
                                    ),
                                    decoration: BoxDecoration(
                                      color: bucketColor.withValues(
                                        alpha: 0.22,
                                      ),
                                      border: Border.all(
                                        color: bucketColor,
                                        width: 0.7,
                                      ),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: Text(
                                      bucketLabel.isNotEmpty
                                          ? bucketLabel
                                          : bucket,
                                      style: TextStyle(
                                        fontSize: 9,
                                        color: bucketColor,
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                            const SizedBox(height: 3),
                            Row(
                              children: [
                                Text(
                                  hasV2
                                      ? 'tgt $tgt · v1 $act · v2 $v2Pct  BPM ${bpm > 0 ? bpm.toStringAsFixed(0) : "—"}'
                                      : 'tgt $tgt · v1 $act  (v2 待加载)',
                                  style: const TextStyle(
                                    fontSize: 10,
                                    color: Colors.grey,
                                  ),
                                ),
                                if (styleUsed.isNotEmpty &&
                                    styleUsed != 'no_dj') ...[
                                  const SizedBox(width: 6),
                                  Text(
                                    '· $styleUsed',
                                    style: const TextStyle(
                                      fontSize: 10,
                                      color: Color(0x61000000),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                            const SizedBox(height: 3),
                            LayoutBuilder(
                              builder: (ctx, c) {
                                final w = c.maxWidth;
                                final fillW =
                                    (hasV2 ? v2Total : act / 100.0).clamp(
                                      0.0,
                                      1.0,
                                    ) *
                                    w;
                                final tgtX = (tgt / 100.0).clamp(0.0, 1.0) * w;
                                return SizedBox(
                                  height: 8,
                                  child: Stack(
                                    children: [
                                      Container(
                                        height: 6,
                                        color: Colors.black26,
                                      ),
                                      Container(
                                        height: 6,
                                        width: fillW,
                                        decoration: BoxDecoration(
                                          gradient: LinearGradient(
                                            colors: [
                                              bucketColor.withValues(
                                                alpha: 0.65,
                                              ),
                                              bucketColor,
                                            ],
                                          ),
                                          borderRadius: BorderRadius.circular(
                                            2,
                                          ),
                                        ),
                                      ),
                                      Positioned(
                                        left: (tgtX - 1).clamp(0.0, w - 2),
                                        child: Container(
                                          width: 2,
                                          height: 8,
                                          color: Color(0xFF1A1A1A),
                                        ),
                                      ),
                                    ],
                                  ),
                                );
                              },
                            ),
                            if (explain.isNotEmpty)
                              Padding(
                                padding: const EdgeInsets.only(top: 3),
                                child: Text(
                                  explain,
                                  style: const TextStyle(
                                    fontSize: 10,
                                    color: Color(0x99000000),
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            if (factors.isNotEmpty)
                              Padding(
                                padding: const EdgeInsets.only(top: 3),
                                child: _FactorRibbon(
                                  factors: factors,
                                  color: bucketColor,
                                ),
                              ),
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

/// 7 perceptual factors mini-bar — bass_punch / drum_drive / groove_intensity
/// / tempo_drive / attack_brightness / density_pulse / dynamic_thrust.
/// Renders as a horizontal strip of 7 short bars so the user can eyeball why
/// two songs at the same total energy "feel" different.
class _FactorRibbon extends StatelessWidget {
  const _FactorRibbon({required this.factors, required this.color});
  final Map<String, dynamic> factors;
  final Color color;

  static const List<({String key, String label})> _slots = [
    (key: 'bass_punch', label: '低'),
    (key: 'drum_drive', label: '鼓'),
    (key: 'groove_intensity', label: '切'),
    (key: 'tempo_drive', label: '速'),
    (key: 'attack_brightness', label: '亮'),
    (key: 'density_pulse', label: '密'),
    (key: 'dynamic_thrust', label: '冲'),
  ];

  double _v(String k) {
    final raw = factors[k];
    if (raw is num) return raw.toDouble().clamp(0.0, 1.0);
    return 0.0;
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children:
          _slots.map((s) {
            final v = _v(s.key);
            return Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 1),
                child: Column(
                  children: [
                    SizedBox(
                      height: 14,
                      child: Stack(
                        alignment: Alignment.bottomCenter,
                        children: [
                          Container(color: Colors.black26),
                          FractionallySizedBox(
                            heightFactor: v,
                            widthFactor: 1.0,
                            child: Container(color: color),
                          ),
                        ],
                      ),
                    ),
                    Text(
                      s.label,
                      style: const TextStyle(
                        fontSize: 8,
                        color: Color(0x8A000000),
                      ),
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
    );
  }
}

// =========================================================================== //
// Step 3 — 混音 (rules + bpm-diff hints + start live mix)
// =========================================================================== //
class _Step3Mix extends StatelessWidget {
  const _Step3Mix({
    required this.rules,
    required this.picked,
    required this.sequence,
    required this.canStart,
    required this.onStart,
  });
  final Map<String, dynamic>? rules;
  final List<LibrarySong> picked;
  final List<Map<String, dynamic>> sequence;
  final bool canStart;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    final byId = {for (final s in picked) s.id: s};
    final analyzed =
        ((rules?['analyzed'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
    final raw =
        ((rules?['raw'] as List?) ?? const []).cast<Map<String, dynamic>>();
    final crossStyle =
        ((rules?['cross_style'] as List?) ?? const [])
            .cast<Map<String, dynamic>>();
    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        const Text(
          '混音采用现有 7 原生 + 11 分析型方案，并在跨度大时自动启用跨风格过渡。点 ▶ 开始混音播放后即进入实时切歌 / 加花。',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
        const SizedBox(height: 8),
        Center(
          child: ElevatedButton.icon(
            onPressed: canStart ? onStart : null,
            icon: const Icon(Icons.play_arrow),
            label: Text(
              canStart ? '▶ 开始混音播放（${sequence.length} 首）' : '需要先在 Step 2 排序',
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFE85A2A),
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
              textStyle: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ),
        if (sequence.length >= 2) ...[
          const SizedBox(height: 10),
          Card(
            color: const Color(0x0A000000),
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '相邻过渡（${sequence.length - 1} 段）',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  ...List.generate(sequence.length - 1, (i) {
                    final a = byId[sequence[i]['song_id'].toString()];
                    final b = byId[sequence[i + 1]['song_id'].toString()];
                    final diff =
                        (a?.bpm != null && b?.bpm != null)
                            ? (a!.bpm! - b!.bpm!).abs()
                            : null;
                    final tag =
                        diff == null
                            ? '—'
                            : diff <= 3
                            ? '完美吻合'
                            : diff <= 8
                            ? '可拉伸混'
                            : diff <= 16
                            ? '建议加 FX 衔接'
                            : '建议硬切 / Rewind';
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Row(
                        children: [
                          SizedBox(
                            width: 38,
                            child: Text(
                              '#${i + 1}→#${i + 2}',
                              style: const TextStyle(
                                fontSize: 10,
                                color: Colors.grey,
                              ),
                            ),
                          ),
                          Expanded(
                            child: Text(
                              '${a?.title ?? '-'} → ${b?.title ?? '-'}',
                              style: const TextStyle(fontSize: 11),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          Text(
                            'Δ${diff?.toStringAsFixed(1) ?? '?'} · $tag',
                            style: const TextStyle(
                              fontSize: 10,
                              color: const Color(0xFFE85A2A),
                            ),
                          ),
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
          Text(
            '分析型过渡（${analyzed.length}）',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children:
                analyzed.map((r) => _ruleChip(r, Colors.deepPurple)).toList(),
          ),
          const SizedBox(height: 10),
          Text(
            '原生过渡（${raw.length}）',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: raw.map((r) => _ruleChip(r, Colors.indigo)).toList(),
          ),
          if (crossStyle.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              '跨风格过渡（${crossStyle.length}）',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children:
                  crossStyle.map((r) => _ruleChip(r, Colors.teal)).toList(),
            ),
          ],
        ],
      ],
    );
  }

  Widget _ruleChip(Map<String, dynamic> r, Color base) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
    decoration: BoxDecoration(
      color: base.withOpacity(0.25),
      borderRadius: BorderRadius.circular(5),
    ),
    child: Text(
      r['label_zh']?.toString() ?? '',
      style: const TextStyle(fontSize: 11),
    ),
  );
}

// =========================================================================== //
// Step 4 — 实时操作（切歌 + 加花 FX，全部叠在 RK3588 播放之上）
// =========================================================================== //
class _Step4Live extends StatelessWidget {
  const _Step4Live({
    required this.ordered,
    required this.idx,
    required this.liveStarted,
    required this.fxItems,
    required this.onCut,
    required this.onPlayFx,
  });
  final List<LibrarySong> ordered;
  final int idx;
  final bool liveStarted;
  final List<Map<String, dynamic>> fxItems;
  final Future<void> Function(String strategy) onCut;
  final Future<void> Function(String key) onPlayFx;

  static const _groupOrder = ['hype', 'drop', 'drum'];
  static const _groupTitle = {
    'hype': '🚨 喊场',
    'drop': '💥 Drop',
    'drum': '🥁 节奏',
  };

  String _iconFor(String key) =>
      const {
        'air_horn': '📯',
        'bass_drop': '💣',
        'vinyl_stop': '🛑',
        'snare_crack': '🥁',
        'beat_juggle_stutter': '🎛️',
      }[key] ??
      '🔊';

  @override
  Widget build(BuildContext context) {
    if (!liveStarted) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: Text(
            '请先回到 Step 3 点 ▶ 开始混音播放',
            style: TextStyle(color: Colors.grey),
          ),
        ),
      );
    }
    final current = idx < ordered.length ? ordered[idx] : null;
    final next = idx + 1 < ordered.length ? ordered[idx + 1] : null;

    return ListView(
      padding: const EdgeInsets.all(10),
      children: [
        Card(
          color: const Color(0x0A000000),
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '当前 #${idx + 1} · ${current?.title ?? '-'}',
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  current?.artist ?? '',
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                ),
                const SizedBox(height: 6),
                Text(
                  '下一首：${next?.title ?? '— 队尾 —'}',
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Phase-2 节奏对齐：outro 出歌、跳过 intro、按 7+11 衔接、BPM 接近时拉速对拍。',
                  style: TextStyle(fontSize: 10, color: Color(0xFF2E7D32)),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 10),
        const Text(
          '✂️ 现场切歌',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
        ),
        const SizedBox(height: 4),
        _cutBtn(
          '⚡ 快切 fast_cut',
          '5 秒内寻找下一个 downbeat/beat，硬切到队列下一首。',
          'fast_cut',
        ),
        _cutBtn(
          '🔥 升能量切 energy_up_cut',
          '从已选池挑能量更高的歌替换后切。冲峰 / 喊大招用。',
          'energy_up_cut',
        ),
        _cutBtn(
          '❄️ 降能量切 energy_down_cut',
          '挑能量更低的歌，让 cypher 喘口气。',
          'energy_down_cut',
        ),
        const SizedBox(height: 14),
        const Text(
          '🎛️ 加花 FX Pad（数字键 1-5）',
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
        ),
        const SizedBox(height: 4),
        GridView.count(
          crossAxisCount: 5,
          mainAxisSpacing: 6,
          crossAxisSpacing: 6,
          childAspectRatio: 0.9,
          physics: const NeverScrollableScrollPhysics(),
          shrinkWrap: true,
          children:
              fxItems.asMap().entries.map((entry) {
                final i = entry.key;
                final fx = entry.value;
                final k = fx['key'] as String;
                final rkKey = fx['rk_key'] as int? ?? (i + 1);
                return GestureDetector(
                  onTap: () => onPlayFx(k),
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: const Color(0x0A000000),
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(
                        color: const Color(0xFFE85A2A).withOpacity(0.4),
                      ),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          '$rkKey',
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: const Color(0xFFE85A2A),
                          ),
                        ),
                        Text(_iconFor(k), style: const TextStyle(fontSize: 18)),
                        const SizedBox(height: 2),
                        Text(
                          fx['label_zh'] as String? ?? k,
                          style: const TextStyle(
                            fontSize: 9,
                            fontWeight: FontWeight.bold,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                );
              }).toList(),
        ),
      ],
    );
  }

  Widget _cutBtn(String title, String desc, String strategy) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: ElevatedButton(
        onPressed: () => onCut(strategy),
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0x0A000000),
          foregroundColor: Colors.white,
          alignment: Alignment.centerLeft,
          padding: const EdgeInsets.all(10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 2),
            Text(
              desc,
              style: const TextStyle(fontSize: 10, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}

/// Tiny sparkline painter for the auto-set card energy curve preview.
class _CurvePainter extends CustomPainter {
  _CurvePainter({required this.curve, required this.color});
  final List<double> curve;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (curve.length < 2) return;
    final fill =
        Paint()
          ..color = color.withOpacity(0.18)
          ..style = PaintingStyle.fill;
    final stroke =
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.6;
    final path = Path();
    final fillPath = Path();
    final n = curve.length;
    for (var i = 0; i < n; i++) {
      final x = (i / (n - 1)) * size.width;
      final y = size.height - curve[i].clamp(0.0, 1.0) * size.height;
      if (i == 0) {
        path.moveTo(x, y);
        fillPath.moveTo(x, size.height);
        fillPath.lineTo(x, y);
      } else {
        path.lineTo(x, y);
        fillPath.lineTo(x, y);
      }
    }
    fillPath.lineTo(size.width, size.height);
    fillPath.close();
    canvas.drawPath(fillPath, fill);
    canvas.drawPath(path, stroke);
  }

  @override
  bool shouldRepaint(covariant _CurvePainter old) =>
      old.curve != curve || old.color != color;
}
