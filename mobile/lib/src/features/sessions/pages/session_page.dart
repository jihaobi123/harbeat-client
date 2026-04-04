import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/neon_button.dart';
import '../../../core/widgets/section_title.dart';
import '../../auth/auth_controller.dart';
import '../../library/library_service.dart';
import '../../player/player_controller.dart';
import '../models.dart';
import '../sessions_service.dart';

class SessionPage extends StatefulWidget {
  const SessionPage({super.key});

  @override
  State<SessionPage> createState() => _SessionPageState();
}

class _SessionPageState extends State<SessionPage> {
  final _service = SessionsService();
  final _libraryService = LibraryService();
  final List<int> _durations = const [15, 30, 60, 90];

  int _selectedDuration = 30;
  int? _activeSessionId;
  bool _loading = false;
  bool _ending = false;
  String? _error;
  List<PracticeTrack> _tracks = [];
  DateTime? _sessionStartedAt;

  String get _modeLabel => _selectedDuration >= 60 ? 'marathon' : 'practice';

  Future<void> _startSession() async {
    final auth = context.read<AuthController>();
    final user = auth.currentUser;
    if (user == null) {
      setState(() => _error = 'Please login again before starting a session.');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final sessionId = await _service.startSession(
        userId: user.id,
        mode: _modeLabel,
      );
      final tracks = await _service.generatePracticeList(
        userId: user.id,
        targetDuration: _selectedDuration,
        danceStyle: user.danceStyle.isEmpty ? null : user.danceStyle,
      );
      await _service.logSessionEvent(
        sessionId: sessionId,
        eventType: 'session_started',
        eventValue: '${_selectedDuration}m',
      );

      if (!mounted) return;
      setState(() {
        _activeSessionId = sessionId;
        _tracks = tracks;
        _sessionStartedAt = DateTime.now();
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _endSession() async {
    final sessionId = _activeSessionId;
    if (sessionId == null) return;

    setState(() => _ending = true);
    try {
      await _service.endSession(sessionId);
      if (!mounted) return;
      setState(() {
        _activeSessionId = null;
        _tracks = [];
        _sessionStartedAt = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Session ended.')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('End session failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _ending = false);
    }
  }

  Future<void> _playTrack(PracticeTrack track) async {
    final player = context.read<PlayerController>();
    final auth = context.read<AuthController>();

    await player.setTrack(
      PlayerTrack(
        songId: track.id,
        title: track.title,
        artist: track.artist,
        originalUrl: auth.session == null
            ? null
            : _libraryService.getStreamUrl(track.id, auth.session!.accessToken),
        bpm: track.bpm?.round(),
      ),
      play: true,
    );

    final sessionId = _activeSessionId;
    final user = auth.currentUser;
    if (sessionId == null || user == null) return;

    try {
      await _service.logSessionEvent(
        sessionId: sessionId,
        eventType: 'track_selected',
        eventValue: track.id,
      );
      await _service.logInteraction({
        'user_id': user.id,
        'track_id': track.id,
        'action_type': 'play',
        'listen_mode': _modeLabel,
        'current_dance_style': user.danceStyle,
      });
    } catch (_) {
      // Keep UX smooth even if analytics logging fails.
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final user = auth.currentUser;
    final elapsed = _sessionStartedAt == null
        ? '--:--'
        : _formatElapsed(DateTime.now().difference(_sessionStartedAt!));

    return Scaffold(
      appBar: AppBar(
        title: const Text('HarBeat'),
        actions: [
          if (_activeSessionId != null)
            TextButton(
              onPressed: _ending ? null : _endSession,
              child: Text(
                'END',
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                      color: AppColors.secondary,
                    ),
              ),
            ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 180),
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(28),
                color: AppColors.surfaceContainerHigh,
              ),
              child: Column(
                children: [
                  Text(
                    _activeSessionId == null ? 'SESSION READY' : 'LIVE SESSION',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: AppColors.secondary,
                        ),
                  ),
                  const SizedBox(height: 18),
                  Container(
                    width: 220,
                    height: 220,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(color: AppColors.secondary, width: 2),
                    ),
                    child: Center(
                      child: Text(
                        elapsed,
                        style: Theme.of(context).textTheme.displayLarge,
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    _tracks.isEmpty ? 'No queue yet' : _tracks.first.title,
                    style: Theme.of(context).textTheme.headlineLarge,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _tracks.isEmpty
                        ? 'Pick a duration and generate a practice flow.'
                        : '${_tracks.first.artist} - ${_tracks.first.bpm?.round() ?? '--'} BPM',
                    style: Theme.of(context).textTheme.bodySmall,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 18),
                  GridView.count(
                    crossAxisCount: 2,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    childAspectRatio: 1.8,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                    children: [
                      _QuickAction(
                        icon: Icons.queue_music,
                        label: '${_tracks.length} Tracks',
                      ),
                      _QuickAction(
                        icon: Icons.sports_martial_arts,
                        label: user?.danceStyle.isEmpty ?? true
                            ? 'Style Free'
                            : user!.danceStyle,
                      ),
                      _QuickAction(
                        icon: Icons.timer_outlined,
                        label: '$_selectedDuration Min',
                      ),
                      _QuickAction(
                        icon: Icons.local_fire_department_outlined,
                        label: _modeLabel,
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 28),
            const SectionTitle(title: 'Configure Practice'),
            const SizedBox(height: 16),
            Row(
              children: _durations
                  .map(
                    (duration) => Expanded(
                      child: Padding(
                        padding: EdgeInsets.only(
                          right: duration == _durations.last ? 0 : 10,
                        ),
                        child: _DurationCard(
                          label: '${duration}m',
                          selected: _selectedDuration == duration,
                          onTap: () => setState(() => _selectedDuration = duration),
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
            const SizedBox(height: 20),
            NeonButton(
              label: _activeSessionId == null ? 'Start Session' : 'Refresh Practice List',
              onPressed: _loading ? null : _startSession,
            ),
            if (_error != null) ...[
              const SizedBox(height: 14),
              _MessageCard(message: _error!),
            ],
            const SizedBox(height: 28),
            const SectionTitle(title: 'Practice Queue'),
            const SizedBox(height: 16),
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 48),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_tracks.isEmpty)
              const _MessageCard(
                message: 'Start a session to generate a queue from your current profile.',
              )
            else
              ..._tracks.asMap().entries.map(
                    (entry) => Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: _PracticeTrackTile(
                        index: entry.key + 1,
                        track: entry.value,
                        onTap: () => _playTrack(entry.value),
                      ),
                    ),
                  ),
          ],
        ),
      ),
    );
  }

  String _formatElapsed(Duration duration) {
    final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }
}

class _QuickAction extends StatelessWidget {
  const _QuickAction({
    required this.icon,
    required this.label,
  });

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: AppColors.surfaceContainerLow,
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: AppColors.primary),
          const SizedBox(height: 8),
          Text(
            label.toUpperCase(),
            style: Theme.of(context).textTheme.labelSmall,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

class _DurationCard extends StatelessWidget {
  const _DurationCard({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Ink(
          height: 74,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            color: selected ? AppColors.surfaceContainerHighest : AppColors.surfaceContainerLow,
            border: Border.all(
              color: selected ? AppColors.primary : AppColors.outlineVariant,
            ),
          ),
          child: Center(
            child: Text(
              label,
              style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                    color: selected ? AppColors.primary : AppColors.onSurfaceVariant,
                  ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PracticeTrackTile extends StatelessWidget {
  const _PracticeTrackTile({
    required this.index,
    required this.track,
    required this.onTap,
  });

  final int index;
  final PracticeTrack track;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(22),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(22),
          color: AppColors.surfaceContainerLow,
        ),
        child: Row(
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(14),
                color: AppColors.primary.withValues(alpha: 0.18),
              ),
              alignment: Alignment.center,
              child: Text(
                '$index',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      color: AppColors.primary,
                    ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(track.title, style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Text(
                    '${track.artist} - ${track.bpm?.round() ?? '--'} BPM',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            Text(
              '${track.duration.round()}s',
              style: Theme.of(context).textTheme.labelSmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _MessageCard extends StatelessWidget {
  const _MessageCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        color: AppColors.surfaceContainerHigh,
      ),
      child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
    );
  }
}
