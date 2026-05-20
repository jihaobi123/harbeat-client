import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../state/providers.dart';
import '../models/models.dart';
import '../core/api/rk_client.dart';

enum EnergyLevel { high, medium, low }
enum MusicStyle { hiphop, breaking }

class LivePage extends ConsumerStatefulWidget {
  const LivePage({super.key});

  @override
  ConsumerState<LivePage> createState() => _LivePageState();
}

class _LivePageState extends ConsumerState<LivePage> {
  Timer? _nextPressTimer;
  bool _isNextPressed = false;
  EnergyLevel _selectedEnergy = EnergyLevel.medium;
  MusicStyle _selectedStyle = MusicStyle.hiphop;
  bool _isLooping = false;
  bool _isFxPanelOpen = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        final rkClient = ref.read(rkClientProvider);
        if (rkClient.isConnected) {
          ref.read(liveProvider.notifier).setConnected(true);
        }
      }
    });
  }

  @override
  void dispose() {
    _nextPressTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final playback = ref.watch(playbackProvider);
    final device = ref.watch(deviceProvider);
    final liveState = ref.watch(liveProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('AI DJ 控制台'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {},
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (device != null && device.hasWarning)
              _WarningBanner(device: device),

            _CurrentTrackInfo(playback: playback),

            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    _TransportControls(
                      playback: playback,
                      isConnected: liveState.isConnected,
                      isLooping: _isLooping,
                      onPlayPause: () => _togglePauseResume(playback),
                      onLoop: () => _toggleLoop(),
                      onNext: () => _executeNext(),
                    ),
                    const SizedBox(height: 20),
                    _EnergyButtons(
                      selected: _selectedEnergy,
                      onSelect: (energy) => _selectEnergy(energy),
                      enabled: liveState.isConnected,
                    ),
                    const SizedBox(height: 20),
                    _StyleButtons(
                      selected: _selectedStyle,
                      onSelect: (style) => _selectStyle(style),
                      enabled: liveState.isConnected,
                    ),
                    const SizedBox(height: 20),
                    _MixButtons(enabled: liveState.isConnected),
                    const SizedBox(height: 20),
                    _FxPanel(
                      isOpen: _isFxPanelOpen,
                      onToggle: () => setState(() => _isFxPanelOpen = !_isFxPanelOpen),
                      enabled: liveState.isConnected,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _togglePauseResume(PlaybackState? playback) {
    HapticFeedback.mediumImpact();
    if (playback?.paused == true) {
      ref.read(playbackProvider.notifier).resume();
    } else {
      ref.read(playbackProvider.notifier).pause();
    }
  }

  void _toggleLoop() {
    setState(() => _isLooping = !_isLooping);
    HapticFeedback.mediumImpact();
    if (_isLooping) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已启用循环模式（前30秒）')),
      );
    }
  }

  void _executeNext() {
    HapticFeedback.heavyImpact();
    ref.read(playbackProvider.notifier).next();
  }

  void _selectEnergy(EnergyLevel energy) {
    setState(() => _selectedEnergy = energy);
    HapticFeedback.lightImpact();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('能量: ${_getEnergyLabel(energy)}')),
    );
  }

  void _selectStyle(MusicStyle style) {
    setState(() => _selectedStyle = style);
    HapticFeedback.lightImpact();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('风格: ${_getStyleLabel(style)}')),
    );
  }

  String _getEnergyLabel(EnergyLevel energy) {
    switch (energy) {
      case EnergyLevel.high: return '高能量';
      case EnergyLevel.medium: return '中能量';
      case EnergyLevel.low: return '低能量';
    }
  }

  String _getStyleLabel(MusicStyle style) {
    switch (style) {
      case MusicStyle.hiphop: return 'Hiphop';
      case MusicStyle.breaking: return 'Breaking';
    }
  }
}

class _CurrentTrackInfo extends StatelessWidget {
  final PlaybackState? playback;

  const _CurrentTrackInfo({required this.playback});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          Text(
            playback?.currentSongId != null
                ? '歌曲 #${playback!.currentSongId}'
                : '未播放',
            style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                '-- BPM',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(width: 16),
              Container(width: 2, height: 16, color: theme.dividerColor),
              const SizedBox(width: 16),
              Text(
                playback?.paused == true ? '已暂停' : (playback != null ? '播放中' : '空闲'),
                style: theme.textTheme.bodyMedium,
              ),
            ],
          ),
          if (playback != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Column(
                children: [
                  Slider(
                    value: playback!.positionSec,
                    max: 180,
                    onChanged: (value) => {},
                  ),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(_formatTime(playback!.positionSec)),
                      const Text('3:00'),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  String _formatTime(double seconds) {
    final mins = (seconds ~/ 60).toString().padLeft(2, '0');
    final secs = (seconds % 60).toStringAsFixed(0).padLeft(2, '0');
    return '$mins:$secs';
  }
}

class _TransportControls extends StatelessWidget {
  final PlaybackState? playback;
  final bool isConnected;
  final bool isLooping;
  final VoidCallback onPlayPause;
  final VoidCallback onLoop;
  final VoidCallback onNext;

  const _TransportControls({
    required this.playback,
    required this.isConnected,
    required this.isLooping,
    required this.onPlayPause,
    required this.onLoop,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        Expanded(
          child: ElevatedButton.icon(
            onPressed: isConnected ? onPlayPause : null,
            icon: Icon(
              playback?.paused == true ? Icons.play_arrow : Icons.pause,
              size: 24,
            ),
            label: Text(
              playback?.paused == true ? '播放' : '暂停',
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
            ),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: Colors.white,
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: ElevatedButton.icon(
            onPressed: isConnected ? onLoop : null,
            icon: Icon(isLooping ? Icons.repeat_one : Icons.repeat, size: 24),
            label: Text(
              isLooping ? '循环中' : '循环',
              style: TextStyle(
                color: isLooping ? Colors.white : theme.colorScheme.onSurface,
                fontWeight: FontWeight.bold,
              ),
            ),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
              backgroundColor: isLooping ? Colors.blue : theme.colorScheme.surface,
              foregroundColor: isLooping ? Colors.white : theme.colorScheme.onSurface,
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: ElevatedButton.icon(
            onPressed: isConnected ? onNext : null,
            icon: const Icon(Icons.skip_next, size: 24),
            label: const Text('下一首'),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
              backgroundColor: theme.colorScheme.surface,
              foregroundColor: theme.colorScheme.onSurface,
            ),
          ),
        ),
      ],
    );
  }
}

class _EnergyButtons extends StatelessWidget {
  final EnergyLevel selected;
  final ValueChanged<EnergyLevel> onSelect;
  final bool enabled;

  const _EnergyButtons({
    required this.selected,
    required this.onSelect,
    required this.enabled,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('能量等级', style: TextStyle(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: ElevatedButton(
                onPressed: enabled ? () => onSelect(EnergyLevel.high) : null,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: selected == EnergyLevel.high ? Colors.red : theme.colorScheme.surface,
                  foregroundColor: selected == EnergyLevel.high ? Colors.white : theme.colorScheme.onSurface,
                  side: BorderSide(color: Colors.red, width: selected == EnergyLevel.high ? 2 : 1),
                ),
                child: const Text('高', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: ElevatedButton(
                onPressed: enabled ? () => onSelect(EnergyLevel.medium) : null,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: selected == EnergyLevel.medium ? Colors.yellow : theme.colorScheme.surface,
                  foregroundColor: selected == EnergyLevel.medium ? Colors.white : theme.colorScheme.onSurface,
                  side: BorderSide(color: Colors.yellow, width: selected == EnergyLevel.medium ? 2 : 1),
                ),
                child: const Text('中', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: ElevatedButton(
                onPressed: enabled ? () => onSelect(EnergyLevel.low) : null,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: selected == EnergyLevel.low ? Colors.green : theme.colorScheme.surface,
                  foregroundColor: selected == EnergyLevel.low ? Colors.white : theme.colorScheme.onSurface,
                  side: BorderSide(color: Colors.green, width: selected == EnergyLevel.low ? 2 : 1),
                ),
                child: const Text('低', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _StyleButtons extends StatelessWidget {
  final MusicStyle selected;
  final ValueChanged<MusicStyle> onSelect;
  final bool enabled;

  const _StyleButtons({
    required this.selected,
    required this.onSelect,
    required this.enabled,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('风格切换', style: TextStyle(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: ElevatedButton(
                onPressed: enabled ? () => onSelect(MusicStyle.hiphop) : null,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: selected == MusicStyle.hiphop
                      ? theme.colorScheme.primary
                      : theme.colorScheme.surface,
                  foregroundColor: selected == MusicStyle.hiphop
                      ? Colors.white
                      : theme.colorScheme.onSurface,
                ),
                child: const Text('Hiphop', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: ElevatedButton(
                onPressed: enabled ? () => onSelect(MusicStyle.breaking) : null,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: selected == MusicStyle.breaking
                      ? theme.colorScheme.primary
                      : theme.colorScheme.surface,
                  foregroundColor: selected == MusicStyle.breaking
                      ? Colors.white
                      : theme.colorScheme.onSurface,
                ),
                child: const Text('Breaking', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _MixButtons extends StatelessWidget {
  final bool enabled;

  const _MixButtons({required this.enabled});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('混音切割', style: TextStyle(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: ElevatedButton(
                onPressed: enabled ? () => _executeMix('smooth') : null,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: Colors.purple.shade100,
                  foregroundColor: Colors.purple,
                ),
                child: const Text('平滑过渡'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: ElevatedButton(
                onPressed: enabled ? () => _executeMix('energy') : null,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: Colors.orange.shade100,
                  foregroundColor: Colors.orange,
                ),
                child: const Text('能量提升'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: ElevatedButton(
                onPressed: enabled ? () => _executeMix('hard') : null,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: Colors.blue.shade100,
                  foregroundColor: Colors.blue,
                ),
                child: const Text('硬切'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  void _executeMix(String type) {
    HapticFeedback.mediumImpact();
  }
}

class _FxPanel extends StatelessWidget {
  final bool isOpen;
  final VoidCallback onToggle;
  final bool enabled;

  const _FxPanel({
    required this.isOpen,
    required this.onToggle,
    required this.enabled,
  });

  static const List<Map<String, String>> fxList = [
    {'label': 'ha!', 'icon': '😎'},
    {'label': 'scratch', 'icon': '🎧'},
    {'label': 'horn', 'icon': '📯'},
    {'label': 'drum', 'icon': '🥁'},
    {'label': 'bass', 'icon': '🔊'},
    {'label': 'hat', 'icon': '👒'},
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text('一键加花', style: TextStyle(fontWeight: FontWeight.bold)),
            IconButton(
              icon: Icon(isOpen ? Icons.expand_less : Icons.expand_more),
              onPressed: onToggle,
            ),
          ],
        ),
        if (isOpen)
          GridView.count(
            crossAxisCount: 3,
            mainAxisSpacing: 8,
            crossAxisSpacing: 8,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            children: fxList.map((fx) => _FxButton(
              label: fx['label']!,
              icon: fx['icon']!,
              onTap: () => _triggerFx(fx['label']!),
              enabled: enabled,
            )).toList(),
          ),
      ],
    );
  }

  void _triggerFx(String fxName) {
    HapticFeedback.lightImpact();
  }
}

class _FxButton extends StatelessWidget {
  final String label;
  final String icon;
  final VoidCallback onTap;
  final bool enabled;

  const _FxButton({
    required this.label,
    required this.icon,
    required this.onTap,
    required this.enabled,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ElevatedButton(
      onPressed: enabled ? onTap : null,
      style: ElevatedButton.styleFrom(
        padding: const EdgeInsets.all(12),
        backgroundColor: theme.colorScheme.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      child: Column(
        children: [
          Text(icon, style: const TextStyle(fontSize: 24)),
          const SizedBox(height: 4),
          Text(label, style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }
}

class _WarningBanner extends StatelessWidget {
  final DeviceInfo device;

  const _WarningBanner({required this.device});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final messages = <String>[];

    if (device.isOverheating) {
      messages.add('RK温度过高: ${device.tempC.toStringAsFixed(1)}°C');
    }
    if (device.hasAudioIssues) {
      messages.add('音频XRun: ${device.audioXrunCount}次');
    }
    if (!device.jetsonReachable) {
      messages.add('Jetson离线');
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      color: theme.colorScheme.error,
      child: Row(
        children: [
          const Icon(Icons.warning_amber, color: Colors.white),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              messages.join(' | '),
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
    );
  }
}