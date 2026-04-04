import 'dart:io';

import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/section_title.dart';
import '../../auth/auth_controller.dart';
import '../../library/library_service.dart';
import '../../library/models.dart';
import '../../player/player_controller.dart';

class LibraryPage extends StatefulWidget {
  const LibraryPage({super.key});

  @override
  State<LibraryPage> createState() => _LibraryPageState();
}

class _LibraryPageState extends State<LibraryPage> {
  final _libraryService = LibraryService();
  final _searchController = TextEditingController();

  bool _loading = true;
  bool _busy = false;
  String? _error;
  List<LibrarySong> _songs = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadSongs());
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadSongs({String? query}) async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final songs = (query != null && query.trim().isNotEmpty)
          ? await _libraryService.searchLibrarySongs(query.trim())
          : await _libraryService.getLibrarySongs();
      if (!mounted) return;
      setState(() => _songs = songs);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _analyzeSong(String songId) async {
    setState(() => _busy = true);
    try {
      final updated = await _libraryService.analyzeSong(songId);
      if (!mounted) return;
      setState(() {
        _songs = _songs.map((song) => song.id == songId ? updated : song).toList();
      });
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Analyze failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pickAndUpload() async {
    setState(() => _busy = true);
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: const ['mp3', 'flac', 'wav', 'ogg', 'aac', 'm4a', 'opus', 'wma', 'ncm'],
      );
      if (result == null || result.files.isEmpty || result.files.single.path == null) {
        return;
      }

      final file = File(result.files.single.path!);
      final uploaded = await _libraryService.uploadSong(file: file);
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${uploaded.title} uploaded successfully')),
      );
      await _loadSongs(query: _searchController.text);
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Upload failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final player = context.read<PlayerController>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('HarBeat'),
        actions: [
          IconButton(
            onPressed: _busy ? null : _pickAndUpload,
            icon: const Icon(Icons.upload_file),
          ),
          IconButton(
            onPressed: _busy ? null : () => _loadSongs(query: _searchController.text),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadSongs,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 180),
            children: [
              Text.rich(
                TextSpan(
                  text: 'My\n',
                  style: Theme.of(context).textTheme.displayMedium,
                  children: const [
                    TextSpan(
                      text: 'Library',
                      style: TextStyle(
                        color: AppColors.primary,
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              Text(
                auth.currentUser == null
                    ? 'Local device library'
                    : '@${auth.currentUser!.username} - ${_songs.length} tracks',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 20),
              TextField(
                controller: _searchController,
                onSubmitted: (value) => _loadSongs(query: value),
                decoration: InputDecoration(
                  hintText: 'Search by title or artist',
                  suffixIcon: IconButton(
                    onPressed: () => _loadSongs(query: _searchController.text),
                    icon: const Icon(Icons.search),
                  ),
                ),
              ),
              const SizedBox(height: 24),
              const SectionTitle(title: 'Track List'),
              const SizedBox(height: 16),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 48),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_error != null)
                _StatusCard(
                  title: 'Load Failed',
                  subtitle: _error!,
                )
              else if (_songs.isEmpty)
                const _StatusCard(
                  title: 'No Songs Yet',
                  subtitle: 'Upload or download songs, then your library will appear here.',
                )
              else
                ..._songs.map(
                  (song) => Padding(
                    padding: const EdgeInsets.only(bottom: 14),
                    child: _LibrarySongTile(
                      song: song,
                      busy: _busy,
                      onTap: () async {
                        final token = auth.session?.accessToken;
                        final stemUrls = <String, String>{};
                        for (final stem in const ['vocals', 'drums', 'bass', 'other']) {
                          if ((song.stems ?? {}).containsKey(stem)) {
                            stemUrls[stem] = _libraryService.getStemStreamUrl(song.id, stem, token ?? '');
                          }
                        }
                        await player.setTrack(
                          PlayerTrack(
                            songId: song.id,
                            title: song.title,
                            artist: song.artist,
                            originalUrl: token == null || token.isEmpty
                                ? null
                                : _libraryService.getStreamUrl(song.id, token),
                            stemUrls: token == null || token.isEmpty ? const {} : stemUrls,
                            bpm: song.bpm?.round(),
                          ),
                          play: true,
                        );
                      },
                      onAnalyze: song.analysisStatus == 'completed'
                          ? null
                          : () => _analyzeSong(song.id),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LibrarySongTile extends StatelessWidget {
  const _LibrarySongTile({
    required this.song,
    required this.busy,
    required this.onTap,
    this.onAnalyze,
  });

  final LibrarySong song;
  final bool busy;
  final VoidCallback onTap;
  final VoidCallback? onAnalyze;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
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
                gradient: LinearGradient(
                  colors: [
                    AppColors.primary.withValues(alpha: 0.8),
                    AppColors.secondary.withValues(alpha: 0.8),
                  ],
                ),
              ),
              child: const Icon(Icons.music_note, color: Colors.black),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(song.title, style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Text(
                    '${song.artist}${song.bpm == null ? '' : ' - ${song.bpm!.round()} BPM'}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'status: ${song.analysisStatus}',
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                ],
              ),
            ),
            if (onAnalyze != null)
              IconButton(
                onPressed: busy ? null : onAnalyze,
                icon: const Icon(Icons.auto_awesome),
                color: AppColors.primary,
              )
            else
              const Icon(Icons.check_circle, color: AppColors.success),
          ],
        ),
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({
    required this.title,
    required this.subtitle,
  });

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        color: AppColors.surfaceContainerHigh,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}
