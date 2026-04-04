import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/glass_panel.dart';
import '../pages/player_page.dart';
import '../player_controller.dart';

class MiniPlayer extends StatelessWidget {
  const MiniPlayer({super.key});

  @override
  Widget build(BuildContext context) {
    final player = context.watch<PlayerController>();

    if (!player.hasTrack) {
      return const SizedBox.shrink();
    }

    final track = player.currentTrack!;
    final duration = player.duration;
    final progress = duration == null || duration.inMilliseconds <= 0
        ? 0.0
        : (player.position.inMilliseconds / duration.inMilliseconds).clamp(0.0, 1.0);

    return InkWell(
      borderRadius: BorderRadius.circular(24),
      onTap: () {
        Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => const PlayerPage()),
        );
      },
      child: GlassPanel(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    gradient: const LinearGradient(
                      colors: [AppColors.primary, AppColors.secondary],
                    ),
                  ),
                  child: const Icon(Icons.music_note, color: Colors.black),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        track.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${track.artist}${track.bpm == null ? '' : ' - ${track.bpm} BPM'}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      if (player.errorMessage != null) ...[
                        const SizedBox(height: 4),
                        Text(
                          'Playback error',
                          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                color: Colors.redAccent,
                              ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (player.isLoading || player.isBuffering)
                  const SizedBox(
                    width: 28,
                    height: 28,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                else
                  IconButton(
                    onPressed: player.hasPlayableSource ? player.togglePlayback : null,
                    icon: Icon(
                      player.isPlaying ? Icons.pause_circle_filled : Icons.play_circle_fill,
                      color: player.hasPlayableSource ? AppColors.primary : AppColors.onSurfaceVariant,
                      size: 34,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            LinearProgressIndicator(
              minHeight: 4,
              value: progress,
              color: AppColors.primary,
              backgroundColor: AppColors.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(999),
            ),
          ],
        ),
      ),
    );
  }
}
