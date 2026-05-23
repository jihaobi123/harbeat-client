import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/models/song.dart';
import '../../data/services/song_service.dart';
import '../../core/utils/logger.dart';
import '../../state/providers.dart';
import '../widgets/song_card.dart';
import '../widgets/mini_player.dart';
import 'song_detail_page.dart';

/// 音乐库页面
class LibraryPage extends ConsumerStatefulWidget {
  const LibraryPage({super.key});

  @override
  ConsumerState<LibraryPage> createState() => _LibraryPageState();
}

class _LibraryPageState extends ConsumerState<LibraryPage> {
  final SongService _songService = SongService();
  List<Song> _songs = [];
  List<Map<String, dynamic>> _rawSongs = [];
  bool _isLoading = true;
  String _searchQuery = '';
  
  @override
  void initState() {
    super.initState();
    _loadSongs();
  }
  
  Future<void> _loadSongs() async {
    setState(() => _isLoading = true);
    
    try {
      final raw = await _songService.getRawSongs(
        query: _searchQuery.isEmpty ? null : _searchQuery,
      );
      final songs = raw.map((m) => Song.fromJson(m)).toList();
      
      if (mounted) {
        setState(() {
          _songs = songs;
          _rawSongs = raw;
          _isLoading = false;
        });
      }
    } catch (e) {
      AppLogger.error('Load songs failed', error: e);
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('加载失败: $e')),
        );
      }
    }
  }
  
  Future<void> _cacheToRk(List<Song> songs) async {
    final libIds = songs
        .map((s) => s.libraryId)
        .whereType<String>()
        .toList();
    if (libIds.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('歌曲缺少 library_song_id，无法触发缓存')),
      );
      return;
    }
    final sync = ref.read(rkSyncServiceProvider);
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(SnackBar(
      content: Text('开始缓存 ${libIds.length} 首到 RK3588 …'),
      duration: const Duration(seconds: 2),
    ));

    // 进度对话框
    final progressNotifier = ValueNotifier<Map<String, dynamic>>({
      'percent': 0.0,
      'stage': 'init',
    });
    bool dialogOpen = true;
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('缓存到 RK3588'),
        content: ValueListenableBuilder<Map<String, dynamic>>(
          valueListenable: progressNotifier,
          builder: (_, value, __) {
            final p = (value['percent'] as num?)?.toDouble() ?? 0;
            final stage = value['stage'] ?? '';
            final done = value['done'] == true;
            final errs = (value['errors'] as List?) ?? const [];
            return SizedBox(
              width: 320,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  LinearProgressIndicator(value: (p / 100).clamp(0.0, 1.0)),
                  const SizedBox(height: 8),
                  Text('${p.toStringAsFixed(1)}%  ·  $stage'),
                  if (value['current_file'] != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        '当前：${value['current_file']}',
                        style: const TextStyle(fontSize: 12, color: Colors.grey),
                      ),
                    ),
                  if (done && errs.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        '错误：${errs.length} 个\n${errs.take(2).join("\n")}',
                        style: const TextStyle(color: Colors.red, fontSize: 12),
                      ),
                    ),
                  if (done && errs.isEmpty)
                    const Padding(
                      padding: EdgeInsets.only(top: 8),
                      child: Text('✓ 缓存完成', style: TextStyle(color: Colors.green)),
                    ),
                ],
              ),
            );
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('关闭'),
          ),
        ],
      ),
    ).whenComplete(() {
      dialogOpen = false;
    });

    try {
      await for (final ev in sync.cacheSongs(librarySongIds: libIds)) {
        if (!dialogOpen) break;
        progressNotifier.value = ev;
        if (ev['done'] == true) {
          final errs = (ev['errors'] as List?) ?? const [];
          if (errs.isEmpty) {
            AppLogger.info('Cache complete: ${ev['completed']}/${ev['total']}');
          } else {
            AppLogger.error('Cache finished with errors: ${errs.length}');
          }
          break;
        }
      }
    } catch (e) {
      AppLogger.error('Cache flow failed', error: e);
      progressNotifier.value = {
        'done': true,
        'percent': 0.0,
        'errors': ['$e'],
      };
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('音乐库'),
        actions: [
          IconButton(
            icon: const Icon(Icons.cloud_download_outlined),
            tooltip: '缓存全部到 RK3588',
            onPressed: _songs.isEmpty ? null : () => _cacheToRk(_songs),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadSongs,
          ),
        ],
      ),
      body: Column(
        children: [
          // 搜索框
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              decoration: InputDecoration(
                hintText: '搜索歌曲...',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          setState(() => _searchQuery = '');
                          _loadSongs();
                        },
                      )
                    : null,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              onChanged: (value) {
                setState(() => _searchQuery = value);
                _loadSongs();
              },
            ),
          ),
          
          // 歌曲列表
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _songs.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.music_off,
                              size: 64,
                              color: Colors.grey[400],
                            ),
                            const SizedBox(height: 16),
                            Text(
                              '暂无歌曲',
                              style: TextStyle(
                                fontSize: 16,
                                color: Colors.grey[600],
                              ),
                            ),
                          ],
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        itemCount: _songs.length,
                        itemBuilder: (context, index) {
                          final song = _songs[index];
                          final raw = index < _rawSongs.length
                              ? _rawSongs[index]
                              : <String, dynamic>{
                                  'id': song.libraryId,
                                  'title': song.title,
                                  'artist': song.artist,
                                };
                          return GestureDetector(
                            onLongPress: () => _cacheToRk([song]),
                            child: SongCard(
                              song: song,
                              onTap: () => _openDetail(raw),
                            ),
                          );
                        },
                      ),
          ),
          // 全局底部 Mini Player
          const MiniPlayer(),
        ],
      ),
    );
  }

  void _openDetail(Map<String, dynamic> raw) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => SongDetailPage(raw: raw)),
    );
  }
}
