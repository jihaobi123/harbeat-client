import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/config/theme_config.dart';
import '../../core/services/hardware_service.dart';
import '../../core/utils/helpers.dart';
import '../../data/models/models.dart';
import 'device_connection_page.dart';
import 'playlist_selection_page.dart';
import 'discovery_page.dart';
import 'mc_control_page.dart';
import 'session_history_page.dart';

class MainPage extends StatefulWidget {
  const MainPage({super.key});

  @override
  State<MainPage> createState() => _MainPageState();
}

class _MainPageState extends State<MainPage> {
  final _hardwareService = HardwareService();
  int _currentIndex = 0;
  Playlist? _currentPlaylist;
  bool _isPlaying = false;
  double _progress = 0.0;
  Duration _currentTime = Duration.zero;
  Duration _totalDuration = Duration.zero;
  bool _isDeviceConnected = false;

  final List<Widget> _pages = [];

  @override
  void initState() {
    super.initState();
    _initPages();
    _checkConnection();
  }

  void _initPages() {
    _pages.addAll([
      DeviceConnectionPage(onConnected: _onDeviceConnected),
      DiscoveryPage(onPlaylistSelected: _onPlaylistSelected),
      PlaylistSelectionPage(onPlaylistSelected: _onPlaylistSelected),
      MCControlPage(
        currentPlaylist: _currentPlaylist,
        isPlaying: _isPlaying,
        progress: _progress,
        currentTime: _currentTime,
        totalDuration: _totalDuration,
        onTogglePlay: _togglePlay,
        onNextTrack: _nextTrack,
      ),
    ]);
  }

  Future<void> _checkConnection() async {
    final connected = await _hardwareService.checkHealth();
    if (mounted) {
      setState(() {
        _isDeviceConnected = connected;
      });
    }
  }

  void _onDeviceConnected() {
    setState(() {
      _isDeviceConnected = true;
    });
    Future.delayed(Duration(milliseconds: 500), () {
      if (mounted) {
        setState(() {
          _currentIndex = 3;
        });
      }
    });
  }

  void _onPlaylistSelected(Playlist playlist) {
    setState(() {
      _currentPlaylist = playlist;
    });
    AppHaptics.medium();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('✅ 已选择: ${playlist.name}'),
        backgroundColor: ThemeConfig.accentGreen,
        duration: Duration(seconds: 1),
      ),
    );
  }

  void _togglePlay() {
    AppHaptics.light();
    setState(() {
      _isPlaying = !_isPlaying;
    });
  }

  void _nextTrack() {
    AppHaptics.light();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('⏭ 已切换到下一首'),
        duration: Duration(seconds: 1),
      ),
    );
  }

  /// 每次 build 时重建 pages，保证子页拿到最新的 _currentPlaylist / _isPlaying 等。
  List<Widget> _buildPages() {
    return [
      DeviceConnectionPage(onConnected: _onDeviceConnected),
      DiscoveryPage(onPlaylistSelected: _onPlaylistSelected),
      PlaylistSelectionPage(onPlaylistSelected: _onPlaylistSelected),
      MCControlPage(
        currentPlaylist: _currentPlaylist,
        isPlaying: _isPlaying,
        progress: _progress,
        currentTime: _currentTime,
        totalDuration: _totalDuration,
        onTogglePlay: _togglePlay,
        onNextTrack: _nextTrack,
        onPlaylistSelected: _onPlaylistSelected,
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final pages = _buildPages();
    return PopScope(
      canPop: false,
      child: Scaffold(
        backgroundColor: ThemeConfig.backgroundPrimary,
        body: Column(
          children: [
            _buildAppBar(),
            Expanded(
              child: IndexedStack(
                index: _currentIndex,
                children: pages,
              ),
            ),
          ],
        ),
        bottomNavigationBar: _buildBottomNavBar(),
      ),
    );
  }

  Widget _buildAppBar() {
    return Container(
      padding: EdgeInsets.only(top: MediaQuery.of(context).padding.top + 8, left: 16, right: 16, bottom: 8),
      decoration: BoxDecoration(
        color: ThemeConfig.backgroundPrimary,
        border: Border(
          bottom: BorderSide(
            color: ThemeConfig.backgroundSecondary.withOpacity(0.3),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(8),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.asset(
                'assets/images/ui/vinyl_record.jpg',
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) {
                  return Container(
                    color: ThemeConfig.backgroundSecondary,
                    child: Icon(
                      Icons.album,
                      color: ThemeConfig.textLight,
                      size: 24,
                    ),
                  );
                },
              ),
            ),
          ),
          SizedBox(width: 12),
          Text(
            'HARIBEAT',
            style: TextStyle(
              color: ThemeConfig.textLight,
              fontSize: 24,
              fontWeight: FontWeight.bold,
              letterSpacing: 2,
            ),
          ),
          GestureDetector(
            onTap: () {
              AppHaptics.selection();
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => const SessionHistoryPage()),
              );
            },
            child: Container(
              padding: EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: ThemeConfig.backgroundSecondary.withOpacity(0.5),
                borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
              ),
              child: Icon(
                Icons.history,
                color: ThemeConfig.textLight.withOpacity(0.8),
                size: 24,
              ),
            ),
          ),
          SizedBox(width: 12),
          if (_isDeviceConnected)
            Container(
              padding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: ThemeConfig.accentSuccess.withOpacity(0.2),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: ThemeConfig.accentSuccess.withOpacity(0.5)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.check_circle, color: ThemeConfig.accentSuccess, size: 14),
                  SizedBox(width: 4),
                  Text(
                    '已连接',
                    style: TextStyle(
                      color: ThemeConfig.accentSuccess,
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildBottomNavBar() {
    return Container(
      decoration: BoxDecoration(
        color: ThemeConfig.backgroundSecondary.withOpacity(0.95),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.2),
            blurRadius: 8,
            offset: Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _buildNavItem(
                icon: Icons.wifi,
                label: '设备',
                index: 0,
                isActive: _isDeviceConnected,
              ),
              _buildNavItem(
                icon: Icons.explore,
                label: '发现',
                index: 1,
              ),
              _buildNavItem(
                icon: Icons.playlist_play,
                label: '歌单',
                index: 2,
              ),
              _buildNavItem(
                icon: Icons.control_camera,
                label: '控台',
                index: 3,
                showBadge: _currentPlaylist != null,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNavItem({
    required IconData icon,
    required String label,
    required int index,
    bool isActive = false,
    bool showBadge = false,
  }) {
    final isSelected = _currentIndex == index;
    
    return GestureDetector(
      onTap: () {
        AppHaptics.selection();
        setState(() {
          _currentIndex = index;
        });
      },
      child: AnimatedContainer(
        duration: Duration(milliseconds: 200),
        padding: EdgeInsets.symmetric(horizontal: 20, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected
              ? ThemeConfig.accentGreen.withOpacity(0.2)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                Icon(
                  icon,
                  size: 26,
                  color: isSelected
                      ? ThemeConfig.accentGreen
                      : (isActive ? ThemeConfig.accentSuccess : ThemeConfig.textLight.withOpacity(0.6)),
                ),
                if (showBadge && !isSelected)
                  Positioned(
                    right: -6,
                    top: -6,
                    child: Container(
                      width: 12,
                      height: 12,
                      decoration: BoxDecoration(
                        color: ThemeConfig.accentOrange,
                        shape: BoxShape.circle,
                        border: Border.all(color: ThemeConfig.backgroundSecondary, width: 2),
                      ),
                    ),
                  ),
              ],
            ),
            SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                color: isSelected
                    ? ThemeConfig.accentGreen
                    : (isActive ? ThemeConfig.accentSuccess : ThemeConfig.textLight.withOpacity(0.6)),
                fontSize: ThemeConfig.fontSizeSmall,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
