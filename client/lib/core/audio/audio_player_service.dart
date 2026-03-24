import 'package:just_audio/just_audio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

// 提供一个全局单例的 AudioPlayerService
final audioPlayerProvider = Provider<AudioPlayerService>((ref) {
  return AudioPlayerService();
});

class AudioPlayerService {
  final AudioPlayer _player = AudioPlayer();
  
  Duration? _pointA;
  Duration? _pointB;

  AudioPlayerService() {
    // 核心逻辑：监听播放进度，实现 A-B 无缝循环
    _player.positionStream.listen((position) {
      if (_pointA != null && _pointB != null) {
        // 如果当前时间超过了 B 点，瞬间跳回 A 点
        if (position >= _pointB!) {
          _player.seek(_pointA!);
        }
      }
    });
  }

  AudioPlayer get player => _player;

  // 设置 A 点
  void setPointA(Duration position) {
    _pointA = position;
  }

  // 设置 B 点
  void setPointB(Duration position) {
    _pointB = position;
  }

  // 清除循环
  void clearLoop() {
    _pointA = null;
    _pointB = null;
  }

  Future<void> loadAudio(String url) async {
    await _player.setUrl(url);
  }
}