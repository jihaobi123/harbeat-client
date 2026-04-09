import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';

import 'api_client.dart';
import 'models.dart';

class SongDetailSheet extends StatefulWidget {
  const SongDetailSheet({
    super.key,
    required this.apiClient,
    required this.session,
    required this.song,
    required this.onPlay,
    required this.onAnalyze,
  });

  final HarBeatApiClient apiClient;
  final SessionBundle session;
  final LibrarySong song;
  final Future<void> Function(LibrarySong song) onPlay;
  final Future<void> Function(LibrarySong song) onAnalyze;

  @override
  State<SongDetailSheet> createState() => _SongDetailSheetState();
}

class _SongDetailSheetState extends State<SongDetailSheet> {
  CatalogSong? _catalogSong;
  List<SongCue> _cues = const [];
  bool _loading = true;
  bool _processing = false;
  String? _error;
  StyleProcessResult? _styleResult;
  final TextEditingController _cueLabelController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _cueLabelController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final songs = await widget.apiClient.getCatalogSongs();
      final match = songs.where((item) =>
          item.title.toLowerCase() == widget.song.title.toLowerCase() &&
          item.artist.toLowerCase() == widget.song.artist.toLowerCase()).cast<CatalogSong?>().firstWhere(
            (_) => true,
            orElse: () => null,
          );
      List<SongCue> cues = const [];
      if (match != null) {
        cues = await widget.apiClient.getCues(
          songId: match.id,
          userId: widget.session.profile.id,
        );
      }
      setState(() {
        _catalogSong = match;
        _cues = cues;
        _loading = false;
      });
    } catch (error) {
      setState(() {
        _loading = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _addCue() async {
    final catalogSong = _catalogSong;
    if (catalogSong == null) return;
    try {
      final cue = await widget.apiClient.createCue(
        songId: catalogSong.id,
        userId: widget.session.profile.id,
        cueType: 'marker',
        startTime: 0,
        label: _cueLabelController.text.trim().isEmpty ? 'Cue' : _cueLabelController.text.trim(),
      );
      setState(() {
        _cues = [..._cues, cue];
        _cueLabelController.clear();
      });
    } catch (error) {
      setState(() => _error = error.toString());
    }
  }

  Future<void> _processStyle() async {
    final catalogSong = _catalogSong;
    if (catalogSong == null) return;
    setState(() {
      _processing = true;
      _error = null;
    });
    try {
      final result = await widget.apiClient.processSongStyle(
        songId: catalogSong.id,
        styles: [widget.session.profile.danceStyle],
      );
      setState(() {
        _styleResult = result;
        _processing = false;
      });
    } catch (error) {
      setState(() {
        _processing = false;
        _error = error.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.song.title)),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(widget.song.title),
                  subtitle: Text(widget.song.artist),
                  trailing: FilledButton(
                    onPressed: () => widget.onPlay(widget.song),
                    child: const Text('播放'),
                  ),
                ),
                if (_error != null) ...[
                  Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(_error!))),
                  const SizedBox(height: 12),
                ],
                _MetaBlock(song: widget.song),
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('分析与分轨', style: TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        Text('分析状态: ${widget.song.analysisStatus}'),
                        Text('分轨状态: ${widget.song.sourceType.isNotEmpty ? '可从 Web 端继续处理' : '未知'}'),
                        const SizedBox(height: 12),
                        FilledButton.tonal(
                          onPressed: () => widget.onAnalyze(widget.song),
                          child: const Text('分析 BPM / Key'),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Cue 点', style: TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        if (_catalogSong == null)
                          const Text('当前歌曲还没有对应 catalog 记录，无法创建用户 Cue。')
                        else ...[
                          Row(
                            children: [
                              Expanded(
                                child: TextField(
                                  controller: _cueLabelController,
                                  decoration: const InputDecoration(
                                    hintText: '新 Cue 标签',
                                    border: OutlineInputBorder(),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              FilledButton.tonal(
                                onPressed: _addCue,
                                child: const Text('添加'),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          if (_cues.isEmpty)
                            const Text('还没有用户 Cue 点')
                          else
                            ..._cues.map((cue) => ListTile(
                                  contentPadding: EdgeInsets.zero,
                                  title: Text(cue.label ?? cue.cueType),
                                  subtitle: Text('开始 ${cue.startTime.toStringAsFixed(2)}s'),
                                )),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('风格处理', style: TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        FilledButton.tonal(
                          onPressed: _processing ? null : _processStyle,
                          child: Text(_processing ? '处理中...' : '按当前舞种生成处理版'),
                        ),
                        if (_styleResult != null) ...[
                          const SizedBox(height: 12),
                          ..._styleResult!.processedFiles.entries.map(
                            (entry) => ListTile(
                              contentPadding: EdgeInsets.zero,
                              title: Text(entry.key),
                              subtitle: Text(entry.value),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}

class DiscoverTab extends StatefulWidget {
  const DiscoverTab({
    super.key,
    required this.apiClient,
    required this.userId,
    required this.onAdded,
  });

  final HarBeatApiClient apiClient;
  final int userId;
  final Future<void> Function() onAdded;

  @override
  State<DiscoverTab> createState() => _DiscoverTabState();
}

class _DiscoverTabState extends State<DiscoverTab> {
  List<DiscoverSectionData> _sections = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final sections = await widget.apiClient.discoverSongs(userId: widget.userId);
      setState(() {
        _sections = sections;
        _loading = false;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  Future<void> _add(DiscoverSongItem song) async {
    await widget.apiClient.addSongToLibrary(userId: widget.userId, songId: song.songId);
    await widget.onAdded();
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (_error != null) Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(_error!))),
        ..._sections.map((section) => Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${section.icon} ${section.title}', style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 4),
                    Text(section.description),
                    const SizedBox(height: 12),
                    ...section.songs.map((song) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(song.title),
                          subtitle: Text([
                            song.artist,
                            if (song.style != null) song.style!,
                            if (song.energy != null) song.energy!,
                          ].join(' · ')),
                          trailing: song.inLibrary
                              ? const Text('已在曲库')
                              : FilledButton.tonal(
                                  onPressed: () => _add(song),
                                  child: const Text('加入'),
                                ),
                        )),
                  ],
                ),
              ),
            )),
      ],
    );
  }
}

class ProfileTab extends StatefulWidget {
  const ProfileTab({
    super.key,
    required this.apiClient,
    required this.user,
  });

  final HarBeatApiClient apiClient;
  final UserProfile user;

  @override
  State<ProfileTab> createState() => _ProfileTabState();
}

class _ProfileTabState extends State<ProfileTab> {
  MusicProfile? _profile;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final profile = await widget.apiClient.getProfile(widget.user.id);
      setState(() {
        _profile = profile;
        _loading = false;
      });
    } catch (error) {
      setState(() {
        _loading = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _generate() async {
    try {
      final profile = await widget.apiClient.generateProfile(widget.user.id);
      setState(() => _profile = profile);
    } catch (error) {
      setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: ListTile(
            leading: CircleAvatar(child: Text(widget.user.username[0].toUpperCase())),
            title: Text(widget.user.username),
            subtitle: Text('${widget.user.danceStyle} · ${widget.user.level}'),
            trailing: FilledButton.tonal(onPressed: _generate, child: const Text('生成画像')),
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(_error!))),
        ],
        if (_profile != null) ...[
          const SizedBox(height: 12),
          _profileItem('偏好风格', _profile!.favoriteStyle),
          _profileItem('平均 BPM', _profile!.avgBpmPreference?.toString() ?? '--'),
          _profileItem('能量偏好', _profile!.energyPreference ?? '--'),
          _profileItem('人声偏好', _profile!.vocalPreference ?? '--'),
          _profileItem('律动偏好', _profile!.groovePreference ?? '--'),
        ],
      ],
    );
  }

  Widget _profileItem(String label, String value) {
    return Card(
      child: ListTile(
        title: Text(label),
        subtitle: Text(value),
      ),
    );
  }
}

class SessionTab extends StatefulWidget {
  const SessionTab({
    super.key,
    required this.apiClient,
    required this.user,
    required this.onPlayLibrarySong,
  });

  final HarBeatApiClient apiClient;
  final UserProfile user;
  final Future<void> Function(String librarySongId) onPlayLibrarySong;

  @override
  State<SessionTab> createState() => _SessionTabState();
}

class _SessionTabState extends State<SessionTab> {
  int? _sessionId;
  List<PracticeTrack> _tracks = const [];
  String _mode = 'training';
  bool _loading = false;
  String? _error;

  Future<void> _start() async {
    setState(() => _loading = true);
    try {
      final id = await widget.apiClient.startSession(userId: widget.user.id, mode: _mode);
      setState(() {
        _sessionId = id;
        _loading = false;
      });
    } catch (error) {
      setState(() {
        _loading = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _practice() async {
    setState(() => _loading = true);
    try {
      final tracks = await widget.apiClient.generatePracticeList(
        userId: widget.user.id,
        targetDuration: 30,
      );
      setState(() {
        _tracks = tracks;
        _loading = false;
      });
    } catch (error) {
      setState(() {
        _loading = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _end() async {
    final sessionId = _sessionId;
    if (sessionId == null) return;
    await widget.apiClient.endSession(sessionId);
    setState(() => _sessionId = null);
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Session 模式', style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  initialValue: _mode,
                  items: const [
                    DropdownMenuItem(value: 'freeplay', child: Text('freeplay')),
                    DropdownMenuItem(value: 'cypher', child: Text('cypher')),
                    DropdownMenuItem(value: 'battle', child: Text('battle')),
                    DropdownMenuItem(value: 'showcase', child: Text('showcase')),
                    DropdownMenuItem(value: 'training', child: Text('training')),
                  ],
                  onChanged: (value) => setState(() => _mode = value ?? 'training'),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    FilledButton.tonal(onPressed: _loading ? null : _start, child: const Text('开始 Session')),
                    const SizedBox(width: 12),
                    FilledButton.tonal(onPressed: _loading ? null : _practice, child: const Text('生成练习歌单')),
                    const SizedBox(width: 12),
                    if (_sessionId != null)
                      FilledButton.tonal(onPressed: _end, child: const Text('结束')),
                  ],
                ),
                if (_sessionId != null) ...[
                  const SizedBox(height: 8),
                  Text('当前 Session ID: $_sessionId'),
                ],
              ],
            ),
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(_error!))),
        ],
        if (_loading) const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator())),
        if (_tracks.isNotEmpty) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('练习歌单', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  ..._tracks.map((track) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(track.title),
                        subtitle: Text('${track.artist} · ${track.bpm?.toStringAsFixed(0) ?? '--'} BPM'),
                        trailing: FilledButton.tonal(
                          onPressed: () => widget.onPlayLibrarySong(track.id),
                          child: const Text('播放'),
                        ),
                      )),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class DjToolsTab extends StatefulWidget {
  const DjToolsTab({
    super.key,
    required this.apiClient,
    required this.session,
    required this.playlists,
  });

  final HarBeatApiClient apiClient;
  final SessionBundle session;
  final List<PlaylistSummary> playlists;

  @override
  State<DjToolsTab> createState() => _DjToolsTabState();
}

class _DjToolsTabState extends State<DjToolsTab> {
  final AudioPlayer _player = AudioPlayer();
  String _style = 'hiphop';
  int _duration = 30;
  int? _playlistId;
  bool _loading = false;
  String? _error;
  DjMixPlanResult? _mixPlan;
  DjOfflineMixResult? _offline;

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _generatePlan() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await widget.apiClient.generateDjMixPlan(
        style: _style,
        durationMinutes: _duration,
        playlistId: _playlistId,
      );
      setState(() {
        _mixPlan = result;
        _loading = false;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  Future<void> _renderOffline() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await widget.apiClient.generateDjOfflineMix(
        style: _style,
        durationMinutes: _duration,
        playlistId: _playlistId,
      );
      setState(() {
        _offline = result;
        _mixPlan = result.mixPlan;
        _loading = false;
      });
    } catch (error) {
      setState(() {
        _error = error.toString();
        _loading = false;
      });
    }
  }

  Future<void> _playProcessed(String filePath) async {
    final url = widget.apiClient.processedStreamUrl(
      token: widget.session.token,
      filePath: filePath,
    );
    await _player.setUrl(url);
    await _player.play();
  }

  Future<void> _playOffline(String filename) async {
    final url = widget.apiClient.mixStreamUrl(
      token: widget.session.token,
      filename: filename,
    );
    await _player.setUrl(url);
    await _player.play();
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('DJ Tools', style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: _style,
                  decoration: const InputDecoration(labelText: '舞种'),
                  items: const [
                    'hiphop', 'jazz', 'breaking', 'popping', 'locking', 'waacking', 'house', 'krump'
                  ].map((item) => DropdownMenuItem(value: item, child: Text(item))).toList(),
                  onChanged: (value) => setState(() => _style = value ?? 'hiphop'),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<int?>(
                  initialValue: _playlistId,
                  decoration: const InputDecoration(labelText: '来源歌单'),
                  items: [
                    const DropdownMenuItem<int?>(value: null, child: Text('全部曲库')),
                    ...widget.playlists.map((playlist) => DropdownMenuItem<int?>(
                          value: playlist.id,
                          child: Text(playlist.name),
                        )),
                  ],
                  onChanged: (value) => setState(() => _playlistId = value),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<int>(
                  initialValue: _duration,
                  decoration: const InputDecoration(labelText: '时长'),
                  items: const [15, 30, 45, 60].map((value) => DropdownMenuItem(value: value, child: Text('$value 分钟'))).toList(),
                  onChanged: (value) => setState(() => _duration = value ?? 30),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    FilledButton.tonal(
                      onPressed: _loading ? null : _generatePlan,
                      child: const Text('生成 DJ Plan'),
                    ),
                    FilledButton.tonal(
                      onPressed: _loading ? null : _renderOffline,
                      child: const Text('离线渲染'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        if (_loading) const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator())),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(_error!))),
        ],
        if (_mixPlan != null) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('DJ Mix Plan', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  ..._mixPlan!.playlist.map((track) {
                    final file = _mixPlan!.processedFiles[track.songId];
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(track.title),
                      subtitle: Text('${track.artist} · ${track.bpm ?? '--'} BPM'),
                      trailing: file == null
                          ? null
                          : FilledButton.tonal(
                              onPressed: () => _playProcessed(file),
                              child: const Text('预览'),
                            ),
                    );
                  }),
                ],
              ),
            ),
          ),
        ],
        if (_offline != null) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Offline Mix', style: TextStyle(fontWeight: FontWeight.bold)),
                  Text('时长 ${_offline!.durationSec.toStringAsFixed(1)} 秒'),
                  if (_offline!.warnings.isNotEmpty) Text('警告: ${_offline!.warnings.join(' | ')}'),
                  const SizedBox(height: 8),
                  ..._offline!.streamFiles.entries.map((entry) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(entry.key.toUpperCase()),
                        subtitle: Text(entry.value),
                        trailing: FilledButton.tonal(
                          onPressed: () => _playOffline(entry.value),
                          child: const Text('播放'),
                        ),
                      )),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _MetaBlock extends StatelessWidget {
  const _MetaBlock({required this.song});

  final LibrarySong song;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            _meta('BPM', song.bpm?.toStringAsFixed(0) ?? '--'),
            _meta('Key', song.key ?? '--'),
            _meta('Camelot', song.camelotKey ?? '--'),
            _meta('格式', song.format.toUpperCase()),
            _meta('时长', '${song.duration.toStringAsFixed(0)}s'),
            _meta('状态', song.analysisStatus),
          ],
        ),
      ),
    );
  }

  Widget _meta(String label, String value) {
    return SizedBox(
      width: 120,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
          const SizedBox(height: 4),
          Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}
