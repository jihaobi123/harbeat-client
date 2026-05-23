import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/services/audio_player_service.dart';

/// 歌曲详情页：展示完整分析结果（BPM/Key/Energy/Beat grid/Cue points/Stems …）
/// 并通过全局 AudioPlayer 播放主轨�?
class SongDetailPage extends ConsumerWidget {
  /// 原始 JSON（来�?`/api/library/songs` 单条 song dict�?
  final Map<String, dynamic> raw;

  const SongDetailPage({super.key, required this.raw});

  String get _libraryId => (raw['id'] ?? '').toString();
  int? get _rkSongId {
    final v = raw['song_id'];
    if (v is int) return v;
    if (v is num) return v.toInt();
    if (v is String) return int.tryParse(v);
    return null;
  }
  String get _title => (raw['title'] ?? '未命名').toString();
  String get _artist => (raw['artist'] ?? '未知艺人').toString();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(audioPlayerProvider);
    final isCurrent = s.songId == _libraryId;

    return Scaffold(
      appBar: AppBar(title: const Text('歌曲详情')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _header(context),
          const SizedBox(height: 16),
          _playerCard(context, ref, s, isCurrent),
          const SizedBox(height: 16),
          _analysisGrid(context),
          const SizedBox(height: 16),
          _cuePoints(context, ref, isCurrent),
          const SizedBox(height: 16),
          _beatGrid(context),
          const SizedBox(height: 16),
          _stemsCard(context),
          const SizedBox(height: 16),
          _tagsCard(context),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  Widget _header(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 80,
          height: 80,
          decoration: BoxDecoration(
            gradient: LinearGradient(colors: [
              Theme.of(context).primaryColor,
              Theme.of(context).primaryColor.withOpacity(0.7),
            ]),
            borderRadius: BorderRadius.circular(12),
          ),
          child: const Icon(Icons.music_note, color: Colors.white, size: 40),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_title,
                  style: const TextStyle(
                      fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 4),
              Text(_artist,
                  style: TextStyle(fontSize: 14, color: Colors.grey[600])),
              const SizedBox(height: 4),
              Text(
                '时长 ${_fmtSec(_asDouble(raw['duration']))}'
                ' · ${(raw['format'] ?? '').toString().toUpperCase()}',
                style: TextStyle(fontSize: 12, color: Colors.grey[500]),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _playerCard(
      BuildContext context, WidgetRef ref, AudioPlaybackState s, bool isCurrent) {
    final pos = isCurrent ? s.position : Duration.zero;
    final dur = isCurrent && s.duration > Duration.zero
        ? s.duration
        : Duration(milliseconds: ((_asDouble(raw['duration']) ?? 0) * 1000).round());
    final progress = (dur.inMilliseconds > 0)
        ? (pos.inMilliseconds / dur.inMilliseconds).clamp(0.0, 1.0)
        : 0.0;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              children: [
                Text(_fmt(pos), style: const TextStyle(fontSize: 12)),
                Expanded(
                  child: Slider(
                    value: progress,
                    onChanged: isCurrent
                        ? (v) {
                            final to = Duration(
                                milliseconds:
                                    (dur.inMilliseconds * v).round());
                            ref
                                .read(audioPlayerProvider.notifier)
                                .seek(to);
                          }
                        : null,
                  ),
                ),
                Text(_fmt(dur), style: const TextStyle(fontSize: 12)),
              ],
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                IconButton(
                  iconSize: 36,
                  icon: const Icon(Icons.replay_10),
                  onPressed: isCurrent
                      ? () {
                          final to = pos - const Duration(seconds: 10);
                          ref.read(audioPlayerProvider.notifier).seek(
                              to.isNegative ? Duration.zero : to);
                        }
                      : null,
                ),
                const SizedBox(width: 8),
                IconButton(
                  iconSize: 56,
                  icon: Icon(
                    (isCurrent && s.playing)
                        ? Icons.pause_circle_filled
                        : Icons.play_circle_filled,
                    color: Theme.of(context).primaryColor,
                  ),
                  onPressed: (isCurrent && s.loading)
                      ? null
                      : () async {
                          final notifier =
                              ref.read(audioPlayerProvider.notifier);
                          if (isCurrent) {
                            await notifier.toggle();
                          } else {
                            await notifier.play(
                              songId: _libraryId,
                              rkSongId: _rkSongId,
                              title: _title,
                              artist: _artist,
                              durationSec: _asDouble(raw['duration']),
                            );
                          }
                        },
                ),
                const SizedBox(width: 8),
                IconButton(
                  iconSize: 36,
                  icon: const Icon(Icons.forward_10),
                  onPressed: isCurrent
                      ? () {
                          final to = pos + const Duration(seconds: 10);
                          ref.read(audioPlayerProvider.notifier).seek(
                              to > dur ? dur : to);
                        }
                      : null,
                ),
              ],
            ),
            if (isCurrent && s.loading)
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: LinearProgressIndicator(minHeight: 2),
              ),
            if (isCurrent && s.caching)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '正在缓存到 RK3588: ${s.cacheStage ?? ""} ${s.cachePercent.toStringAsFixed(0)}%',
                      style: const TextStyle(fontSize: 12),
                    ),
                    const SizedBox(height: 4),
                    LinearProgressIndicator(
                      value: s.cachePercent / 100.0,
                      minHeight: 4,
                    ),
                  ],
                ),
              ),
            if (isCurrent && s.errorMessage != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: Colors.red.withOpacity(0.3)),
                  ),
                  child: Text(
                    s.errorMessage!,
                    style: const TextStyle(
                        color: Colors.red, fontSize: 12),
                  ),
                ),
              ),
            if (isCurrent && s.stemName != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Chip(
                  label: Text('当前分轨: ${s.stemName}',
                      style: const TextStyle(fontSize: 11)),
                  backgroundColor: Colors.purple.withOpacity(0.1),
                  visualDensity: VisualDensity.compact,
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _analysisGrid(BuildContext context) {
    final bpm = _asDouble(raw['bpm']);
    final key = (raw['key'] ?? '').toString();
    final camelot = (raw['camelot_key'] ?? '').toString();
    final energy = _asDouble(raw['energy']);
    final status = (raw['analysis_status'] ?? '').toString();
    final beatCount = (raw['beat_points'] as List?)?.length ?? 0;
    final cueCount = (raw['cue_points'] as List?)?.length ?? 0;

    final items = <Widget>[
      _statTile(context, 'BPM', bpm == null ? '--' : bpm.toStringAsFixed(1),
          Icons.speed, Colors.blue),
      _statTile(context, 'Key', key.isEmpty ? '--' : key,
          Icons.piano, Colors.purple),
      _statTile(context, 'Camelot', camelot.isEmpty ? '--' : camelot,
          Icons.timeline, Colors.deepPurple),
      _statTile(
          context,
          'Energy',
          energy == null ? '--' : energy.toStringAsFixed(2),
          Icons.bolt,
          _energyColor(energy)),
      _statTile(context, '节拍数', '$beatCount',
          Icons.graphic_eq, Colors.teal),
      _statTile(
          context, '段落数', '$cueCount', Icons.bookmark, Colors.orange),
      _statTile(
          context,
          '分析',
          status.isEmpty ? '--' : status,
          status == 'completed' ? Icons.check_circle : Icons.hourglass_top,
          status == 'completed' ? Colors.green : Colors.amber),
      _statTile(
          context,
          '大小',
          _fmtBytes(raw['file_size']),
          Icons.storage,
          Colors.blueGrey),
    ];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 4, vertical: 4),
              child: Text('🎵 音乐特征',
                  style:
                      TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
            ),
            const SizedBox(height: 4),
            GridView.count(
              crossAxisCount: 4,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              childAspectRatio: 0.95,
              children: items,
            ),
          ],
        ),
      ),
    );
  }

  Widget _statTile(BuildContext context, String label, String value,
      IconData icon, Color color) {
    return Container(
      margin: const EdgeInsets.all(4),
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 2),
          Text(value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  fontSize: 13, fontWeight: FontWeight.bold)),
          Text(label,
              style: TextStyle(fontSize: 10, color: Colors.grey[600])),
        ],
      ),
    );
  }

  Widget _cuePoints(BuildContext context, WidgetRef ref, bool isCurrent) {
    final cues = (raw['cue_points'] as List?) ?? const [];
    if (cues.isEmpty) {
      return const SizedBox.shrink();
    }
    final total = _asDouble(raw['duration']) ?? 0;
    // 构造段落区间：每段 = [start, nextStart 或 total]
    final segments = <Map<String, dynamic>>[];
    final sorted = cues.whereType<Map>().toList()
      ..sort((a, b) => (_asDouble(a['time']) ?? 0)
          .compareTo(_asDouble(b['time']) ?? 0));
    for (var i = 0; i < sorted.length; i++) {
      final start = _asDouble(sorted[i]['time']) ?? 0;
      final end = (i + 1 < sorted.length)
          ? (_asDouble(sorted[i + 1]['time']) ?? total)
          : total;
      segments.add({
        'start': start,
        'end': end,
        'label': sorted[i]['label']?.toString() ?? '',
        'color': _parseHex((sorted[i]['color'] ?? '#888888').toString()),
      });
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('🔖 段落结构 · ${segments.length} 段',
                style: const TextStyle(
                    fontSize: 14, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            if (total > 0)
              SizedBox(
                height: 28,
                child: LayoutBuilder(builder: (ctx, c) {
                  final w = c.maxWidth;
                  return Stack(children: [
                    for (final seg in segments)
                      Positioned(
                        left: ((seg['start'] as double) / total) * w,
                        width: (((seg['end'] as double) -
                                    (seg['start'] as double)) /
                                total) *
                            w,
                        top: 0,
                        bottom: 0,
                        child: GestureDetector(
                          onTap: () async {
                            final notifier =
                                ref.read(audioPlayerProvider.notifier);
                            if (!isCurrent) {
                              await notifier.play(
                                songId: _libraryId,
                                rkSongId: _rkSongId,
                                title: _title,
                                artist: _artist,
                                durationSec: _asDouble(raw['duration']),
                              );
                            }
                            await notifier.seek(Duration(
                                milliseconds:
                                    ((seg['start'] as double) * 1000).round()));
                          },
                          child: Container(
                            margin:
                                const EdgeInsets.symmetric(horizontal: 1),
                            decoration: BoxDecoration(
                              color: (seg['color'] as Color).withOpacity(0.7),
                              borderRadius: BorderRadius.circular(3),
                            ),
                            child: Center(
                              child: Text(
                                seg['label'] as String,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontSize: 10,
                                  color: Colors.white,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                  ]);
                }),
              ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: segments.map((seg) {
                return ActionChip(
                  avatar: CircleAvatar(
                      backgroundColor: seg['color'] as Color, radius: 6),
                  label: Text(
                      '${seg['label']} · ${_fmtSec(seg['start'] as double)}'),
                  onPressed: () async {
                    final notifier = ref.read(audioPlayerProvider.notifier);
                    if (!isCurrent) {
                      await notifier.play(
                        songId: _libraryId,
                        rkSongId: _rkSongId,
                        title: _title,
                        artist: _artist,
                        durationSec: _asDouble(raw['duration']),
                      );
                    }
                    await notifier.seek(Duration(
                        milliseconds:
                            ((seg['start'] as double) * 1000).round()));
                  },
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _beatGrid(BuildContext context) {
    final beats = (raw['beat_points'] as List?) ?? const [];
    if (beats.isEmpty) return const SizedBox.shrink();
    final total = _asDouble(raw['duration']) ?? 0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '🎯 Beat Grid · ${beats.length} 拍',
              style: const TextStyle(
                  fontSize: 14, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 36,
              child: LayoutBuilder(
                builder: (ctx, c) {
                  final w = c.maxWidth;
                  return Stack(children: [
                    Container(
                      decoration: BoxDecoration(
                        color: Colors.grey.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                    ...beats.whereType<num>().map((t) {
                      final x = total > 0 ? (t / total) * w : 0.0;
                      return Positioned(
                        left: x.clamp(0.0, w),
                        top: 4,
                        bottom: 4,
                        child: Container(
                          width: 1,
                          color: Colors.blue.withOpacity(0.6),
                        ),
                      );
                    }),
                  ]);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _stemsCard(BuildContext context) {
    final stems = raw['stems'];
    if (stems is! Map || stems.isEmpty) return const SizedBox.shrink();
    final names = ['vocals', 'drums', 'bass', 'other'];
    final emoji = {
      'vocals': '🎤',
      'drums': '🥁',
      'bass': '🎸',
      'other': '🎹',
    };
    return Consumer(builder: (ctx, ref, _) {
      final s = ref.watch(audioPlayerProvider);
      final isCurrent = s.songId == _libraryId;
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('🎛 音轨分离 (Stems)',
                  style: TextStyle(
                      fontSize: 14, fontWeight: FontWeight.bold)),
              const SizedBox(height: 6),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.equalizer, size: 16),
                      label: const Text('主轨（全部音轨）'),
                      style: OutlinedButton.styleFrom(
                        backgroundColor:
                            (isCurrent && s.stemName == null)
                                ? Theme.of(context)
                                    .primaryColor
                                    .withOpacity(0.15)
                                : null,
                      ),
                      onPressed: () async {
                        final notifier =
                            ref.read(audioPlayerProvider.notifier);
                        if (!isCurrent) {
                          await notifier.play(
                            songId: _libraryId,
                            rkSongId: _rkSongId,
                            title: _title,
                            artist: _artist,
                            durationSec: _asDouble(raw['duration']),
                          );
                        }
                        await notifier.setStemSolo(null);
                      },
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              ...names.where((n) => stems[n] != null).map((n) {
                final active = isCurrent && s.stemName == n;
                return ListTile(
                  dense: true,
                  visualDensity: VisualDensity.compact,
                  leading: Text(emoji[n] ?? '🎵',
                      style: const TextStyle(fontSize: 22)),
                  title: Text(n,
                      style: TextStyle(
                          fontWeight: active
                              ? FontWeight.bold
                              : FontWeight.normal,
                          color: active
                              ? Theme.of(context).primaryColor
                              : null)),
                  subtitle: Text(active ? '正在独奏（其它轨已静音）' : '点击仅播放此轨',
                      style: const TextStyle(fontSize: 11, color: Colors.grey)),
                  trailing: Icon(
                    active ? Icons.headset : Icons.play_circle_outline,
                    color: active
                        ? Theme.of(context).primaryColor
                        : Colors.grey,
                    size: 22,
                  ),
                  onTap: () async {
                    final notifier =
                        ref.read(audioPlayerProvider.notifier);
                    if (!isCurrent) {
                      await notifier.play(
                        songId: _libraryId,
                        rkSongId: _rkSongId,
                        title: _title,
                        artist: _artist,
                        durationSec: _asDouble(raw['duration']),
                      );
                    }
                    await notifier.setStemSolo(active ? null : n);
                  },
                );
              }),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                child: Text(
                  '提示：开启独奏后会持续静音其它轨，再次点击同一轨即可恢复主轨。',
                  style: TextStyle(fontSize: 11, color: Colors.grey),
                ),
              ),
            ],
          ),
        ),
      );
    });
  }

  Widget _tagsCard(BuildContext context) {
    final danceStyles = (raw['dance_styles'] as List?) ?? const [];
    final genres = (raw['genres'] as List?) ?? const [];
    final source = (raw['source_type'] ?? '').toString();
    if (danceStyles.isEmpty && genres.isEmpty && source.isEmpty) {
      return const SizedBox.shrink();
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('🏷 标签',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                if (source.isNotEmpty)
                  _tag('来源: $source', Colors.blueGrey),
                ...danceStyles
                    .map((s) => _tag(s.toString(), Colors.deepOrange)),
                ...genres.map((g) => _tag(g.toString(), Colors.indigo)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _tag(String label, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          border: Border.all(color: color.withOpacity(0.5)),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(label,
            style: TextStyle(
                fontSize: 11, color: color, fontWeight: FontWeight.w600)),
      );

  // ───── helpers ─────
  static double? _asDouble(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }

  static String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  static String _fmtSec(double? sec) {
    if (sec == null || sec <= 0) return '--:--';
    final m = (sec ~/ 60).toString().padLeft(2, '0');
    final s = (sec % 60).toInt().toString().padLeft(2, '0');
    return '$m:$s';
  }

  static String _fmtBytes(dynamic v) {
    final b = (v is num) ? v.toDouble() : double.tryParse(v?.toString() ?? '');
    if (b == null) return '--';
    if (b < 1024) return '${b.toInt()} B';
    if (b < 1024 * 1024) return '${(b / 1024).toStringAsFixed(1)} KB';
    return '${(b / 1024 / 1024).toStringAsFixed(2)} MB';
  }

  static Color _energyColor(double? e) {
    if (e == null) return Colors.grey;
    if (e < 0.4) return Colors.green;
    if (e < 0.7) return Colors.orange;
    return Colors.red;
  }

  static Color _parseHex(String hex) {
    var v = hex.replaceFirst('#', '');
    if (v.length == 6) v = 'FF$v';
    final n = int.tryParse(v, radix: 16);
    return n == null ? Colors.grey : Color(n);
  }
}
