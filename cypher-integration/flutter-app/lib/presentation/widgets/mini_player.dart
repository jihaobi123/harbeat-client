import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/services/audio_player_service.dart';

/// 全局底部 Mini-Player（带�?LibraryPage 底部）�?
class MiniPlayer extends ConsumerWidget {
  final VoidCallback? onTap;
  const MiniPlayer({super.key, this.onTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(audioPlayerProvider);
    if (s.songId == null) return const SizedBox.shrink();

    final p = s.position;
    final d = s.duration;
    final progress = (d.inMilliseconds > 0)
        ? (p.inMilliseconds / d.inMilliseconds).clamp(0.0, 1.0)
        : 0.0;

    return Material(
      elevation: 4,
      color: Theme.of(context).colorScheme.surface,
      child: InkWell(
        onTap: onTap,
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                LinearProgressIndicator(value: progress, minHeight: 2),
                const SizedBox(height: 4),
                Row(
                  children: [
                    const Icon(Icons.music_note, size: 28),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            s.title ?? '未知歌曲',
                            style: const TextStyle(
                                fontSize: 14, fontWeight: FontWeight.w600),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          Text(
                            s.artist ?? '',
                            style: TextStyle(
                                fontSize: 12, color: Colors.grey[600]),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                    Text(
                      '${_fmt(p)} / ${_fmt(d)}',
                      style: const TextStyle(fontSize: 11),
                    ),
                    IconButton(
                      icon: Icon(s.playing ? Icons.pause : Icons.play_arrow),
                      onPressed: s.loading
                          ? null
                          : () => ref
                              .read(audioPlayerProvider.notifier)
                              .toggle(),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () =>
                          ref.read(audioPlayerProvider.notifier).stop(),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  static String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }
}
