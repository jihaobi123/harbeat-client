import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/glass_panel.dart';
import '../../auth/auth_controller.dart';
import '../../library/library_service.dart';
import '../player_controller.dart';

class PlayerPage extends StatefulWidget {
  const PlayerPage({super.key});

  @override
  State<PlayerPage> createState() => _PlayerPageState();
}

class _PlayerPageState extends State<PlayerPage> {
  final _libraryService = LibraryService();
  bool _generatingStems = false;

  Future<void> _generateStems() async {
    final player = context.read<PlayerController>();
    final auth = context.read<AuthController>();
    final track = player.currentTrack;
    final token = auth.session?.accessToken;
    if (track?.songId == null || token == null || token.isEmpty) return;

    setState(() => _generatingStems = true);
    try {
      await _libraryService.separateStems(track!.songId!);
      final stemUrls = {
        for (final stem in const ['vocals', 'drums', 'bass', 'other'])
          stem: _libraryService.getStemStreamUrl(track.songId!, stem, token),
      };
      player.updateStemUrls(stemUrls);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Stem files are ready.')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Stem generation failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _generatingStems = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final player = context.watch<PlayerController>();
    final track = player.currentTrack;
    final isOriginal = player.activeSource == 'original';
    final statusText = player.isLoading || player.isBuffering
        ? 'Buffering'
        : player.isPlaying
            ? 'Playing'
            : 'Paused';

    return Scaffold(
      appBar: AppBar(title: const Text('Now Playing')),
      body: track == null
          ? const Center(child: Text('No track selected yet.'))
          : SafeArea(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 40),
                children: [
                  GlassPanel(
                    padding: const EdgeInsets.all(24),
                    borderRadius: 32,
                    child: Column(
                      children: [
                        Container(
                          width: double.infinity,
                          height: 320,
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(28),
                            gradient: const LinearGradient(
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                              colors: [Color(0xFF232A4B), Color(0xFF0B0B12)],
                            ),
                          ),
                          child: Stack(
                            alignment: Alignment.center,
                            children: [
                              const Icon(
                                Icons.graphic_eq_rounded,
                                size: 120,
                                color: AppColors.primary,
                              ),
                              Positioned(
                                top: 16,
                                right: 16,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(999),
                                    color: Colors.black.withValues(alpha: 0.35),
                                  ),
                                  child: Text(
                                    statusText.toUpperCase(),
                                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                          color: AppColors.primary,
                                        ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 24),
                        Text(
                          track.title,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.displaySmall,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '${track.artist}${track.bpm == null ? '' : ' - ${track.bpm} BPM'}',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                        const SizedBox(height: 24),
                        Wrap(
                          alignment: WrapAlignment.center,
                          spacing: 10,
                          runSpacing: 10,
                          children: [
                            _InfoChip(
                              icon: Icons.album_outlined,
                              label: isOriginal ? 'Original Mix' : player.activeSource.toUpperCase(),
                            ),
                            _InfoChip(
                              icon: Icons.speed_outlined,
                              label: track.bpm == null ? '-- BPM' : '${track.bpm} BPM',
                            ),
                            _InfoChip(
                              icon: Icons.network_check_outlined,
                              label: track.songId == null ? 'Preview' : 'Streaming',
                            ),
                          ],
                        ),
                        const SizedBox(height: 20),
                        SliderTheme(
                          data: SliderTheme.of(context).copyWith(
                            activeTrackColor: AppColors.primary,
                            inactiveTrackColor: AppColors.surfaceContainerHighest,
                            thumbColor: AppColors.primary,
                            overlayColor: AppColors.primary.withValues(alpha: 0.15),
                          ),
                          child: Slider(
                            min: 0,
                            max: (player.duration?.inMilliseconds ?? 1).toDouble(),
                            value: player.position.inMilliseconds
                                .clamp(0, player.duration?.inMilliseconds ?? 1)
                                .toDouble(),
                            onChanged: (value) => player.seek(Duration(milliseconds: value.round())),
                          ),
                        ),
                        Row(
                          children: [
                            Text(_formatDuration(player.position)),
                            const Spacer(),
                            Text(_formatDuration(player.duration ?? Duration.zero)),
                          ],
                        ),
                        const SizedBox(height: 24),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            _ControlButton(
                              icon: Icons.stop_circle_outlined,
                              onPressed: player.stop,
                            ),
                            const SizedBox(width: 16),
                            _ControlButton(
                              icon: player.isPlaying
                                  ? Icons.pause_circle_filled
                                  : Icons.play_circle_fill,
                              filled: true,
                              onPressed: player.hasPlayableSource ? player.togglePlayback : null,
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 28),
                  Row(
                    children: [
                      const Expanded(child: Text('Playback Source', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700))),
                      if (track.songId != null)
                        TextButton(
                          onPressed: _generatingStems ? null : _generateStems,
                          child: Text(_generatingStems ? 'Generating...' : 'Generate Stems'),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: player.availableSources.map((source) {
                      final selected = source == player.activeSource;
                      return ChoiceChip(
                        label: Text(source.toUpperCase()),
                        selected: selected,
                        onSelected: (_) => player.switchSource(source),
                      );
                    }).toList(),
                  ),
                  if (player.errorMessage != null) ...[
                    const SizedBox(height: 20),
                    Text(
                      player.errorMessage!,
                      style: const TextStyle(color: Colors.redAccent),
                    ),
                  ],
                  const SizedBox(height: 24),
                  GlassPanel(
                    padding: const EdgeInsets.all(18),
                    borderRadius: 24,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Track Notes',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        const SizedBox(height: 10),
                        Text(
                          'Lyrics are not available from the current backend yet, so this section acts as a live notes area for testing playback context. You can use it to validate UI spacing, long text rendering, and later replace it with real lyrics or track commentary.',
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({
    required this.icon,
    required this.label,
  });

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: AppColors.surfaceContainerHighest,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: AppColors.secondary),
          const SizedBox(width: 6),
          Text(label, style: Theme.of(context).textTheme.labelLarge),
        ],
      ),
    );
  }
}

class _ControlButton extends StatelessWidget {
  const _ControlButton({
    required this.icon,
    required this.onPressed,
    this.filled = false,
  });

  final IconData icon;
  final VoidCallback? onPressed;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final child = Icon(icon, size: filled ? 64 : 42);
    if (filled) {
      return IconButton(
        onPressed: onPressed,
        icon: child,
        color: AppColors.primary,
      );
    }

    return IconButton(
      onPressed: onPressed,
      icon: child,
      color: AppColors.onSurfaceVariant,
    );
  }
}
