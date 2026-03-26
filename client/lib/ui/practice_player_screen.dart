import 'dart:io' as io;

import 'package:audio_waveforms/audio_waveforms.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../core/audio/audio_player_service.dart';
import '../core/network/api_repository.dart';
import '../providers/practice_session_provider.dart';

class PracticePlayerScreen extends ConsumerStatefulWidget {
  final int userId;
  final int trackId;
  final String mode;

  const PracticePlayerScreen({
    super.key,
    this.userId = 1,
    this.trackId = 1,
    this.mode = 'practice',
  });

  @override
  ConsumerState<PracticePlayerScreen> createState() => _PracticePlayerScreenState();
}

class _PracticePlayerScreenState extends ConsumerState<PracticePlayerScreen> {
  late final PlayerController _waveController;
  bool _isWaveLoaded = false;
  String _localPath = '';
  TrackDto? _track;

  @override
  void initState() {
    super.initState();
    _waveController = PlayerController();
    _prepareAudioAndWaveform();
  }

  @override
  void dispose() {
    _waveController.dispose();
    super.dispose();
  }

  Future<void> _prepareAudioAndWaveform() async {
    try {
      final api = ref.read(apiRepoProvider);
      final track = await api.fetchTrack(widget.trackId);
      final networkUrl = api.resolveMediaUrl(track.originalUrl);

      final appDocDir = await getApplicationDocumentsDirectory();
      _localPath = p.join(appDocDir.path, 'track_${widget.trackId}_${p.basename(track.originalUrl)}');

      if (!await io.File(_localPath).exists()) {
        await Dio().download(networkUrl, _localPath);
      }

      await ref.read(audioPlayerProvider).loadAudio(networkUrl);
      await ref.read(practiceProvider.notifier).initialize(
        userId: widget.userId,
        trackId: widget.trackId,
        mode: widget.mode,
      );

      await _waveController.preparePlayer(
        path: _localPath,
        shouldExtractWaveform: true,
      );

      if (mounted) {
        setState(() {
          _track = track;
          _isWaveLoaded = true;
        });
      }
    } catch (e) {
      debugPrint('prepare waveform failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final practiceState = ref.watch(practiceProvider);
    final audioPlayerService = ref.read(audioPlayerProvider);

    return Scaffold(
      appBar: AppBar(title: Text(_track?.filename ?? 'Practice Player')),
      body: Container(
        color: Colors.black,
        child: Column(
          children: [
            const SizedBox(height: 50),
            _isWaveLoaded
                ? Container(
                    height: 100,
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    child: AudioFileWaveforms(
                      size: Size(MediaQuery.of(context).size.width, 100.0),
                      playerController: _waveController,
                      enableSeekGesture: true,
                      playerWaveStyle: const PlayerWaveStyle(
                        fixedWaveColor: Colors.grey,
                        liveWaveColor: Colors.tealAccent,
                        spacing: 6.0,
                        waveThickness: 3.0,
                      ),
                    ),
                  )
                : const Center(child: CircularProgressIndicator(color: Colors.tealAccent)),
            const SizedBox(height: 20),
            StreamBuilder<int>(
              stream: _waveController.onCurrentDurationChanged,
              builder: (context, snapshot) {
                final current = Duration(milliseconds: snapshot.data ?? 0);
                return Column(
                  children: [
                    Text('Current time: ${current.inSeconds}s', style: const TextStyle(color: Colors.white70)),
                    const SizedBox(height: 10),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text('A: ${practiceState.pointA?.inSeconds ?? "--"}s', style: const TextStyle(color: Colors.orange)),
                        const SizedBox(width: 20),
                        Text('B: ${practiceState.pointB?.inSeconds ?? "--"}s', style: const TextStyle(color: Colors.green)),
                      ],
                    ),
                  ],
                );
              },
            ),
            const SizedBox(height: 20),
            IconButton(
              iconSize: 64,
              icon: Icon(_waveController.playerState.isPlaying ? Icons.pause_circle : Icons.play_circle),
              color: Colors.tealAccent,
              onPressed: () async {
                if (_waveController.playerState.isPlaying) {
                  await _waveController.pausePlayer();
                  await audioPlayerService.player.pause();
                } else {
                  await _waveController.startPlayer(finishMode: FinishMode.pause);
                  await audioPlayerService.player.play();
                }
                setState(() {});
              },
            ),
            const Divider(color: Colors.white24),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                children: [
                  const Text('Interactive Markers', style: TextStyle(color: Colors.white, fontSize: 18)),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 10,
                    children: [
                      ActionChip(
                        label: const Text('Set A'),
                        onPressed: () async {
                          final pos = Duration(milliseconds: await _waveController.getDuration(DurationType.current));
                          ref.read(practiceProvider.notifier).setPointA(pos);
                        },
                      ),
                      ActionChip(
                        label: const Text('Set B'),
                        onPressed: () async {
                          final pos = Duration(milliseconds: await _waveController.getDuration(DurationType.current));
                          ref.read(practiceProvider.notifier).setPointB(pos, widget.trackId);
                        },
                      ),
                      ActionChip(
                        label: const Text('Add Cue'),
                        onPressed: () async {
                          final pos = Duration(milliseconds: await _waveController.getDuration(DurationType.current));
                          _showCueRemarkDialog(context, pos, widget.trackId);
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  for (var cue in practiceState.cuePoints)
                    ListTile(
                      leading: const Icon(Icons.bookmark, color: Colors.purpleAccent),
                      title: Text(cue.remark, style: const TextStyle(color: Colors.white)),
                      subtitle: Text('${cue.position.inSeconds}s', style: const TextStyle(color: Colors.white54)),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showCueRemarkDialog(BuildContext context, Duration pos, int trackId) async {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Mark at ${pos.inSeconds}s'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(hintText: 'Remark'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          TextButton(
            onPressed: () {
              ref.read(practiceProvider.notifier).addCuePoint(pos, controller.text, trackId);
              Navigator.pop(context);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }
}
