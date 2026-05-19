import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../state/providers.dart';
import '../../models/models.dart';

class PrepPage extends ConsumerStatefulWidget {
  const PrepPage({super.key});

  @override
  ConsumerState<PrepPage> createState() => _PrepPageState();
}

class _PrepPageState extends ConsumerState<PrepPage> {
  final _searchController = TextEditingController();
  Timer? _debounce;
  List<SongStatus> _searchResults = [];

  @override
  void dispose() {
    _searchController.dispose();
    _debounce?.cancel();
    super.dispose();
  }

  void _onSearchChanged(String query) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), () {
      _performSearch(query);
    });
  }

  Future<void> _performSearch(String query) async {
    final response = await ref.read(libraryProvider(query).future);
    setState(() {
      _searchResults = response;
    });
  }

  @override
  Widget build(BuildContext context) {
    final setState = ref.watch(setProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('赛前准备'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () {
              ref.read(authProvider.notifier).logout();
            },
          ),
        ],
      ),
      body: Row(
        children: [
          Expanded(
            flex: 2,
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: TextField(
                    controller: _searchController,
                    onChanged: _onSearchChanged,
                    decoration: InputDecoration(
                      hintText: '搜索歌曲...',
                      prefixIcon: const Icon(Icons.search),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      filled: true,
                    ),
                  ),
                ),
                Expanded(
                  child: _searchResults.isEmpty
                      ? const Center(child: Text('搜索歌曲添加到Set'))
                      : ListView.builder(
                          itemCount: _searchResults.length,
                          itemBuilder: (context, index) {
                            final song = _searchResults[index];
                            return _SongTile(
                              song: song,
                              onAdd: () {
                                ref.read(setProvider.notifier).addSong(song);
                              },
                            );
                          },
                        ),
                ),
              ],
            ),
          ),
          Container(
            width: 1,
            color: theme.dividerColor,
          ),
          Expanded(
            flex: 3,
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      Text(
                        '当前 Set (${setState.songs.length}首)',
                        style: theme.textTheme.titleLarge,
                      ),
                      const Spacer(),
                      ElevatedButton.icon(
                        onPressed: setState.isPlanning
                            ? null
                            : () => ref.read(setProvider.notifier).startPlanning(),
                        icon: setState.isPlanning
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.auto_awesome),
                        label: Text(setState.isPlanning ? '规划中...' : 'Plan This Set'),
                      ),
                    ],
                  ),
                ),
                if (setState.mixPlan != null)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Card(
                      child: ListTile(
                        leading: const Icon(Icons.check_circle, color: Colors.green),
                        title: const Text('MixPlan已生成'),
                        subtitle: Text('共${setState.mixPlan!.tracks.length}首'),
                        trailing: setState.isSyncing
                            ? CircularProgressIndicator(
                                value: setState.syncProgress / 100,
                              )
                            : ElevatedButton(
                                onPressed: () => ref.read(setProvider.notifier).syncToRK(),
                                child: const Text('Sync to RK'),
                              ),
                      ),
                    ),
                  ),
                if (setState.isSyncing)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Column(
                      children: [
                        const LinearProgressIndicator(),
                        const SizedBox(height: 8),
                        Text('同步进度: ${setState.syncProgress.toStringAsFixed(1)}%'),
                      ],
                    ),
                  ),
                const SizedBox(height: 16),
                Expanded(
                  child: ReorderableListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    itemCount: setState.songs.length,
                    onReorder: (oldIndex, newIndex) {
                      // Handle reorder
                    },
                    itemBuilder: (context, index) {
                      final song = setState.songs[index];
                      return Card(
                        key: ValueKey(song.songId),
                        child: ListTile(
                          leading: CircleAvatar(
                            child: Text('${index + 1}'),
                          ),
                          title: Text(song.title),
                          subtitle: Text('${song.artist} | ${song.bpm.toStringAsFixed(0)} BPM | ${song.key}'),
                          trailing: IconButton(
                            icon: const Icon(Icons.remove_circle_outline),
                            onPressed: () {
                              ref.read(setProvider.notifier).removeSong(song);
                            },
                          ),
                        ),
                      );
                    },
                  ),
                ),
                if (setState.isReadyToLive)
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: ElevatedButton(
                      onPressed: () {
                        Navigator.pushNamed(context, '/live');
                      },
                      style: ElevatedButton.styleFrom(
                        minimumSize: const Size(double.infinity, 56),
                        backgroundColor: theme.colorScheme.primary,
                      ),
                      child: const Text(
                        '🚀 开始现场',
                        style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SongTile extends StatelessWidget {
  final SongStatus song;
  final VoidCallback onAdd;

  const _SongTile({required this.song, required this.onAdd});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: ListTile(
        leading: Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: song.isReady ? Colors.green.shade100 : Colors.grey.shade200,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Center(
            child: Icon(
              song.isReady ? Icons.music_note : Icons.hourglass_empty,
              color: song.isReady ? Colors.green : Colors.grey,
            ),
          ),
        ),
        title: Text(song.title),
        subtitle: Text('${song.artist} | ${song.bpm.toStringAsFixed(0)} BPM | ${song.key}'),
        trailing: song.isReady
            ? IconButton(
                icon: const Icon(Icons.add_circle),
                color: theme.colorScheme.primary,
                onPressed: onAdd,
              )
            : Chip(
                label: Text(
                  song.analysisStatus.name,
                  style: const TextStyle(fontSize: 10),
                ),
                backgroundColor: Colors.orange.shade100,
              ),
      ),
    );
  }
}
