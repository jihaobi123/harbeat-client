import 'dart:async';
import 'package:just_audio/just_audio.dart';
import '../utils/logger.dart';

/// 简单的音频播放服务
class AudioPlayerService {
  static final AudioPlayerService _instance = AudioPlayerService._internal();
  factory AudioPlayerService() => _instance;
  AudioPlayerService._internal();
  
  late AudioPlayer _player;
  
  // 播放状态流
  final _playingController = StreamController<bool>.broadcast();
  Stream<bool> get playingStream => _playingController.stream;
  
  final _positionController = StreamController<Duration>.broadcast();
  Stream<Duration> get positionStream => _positionController.stream;
  
  final _durationController = StreamController<Duration>.broadcast();
  Stream<Duration> get durationStream => _durationController.stream;
  
  bool get isPlaying => _player.playing;
  Duration get position => _player.position;
  Duration get duration => _player.duration ?? Duration.zero;
  
  Future<void> init() async {
    _player = AudioPlayer();
    
    // 监听播放状态变化
    _player.playerStateStream.listen((state) {
      _playingController.add(state.playing);
    });
    
    // 监听位置变化
    _player.positionStream.listen((pos) {
      _positionController.add(pos);
    });
    
    // 监听时长变化
    _player.durationStream.listen((dur) {
      if (dur != null) {
        _durationController.add(dur);
      }
    });
    
    AppLogger.info('AudioPlayer initialized');
  }
  
  /// 暂停
  Future<void> pause() async {
    await _player.pause();
  }
  
  /// 恢复播放
  Future<void> resume() async {
    await _player.play();
  }
  
  /// 停止
  Future<void> stop() async {
    await _player.stop();
  }
  
  /// 跳转到指定位置
  Future<void> seek(Duration position) async {
    await _player.seek(position);
  }
  
  /// 释放资源
  Future<void> dispose() async {
    await _player.dispose();
    await _playingController.close();
    await _positionController.close();
    await _durationController.close();
  }
}
