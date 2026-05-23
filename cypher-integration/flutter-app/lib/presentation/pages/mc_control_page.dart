import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/config/theme_config.dart';
import '../../core/services/hardware_service.dart';
import '../../core/services/session_service.dart';
import '../../core/utils/helpers.dart';
import '../../data/models/models.dart';

enum DJControlType { playPause, nextTrack, energy, style, loop, cut, effect, voice }

class MCControlPage extends StatefulWidget {
  final Playlist? currentPlaylist;
  final VoidCallback? onNextTrack;
  final VoidCallback? onTogglePlay;
  final bool isPlaying;
  final double progress;
  final Duration currentTime;
  final Duration totalDuration;
  final Function(Playlist)? onPlaylistSelected;
  
  const MCControlPage({
    super.key,
    this.currentPlaylist,
    this.onNextTrack,
    this.onTogglePlay,
    this.isPlaying = false,
    this.progress = 0.0,
    this.currentTime = Duration.zero,
    this.totalDuration = Duration.zero,
    this.onPlaylistSelected,
  });

  @override
  State<MCControlPage> createState() => _MCControlPageState();
}

class _MCControlPageState extends State<MCControlPage> with TickerProviderStateMixin {
  final _hardwareService = HardwareService();
  
  int _volume = 75;
  bool _isLooping = false;
  bool _isVoiceMode = false;
  bool _isPlayingLocal = false;
  EnergyMode _currentEnergyMode = EnergyMode.medium;
  MusicStyle _currentStyle = MusicStyle.hiphop;
  CutMode _currentCutMode = CutMode.clean_blend;
  Song? _currentSong;
  Timer? _progressTimer;
  double _displayProgress = 0.0;
  Duration _displayCurrentTime = Duration.zero;
  Duration _displayTotalDuration = Duration(minutes: 3, seconds: 45);
  
  EdgeStatus? _edgeStatus;
  bool _isDeviceConnected = false;

  final List<Map<String, dynamic>> _energyModes = [
    {'mode': EnergyMode.low, 'label': '低能量', 'icon': Icons.battery_1_bar, 'color': Color(0xFF4A90E2)},
    {'mode': EnergyMode.medium, 'label': '中能量', 'icon': Icons.battery_3_bar, 'color': Color(0xFFFFB800)},
    {'mode': EnergyMode.high, 'label': '高能量', 'icon': Icons.battery_full, 'color': Color(0xFFFF3B30)},
  ];

  final List<Map<String, dynamic>> _musicStyles = [
    {'style': MusicStyle.hiphop, 'label': 'Hip-hop', 'icon': Icons.music_note},
    {'style': MusicStyle.breaking, 'label': 'Breaking', 'icon': Icons.sports_martial_arts},
    {'style': MusicStyle.popping, 'label': 'Popping', 'icon': Icons.animation},
    {'style': MusicStyle.locking, 'label': 'Locking', 'icon': Icons.lock},
    {'style': MusicStyle.house, 'label': 'House', 'icon': Icons.home},
    {'style': MusicStyle.all, 'label': '全部', 'icon': Icons.all_inclusive},
  ];

  final List<Map<String, dynamic>> _soundEffects = [
    {'name': 'scratch', 'label': '搓碟', 'icon': Icons.album},
    {'name': 'applause', 'label': '鼓掌', 'icon': Icons.thumb_up},
    {'name': 'airhorn', 'label': '气喇叭', 'icon': Icons.campaign},
    {'name': 'drumroll', 'label': '鼓点', 'icon': Icons.music_video},
    {'name': 'boom', 'label': '重音', 'icon': Icons.flare},
  ];

  @override
  void initState() {
    super.initState();
    _loadVolume();
    _startProgressSimulation();
    _checkDeviceConnection();
    _setupMessageHandler();
  }

  @override
  void dispose() {
    _progressTimer?.cancel();
    super.dispose();
  }

  void _setupMessageHandler() {
    _hardwareService.setMessageHandler((message) {
      if (mounted) {
        setState(() {
          if (message['type'] == 'status') {
            _edgeStatus = EdgeStatus.fromJson(message);
            _isPlayingLocal = _edgeStatus?.isPlaying ?? false;
            _volume = _edgeStatus?.volume ?? 75;
            _currentStyle = _parseStyle(_edgeStatus?.currentStyle ?? '');
          }
        });
      }
    });
  }

  MusicStyle _parseStyle(String style) {
    switch (style.toLowerCase()) {
      case 'breaking': return MusicStyle.breaking;
      case 'popping': return MusicStyle.popping;
      case 'locking': return MusicStyle.locking;
      case 'house': return MusicStyle.house;
      default: return MusicStyle.hiphop;
    }
  }

  Future<void> _checkDeviceConnection() async {
    setState(() {
      _isDeviceConnected = _hardwareService.isDeviceConnected;
    });
  }

  void _startProgressSimulation() {
    _progressTimer = Timer.periodic(Duration(milliseconds: 500), (timer) {
      if (widget.isPlaying && mounted) {
        setState(() {
          _displayCurrentTime += Duration(milliseconds: 500);
          if (_displayCurrentTime >= _displayTotalDuration) {
            _displayCurrentTime = Duration.zero;
          }
          _displayProgress = _displayCurrentTime.inMilliseconds / _displayTotalDuration.inMilliseconds;
        });
      }
    });
  }

  Future<void> _loadVolume() async {
    final volume = await _hardwareService.getVolume();
    if (volume != null && mounted) {
      setState(() {
        _volume = volume;
      });
    }
  }

  Future<void> _setVolume(int value) async {
    setState(() {
      _volume = value.clamp(0, 100);
    });
    await _hardwareService.setVolume(_volume);
    await SessionService().recordEvent(
      type: 'volume',
      description: '音量调整到 $_volume%',
      data: {'volume': _volume},
    );
  }

  void _togglePlayPause() async {
    AppHaptics.medium();
    if (widget.isPlaying) {
      await _hardwareService.pause();
      await SessionService().recordEvent(
        type: 'pause',
        description: '暂停播放',
      );
    } else {
      // 首次播放：需传 song_id；以后的「继续」不传 -> /resume
      int? songId = _currentSong?.id;
      if (songId == null && widget.currentPlaylist?.songs != null && widget.currentPlaylist!.songs!.isNotEmpty) {
        final first = widget.currentPlaylist!.songs!.first;
        songId = first.id;
        _currentSong = first;
      }
      final ok = await _hardwareService.play(songId: songId);
      if (!ok && mounted) {
        _showSnackBar('⚠ 播放失败：请先选择歌单或确认设备已连接');
      }
      await SessionService().recordEvent(
        type: 'play',
        description: songId == null ? '继续播放' : '播放歌曲 $songId',
        data: songId == null ? null : {'song_id': songId},
      );
    }
    widget.onTogglePlay?.call();
  }

  void _nextTrack() async {
    AppHaptics.medium();
    await _hardwareService.nextTrack();
    await SessionService().recordEvent(
      type: 'next',
      description: '切换到下一首',
    );
    setState(() {
      _displayCurrentTime = Duration.zero;
      _displayProgress = 0.0;
    });
    widget.onNextTrack?.call();
    _showSnackBar('⏭ 已切换到下一首');
  }

  void _previousTrack() async {
    AppHaptics.medium();
    await _hardwareService.previousTrack();
    await SessionService().recordEvent(
      type: 'previous',
      description: '切换到上一首',
    );
    setState(() {
      _displayCurrentTime = Duration.zero;
      _displayProgress = 0.0;
    });
    _showSnackBar('⏮ 已切换到上一首');
  }

  void _setEnergyMode(EnergyMode mode) async {
    AppHaptics.heavy();
    await _hardwareService.setEnergyMode(mode);
    final modeInfo = _energyModes.firstWhere((e) => e['mode'] == mode);
    await SessionService().recordEvent(
      type: 'energy',
      description: '能量模式: ${modeInfo['label']}',
      data: {'mode': mode.toString()},
    );
    setState(() {
      _currentEnergyMode = mode;
    });
    _showSnackBar('⚡ 能量: ${modeInfo['label']}', modeInfo['color']);
  }

  void _setMusicStyle(MusicStyle style) async {
    AppHaptics.heavy();
    await _hardwareService.setMusicStyle(style);
    final styleInfo = _musicStyles.firstWhere((s) => s['style'] == style);
    await SessionService().recordEvent(
      type: 'style',
      description: '音乐风格: ${styleInfo['label']}',
      data: {'style': style.toString()},
    );
    setState(() {
      _currentStyle = style;
    });
    _showSnackBar('🎵 风格: ${styleInfo['label']}', ThemeConfig.accentGreen);
  }

  void _toggleLoop() async {
    AppHaptics.selection();
    if (_isLooping) {
      await _hardwareService.stopLoop();
      await SessionService().recordEvent(
        type: 'loop',
        description: '关闭循环',
      );
      setState(() {
        _isLooping = false;
      });
      _showSnackBar('🔄 已关闭循环');
    } else {
      await _hardwareService.startLoop(durationMs: 30000);
      await SessionService().recordEvent(
        type: 'loop',
        description: '开启30秒循环',
      );
      setState(() {
        _isLooping = true;
      });
      _showSnackBar('🔄 已开启30秒循环', ThemeConfig.accentGreen);
    }
  }

  void _cutToNext() async {
    AppHaptics.heavy();
    await _hardwareService.cutToNext(mode: _currentCutMode);
    await SessionService().recordEvent(
      type: 'cut',
      description: '切割切换下一首',
    );
    _showSnackBar('✂️ 切割切换下一首', ThemeConfig.accentOrange);
  }

  void _playSoundEffect(String effectName) async {
    AppHaptics.medium();
    await _hardwareService.triggerSoundEffect(effectName, gain: 0.5);
    await SessionService().recordEvent(
      type: 'effect',
      description: '播放音效: $effectName',
      data: {'effect': effectName},
    );
    _showSnackBar('🎉 播放音效: $effectName', ThemeConfig.accentOrange);
  }

  void _toggleVoiceMode() {
    AppHaptics.medium();
    if (_isVoiceMode) {
      _setVolume(75);
      setState(() {
        _isVoiceMode = false;
      });
      _showSnackBar('🔊 已恢复正常音量');
    } else {
      _setVolume(25);
      setState(() {
        _isVoiceMode = true;
      });
      _showSnackBar('🎤 讲话模式（音量25%）', Color(0xFF4A90E2));
    }
  }

  void _seekTo(double value) {
    final positionMs = (value * _displayTotalDuration.inMilliseconds).toInt();
    _hardwareService.seekTo(positionMs);
    setState(() {
      _displayCurrentTime = Duration(milliseconds: positionMs);
      _displayProgress = value;
    });
  }

  void _showSnackBar(String message, [Color? color]) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: color ?? ThemeConfig.backgroundSecondary,
        duration: Duration(seconds: 1),
      ),
    );
  }

  void _showEnergySelector() {
    showModalBottomSheet(
      context: context,
      backgroundColor: ThemeConfig.backgroundSecondary,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(ThemeConfig.radiusLarge)),
      ),
      builder: (context) => Container(
        padding: EdgeInsets.all(ThemeConfig.spacingLarge),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('能量模式', style: TextStyle(color: ThemeConfig.textLight, fontSize: ThemeConfig.fontSizeLarge, fontWeight: FontWeight.bold)),
            SizedBox(height: ThemeConfig.spacingMedium),
            ...(_energyModes.map((mode) => ListTile(
              leading: Icon(mode['icon'], color: mode['color'], size: 32),
              title: Text(mode['label'], style: TextStyle(color: ThemeConfig.textLight)),
              trailing: _currentEnergyMode == mode['mode'] ? Icon(Icons.check, color: ThemeConfig.accentGreen) : null,
              onTap: () {
                Navigator.pop(context);
                _setEnergyMode(mode['mode']);
              },
            ))),
          ],
        ),
      ),
    );
  }

  void _showStyleSelector() {
    showModalBottomSheet(
      context: context,
      backgroundColor: ThemeConfig.backgroundSecondary,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(ThemeConfig.radiusLarge)),
      ),
      builder: (context) => Container(
        padding: EdgeInsets.all(ThemeConfig.spacingLarge),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('音乐风格', style: TextStyle(color: ThemeConfig.textLight, fontSize: ThemeConfig.fontSizeLarge, fontWeight: FontWeight.bold)),
            SizedBox(height: ThemeConfig.spacingMedium),
            Wrap(
              spacing: ThemeConfig.spacingMedium,
              runSpacing: ThemeConfig.spacingMedium,
              children: _musicStyles.map((style) => GestureDetector(
                onTap: () {
                  Navigator.pop(context);
                  _setMusicStyle(style['style']);
                },
                child: Container(
                  padding: EdgeInsets.symmetric(horizontal: ThemeConfig.spacingMedium, vertical: ThemeConfig.spacingSmall),
                  decoration: BoxDecoration(
                    color: _currentStyle == style['style'] ? ThemeConfig.accentGreen : ThemeConfig.backgroundPrimary.withOpacity(0.3),
                    borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                    border: Border.all(color: _currentStyle == style['style'] ? ThemeConfig.accentGreen : ThemeConfig.backgroundSecondary),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(style['icon'], color: ThemeConfig.textLight, size: 20),
                      SizedBox(width: 8),
                      Text(style['label'], style: TextStyle(color: ThemeConfig.textLight)),
                    ],
                  ),
                ),
              )).toList(),
            ),
          ],
        ),
      ),
    );
  }

  void _showEffectSelector() {
    showModalBottomSheet(
      context: context,
      backgroundColor: ThemeConfig.backgroundSecondary,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(ThemeConfig.radiusLarge)),
      ),
      builder: (context) => Container(
        padding: EdgeInsets.all(ThemeConfig.spacingLarge),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('加花音效', style: TextStyle(color: ThemeConfig.textLight, fontSize: ThemeConfig.fontSizeLarge, fontWeight: FontWeight.bold)),
            SizedBox(height: ThemeConfig.spacingMedium),
            Wrap(
              spacing: ThemeConfig.spacingMedium,
              runSpacing: ThemeConfig.spacingMedium,
              children: _soundEffects.map((effect) => GestureDetector(
                onTap: () {
                  Navigator.pop(context);
                  _playSoundEffect(effect['name']);
                },
                child: Container(
                  width: 80,
                  padding: EdgeInsets.all(ThemeConfig.spacingMedium),
                  decoration: BoxDecoration(
                    color: ThemeConfig.accentOrange.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                    border: Border.all(color: ThemeConfig.accentOrange),
                  ),
                  child: Column(
                    children: [
                      Icon(effect['icon'], color: ThemeConfig.accentOrange, size: 32),
                      SizedBox(height: 4),
                      Text(effect['label'], style: TextStyle(color: ThemeConfig.textLight, fontSize: ThemeConfig.fontSizeSmall)),
                    ],
                  ),
                ),
              )).toList(),
            ),
          ],
        ),
      ),
    );
  }

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes.toString().padLeft(2, '0');
    final seconds = (duration.inSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ThemeConfig.backgroundPrimary,
      body: SafeArea(
        child: Column(
          children: [
            _buildTopBar(),
            _buildDeviceStatusBar(),
            Expanded(child: _buildControlGrid()),
            _buildBottomControls(),
          ],
        ),
      ),
    );
  }

  Widget _buildDeviceStatusBar() {
    if (!_isDeviceConnected) {
      return Container(
        padding: EdgeInsets.symmetric(horizontal: ThemeConfig.spacingMedium, vertical: ThemeConfig.spacingSmall),
        decoration: BoxDecoration(
          color: ThemeConfig.accentRed.withOpacity(0.1),
          border: Border(bottom: BorderSide(color: ThemeConfig.accentRed.withOpacity(0.3))),
        ),
        child: Row(
          children: [
            Icon(Icons.warning, color: ThemeConfig.accentRed, size: 16),
            SizedBox(width: 8),
            Text('未连接 RK3588 设备', style: TextStyle(color: ThemeConfig.accentRed, fontSize: ThemeConfig.fontSizeSmall)),
          ],
        ),
      );
    }

    return Container(
      padding: EdgeInsets.symmetric(horizontal: ThemeConfig.spacingMedium, vertical: ThemeConfig.spacingSmall),
      decoration: BoxDecoration(
        color: ThemeConfig.accentSuccess.withOpacity(0.1),
        border: Border(bottom: BorderSide(color: ThemeConfig.accentSuccess.withOpacity(0.3))),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Icon(Icons.check_circle, color: ThemeConfig.accentSuccess, size: 16),
              SizedBox(width: 8),
              Text('RK3588 已连接', style: TextStyle(color: ThemeConfig.accentSuccess, fontSize: ThemeConfig.fontSizeSmall)),
            ],
          ),
          Row(
            children: [
              _buildStatusIndicator('麦克风', _edgeStatus?.micActive ?? false),
              SizedBox(width: 8),
              _buildStatusIndicator('音箱', _edgeStatus?.speakerActive ?? false),
              SizedBox(width: 8),
              _buildStatusIndicator('键盘', _edgeStatus?.keyboardActive ?? false),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildEmergencyStopButton() {
    return GestureDetector(
      onTap: _showEmergencyStopConfirmation,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: ThemeConfig.accentRed.withOpacity(0.2),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: ThemeConfig.accentRed, width: 2),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.warning_amber, color: ThemeConfig.accentRed, size: 20),
            SizedBox(width: 4),
            Text(
              'STOP',
              style: TextStyle(
                color: ThemeConfig.accentRed,
                fontSize: ThemeConfig.fontSizeSmall,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showEmergencyStopConfirmation() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: ThemeConfig.backgroundSecondary,
        title: Row(
          children: [
            Icon(Icons.warning_amber, color: ThemeConfig.accentRed, size: 28),
            SizedBox(width: 8),
            Text(
              '紧急停止',
              style: TextStyle(color: ThemeConfig.textLight, fontWeight: FontWeight.bold),
            ),
          ],
        ),
        content: Text(
          '确定要立即停止所有播放和音效吗？\n这将立即静音 Deck + SFX + MC。',
          style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.8)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('取消', style: TextStyle(color: ThemeConfig.textLight)),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _executeEmergencyStop();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: ThemeConfig.accentRed,
            ),
            child: Text('立即停止', style: TextStyle(color: ThemeConfig.textLight, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  Future<void> _executeEmergencyStop() async {
    AppHaptics.heavy();
    await _hardwareService.emergencyStop();
    await SessionService().recordEvent(
      type: 'emergency_stop',
      description: '执行紧急停止',
    );
    
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              Icon(Icons.warning_amber, color: ThemeConfig.textLight),
              SizedBox(width: 8),
              Text('紧急停止已执行', style: TextStyle(color: ThemeConfig.textLight)),
            ],
          ),
          backgroundColor: ThemeConfig.accentRed,
          duration: Duration(seconds: 3),
        ),
      );
    }
  }

  Widget _buildStatusIndicator(String label, bool isActive) {
    return Row(
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            color: isActive ? ThemeConfig.accentSuccess : ThemeConfig.textLight.withOpacity(0.3),
            borderRadius: BorderRadius.circular(4),
          ),
        ),
        SizedBox(width: 4),
        Text(label, style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.6), fontSize: ThemeConfig.fontSizeSmall)),
      ],
    );
  }

  Widget _buildTopBar() {
    return Container(
      padding: EdgeInsets.all(ThemeConfig.spacingMedium),
      decoration: BoxDecoration(
        color: ThemeConfig.backgroundSecondary.withOpacity(0.2),
        border: Border(bottom: BorderSide(color: ThemeConfig.backgroundSecondary.withOpacity(0.3))),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _edgeStatus?.currentTrack ?? widget.currentPlaylist?.name ?? '未选择歌单',
                      style: TextStyle(color: ThemeConfig.textLight, fontSize: ThemeConfig.fontSizeLarge, fontWeight: FontWeight.bold),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      _edgeStatus?.currentStyle ?? widget.currentPlaylist?.description ?? '请在歌单页选择',
                      style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.6), fontSize: ThemeConfig.fontSizeSmall),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              _buildEmergencyStopButton(),
              SizedBox(width: ThemeConfig.spacingSmall),
              Container(
                padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: widget.isPlaying ? ThemeConfig.accentSuccess : ThemeConfig.backgroundSecondary,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      widget.isPlaying ? Icons.play_arrow : Icons.pause,
                      color: ThemeConfig.textLight,
                      size: 16,
                    ),
                    SizedBox(width: 4),
                    Text(
                      widget.isPlaying ? '播放中' : '已暂停',
                      style: TextStyle(color: ThemeConfig.textLight, fontSize: ThemeConfig.fontSizeSmall, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: ThemeConfig.spacingMedium),
          Row(
            children: [
              Text(_formatDuration(_displayCurrentTime), style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.7), fontSize: ThemeConfig.fontSizeSmall, fontFamily: 'monospace')),
              Expanded(
                child: Slider(
                  value: _displayProgress.clamp(0.0, 1.0),
                  onChanged: _seekTo,
                  activeColor: ThemeConfig.accentOrange,
                  inactiveColor: ThemeConfig.backgroundSecondary.withOpacity(0.3),
                ),
              ),
              Text(_formatDuration(_displayTotalDuration), style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.7), fontSize: ThemeConfig.fontSizeSmall, fontFamily: 'monospace')),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildControlGrid() {
    return Padding(
      padding: EdgeInsets.all(ThemeConfig.spacingMedium),
      child: GridView.count(
        crossAxisCount: 3,
        mainAxisSpacing: ThemeConfig.spacingMedium,
        crossAxisSpacing: ThemeConfig.spacingMedium,
        childAspectRatio: 1.0,
        children: [
          _buildControlButton(
            icon: widget.isPlaying ? Icons.pause_circle_filled : Icons.play_circle_filled,
            label: widget.isPlaying ? '暂停' : '播放',
            color: ThemeConfig.accentOrange,
            onTap: _togglePlayPause,
            size: 72,
          ),
          _buildControlButton(
            icon: Icons.skip_next,
            label: '切歌',
            color: ThemeConfig.textLight.withOpacity(0.8),
            onTap: _nextTrack,
          ),
          _buildControlButton(
            icon: Icons.skip_previous,
            label: '上一首',
            color: ThemeConfig.textLight.withOpacity(0.8),
            onTap: _previousTrack,
          ),
          _buildControlButton(
            icon: _energyModes.firstWhere((e) => e['mode'] == _currentEnergyMode)['icon'],
            label: '能量',
            color: _energyModes.firstWhere((e) => e['mode'] == _currentEnergyMode)['color'],
            onTap: _showEnergySelector,
            isActive: true,
          ),
          _buildControlButton(
            icon: Icons.music_note,
            label: '风格',
            color: ThemeConfig.accentGreen,
            onTap: _showStyleSelector,
            isActive: true,
          ),
          _buildControlButton(
            icon: Icons.content_cut,
            label: '切割',
            color: ThemeConfig.accentOrange,
            onTap: _cutToNext,
          ),
          _buildControlButton(
            icon: _isLooping ? Icons.repeat_one : Icons.repeat,
            label: _isLooping ? '循环中' : '循环',
            color: _isLooping ? ThemeConfig.accentGreen : ThemeConfig.textLight.withOpacity(0.6),
            onTap: _toggleLoop,
            isActive: _isLooping,
          ),
          _buildControlButton(
            icon: Icons.auto_awesome,
            label: '加花',
            color: ThemeConfig.accentOrange,
            onTap: _showEffectSelector,
          ),
          _buildControlButton(
            icon: _isVoiceMode ? Icons.mic : Icons.mic_off,
            label: _isVoiceMode ? '讲话中' : '讲话',
            color: _isVoiceMode ? Color(0xFF4A90E2) : ThemeConfig.textLight.withOpacity(0.6),
            onTap: _toggleVoiceMode,
            isActive: _isVoiceMode,
          ),
        ],
      ),
    );
  }

  Widget _buildControlButton({
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
    bool isActive = false,
    double size = 56,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: Duration(milliseconds: 200),
        decoration: BoxDecoration(
          color: isActive ? color.withOpacity(0.2) : ThemeConfig.backgroundSecondary.withOpacity(0.3),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
          border: Border.all(color: isActive ? color : ThemeConfig.backgroundSecondary.withOpacity(0.3), width: isActive ? 2 : 1),
          boxShadow: isActive ? [BoxShadow(color: color.withOpacity(0.3), blurRadius: 8, offset: Offset(0, 4))] : ThemeConfig.cardShadow,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: size * 0.5, color: isActive ? color : ThemeConfig.textLight.withOpacity(0.8)),
            SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(color: ThemeConfig.textLight, fontSize: ThemeConfig.fontSizeSmall, fontWeight: isActive ? FontWeight.bold : FontWeight.normal),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBottomControls() {
    return Container(
      padding: EdgeInsets.all(ThemeConfig.spacingLarge),
      decoration: BoxDecoration(
        color: ThemeConfig.backgroundSecondary.withOpacity(0.2),
        border: Border(top: BorderSide(color: ThemeConfig.backgroundSecondary.withOpacity(0.3))),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Icon(Icons.volume_down, color: ThemeConfig.textLight.withOpacity(0.7), size: 24),
              Expanded(
                child: Slider(
                  value: _volume.toDouble(),
                  min: 0,
                  max: 100,
                  divisions: 100,
                  activeColor: ThemeConfig.accentOrange,
                  inactiveColor: ThemeConfig.backgroundSecondary.withOpacity(0.3),
                  onChanged: (value) => _setVolume(value.toInt()),
                ),
              ),
              Icon(Icons.volume_up, color: ThemeConfig.textLight.withOpacity(0.7), size: 24),
            ],
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildQuickButton(icon: Icons.remove, label: '-5', onTap: () => _setVolume(_volume - 5)),
              SizedBox(width: ThemeConfig.spacingMedium),
              Container(
                padding: EdgeInsets.symmetric(horizontal: ThemeConfig.spacingLarge, vertical: ThemeConfig.spacingSmall),
                decoration: BoxDecoration(
                  color: ThemeConfig.accentOrange.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                ),
                child: Text(
                  '$_volume%',
                  style: TextStyle(color: ThemeConfig.textLight, fontSize: ThemeConfig.fontSizeMedium, fontWeight: FontWeight.bold, fontFamily: 'monospace'),
                ),
              ),
              SizedBox(width: ThemeConfig.spacingMedium),
              _buildQuickButton(icon: Icons.add, label: '+5', onTap: () => _setVolume(_volume + 5)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildQuickButton({required IconData icon, required String label, required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.all(ThemeConfig.spacingSmall),
        decoration: BoxDecoration(
          color: ThemeConfig.backgroundSecondary.withOpacity(0.3),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: ThemeConfig.textLight, size: 20),
            SizedBox(width: 4),
            Text(label, style: TextStyle(color: ThemeConfig.textLight, fontSize: ThemeConfig.fontSizeSmall)),
          ],
        ),
      ),
    );
  }
}