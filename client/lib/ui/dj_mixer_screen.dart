import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:io' as io;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../core/network/api_repository.dart';

class DjMixerScreen extends ConsumerStatefulWidget {
  const DjMixerScreen({super.key});

  @override
  ConsumerState<DjMixerScreen> createState() => _DjMixerScreenState();
}

class _DjMixerScreenState extends ConsumerState<DjMixerScreen> {
  final AudioPlayer _playerA = AudioPlayer();
  final AudioPlayer _playerB = AudioPlayer();

  double? _bpmA; 
  double? _bpmB; 

  double _crossfadeValue = 0.0;
  bool _isReady = false;
  
  bool _isAnalyzingBpm = false;

  @override
  void initState() {
    super.initState();
    _initDecks();
  }

  @override
  void dispose() {
    _playerA.dispose();
    _playerB.dispose();
    super.dispose();
  }

  Future<void> _initDecks() async {
    try {
      final appDocDir = await getApplicationDocumentsDirectory();
      
      String pathA = p.join(appDocDir.path, "test.mp3");
      if (!await io.File(pathA).exists()) {
        final byteData = await rootBundle.load('assets/test.mp3');
        await io.File(pathA).writeAsBytes(byteData.buffer.asUint8List());
      }
      await _playerA.setFilePath(pathA);
      await _playerA.setVolume(1.0);

      String pathB = p.join(appDocDir.path, "song2.mp3");
      if (!await io.File(pathB).exists()) {
        final byteData = await rootBundle.load('assets/song2.mp3');
        await io.File(pathB).writeAsBytes(byteData.buffer.asUint8List());
      }
      await _playerB.setFilePath(pathB);
      await _playerB.setVolume(0.0);

      if (mounted) setState(() => _isReady = true);
    } catch (e) {
      debugPrint("加载失败: $e");
    }
  }

  Future<void> _analyzeBpm() async {
    if (_isAnalyzingBpm) return;
    
    setState(() => _isAnalyzingBpm = true);
    
    try {
      final appDocDir = await getApplicationDocumentsDirectory();
      String pathA = p.join(appDocDir.path, "test.mp3");
      String pathB = p.join(appDocDir.path, "song2.mp3");

      final apiRepo = ref.read(apiRepoProvider);
      
      final resultA = await apiRepo.uploadAndAnalyzeBpm(pathA);
      final resultB = await apiRepo.uploadAndAnalyzeBpm(pathB);

      if (mounted) {
        setState(() {
          _bpmA = (resultA['bpm'] as num).toDouble();
          _bpmB = (resultB['bpm'] as num).toDouble();
          _isAnalyzingBpm = false;
        });
        
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("✅ 测算完成！"), backgroundColor: Colors.green),
        );
      }
    } catch (e) {
      debugPrint("测算失败: $e");
      if (mounted) {
        setState(() => _isAnalyzingBpm = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("测算失败: $e"), backgroundColor: Colors.red),
        );
      }
    }
  }

  void _onCrossfadeChanged(double value) {
    setState(() {
      _crossfadeValue = value;
      _playerA.setVolume(1.0 - value);
      _playerB.setVolume(value);
    });
  }

  void _syncBtoA() {
    if (_bpmA == null || _bpmB == null || _bpmB == 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("⚠️ 请先点击上方的「测算双轨 BPM」！"), backgroundColor: Colors.redAccent),
      );
      return;
    }
    
    double speedRatio = _bpmA! / _bpmB!;
    speedRatio = speedRatio.clamp(0.5, 2.0);
    
    _playerB.setSpeed(speedRatio);
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text("BPM 已精准对齐！B 轨变速为 ${(speedRatio).toStringAsFixed(2)}x"), backgroundColor: Colors.purple),
    );
  }

  Widget _buildDeck(String name, AudioPlayer player, double? currentBpm, Color themeColor) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white10,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: themeColor.withOpacity(0.5)),
      ),
      child: Column(
        children: [
          Text("DECK $name", style: TextStyle(color: themeColor, fontSize: 20, fontWeight: FontWeight.bold)),
          Text("真实 BPM: ${currentBpm != null ? currentBpm.toStringAsFixed(1) : '--'}", 
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          StreamBuilder<PlayerState>(
            stream: player.playerStateStream,
            builder: (context, snapshot) {
              final playing = snapshot.data?.playing ?? false;
              return IconButton(
                iconSize: 64,
                icon: Icon(playing ? Icons.pause_circle : Icons.play_circle, color: themeColor),
                onPressed: () => playing ? player.pause() : player.play(),
              );
            },
          ),
          StreamBuilder<Duration>(
            stream: player.positionStream,
            builder: (context, snapshot) {
              final pos = snapshot.data?.inSeconds ?? 0;
              final total = player.duration?.inSeconds ?? 1;
              return LinearProgressIndicator(
                value: pos / total,
                color: themeColor,
                backgroundColor: Colors.white12,
              );
            },
          )
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_isReady) {
      return const Scaffold(backgroundColor: Colors.black, body: Center(child: CircularProgressIndicator(color: Colors.tealAccent)));
    }

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(title: const Text("DJ 混音台 (Dual Deck)")),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(child: _buildDeck("A", _playerA, _bpmA, Colors.tealAccent)),
                const SizedBox(width: 16),
                Expanded(child: _buildDeck("B", _playerB, _bpmB, Colors.orangeAccent)),
              ],
            ),
            
            const Spacer(),

            ElevatedButton.icon(
              icon: _isAnalyzingBpm 
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2)) 
                  : const Icon(Icons.analytics),
              label: Text(_isAnalyzingBpm ? "AI 正在疯狂死磕中..." : "测算双轨 BPM"),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.blueAccent, foregroundColor: Colors.white),
              onPressed: _isAnalyzingBpm ? null : _analyzeBpm,
            ),
            
            const SizedBox(height: 10),

            ElevatedButton.icon(
              icon: const Icon(Icons.sync),
              label: const Text("强制对轨 (Sync B to A)"),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.purple, foregroundColor: Colors.white),
              onPressed: _syncBtoA,
            ),
            
            const SizedBox(height: 30),

            const Text("混音推子 (Crossfader)", style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text("纯 A", style: TextStyle(color: Colors.tealAccent)),
                Expanded(
                  child: Slider(
                    value: _crossfadeValue,
                    min: 0.0, max: 1.0,
                    activeColor: Colors.white,
                    inactiveColor: Colors.white24,
                    thumbColor: Colors.purpleAccent,
                    onChanged: _onCrossfadeChanged,
                  ),
                ),
                const Text("纯 B", style: TextStyle(color: Colors.orangeAccent)),
              ],
            ),
            const Spacer(),
          ],
        ),
      ),
    );
  }
}