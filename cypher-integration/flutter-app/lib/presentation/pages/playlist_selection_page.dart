import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/config/theme_config.dart';
import '../../core/utils/helpers.dart';
import '../../data/services/data_services.dart';
import '../../data/models/models.dart';

/// 歌单选择页 - MC 现场氛围歌单
class PlaylistSelectionPage extends StatefulWidget {
  final Function(Playlist) onPlaylistSelected;
  
  const PlaylistSelectionPage({
    super.key,
    required this.onPlaylistSelected,
  });

  @override
  State<PlaylistSelectionPage> createState() => _PlaylistSelectionPageState();
}

class _PlaylistSelectionPageState extends State<PlaylistSelectionPage> {
  final _playlistService = PlaylistService();
  
  List<Playlist> _playlists = [];
  int? _selectedPlaylistId;
  bool _isLoading = true;

  // 官方歌单配置（V0.1 固定 5 个）
  final List<Map<String, dynamic>> _officialPlaylists = [
    {
      'id': 1,
      'name': '测试调试歌单',
      'description': '活动开场试音、设备测试专用，节奏平缓',
      'icon': Icons.tune,
      'color': ThemeConfig.accentGreen,
      'type': 'test',
    },
    {
      'id': 2,
      'name': '炸场高能歌单',
      'description': '气氛拉高、蹦迪、互动、暖场、高潮环节用',
      'icon': Icons.whatshot,
      'color': ThemeConfig.accentOrange,
      'type': 'hype',
    },
    {
      'id': 3,
      'name': '平稳控场歌单',
      'description': '主持人讲话、流程过渡、安静环节、缓和气氛用',
      'icon': Icons.remove_circle_outline,
      'color': Color(0xFF4A90E2),
      'type': 'calm',
    },
    {
      'id': 4,
      'name': '街舞练舞歌单',
      'description': 'Cypher、基本功练习、街舞排练专用节奏',
      'icon': Icons.directions_run,
      'color': Color(0xFF9B59B6),
      'type': 'dance',
    },
    {
      'id': 5,
      'name': '轻柔背景歌单',
      'description': '签到、入座、闲聊、冷场垫底轻音乐',
      'icon': Icons.music_note,
      'color': Color(0xFF1ABC9C),
      'type': 'background',
    },
  ];

  @override
  void initState() {
    super.initState();
    _loadPlaylists();
  }

  /// 加载歌单列表
  Future<void> _loadPlaylists() async {
    setState(() {
      _isLoading = true;
    });

    try {
      // 先使用官方歌单配置
      setState(() {
        _playlists = _officialPlaylists.map((config) {
          return Playlist(
            id: config['id'],
            name: config['name'],
            description: config['description'],
            type: config['type'],
          );
        }).toList();
        _isLoading = false;
      });

      // 尝试从后端获取真实歌单（可选）
      // final officialPlaylists = await _playlistService.getOfficialPlaylists();
      // if (officialPlaylists.isNotEmpty) {
      //   setState(() {
      //     _playlists = officialPlaylists;
      //   });
      // }
    } catch (e) {
      setState(() {
        _isLoading = false;
      });
      AppLogger.error('加载歌单失败: $e');
    }
  }

  /// 选择歌单
  void _selectPlaylist(Playlist playlist) {
    AppHaptics.medium();
    
    setState(() {
      _selectedPlaylistId = playlist.id;
    });

    // 通知父组件
    widget.onPlaylistSelected(playlist);

    // 显示成功提示
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(
          children: [
            Icon(Icons.check_circle, color: Colors.white),
            SizedBox(width: 8),
            Text('已选择: ${playlist.name}'),
          ],
        ),
        backgroundColor: ThemeConfig.accentGreen,
        duration: Duration(seconds: 1),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ThemeConfig.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Stack(
              children: [
                Text(
                  '现场氛围歌单',
                  style: TextStyle(
                    color: ThemeConfig.textLight,
                    fontSize: ThemeConfig.fontSizeXXLarge,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            Text(
              '一键选择适配当下活动的背景音乐',
              style: TextStyle(
                color: ThemeConfig.textLight.withOpacity(0.7),
                fontSize: ThemeConfig.fontSizeSmall,
              ),
            ),
          ],
        ),
      ),
      body: Stack(
        children: [
          Positioned.fill(
            child: Opacity(
              opacity: 0.15,
              child: Image.asset(
                'assets/images/ui/b_boy_silhouette.jpg',
                fit: BoxFit.contain,
                errorBuilder: (context, error, stackTrace) {
                  return SizedBox.shrink();
                },
              ),
            ),
          ),
          _isLoading
              ? Center(
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(ThemeConfig.accentOrange),
                  ),
                )
              : ListView.builder(
                  padding: EdgeInsets.symmetric(
                    horizontal: ThemeConfig.spacingMedium,
                    vertical: ThemeConfig.spacingMedium,
                  ),
                  itemCount: _playlists.length,
                  itemBuilder: (context, index) {
                    final playlist = _playlists[index];
                    final isSelected = playlist.id == _selectedPlaylistId;
                    final config = _officialPlaylists.firstWhere(
                      (c) => c['id'] == playlist.id,
                      orElse: () => _officialPlaylists[0],
                    );

                    return Column(
                      children: [
                        _buildPlaylistCard(playlist, config, isSelected),
                        if (index < _playlists.length - 1)
                          _buildBrushStrokeDivider(),
                      ],
                    );
                  },
                ),
        ],
      ),
    );
  }

  Widget _buildBrushStrokeDivider() {
    return Container(
      margin: EdgeInsets.symmetric(vertical: 8),
      height: 3,
      child: Opacity(
        opacity: 0.4,
        child: Image.asset(
          'assets/images/ui/brush_stroke.png',
          fit: BoxFit.fitWidth,
          repeat: ImageRepeat.repeatX,
          errorBuilder: (context, error, stackTrace) {
            return Container(
              height: 3,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    Colors.transparent,
                    ThemeConfig.accentOrange.withOpacity(0.5),
                    ThemeConfig.accentGreen.withOpacity(0.3),
                    Colors.transparent,
                  ],
                ),
                borderRadius: BorderRadius.circular(2),
              ),
            );
          },
        ),
      ),
    );
  }

  /// 构建歌单卡片
  Widget _buildPlaylistCard(
    Playlist playlist,
    Map<String, dynamic> config,
    bool isSelected,
  ) {
    return GestureDetector(
      onTap: () => _selectPlaylist(playlist),
      child: Container(
        margin: EdgeInsets.only(bottom: ThemeConfig.spacingMedium),
        padding: EdgeInsets.all(ThemeConfig.spacingLarge),
        decoration: BoxDecoration(
          gradient: isSelected
              ? LinearGradient(
                  colors: [
                    config['color'].withOpacity(0.3),
                    config['color'].withOpacity(0.1),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                )
              : null,
          color: isSelected ? null : ThemeConfig.backgroundSecondary.withOpacity(0.2),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusLarge),
          border: Border.all(
            color: isSelected
                ? config['color']
                : ThemeConfig.backgroundSecondary.withOpacity(0.3),
            width: isSelected ? 3 : 1,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: config['color'].withOpacity(0.3),
                    blurRadius: 12,
                    offset: Offset(0, 6),
                  ),
                ]
              : ThemeConfig.cardShadow,
        ),
        child: Row(
          children: [
            // 图标区域
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: config['color'].withOpacity(0.2),
                borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                border: Border.all(
                  color: config['color'].withOpacity(0.5),
                  width: 2,
                ),
              ),
              child: Icon(
                config['icon'],
                color: config['color'],
                size: 36,
              ),
            ),
            
            SizedBox(width: ThemeConfig.spacingLarge),
            
            // 文字信息
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          playlist.name,
                          style: TextStyle(
                            color: ThemeConfig.textLight,
                            fontSize: ThemeConfig.fontSizeXLarge,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                      if (isSelected)
                        Container(
                          padding: EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          decoration: BoxDecoration(
                            color: config['color'],
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(
                            '已选',
                            style: TextStyle(
                              color: ThemeConfig.textLight,
                              fontSize: ThemeConfig.fontSizeXS,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                    ],
                  ),
                  SizedBox(height: 8),
                  Text(
                    playlist.description ?? '',
                    style: TextStyle(
                      color: ThemeConfig.textLight.withOpacity(0.7),
                      fontSize: ThemeConfig.fontSizeSmall,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
