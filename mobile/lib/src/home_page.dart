import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import 'api_client.dart';
import 'extra_tabs.dart';
import 'models.dart';

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.apiClient,
    required this.session,
    required this.data,
    required this.loading,
    required this.error,
    required this.onRefresh,
    required this.onLogout,
  });

  final HarBeatApiClient apiClient;
  final SessionBundle session;
  final DashboardData? data;
  final bool loading;
  final String? error;
  final Future<void> Function() onRefresh;
  final Future<void> Function() onLogout;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final AudioPlayer _player = AudioPlayer();
  final TextEditingController _librarySearchController = TextEditingController();
  final TextEditingController _onlineSearchController = TextEditingController();

  DashboardData? _data;
  List<LibrarySong> _displaySongs = const [];
  List<FangpiSong> _remoteResults = const [];
  PlaylistDetail? _selectedPlaylist;
  LibrarySong? _currentSong;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  bool _librarySearching = false;
  bool _remoteSearching = false;
  bool _uploading = false;
  bool _playlistLoading = false;
  String? _localError;
  int _selectedIndex = 0;

  StreamSubscription<Duration>? _positionSub;
  StreamSubscription<Duration?>? _durationSub;

  @override
  void initState() {
    super.initState();
    _syncFromWidget();
    _positionSub = _player.positionStream.listen((value) {
      if (mounted) setState(() => _position = value);
    });
    _durationSub = _player.durationStream.listen((value) {
      if (mounted) setState(() => _duration = value ?? Duration.zero);
    });
  }

  @override
  void didUpdateWidget(covariant HomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.data != widget.data || oldWidget.error != widget.error) {
      _syncFromWidget();
    }
  }

  void _syncFromWidget() {
    _data = widget.data;
    _displaySongs = widget.data?.songs ?? const [];
    _localError = widget.error;
  }

  @override
  void dispose() {
    _positionSub?.cancel();
    _durationSub?.cancel();
    _player.dispose();
    _librarySearchController.dispose();
    _onlineSearchController.dispose();
    super.dispose();
  }

  Future<void> _refreshAll() async {
    await widget.onRefresh();
    _syncFromWidget();
    if (mounted) setState(() {});
  }

  Future<void> _searchLibrary(String value) async {
    if (value.trim().isEmpty) {
      setState(() {
        _displaySongs = _data?.songs ?? const [];
        _librarySearching = false;
      });
      return;
    }

    setState(() => _librarySearching = true);
    try {
      final result = await widget.apiClient.searchLibrarySongs(
        token: widget.session.token,
        query: value.trim(),
      );
      setState(() {
        _displaySongs = result;
        _librarySearching = false;
      });
    } catch (error) {
      setState(() {
        _localError = error.toString();
        _librarySearching = false;
      });
    }
  }

  Future<void> _searchOnline() async {
    if (_onlineSearchController.text.trim().isEmpty) return;
    setState(() {
      _remoteSearching = true;
      _localError = null;
    });
    try {
      final result = await widget.apiClient.searchFangpi(
        token: widget.session.token,
        query: _onlineSearchController.text.trim(),
      );
      setState(() {
        _remoteResults = result;
        _remoteSearching = false;
      });
    } catch (error) {
      setState(() {
        _remoteSearching = false;
        _localError = error.toString();
      });
    }
  }

  Future<void> _downloadRemote(FangpiSong song) async {
    try {
      final created = await widget.apiClient.downloadFangpi(
        token: widget.session.token,
        song: song,
      );
      final songs = [created, ...?_data?.songs];
      setState(() {
        _data = DashboardData(
          profile: _data?.profile ?? widget.session.profile,
          songs: songs,
          playlists: _data?.playlists ?? const [],
        );
        _displaySongs = songs;
      });
    } catch (error) {
      setState(() => _localError = error.toString());
    }
  }

  Future<void> _pickAndUpload() async {
    final result = await FilePicker.platform.pickFiles(
      allowMultiple: true,
      type: FileType.custom,
      allowedExtensions: ['mp3', 'flac', 'wav', 'ogg', 'aac', 'm4a', 'opus', 'ncm'],
    );
    if (result == null || result.files.isEmpty) return;

    setState(() {
      _uploading = true;
      _localError = null;
    });

    try {
      final uploaded = <LibrarySong>[];
      for (final file in result.files) {
        if (file.path == null) continue;
        final parsed = _guessTitleArtist(file.name);
        final song = await widget.apiClient.uploadSong(
          token: widget.session.token,
          file: File(file.path!),
          title: parsed.$1,
          artist: parsed.$2,
        );
        uploaded.add(song);
      }
      final songs = [...uploaded, ...?_data?.songs];
      setState(() {
        _data = DashboardData(
          profile: _data?.profile ?? widget.session.profile,
          songs: songs,
          playlists: _data?.playlists ?? const [],
        );
        _displaySongs = songs;
        _uploading = false;
      });
    } catch (error) {
      setState(() {
        _uploading = false;
        _localError = error.toString();
      });
    }
  }

  (String, String) _guessTitleArtist(String filename) {
    final raw = filename.replaceFirst(RegExp(r'\.[^.]+$'), '');
    if (raw.contains(' - ')) {
      final parts = raw.split(' - ');
      return (parts.skip(1).join(' - ').trim(), parts.first.trim());
    }
    return (raw, 'Unknown Artist');
  }

  Future<void> _openPlaylist(PlaylistSummary playlist) async {
    setState(() {
      _playlistLoading = true;
      _selectedPlaylist = null;
    });
    try {
      final detail = await widget.apiClient.getPlaylistDetail(
        token: widget.session.token,
        playlistId: playlist.id,
      );
      setState(() {
        _selectedPlaylist = detail;
        _playlistLoading = false;
      });
      if (!mounted) return;
      await showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        builder: (context) => PlaylistDetailSheet(
          playlist: detail,
          librarySongs: _data?.songs ?? const [],
          onPlayPlaylistSong: _playPlaylistSong,
        ),
      );
    } catch (error) {
      setState(() {
        _playlistLoading = false;
        _localError = error.toString();
      });
    }
  }

  Future<void> _openSongDetail(LibrarySong song) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => SongDetailSheet(
        apiClient: widget.apiClient,
        session: widget.session,
        song: song,
        onPlay: _playSong,
        onAnalyze: _analyzeSong,
      ),
    );
  }

  Future<void> _playSong(LibrarySong song) async {
    try {
      final url = widget.apiClient.streamUrl(
        token: widget.session.token,
        songId: song.id,
      );
      await _player.setUrl(url);
      await _player.play();
      setState(() {
        _currentSong = song;
      });
    } catch (error) {
      setState(() => _localError = '播放失败: $error');
    }
  }

  Future<void> _playSongById(String librarySongId) async {
    for (final item in _data?.songs ?? const <LibrarySong>[]) {
      if (item.id == librarySongId) {
        await _playSong(item);
        return;
      }
    }
    setState(() => _localError = '曲库中未找到对应歌曲');
  }

  Future<void> _playPlaylistSong(PlaylistSong playlistSong) async {
    for (final item in _data?.songs ?? const <LibrarySong>[]) {
      if (item.title.toLowerCase() == playlistSong.title.toLowerCase() &&
          item.artist.toLowerCase() == playlistSong.artist.toLowerCase()) {
        await _playSong(item);
        return;
      }
    }
    setState(() => _localError = '当前歌单歌曲没有对应的本地曲库文件，暂时无法播放');
  }

  Future<void> _togglePlayback() async {
    if (_player.playing) {
      await _player.pause();
    } else {
      await _player.play();
    }
    if (mounted) setState(() {});
  }

  Future<void> _seek(double value) async {
    await _player.seek(Duration(seconds: value.round()));
  }

  Future<void> _analyzeSong(LibrarySong song) async {
    try {
      final updated = await widget.apiClient.analyzeSong(
        token: widget.session.token,
        songId: song.id,
      );
      final songs = (_data?.songs ?? const <LibrarySong>[])
          .map((item) => item.id == song.id ? updated : item)
          .toList();
      setState(() {
        _data = DashboardData(
          profile: _data?.profile ?? widget.session.profile,
          songs: songs,
          playlists: _data?.playlists ?? const [],
        );
        _displaySongs = songs;
        if (_currentSong?.id == song.id) {
          _currentSong = updated;
        }
      });
    } catch (error) {
      setState(() => _localError = error.toString());
    }
  }

  Future<void> _deleteSong(LibrarySong song) async {
    try {
      await widget.apiClient.deleteSong(token: widget.session.token, songId: song.id);
      final songs = (_data?.songs ?? const <LibrarySong>[])
          .where((item) => item.id != song.id)
          .toList();
      if (_currentSong?.id == song.id) {
        await _player.stop();
      }
      setState(() {
        _data = DashboardData(
          profile: _data?.profile ?? widget.session.profile,
          songs: songs,
          playlists: _data?.playlists ?? const [],
        );
        _displaySongs = songs;
        if (_currentSong?.id == song.id) {
          _currentSong = null;
          _position = Duration.zero;
          _duration = Duration.zero;
        }
      });
    } catch (error) {
      setState(() => _localError = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final songs = _data?.songs ?? const <LibrarySong>[];
    final playlists = _data?.playlists ?? const <PlaylistSummary>[];

    return Scaffold(
      appBar: AppBar(
        title: Text(_titleForTab(_selectedIndex)),
        actions: [
          if (_selectedIndex == 1)
            IconButton(
              tooltip: '上传歌曲',
              onPressed: _uploading ? null : _pickAndUpload,
              icon: _uploading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.upload_file),
            ),
          IconButton(
            tooltip: '刷新',
            onPressed: () => _refreshAll(),
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: '退出登录',
            onPressed: () => widget.onLogout(),
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (_localError != null)
              MaterialBanner(
                content: Text(_localError!),
                actions: [
                  TextButton(
                    onPressed: () => setState(() => _localError = null),
                    child: const Text('关闭'),
                  ),
                ],
              ),
            Expanded(
              child: IndexedStack(
                index: _selectedIndex,
                children: [
                  OverviewTab(
                    profile: widget.session.profile,
                    songs: songs,
                    playlists: playlists,
                    loading: widget.loading,
                  ),
                  LibraryTab(
                    controller: _librarySearchController,
                    songs: _displaySongs,
                    searching: _librarySearching,
                    onSearchChanged: _searchLibrary,
                    onPlay: _playSong,
                    onAnalyze: _analyzeSong,
                    onDelete: _deleteSong,
                    onDetails: _openSongDetail,
                  ),
                  OnlineSearchTab(
                    controller: _onlineSearchController,
                    results: _remoteResults,
                    searching: _remoteSearching,
                    onSearch: _searchOnline,
                    onDownload: _downloadRemote,
                  ),
                  PlaylistsTab(
                    playlists: playlists,
                    loading: _playlistLoading,
                    onOpen: _openPlaylist,
                    selectedPlaylist: _selectedPlaylist,
                  ),
                  DiscoverTab(
                    apiClient: widget.apiClient,
                    userId: widget.session.profile.id,
                    onAdded: _refreshAll,
                  ),
                  SessionTab(
                    apiClient: widget.apiClient,
                    user: widget.session.profile,
                    onPlayLibrarySong: _playSongById,
                  ),
                  ProfileTab(
                    apiClient: widget.apiClient,
                    user: widget.session.profile,
                  ),
                  DjToolsTab(
                    apiClient: widget.apiClient,
                    session: widget.session,
                    playlists: playlists,
                  ),
                ],
              ),
            ),
            if (_currentSong != null)
              MiniPlayer(
                song: _currentSong!,
                isPlaying: _player.playing,
                position: _position,
                duration: _duration,
                onToggle: _togglePlayback,
                onSeek: _seek,
              ),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (value) => setState(() => _selectedIndex = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dashboard_outlined), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.library_music_outlined), label: 'Library'),
          NavigationDestination(icon: Icon(Icons.travel_explore_outlined), label: 'Search'),
          NavigationDestination(icon: Icon(Icons.queue_music_outlined), label: 'Playlists'),
          NavigationDestination(icon: Icon(Icons.auto_awesome_outlined), label: 'Discover'),
          NavigationDestination(icon: Icon(Icons.podcasts_outlined), label: 'Session'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: 'Profile'),
          NavigationDestination(icon: Icon(Icons.equalizer), label: 'DJ'),
        ],
      ),
    );
  }

  String _titleForTab(int index) {
    switch (index) {
      case 1:
        return 'Library';
      case 2:
        return 'Search';
      case 3:
        return 'Playlists';
      case 4:
        return 'Discover';
      case 5:
        return 'Session';
      case 6:
        return 'Profile';
      case 7:
        return 'DJ Tools';
      default:
        return 'HarBeat';
    }
  }
}

class OverviewTab extends StatelessWidget {
  const OverviewTab({
    super.key,
    required this.profile,
    required this.songs,
    required this.playlists,
    required this.loading,
  });

  final UserProfile profile;
  final List<LibrarySong> songs;
  final List<PlaylistSummary> playlists;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final analyzed = songs.where((item) => item.analysisStatus == 'completed').length;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: ListTile(
            leading: CircleAvatar(child: Text(profile.username.isEmpty ? '?' : profile.username[0].toUpperCase())),
            title: Text(profile.username),
            subtitle: Text('${profile.danceStyle} · ${profile.level} · 喜欢 ${profile.favoriteStyle}'),
          ),
        ),
        const SizedBox(height: 12),
        GridView.count(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisCount: 2,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          childAspectRatio: 1.6,
          children: [
            StatCard(label: '歌曲', value: '${songs.length}'),
            StatCard(label: '歌单', value: '${playlists.length}'),
            StatCard(label: '已分析', value: '$analyzed'),
            StatCard(label: '状态', value: loading ? '同步中' : '就绪'),
          ],
        ),
        const SizedBox(height: 16),
        SectionCard(
          title: '最近歌曲',
          child: Column(
            children: songs.take(5).map((song) => SongSummaryTile(song: song)).toList(),
          ),
        ),
      ],
    );
  }
}

class LibraryTab extends StatelessWidget {
  const LibraryTab({
    super.key,
    required this.controller,
    required this.songs,
    required this.searching,
    required this.onSearchChanged,
    required this.onPlay,
    required this.onAnalyze,
    required this.onDelete,
    required this.onDetails,
  });

  final TextEditingController controller;
  final List<LibrarySong> songs;
  final bool searching;
  final ValueChanged<String> onSearchChanged;
  final Future<void> Function(LibrarySong song) onPlay;
  final Future<void> Function(LibrarySong song) onAnalyze;
  final Future<void> Function(LibrarySong song) onDelete;
  final Future<void> Function(LibrarySong song) onDetails;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: TextField(
            controller: controller,
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search),
              suffixIcon: searching
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                    )
                  : null,
              hintText: '搜索曲库中的歌曲或艺人',
              border: const OutlineInputBorder(),
            ),
            onChanged: onSearchChanged,
          ),
        ),
        Expanded(
          child: songs.isEmpty
              ? const Center(child: Text('曲库为空，先上传或下载歌曲'))
              : ListView.separated(
                  itemCount: songs.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final song = songs[index];
                    return ListTile(
                      leading: const CircleAvatar(child: Icon(Icons.music_note)),
                      title: Text(song.title),
                      subtitle: Text([
                        song.artist,
                        if (song.bpm != null) '${song.bpm!.toStringAsFixed(0)} BPM',
                        song.analysisStatus,
                      ].join(' · ')),
                      onTap: () => _showSongActions(context, song),
                    );
                  },
                ),
        ),
      ],
    );
  }

  void _showSongActions(BuildContext context, LibrarySong song) {
    showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      builder: (context) => Wrap(
        children: [
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('详情'),
            onTap: () async {
              Navigator.pop(context);
              await onDetails(song);
            },
          ),
          ListTile(
            leading: const Icon(Icons.play_arrow),
            title: const Text('播放'),
            onTap: () async {
              Navigator.pop(context);
              await onPlay(song);
            },
          ),
          ListTile(
            leading: const Icon(Icons.analytics_outlined),
            title: const Text('分析 BPM / Key'),
            onTap: () async {
              Navigator.pop(context);
              await onAnalyze(song);
            },
          ),
          ListTile(
            leading: const Icon(Icons.delete_outline),
            title: const Text('删除'),
            onTap: () async {
              Navigator.pop(context);
              await onDelete(song);
            },
          ),
        ],
      ),
    );
  }
}

class OnlineSearchTab extends StatelessWidget {
  const OnlineSearchTab({
    super.key,
    required this.controller,
    required this.results,
    required this.searching,
    required this.onSearch,
    required this.onDownload,
  });

  final TextEditingController controller;
  final List<FangpiSong> results;
  final bool searching;
  final Future<void> Function() onSearch;
  final Future<void> Function(FangpiSong song) onDownload;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.travel_explore),
                    hintText: '搜索在线歌曲',
                    border: OutlineInputBorder(),
                  ),
                  onSubmitted: (_) => onSearch(),
                ),
              ),
              const SizedBox(width: 12),
              FilledButton(
                onPressed: searching ? null : () => onSearch(),
                child: searching
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('搜索'),
              ),
            ],
          ),
        ),
        Expanded(
          child: results.isEmpty
              ? const Center(child: Text('输入关键词后搜索在线音乐'))
              : ListView.separated(
                  itemCount: results.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final song = results[index];
                    return ListTile(
                      leading: const CircleAvatar(child: Icon(Icons.cloud_download_outlined)),
                      title: Text(song.title),
                      subtitle: Text(song.artist),
                      trailing: FilledButton.tonal(
                        onPressed: () => onDownload(song),
                        child: const Text('下载'),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }
}

class PlaylistsTab extends StatelessWidget {
  const PlaylistsTab({
    super.key,
    required this.playlists,
    required this.loading,
    required this.onOpen,
    required this.selectedPlaylist,
  });

  final List<PlaylistSummary> playlists;
  final bool loading;
  final Future<void> Function(PlaylistSummary playlist) onOpen;
  final PlaylistDetail? selectedPlaylist;

  @override
  Widget build(BuildContext context) {
    return loading
        ? const Center(child: CircularProgressIndicator())
        : ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: playlists.length,
            separatorBuilder: (_, _) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final playlist = playlists[index];
              final selected = selectedPlaylist?.id == playlist.id;
              return Card(
                color: selected ? Theme.of(context).colorScheme.primaryContainer : null,
                child: ListTile(
                  leading: const CircleAvatar(child: Icon(Icons.queue_music)),
                  title: Text(playlist.name),
                  subtitle: Text('${playlist.songCount} 首歌 · ${playlist.sourceType}'),
                  onTap: () => onOpen(playlist),
                ),
              );
            },
          );
  }
}

class PlaylistDetailSheet extends StatelessWidget {
  const PlaylistDetailSheet({
    super.key,
    required this.playlist,
    required this.librarySongs,
    required this.onPlayPlaylistSong,
  });

  final PlaylistDetail playlist;
  final List<LibrarySong> librarySongs;
  final Future<void> Function(PlaylistSong song) onPlayPlaylistSong;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(playlist.name)),
      body: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: playlist.songs.length,
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (context, index) {
          final song = playlist.songs[index];
          final playable = librarySongs.any(
            (item) =>
                item.title.toLowerCase() == song.title.toLowerCase() &&
                item.artist.toLowerCase() == song.artist.toLowerCase(),
          );
          return ListTile(
            leading: CircleAvatar(child: Text('${song.orderIndex + 1}')),
            title: Text(song.title),
            subtitle: Text([
              song.artist,
              if (song.bpm != null) '${song.bpm} BPM',
              if (song.tags.isNotEmpty) song.tags.join(', '),
            ].join(' · ')),
            trailing: playable ? const Icon(Icons.play_circle_outline) : null,
            onTap: playable ? () => onPlayPlaylistSong(song) : null,
          );
        },
      ),
    );
  }
}

class MiniPlayer extends StatelessWidget {
  const MiniPlayer({
    super.key,
    required this.song,
    required this.isPlaying,
    required this.position,
    required this.duration,
    required this.onToggle,
    required this.onSeek,
  });

  final LibrarySong song;
  final bool isPlaying;
  final Duration position;
  final Duration duration;
  final Future<void> Function() onToggle;
  final Future<void> Function(double value) onSeek;

  @override
  Widget build(BuildContext context) {
    final maxSeconds = duration.inSeconds > 0
        ? duration.inSeconds.toDouble()
        : (song.duration > 0 ? song.duration.toDouble() : 1.0);
    final currentSeconds = position.inSeconds.clamp(0, maxSeconds.toInt()).toDouble();
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  const CircleAvatar(child: Icon(Icons.graphic_eq)),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(song.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                        Text(song.artist, style: Theme.of(context).textTheme.bodySmall),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: onToggle,
                    icon: Icon(isPlaying ? Icons.pause_circle_filled : Icons.play_circle_fill),
                  ),
                ],
              ),
              Slider(
                value: currentSeconds,
                max: maxSeconds,
                onChanged: (value) => onSeek(value),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(_formatDuration(position)),
                  Text(_formatDuration(duration)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _formatDuration(Duration value) {
    final total = value.inSeconds;
    final minutes = total ~/ 60;
    final seconds = total % 60;
    return '$minutes:${seconds.toString().padLeft(2, '0')}';
  }
}

class StatCard extends StatelessWidget {
  const StatCard({super.key, required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label),
            const SizedBox(height: 8),
            Text(value, style: Theme.of(context).textTheme.headlineSmall),
          ],
        ),
      ),
    );
  }
}

class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}

class SongSummaryTile extends StatelessWidget {
  const SongSummaryTile({super.key, required this.song});

  final LibrarySong song;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const CircleAvatar(child: Icon(Icons.music_note)),
      title: Text(song.title),
      subtitle: Text([song.artist, song.analysisStatus].join(' · ')),
    );
  }
}
