import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../fangpi/pages/fangpi_page.dart';
import '../../music/pages/music_tags_page.dart';
import '../../playlists/pages/playlists_page.dart';

class ToolsPage extends StatelessWidget {
  const ToolsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('HarBeat Tools')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 180),
          children: [
            Text(
              'Testing Hub',
              style: Theme.of(context).textTheme.displayMedium?.copyWith(
                    fontStyle: FontStyle.italic,
                  ),
            ),
            const SizedBox(height: 10),
            Text(
              'Everything you need to validate import, download, playlist, and catalog tagging workflows.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 24),
            _ToolCard(
              title: 'Fangpi Search & Download',
              subtitle: 'Search, download to library, parse playlist links, and import a playlist.',
              icon: Icons.download_for_offline_outlined,
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const FangpiPage()),
                );
              },
            ),
            const SizedBox(height: 14),
            _ToolCard(
              title: 'Playlists',
              subtitle: 'Create playlists, inspect contents, and add songs from library.',
              icon: Icons.queue_music_outlined,
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const PlaylistsPage()),
                );
              },
            ),
            const SizedBox(height: 14),
            _ToolCard(
              title: 'Catalog Tags & Cues',
              subtitle: 'Search the songs table, edit tags, and manage cue points.',
              icon: Icons.tune_outlined,
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const MusicTagsPage()),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _ToolCard extends StatelessWidget {
  const _ToolCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(28),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(28),
          color: AppColors.surfaceContainerHigh,
        ),
        child: Row(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(18),
                color: AppColors.primary.withValues(alpha: 0.15),
              ),
              child: Icon(icon, color: AppColors.primary),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 8),
                  Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: AppColors.secondary),
          ],
        ),
      ),
    );
  }
}
