import 'dart:io' as io;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:just_audio/just_audio.dart'; // 新增：用于独立的音轨试听播放器
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../core/audio/audio_player_service.dart';
import '../providers/practice_session_provider.dart';
import '../core/network/api_repository.dart';

class PracticePlayerScreen extends ConsumerStatefulWidget {
  const PracticePlayerScreen({super.key});

  @override
  ConsumerState<PracticePlayerScreen> createState() => _PracticePlayerScreenState();
}

class _PracticePlayerScreenState extends ConsumerState<PracticePlayerScreen> {
  bool _isAudioReady = false;
  String _localPath = "";
  String? _audioPrepareError;
  static const String _assetAudioPath = 'assets/test.mp3';
  
  // A-B 循环开关状态
  bool _isABLooping = false;
  
  // 后端分配的真实 trackId
  int? _backendTrackId;

  @override
  void initState() {
    super.initState();
    _prepareAudio();
  }

  Future<void> _prepareAudio() async {
    if (mounted) {
      setState(() {
        _isAudioReady = false;
        _audioPrepareError = null;
      });
    }
    try {
      final appDocDir = await getApplicationDocumentsDirectory();
      _localPath = p.join(appDocDir.path, "test.mp3");

      final file = io.File(_localPath);
      // 核心：从打包到 App 的 assets 里拷贝一份到真实文件系统（方便上传给后端 + just_audio 播放）
      if (!await file.exists()) {
        final byteData = await rootBundle.load(_assetAudioPath);
        await file.writeAsBytes(
          byteData.buffer.asUint8List(byteData.offsetInBytes, byteData.lengthInBytes),
        );
      }

      // 1. 先声明并拿到播放器服务
      final audioPlayerService = ref.read(audioPlayerProvider);
      
      // 2. 播放本地文件
      await audioPlayerService.player.setFilePath(_localPath);
      
      if (mounted) {
        setState(() => _isAudioReady = true);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _audioPrepareError =
              "${e.toString()}\n\n请确认你已把音频放到：client/assets/test.mp3，并在 pubspec.yaml 里注册了 assets（本项目已注册 assets/ 目录）。";
          _isAudioReady = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("加载失败: $e")));
      }
      debugPrint("准备音频失败: $e");
    }
  }

  // 格式化时间辅助函数 (如 01:23)
  String _formatDuration(Duration d) {
    final minutes = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return "$minutes:$seconds";
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
            const SizedBox(height: 40),
            
            // 封面或黑胶唱片占位图
            Container(
              width: 200,
              height: 200,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const RadialGradient(colors: [Colors.grey, Colors.black]),
                border: Border.all(color: Colors.tealAccent.withOpacity(0.5), width: 2),
              ),
              child: const Icon(Icons.music_note, size: 80, color: Colors.white24),
            ),
            
            const SizedBox(height: 30),

            // 进度条与时间显示
            if (!_isAudioReady)
              Padding(
                padding: const EdgeInsets.all(20.0),
                child: Column(
                  children: [
                    const CircularProgressIndicator(color: Colors.tealAccent),
                    if (_audioPrepareError != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        "音频加载失败：$_audioPrepareError",
                        style: const TextStyle(color: Colors.redAccent, fontSize: 12),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),
                      TextButton(
                        onPressed: _prepareAudio,
                        child: const Text("重试加载"),
                      ),
                    ]
                  ],
                ),
              )
            else
              StreamBuilder<Duration?>(
                stream: audioPlayerService.player.durationStream,
                builder: (context, durationSnapshot) {
                  final duration = durationSnapshot.data ?? Duration.zero;
                  
                  return StreamBuilder<Duration>(
                    stream: audioPlayerService.player.positionStream,
                    builder: (context, positionSnapshot) {
                      var position = positionSnapshot.data ?? Duration.zero;
                      if (position > duration) position = duration;

                      return Column(
                        children: [
                          SliderTheme(
                            data: SliderTheme.of(context).copyWith(
                              trackHeight: 4.0,
                              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 8.0),
                            ),
                            child: Slider(
                              min: 0.0,
                              max: duration.inMilliseconds > 0 ? duration.inMilliseconds.toDouble() : 1.0,
                              value: position.inMilliseconds.toDouble(),
                              activeColor: Colors.tealAccent,
                              inactiveColor: Colors.white24,
                              onChanged: (value) {
                                // 拖拽进度条时，直接让音频跳转
                                audioPlayerService.player.seek(Duration(milliseconds: value.toInt()));
                              },
                            ),
                          ),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 24.0),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(_formatDuration(position), style: const TextStyle(color: Colors.white70)),
                                Text(_formatDuration(duration), style: const TextStyle(color: Colors.white70)),
                              ],
                            ),
                          ),
                        ],
                      );
                    },
                  );
                },
              ),

            const SizedBox(height: 10),

            // 播放控制器 (上一首、播放/暂停、下一首)
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                IconButton(
                  iconSize: 40,
                  icon: const Icon(Icons.skip_previous),
                  color: Colors.white,
                  onPressed: () {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("上一首功能开发中...")));
                  },
                ),
                const SizedBox(width: 20),
                IconButton(
                  iconSize: 72,
                  icon: Icon(audioPlayerService.player.playing ? Icons.pause_circle_filled : Icons.play_circle_fill),
                  color: Colors.tealAccent,
                  onPressed: () async {
                    if (audioPlayerService.player.playing) {
                      await audioPlayerService.player.pause();
                    } else {
                      await audioPlayerService.player.play();
                    }
                    setState(() {});
                  },
                ),
                const SizedBox(width: 20),
                IconButton(
                  iconSize: 40,
                  icon: const Icon(Icons.skip_next),
                  color: Colors.white,
                  onPressed: () {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("下一首功能开发中...")));
                  },
                ),
              ],
            ),

            const SizedBox(height: 10),
            
            // A-B 点状态显示与循环开关
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                Row(
                  children: [
                    Text('A: ${practiceState.pointA != null ? _formatDuration(practiceState.pointA!) : "--:--"}', 
                        style: const TextStyle(color: Colors.orange, fontWeight: FontWeight.bold)),
                    const SizedBox(width: 16),
                    Text('B: ${practiceState.pointB != null ? _formatDuration(practiceState.pointB!) : "--:--"}', 
                        style: const TextStyle(color: Colors.green, fontWeight: FontWeight.bold)),
                  ],
                ),
                Row(
                  children: [
                    const Text('循环 A-B', style: TextStyle(color: Colors.white70)),
                    Switch(
                      value: _isABLooping,
                      activeColor: Colors.tealAccent,
                      onChanged: (val) {
                        setState(() {
                          _isABLooping = val;
                          if (!val) {
                            audioPlayerService.clearLoop();
                          } else {
                            if (practiceState.pointA != null && practiceState.pointB != null) {
                              audioPlayerService.setPointA(practiceState.pointA!);
                              audioPlayerService.setPointB(practiceState.pointB!);
                            }
                          }
                        });
                      },
                    ),
                  ],
                ),
              ],
            ),

            const Divider(color: Colors.white24, height: 30),
            
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                children: [
                  const Text("交互选点与 AI 处理", style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 15),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      ActionChip(
                        label: const Text('设为 A 点'),
                        onPressed: () async {
                          final pos = audioPlayerService.player.position;
                          ref.read(practiceProvider.notifier).setPointA(pos);
                          if (_isABLooping) audioPlayerService.setPointA(pos);
                        },
                      ),
                      ActionChip(
                        label: const Text('设为 B 点'),
                        onPressed: () async {
                          final pos = audioPlayerService.player.position;
                          ref.read(practiceProvider.notifier).setPointB(pos, _backendTrackId ?? 999);
                          if (_isABLooping) audioPlayerService.setPointB(pos);
                        },
                      ),
                      ActionChip(
                        label: const Text('打 Cue 点'),
                        onPressed: () async {
                          final pos = audioPlayerService.player.position;
                          _showCueRemarkDialog(context, pos, _backendTrackId ?? 999);
                        },
                      ),
                      ActionChip(
                        label: const Text('BPM/Key 测算', style: TextStyle(color: Colors.deepPurple, fontWeight: FontWeight.bold)),
                        backgroundColor: Colors.purple.shade100,
                        onPressed: () => _handleBpmAnalysis(context),
                      ),
                      ActionChip(
                        label: const Text('AI 音轨分离', style: TextStyle(color: Colors.blueAccent, fontWeight: FontWeight.bold)),
                        backgroundColor: _backendTrackId == null ? Colors.grey.shade300 : Colors.blue.shade100,
                        onPressed: _backendTrackId == null ? null : () => _handleStemSplit(context),
                      ),
                    ],
                  ),
                  
                  if (_backendTrackId != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 15),
                      child: Text('✅ 已绑定后端 TrackID: $_backendTrackId', style: const TextStyle(color: Colors.greenAccent, fontSize: 12)),
                    ),
                  
                  const SizedBox(height: 20),
                  for (var cue in practiceState.cuePoints)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.bookmark, color: Colors.purpleAccent),
                      title: Text(cue.remark, style: const TextStyle(color: Colors.white)),
                      subtitle: Text(_formatDuration(cue.position), style: const TextStyle(color: Colors.white54)),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _handleBpmAnalysis(BuildContext context) async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (c) => const Center(child: CircularProgressIndicator(color: Colors.tealAccent)),
    );
    
    final result = await ref.read(apiRepoProvider).uploadAndAnalyzeBpm(_localPath);
    
    if (mounted) {
      Navigator.pop(context); 
      setState(() => _backendTrackId = result['track_id']);

      showDialog(
        context: context,
        builder: (c) => AlertDialog(
          title: const Text('🎵 测算结果'),
          content: Text("BPM: ${result['bpm']}\nKey: ${result['key']}\n\n数据已入库，TrackID: $_backendTrackId。"),
          actions: [TextButton(onPressed: () => Navigator.pop(c), child: const Text('太棒了'))],
        ),
      );
    }
  }

  // 🚀 核心修改：弹出底部控制面板
  Future<void> _handleStemSplit(BuildContext context) async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (c) => const Center(
        child: Card(
          child: Padding(
            padding: EdgeInsets.all(20.0),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(color: Colors.blueAccent),
                SizedBox(height: 15),
                Text("AI 正在死磕音轨...", style: TextStyle(fontWeight: FontWeight.bold)),
                Text("请稍候", style: TextStyle(fontSize: 12, color: Colors.grey)),
              ],
            ),
          ),
        ),
      ),
    );
    
    final result = await ref.read(apiRepoProvider).splitStemsByTrackId(_backendTrackId!);
    
    if (mounted) {
      Navigator.pop(context); // 关掉 loading
      
      // 暂停主播放器，避免声音打架
      final audioPlayerService = ref.read(audioPlayerProvider);
      if (audioPlayerService.player.playing) {
        await audioPlayerService.player.pause();
        setState(() {}); 
      }

      // 弹出高级的底部音轨控制面板
      showModalBottomSheet(
        context: context,
        backgroundColor: Colors.grey[900],
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        builder: (context) => StemPlayerSheet(urls: result),
      );
    }
  }

  Future<void> _showCueRemarkDialog(BuildContext context, Duration pos, int trackId) async {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('标记在 ${_formatDuration(pos)}'),
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

// ==========================================
// 👇 新增：独立的音轨播放面板组件 (BottomSheet)
// ==========================================
class StemPlayerSheet extends StatefulWidget {
  final Map<String, dynamic> urls;
  const StemPlayerSheet({super.key, required this.urls});

  @override
  State<StemPlayerSheet> createState() => _StemPlayerSheetState();
}

class _StemPlayerSheetState extends State<StemPlayerSheet> {
  final AudioPlayer _stemPlayer = AudioPlayer();
  String? _playingTrack; // 记录当前正在播哪一轨
  bool _isLoading = false;

  @override
  void dispose() {
    _stemPlayer.dispose(); // 面板关闭时，自动销毁独立播放器，释放资源
    super.dispose();
  }

  Future<void> _playOrPause(String trackName, String url) async {
    try {
      if (_playingTrack == trackName && _stemPlayer.playing) {
        // 如果点的就是当前在播的，就暂停
        await _stemPlayer.pause();
        setState(() {});
      } else {
        // 否则，切歌并播放
        setState(() {
          _playingTrack = trackName;
          _isLoading = true;
        });
        
        await _stemPlayer.setUrl(url);
        await _stemPlayer.play();
        
        if (mounted) {
          setState(() => _isLoading = false);
        }
      }
    } catch (e) {
      if (mounted) setState(() => _isLoading = false);
      debugPrint("音轨播放失败: $e");
    }
    
    // 监听播放结束，自动重置状态
    _stemPlayer.playerStateStream.listen((state) {
      if (state.processingState == ProcessingState.completed) {
        if (mounted) setState(() => _playingTrack = null);
      }
    });
  }

  Widget _buildTrackButton(String title, String trackKey, IconData icon, Color color) {
    final url = widget.urls[trackKey] as String?;
    final isThisPlaying = _playingTrack == trackKey && _stemPlayer.playing;
    final isThisLoading = _playingTrack == trackKey && _isLoading;

    return ListTile(
      leading: Icon(icon, color: color),
      title: Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
      trailing: IconButton(
        icon: isThisLoading 
            ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))
            : Icon(isThisPlaying ? Icons.pause_circle : Icons.play_circle, color: color, size: 36),
        onPressed: url == null ? null : () => _playOrPause(trackKey, url),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 10),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 顶部小横条提示
          Container(
            width: 40,
            height: 5,
            decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(10)),
          ),
          const SizedBox(height: 20),
          const Text("🎛️ 独立音轨试听", style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          
          _buildTrackButton("人声 (Vocals)", "vocals", Icons.mic, Colors.pinkAccent),
          _buildTrackButton("鼓点 (Drums)", "drums", Icons.album, Colors.amber),
          _buildTrackButton("贝斯 (Bass)", "bass", Icons.waves, Colors.blueAccent),
          _buildTrackButton("其他 (Other)", "other", Icons.piano, Colors.purpleAccent),
          
          const SizedBox(height: 10),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text("关闭面板", style: TextStyle(color: Colors.white54)),
          )
        ],
      ),
    );
  }
}