import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../state/providers.dart';
import '../state/mixtape_provider.dart';

/// Mixtape 待混音清单 —— 对齐网页 DJ Session "MIXTAPE 待混音列表" 区块
///   方式 A：歌单 URL 导入（/api/fangpi/parse-playlist + /import-songs）
///   方式 B：风格标签搜索（/api/fangpi/vibe-search mode=style）
///   方式 C：VIBE 语义搜索（/api/fangpi/vibe-search mode=vibe）
class MixtapePage extends ConsumerStatefulWidget {
  /// 进入页面时默认选中的方式：0=导入歌单 1=曲库导入 2=语义搜索
  final int initialTab;
  const MixtapePage({super.key, this.initialTab = 0});

  @override
  ConsumerState<MixtapePage> createState() => _MixtapePageState();
}

class _MixtapePageState extends ConsumerState<MixtapePage>
    with SingleTickerProviderStateMixin {
  late final TabController _tab;

  // 方式 A：URL 解析
  final _urlCtrl = TextEditingController();
  bool _parsing = false;
  List<Map<String, dynamic>> _parsedCandidates = [];
  final Set<int> _parsedSelected = {};

  // 方式 B：曲库（直接拉取用户的全部已分析歌曲）
  bool _libraryLoading = false;
  String _libraryQuery = '';
  final _libraryQueryCtrl = TextEditingController();
  List<Map<String, dynamic>> _librarySongs = [];
  String? _libraryError;

  // 方式 C：VIBE 搜索
  final _vibeCtrl = TextEditingController();
  bool _vibeSearching = false;
  List<Map<String, dynamic>> _vibeLocal = [];
  List<Map<String, dynamic>> _vibeExternal = [];

  static const List<String> _styles = [
    'hiphop', 'breaking', 'popping', 'locking', 'krump', 'waacking',
    'vogue', 'house', 'urban', 'commercial', 'jazzfunk', 'contemporary',
  ];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_librarySongs.isEmpty && !_libraryLoading && _libraryError == null) {
      // 首次进入页面时自动拉一次曲库
      _loadLibrary();
    }
  }

  @override
  void initState() {
    super.initState();
    _tab = TabController(
      length: 3,
      vsync: this,
      initialIndex: widget.initialTab.clamp(0, 2),
    );
  }

  @override
  void dispose() {
    _tab.dispose();
    _urlCtrl.dispose();
    _vibeCtrl.dispose();
    _libraryQueryCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final mixtape = ref.watch(mixtapeProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text('📋 Mixtape  (${mixtape.length})'),
        bottom: TabBar(
          controller: _tab,
          isScrollable: true,
          tabs: const [
            Tab(text: '导入歌单 (URL)'),
            Tab(text: '曲库'),
            Tab(text: '语义搜索 (VIBE)'),
          ],
        ),
        actions: [
          IconButton(
            tooltip: '清空待混音清单',
            icon: const Icon(Icons.delete_sweep),
            onPressed: mixtape.isEmpty
                ? null
                : () {
                    ref.read(mixtapeProvider.notifier).clear();
                  },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: TabBarView(
              controller: _tab,
              children: [
                _tabUrl(),
                _tabLibrary(),
                _tabVibe(),
              ],
            ),
          ),
          const Divider(height: 1),
          _mixtapeListView(mixtape),
        ],
      ),
    );
  }

  // ─────────── 方式 A：URL ───────────
  Widget _tabUrl() {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('支持：网易云 / QQ 音乐 / fangpi 歌单链接',
              style: TextStyle(fontSize: 12, color: Colors.grey)),
          const SizedBox(height: 8),
          TextField(
            controller: _urlCtrl,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: 'https://music.163.com/playlist?id=...',
              isDense: true,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _parsing ? null : _parsePlaylist,
                  icon: _parsing
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.link),
                  label: const Text('解析'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _parsedCandidates.isEmpty
                      ? null
                      : () => _addCandidates(
                          _parsedCandidates
                              .asMap()
                              .entries
                              .where((e) => _parsedSelected.contains(e.key))
                              .map((e) => e.value)
                              .toList(),
                          source: 'fangpi'),
                  icon: const Icon(Icons.add),
                  label: Text('导入选中 (${_parsedSelected.length})'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _parsedCandidates.isEmpty
                      ? null
                      : () => _addCandidates(_parsedCandidates, source: 'fangpi'),
                  icon: const Icon(Icons.done_all),
                  label: const Text('全导入'),
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (_parsedCandidates.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 24),
              child: Text('粘贴歌单 URL 后点击 "解析"',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey)),
            )
          else
            Expanded(
              child: ListView.separated(
                itemCount: _parsedCandidates.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final c = _parsedCandidates[i];
                  final sel = _parsedSelected.contains(i);
                  return CheckboxListTile(
                    dense: true,
                    value: sel,
                    onChanged: (v) {
                      setState(() {
                        if (v == true) {
                          _parsedSelected.add(i);
                        } else {
                          _parsedSelected.remove(i);
                        }
                      });
                    },
                    title: Text('${c['title'] ?? '?'}',
                        maxLines: 1, overflow: TextOverflow.ellipsis),
                    subtitle: Text('${c['artist'] ?? 'Unknown'}',
                        style: const TextStyle(fontSize: 11)),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }

  // ─────────── 方式 B：曲库 ───────────
  Widget _tabLibrary() {
    final filtered = _filteredLibrary();
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _libraryQueryCtrl,
                  decoration: const InputDecoration(
                    border: OutlineInputBorder(),
                    hintText: '搜索曲库（标题 / 艺人）',
                    isDense: true,
                    prefixIcon: Icon(Icons.search, size: 18),
                  ),
                  onChanged: (v) => setState(() => _libraryQuery = v.trim()),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: '刷新曲库',
                onPressed: _libraryLoading ? null : _loadLibrary,
                icon: _libraryLoading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.refresh),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Text('共 ${_librarySongs.length} 首·当前显示 ${filtered.length}',
                  style: const TextStyle(fontSize: 11, color: Colors.grey)),
              const Spacer(),
              if (filtered.isNotEmpty)
                TextButton.icon(
                  onPressed: () => _addCandidates(filtered, source: 'library'),
                  icon: const Icon(Icons.playlist_add, size: 16),
                  label: Text('全部加入 (${filtered.length})'),
                ),
            ],
          ),
          const Divider(height: 8),
          Expanded(
            child: _libraryError != null
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Text(
                        '加载失败：$_libraryError\n点右上角刷新重试',
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: Colors.red, fontSize: 12),
                      ),
                    ),
                  )
                : (_libraryLoading && filtered.isEmpty)
                    ? const Center(child: CircularProgressIndicator())
                    : filtered.isEmpty
                        ? const Center(
                            child: Text(
                              '曲库为空。请先通过“导入歌单”或“语义搜索”添加歌曲。',
                              style:
                                  TextStyle(color: Colors.grey, fontSize: 12),
                            ),
                          )
                        : ListView.builder(
                            itemCount: filtered.length,
                            itemBuilder: (_, i) {
                              final c = filtered[i];
                              final bpm = c['bpm'];
                              final dur = c['duration'];
                              final key = c['camelot_key'] ?? c['key'] ?? '';
                              final status =
                                  (c['analysis_status'] ?? '').toString();
                              return ListTile(
                                dense: true,
                                contentPadding: const EdgeInsets.symmetric(
                                    horizontal: 4),
                                title: Text(
                                  (c['title'] ?? '?').toString(),
                                  style: const TextStyle(fontSize: 13),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                subtitle: Text(
                                  '${c['artist'] ?? '?'}'
                                  '${bpm != null ? '  · ${(bpm is num) ? bpm.toStringAsFixed(0) : bpm} BPM' : ''}'
                                  '${key != '' ? '  · $key' : ''}'
                                  '${dur is num ? '  · ${(dur ~/ 60).toString().padLeft(1, '0')}:${(dur.toInt() % 60).toString().padLeft(2, '0')}' : ''}',
                                  style: const TextStyle(fontSize: 11),
                                ),
                                trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    if (status.isNotEmpty &&
                                        status != 'completed')
                                      Padding(
                                        padding: const EdgeInsets.only(
                                            right: 4),
                                        child: Text(status,
                                            style: const TextStyle(
                                                fontSize: 10,
                                                color: Colors.orange)),
                                      ),
                                    IconButton(
                                      iconSize: 20,
                                      icon: const Icon(Icons.add_circle,
                                          color: Colors.green),
                                      tooltip: '+ 加入待混音',
                                      onPressed: () => _addCandidates([c],
                                          source: 'library'),
                                    ),
                                  ],
                                ),
                              );
                            },
                          ),
          ),
        ],
      ),
    );
  }

  List<Map<String, dynamic>> _filteredLibrary() {
    if (_libraryQuery.isEmpty) return _librarySongs;
    final q = _libraryQuery.toLowerCase();
    return _librarySongs.where((c) {
      final t = (c['title'] ?? '').toString().toLowerCase();
      final a = (c['artist'] ?? '').toString().toLowerCase();
      return t.contains(q) || a.contains(q);
    }).toList();
  }

  // ─────────── 方式 C：VIBE ───────────
  Widget _tabVibe() {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            controller: _vibeCtrl,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: '例：午夜霓虹 trap / 节奏强烈的 hiphop / 慢摇 chill',
              isDense: true,
            ),
            maxLines: 2,
          ),
          const SizedBox(height: 8),
          ElevatedButton.icon(
            onPressed: _vibeSearching ? null : _searchByVibe,
            icon: _vibeSearching
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.auto_awesome),
            label: const Text('VIBE 语义搜索'),
            style: ElevatedButton.styleFrom(
                backgroundColor: Colors.purple,
                foregroundColor: Colors.white),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: _candidateLists('本地', _vibeLocal, '外部候选', _vibeExternal),
          ),
        ],
      ),
    );
  }

  Widget _candidateLists(String leftLabel, List<Map<String, dynamic>> left,
      String rightLabel, List<Map<String, dynamic>> right) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: _candidateColumn('$leftLabel (${left.length})', left, isLocal: true)),
        const VerticalDivider(),
        Expanded(child: _candidateColumn('$rightLabel (${right.length})', right, isLocal: false)),
      ],
    );
  }

  Widget _candidateColumn(String title, List<Map<String, dynamic>> items,
      {required bool isLocal}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
          child: Text(title,
              style: const TextStyle(
                  fontSize: 12, fontWeight: FontWeight.bold)),
        ),
        Expanded(
          child: items.isEmpty
              ? const Center(
                  child: Text('--',
                      style: TextStyle(color: Colors.grey, fontSize: 12)))
              : ListView.builder(
                  itemCount: items.length,
                  itemBuilder: (_, i) {
                    final c = items[i];
                    final title = c['title']?.toString() ?? '?';
                    final artist = c['artist']?.toString() ?? '';
                    return ListTile(
                      dense: true,
                      contentPadding:
                          const EdgeInsets.symmetric(horizontal: 4),
                      title: Text(title,
                          style: const TextStyle(fontSize: 12),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis),
                      subtitle: Text(artist,
                          style: const TextStyle(fontSize: 10)),
                      trailing: IconButton(
                        iconSize: 18,
                        icon: const Icon(Icons.add_circle, color: Colors.green),
                        tooltip: '+ 加入待混音',
                        onPressed: () => _addCandidates([c],
                            source: isLocal ? 'library' : 'fangpi'),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  // ─────────── 待混音清单视图 ───────────
  Widget _mixtapeListView(List<MixtapeItem> items) {
    return Container(
      height: 160,
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Text('🎚 待混音清单 (${items.length})',
                style: const TextStyle(
                    fontSize: 12, fontWeight: FontWeight.bold)),
          ),
          Expanded(
            child: items.isEmpty
                ? const Center(
                    child: Text('从上方搜索结果或歌单解析中点击 + 加入待混音',
                        style: TextStyle(color: Colors.grey, fontSize: 12)))
                : ListView.builder(
                    itemCount: items.length,
                    itemBuilder: (_, i) {
                      final it = items[i];
                      return Dismissible(
                        key: ValueKey('${it.title}-${it.artist}-$i'),
                        background: Container(color: Colors.red),
                        onDismissed: (_) =>
                            ref.read(mixtapeProvider.notifier).removeAt(i),
                        child: ListTile(
                          dense: true,
                          leading: CircleAvatar(
                            radius: 12,
                            child: Text('${i + 1}',
                                style: const TextStyle(fontSize: 11)),
                          ),
                          title: Text(it.title,
                              style: const TextStyle(fontSize: 12),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis),
                          subtitle: Text(it.artist,
                              style: const TextStyle(fontSize: 10)),
                          trailing: IconButton(
                            icon: const Icon(Icons.close, size: 16),
                            onPressed: () => ref
                                .read(mixtapeProvider.notifier)
                                .removeAt(i),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  // ─────────── API 调用 ───────────

  Future<void> _parsePlaylist() async {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) {
      _snack('请粘贴歌单 URL');
      return;
    }
    setState(() {
      _parsing = true;
      _parsedCandidates = [];
      _parsedSelected.clear();
    });
    try {
      final jet = ref.read(jetsonClientProvider);
      final r = await jet.fangpiParsePlaylist(url);
      final data = (r['data'] ?? r) as Map<String, dynamic>;
      final list = (data['tracks'] ?? data['songs'] ?? data['candidates'] ?? [])
          as List;
      setState(() {
        _parsedCandidates = list
            .map<Map<String, dynamic>>((e) => Map<String, dynamic>.from(e))
            .toList();
        _parsedSelected.addAll(
            List.generate(_parsedCandidates.length, (i) => i));
      });
      _snack('解析到 ${_parsedCandidates.length} 首');
    } catch (e) {
      _snack('解析失败: ${_errMsg(e)}');
    } finally {
      if (mounted) setState(() => _parsing = false);
    }
  }

  Future<void> _loadLibrary() async {
    setState(() {
      _libraryLoading = true;
      _libraryError = null;
    });
    try {
      final jet = ref.read(jetsonClientProvider);
      final r = await jet.getLibrarySongs(onlyReady: false);
      final data = (r['data'] ?? r) as Map<String, dynamic>;
      final list = _coerceList(data['songs'] ?? data['list'] ?? data['items']);
      setState(() => _librarySongs = list);
    } catch (e) {
      setState(() => _libraryError = _errMsg(e));
    } finally {
      if (mounted) setState(() => _libraryLoading = false);
    }
  }

  Future<void> _searchByVibe() async {
    final vibe = _vibeCtrl.text.trim();
    if (vibe.isEmpty) {
      _snack('请输入 VIBE 描述');
      return;
    }
    setState(() {
      _vibeSearching = true;
      _vibeLocal = [];
      _vibeExternal = [];
    });
    try {
      final jet = ref.read(jetsonClientProvider);
      final r = await jet.fangpiVibeSearch(vibe: vibe, mode: 'vibe', limit: 20);
      final data = (r['data'] ?? r) as Map<String, dynamic>;
      setState(() {
        _vibeLocal = _coerceList(data['local'] ?? data['library']);
        _vibeExternal = _coerceList(
            data['external'] ?? data['online'] ?? data['fangpi']);
      });
    } catch (e) {
      _snack('VIBE 搜索失败: ${_errMsg(e)}');
    } finally {
      if (mounted) setState(() => _vibeSearching = false);
    }
  }

  void _addCandidates(List<Map<String, dynamic>> items, {required String source}) {
    final notifier = ref.read(mixtapeProvider.notifier);
    int added = 0;
    for (final c in items) {
      // library_song_id 必须是 UUID hex 字符串（服务器用于 LibrarySong.id 查表）。
      // 仅某些 URL 解析结果可能带着数字型 song_id——不能用作伪造的 UUID。
      String? rawLib = c['library_song_id']?.toString();
      if (rawLib != null && !_looksLikeUuid(rawLib)) rawLib = null;
      notifier.add(MixtapeItem(
        title: (c['title'] ?? '?').toString(),
        artist: (c['artist'] ?? 'Unknown').toString(),
        musicId: c['music_id']?.toString(),
        librarySongId: rawLib,
        songId: c['song_id'] is int
            ? c['song_id'] as int
            : int.tryParse(c['song_id']?.toString() ?? ''),
        source: source,
        tags: List<String>.from((c['tags'] ?? []) as List),
      ));
      added++;
    }
    _snack('已加入 $added 首');
  }

  static bool _looksLikeUuid(String s) {
    // 服务器 LibrarySong.id 是 32-字符 hex（去横线）或标准 8-4-4-4-12。
    final hex = s.replaceAll('-', '').toLowerCase();
    if (hex.length != 32) return false;
    return RegExp(r'^[0-9a-f]{32}$').hasMatch(hex);
  }

  List<Map<String, dynamic>> _coerceList(dynamic raw) {
    if (raw is List) {
      return raw.map<Map<String, dynamic>>((e) {
        if (e is Map) return Map<String, dynamic>.from(e);
        return {'title': e?.toString() ?? ''};
      }).toList();
    }
    return [];
  }

  String _errMsg(Object e) {
    if (e is DioException) {
      final code = e.response?.statusCode;
      if (code == 401) return '需要登录服务器（401）';
      if (code == 404) return '后端未启用该接口（404）';
      return e.message ?? e.toString();
    }
    return e.toString();
  }

  void _snack(String m) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));
  }
}
