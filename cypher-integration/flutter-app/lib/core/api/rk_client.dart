import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../utils/logger.dart';

class RkClient {
  late Dio _dio;
  WebSocketChannel? _wsChannel;
  String? _deviceToken;
  String? _currentUrl;
  bool _mockMode = false;
  Timer? _mockTimer;
  
  Map<String, dynamic>? _currentPlaybackState;
  Map<String, dynamic>? _currentDeviceInfo;
  double _currentSyncProgress = 0.0;

  final _playbackController = StreamController<Map<String, dynamic>>.broadcast();
  final _deviceController = StreamController<Map<String, dynamic>>.broadcast();
  final _syncController = StreamController<double>.broadcast();

  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;
  static const int _maxReconnectAttempts = 10;
  static const Duration _reconnectDelay = Duration(seconds: 1);

  Stream<Map<String, dynamic>> get playbackStream => _playbackController.stream;
  Stream<Map<String, dynamic>> get deviceStream => _deviceController.stream;
  Stream<double> get syncProgressStream => _syncController.stream;
  
  bool get isConnected => _currentUrl != null && (_mockMode || _wsChannel != null);
  String? get currentUrl => _currentUrl;

  RkClient({String? baseUrl}) {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl ?? 'http://localhost:9000',
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 15),
    ));
  }
  
  void setBaseUrl(String baseUrl) {
    _dio.options.baseUrl = baseUrl;
  }

  void setMockMode(bool enabled) {
    _mockMode = enabled;
    if (_mockMode) {
      _startMockUpdates();
    } else {
      _mockTimer?.cancel();
    }
  }

  void _startMockUpdates() {
    _mockTimer?.cancel();
    _currentDeviceInfo = null;
    _currentPlaybackState = null;
    _mockTimer = Timer.periodic(const Duration(milliseconds: 500), (_) {
      if (_currentDeviceInfo == null) {
        _currentDeviceInfo = {
          'type': 'device_info',
          'device_id': 'mock-device-001',
          'model': 'RK3588-MOCK',
          'status': 'connected',
          'battery': 100,
        };
        _deviceController.add(_currentDeviceInfo!);
      }
      
      if (_currentPlaybackState == null) {
        _currentPlaybackState = {
          'type': 'playback_state',
          'state': 'idle',
          'current_song_id': null,
          'current_position_sec': 0.0,
          'current_bpm': 120.0,
        };
        _playbackController.add(_currentPlaybackState!);
      }
    });
  }

  void setDeviceToken(String token) {
    _deviceToken = token;
    _dio.options.headers['Authorization'] = 'Bearer $token';
  }

  Future<bool> testConnection(String url) async {
    if (_mockMode) {
      return true;
    }
    try {
      final testDio = Dio();
      testDio.options.connectTimeout = const Duration(seconds: 3);
      testDio.options.receiveTimeout = const Duration(seconds: 3);
      final response = await testDio.get('$url/api/edge/info');
      return response.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  Future<String?> autoDetectBestUrl(List<String> urls) async {
    final futures = urls.map((url) => testConnection(url));
    final results = await Future.wait(futures.map((f) async {
      try {
        return await f;
      } catch (e) {
        return false;
      }
    }));

    for (int i = 0; i < results.length; i++) {
      if (results[i]) {
        return urls[i];
      }
    }
    return null;
  }

  Future<bool> connect(String url, {String? token}) async {
    if (_mockMode) {
      _currentUrl = url;
      _dio.options.baseUrl = url;
      if (token != null) {
        setDeviceToken(token);
      }
      AppLogger.info('Mock RK3588连接成功');
      _startMockUpdates();
      return true;
    }
    
    _currentUrl = url;
    _dio.options.baseUrl = url;
    if (token != null) {
      setDeviceToken(token);
    }

    try {
      await _dio.get('$url/api/edge/info');
      await _connectWebSocket(url, token ?? _deviceToken ?? '');
      return true;
    } catch (e) {
      AppLogger.error('RK3588连接失败: $e');
      return false;
    }
  }

  Future<void> _connectWebSocket(String url, String token) async {
    // WS is served on the same port as REST (:9000/ws/control)
    String wsUrl = url.replaceFirst('http://', 'ws://').replaceFirst('https://', 'wss://');
    wsUrl += '/ws/control${token.isNotEmpty ? '?token=$token' : ''}';

    AppLogger.info('RK WebSocket连接: $wsUrl');

    try {
      _wsChannel = WebSocketChannel.connect(Uri.parse(wsUrl));

      _wsChannel!.stream.listen(
        (message) {
          try {
            final data = jsonDecode(message);
            _handleWebSocketMessage(data);
          } catch (e) {
            AppLogger.error('WebSocket消息解析失败: $e');
          }
        },
        onError: (error) {
          AppLogger.error('WebSocket错误: $error');
          _scheduleReconnect();
        },
        onDone: () {
          AppLogger.info('WebSocket连接关闭');
          _scheduleReconnect();
        },
      );
    } catch (e) {
      AppLogger.error('WebSocket连接失败: $e');
      _scheduleReconnect();
    }
  }

  void _handleWebSocketMessage(Map<String, dynamic> data) {
    final type = data['type'];
    switch (type) {
      case 'playback_state':
        _playbackController.add(data);
        break;
      case 'device_info':
        _deviceController.add(data);
        break;
      case 'sync_progress':
        final progress = (data['progress'] as num?)?.toDouble() ?? 0.0;
        _syncController.add(progress);
        break;
      default:
        AppLogger.info('Unknown WS message type: $type');
    }
  }

  void _scheduleReconnect() {
    if (_reconnectAttempts >= _maxReconnectAttempts) {
      AppLogger.error('达到最大重连次数');
      return;
    }

    _reconnectTimer?.cancel();
    _reconnectAttempts++;

    AppLogger.info('${_reconnectDelay.inSeconds}秒后尝试重连 (第 $_reconnectAttempts 次)');

    _reconnectTimer = Timer(_reconnectDelay, () async {
      if (_currentUrl != null) {
        await connect(_currentUrl!);
      }
    });
  }

  Future<void> play(int songId, {double startAt = 0}) async {
    if (_mockMode) {
      _currentPlaybackState = {
        'type': 'playback_state',
        'state': 'playing',
        'current_song_id': songId,
        'current_position_sec': startAt,
        'current_bpm': 120.0,
      };
      _playbackController.add(_currentPlaybackState!);
      AppLogger.info('Mock播放: song_id=$songId, startAt=$startAt');
      return;
    }
    await _dio.post('/play', data: {
      'song_id': songId,
      'start_at_sec': startAt,
    });
  }

  Future<void> pause() async {
    if (_mockMode) {
      if (_currentPlaybackState != null) {
        _currentPlaybackState!['state'] = 'paused';
        _playbackController.add(_currentPlaybackState!);
      }
      AppLogger.info('Mock暂停');
      return;
    }
    await _dio.post('/pause', data: {});
  }

  Future<void> resume() async {
    if (_mockMode) {
      if (_currentPlaybackState != null) {
        _currentPlaybackState!['state'] = 'playing';
        _playbackController.add(_currentPlaybackState!);
      }
      AppLogger.info('Mock继续');
      return;
    }
    await _dio.post('/resume', data: {});
  }

  Future<void> next() async {
    if (_mockMode) {
      AppLogger.info('Mock下一首');
      return;
    }
    await _dio.post('/next', data: {});
  }

  Future<void> seek(double sec) async {
    if (_mockMode) {
      if (_currentPlaybackState != null) {
        _currentPlaybackState!['current_position_sec'] = sec;
        _playbackController.add(_currentPlaybackState!);
      }
      AppLogger.info('Mock跳转: $sec秒');
      return;
    }
    await _dio.post('/seek', data: {'sec': sec});
  }

  /// 返回 RK /trigger 的响应体（含 action / key / ok），失败抛错。
  Future<Map<String, dynamic>> trigger(int key) async {
    if (_mockMode) {
      AppLogger.info('Mock触发按键: key=$key');
      return {'ok': true, 'key': key, 'action': 'mock'};
    }
    final resp = await _dio.post('/trigger', data: {'key': key});
    if (resp.data is Map<String, dynamic>) {
      return resp.data as Map<String, dynamic>;
    }
    return {'ok': true, 'key': key};
  }

  Future<void> setEnergy(String level) async {
    if (_mockMode) {
      AppLogger.info('Mock设置能量等级: $level');
      return;
    }
    await _dio.post('/energy', data: {'level': level});
  }

  Future<void> setStyle(String style) async {
    if (_mockMode) {
      AppLogger.info('Mock设置风格: $style');
      return;
    }
    await _dio.post('/style', data: {'style': style});
  }

  Future<void> setMix(String transition) async {
    if (_mockMode) {
      AppLogger.info('Mock设置混音: $transition');
      return;
    }
    await _dio.post('/mix', data: {'transition': transition});
  }

  Future<void> setLoop(bool enabled) async {
    if (_mockMode) {
      AppLogger.info('Mock设置循环: $enabled');
      return;
    }
    await _dio.post('/loop', data: {'enabled': enabled});
  }

  Future<void> loadPlan(Map<String, dynamic> mixPlan, Map<String, dynamic> manifest) async {
    if (_mockMode) {
      _currentSyncProgress = 0.0;
      _syncController.add(0.0);
      Timer.periodic(const Duration(milliseconds: 100), (timer) {
        _currentSyncProgress += 0.05;
        if (_currentSyncProgress >= 1.0) {
          _currentSyncProgress = 1.0;
          timer.cancel();
        }
        _syncController.add(_currentSyncProgress);
      });
      AppLogger.info('Mock加载计划');
      return;
    }
    await _dio.post('/load_plan', data: {
      'mix_plan': mixPlan,
      'manifest': manifest,
    });
  }

  Stream<Map<String, dynamic>> watchPlayback() {
    return playbackStream;
  }

  Stream<Map<String, dynamic>> watchDevice() {
    return deviceStream;
  }

  Stream<double> watchSyncProgress() {
    return syncProgressStream;
  }

  void dispose() {
    _reconnectTimer?.cancel();
    _wsChannel?.sink.close();
    _playbackController.close();
    _deviceController.close();
    _syncController.close();
  }
}
