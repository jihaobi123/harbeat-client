import 'dart:io' as io;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:audio_waveforms/audio_waveforms.dart';
import 'package:dio/dio.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../core/audio/audio_player_service.dart';
import '../providers/practice_session_provider.dart';

class PracticePlayerScreen extends ConsumerStatefulWidget {
  final int trackId = 1;
  final String networkUrl = 'http://10.0.2.2:8000/uploads/raw/test.mp3';

  const PracticePlayerScreen({super.key});

  @override
  ConsumerState<PracticePlayerScreen> createState() => _PracticePlayerScreenState();
}

class _PracticePlayerScreenState extends ConsumerState<PracticePlayerScreen> {
  late final PlayerController _waveController;
  bool _isWaveLoaded = false;
  String _localPath = "";

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
      final appDocDir = await getApplicationDocumentsDirectory();
      _localPath = p.join(appDocDir.path, "temp_test.mp3");

      if (!await io.File(_localPath).exists()) {
        await Dio().download(widget.networkUrl, _localPath);
      }

      await ref.read(audioPlayerProvider).loadAudio(widget.networkUrl);

      // 准备波形播放器
      await _waveController.preparePlayer(
        path: _localPath,
        shouldExtractWaveform: true,
      );
      
      if (mounted) setState(() => _isWaveLoaded = true);
    } catch (e) {
      debugPrint("准备波形失败: $e");
    }
  }

  @override
  Widget build(BuildContext context) {
    final practiceState = ref.watch(practiceProvider);
    final audioPlayerService = ref.read(audioPlayerProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('DJ 练习室 P2')),
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

            // 显示当前播放进度
            StreamBuilder<int>(
              stream: _waveController.onCurrentDurationChanged,
              builder: (context, snapshot) {
                final current = Duration(milliseconds: snapshot.data ?? 0);
                return Column(
                  children: [
                    Text('当前时间: ${current.inSeconds}秒', style: const TextStyle(color: Colors.white70)),
                    const SizedBox(height: 10),
                    // 显示 A/B 点状态
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

            // 播放控制
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
                  const Text("交互选点", style: TextStyle(color: Colors.white, fontSize: 18)),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 10,
                    children: [
                      ActionChip(
                        label: const Text('设为 A 点'),
                        onPressed: () async {
                          final pos = Duration(milliseconds: await _waveController.getDuration(DurationType.current));
                          ref.read(practiceProvider.notifier).setPointA(pos);
                        },
                      ),
                      ActionChip(
                        label: const Text('设为 B 点'),
                        onPressed: () async {
                          final pos = Duration(milliseconds: await _waveController.getDuration(DurationType.current));
                          ref.read(practiceProvider.notifier).setPointB(pos, widget.trackId);
                        },
                      ),
                      ActionChip(
                        label: const Text('打 Cue 点'),
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
                      subtitle: Text('${cue.position.inSeconds}秒', style: const TextStyle(color: Colors.white54)),
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
        title: Text('标记在 ${pos.inSeconds}s'),
        content: TextField(controller: controller, decoration: const InputDecoration(hintText: '备注内容')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')),
          TextButton(
            onPressed: () {
              ref.read(practiceProvider.notifier).addCuePoint(pos, controller.text, trackId);
              Navigator.pop(context);
            },
            child: const Text('保存'),
          ),
        ],
      ),
    );
  }
}