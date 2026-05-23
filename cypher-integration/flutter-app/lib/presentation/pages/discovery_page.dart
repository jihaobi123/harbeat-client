import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/config/theme_config.dart';
import '../../core/services/hardware_service.dart';
import '../../core/utils/helpers.dart';
import '../../data/models/models.dart' hide Song;
import '../../data/models/song.dart';
import '../../data/services/song_service.dart';

class DiscoveryPage extends StatefulWidget {
  final Function(Playlist)? onPlaylistSelected;
  
  const DiscoveryPage({super.key, this.onPlaylistSelected});

  @override
  State<DiscoveryPage> createState() => _DiscoveryPageState();
}

class _DiscoveryPageState extends State<DiscoveryPage> with SingleTickerProviderStateMixin {
  final _hardwareService = HardwareService();
  final _songService = SongService();
  final _searchController = TextEditingController();
  late TabController _tabController;
  bool _isLoading = false;
  String _searchQuery = '';
  List<Song> _searchResults = [];

  final List<Map<String, dynamic>> _recommendedPlaylists = [
    {'id': 1, 'name': '🔥 炸场高能', 'desc': 'Battle时刻专用', 'icon': Icons.whatshot, 'color': ThemeConfig.accentOrange, 'songs': 25},
    {'id': 2, 'name': '🕺 Hip-hop经典', 'desc': 'Old School精选', 'icon': Icons.music_note, 'color': ThemeConfig.accentGreen, 'songs': 30},
    {'id': 3, 'name': '💥 Breaking节奏', 'desc': 'Power Move专用', 'icon': Icons.sports_martial_arts, 'color': Color(0xFF9B59B6), 'songs': 20},
    {'id': 4, 'name': '🎯 Cypher实战', 'desc': '即兴对战专用', 'icon': Icons.people, 'color': Color(0xFF4A90E2), 'songs': 15},
    {'id': 5, 'name': '😌 舒缓练习', 'desc': '基本功训练', 'icon': Icons.self_improvement, 'color': Color(0xFF1ABC9C), 'songs': 28},
    {'id': 6, 'name': '🎉 派对时刻', 'desc': 'After Party专用', 'icon': Icons.celebration, 'color': Color(0xFFFFB800), 'songs': 22},
  ];

  final List<Map<String, dynamic>> _quickTags = [
    {'label': '炸场', 'icon': Icons.whatshot, 'color': ThemeConfig.accentOrange},
    {'label': '练习', 'icon': Icons.fitness_center, 'color': Color(0xFF4A90E2)},
    {'label': 'Battle', 'icon': Icons.sports_kabaddi, 'color': Color(0xFF9B59B6)},
    {'label': 'Cypher', 'icon': Icons.group, 'color': ThemeConfig.accentGreen},
    {'label': 'Freestyle', 'icon': Icons.psychology, 'color': Color(0xFFFFB800)},
    {'label': 'Powermove', 'icon': Icons.sports_martial_arts, 'color': Color(0xFFFF3B30)},
  ];

  final List<Map<String, dynamic>> _semanticSuggestions = [
    {'query': '想听炸一点的音乐', 'icon': Icons.mood},
    {'query': '练习Breaking用的', 'icon': Icons.sports},
    {'query': 'Cypher对战时候放', 'icon': Icons.groups},
    {'query': '热身时候放的', 'icon': Icons.accessibility},
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _onSearch(String query) async {
    if (query.trim().isEmpty) return;

    setState(() {
      _isLoading = true;
      _searchQuery = query;
      _searchResults = [];
    });

    AppHaptics.medium();
    try {
      final results = await _songService.searchSongs(query);
      if (!mounted) return;
      setState(() {
        _searchResults = results;
        _isLoading = false;
      });
      _showSearchResults();
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('搜索失败: $e'),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  void _showSearchResults() {
    showModalBottomSheet(
      context: context,
      backgroundColor: ThemeConfig.backgroundPrimary,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.3,
        maxChildSize: 0.95,
        expand: false,
        builder: (_, scrollCtrl) => Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  const Icon(Icons.search, color: ThemeConfig.accentOrange),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      '“$_searchQuery” 的结果 (${_searchResults.length})',
                      style: const TextStyle(
                        color: ThemeConfig.textLight,
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: ThemeConfig.textLight),
                    onPressed: () => Navigator.of(ctx).pop(),
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: ThemeConfig.backgroundSecondary),
            Expanded(
              child: _searchResults.isEmpty
                  ? const Center(
                      child: Text(
                        '没有找到匹配的歌曲',
                        style: TextStyle(color: Colors.white54),
                      ),
                    )
                  : ListView.builder(
                      controller: scrollCtrl,
                      itemCount: _searchResults.length,
                      itemBuilder: (_, i) {
                        final s = _searchResults[i];
                        return ListTile(
                          leading: const CircleAvatar(
                            backgroundColor: ThemeConfig.accentGreen,
                            child: Icon(Icons.music_note, color: Colors.white),
                          ),
                          title: Text(
                            s.title,
                            style: const TextStyle(color: ThemeConfig.textLight),
                          ),
                          subtitle: Text(
                            '${s.artist}  ·  ${s.bpmDisplay}',
                            style: const TextStyle(color: Colors.white54),
                          ),
                          trailing: const Icon(Icons.play_arrow, color: ThemeConfig.accentOrange),
                          onTap: () {
                            Navigator.of(ctx).pop();
                            _playSearchResult(s);
                          },
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _playSearchResult(Song song) async {
    AppHaptics.medium();
    try {
      final ok = await _hardwareService.play(songId: song.id, startAtSec: 0.0);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(ok ? '▶️ 播放：${song.title}' : '❌ 后端未返回 OK'),
          backgroundColor: ok ? ThemeConfig.accentGreen : Colors.red,
          duration: const Duration(seconds: 2),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('播放失败：$e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  void _selectPlaylist(Map<String, dynamic> playlistConfig) {
    AppHaptics.medium();
    
    final playlist = Playlist(
      id: playlistConfig['id'],
      name: playlistConfig['name'],
      description: playlistConfig['desc'],
      type: playlistConfig['name'].toString().contains('Hip-hop') ? 'hiphop' : 
            playlistConfig['name'].toString().contains('Breaking') ? 'breaking' :
            playlistConfig['name'].toString().contains('练习') ? 'practice' : 'general',
    );
    
    widget.onPlaylistSelected?.call(playlist);
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('✅ 已选择: ${playlistConfig['name']}'),
        backgroundColor: ThemeConfig.accentGreen,
        duration: Duration(seconds: 1),
      ),
    );
  }

  void _onSemanticSuggestion(String query) {
    AppHaptics.light();
    _searchController.text = query;
    _onSearch(query);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ThemeConfig.backgroundPrimary,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(),
            _buildSearchBar(),
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  _buildRecommendTab(),
                  _buildQuickSelectTab(),
                  _buildSemanticTab(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: EdgeInsets.all(ThemeConfig.spacingMedium),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '音乐发现',
            style: TextStyle(
              color: ThemeConfig.textLight,
              fontSize: ThemeConfig.fontSizeXXLarge,
              fontWeight: FontWeight.bold,
            ),
          ),
          Text(
            '智能推荐 · 快速选歌 · 语义搜索',
            style: TextStyle(
              color: ThemeConfig.textLight.withOpacity(0.7),
              fontSize: ThemeConfig.fontSizeSmall,
            ),
          ),
          SizedBox(height: ThemeConfig.spacingMedium),
          TabBar(
            controller: _tabController,
            indicatorColor: ThemeConfig.accentOrange,
            labelColor: ThemeConfig.textLight,
            unselectedLabelColor: ThemeConfig.textLight.withOpacity(0.5),
            tabs: [
              Tab(text: '推荐'),
              Tab(text: '快捷'),
              Tab(text: '语义'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSearchBar() {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: ThemeConfig.spacingMedium, vertical: ThemeConfig.spacingSmall),
      child: Row(
        children: [
          Expanded(
            child: Container(
              padding: EdgeInsets.symmetric(horizontal: ThemeConfig.spacingMedium),
              decoration: BoxDecoration(
                color: ThemeConfig.backgroundSecondary.withOpacity(0.3),
                borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                border: Border.all(color: ThemeConfig.backgroundSecondary),
              ),
              child: TextField(
                controller: _searchController,
                style: TextStyle(color: ThemeConfig.textLight),
                decoration: InputDecoration(
                  hintText: '搜索歌曲、歌单...',
                  hintStyle: TextStyle(color: ThemeConfig.textLight.withOpacity(0.3)),
                  border: InputBorder.none,
                  prefixIcon: Icon(Icons.search, color: ThemeConfig.textLight.withOpacity(0.5)),
                  suffixIcon: _searchController.text.isNotEmpty
                      ? IconButton(
                          icon: Icon(Icons.clear, color: ThemeConfig.textLight.withOpacity(0.5)),
                          onPressed: () {
                            _searchController.clear();
                            setState(() {});
                          },
                        )
                      : null,
                ),
                onSubmitted: _onSearch,
                onChanged: (value) => setState(() {}),
              ),
            ),
          ),
          SizedBox(width: ThemeConfig.spacingSmall),
          GestureDetector(
            onTap: () => _onSearch(_searchController.text),
            child: Container(
              padding: EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: ThemeConfig.accentOrange,
                borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
              ),
              child: Icon(Icons.search, color: ThemeConfig.textLight),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecommendTab() {
    return SingleChildScrollView(
      padding: EdgeInsets.all(ThemeConfig.spacingMedium),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '🔥 热门推荐',
            style: TextStyle(
              color: ThemeConfig.textLight,
              fontSize: ThemeConfig.fontSizeLarge,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: ThemeConfig.spacingMedium),
          ...(_recommendedPlaylists.map((playlist) => _buildPlaylistCard(playlist))),
        ],
      ),
    );
  }

  Widget _buildQuickSelectTab() {
    return SingleChildScrollView(
      padding: EdgeInsets.all(ThemeConfig.spacingMedium),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '⚡ 快速选择场景',
            style: TextStyle(
              color: ThemeConfig.textLight,
              fontSize: ThemeConfig.fontSizeLarge,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: ThemeConfig.spacingMedium),
          Wrap(
            spacing: ThemeConfig.spacingMedium,
            runSpacing: ThemeConfig.spacingMedium,
            children: _quickTags.map((tag) => _buildQuickTagCard(tag)).toList(),
          ),
          SizedBox(height: ThemeConfig.spacingLarge),
          Text(
            '📋 推荐歌单',
            style: TextStyle(
              color: ThemeConfig.textLight,
              fontSize: ThemeConfig.fontSizeLarge,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: ThemeConfig.spacingMedium),
          ...(_recommendedPlaylists.take(3).map((playlist) => _buildPlaylistCard(playlist))),
        ],
      ),
    );
  }

  Widget _buildSemanticTab() {
    return SingleChildScrollView(
      padding: EdgeInsets.all(ThemeConfig.spacingMedium),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '🗣️ 语义搜索示例',
            style: TextStyle(
              color: ThemeConfig.textLight,
              fontSize: ThemeConfig.fontSizeLarge,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: ThemeConfig.spacingMedium),
          Text(
            '试试这样说：',
            style: TextStyle(
              color: ThemeConfig.textLight.withOpacity(0.7),
              fontSize: ThemeConfig.fontSizeSmall,
            ),
          ),
          SizedBox(height: ThemeConfig.spacingMedium),
          ...(_semanticSuggestions.map((s) => _buildSemanticSuggestionCard(s))),
        ],
      ),
    );
  }

  Widget _buildPlaylistCard(Map<String, dynamic> playlist) {
    return GestureDetector(
      onTap: () => _selectPlaylist(playlist),
      child: Container(
        margin: EdgeInsets.only(bottom: ThemeConfig.spacingMedium),
        padding: EdgeInsets.all(ThemeConfig.spacingLarge),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              (playlist['color'] as Color).withOpacity(0.2),
              (playlist['color'] as Color).withOpacity(0.05),
            ],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
          border: Border.all(color: (playlist['color'] as Color).withOpacity(0.3)),
        ),
        child: Row(
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: (playlist['color'] as Color).withOpacity(0.2),
                borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
              ),
              child: Icon(playlist['icon'], color: playlist['color'], size: 32),
            ),
            SizedBox(width: ThemeConfig.spacingMedium),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    playlist['name'],
                    style: TextStyle(
                      color: ThemeConfig.textLight,
                      fontSize: ThemeConfig.fontSizeMedium,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    playlist['desc'],
                    style: TextStyle(
                      color: ThemeConfig.textLight.withOpacity(0.6),
                      fontSize: ThemeConfig.fontSizeSmall,
                    ),
                  ),
                  Text(
                    '${playlist['songs']} 首歌曲',
                    style: TextStyle(
                      color: (playlist['color'] as Color).withOpacity(0.8),
                      fontSize: ThemeConfig.fontSizeXS,
                    ),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right, color: ThemeConfig.textLight.withOpacity(0.5)),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickTagCard(Map<String, dynamic> tag) {
    return GestureDetector(
      onTap: () {
        AppHaptics.light();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('⚡ ${tag['label']} 模式'),
            backgroundColor: tag['color'],
            duration: Duration(seconds: 1),
          ),
        );
      },
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: ThemeConfig.spacingLarge, vertical: ThemeConfig.spacingMedium),
        decoration: BoxDecoration(
          color: (tag['color'] as Color).withOpacity(0.2),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
          border: Border.all(color: (tag['color'] as Color).withOpacity(0.5)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(tag['icon'], color: tag['color'], size: 20),
            SizedBox(width: 8),
            Text(
              tag['label'],
              style: TextStyle(
                color: ThemeConfig.textLight,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSemanticSuggestionCard(Map<String, dynamic> suggestion) {
    return GestureDetector(
      onTap: () => _onSemanticSuggestion(suggestion['query']),
      child: Container(
        margin: EdgeInsets.only(bottom: ThemeConfig.spacingSmall),
        padding: EdgeInsets.all(ThemeConfig.spacingMedium),
        decoration: BoxDecoration(
          color: ThemeConfig.backgroundSecondary.withOpacity(0.2),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
        ),
        child: Row(
          children: [
            Icon(suggestion['icon'], color: ThemeConfig.accentOrange, size: 24),
            SizedBox(width: ThemeConfig.spacingMedium),
            Expanded(
              child: Text(
                suggestion['query'],
                style: TextStyle(
                  color: ThemeConfig.textLight,
                  fontSize: ThemeConfig.fontSizeMedium,
                ),
              ),
            ),
            Icon(Icons.arrow_forward_ios, color: ThemeConfig.textLight.withOpacity(0.3), size: 16),
          ],
        ),
      ),
    );
  }
}
