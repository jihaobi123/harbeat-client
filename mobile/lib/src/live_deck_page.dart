import 'dart:async';

import 'package:flutter/material.dart';

import 'edge_agent_client.dart';
import 'live_models.dart';

class LiveDeckPage extends StatefulWidget {
  const LiveDeckPage({
    super.key,
    required this.edgeClient,
  });

  final EdgeAgentClient edgeClient;

  @override
  State<LiveDeckPage> createState() => _LiveDeckPageState();
}

class _LiveDeckPageState extends State<LiveDeckPage> {
  LivePlaybackState? _state;
  bool _connected = false;
  String? _error;
  Timer? _pollTimer;
  Duration _pollInterval = const Duration(milliseconds: 1500);
  DateTime _lastPollTime = DateTime.now();
  bool _acting = false;

  static const _fastPoll = Duration(milliseconds: 1500);
  static const _slowPoll = Duration(seconds: 5);

  @override
  void initState() {
    super.initState();
    _pollState();
    _startPolling();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  void _startPolling() {
    _pollTimer = Timer.periodic(_pollInterval, (_) => _pollState());
  }

  void _adjustPollInterval(Duration newInterval) {
    if (_pollInterval == newInterval) return;
    _pollInterval = newInterval;
    _pollTimer?.cancel();
    _startPolling();
  }

  Future<void> _pollState() async {
    try {
      final state = await widget.edgeClient.getState();
      if (!mounted) return;
      final wasDisconnected = !_connected;
      setState(() {
        _state = state;
        _connected = state.error == null;
        _error = state.error;
        _lastPollTime = DateTime.now();
      });
      if (wasDisconnected && _connected) {
        _adjustPollInterval(_fastPoll);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _connected = false;
        _error = 'Poll failed: $e';
      });
      _adjustPollInterval(_slowPoll);
    }
  }

  // ── Actions ──────────────────────────────────────────────────────

  Future<void> _handleAction(String action) async {
    if (_acting || !_connected) return;
    setState(() => _acting = true);

    try {
      switch (action) {
        case 'play_pause':
          if (_state?.playing == true) {
            await widget.edgeClient.pause();
          } else {
            await widget.edgeClient.resume();
          }
          break;
        case 'skip_now':
          await widget.edgeClient.liveOverride(
            LiveOverrideRequest(execute: 'now'),
          );
          break;
        case 'delay':
          await widget.edgeClient.liveOverride(
            LiveOverrideRequest(execute: 'next_bar'),
          );
          break;
        case 'shorter':
          await widget.edgeClient.liveIntent(
            LiveIntentRequest(intent: 'harder', scope: 'next_transition'),
          );
          break;
        case 'longer':
          await widget.edgeClient.liveIntent(
            LiveIntentRequest(intent: 'smoother', scope: 'next_transition'),
          );
          break;
        case 'safer':
          await widget.edgeClient.liveIntent(
            LiveIntentRequest(intent: 'safer', scope: 'next_transition'),
          );
          break;
        case 'energy_up':
          await widget.edgeClient.liveIntent(
            LiveIntentRequest(intent: 'energy_up', scope: 'next_transition'),
          );
          break;
        case 'energy_down':
          await widget.edgeClient.liveIntent(
            LiveIntentRequest(intent: 'energy_down', scope: 'next_transition'),
          );
          break;
        case 'vocal_safe':
          await widget.edgeClient.liveIntent(
            LiveIntentRequest(intent: 'vocal_safe', scope: 'next_transition'),
          );
          break;
        case 'instrumental':
          await widget.edgeClient.liveIntent(
            LiveIntentRequest(intent: 'instrumental', scope: 'next_transition'),
          );
          break;
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$action sent'), duration: const Duration(seconds: 1)),
        );
      }
      _pollState(); // immediate refresh
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$action failed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  // ── Build Helpers ────────────────────────────────────────────────

  Widget _sectionBadge(String? section) {
    if (section == null || section.isEmpty) return const SizedBox.shrink();
    const colors = {
      'intro': Colors.blue,
      'verse': Colors.teal,
      'chorus': Colors.orange,
      'drop': Colors.deepOrange,
      'bridge': Colors.purple,
      'outro': Colors.red,
      'breakdown': Colors.indigo,
      'build': Colors.amber,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: colors[section.toLowerCase()] ?? Colors.grey,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        section.toUpperCase(),
        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
      ),
    );
  }

  Widget _tierBadge(String? tier) {
    if (tier == null) return const SizedBox.shrink();
    final color = {
      'stem_aware': Colors.green,
      'non_stem': Colors.amber,
      'basic': Colors.grey,
    }[tier] ?? Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withAlpha(60),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color),
      ),
      child: Text(
        tier.replaceAll('_', ' ').toUpperCase(),
        style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600),
      ),
    );
  }

  Widget _riskBadge(String tag) {
    final isRisky = ['double_vocal', 'bass_conflict', 'bpm_risky', 'key_tense']
        .contains(tag);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      margin: const EdgeInsets.only(right: 4),
      decoration: BoxDecoration(
        color: isRisky ? Colors.red.shade900 : Colors.grey.shade800,
        borderRadius: BorderRadius.circular(4),
        border: isRisky ? Border.all(color: Colors.redAccent) : null,
      ),
      child: Text(
        tag.replaceAll('_', ' ').toUpperCase(),
        style: TextStyle(
          fontSize: 9,
          color: isRisky ? Colors.redAccent : Colors.grey.shade400,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _energyMeter(double? energy) {
    final value = energy ?? 0.0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text('Energy', style: TextStyle(fontSize: 12, color: Colors.grey)),
            const Spacer(),
            Text('${(value * 100).toInt()}%',
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          ],
        ),
        const SizedBox(height: 4),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: value.clamp(0.0, 1.0),
            minHeight: 8,
            backgroundColor: Colors.grey.shade800,
            valueColor: AlwaysStoppedAnimation<Color>(
              Color.lerp(Colors.blue, Colors.orange, value)!,
            ),
          ),
        ),
      ],
    );
  }

  String _formatTime(double seconds) {
    final mins = (seconds / 60).floor();
    final secs = (seconds % 60).floor();
    return '${mins.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}';
  }

  // ── Build ────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final state = _state;
    final next = state?.nextTransition;

    // Estimated countdown (interpolate from last poll)
    double countdown = 0;
    if (next != null && state != null && state.playing) {
      final elapsed = DateTime.now().difference(_lastPollTime).inMilliseconds / 1000.0;
      countdown = (next.startsInSec - elapsed).clamp(0, 9999);
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // ── Connection Status ──
        Card(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                Icon(
                  Icons.circle,
                  size: 10,
                  color: _connected ? Colors.green : Colors.red,
                ),
                const SizedBox(width: 8),
                Text(
                  _connected ? 'RK Online' : 'RK Offline',
                  style: TextStyle(
                    color: _connected ? Colors.green : Colors.red,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const Spacer(),
                if (_error != null)
                  Flexible(
                    child: Text(
                      _error!,
                      style: const TextStyle(fontSize: 11, color: Colors.grey),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                if (!_connected)
                  TextButton(
                    onPressed: _pollState,
                    child: const Text('Retry'),
                  ),
              ],
            ),
          ),
        ),

        const SizedBox(height: 12),

        // ── Now Playing ──
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        state?.currentSongId ?? 'No track',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                    ),
                    if (state?.currentSection != null)
                      _sectionBadge(state!.currentSection!),
                  ],
                ),
                const SizedBox(height: 8),
                if (state != null) ...[
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: LinearProgressIndicator(
                      value: state.durationSec > 0
                          ? (state.positionSec / state.durationSec).clamp(0.0, 1.0)
                          : 0,
                      minHeight: 6,
                      backgroundColor: Colors.grey.shade800,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Text(_formatTime(state.positionSec),
                          style: const TextStyle(fontSize: 13)),
                      const Spacer(),
                      Text(_formatTime(state.durationSec),
                          style: const TextStyle(fontSize: 13, color: Colors.grey)),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      _tierBadge(state.playbackTier),
                      const Spacer(),
                      _energyMeter(state.currentEnergy),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),

        const SizedBox(height: 12),

        // ── Next Transition ──
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('NEXT TRANSITION',
                    style: TextStyle(fontSize: 11, color: Colors.grey, letterSpacing: 1.2)),
                const SizedBox(height: 8),
                if (next != null) ...[
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'to: ${next.toSongId}',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.orange.withAlpha(40),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.orange),
                        ),
                        child: Text(
                          next.style.replaceAll('_', ' ').toUpperCase(),
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: Colors.orange,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      const Icon(Icons.timer, size: 16, color: Colors.grey),
                      const SizedBox(width: 4),
                      Text(
                        'In ${countdown.toInt()}s',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Text(
                        'confidence: ${(next.confidence * 100).toInt()}%',
                        style: const TextStyle(fontSize: 12, color: Colors.grey),
                      ),
                    ],
                  ),
                  if (next.tags.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 4,
                      runSpacing: 4,
                      children: next.tags.map((t) => _riskBadge(t)).toList(),
                    ),
                  ],
                ] else ...[
                  const Text('No upcoming transition',
                      style: TextStyle(color: Colors.grey)),
                ],
              ],
            ),
          ),
        ),

        const SizedBox(height: 12),

        // ── Actions ──
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('TRANSPORT',
                    style: TextStyle(fontSize: 11, color: Colors.grey, letterSpacing: 1.2)),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    _actionBtn(
                      _state?.playing == true ? 'Pause' : 'Play',
                      Icons.play_arrow,
                      'play_pause',
                    ),
                    _actionBtn('Skip Now', Icons.skip_next, 'skip_now'),
                    _actionBtn('Delay 8 bars', Icons.timer, 'delay'),
                  ],
                ),
                const SizedBox(height: 20),
                const Text('CONTROL',
                    style: TextStyle(fontSize: 11, color: Colors.grey, letterSpacing: 1.2)),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    _actionBtn('Shorter', Icons.compress, 'shorter'),
                    _actionBtn('Longer', Icons.expand, 'longer'),
                    _actionBtn('Safer', Icons.shield, 'safer'),
                    _actionBtn('Energy Up', Icons.trending_up, 'energy_up'),
                    _actionBtn('Energy Down', Icons.trending_down, 'energy_down'),
                    _actionBtn('Vocal Safe', Icons.mic_off, 'vocal_safe'),
                    _actionBtn('Instrumental', Icons.piano, 'instrumental'),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _actionBtn(String label, IconData icon, String action) {
    return FilledButton.tonal(
      onPressed: (_connected && !_acting) ? () => _handleAction(action) : null,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18),
          const SizedBox(width: 6),
          Text(label),
        ],
      ),
    );
  }
}
