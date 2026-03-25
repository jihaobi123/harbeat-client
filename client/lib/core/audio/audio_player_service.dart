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

  // --- 将以下代码加到你的 AudioPlayerService 类中 ---

  double? _masterBpm; // 记录当前作为基准的 BPM

  // 1. 开启 Sync 模式：设置当前歌曲为基准 BPM
  void setMasterBpm(double currentBpm) {
    _masterBpm = currentBpm;
    print("🎛️ Sync开启：已锁定全局 BPM 为 $_masterBpm");
  }

  // 2. 播放下一首歌（带自动 BPM 适配）
  Future<void> playNextWithSync(String url, double nextSongBpm) async {
    await _player.setUrl(url);
    
    // 如果开启了 Sync 并且有基准 BPM，就计算拉伸比例
    if (_masterBpm != null && nextSongBpm > 0) {
      double speedRatio = _masterBpm! / nextSongBpm;
      
      // 为了防止极端的变速导致声音严重失真，通常限制在 0.5 到 2.0 倍之间
      speedRatio = speedRatio.clamp(0.5, 2.0); 
      
      await _player.setSpeed(speedRatio);
      print("🎛️ 自动拉伸：原BPM $nextSongBpm -> 目标BPM $_masterBpm (变速比: $speedRatio)");
    } else {
      // 没开启 Sync，就按原速 1.0 播放
      await _player.setSpeed(1.0);
    }
    
    await _player.play();
  }
  
  // 3. 关闭 Sync 模式
  void disableSync() {
    _masterBpm = null;
    _player.setSpeed(1.0); // 恢复原速
  }
}