import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../auth/auth_controller.dart';
import '../../library/library_service.dart';
import '../../player/player_controller.dart';
import '../../playlists/playlists_service.dart';
import '../fangpi_service.dart';
import '../models.dart';

class FangpiPage extends StatefulWidget {
  const FangpiPage({super.key});

  @override
  State<FangpiPage> createState() => _FangpiPageState();
}

class _FangpiPageState extends State<FangpiPage> {
  final _fangpiService = FangpiService();
  final _libraryService = LibraryService();
  final _playlistsService = PlaylistsService();
  final _searchController = TextEditingController();
  final _playlistUrlController = TextEditingController();

  bool _searching = false;
  bool _parsing = false;
  bool _downloading = false;
  bool _batchSearching = false;
  List<FangpiSong> _results = [];
  ParsedPlaylist? _parsedPlaylist;
  List<BatchSearchResultItem> _batchResults = [];
  final Map<String, BatchSearchCandidate> _selectedCandidates = {};
  String? _error;

  @override
  void dispose() {
    _searchController.dispose();
    _playlistUrlController.dispose();
    super.dispose();
  }

  Future<void> _search() async {
    final query = _searchController.text.trim();
    if (query.isEmpty) return;
    setState(() {
      _searching = true;
      _error = null;
    });
    try {
      final results = await _fangpiService.search(query);
      if (!mounted) return;
      setState(() => _results = results);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _downloadSong(FangpiSong song) async {
    final auth = context.read<AuthController>();
    final token = auth.session?.accessToken;
    setState(() => _downloading = true);
    try {
      final librarySong = await _fangpiService.download({
        'music_id': song.id,
        'title': song.title,
        'artist': song.artist,
        'source': song.source ?? 'fangpi',
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${song.title} downloaded to library')),
      );
      if (token != null && token.isNotEmpty) {
        await context.read<PlayerController>().setTrack(
          PlayerTrack(
            songId: librarySong.id,
            title: librarySong.title,
            artist: librarySong.artist,
            originalUrl: _libraryService.getStreamUrl(librarySong.id, token),
            bpm: librarySong.bpm?.round(),
          ),
          play: true,
        );
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Download failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  Future<void> _parsePlaylist() async {
    final url = _playlistUrlController.text.trim();
    if (url.isEmpty) return;
    setState(() {
      _parsing = true;
      _error = null;
    });
    try {
      final parsed = await _fangpiService.parsePlaylistUrl(url);
      if (!mounted) return;
      setState(() => _parsedPlaylist = parsed);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _parsing = false);
    }
  }

  Future<void> _importParsedPlaylist() async {
    final auth = context.read<AuthController>();
    final userId = auth.currentUser?.id;
    final parsed = _parsedPlaylist;
    if (userId == null || parsed == null) return;

    setState(() => _downloading = true);
    try {
      await _playlistsService.importPlaylist(
        userId: userId,
        playlistName: parsed.name,
        sourceType: parsed.platform,
        songs: parsed.tracks
            .map((track) => {
                  'title': track.title,
                  'artist': track.artist,
                  'duration': track.duration.toDouble(),
                  'tags': <String>[],
                })
            .toList(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Playlist "${parsed.name}" imported')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Import failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  Future<void> _batchMatchParsedPlaylist() async {
    final parsed = _parsedPlaylist;
    if (parsed == null) return;
    setState(() {
      _batchSearching = true;
      _error = null;
      _batchResults = [];
      _selectedCandidates.clear();
    });
    try {
      final results = await _fangpiService.batchSearch(
        parsed.tracks
            .map((track) => {'title': track.title, 'artist': track.artist})
            .toList(),
      );
      if (!mounted) return;
      setState(() {
        _batchResults = results;
        for (final result in results) {
          if (result.candidates.isNotEmpty) {
            _selectedCandidates['${result.title}::${result.artist}'] = result.candidates.first;
          }
        }
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _batchSearching = false);
    }
  }

  Future<void> _downloadMatchedBatch() async {
    if (_selectedCandidates.isEmpty) return;
    setState(() => _downloading = true);
    try {
      for (final entry in _selectedCandidates.values) {
        await _fangpiService.download({
          'music_id': entry.id,
          'title': entry.title,
          'artist': entry.artist,
          'source': entry.source ?? 'fangpi',
        });
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Downloaded ${_selectedCandidates.length} matched songs to library')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Batch download failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Fangpi / Kuwo')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 40),
          children: [
            TextField(
              controller: _searchController,
              onSubmitted: (_) => _search(),
              decoration: InputDecoration(
                hintText: 'Search music from Fangpi / Kuwo',
                suffixIcon: IconButton(
                  onPressed: _searching ? null : _search,
                  icon: const Icon(Icons.search),
                ),
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _searching ? null : _search,
              child: Text(_searching ? 'Searching...' : 'Search Songs'),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _playlistUrlController,
              decoration: InputDecoration(
                hintText: 'Paste playlist URL from NetEase / QQ',
                suffixIcon: IconButton(
                  onPressed: _parsing ? null : _parsePlaylist,
                  icon: const Icon(Icons.playlist_play),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton.tonal(
                    onPressed: _parsing ? null : _parsePlaylist,
                    child: Text(_parsing ? 'Parsing...' : 'Parse Playlist'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    onPressed: _parsedPlaylist == null || _downloading ? null : _importParsedPlaylist,
                    child: const Text('Import as Playlist'),
                  ),
                ),
              ],
            ),
            if (_parsedPlaylist != null) ...[
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: FilledButton.tonal(
                      onPressed: _batchSearching ? null : _batchMatchParsedPlaylist,
                      child: Text(_batchSearching ? 'Matching...' : 'Batch Match Candidates'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton(
                      onPressed: _selectedCandidates.isEmpty || _downloading ? null : _downloadMatchedBatch,
                      child: const Text('Download Matches'),
                    ),
                  ),
                ],
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 16),
              Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            ],
            if (_parsedPlaylist != null) ...[
              const SizedBox(height: 24),
              _SectionCard(
                title: '${_parsedPlaylist!.name} (${_parsedPlaylist!.platform})',
                child: Column(
                  children: _parsedPlaylist!.tracks.take(8).map((track) {
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Row(
                        children: [
                          const Icon(Icons.music_note, color: AppColors.primary),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text('${track.title} - ${track.artist}'),
                          ),
                        ],
                      ),
                    );
                  }).toList(),
                ),
              ),
            ],
            const SizedBox(height: 24),
            ..._results.map(
              (song) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _SectionCard(
                  title: song.title,
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          '${song.artist}${song.source == null ? '' : ' - ${song.source}'}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                      FilledButton(
                        onPressed: _downloading ? null : () => _downloadSong(song),
                        child: const Text('Download'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            if (_batchResults.isNotEmpty) ...[
              const SizedBox(height: 24),
              ..._batchResults.map(
                (result) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _SectionCard(
                    title: '${result.title} - ${result.artist}',
                    child: result.candidates.isEmpty
                        ? const Text('No candidate found')
                        : Column(
                            children: result.candidates.map((candidate) {
                              final key = '${result.title}::${result.artist}';
                              final selected = _selectedCandidates[key]?.id == candidate.id;
                              return ListTile(
                                onTap: () {
                                  setState(() => _selectedCandidates[key] = candidate);
                                },
                                leading: Icon(
                                  selected ? Icons.radio_button_checked : Icons.radio_button_off,
                                  color: selected ? AppColors.primary : AppColors.onSurfaceVariant,
                                ),
                                title: Text(candidate.title),
                                subtitle: Text(
                                  '${candidate.artist}${candidate.source == null ? '' : ' - ${candidate.source}'}',
                                ),
                                selected: selected,
                              );
                            }).toList(),
                          ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.title,
    required this.child,
  });

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        color: AppColors.surfaceContainerHigh,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          child,
        ],
      ),
    );
  }
}
