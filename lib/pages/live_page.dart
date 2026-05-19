import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../state/providers.dart';
import '../../widgets/nine_key_grid.dart';
import '../../widgets/transport_bar.dart';
import '../../models/models.dart';

class LivePage extends ConsumerStatefulWidget {
  const LivePage({super.key});

  @override
  ConsumerState<LivePage> createState() => _LivePageState();
}

class _LivePageState extends ConsumerState<LivePage> {
  Timer? _nextPressTimer;
  bool _isNextPressed = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(liveProvider.notifier).setConnected(true);
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
      body: SafeArea(
        child: Column(
          children: [
            if (device != null && device.hasWarning)
              _WarningBanner(device: device),

            Padding(
              padding: const EdgeInsets.all(16),
              child: const TransportBar(),
            ),

            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: AbsorbPointer(
                  absorbing: !liveState.isConnected,
                  child: Opacity(
                    opacity: liveState.isConnected ? 1.0 : 0.5,
                    child: const NineKeyGrid(),
                  ),
                ),
              ),
            ),

            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: liveState.isConnected
                          ? () => _togglePauseResume(playback)
                          : null,
                      icon: Icon(
                        playback?.paused == true
                            ? Icons.play_arrow
                            : Icons.pause,
                      ),
                      label: Text(
                        playback?.paused == true ? 'Resume' : 'Pause',
                      ),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: liveState.isConnected
                          ? () => _handleNextPress()
                          : null,
                      onLongPress: liveState.isConnected
                          ? () => _executeNext()
                          : null,
                      icon: const Icon(Icons.skip_next),
                      label: const Text('Hold for Next'),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        backgroundColor: theme.colorScheme.secondary,
                        foregroundColor: theme.colorScheme.onSecondary,
                      ),
                    ),
                  ),
                ],
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

  void _handleNextPress() {
    if (_isNextPressed) return;

    setState(() => _isNextPressed = true);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Long press 0.5s to skip'),
        duration: Duration(seconds: 1),
      ),
    );

    _nextPressTimer = Timer(const Duration(milliseconds: 500), () {
      setState(() => _isNextPressed = false);
    });
  }

  void _executeNext() {
    HapticFeedback.heavyImpact();
    ref.read(playbackProvider.notifier).next();
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
          const Icon(
            Icons.warning_amber,
            color: Colors.white,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              messages.join(' | '),
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
