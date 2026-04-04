import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../auth/auth_controller.dart';
import '../../library/library_service.dart';
import '../../library/models.dart';
import '../../player/player_controller.dart';
import '../models.dart';
import '../playlists_service.dart';

class PlaylistsPage extends StatefulWidget {
  const PlaylistsPage({super.key});

  @override
  State<PlaylistsPage> createState() => _PlaylistsPageState();
}

class _PlaylistsPageState extends State<PlaylistsPage> {
  final _service = PlaylistsService();
  bool _loading = true;
  List<PlaylistSummary> _playlists = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final userId = context.read<AuthController>().currentUser?.id;
    if (userId == null) {
      setState(() {
        _loading = false;
        _error = 'Please login again to load playlists.';
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final playlists = await _service.getPlaylists(userId);
      if (!mounted) return;
      setState(() => _playlists = playlists);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createPlaylist() async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Create Playlist'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(hintText: 'Playlist name'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Create'),
          ),
        ],
      ),
    );
    if (name == null || name.isEmpty) return;
    try {
      await _service.createPlaylist(name);
      if (!mounted) return;
      await _load();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Create failed: $error')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Playlists'),
        actions: [
          IconButton(onPressed: _createPlaylist, icon: const Icon(Icons.add)),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 40),
            children: [
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 48),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_error != null)
                Text(_error!, style: const TextStyle(color: Colors.redAccent))
              else if (_playlists.isEmpty)
                const Text('No playlists yet. Create one to start organizing songs.')
              else
                ..._playlists.map(
                  (playlist) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(22),
                      onTap: () async {
                        await Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => PlaylistDetailPage(playlist: playlist),
                          ),
                        );
                        await _load();
                      },
                      child: Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(22),
                          color: AppColors.surfaceContainerHigh,
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.queue_music, color: AppColors.primary),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(playlist.playlistName, style: Theme.of(context).textTheme.titleLarge),
                                  const SizedBox(height: 4),
                                  Text(
                                    '${playlist.songCount} songs - ${playlist.sourceType}',
                                    style: Theme.of(context).textTheme.bodySmall,
                                  ),
                                ],
                              ),
                            ),
                            const Icon(Icons.chevron_right),
                          ],
                        ),
                      ),
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

class PlaylistDetailPage extends StatefulWidget {
  const PlaylistDetailPage({
    super.key,
    required this.playlist,
  });

  final PlaylistSummary playlist;

  @override
  State<PlaylistDetailPage> createState() => _PlaylistDetailPageState();
}

class _PlaylistDetailPageState extends State<PlaylistDetailPage> {
  final _service = PlaylistsService();
  final _libraryService = LibraryService();
  bool _loading = true;
  PlaylistDetail? _detail;
  List<LibrarySong> _librarySongs = [];
  bool _reorderDirty = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final detail = await _service.getPlaylistDetail(widget.playlist.id);
      final librarySongs = await _libraryService.getLibrarySongs();
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _librarySongs = librarySongs;
        _reorderDirty = false;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _addSongs() async {
    final selected = <String>{};
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setLocalState) => AlertDialog(
          title: const Text('Add Songs From Library'),
          content: SizedBox(
            width: double.maxFinite,
            child: ListView(
              shrinkWrap: true,
              children: _librarySongs.map((song) {
                return CheckboxListTile(
                  value: selected.contains(song.id),
                  onChanged: (value) {
                    setLocalState(() {
                      if (value == true) {
                        selected.add(song.id);
                      } else {
                        selected.remove(song.id);
                      }
                    });
                  },
                  title: Text(song.title),
                  subtitle: Text(song.artist),
                );
              }).toList(),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Add')),
          ],
        ),
      ),
    );
    if (confirmed != true || selected.isEmpty) return;

    try {
      await _service.addSongsToPlaylist(widget.playlist.id, selected.toList());
      if (!mounted) return;
      await _load();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Add songs failed: $error')),
      );
    }
  }

  Future<void> _deletePlaylist() async {
    await _service.deletePlaylist(widget.playlist.id);
    if (!mounted) return;
    Navigator.of(context).pop();
  }

  Future<void> _persistOrder() async {
    final detail = _detail;
    if (detail == null || !_reorderDirty) return;
    try {
      await _service.reorderPlaylistSongs(widget.playlist.id, detail.songs);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Playlist order saved')),
      );
      await _load();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Save order failed: $error')),
      );
    }
  }

  Future<void> _editSongTags(PlaylistSong song) async {
    final controller = TextEditingController(text: song.tags.join(', '));
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Edit Tags - ${song.title}'),
        content: TextField(
          controller: controller,
          maxLines: 2,
          decoration: const InputDecoration(hintText: 'comma,separated,tags'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (result == null) return;

    final tags = result
        .split(',')
        .map((tag) => tag.trim())
        .where((tag) => tag.isNotEmpty)
        .toList();

    try {
      await _service.updatePlaylistSongTags(widget.playlist.id, song.songId, tags);
      if (!mounted) return;
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Playlist song tags updated')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Update tags failed: $error')),
      );
    }
  }

  Future<void> _playSong(PlaylistSong song) async {
    final token = context.read<AuthController>().session?.accessToken;
    final player = context.read<PlayerController>();
    if (token == null || token.isEmpty) return;

    try {
      final librarySong = await _libraryService.findExactLibrarySong(
        title: song.title,
        artist: song.artist,
      );
      if (librarySong == null) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('This playlist song is not available in local library yet.')),
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
        title: Text(widget.playlist.playlistName),
        actions: [
          if (_reorderDirty)
            IconButton(onPressed: _persistOrder, icon: const Icon(Icons.save_outlined)),
          IconButton(onPressed: _addSongs, icon: const Icon(Icons.playlist_add)),
          IconButton(onPressed: _deletePlaylist, icon: const Icon(Icons.delete_outline)),
        ],
      ),
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 40),
                children: [
                  if (_detail == null)
                    const Text('Playlist not found.')
                  else ...[
                    if (_reorderDirty)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(18),
                            color: AppColors.surfaceContainerHighest,
                          ),
                          child: const Text(
                            'Drag songs to reorder, then tap the save icon in the top bar to persist the new order.',
                          ),
                        ),
                      ),
                    ReorderableListView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: _detail!.songs.length,
                      onReorder: (oldIndex, newIndex) {
                        final songs = [..._detail!.songs];
                        if (newIndex > oldIndex) newIndex -= 1;
                        final item = songs.removeAt(oldIndex);
                        songs.insert(newIndex, item);
                        setState(() {
                          _detail = PlaylistDetail(
                            id: _detail!.id,
                            userId: _detail!.userId,
                            playlistName: _detail!.playlistName,
                            sourceType: _detail!.sourceType,
                            songs: songs,
                          );
                          _reorderDirty = true;
                        });
                      },
                      itemBuilder: (context, index) {
                        final song = _detail!.songs[index];
                        return Padding(
                          key: ValueKey('${song.songId}-${song.orderIndex}-$index'),
                          padding: const EdgeInsets.only(bottom: 12),
                          child: InkWell(
                            borderRadius: BorderRadius.circular(20),
                            onTap: () => _playSong(song),
                            child: Container(
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(20),
                                color: AppColors.surfaceContainerHigh,
                              ),
                              child: Row(
                                children: [
                                  const Icon(Icons.drag_handle, color: AppColors.onSurfaceVariant),
                                  const SizedBox(width: 8),
                                  const Icon(Icons.play_circle_fill, color: AppColors.primary, size: 34),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(song.title, style: Theme.of(context).textTheme.titleLarge),
                                        const SizedBox(height: 4),
                                        Text('${song.artist}${song.bpm == null ? '' : ' - ${song.bpm} BPM'}'),
                                        if (song.tags.isNotEmpty) ...[
                                          const SizedBox(height: 8),
                                          Wrap(
                                            spacing: 8,
                                            runSpacing: 8,
                                            children: song.tags.map((tag) => Chip(label: Text(tag))).toList(),
                                          ),
                                        ],
                                      ],
                                    ),
                                  ),
                                  IconButton(
                                    onPressed: () => _editSongTags(song),
                                    icon: const Icon(Icons.edit_outlined),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                  ],
                ],
              ),
      ),
    );
  }
}
