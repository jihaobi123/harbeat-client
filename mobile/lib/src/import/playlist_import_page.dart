import 'dart:async';

import 'package:flutter/material.dart';

import '../api_client.dart';
import '../models.dart';

/// Module 2: Playlist Import page.
///
/// Two tabs:
///   1) 🔗 链接导入 — paste a QQ / NetEase Cloud playlist URL, parse, choose
///      tracks, batch-search Fangpi candidates and download. The download
///      endpoint triggers BPM / key / phrase / stem-separation analysis in the
///      background, so the user only needs to wait until status is `completed`.
///   2) 🎭 Vibe 搜索 — natural-language semantic search via
///      `/api/recommendations/vibe-search`. Local-library matches are surfaced
///      with a "已入库" badge; Spotify candidates can be auto-imported through
///      `/api/recommendations/import-from-vibe`.
class PlaylistImportPage extends StatefulWidget {
  const PlaylistImportPage({
    super.key,
    required this.apiClient,
    required this.token,
    required this.userId,
    this.onImported,
  });

  final HarBeatApiClient apiClient;
  final String token;
  final int userId;
  final Future<void> Function()? onImported;

  @override
  State<PlaylistImportPage> createState() => _PlaylistImportPageState();
}

class _PlaylistImportPageState extends State<PlaylistImportPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('导入歌单'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.link), text: '链接导入'),
            Tab(icon: Icon(Icons.search), text: '单曲搜索'),
            Tab(icon: Icon(Icons.auto_awesome), text: 'Vibe'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          UrlImportTab(
            apiClient: widget.apiClient,
            token: widget.token,
            onImported: widget.onImported,
          ),
          SingleSearchTab(
            apiClient: widget.apiClient,
            token: widget.token,
            onImported: widget.onImported,
          ),
          VibeImportTab(
            apiClient: widget.apiClient,
            token: widget.token,
            userId: widget.userId,
            onImported: widget.onImported,
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 1: URL import
// ─────────────────────────────────────────────────────────────────────────────

enum _UrlStage { input, select, downloading, done }

class _TrackRow {
  _TrackRow({required this.track, this.selected = true});

  final ExternalPlaylistTrack track;
  bool selected;
  // status: pending | in-library | no-source | downloading | done | failed
  String status = 'pending';
  String? error;
  FangpiCandidate? chosen;
  List<FangpiCandidate> alternatives = const [];
  LibrarySong? imported;
}

class UrlImportTab extends StatefulWidget {
  const UrlImportTab({
    super.key,
    required this.apiClient,
    required this.token,
    this.onImported,
  });

  final HarBeatApiClient apiClient;
  final String token;
  final Future<void> Function()? onImported;

  @override
  State<UrlImportTab> createState() => _UrlImportTabState();
}

class _UrlImportTabState extends State<UrlImportTab> {
  final _urlController = TextEditingController();
  final _nameController = TextEditingController();
  _UrlStage _stage = _UrlStage.input;
  bool _busy = false;
  String? _error;
  ParsedExternalPlaylist? _parsed;
  final List<_TrackRow> _rows = [];
  int _progress = 0;

  @override
  void dispose() {
    _urlController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _parse() async {
    final url = _urlController.text.trim();
    if (url.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final parsed = await widget.apiClient.parseExternalPlaylist(
        token: widget.token,
        url: url,
      );
      setState(() {
        _parsed = parsed;
        _nameController.text = parsed.name;
        _rows
          ..clear()
          ..addAll(parsed.tracks.map((t) => _TrackRow(track: t)));
        _stage = _UrlStage.select;
      });
    } catch (e) {
      setState(() => _error = '解析失败: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _downloadAll() async {
    final selectedRows = _rows.where((r) => r.selected).toList();
    if (selectedRows.isEmpty) {
      setState(() => _error = '请至少选择一首歌');
      return;
    }

    setState(() {
      _stage = _UrlStage.downloading;
      _progress = 0;
      _error = null;
      for (final r in selectedRows) {
        r.status = 'pending';
        r.error = null;
        r.imported = null;
        r.chosen = null;
        r.alternatives = const [];
      }
    });

    // ── Step 1: load user library and mark already-imported tracks ──────
    Set<String> libraryKeys = {};
    try {
      final lib = await widget.apiClient.getLibrarySongs(widget.token);
      libraryKeys = lib
          .map((s) => _normKey(s.title, s.artist))
          .where((k) => k.isNotEmpty)
          .toSet();
    } catch (_) {
      // If library fetch fails, fall back to backend-side dedup only.
    }

    final pendingRows = <_TrackRow>[];
    for (final r in selectedRows) {
      if (libraryKeys.contains(_normKey(r.track.title, r.track.artist))) {
        r.status = 'in-library';
      } else {
        pendingRows.add(r);
      }
    }
    if (mounted) setState(() {});

    // ── Step 2: batch search candidates for non-library rows ────────────
    if (pendingRows.isNotEmpty) {
      try {
        final batch = await widget.apiClient.batchSearchExternal(
          token: widget.token,
          tracks: pendingRows.map((r) => r.track).toList(),
        );
        for (var i = 0; i < pendingRows.length && i < batch.length; i++) {
          final row = pendingRows[i];
          final entry = batch[i];
          if (entry.found && entry.candidates.isNotEmpty) {
            row.chosen = entry.candidates.first;
            row.alternatives = entry.candidates.length > 1
                ? entry.candidates.sublist(1)
                : const [];
          } else {
            row.status = 'no-source';
          }
        }
      } catch (e) {
        setState(() => _error = '批量搜索失败: $e');
        return;
      }
    }
    if (mounted) setState(() {});

    // ── Step 3: parallel download (concurrency = 3); fire-and-forget analysis ──
    final downloadable = pendingRows
        .where((r) => r.chosen != null && r.status != 'no-source')
        .toList();
    final imported = <LibrarySong>[];
    int done = 0;

    Future<void> downloadOne(_TrackRow row) async {
      row.status = 'downloading';
      if (mounted) setState(() {});
      try {
        final song = await widget.apiClient.downloadFangpiCandidate(
          token: widget.token,
          candidate: row.chosen!,
        );
        row.imported = song;
        row.status = 'done';
        imported.add(song);
      } catch (e) {
        row.error = e.toString();
        row.status = 'failed';
      } finally {
        done++;
        if (mounted) {
          setState(() => _progress = done);
        }
      }
    }

    await _runWithConcurrency<_TrackRow>(
      downloadable,
      3,
      downloadOne,
    );

    // ── Step 4: 2nd-pass retry for failed (try alternate candidate, then
    //            fresh search if no alt available) ─────────────────────────
    final failed = downloadable.where((r) => r.status == 'failed').toList();
    if (failed.isNotEmpty) {
      for (final row in failed) {
        row.status = 'downloading';
        row.error = null;
      }
      if (mounted) setState(() {});

      Future<void> retryOne(_TrackRow row) async {
        // 1) try next alternative if any
        if (row.alternatives.isNotEmpty) {
          row.chosen = row.alternatives.first;
          row.alternatives = row.alternatives.length > 1
              ? row.alternatives.sublist(1)
              : const [];
        } else {
          // 2) re-search via single-song endpoint (smart_search hits fangpi+kuwo+...)
          try {
            final hits = await widget.apiClient.searchFangpi(
              token: widget.token,
              query: '${row.track.title} ${row.track.artist}',
            );
            if (hits.isEmpty) {
              row.status = 'failed';
              row.error = '无可用音源';
              if (mounted) setState(() {});
              return;
            }
            row.chosen = FangpiCandidate(
              id: hits.first.id,
              title: hits.first.title,
              artist: hits.first.artist,
              source: hits.first.source ?? 'fangpi',
            );
          } catch (e) {
            row.status = 'failed';
            row.error = '重试搜索失败: $e';
            if (mounted) setState(() {});
            return;
          }
        }
        try {
          final song = await widget.apiClient.downloadFangpiCandidate(
            token: widget.token,
            candidate: row.chosen!,
          );
          row.imported = song;
          row.status = 'done';
          imported.add(song);
        } catch (e) {
          row.status = 'failed';
          row.error = e.toString();
        } finally {
          if (mounted) setState(() {});
        }
      }

      await _runWithConcurrency<_TrackRow>(failed, 2, retryOne);
    }

    setState(() {
      _progress = downloadable.length;
      _stage = _UrlStage.done;
    });

    // ── Step 5: optionally create a new playlist with all in-library +
    //            successfully-downloaded songs ─────────────────────────────
    final name = _nameController.text.trim();
    final playlistSongIds = <String>[
      ...selectedRows
          .where((r) => r.status == 'in-library')
          .map((r) => _findLibraryId(libraryKeys, r))
          .whereType<String>(),
      ...imported.map((s) => s.id),
    ];
    if (name.isNotEmpty && playlistSongIds.isNotEmpty) {
      try {
        final pid = await widget.apiClient.createPlaylist(
          token: widget.token,
          name: name,
        );
        await widget.apiClient.addSongsToPlaylist(
          token: widget.token,
          playlistId: pid,
          librarySongIds: playlistSongIds,
        );
      } catch (e) {
        setState(() => _error = '已下载，但创建歌单失败: $e');
      }
    }

    if (widget.onImported != null) {
      await widget.onImported!();
    }
  }

  String _normKey(String title, String artist) {
    return '${title.trim().toLowerCase()}|${artist.trim().toLowerCase()}';
  }

  /// Only used to skip dedup-songs without re-querying library; we don't
  /// need actual IDs unless adding to a playlist. Returns null safely.
  String? _findLibraryId(Set<String> _, _TrackRow __) => null;

  Future<void> _runWithConcurrency<T>(
    List<T> items,
    int concurrency,
    Future<void> Function(T) worker,
  ) async {
    final iter = items.iterator;
    final futures = <Future<void>>[];
    for (var i = 0; i < concurrency; i++) {
      futures.add(Future(() async {
        while (true) {
          T item;
          if (!iter.moveNext()) return;
          item = iter.current;
          await worker(item);
        }
      }));
    }
    await Future.wait(futures);
  }

  void _reset() {
    setState(() {
      _stage = _UrlStage.input;
      _busy = false;
      _error = null;
      _parsed = null;
      _rows.clear();
      _urlController.clear();
      _nameController.clear();
      _progress = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    switch (_stage) {
      case _UrlStage.input:
        return _buildInput();
      case _UrlStage.select:
        return _buildSelect();
      case _UrlStage.downloading:
        return _buildDownloading();
      case _UrlStage.done:
        return _buildDone();
    }
  }

  Widget _buildInput() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('粘贴歌单链接', style: TextStyle(fontSize: 16)),
          const SizedBox(height: 6),
          const Text(
            '支持 QQ 音乐 / 网易云音乐 公开歌单的分享链接',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _urlController,
            maxLines: 3,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: 'https://y.music.163.com/m/playlist?id=...',
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _busy ? null : _parse,
            icon: const Icon(Icons.search),
            label: Text(_busy ? '解析中...' : '解析歌单'),
          ),
        ],
      ),
    );
  }

  Widget _buildSelect() {
    final selectedCount = _rows.where((r) => r.selected).length;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _nameController,
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  labelText: '新歌单名称（留空则不创建歌单，仅入库）',
                ),
              ),
              const SizedBox(height: 6),
              Row(
                children: [
                  Text('共 ${_rows.length} 首 · 已选 $selectedCount'),
                  const Spacer(),
                  TextButton(
                    onPressed: () => setState(() {
                      final allSelected = _rows.every((r) => r.selected);
                      for (final r in _rows) {
                        r.selected = !allSelected;
                      }
                    }),
                    child: const Text('全选/全不选'),
                  ),
                ],
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: ListView.builder(
            itemCount: _rows.length,
            itemBuilder: (context, i) {
              final r = _rows[i];
              return CheckboxListTile(
                value: r.selected,
                onChanged: (v) => setState(() => r.selected = v ?? false),
                title: Text(r.track.title),
                subtitle: Text(r.track.artist),
              );
            },
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _reset,
                    child: const Text('返回'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  flex: 2,
                  child: FilledButton.icon(
                    onPressed: selectedCount == 0 ? null : _downloadAll,
                    icon: const Icon(Icons.download),
                    label: Text('开始导入 ($selectedCount 首)'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDownloading() {
    final selectedRows = _rows.where((r) => r.selected).toList();
    final downloadable = selectedRows
        .where((r) => r.status != 'in-library' && r.status != 'no-source')
        .length;
    return Column(
      children: [
        const SizedBox(height: 12),
        LinearProgressIndicator(
          value: downloadable == 0 ? null : (_progress / downloadable).clamp(0.0, 1.0),
        ),
        Padding(
          padding: const EdgeInsets.all(12),
          child: Text('正在下载 $_progress / $downloadable（已入库的歌曲自动跳过）'),
        ),
        const Divider(height: 1),
        Expanded(
          child: ListView.builder(
            itemCount: selectedRows.length,
            itemBuilder: (context, i) {
              final r = selectedRows[i];
              return ListTile(
                dense: true,
                leading: _statusIcon(r.status),
                title: Text(r.track.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                subtitle: Text(
                  '${r.track.artist} · ${_statusText(r)}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildDone() {
    final selectedRows = _rows.where((r) => r.selected).toList();
    final inLib = selectedRows.where((r) => r.status == 'in-library').length;
    final ok = selectedRows.where((r) => r.status == 'done').length;
    final noSrc = selectedRows.where((r) => r.status == 'no-source').length;
    final fail = selectedRows.where((r) => r.status == 'failed').length;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 12),
          const Icon(Icons.check_circle, color: Colors.green, size: 56),
          const SizedBox(height: 12),
          Text(
            '导入完成\n已入库 $inLib · 新下载 $ok · 无音源 $noSrc · 失败 $fail',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 15),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!,
                style: const TextStyle(color: Colors.red),
                textAlign: TextAlign.center),
          ],
          const SizedBox(height: 8),
          const Text(
            '所有下载已完成；BPM/调性/段落/分轨分析在后台继续。',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey, fontSize: 12),
          ),
          const SizedBox(height: 12),
          Expanded(
            child: ListView.builder(
              itemCount: selectedRows.length,
              itemBuilder: (context, i) {
                final r = selectedRows[i];
                return ListTile(
                  dense: true,
                  leading: _statusIcon(r.status),
                  title: Text(r.track.title,
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                  subtitle: Text(
                    '${r.track.artist} · ${_statusText(r)}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                );
              },
            ),
          ),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _reset,
                  child: const Text('再导一个'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: FilledButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('完成'),
                ),
              ),
            ],
          ),
          const SafeArea(top: false, child: SizedBox(height: 0)),
        ],
      ),
    );
  }

  Widget _statusIcon(String status) {
    switch (status) {
      case 'done':
        return const Icon(Icons.check_circle, color: Colors.green);
      case 'failed':
        return const Icon(Icons.error_outline, color: Colors.red);
      case 'no-source':
        return const Icon(Icons.cloud_off, color: Colors.grey);
      case 'in-library':
        return const Icon(Icons.library_music, color: Colors.blue);
      case 'downloading':
        return const SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        );
      default:
        return const Icon(Icons.radio_button_unchecked, color: Colors.grey);
    }
  }

  String _statusText(_TrackRow r) {
    switch (r.status) {
      case 'in-library':
        return '已在曲库，跳过';
      case 'done':
        return '已下载，后台分析中';
      case 'downloading':
        return '下载中...';
      case 'no-source':
        return '无可用音源';
      case 'failed':
        return r.error ?? '下载失败';
      default:
        return '排队中';
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 2: Single-song search (search → download one)
// ─────────────────────────────────────────────────────────────────────────────

class SingleSearchTab extends StatefulWidget {
  const SingleSearchTab({
    super.key,
    required this.apiClient,
    required this.token,
    this.onImported,
  });

  final HarBeatApiClient apiClient;
  final String token;
  final Future<void> Function()? onImported;

  @override
  State<SingleSearchTab> createState() => _SingleSearchTabState();
}

class _SingleSearchTabState extends State<SingleSearchTab> {
  final _controller = TextEditingController();
  bool _loading = false;
  String? _error;
  List<FangpiSong> _results = const [];
  Set<String> _libraryKeys = {};
  final Set<String> _downloading = {};
  final Set<String> _done = {};

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  String _normKey(String title, String artist) =>
      '${title.trim().toLowerCase()}|${artist.trim().toLowerCase()}';

  Future<void> _loadLibraryKeys() async {
    try {
      final lib = await widget.apiClient.getLibrarySongs(widget.token);
      _libraryKeys = lib.map((s) => _normKey(s.title, s.artist)).toSet();
    } catch (_) {
      _libraryKeys = {};
    }
  }

  Future<void> _search() async {
    final q = _controller.text.trim();
    if (q.isEmpty) return;
    setState(() {
      _loading = true;
      _error = null;
      _results = const [];
    });
    try {
      await _loadLibraryKeys();
      final hits = await widget.apiClient.searchFangpi(
        token: widget.token,
        query: q,
      );
      setState(() => _results = hits);
    } catch (e) {
      setState(() => _error = '搜索失败: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _download(FangpiSong s) async {
    final key = _normKey(s.title, s.artist);
    if (_libraryKeys.contains(key) || _done.contains(key)) return;
    setState(() => _downloading.add(key));
    try {
      await widget.apiClient.downloadFangpi(token: widget.token, song: s);
      _done.add(key);
      _libraryKeys.add(key);
      if (widget.onImported != null) await widget.onImported!();
    } catch (e) {
      setState(() => _error = '下载失败: $e');
    } finally {
      if (mounted) setState(() => _downloading.remove(key));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  onSubmitted: (_) => _search(),
                  decoration: const InputDecoration(
                    border: OutlineInputBorder(),
                    hintText: '输入歌名 / 艺人，如：周杰伦 稻香',
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _loading ? null : _search,
                child: Text(_loading ? '搜索中' : '搜索'),
              ),
            ],
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(_error!, style: const TextStyle(color: Colors.red)),
          ),
        const Divider(height: 1),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _results.isEmpty
                  ? const Center(
                      child: Text('搜索任意歌曲，免费音源直接下载到曲库',
                          style: TextStyle(color: Colors.grey)),
                    )
                  : ListView.separated(
                      itemCount: _results.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, i) {
                        final s = _results[i];
                        final key = _normKey(s.title, s.artist);
                        final inLib = _libraryKeys.contains(key);
                        final downloading = _downloading.contains(key);
                        return ListTile(
                          dense: true,
                          title: Text(s.title,
                              maxLines: 1, overflow: TextOverflow.ellipsis),
                          subtitle: Text(
                            '${s.artist} · ${s.source ?? "fangpi"}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          trailing: inLib
                              ? const Chip(
                                  label: Text('已入库',
                                      style: TextStyle(fontSize: 11)),
                                  visualDensity: VisualDensity.compact,
                                )
                              : downloading
                                  ? const SizedBox(
                                      width: 22,
                                      height: 22,
                                      child: CircularProgressIndicator(
                                          strokeWidth: 2),
                                    )
                                  : IconButton(
                                      icon: const Icon(Icons.download),
                                      tooltip: '下载到曲库',
                                      onPressed: () => _download(s),
                                    ),
                        );
                      },
                    ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 3: Vibe search
// ─────────────────────────────────────────────────────────────────────────────

const _kMoodPresets = <_MoodPreset>[
  _MoodPreset('🔥 Battle 炸场', 'battle炸场 高能量 hard hitting beats'),
  _MoodPreset('🌊 Chill Vibes', '放松 chill groovy 轻松氛围'),
  _MoodPreset('💃 Waacking 华丽', 'waacking disco funk 华丽 dramatic'),
  _MoodPreset('🎭 Popping 机械', 'popping funk electronic 机械感 robot'),
  _MoodPreset('🌙 夜晚慢歌', '深夜 慢歌 r&b smooth 抒情'),
  _MoodPreset('⚡ House 律动', 'house dance 律动 groovy bounce'),
];

class _MoodPreset {
  const _MoodPreset(this.label, this.query);
  final String label;
  final String query;
}

class VibeImportTab extends StatefulWidget {
  const VibeImportTab({
    super.key,
    required this.apiClient,
    required this.token,
    required this.userId,
    this.onImported,
  });

  final HarBeatApiClient apiClient;
  final String token;
  final int userId;
  final Future<void> Function()? onImported;

  @override
  State<VibeImportTab> createState() => _VibeImportTabState();
}

class _VibeImportTabState extends State<VibeImportTab> {
  final _queryController = TextEditingController();
  bool _loading = false;
  String? _error;
  VibeSearchResult? _result;
  final Set<String> _importing = {};
  final Set<String> _imported = {};

  @override
  void dispose() {
    _queryController.dispose();
    super.dispose();
  }

  Future<void> _search([String? override]) async {
    final q = (override ?? _queryController.text).trim();
    if (q.isEmpty) return;
    if (override != null) _queryController.text = override;
    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });
    try {
      final res = await widget.apiClient.vibeSearch(
        token: widget.token,
        query: q,
        userId: widget.userId,
      );
      setState(() => _result = res);
    } catch (e) {
      setState(() => _error = 'Vibe 搜索失败: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _importSong(VibeSong song) async {
    final key = song.spotifyId ?? '${song.title}-${song.artist}';
    if (song.inLibrary) return;
    setState(() {
      _importing.add(key);
      _error = null;
    });
    try {
      // 复用单曲搜索导入路径：title + artist → searchFangpi → downloadFangpi(first hit)。
      // 比 importFromVibe（再跑一次 Spotify+CLAP+yt-dlp）快得多，也不容易超时。
      final hits = await widget.apiClient.searchFangpi(
        token: widget.token,
        query: '${song.title} ${song.artist}'.trim(),
      );
      if (hits.isEmpty) {
        throw Exception('未找到可用音源');
      }
      await widget.apiClient.downloadFangpi(
        token: widget.token,
        song: hits.first,
      );
      _imported.add(key);
      if (widget.onImported != null) await widget.onImported!();
    } catch (e) {
      setState(() => _error = '导入失败: $e');
    } finally {
      if (mounted) setState(() => _importing.remove(key));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _queryController,
                      onSubmitted: (_) => _search(),
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        hintText: '描述你想要的音乐氛围... 例如: 深夜popping cypher 低沉有力',
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _loading ? null : () => _search(),
                    child: Text(_loading ? '搜索中' : '🔍 搜索'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: _kMoodPresets
                      .map(
                        (p) => Padding(
                          padding: const EdgeInsets.only(right: 6),
                          child: ActionChip(
                            label: Text(p.label,
                                style: const TextStyle(fontSize: 12)),
                            onPressed:
                                _loading ? null : () => _search(p.query),
                          ),
                        ),
                      )
                      .toList(),
                ),
              ),
            ],
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(_error!, style: const TextStyle(color: Colors.red)),
          ),
        const Divider(height: 1),
        Expanded(child: _buildResults()),
      ],
    );
  }

  Widget _buildResults() {
    if (_loading) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 12),
            Text('正在用 CLAP + Spotify 搜索...',
                style: TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }
    final result = _result;
    if (result == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            '用自然语言描述你想要的音乐氛围，或点上方的预设氛围标签开始',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey),
          ),
        ),
      );
    }
    if (result.songs.isEmpty) {
      return const Center(child: Text('没有找到匹配的音乐，试试换个描述？'));
    }
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      itemCount: result.songs.length + 1,
      itemBuilder: (context, i) {
        if (i == 0) {
          return Padding(
            padding: const EdgeInsets.all(12),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Text('🎭 Vibe 解读: ',
                            style: TextStyle(fontWeight: FontWeight.bold)),
                        Expanded(child: Text(result.vibeDescription)),
                      ],
                    ),
                    if (result.genres.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: result.genres
                            .map((g) => Chip(
                                  label: Text(g,
                                      style: const TextStyle(fontSize: 11)),
                                  visualDensity: VisualDensity.compact,
                                ))
                            .toList(),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          );
        }
        final song = result.songs[i - 1];
        return _buildSongTile(song);
      },
    );
  }

  Widget _buildSongTile(VibeSong song) {
    final key = song.spotifyId ?? '${song.title}-${song.artist}';
    final isImporting = _importing.contains(key);
    final wasImported = _imported.contains(key);
    final inLib = song.inLibrary || wasImported;
    final matchColor = song.matchPercentage >= 70
        ? Colors.green
        : song.matchPercentage >= 40
            ? Colors.orange
            : Colors.grey;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: ListTile(
        leading: song.albumArt != null && song.albumArt!.isNotEmpty
            ? ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: Image.network(
                  song.albumArt!,
                  width: 44,
                  height: 44,
                  fit: BoxFit.cover,
                  errorBuilder: (_, _, _) => const Icon(Icons.music_note),
                ),
              )
            : CircleAvatar(
                child: Icon(song.source == 'local'
                    ? Icons.library_music
                    : Icons.music_note),
              ),
        title: Text(song.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          [
            song.artist,
            if (song.style != null) song.style,
            song.source == 'local' ? '曲库' : 'Spotify',
          ].whereType<String>().join(' · '),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '${song.matchPercentage.round()}%',
              style:
                  TextStyle(color: matchColor, fontWeight: FontWeight.bold),
            ),
            const SizedBox(width: 8),
            if (inLib)
              const Chip(
                label: Text('已入库', style: TextStyle(fontSize: 10)),
                visualDensity: VisualDensity.compact,
                backgroundColor: Color(0x3300C853),
              )
            else if (isImporting)
              const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            else
              IconButton(
                icon: const Icon(Icons.add_circle_outline),
                tooltip: '导入到曲库',
                onPressed: () => _importSong(song),
              ),
          ],
        ),
      ),
    );
  }
}
