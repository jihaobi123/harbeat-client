import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/section_title.dart';
import '../../auth/auth_controller.dart';
import '../../library/library_service.dart';
import '../../player/player_controller.dart';
import '../models.dart';
import '../recommendations_service.dart';

class DiscoverPage extends StatefulWidget {
  const DiscoverPage({super.key});

  @override
  State<DiscoverPage> createState() => _DiscoverPageState();
}

class _DiscoverPageState extends State<DiscoverPage> {
  final _service = RecommendationsService();
  final _libraryService = LibraryService();

  bool _loading = true;
  bool _busy = false;
  String? _error;
  List<DiscoverSectionModel> _sections = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadDiscover());
  }

  Future<void> _loadDiscover() async {
    final userId = context.read<AuthController>().session?.userId;
    if (userId == null || userId <= 0) {
      setState(() {
        _loading = false;
        _error = 'Please login again to load personalized discovery.';
      });
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final sections = await _service.discoverSongs(userId);
      if (!mounted) return;
      setState(() => _sections = sections);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _addToLibrary(DiscoverSongItem song) async {
    final userId = context.read<AuthController>().session?.userId;
    final player = context.read<PlayerController>();
    if (userId == null || userId <= 0) return;

    setState(() => _busy = true);
    try {
      final added = await _service.addSongToLibrary(userId, song.songId);
      if (!mounted) return;
      setState(() {
        _sections = _sections
            .map(
              (section) => DiscoverSectionModel(
                key: section.key,
                title: section.title,
                icon: section.icon,
                description: section.description,
                songs: section.songs
                    .map(
                      (item) => item.songId == song.songId
                          ? DiscoverSongItem(
                              songId: item.songId,
                              title: item.title,
                              artist: item.artist,
                              style: item.style,
                              energy: item.energy,
                              inLibrary: true,
                            )
                          : item,
                    )
                    .toList(),
              ),
            )
            .toList();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${song.title} added to library')),
      );
      final token = context.read<AuthController>().session?.accessToken;
      if (token != null && token.isNotEmpty) {
        final librarySong = await _libraryService.getLibrarySong(added.librarySongId);
        if (!mounted) return;
        await player.setTrack(
          PlayerTrack(
            songId: librarySong.id,
            title: librarySong.title,
            artist: librarySong.artist,
            originalUrl: _libraryService.getStreamUrl(librarySong.id, token),
            stemUrls: _libraryService.buildStemUrls(librarySong, token),
            bpm: librarySong.bpm?.round(),
          ),
          play: true,
        );
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Add failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _playDiscoverSong(DiscoverSongItem song) async {
    final auth = context.read<AuthController>();
    final player = context.read<PlayerController>();
    final token = auth.session?.accessToken;
    if (token == null || token.isEmpty) return;

    if (!song.inLibrary) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add this track to your library before playback.')),
      );
      return;
    }

    try {
      final librarySong = await _libraryService.findExactLibrarySong(
        title: song.title,
        artist: song.artist,
      );
      if (librarySong == null) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Track marked in library but no local file was found.')),
        );
        return;
      }

      await player.setTrack(
        PlayerTrack(
          songId: librarySong.id,
          title: librarySong.title,
          artist: librarySong.artist,
          originalUrl: _libraryService.getStreamUrl(librarySong.id, token),
          stemUrls: _libraryService.buildStemUrls(librarySong, token),
          bpm: librarySong.bpm?.round(),
        ),
        play: true,
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Playback failed: $error')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('HarBeat'),
        actions: [
          IconButton(
            onPressed: _busy ? null : _loadDiscover,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadDiscover,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 180),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Guess You Like',
                      style: Theme.of(context).textTheme.displayMedium?.copyWith(
                            fontStyle: FontStyle.italic,
                          ),
                    ),
                  ),
                  Text(
                    'SLIDE FOR VIBE',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: AppColors.secondary,
                        ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 48),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_error != null)
                _DiscoverStatusCard(message: _error!)
              else if (_sections.isEmpty)
                const _DiscoverStatusCard(message: 'No discovery data available yet.')
              else ...[
                if (_sections.isNotEmpty)
                  SizedBox(
                    height: 320,
                    child: ListView.separated(
                      scrollDirection: Axis.horizontal,
                      itemBuilder: (context, index) {
                        final section = _sections[index];
                        final featured = section.songs.isNotEmpty ? section.songs.first : null;
                        if (featured == null) return const SizedBox.shrink();
                        return _HeroCard(
                          title: featured.title,
                          subtitle: featured.artist,
                          badge: featured.energy ?? section.title,
                          onPlay: () => _playDiscoverSong(featured),
                        );
                      },
                      separatorBuilder: (_, __) => const SizedBox(width: 16),
                      itemCount: _sections.length.clamp(0, 5),
                    ),
                  ),
                const SizedBox(height: 28),
                ..._sections.map((section) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 28),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SectionTitle(title: section.title),
                        const SizedBox(height: 6),
                        Text(section.description, style: Theme.of(context).textTheme.bodySmall),
                        const SizedBox(height: 14),
                        ...section.songs.map(
                          (song) => Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: _DiscoverSongTile(
                              song: song,
                              busy: _busy,
                              onPlay: () => _playDiscoverSong(song),
                              onAdd: song.inLibrary ? null : () => _addToLibrary(song),
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                }),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _HeroCard extends StatelessWidget {
  const _HeroCard({
    required this.title,
    required this.subtitle,
    required this.badge,
    required this.onPlay,
  });

  final String title;
  final String subtitle;
  final String badge;
  final VoidCallback onPlay;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 292,
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        gradient: const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF362047), Color(0xFF11111A)],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: AppColors.primary,
              borderRadius: BorderRadius.circular(999),
            ),
            child: Text(
              badge.toUpperCase(),
              style: const TextStyle(color: Colors.black, fontWeight: FontWeight.w900),
            ),
          ),
          const Spacer(),
          Text(title, style: Theme.of(context).textTheme.displayMedium),
          const SizedBox(height: 6),
          Text(subtitle, style: Theme.of(context).textTheme.bodyMedium),
          const SizedBox(height: 18),
          FilledButton.icon(
            onPressed: onPlay,
            icon: const Icon(Icons.play_arrow),
            label: const Text('DROP IN'),
          ),
        ],
      ),
    );
  }
}

class _DiscoverSongTile extends StatelessWidget {
  const _DiscoverSongTile({
    required this.song,
    required this.busy,
    required this.onPlay,
    this.onAdd,
  });

  final DiscoverSongItem song;
  final bool busy;
  final VoidCallback onPlay;
  final VoidCallback? onAdd;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPlay,
      borderRadius: BorderRadius.circular(22),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(22),
          color: AppColors.surfaceContainerHigh,
        ),
        child: Row(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                color: AppColors.surfaceContainerHighest,
              ),
              child: const Icon(Icons.graphic_eq, color: AppColors.primary),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(song.title, style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Text(song.artist, style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 6),
                  Text(
                    '${song.style ?? 'unknown'}${song.energy == null ? '' : ' - ${song.energy}'}',
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                ],
              ),
            ),
            IconButton(
              onPressed: onAdd == null || busy ? null : onAdd,
              icon: Icon(
                onAdd == null ? Icons.check_circle : Icons.add_circle_outline,
                color: onAdd == null ? AppColors.success : AppColors.primary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DiscoverStatusCard extends StatelessWidget {
  const _DiscoverStatusCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        color: AppColors.surfaceContainerHigh,
      ),
      child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
    );
  }
}
