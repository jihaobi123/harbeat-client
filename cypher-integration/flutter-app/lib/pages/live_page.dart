import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:dio/dio.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import '../state/providers.dart';
import '../state/mixtape_provider.dart';
import '../models/models.dart';
import '../core/api/rk_client.dart';
import '../core/api/jetson_client.dart';
import '../data/services/audio_player_service.dart';
import '../services/local_sfx.dart';
import 'mixtape_page.dart';

/// AI DJ 控制台 —— 参照网页 DJ Session 的功能集：
///  ① Deck（当前曲目 / 进度）
///  ② 歌曲选择（3 种导入方式）
///  ③ 风格 (12 chips) + 能量等级
///  ④ 循环最后 30 秒 / 切歌方式
///  ⑤ DJ 现场音效（5 种客户端实时合成：Scratch / Air Horn / Spinback / Siren / Whoosh）
///  ⑥ MC 语音控制（占位）
///  ⑦ Mix Plan（生成混音方案）
///  ⑧ 事件日志
class LivePage extends ConsumerStatefulWidget {
  const LivePage({super.key});

  @override
  ConsumerState<LivePage> createState() => _LivePageState();
}

class _LivePageState extends ConsumerState<LivePage> {
  // 选中的风格 chip（默认 hiphop），可任意切换 12 种
  String _selectedStyle = 'hiphop';
  String _selectedEnergy = 'medium';
  bool _isLooping = false;

  // Mix Plan section state
  String _planStyle = 'hiphop';
  int _planDurationMin = 10;
  String _planStrategy = 'CLEAN_BLEND';
  final List<int> _energyCurve = List<int>.filled(6, 5);
  bool _generatingPlan = false;
  bool _pushingPlan = false;
  Map<String, dynamic>? _lastPlanResult;
  // 当前播放的 plan track 下标（用于能量/风格切歌时定位）
  int _planTrackIdx = -1;
  // 已播放过的 plan track 下标集合（风格切歌时去重）
  final Set<int> _planPlayedIdx = {};
  // 推送/切歌时 RK /play 失败的 track 下标集合（后续不再选中）
  final Set<int> _planFailedIdx = {};

  // MC 语音
  final stt.SpeechToText _stt = stt.SpeechToText();
  bool _voiceAvailable = false;
  bool _voiceListening = false;
  String _voicePartial = '';

  // 全局硬件键盘监听（不依赖 Focus，避免 TextField 抢焦点导致 1-9 失效）
  bool _hwKeyHandlerRegistered = false;

  static const List<String> _mixStrategies = [
    'CLEAN_BLEND',
    'ENERGY_RAMP',
    'GENRE_BRIDGE',
    'BUILDUP_DROP',
    'BREAKDOWN_REBUILD',
    'VOCAL_SWAP',
    'BPM_RIDE',
    'CUT_THROAT',
  ];

  // 事件日志（最新在顶部）
  final List<_LogEntry> _logs = [];
  static const int _maxLogs = 40;

  static const List<String> _styles = [
    'hiphop', 'breaking', 'popping', 'locking', 'krump', 'waacking',
    'vogue', 'house', 'urban', 'commercial', 'jazzfunk', 'contemporary',
  ];

  @override
  void initState() {
    super.initState();
    HardwareKeyboard.instance.addHandler(_onHardwareKey);
    _hwKeyHandlerRegistered = true;
  }

  @override
  Widget build(BuildContext context) {
    final audio = ref.watch(audioPlayerProvider);
    final device = ref.watch(deviceProvider);
    final liveState = ref.watch(liveProvider);
    final isConnected = liveState.isConnected;

    return Scaffold(
      appBar: AppBar(
        title: const Text('🎧 DJ 控制台'),
        actions: [
          Consumer(builder: (_, ref, __) {
            final n = ref.watch(mixtapeProvider).length;
            return TextButton.icon(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MixtapePage()),
              ),
              icon: const Icon(Icons.queue_music, color: Colors.white),
              label: Text('Mixtape ($n)',
                  style: const TextStyle(color: Colors.white)),
            );
          }),
          IconButton(
            icon: const Icon(Icons.delete_sweep),
            tooltip: '清空事件日志',
            onPressed: () => setState(() => _logs.clear()),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (device != null && device.hasWarning)
              _WarningBanner(device: device),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _deckCard(audio),
                    const SizedBox(height: 12),
                    _transportRow(audio, isConnected),
                    const SizedBox(height: 16),
                    _sectionCard(
                      '� 歌曲选择（3 种方式）',
                      _importEntries(),
                    ),
                    const SizedBox(height: 12),
                    _sectionCard(
                      '🎼 风格切换',
                      _styleChips(isConnected),
                    ),
                    const SizedBox(height: 12),
                    _sectionCard(
                      '⚡ 能量等级',
                      _energyRow(isConnected),
                    ),
                    const SizedBox(height: 12),
                    _sectionCard(
                      '🔁 循环最后 30 秒',
                      _loopRow(isConnected),
                    ),
                    const SizedBox(height: 12),
                    _sectionCard(
                      '⏭ 切歌方式',
                      _mixTransitionRow(isConnected),
                    ),
                    const SizedBox(height: 12),
                    _sectionCard(
                      '🎵 DJ 现场音效',
                      _djSfxGrid(isConnected),
                    ),
                    const SizedBox(height: 12),
                    _sectionCard(
                      '🎙 MC 语音控制',
                      _mcRow(isConnected),
                    ),
                    const SizedBox(height: 12),
                    _sectionCard(
                      '🎛 Mix Plan（生成混音方案）',
                      _mixPlanSection(),
                    ),
                    const SizedBox(height: 12),
                    _logCard(),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ─────────── 子视图 ───────────

  Widget _sectionCard(String title, Widget child) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: const TextStyle(
                    fontSize: 14, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );
  }

  Widget _deckCard(AudioPlaybackState audio) {
    final theme = Theme.of(context);
    final hasTrack = audio.rkSongId != null || audio.title != null;
    final title = audio.title ??
        (audio.rkSongId != null ? '歌曲 #${audio.rkSongId}' : '未播放');
    final pos = audio.position.inMilliseconds / 1000.0;
    final dur = audio.duration.inMilliseconds / 1000.0;
    final maxV = dur > 0 ? dur : 1.0;
    final value = pos.clamp(0.0, maxV).toDouble();
    final stateLabel = !hasTrack
        ? '空闲'
        : audio.loading
            ? '加载中'
            : (audio.playing ? '播放中' : '已暂停');
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text('DECK A',
                      style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 11)),
                ),
                const SizedBox(width: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: audio.playing
                        ? Colors.green.withOpacity(0.15)
                        : Colors.grey.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(stateLabel,
                      style: TextStyle(
                          color: audio.playing ? Colors.green : Colors.grey,
                          fontWeight: FontWeight.bold,
                          fontSize: 11)),
                ),
                const Spacer(),
                if (audio.stemName != null)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text('独奏 · ${audio.stemName}',
                        style: TextStyle(
                            color: theme.colorScheme.primary,
                            fontWeight: FontWeight.bold,
                            fontSize: 11)),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              title,
              style: theme.textTheme.titleLarge
                  ?.copyWith(fontWeight: FontWeight.bold),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            if (audio.artist != null && audio.artist!.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(audio.artist!, style: theme.textTheme.bodySmall),
              ),
            const SizedBox(height: 8),
            Slider(
              value: value,
              max: maxV,
              onChanged: dur > 0
                  ? (v) {
                      ref
                          .read(audioPlayerProvider.notifier)
                          .seek(Duration(milliseconds: (v * 1000).round()));
                    }
                  : null,
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_fmt(pos), style: theme.textTheme.bodySmall),
                Text(_fmt(dur), style: theme.textTheme.bodySmall),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _transportRow(AudioPlaybackState audio, bool isConnected) {
    final theme = Theme.of(context);
    final canControl = isConnected && audio.rkSongId != null;
    return Row(
      children: [
        Expanded(
          child: ElevatedButton.icon(
            onPressed: canControl
                ? () {
                    HapticFeedback.mediumImpact();
                    ref.read(audioPlayerProvider.notifier).toggle();
                    _log(audio.playing ? '暂停' : '播放');
                  }
                : null,
            icon: Icon(audio.playing ? Icons.pause : Icons.play_arrow),
            label: Text(audio.playing ? '暂停' : '播放',
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.bold)),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: Colors.white,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: OutlinedButton.icon(
            onPressed: canControl
                ? () {
                    HapticFeedback.lightImpact();
                    ref.read(audioPlayerProvider.notifier).stop();
                    _log('停止');
                  }
                : null,
            icon: const Icon(Icons.stop),
            label: const Text('停止'),
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ),
      ],
    );
  }

  Widget _styleChips(bool enabled) {
    final theme = Theme.of(context);
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: _styles.map((s) {
        final sel = s == _selectedStyle;
        return ChoiceChip(
          label: Text(s.toUpperCase(),
              style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: sel ? Colors.white : theme.colorScheme.onSurface)),
          selected: sel,
          selectedColor: theme.colorScheme.primary,
          onSelected: enabled
              ? (_) {
                  setState(() => _selectedStyle = s);
                  HapticFeedback.lightImpact();
                  ref.read(rkClientProvider).setStyle(s);
                  _log('风格 → $s');
                }
              : null,
        );
      }).toList(),
    );
  }

  Widget _energyRow(bool enabled) {
    final theme = Theme.of(context);
    final levels = const [
      {'k': 'low', 'lab': '低', 'color': Colors.green},
      {'k': 'medium', 'lab': '中', 'color': Colors.amber},
      {'k': 'high', 'lab': '高', 'color': Colors.red},
    ];
    return Row(
      children: levels.map((e) {
        final k = e['k'] as String;
        final sel = k == _selectedEnergy;
        final color = e['color'] as Color;
        return Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: ElevatedButton(
              onPressed: enabled
                  ? () {
                      setState(() => _selectedEnergy = k);
                      HapticFeedback.lightImpact();
                      ref.read(rkClientProvider).setEnergy(k);
                      _log('能量 → $k');
                    }
                  : null,
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
                backgroundColor:
                    sel ? color : theme.colorScheme.surface,
                foregroundColor:
                    sel ? Colors.white : theme.colorScheme.onSurface,
                side: BorderSide(color: color, width: sel ? 2 : 1),
              ),
              child: Text(e['lab'] as String,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.bold)),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _loopRow(bool enabled) {
    return Row(
      children: [
        Expanded(
          child: ElevatedButton.icon(
            onPressed: enabled
                ? () {
                    setState(() => _isLooping = true);
                    HapticFeedback.mediumImpact();
                    ref.read(rkClientProvider).setLoop(true);
                    _log('循环最后 30s · ON');
                  }
                : null,
            icon: Icon(_isLooping ? Icons.repeat_one : Icons.repeat),
            label: const Text('循环最后 30s'),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
              backgroundColor: _isLooping ? Colors.orange : null,
              foregroundColor: _isLooping ? Colors.white : null,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: OutlinedButton.icon(
            onPressed: enabled
                ? () {
                    setState(() => _isLooping = false);
                    HapticFeedback.lightImpact();
                    ref.read(rkClientProvider).setLoop(false);
                    _log('循环 · OFF');
                  }
                : null,
            icon: const Icon(Icons.stop),
            label: const Text('退出循环'),
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ),
      ],
    );
  }

  Widget _mixTransitionRow(bool enabled) {
    final hasPlan = _lastPlanResult != null &&
        (((_lastPlanResult!['playlist'] ?? _lastPlanResult!['tracks'] ?? []) as List)
                .isNotEmpty);
    final btns = [
      {
        'lab': '下一首',
        'icon': Icons.skip_next,
        'color': const Color(0xFF26A69A),
        'on': () => _skipNextInPlan(),
      },
      {
        'lab': '能量↑切歌',
        'icon': Icons.trending_up,
        'color': const Color(0xFFE53935),
        'on': () => _skipByEnergy('higher'),
      },
      {
        'lab': '能量↓切歌',
        'icon': Icons.trending_down,
        'color': const Color(0xFF1E88E5),
        'on': () => _skipByEnergy('lower'),
      },
      {
        'lab': '按风格切歌',
        'icon': Icons.style,
        'color': const Color(0xFF673AB7),
        'on': () => _skipByStyle(),
      },
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GridView.count(
          crossAxisCount: 2,
          mainAxisSpacing: 8,
          crossAxisSpacing: 8,
          childAspectRatio: 2.3,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: btns.map((b) {
            return ElevatedButton.icon(
              onPressed: (enabled && hasPlan)
                  ? () {
                      HapticFeedback.mediumImpact();
                      (b['on'] as VoidCallback)();
                    }
                  : null,
              icon: Icon(b['icon'] as IconData, color: Colors.white, size: 18),
              label: Text(b['lab'] as String,
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.bold)),
              style: ElevatedButton.styleFrom(
                backgroundColor: b['color'] as Color,
                foregroundColor: Colors.white,
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 4),
        Text(
          hasPlan
              ? '在 Mix Plan 播放中。当前 #${_planTrackIdx < 0 ? '?' : _planTrackIdx + 1}'
              : '请先生成 Mix Plan，并点击「推送到 RK 并播放」启动播放',
          style: const TextStyle(fontSize: 11, color: Colors.grey),
        ),
      ],
    );
  }

  Widget _djSfxGrid(bool enabled) {
    // 5 种 DJ 现场音效 —— 统一走 RK3588 /trigger，不再本地回退。
    //   1 scratch  搓碟  → RK key=1
    //   2 air_horn 气笛  → RK key=2
    //   3 spinback 倒带  → RK key=3
    //   4 siren    警报  → RK key=4
    //   5 whoosh   嗖声  → RK key=5
    final fx = const [
      {'rkKey': 1, 'localId': 'scratch',  'lab': 'Scratch',  'cn': '搓碟', 'icon': '🎧', 'color': Color(0xFF9C27B0)},
      {'rkKey': 2, 'localId': 'air_horn', 'lab': 'Air Horn', 'cn': '气笛', 'icon': '📯', 'color': Color(0xFFE91E63)},
      {'rkKey': 3, 'localId': 'spinback', 'lab': 'Spinback', 'cn': '倒带', 'icon': '⏪', 'color': Color(0xFF00897B)},
      {'rkKey': 4, 'localId': 'siren',    'lab': 'Siren',    'cn': '警报', 'icon': '🚨', 'color': Color(0xFFFF5722)},
      {'rkKey': 5, 'localId': 'whoosh',   'lab': 'Whoosh',   'cn': '嗖声', 'icon': '💨', 'color': Color(0xFF3F51B5)},
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: fx.map((f) {
            final color = f['color'] as Color;
            return SizedBox(
              width: 104,
              height: 72,
              child: ElevatedButton(
                onPressed: () => _fireSfx(
                  rkKey: f['rkKey'] as int,
                  localId: f['localId'] as String,
                  label: '${f['cn']} ${f['lab']}',
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: color,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.all(6),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(f['icon'] as String,
                        style: const TextStyle(fontSize: 22)),
                    const SizedBox(height: 2),
                    Text('${f['cn']}  ${f['lab']}',
                        style: const TextStyle(
                            fontSize: 11, fontWeight: FontWeight.bold)),
                  ],
                ),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 6),
        const Text(
          '音效在 RK3588 本地播放（/trigger key=1~5）',
          style: TextStyle(fontSize: 11, color: Colors.grey),
        ),
      ],
    );
  }

  Widget _importEntries() {
    final entries = const [
      {
        'tab': 0,
        'title': '导入歌单',
        'desc': '粘贴 QQ / 网易云 / Spotify URL',
        'icon': Icons.link,
        'color': Color(0xFF6750A4),
      },
      {
        'tab': 1,
        'title': '曲库导入',
        'desc': '从已上传分析的曲库中选曲',
        'icon': Icons.library_music,
        'color': Color(0xFF1976D2),
      },
      {
        'tab': 2,
        'title': '语义搜索',
        'desc': '用 VIBE 关键词检索',
        'icon': Icons.psychology,
        'color': Color(0xFF388E3C),
      },
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final e in entries) ...[
          SizedBox(
            height: 56,
            child: ElevatedButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) =>
                      MixtapePage(initialTab: e['tab'] as int),
                ),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: e['color'] as Color,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                alignment: Alignment.centerLeft,
              ),
              child: Row(
                children: [
                  Icon(e['icon'] as IconData, size: 22),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(e['title'] as String,
                            style: const TextStyle(
                                fontSize: 14, fontWeight: FontWeight.bold)),
                        Text(e['desc'] as String,
                            style: const TextStyle(
                                fontSize: 11, color: Colors.white70)),
                      ],
                    ),
                  ),
                  const Icon(Icons.chevron_right, size: 20),
                ],
              ),
            ),
          ),
          const SizedBox(height: 6),
        ],
        Consumer(builder: (_, ref, __) {
          final n = ref.watch(mixtapeProvider).length;
          return Text(
            n == 0 ? '当前 Mixtape 为空，选择上方任一方式添加歌曲' : '当前 Mixtape 已选 $n 首',
            style: const TextStyle(fontSize: 12, color: Colors.grey),
          );
        }),
      ],
    );
  }

  Widget _mcRow(bool enabled) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: _voiceListening ? _stopVoice : _startVoice,
                icon: Icon(_voiceListening ? Icons.stop : Icons.mic),
                label: Text(_voiceListening ? '停止聆听' : '开始 MC 语音'),
                style: ElevatedButton.styleFrom(
                  backgroundColor:
                      _voiceListening ? Colors.red : theme.colorScheme.primary,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _runVoiceTextManually(),
                icon: const Icon(Icons.keyboard_voice),
                label: const Text('文本指令'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          _voiceListening
              ? '🎙 监听中… "${_voicePartial}"'
              : '说："下一首" / "升能量" / "切风格" / "循环30秒" / "暂停"',
          style: const TextStyle(fontSize: 11, color: Colors.grey),
        ),
      ],
    );
  }

  Widget _logCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('📜 事件日志',
                style:
                    TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            if (_logs.isEmpty)
              const Text('等待操作...',
                  style: TextStyle(fontSize: 12, color: Colors.grey))
            else
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 180),
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: _logs.length,
                  itemBuilder: (_, i) {
                    final e = _logs[i];
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Text(
                        '${e.timeText}  ${e.message}',
                        style: const TextStyle(
                            fontSize: 11, fontFamily: 'monospace'),
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }

  // ─────────── helpers ───────────

  /// 全部音效走 RK3588 /trigger，不再本地回退（用户要求 SFX 仅在 RK 播放）。
  Future<void> _fireSfx({
    required int rkKey,
    required String localId,
    required String label,
  }) async {
    HapticFeedback.lightImpact();
    try {
      final resp = await ref
          .read(rkClientProvider)
          .trigger(rkKey)
          .timeout(const Duration(milliseconds: 1500));
      final action = (resp['action'] ?? resp['ok'] ?? '').toString();
      _log('SFX · $label  → RK key=$rkKey  $action');
    } catch (e) {
      _log('SFX · $label ✗ RK key=$rkKey: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('RK 音效 key=$rkKey 失败: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Widget _mixPlanSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text('风格：', style: TextStyle(fontSize: 12)),
            const SizedBox(width: 4),
            DropdownButton<String>(
              value: _planStyle,
              isDense: true,
              items: _styles
                  .map((s) => DropdownMenuItem(
                      value: s,
                      child: Text(s.toUpperCase(),
                          style: const TextStyle(fontSize: 12))))
                  .toList(),
              onChanged: (v) => setState(() => _planStyle = v ?? 'hiphop'),
            ),
            const SizedBox(width: 12),
            const Text('时长：', style: TextStyle(fontSize: 12)),
            SizedBox(
              width: 56,
              child: TextFormField(
                initialValue: '$_planDurationMin',
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                    isDense: true, suffixText: 'min'),
                onChanged: (v) {
                  final n = int.tryParse(v);
                  if (n != null && n > 0 && n <= 120) {
                    _planDurationMin = n;
                  }
                },
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            const Text('混音策略：', style: TextStyle(fontSize: 12)),
            const SizedBox(width: 4),
            Expanded(
              child: DropdownButton<String>(
                value: _planStrategy,
                isExpanded: true,
                isDense: true,
                items: _mixStrategies
                    .map((s) => DropdownMenuItem(
                        value: s,
                        child: Text(s,
                            style: const TextStyle(fontSize: 12))))
                    .toList(),
                onChanged: (v) =>
                    setState(() => _planStrategy = v ?? 'CLEAN_BLEND'),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        const Text('能量曲线（6 段，1-10；所有值相同则不发送曲线）',
            style: TextStyle(fontSize: 11, color: Colors.grey)),
        const SizedBox(height: 6),
        Row(
          children: List.generate(6, (i) {
            return Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2),
                child: Column(
                  children: [
                    Text('#${i + 1}',
                        style: const TextStyle(fontSize: 10)),
                    SizedBox(
                      height: 36,
                      child: TextFormField(
                        key: ValueKey('ec-$i-${_energyCurve[i]}'),
                        initialValue: '${_energyCurve[i]}',
                        textAlign: TextAlign.center,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                            isDense: true, contentPadding: EdgeInsets.all(4)),
                        onChanged: (v) {
                          final n = int.tryParse(v);
                          if (n != null && n >= 1 && n <= 10) {
                            _energyCurve[i] = n;
                          }
                        },
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
        ),
        const SizedBox(height: 6),
        Wrap(
          spacing: 4,
          children: [
            OutlinedButton(
              onPressed: () => setState(() {
                for (var i = 0; i < 6; i++) {
                  _energyCurve[i] = 1 + (9 * i / 5).round();
                }
              }),
              child: const Text('渐强', style: TextStyle(fontSize: 11)),
            ),
            OutlinedButton(
              onPressed: () => setState(() {
                const v = [10, 6, 2, 2, 6, 10];
                for (var i = 0; i < 6; i++) {
                  _energyCurve[i] = v[i];
                }
              }),
              child: const Text('V形', style: TextStyle(fontSize: 11)),
            ),
            OutlinedButton(
              onPressed: () => setState(() {
                const v = [3, 9, 5, 5, 9, 3];
                for (var i = 0; i < 6; i++) {
                  _energyCurve[i] = v[i];
                }
              }),
              child: const Text('双峰', style: TextStyle(fontSize: 11)),
            ),
            OutlinedButton(
              onPressed: () => setState(() {
                for (var i = 0; i < 6; i++) {
                  _energyCurve[i] = 5;
                }
              }),
              child: const Text('清空', style: TextStyle(fontSize: 11)),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Consumer(builder: (_, ref, __) {
          final mixtape = ref.watch(mixtapeProvider);
          return Text(
            '将使用 Mixtape 中的 ${mixtape.length} 首歌作为混音输入'
            '${mixtape.isEmpty ? '（为空时后端将自动选曲）' : ''}',
            style: const TextStyle(fontSize: 11, color: Colors.grey),
          );
        }),
        const SizedBox(height: 8),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: _generatingPlan ? null : _generateMixPlan,
            icon: _generatingPlan
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.auto_awesome),
            label: const Text('🚀 生成 Mix Plan'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.deepPurple,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
          ),
        ),
        if (_lastPlanResult != null) ...[
          const SizedBox(height: 8),
          _planResultCard(_lastPlanResult!),
        ],
      ],
    );
  }

  Widget _planResultCard(Map<String, dynamic> plan) {
    // 服务器返回使用 playlist / transition_plan；用 tracks/transitions 作为干补其它另外的代码路径
    final tracks =
        (plan['playlist'] ?? plan['tracks'] ?? []) as List;
    final transitions =
        (plan['transition_plan'] ?? plan['transitions'] ?? []) as List;
    final planId = plan['plan_id']?.toString() ?? '?';
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Colors.deepPurple.withOpacity(0.08),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.deepPurple.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Plan: $planId',
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Text('Tracks: ${tracks.length}    Transitions: ${transitions.length}',
              style: const TextStyle(fontSize: 11)),
          const SizedBox(height: 4),
          ...tracks.take(10).map((t) {
            final m = (t as Map);
            final order = m['order'] ?? m['slot_index'] ?? '?';
            final sid = m['song_id'] ?? m['library_song_id'] ?? '?';
            final start = (m['start_at_sec'] ?? m['start_sec'] ?? 0);
            final dur =
                (m['play_duration_sec'] ?? m['duration_sec'] ?? m['duration'] ?? 0);
            return Text(
              '  $order. song=$sid  '
              'start=${(start is num ? start.toDouble() : 0.0).toStringAsFixed(1)}s  '
              'dur=${(dur is num ? dur.toDouble() : 0.0).toStringAsFixed(1)}s',
              style: const TextStyle(fontSize: 10, fontFamily: 'monospace'),
            );
          }),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _pushingPlan || tracks.isEmpty
                      ? null
                      : () => _pushPlanAndPlay(plan),
                  icon: _pushingPlan
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.play_circle_filled, size: 18),
                  label: const Text('推送到 RK 并播放',
                      style: TextStyle(fontWeight: FontWeight.bold)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.green.shade700,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
              const SizedBox(width: 6),
              OutlinedButton.icon(
                onPressed: tracks.isEmpty
                    ? null
                    : () {
                        HapticFeedback.lightImpact();
                        ref.read(rkClientProvider).next();
                        _log('Plan · 下一首');
                      },
                icon: const Icon(Icons.skip_next, size: 18),
                label: const Text('下一首'),
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            '点击后 Jetson→sync-worker→RK3588 缓存音频，RK3588 真正播放。\n'
            '随后可用下方“循环 / 切歌 / 5 键 SFX”实时控制。',
            style: TextStyle(fontSize: 10, color: Colors.grey),
          ),
        ],
      ),
    );
  }

  /// 调用 audioPlayerProvider 走 RK3588 /play（必要时走 sync）。
  /// 返回空字符串代表成功，否则返回错误文本。
  Future<String> _playOnRk({
    required int? rkSongId,
    required String songUuid,
    required String label,
    String? title,
    String? artist,
    double? durationSec,
  }) async {
    try {
      _log('$label · → RK /play  rk_song_id=$rkSongId  uuid=$songUuid');
      await ref.read(audioPlayerProvider.notifier).play(
            songId: songUuid,
            rkSongId: rkSongId,
            title: title,
            artist: artist,
            durationSec: durationSec,
          );
      final err = ref.read(audioPlayerProvider).errorMessage;
      if (err != null && err.isNotEmpty) return err;
      _log('$label · ▶ $title — $artist (rk_song_id=$rkSongId)');
      return '';
    } catch (e) {
      return '$e';
    }
  }

  /// 主动 crossfade 到目标歌（无缝衔接，复刻网页 SeamlessPlayer）。
  Future<String> _xfadeOnRk({
    required int? rkSongId,
    required String songUuid,
    required String label,
    String? title,
    String? artist,
    double? durationSec,
    double fadeSec = 4.0,
    String style = 'smooth',
  }) async {
    try {
      _log('$label · → RK /xfade  rk_song_id=$rkSongId  uuid=$songUuid  fade=${fadeSec}s style=$style');
      await ref.read(audioPlayerProvider.notifier).xfadeTo(
            songId: songUuid,
            rkSongId: rkSongId,
            title: title,
            artist: artist,
            durationSec: durationSec,
            fadeSec: fadeSec,
            style: style,
          );
      final err = ref.read(audioPlayerProvider).errorMessage;
      if (err != null && err.isNotEmpty) return err;
      _log('$label · ✕→ crossfade [$style] 到 $title — $artist (rk_song_id=$rkSongId)');
      return '';
    } catch (e) {
      return '$e';
    }
  }

  Future<void> _pushPlanAndPlay(Map<String, dynamic> plan) async {
    setState(() => _pushingPlan = true);
    try {
      final tracks = (plan['playlist'] ?? plan['tracks'] ?? []) as List;
      if (tracks.isEmpty) {
        _log('Plan ✗ 无 track 可播放');
        return;
      }
      final first = Map<String, dynamic>.from(tracks.first as Map);
      final libId = first['library_song_id']?.toString() ?? '';
      final sid = first['song_id'];
      final rkSid = sid is int ? sid : int.tryParse('${sid ?? ''}');
      final title = first['title']?.toString();
      final artist = first['artist']?.toString();
      final dur = first['duration'] ?? first['duration_sec'] ?? first['play_duration_sec'];
      final durSec = (dur is num) ? dur.toDouble() : null;
      if (libId.isEmpty) {
        _log('Plan ✗ 首曲缺 library_song_id');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('首曲缺 UUID，无法推送'),
              backgroundColor: Colors.red,
            ),
          );
        }
        return;
      }

      // ① 预先把所有 plan 内的 song 同步到 RK3588 缓存
      //    （Jetson 已存 → 通过 sync-worker 拉到 RK，避免切歌时冷启动 409）
      final allIds = <String>{};
      for (final t in tracks) {
        if (t is! Map) continue;
        final m = Map<String, dynamic>.from(t);
        final id = (m['library_song_id'] ?? m['song_uuid'] ?? m['uuid'])?.toString();
        if (id != null && id.isNotEmpty) allIds.add(id);
      }
      if (allIds.isNotEmpty) {
        _log('Plan · 同步 ${allIds.length} 首歌到 RK3588（Jetson→RK 缓存）…');
        final sync = ref.read(rkSyncServiceProvider);
        try {
          await for (final ev in sync.cacheSongs(librarySongIds: allIds.toList())) {
            final stage = ev['stage'];
            final pct = (ev['percent'] as num?)?.toDouble() ?? 0.0;
            if (stage != null) {
              final cur = ev['current_file'];
              _log('Plan · 同步[${pct.toStringAsFixed(0)}%] $stage${cur != null ? ' $cur' : ''}');
            }
            if (ev['done'] == true) {
              final errs = (ev['errors'] as List?) ?? const [];
              if (errs.isEmpty) {
                _log('Plan · ✓ ${allIds.length} 首歌已缓存到 RK');
              } else {
                _log('Plan · ⚠ 同步完成但有错误：${errs.length} 项 → $errs');
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('同步未完全成功：${errs.first}'),
                      backgroundColor: Colors.orange,
                      duration: const Duration(seconds: 5),
                    ),
                  );
                }
              }
              break;
            }
          }
        } catch (e) {
          _log('Plan · ⚠ 同步异常（继续尝试播放）：$e');
        }
      }

      // ② 播放首曲（此时 RK 应已具备 original.wav）
      _log('Plan · 推送到 RK3588：$title — $artist (rk_song_id=$rkSid)');
      final err = await _playOnRk(
        rkSongId: rkSid,
        songUuid: libId,
        label: 'Plan',
        title: title,
        artist: artist,
        durationSec: durSec,
      );
      if (err.isNotEmpty) {
        _log('Plan ✗ $err');
        // 标记首曲失败，并把 _planTrackIdx 置为 0（让“下一首/能量/风格”能从 1 起跳过它）
        setState(() {
          _planTrackIdx = 0;
          _planPlayedIdx.clear();
          _planFailedIdx
            ..clear()
            ..add(0);
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('首曲推送失败: $err，可按 6/7/8/9 切下一首'),
              backgroundColor: Colors.red,
              duration: const Duration(seconds: 5),
            ),
          );
        }
      } else {
        setState(() {
          _planTrackIdx = 0;
          _planPlayedIdx
            ..clear()
            ..add(0);
          _planFailedIdx.clear();
        });
        _log('Plan ✓ 首曲已开始播放，下方控制可用');
      }
    } catch (e) {
      _log('Plan ✗ 推送失败: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('推送失败: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _pushingPlan = false);
    }
  }

  Future<void> _generateMixPlan() async {
    setState(() {
      _generatingPlan = true;
      _lastPlanResult = null;
    });
    try {
      // 仅当用户改动过 6 段才发送曲线
      final allSame = _energyCurve.every((v) => v == _energyCurve.first);
      final curve = allSame
          ? null
          : _energyCurve.map((v) => v.toDouble()).toList();

      var mixtape = ref.read(mixtapeProvider);
      if (mixtape.isEmpty) {
        _log('Mix Plan ✗ Mixtape 为空，请先从【曲库/导入】选歌。');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Mixtape 为空，请先选择歌曲'),
              backgroundColor: Colors.orange,
            ),
          );
        }
        return;
      }

      // 解析阶段：把没有 library UUID 的条目（通常来自 URL 解析候选）
      // 提交给 Jetson /api/fangpi/import-songs，让服务器下载并落库，
      // 然后用返回的 library_song_id 回填到 mixtape，再走 mix-plan。
      final jet = ref.read(jetsonClientProvider);
      final pendingIdx = <int>[];
      final pendingPayload = <Map<String, dynamic>>[];
      for (var i = 0; i < mixtape.length; i++) {
        final m = mixtape[i];
        final hasUuid = m.librarySongId != null && _isUuid(m.librarySongId!);
        if (!hasUuid) {
          pendingIdx.add(i);
          pendingPayload.add(m.toImportPayload());
        }
      }
      if (pendingPayload.isNotEmpty) {
        _log('Mix Plan · 需先下载 ${pendingPayload.length} 首到 Jetson 曲库…');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('正在 Jetson 下载/分析 ${pendingPayload.length} 首歌…'),
              duration: const Duration(seconds: 4),
            ),
          );
        }
        try {
          final r = await jet.fangpiImportSongs(
            songs: pendingPayload,
            playlistName: 'AppMixtape',
          );
          final data = (r['data'] ?? r) as Map<String, dynamic>;
          final imported = (data['imported'] as List? ?? [])
              .cast<Map<String, dynamic>>();
          final failed = (data['failed'] as List? ?? []);
          // imported[i].index 是 pendingPayload 内的下标；映射回 mixtape 下标
          final notifier = ref.read(mixtapeProvider.notifier);
          for (final it in imported) {
            final pIdx = (it['index'] is int)
                ? it['index'] as int
                : int.tryParse('${it['index']}') ?? -1;
            if (pIdx < 0 || pIdx >= pendingIdx.length) continue;
            final mIdx = pendingIdx[pIdx];
            if (mIdx >= mixtape.length) continue;
            final libId = it['library_song_id']?.toString();
            final sId = (it['song_id'] is int)
                ? it['song_id'] as int
                : int.tryParse('${it['song_id']}');
            if (libId == null) continue;
            notifier.replaceAt(
              mIdx,
              MixtapeNotifier.withIds(
                mixtape[mIdx],
                librarySongId: libId,
                songId: sId,
              ),
            );
          }
          mixtape = ref.read(mixtapeProvider);
          _log('Mix Plan · 下载完成 ok=${imported.length} 失败=${failed.length}');
          if (failed.isNotEmpty) {
            _log('Mix Plan · 失败示例: ${failed.first}');
          }
        } catch (e) {
          String msg = e.toString();
          if (e is DioException) {
            final code = e.response?.statusCode;
            msg = '${code ?? '?'}  ${e.message ?? ''}';
          }
          _log('Mix Plan ✗ 下载阶段失败: $msg（fangpi 不可用，跳过 ${pendingPayload.length} 首未落库歌曲，继续用已落库歌生成）');
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Jetson 下载失败 ($msg)，跳过 ${pendingPayload.length} 首继续生成'),
                backgroundColor: Colors.orange,
                duration: const Duration(seconds: 4),
              ),
            );
          }
          // 不再 return；让已经在 library 里的歌继续往下走 mix-plan
        }
      }

      // 重新提取 UUID / songId
      final libIds = mixtape
          .where((m) => m.librarySongId != null && _isUuid(m.librarySongId!))
          .map((m) => m.librarySongId!)
          .toList();
      final songIds = mixtape
          .where((m) => m.songId != null)
          .map((m) => m.songId!)
          .toList();

      if (libIds.length < 2 && songIds.length < 2) {
        _log('Mix Plan ✗ 可用歌曲不足 2 首，无法生成 mix-plan');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('可用歌曲不足 2 首（需 >=2 已落库歌曲）'),
              backgroundColor: Colors.orange,
            ),
          );
        }
        return;
      }

      final r = await jet.devMixPlan(
        style: _planStyle,
        durationMinutes: _planDurationMin,
        librarySongIds: libIds.length >= 2 ? libIds : null,
        songIds: songIds.isEmpty ? null : songIds,
        targetEnergyCurve: curve,
        maxTracks: 8,
      );
      final data = (r['data'] ?? r) as Map<String, dynamic>;
      setState(() => _lastPlanResult = data);
      final n = ((data['playlist'] ?? data['tracks']) as List?)?.length ?? 0;
      _log('Mix Plan ✓ tracks=$n  strategy=$_planStrategy');
    } catch (e) {
      String msg = e.toString();
      if (e is DioException) {
        final code = e.response?.statusCode;
        msg = '${code ?? '?'}  ${e.message ?? ''}';
      }
      _log('Mix Plan ✗ $msg');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('生成失败: $msg'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _generatingPlan = false);
    }
  }

  bool _isUuid(String s) {
    final hex = s.replaceAll('-', '').toLowerCase();
    return hex.length == 32 && RegExp(r'^[0-9a-f]{32}$').hasMatch(hex);
  }

  // ─────────── Mix Plan 客户端切歌 ───────────
  //
  // 参考网页版 MixSessionController：
  //   - 下一首：plan.playlist 顺序的下一项
  //   - 能量↑/↓：从未播放过的 tracks 中找 energy 差 >= 0.05 的，按差距排序
  //   - 按风格：按 Camelot 键盘距离排序，BPM 差异作为次序

  List<Map<String, dynamic>> _planTracks() {
    final plan = _lastPlanResult;
    if (plan == null) return const [];
    final tracks = (plan['playlist'] ?? plan['tracks'] ?? []) as List;
    return tracks.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  }

  double _trackEnergy(Map<String, dynamic> t) {
    final e = t['energy'];
    if (e is num) return e.toDouble();
    return 0.5;
  }

  /// 从 plan 的 transition_plan 取 (fromIdx → toIdx) 的 transition_type 作为切歌风格。
  /// 缺省 'smooth'。仅在“下一首”按时间表切歌时用得上。
  String _planTransitionStyle(int fromIdx, int toIdx) {
    final plan = _lastPlanResult;
    if (plan == null) return 'smooth';
    final list = (plan['transition_plan'] ?? plan['transitions'] ?? []) as List;
    final tracks = _planTracks();
    if (fromIdx < 0 || fromIdx >= tracks.length) return 'smooth';
    if (toIdx < 0 || toIdx >= tracks.length) return 'smooth';
    final fromSid = tracks[fromIdx]['song_id'];
    final toSid = tracks[toIdx]['song_id'];
    for (final raw in list) {
      if (raw is! Map) continue;
      final m = Map<String, dynamic>.from(raw);
      final fs = m['from_song_id'] ?? m['from_song'];
      final ts = m['to_song_id'] ?? m['to_song'];
      if ('$fs' == '$fromSid' && '$ts' == '$toSid') {
        final tt = (m['transition_type'] ?? m['style'])?.toString();
        if (tt != null && tt.isNotEmpty) return tt;
      }
    }
    return 'smooth';
  }

  /// 异步预取下一首候选歌：plan 内 next + 能量↑/↓ 各一首；非阻塞。
  /// 让 RK audio-engine 把 wav+stems 提前解码到内存，按键 /xfade 即取即用。
  Future<void> _prefetchLikelyNext() async {
    try {
      final tracks = _planTracks();
      if (tracks.isEmpty) return;
      final cur = _planTrackIdx >= 0 && _planTrackIdx < tracks.length
          ? tracks[_planTrackIdx]
          : null;
      final curE = cur != null ? _trackEnergy(cur) : 0.5;
      final picks = <int>{};
      // next in plan
      for (var i = _planTrackIdx + 1; i < tracks.length; i++) {
        if (_planFailedIdx.contains(i)) continue;
        picks.add(i);
        break;
      }
      // energy ↑/↓ 各一首未播放、未失败
      int? bestUp;
      double bestUpE = -1;
      int? bestDn;
      double bestDnE = 2;
      for (var i = 0; i < tracks.length; i++) {
        if (i == _planTrackIdx) continue;
        if (_planPlayedIdx.contains(i)) continue;
        if (_planFailedIdx.contains(i)) continue;
        final e = _trackEnergy(tracks[i]);
        if (e > curE && e > bestUpE) {
          bestUpE = e;
          bestUp = i;
        }
        if (e < curE && e < bestDnE) {
          bestDnE = e;
          bestDn = i;
        }
      }
      if (bestUp != null) picks.add(bestUp);
      if (bestDn != null) picks.add(bestDn);
      final rkIds = <dynamic>[];
      for (final idx in picks) {
        final sid = tracks[idx]['song_id'] ?? tracks[idx]['rk_song_id'];
        if (sid != null) rkIds.add(sid);
      }
      if (rkIds.isEmpty) return;
      await ref.read(audioPlayerProvider.notifier).prefetch(rkIds);
      _log('prefetch · 候选 ${rkIds.length} 首已请求 RK 预解码');
    } catch (e) {
      // 预取失败不影响主流程
    }
  }

  ({int n, String letter})? _parseCamelot(String? k) {
    if (k == null || k.isEmpty) return null;
    final m = RegExp(r'^(\d{1,2})([AaBb])$').firstMatch(k.trim());
    if (m == null) return null;
    final n = int.tryParse(m.group(1)!);
    if (n == null || n < 1 || n > 12) return null;
    return (n: n, letter: m.group(2)!.toUpperCase());
  }

  int _camelotDistance(({int n, String letter}) a, ({int n, String letter}) b) {
    final d = (a.n - b.n).abs();
    final num = math.min(d, 12 - d);
    return num + (a.letter == b.letter ? 0 : 1);
  }

  Future<void> _playPlanTrack(int idx, {required String label}) async {
    final tracks = _planTracks();
    if (idx < 0 || idx >= tracks.length) {
      _log('$label ✗ 索引越界 $idx/${tracks.length}');
      return;
    }
    final t = tracks[idx];
    final libId = (t['library_song_id'] ?? t['song_uuid'] ?? t['uuid'] ?? t['id'])?.toString() ?? '';
    if (libId.isEmpty) {
      _log('$label ✗ track #$idx 缺 UUID：keys=${t.keys.toList()}');
      return;
    }
    final sid = t['song_id'] ?? t['rk_song_id'];
    final rkSid = sid is int ? sid : int.tryParse('${sid ?? ''}');
    final title = t['title']?.toString();
    final artist = t['artist']?.toString();
    final dur = t['duration'] ?? t['duration_sec'] ?? t['play_duration_sec'];
    final durSec = (dur is num) ? dur.toDouble() : null;
    _log('$label · → #${idx + 1} $title  rk_song_id=$rkSid uuid=$libId');
    final err = await _playOnRk(
      rkSongId: rkSid,
      songUuid: libId,
      label: label,
      title: title,
      artist: artist,
      durationSec: durSec,
    );
    if (err.isNotEmpty) {
      _log('$label ✗ $err');
      setState(() => _planFailedIdx.add(idx));
      return;
    }
    setState(() {
      _planTrackIdx = idx;
      _planPlayedIdx.add(idx);
      _planFailedIdx.remove(idx);
    });
  }

  /// 切到 plan 内某一首：若当前已在播，则 /xfade（无缝），否则 /play（硬切）。
  Future<void> _xfadeToPlanTrack(
    int idx, {
    required String label,
    double fadeSec = 4.0,
    String style = 'smooth',
  }) async {
    final tracks = _planTracks();
    if (idx < 0 || idx >= tracks.length) {
      _log('$label ✗ 索引越界 $idx/${tracks.length}');
      return;
    }
    final t = tracks[idx];
    final libId = (t['library_song_id'] ?? t['song_uuid'] ?? t['uuid'] ?? t['id'])?.toString() ?? '';
    if (libId.isEmpty) {
      _log('$label ✗ track #$idx 缺 UUID：keys=${t.keys.toList()}');
      return;
    }
    final sid = t['song_id'] ?? t['rk_song_id'];
    final rkSid = sid is int ? sid : int.tryParse('${sid ?? ''}');
    final title = t['title']?.toString();
    final artist = t['artist']?.toString();
    final dur = t['duration'] ?? t['duration_sec'] ?? t['play_duration_sec'];
    final durSec = (dur is num) ? dur.toDouble() : null;
    _log('$label · ✕→ #${idx + 1} $title  rk_song_id=$rkSid uuid=$libId style=$style');
    final err = await _xfadeOnRk(
      rkSongId: rkSid,
      songUuid: libId,
      label: label,
      title: title,
      artist: artist,
      durationSec: durSec,
      fadeSec: fadeSec,
      style: style,
    );
    if (err.isNotEmpty) {
      _log('$label ✗ $err');
      setState(() => _planFailedIdx.add(idx));
      return;
    }
    setState(() {
      _planTrackIdx = idx;
      _planPlayedIdx.add(idx);
      _planFailedIdx.remove(idx);
    });
    // 异步预取下次最可能被切到的歌，给下一次切歌提供 ~0ms 响应
    unawaited(_prefetchLikelyNext());
  }

  Future<void> _skipNextInPlan() async {
    final tracks = _planTracks();
    _log('下一首 · 列表=${tracks.length} 当前=${_planTrackIdx}');
    if (tracks.isEmpty) {
      _log('下一首 ✗ plan 为空，请先点“推送到 RK”');
      return;
    }
    // 从当前下标往后找第一个未失败、未播过的 track
    int nextIdx = -1;
    for (var i = _planTrackIdx + 1; i < tracks.length; i++) {
      if (_planFailedIdx.contains(i)) continue;
      nextIdx = i;
      break;
    }
    if (nextIdx < 0) {
      // 轮回起点再找一轮（插入可用者）
      for (var i = 0; i <= _planTrackIdx && i < tracks.length; i++) {
        if (i == _planTrackIdx) continue;
        if (_planFailedIdx.contains(i)) continue;
        nextIdx = i;
        break;
      }
    }
    if (nextIdx < 0) {
      _log('下一首 · 已无可用歌曲');
      return;
    }
    await _xfadeToPlanTrack(nextIdx, label: '下一首', fadeSec: 4.0, style: _planTransitionStyle(_planTrackIdx, nextIdx));
  }

  Future<void> _skipByEnergy(String direction) async {
    final tracks = _planTracks();
    if (tracks.isEmpty) return;
    final cur = _planTrackIdx >= 0 && _planTrackIdx < tracks.length
        ? tracks[_planTrackIdx]
        : null;
    final curE = cur != null ? _trackEnergy(cur) : 0.5;
    const delta = 0.05;
    final candidates = <MapEntry<int, double>>[];
    for (var i = 0; i < tracks.length; i++) {
      if (i == _planTrackIdx) continue;
      if (_planPlayedIdx.contains(i)) continue;
      if (_planFailedIdx.contains(i)) continue;
      final e = _trackEnergy(tracks[i]);
      if (direction == 'higher' && e >= curE + delta) {
        candidates.add(MapEntry(i, e));
      } else if (direction == 'lower' && e <= curE - delta) {
        candidates.add(MapEntry(i, e));
      }
    }
    if (candidates.isEmpty) {
      // 放宽：直接挑能量最高/最低的未播放项
      for (var i = 0; i < tracks.length; i++) {
        if (i == _planTrackIdx) continue;
        if (_planPlayedIdx.contains(i)) continue;
        if (_planFailedIdx.contains(i)) continue;
        candidates.add(MapEntry(i, _trackEnergy(tracks[i])));
      }
      if (candidates.isEmpty) {
        _log('能量${direction == 'higher' ? '↑' : '↓'} · 已无可用歌曲');
        return;
      }
    }
    candidates.sort((a, b) =>
        direction == 'higher' ? b.value.compareTo(a.value) : a.value.compareTo(b.value));
    final pick = candidates.first.key;
    await _xfadeToPlanTrack(pick,
        label: '能量${direction == 'higher' ? '↑' : '↓'} (e=${candidates.first.value.toStringAsFixed(2)})',
        fadeSec: 4.0,
        style: direction == 'higher' ? 'power' : 'echo_out');
  }

  Future<void> _skipByStyle() async {
    final tracks = _planTracks();
    if (tracks.isEmpty) return;
    final cur = _planTrackIdx >= 0 && _planTrackIdx < tracks.length
        ? tracks[_planTrackIdx]
        : null;
    final curK = _parseCamelot(cur?['camelot_key']?.toString() ??
        cur?['key']?.toString());
    final curBpm = (cur?['bpm'] is num) ? (cur!['bpm'] as num).toDouble() : 120.0;
    final scored = <({int idx, int dist, double bpmDiff})>[];
    for (var i = 0; i < tracks.length; i++) {
      if (i == _planTrackIdx) continue;
      if (_planPlayedIdx.contains(i)) continue;
      if (_planFailedIdx.contains(i)) continue;
      final k = _parseCamelot(tracks[i]['camelot_key']?.toString() ??
          tracks[i]['key']?.toString());
      final dist = (curK == null || k == null) ? 99 : _camelotDistance(curK, k);
      final bpm = (tracks[i]['bpm'] is num) ? (tracks[i]['bpm'] as num).toDouble() : 120.0;
      scored.add((idx: i, dist: dist, bpmDiff: (bpm - curBpm).abs()));
    }
    if (scored.isEmpty) {
      _log('风格切歌 · 已无可用歌曲');
      return;
    }
    scored.sort((a, b) {
      if (a.dist != b.dist) return a.dist.compareTo(b.dist);
      return a.bpmDiff.compareTo(b.bpmDiff);
    });
    final pick = scored.first;
    await _xfadeToPlanTrack(pick.idx,
        label: '风格 (camelot dist=${pick.dist}, ΔBPM=${pick.bpmDiff.toStringAsFixed(1)})',
        fadeSec: 4.0,
        style: pick.dist <= 1 ? 'bass_swap' : 'filter');
  }

  // ─────────── MC 语音控制 ───────────

  Future<void> _initVoiceIfNeeded() async {
    if (_voiceAvailable) return;
    try {
      _voiceAvailable = await _stt.initialize(
        onError: (e) => _log('MC ✗ STT 错误: ${e.errorMsg}'),
        onStatus: (s) {
          if (s == 'notListening' || s == 'done') {
            if (mounted && _voiceListening) {
              setState(() => _voiceListening = false);
            }
          }
        },
      );
    } catch (e) {
      _log('MC ✗ STT 初始化失败: $e');
    }
  }

  Future<void> _startVoice() async {
    HapticFeedback.lightImpact();
    await _initVoiceIfNeeded();
    if (!_voiceAvailable) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('语音识别不可用，请检查麦克风权限'),
            backgroundColor: Colors.red,
          ),
        );
      }
      return;
    }
    setState(() {
      _voiceListening = true;
      _voicePartial = '';
    });
    _log('MC · 监听开始');
    await _stt.listen(
      onResult: (r) {
        final text = r.recognizedWords;
        setState(() => _voicePartial = text);
        if (r.finalResult && text.trim().isNotEmpty) {
          _handleVoiceText(text);
        }
      },
      localeId: 'zh_CN',
      listenFor: const Duration(seconds: 12),
      pauseFor: const Duration(seconds: 2),
      partialResults: true,
      cancelOnError: true,
    );
  }

  Future<void> _stopVoice() async {
    await _stt.stop();
    if (mounted) setState(() => _voiceListening = false);
    _log('MC · 监听停止');
  }

  Future<void> _runVoiceTextManually() async {
    final ctrl = TextEditingController();
    final text = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('输入 MC 指令'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: '例如：下一首 / 升能量 / 切风格 / 暂停',
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消')),
          ElevatedButton(
              onPressed: () => Navigator.pop(context, ctrl.text),
              child: const Text('执行')),
        ],
      ),
    );
    if (text != null && text.trim().isNotEmpty) {
      _handleVoiceText(text.trim());
    }
  }

  Future<void> _handleVoiceText(String text) async {
    _log('MC · 「$text」');
    try {
      final jet = ref.read(jetsonClientProvider);
      final r = await jet.voiceCommand(text: text, languageHint: 'auto');
      final data = (r['data'] ?? r) as Map<String, dynamic>;
      final intent = data['intent']?.toString() ?? 'noop';
      final conf = (data['confidence'] is num)
          ? (data['confidence'] as num).toDouble()
          : 0.0;
      _log('MC · intent=$intent (${conf.toStringAsFixed(2)})');
      await _dispatchVoiceIntent(intent);
    } catch (e) {
      _log('MC ✗ 服务器调用失败: $e');
    }
  }

  Future<void> _dispatchVoiceIntent(String intent) async {
    final rk = ref.read(rkClientProvider);
    switch (intent) {
      case 'play':
        await ref.read(audioPlayerProvider.notifier).resume();
        break;
      case 'pause':
      case 'hold':
        await ref.read(audioPlayerProvider.notifier).pause();
        break;
      case 'release':
        await ref.read(audioPlayerProvider.notifier).resume();
        break;
      case 'next':
        await _skipNextInPlan();
        break;
      case 'lift_energy':
        await _skipByEnergy('higher');
        break;
      case 'drop_energy':
        await _skipByEnergy('lower');
        break;
      case 'switch_style':
        await _skipByStyle();
        break;
      case 'loop_last_30s':
        await rk.setLoop(true);
        setState(() => _isLooping = true);
        break;
      case 'loop_off':
        await rk.setLoop(false);
        setState(() => _isLooping = false);
        break;
      case 'emergency_stop':
        await ref.read(audioPlayerProvider.notifier).stop();
        break;
      default:
        _log('MC · 指令未识别 ($intent)');
    }
  }

  @override
  void dispose() {
    if (_voiceListening) {
      _stt.stop();
    }
    if (_hwKeyHandlerRegistered) {
      HardwareKeyboard.instance.removeHandler(_onHardwareKey);
      _hwKeyHandlerRegistered = false;
    }
    super.dispose();
  }

  /// 物理键盘 / OTG 键盘 1~9 快捷键（走全局 HardwareKeyboard，不受 TextField 焦点影响）
  ///   1~5 → DJ 现场音效（RK key 1~5）
  ///   6   → 下一首
  ///   7   → 能量↑ 切歌
  ///   8   → 能量↓ 切歌
  ///   9   → 风格切歌
  bool _onHardwareKey(KeyEvent event) {
    if (event is! KeyDownEvent) return false;
    final k = event.logicalKey;
    final sfxKeys = <LogicalKeyboardKey, ({int rkKey, String localId, String cn, String lab})>{
      LogicalKeyboardKey.digit1: (rkKey: 1, localId: 'scratch',  cn: '搓碟', lab: 'Scratch'),
      LogicalKeyboardKey.digit2: (rkKey: 2, localId: 'air_horn', cn: '气笛', lab: 'Air Horn'),
      LogicalKeyboardKey.digit3: (rkKey: 3, localId: 'spinback', cn: '倒带', lab: 'Spinback'),
      LogicalKeyboardKey.digit4: (rkKey: 4, localId: 'siren',    cn: '警报', lab: 'Siren'),
      LogicalKeyboardKey.digit5: (rkKey: 5, localId: 'whoosh',   cn: '嗖声', lab: 'Whoosh'),
      LogicalKeyboardKey.numpad1: (rkKey: 1, localId: 'scratch',  cn: '搓碟', lab: 'Scratch'),
      LogicalKeyboardKey.numpad2: (rkKey: 2, localId: 'air_horn', cn: '气笛', lab: 'Air Horn'),
      LogicalKeyboardKey.numpad3: (rkKey: 3, localId: 'spinback', cn: '倒带', lab: 'Spinback'),
      LogicalKeyboardKey.numpad4: (rkKey: 4, localId: 'siren',    cn: '警报', lab: 'Siren'),
      LogicalKeyboardKey.numpad5: (rkKey: 5, localId: 'whoosh',   cn: '嗖声', lab: 'Whoosh'),
    };
    final hit = sfxKeys[k];
    if (hit != null) {
      _log('⌨ key=${k.keyLabel} → SFX ${hit.cn}');
      _fireSfx(rkKey: hit.rkKey, localId: hit.localId, label: '${hit.cn} ${hit.lab}');
      return true;
    }
    if (k == LogicalKeyboardKey.digit6 || k == LogicalKeyboardKey.numpad6) {
      _log('⌨ key=6 → 下一首');
      _skipNextInPlan();
      return true;
    }
    if (k == LogicalKeyboardKey.digit7 || k == LogicalKeyboardKey.numpad7) {
      _log('⌨ key=7 → 能量↑');
      _skipByEnergy('higher');
      return true;
    }
    if (k == LogicalKeyboardKey.digit8 || k == LogicalKeyboardKey.numpad8) {
      _log('⌨ key=8 → 能量↓');
      _skipByEnergy('lower');
      return true;
    }
    if (k == LogicalKeyboardKey.digit9 || k == LogicalKeyboardKey.numpad9) {
      _log('⌨ key=9 → 切风格');
      _skipByStyle();
      return true;
    }
    return false;
  }

  void _log(String message) {
    setState(() {
      _logs.insert(0, _LogEntry(DateTime.now(), message));
      if (_logs.length > _maxLogs) {
        _logs.removeRange(_maxLogs, _logs.length);
      }
    });
  }

  String _fmt(double seconds) {
    if (seconds.isNaN || seconds.isInfinite || seconds < 0) seconds = 0;
    final mins = (seconds ~/ 60).toString().padLeft(2, '0');
    final secs = (seconds % 60).toStringAsFixed(0).padLeft(2, '0');
    return '$mins:$secs';
  }
}

class _LogEntry {
  final DateTime time;
  final String message;
  const _LogEntry(this.time, this.message);
  String get timeText {
    final h = time.hour.toString().padLeft(2, '0');
    final m = time.minute.toString().padLeft(2, '0');
    final s = time.second.toString().padLeft(2, '0');
    return '$h:$m:$s';
  }
}

class _WarningBanner extends StatelessWidget {
  final DeviceInfo device;
  const _WarningBanner({required this.device});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final messages = <String>[];
    if (device.isOverheating) {
      messages.add('RK温度过高: ${device.tempC.toStringAsFixed(1)}°C');
    }
    if (device.hasAudioIssues) {
      messages.add('音频XRun: ${device.audioXrunCount}次');
    }
    if (!device.jetsonReachable) messages.add('Jetson 离线');
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(8),
      color: theme.colorScheme.error,
      child: Row(
        children: [
          const Icon(Icons.warning_amber, color: Colors.white, size: 18),
          const SizedBox(width: 6),
          Expanded(
            child: Text(messages.join(' | '),
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }
}
