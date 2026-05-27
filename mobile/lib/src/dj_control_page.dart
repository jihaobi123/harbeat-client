import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import 'api_client.dart';
import 'models.dart';

/// DJ Control 模块入口：5 个子页（舞种推荐 / 能量编排 / 混音规则 / 现场切歌 / 加花）。
class DjControlPage extends StatefulWidget {
  const DjControlPage({
    super.key,
    required this.apiClient,
    required this.token,
    required this.librarySongs,
  });

  final HarBeatApiClient apiClient;
  final String token;
  final List<LibrarySong> librarySongs;

  @override
  State<DjControlPage> createState() => _DjControlPageState();
}

class _DjControlPageState extends State<DjControlPage> with SingleTickerProviderStateMixin {
  late final TabController _tab;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 5, vsync: this);
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Material(
          color: Theme.of(context).colorScheme.surface,
          child: TabBar(
            controller: _tab,
            isScrollable: true,
            tabs: const [
              Tab(icon: Icon(Icons.local_fire_department), text: '舞种'),
              Tab(icon: Icon(Icons.trending_up), text: '能量'),
              Tab(icon: Icon(Icons.tune), text: '过渡'),
              Tab(icon: Icon(Icons.content_cut), text: '切歌'),
              Tab(icon: Icon(Icons.graphic_eq), text: 'FX'),
            ],
          ),
        ),
        Expanded(
          child: TabBarView(
            controller: _tab,
            children: [
              _PickByStyleTab(api: widget.apiClient, token: widget.token),
              _SequenceTab(api: widget.apiClient, token: widget.token, songs: widget.librarySongs),
              _TransitionRulesTab(api: widget.apiClient, token: widget.token),
              const _CutStrategiesTab(),
              _FxPadTab(api: widget.apiClient, token: widget.token),
            ],
          ),
        ),
      ],
    );
  }
}

// --------------------------------------------------------------------------- //
// Tab 1: 舞种推荐
// --------------------------------------------------------------------------- //
class _PickByStyleTab extends StatefulWidget {
  const _PickByStyleTab({required this.api, required this.token});
  final HarBeatApiClient api;
  final String token;

  @override
  State<_PickByStyleTab> createState() => _PickByStyleTabState();
}

class _PickByStyleTabState extends State<_PickByStyleTab> {
  List<Map<String, dynamic>> _styles = const [];
  String? _selectedStyle;
  double _minutes = 5;
  bool _loading = false;
  String? _error;
  Map<String, dynamic>? _result;

  @override
  void initState() {
    super.initState();
    _loadStyles();
  }

  Future<void> _loadStyles() async {
    try {
      final s = await widget.api.djListStyles(token: widget.token);
      if (!mounted) return;
      setState(() {
        _styles = s;
        _selectedStyle = s.isNotEmpty ? s.first['key'] as String : null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  Future<void> _run() async {
    if (_selectedStyle == null) return;
    setState(() { _loading = true; _error = null; _result = null; });
    try {
      final r = await widget.api.djPickByStyle(
        token: widget.token,
        style: _selectedStyle!,
        targetDurationSec: _minutes * 60,
      );
      setState(() => _result = r);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            '基于已分析特征（BPM / Beat / Downbeat / 能量 / Phrase）评分，按 BPM 桶分散避免雷同。',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
          const SizedBox(height: 12),
          DropdownButton<String>(
            isExpanded: true,
            value: _selectedStyle,
            hint: const Text('选择舞种'),
            items: _styles.map((s) {
              final r = (s['bpm_range'] as List).cast<num>();
              return DropdownMenuItem<String>(
                value: s['key'] as String,
                child: Text('${s['label_zh']} (${r[0].toInt()}–${r[1].toInt()} BPM)'),
              );
            }).toList(),
            onChanged: (v) => setState(() => _selectedStyle = v),
          ),
          Row(
            children: [
              const Text('时长'),
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
              Text('${_minutes.toInt()} 分'),
            ],
          ),
          ElevatedButton(
            onPressed: _loading || _selectedStyle == null ? null : _run,
            child: Text(_loading ? '推荐中...' : '生成歌单'),
          ),
          if (_error != null) Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text('错误：$_error', style: const TextStyle(color: Colors.red)),
          ),
          if (_result != null) ...[
            const SizedBox(height: 12),
            Text('命中 ${(_result!['songs'] as List).length} 首 · 累计 ${_fmt((_result!['achieved_duration_sec'] as num).toDouble())}'),
            const Divider(),
            ...((_result!['songs'] as List).cast<Map<String, dynamic>>()).asMap().entries.map((entry) {
              final i = entry.key, s = entry.value;
              final score = ((s['score'] as num).toDouble() * 100).toInt();
              return ListTile(
                dense: true,
                leading: CircleAvatar(radius: 14, child: Text('${i + 1}', style: const TextStyle(fontSize: 12))),
                title: Text(s['title']?.toString() ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
                subtitle: Text(s['artist']?.toString() ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
                trailing: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('BPM ${(s['bpm'] as num?)?.toStringAsFixed(0) ?? '-'}', style: const TextStyle(fontSize: 11)),
                    Text('评分 $score', style: const TextStyle(fontSize: 11)),
                  ],
                ),
              );
            }),
          ],
        ],
      ),
    );
  }
}

// --------------------------------------------------------------------------- //
// Tab 2: 能量编排
// --------------------------------------------------------------------------- //
class _SequenceTab extends StatefulWidget {
  const _SequenceTab({required this.api, required this.token, required this.songs});
  final HarBeatApiClient api;
  final String token;
  final List<LibrarySong> songs;

  @override
  State<_SequenceTab> createState() => _SequenceTabState();
}

class _SequenceTabState extends State<_SequenceTab> {
  List<String> _presets = const [];
  String? _preset;
  final Set<String> _selectedIds = {};
  bool _loading = false;
  String? _error;
  List<Map<String, dynamic>> _sequence = const [];

  @override
  void initState() {
    super.initState();
    widget.api.djSequencePresets(token: widget.token).then((p) {
      if (!mounted) return;
      setState(() {
        _presets = p;
        _preset = p.isNotEmpty ? p.first : null;
      });
    }).catchError((e) {
      if (mounted) setState(() => _error = e.toString());
    });
  }

  Future<void> _run() async {
    if (_selectedIds.length < 2 || _preset == null) {
      setState(() => _error = '至少选 2 首');
      return;
    }
    setState(() { _loading = true; _error = null; _sequence = const []; });
    try {
      final s = await widget.api.djSequence(
        token: widget.token,
        songIds: _selectedIds.toList(),
        preset: _preset!,
      );
      setState(() => _sequence = s);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _labelPreset(String p) => const {
    'warmup_to_peak': '暖场上升',
    'wave': '波浪',
    'rise_fall': '起伏',
    'battle': '对垒',
  }[p] ?? p;

  @override
  Widget build(BuildContext context) {
    final songsById = {for (final s in widget.songs) s.id: s};
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Text('曲线 '),
              Expanded(
                child: DropdownButton<String>(
                  isExpanded: true,
                  value: _preset,
                  items: _presets.map((p) => DropdownMenuItem(value: p, child: Text(_labelPreset(p)))).toList(),
                  onChanged: (v) => setState(() => _preset = v),
                ),
              ),
              ElevatedButton(
                onPressed: _loading ? null : _run,
                child: Text(_loading ? '...' : '编排 ${_selectedIds.length}'),
              ),
            ],
          ),
          if (_error != null) Text('错误：$_error', style: const TextStyle(color: Colors.red, fontSize: 12)),
          const SizedBox(height: 8),
          Expanded(
            child: Row(
              children: [
                Expanded(
                  child: Card(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Padding(padding: EdgeInsets.all(6), child: Text('选择歌曲', style: TextStyle(fontSize: 12))),
                        Expanded(
                          child: ListView(
                            children: widget.songs.map((s) {
                              final selected = _selectedIds.contains(s.id);
                              return CheckboxListTile(
                                dense: true,
                                value: selected,
                                title: Text(s.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12)),
                                subtitle: Text('${s.artist} · ${s.bpm?.toStringAsFixed(0) ?? '-'} BPM', style: const TextStyle(fontSize: 10)),
                                onChanged: (v) {
                                  setState(() {
                                    if (v == true) _selectedIds.add(s.id); else _selectedIds.remove(s.id);
                                  });
                                },
                              );
                            }).toList(),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Card(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Padding(padding: EdgeInsets.all(6), child: Text('编排结果', style: TextStyle(fontSize: 12))),
                        Expanded(
                          child: _sequence.isEmpty
                              ? const Center(child: Text('未生成', style: TextStyle(fontSize: 11, color: Colors.grey)))
                              : ListView(
                                  children: _sequence.map((e) {
                                    final id = e['song_id']?.toString() ?? '';
                                    final title = songsById[id]?.title ?? id;
                                    final actual = (e['actual_energy'] as num).toDouble();
                                    final target = (e['target_energy'] as num).toDouble();
                                    return Padding(
                                      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 6),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.stretch,
                                        children: [
                                          Text('#${(e['position'] as int) + 1} $title', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11)),
                                          LinearProgressIndicator(value: actual),
                                          Text('tgt ${(target * 100).toInt()} / act ${(actual * 100).toInt()}', style: const TextStyle(fontSize: 9, color: Colors.grey)),
                                        ],
                                      ),
                                    );
                                  }).toList(),
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// --------------------------------------------------------------------------- //
// Tab 3: 过渡规则
// --------------------------------------------------------------------------- //
class _TransitionRulesTab extends StatefulWidget {
  const _TransitionRulesTab({required this.api, required this.token});
  final HarBeatApiClient api;
  final String token;

  @override
  State<_TransitionRulesTab> createState() => _TransitionRulesTabState();
}

class _TransitionRulesTabState extends State<_TransitionRulesTab> {
  Map<String, dynamic>? _rules;
  String? _error;

  @override
  void initState() {
    super.initState();
    widget.api.djListTransitionRules(token: widget.token).then((r) {
      if (mounted) setState(() => _rules = r);
    }).catchError((e) {
      if (mounted) setState(() => _error = e.toString());
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) return Center(child: Text('错误：$_error', style: const TextStyle(color: Colors.red)));
    if (_rules == null) return const Center(child: CircularProgressIndicator());
    final analyzed = (_rules!['analyzed'] as List).cast<Map<String, dynamic>>();
    final raw = (_rules!['raw'] as List).cast<Map<String, dynamic>>();
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            '分析型过渡需 BPM/Beat/Phrase 全部就绪；原生过渡仅依赖时间线。',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
          const SizedBox(height: 12),
          Text('分析型过渡（${analyzed.length}）', style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          Wrap(spacing: 8, runSpacing: 8, children: analyzed.map((r) => _ruleChip(r)).toList()),
          const SizedBox(height: 16),
          Text('原生过渡（${raw.length}）', style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          Wrap(spacing: 8, runSpacing: 8, children: raw.map((r) => _ruleChip(r)).toList()),
        ],
      ),
    );
  }

  Widget _ruleChip(Map<String, dynamic> r) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.deepPurple.withOpacity(0.1),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(r['label_zh']?.toString() ?? '', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
          Text(r['key']?.toString() ?? '', style: const TextStyle(fontSize: 9, color: Colors.grey)),
        ],
      ),
    );
  }
}

// --------------------------------------------------------------------------- //
// Tab 4: 现场切歌（信息展示，需要播放器集成才能真正调用）
// --------------------------------------------------------------------------- //
class _CutStrategiesTab extends StatelessWidget {
  const _CutStrategiesTab();

  @override
  Widget build(BuildContext context) {
    final items = [
      ('快切 fast_cut', '5 秒内寻找下一个 downbeat / beat / 1 小节边界，硬切到队列下一首。'),
      ('升能量切 energy_up_cut', '从 pool 中挑选能量明显高于当前 next 的候选替换，再执行快切。'),
      ('降能量切 energy_down_cut', '相反方向，挑选明显更低的候选，让 cypher 喘口气。'),
    ];
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const Text(
          '现场切歌需要播放器把 current_song_id / cursor_sec / queue 传给 /api/dj/cut/plan。',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
        const SizedBox(height: 12),
        ...items.map((e) => Card(
          child: ListTile(
            leading: const Icon(Icons.content_cut),
            title: Text(e.$1, style: const TextStyle(fontWeight: FontWeight.bold)),
            subtitle: Text(e.$2, style: const TextStyle(fontSize: 11)),
          ),
        )),
      ],
    );
  }
}

// --------------------------------------------------------------------------- //
// Tab 5: FX
// --------------------------------------------------------------------------- //
class _FxPadTab extends StatefulWidget {
  const _FxPadTab({required this.api, required this.token});
  final HarBeatApiClient api;
  final String token;

  @override
  State<_FxPadTab> createState() => _FxPadTabState();
}

class _FxPadTabState extends State<_FxPadTab> {
  List<Map<String, dynamic>> _items = const [];
  String? _error;
  final AudioPlayer _player = AudioPlayer();

  @override
  void initState() {
    super.initState();
    widget.api.djListFx(token: widget.token).then((x) {
      if (mounted) setState(() => _items = x);
    }).catchError((e) {
      if (mounted) setState(() => _error = e.toString());
    });
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _play(String key) async {
    try {
      await _player.stop();
      await _player.setUrl(widget.api.djFxAudioUrl(key));
      await _player.play();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('播放失败：$e')));
    }
  }

  IconData _iconFor(String key) => const {
    'scratch_chirp': Icons.graphic_eq,
    'air_horn': Icons.campaign,
    'snare_crack': Icons.music_note,
    'kick_roll': Icons.surround_sound,
    'rewind_zip': Icons.fast_rewind,
    'cymbal_swell': Icons.waves,
    'vinyl_stop': Icons.stop_circle,
  }[key] ?? Icons.volume_up;

  @override
  Widget build(BuildContext context) {
    if (_error != null) return Center(child: Text('错误：$_error', style: const TextStyle(color: Colors.red)));
    return GridView.count(
      crossAxisCount: 3,
      padding: const EdgeInsets.all(12),
      childAspectRatio: 1.0,
      children: _items.map((fx) {
        final key = fx['key']?.toString() ?? '';
        return Card(
          child: InkWell(
            onTap: () => _play(key),
            child: Padding(
              padding: const EdgeInsets.all(6),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(_iconFor(key), size: 36),
                  const SizedBox(height: 4),
                  Text(fx['label_zh']?.toString() ?? '', textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                  Text('${((fx['default_duration'] as num).toDouble()).toStringAsFixed(2)}s', style: const TextStyle(fontSize: 9, color: Colors.grey)),
                ],
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}

String _fmt(double sec) {
  final m = (sec / 60).floor();
  final s = (sec % 60).round();
  return '$m:${s.toString().padLeft(2, '0')}';
}
