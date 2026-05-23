import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:dio/dio.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../network/api_client.dart';
import '../utils/logger.dart';

class RK3588DeviceInfo {
  final String deviceId;
  final String name;
  final String localUrl;
  final String? tailscaleUrl;
  final String? gatewayUrl;
  final String? pairCode;
  final int? expiresInSec;
  final bool isConnected;
  final String? deviceToken;
  final int lastConnectedTime;

  RK3588DeviceInfo({
    required this.deviceId,
    required this.name,
    required this.localUrl,
    this.tailscaleUrl,
    this.gatewayUrl,
    this.pairCode,
    this.expiresInSec,
    this.isConnected = false,
    this.deviceToken,
    this.lastConnectedTime = 0,
  });

  factory RK3588DeviceInfo.fromJson(Map<String, dynamic> json) {
    return RK3588DeviceInfo(
      deviceId: json['device_id'] ?? '',
      name: json['name'] ?? 'RK3588',
      localUrl: json['local_url'] ?? '',
      tailscaleUrl: json['tailscale_url'],
      gatewayUrl: json['gateway_url'],
      pairCode: json['pair_code'],
      expiresInSec: json['expires_in_sec'],
      isConnected: json['is_connected'] ?? false,
      deviceToken: json['device_token'],
      lastConnectedTime: json['last_connected_time'] ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'device_id': deviceId,
      'name': name,
      'local_url': localUrl,
      'tailscale_url': tailscaleUrl,
      'gateway_url': gatewayUrl,
      'pair_code': pairCode,
      'expires_in_sec': expiresInSec,
      'is_connected': isConnected,
      'device_token': deviceToken,
      'last_connected_time': lastConnectedTime,
    };
  }

  RK3588DeviceInfo copyWith({
    String? deviceId,
    String? name,
    String? localUrl,
    String? tailscaleUrl,
    String? gatewayUrl,
    String? pairCode,
    int? expiresInSec,
    bool? isConnected,
    String? deviceToken,
    int? lastConnectedTime,
  }) {
    return RK3588DeviceInfo(
      deviceId: deviceId ?? this.deviceId,
      name: name ?? this.name,
      localUrl: localUrl ?? this.localUrl,
      tailscaleUrl: tailscaleUrl ?? this.tailscaleUrl,
      gatewayUrl: gatewayUrl ?? this.gatewayUrl,
      pairCode: pairCode ?? this.pairCode,
      expiresInSec: expiresInSec ?? this.expiresInSec,
      isConnected: isConnected ?? this.isConnected,
      deviceToken: deviceToken ?? this.deviceToken,
      lastConnectedTime: lastConnectedTime ?? this.lastConnectedTime,
    );
  }
}

class EdgeStatus {
  final String currentTrack;
  final String currentStyle;
  final String deck;
  final bool micActive;
  final bool speakerActive;
  final bool keyboardActive;
  final String networkStatus;
  final int volume;
  final bool isPlaying;

  EdgeStatus({
    required this.currentTrack,
    required this.currentStyle,
    required this.deck,
    required this.micActive,
    required this.speakerActive,
    required this.keyboardActive,
    required this.networkStatus,
    required this.volume,
    required this.isPlaying,
  });

  factory EdgeStatus.fromJson(Map<String, dynamic> json) {
    return EdgeStatus(
      currentTrack: json['current_track'] ?? '未知',
      currentStyle: json['current_style'] ?? 'unknown',
      deck: json['deck'] ?? 'A',
      micActive: json['mic_active'] ?? false,
      speakerActive: json['speaker_active'] ?? false,
      keyboardActive: json['keyboard_active'] ?? false,
      networkStatus: json['network_status'] ?? 'unknown',
      volume: json['volume'] ?? 75,
      isPlaying: json['is_playing'] ?? false,
    );
  }
}

enum EnergyMode { low, medium, high }

enum MusicStyle { hiphop, breaking, popping, locking, house, all }

enum CutMode { smooth, hard, echo_out, clean_blend }

enum ConnectionPriority { local, tailscale, gateway, cloud }

enum ConnectionStatus { disconnected, connecting, connected, error }

class HardwareService {
  static final HardwareService _instance = HardwareService._internal();
  factory HardwareService() => _instance;
  HardwareService._internal();

  final _dio = Dio();
  
  RK3588DeviceInfo? _currentDevice;
  EdgeStatus? _currentStatus;
  EnergyMode _currentEnergyMode = EnergyMode.medium;
  MusicStyle _currentStyle = MusicStyle.hiphop;
  bool _isConnected = false;
  int _volume = 75;
  bool _isPlaying = false;
  ConnectionStatus _connectionStatus = ConnectionStatus.disconnected;
  
  WebSocketChannel? _webSocketChannel;
  Function(Map<String, dynamic>)? _onMessageReceived;
  
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;
  static const int _maxReconnectAttempts = 5;
  
  final List<RK3588DeviceInfo> _connectionHistory = [];
  String? _deviceToken;
  String? _lastUsedUrl;

  RK3588DeviceInfo? get currentDevice => _currentDevice;
  EdgeStatus? get currentStatus => _currentStatus;
  bool get isDeviceConnected => _isConnected;
  String? get lastUsedUrl => _lastUsedUrl;
  int get currentVolume => _volume;
  EnergyMode get currentEnergyMode => _currentEnergyMode;
  MusicStyle get currentStyle => _currentStyle;
  bool get isPlaying => _isPlaying;
  ConnectionStatus get connectionStatus => _connectionStatus;
  List<RK3588DeviceInfo> get connectionHistory => List.unmodifiable(_connectionHistory);

  void _updateConnectionStatus(bool connected) {
    _isConnected = connected;
    _connectionStatus = connected ? ConnectionStatus.connected : ConnectionStatus.disconnected;
    AppLogger.info('RK3588 连接状态: ${connected ? "已连接" : "未连接"}');
  }

  void setMessageHandler(Function(Map<String, dynamic>) handler) {
    _onMessageReceived = handler;
  }

  Future<bool> checkHealth() async {
    return _isConnected;
  }

  Future<List<RK3588DeviceInfo>> scanLocalDevices() async {
    final List<RK3588DeviceInfo> foundDevices = [];
    final Set<String> testedUrls = {};
    
    AppLogger.info('开始局域网扫描...');
    
    final baseIps = await _getLocalIpBases();
    AppLogger.info('扫描网段: $baseIps');
    final futures = <Future<void>>[];
    for (final baseIp in baseIps) {
      for (int i = 1; i < 255; i++) {
        final ip = '$baseIp.$i';
        final url = 'http://$ip:9000';
        if (testedUrls.contains(url)) continue;
        testedUrls.add(url);
        futures.add(_testDeviceUrl(url, foundDevices));
      }
    }
    await Future.wait(futures);
    
    foundDevices.addAll(_connectionHistory);
    
    final uniqueDevices = <String, RK3588DeviceInfo>{};
    for (var device in foundDevices) {
      uniqueDevices[device.localUrl] = device;
    }
    
    AppLogger.info('扫描完成，找到 ${uniqueDevices.length} 个设备');
    return uniqueDevices.values.toList();
  }
  
  /// 枚举本机所有 IPv4 网卡地址，提取 /24 网段（如 192.168.43）。
  Future<List<String>> _getLocalIpBases() async {
    final bases = <String>{};
    try {
      final interfaces = await NetworkInterface.list(
        includeLoopback: false,
        type: InternetAddressType.IPv4,
      );
      for (final iface in interfaces) {
        for (final addr in iface.addresses) {
          final ip = addr.address;
          final parts = ip.split('.');
          if (parts.length != 4) continue;
          // 仅扫描常见私有网段
          if (ip.startsWith('192.168.') ||
              ip.startsWith('10.') ||
              (parts[0] == '172' &&
                  int.tryParse(parts[1]) != null &&
                  int.parse(parts[1]) >= 16 &&
                  int.parse(parts[1]) <= 31)) {
            bases.add('${parts[0]}.${parts[1]}.${parts[2]}');
          }
        }
      }
    } catch (e) {
      AppLogger.info('枚举网卡失败: $e');
    }
    if (bases.isEmpty) {
      bases.addAll(['192.168.1', '192.168.0', '192.168.43']);
    }
    return bases.toList();
  }
  
  Future<void> _testDeviceUrl(String url, List<RK3588DeviceInfo> devices) async {
    try {
      final testDio = Dio();
      testDio.options.connectTimeout = Duration(milliseconds: 500);
      testDio.options.receiveTimeout = Duration(milliseconds: 500);
      
      final response = await testDio.get('$url/api/edge/info');
      
      if (response.statusCode == 200) {
        final data = response.data;
        devices.add(RK3588DeviceInfo(
          deviceId: data['device_id'] ?? 'unknown',
          name: data['name'] ?? 'RK3588 Device',
          localUrl: url,
          tailscaleUrl: data['tailscale_url'],
          gatewayUrl: data['gateway_url'],
        ));
        AppLogger.info('发现设备: ${data['name']} @ $url');
      }
    } catch (e) {
    }
  }

  Future<String?> getBestConnectionUrl(RK3588DeviceInfo device) async {
    final List<String> urls = [];
    
    urls.add(device.localUrl);
    
    if (device.tailscaleUrl != null) {
      urls.add(device.tailscaleUrl!);
    }
    
    if (device.gatewayUrl != null) {
      urls.add(device.gatewayUrl!);
    }
    
    for (final url in urls) {
      if (await testConnection(url)) {
        AppLogger.info('最优连接地址: $url');
        return url;
      }
    }
    
    return null;
  }

  Future<RK3588DeviceInfo?> fetchDevicePairInfo(String localUrl) async {
    try {
      final response = await _dio.get('$localUrl/api/edge/pair/start');
      if (response.statusCode == 200) {
        final data = response.data;
        return RK3588DeviceInfo.fromJson(data).copyWith(localUrl: localUrl);
      }
    } catch (e) {
      AppLogger.error('获取配对信息失败: $e');
    }
    return null;
  }

  Future<Map<String, dynamic>?> confirmPairing(String deviceId, String pairCode, String localUrl) async {
    try {
      final response = await _dio.post(
        '$localUrl/api/edge/pair/confirm',
        data: {
          'device_id': deviceId,
          'pair_code': pairCode,
          'client_name': 'HarBeat Mobile',
          'client_type': 'mobile',
        },
      );
      if (response.statusCode == 200) {
        return response.data;
      }
    } catch (e) {
      AppLogger.error('配对确认失败: $e');
    }
    return null;
  }

  Future<bool> connectToRK3588(RK3588DeviceInfo device, String deviceToken) async {
    _connectionStatus = ConnectionStatus.connecting;
    _deviceToken = deviceToken;
    
    try {
      String? baseUrl = await getBestConnectionUrl(device);
      
      if (baseUrl == null) {
        baseUrl = device.localUrl;
      }
      
      _lastUsedUrl = baseUrl;
      _dio.options.baseUrl = baseUrl;
      _dio.options.headers['Authorization'] = 'Bearer $deviceToken';

      final response = await _dio.get('/api/edge/info');
      if (response.statusCode == 200) {
        _currentDevice = device.copyWith(
          isConnected: true,
          deviceToken: deviceToken,
          lastConnectedTime: DateTime.now().millisecondsSinceEpoch,
        );
        
        _addToHistory(_currentDevice!);
        
        _updateConnectionStatus(true);
        await _connectWebSocket(baseUrl, deviceToken);
        _startHeartbeat();
        
        await getStatus();
        
        AppLogger.info('RK3588 连接成功: ${device.deviceId} via $baseUrl');
        return true;
      }
    } catch (e) {
      AppLogger.error('连接 RK3588 失败: $e');
      _updateConnectionStatus(false);
    }
    return false;
  }

  void _addToHistory(RK3588DeviceInfo device) {
    _connectionHistory.removeWhere((d) => d.localUrl == device.localUrl);
    _connectionHistory.insert(0, device);
    
    if (_connectionHistory.length > 10) {
      _connectionHistory.removeLast();
    }
  }

  Future<void> _connectWebSocket(String baseUrl, String deviceToken) async {
    try {
      // WS is served on the same port as REST (:9000/ws/control)
      String wsUrl = baseUrl.replaceFirst('http://', 'ws://').replaceFirst('https://', 'wss://');
      wsUrl += '/ws/control?token=$deviceToken';
      AppLogger.info('WebSocket 连接: $wsUrl');
      
      _webSocketChannel = IOWebSocketChannel.connect(wsUrl);
      
      _webSocketChannel?.stream.listen((message) {
        try {
          final data = jsonDecode(message);
          _handleWebSocketMessage(data);
          _onMessageReceived?.call(data);
          _reconnectAttempts = 0;
        } catch (e) {
          AppLogger.error('WebSocket 消息解析失败: $e');
        }
      }, onError: (error) {
        AppLogger.error('WebSocket 错误: $error');
        _scheduleReconnect();
      }, onDone: () {
        AppLogger.info('WebSocket 连接关闭');
        _scheduleReconnect();
      });
    } catch (e) {
      AppLogger.error('WebSocket 连接失败: $e');
      _scheduleReconnect();
    }
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(Duration(seconds: 30), (timer) async {
      if (_isConnected) {
        try {
          await getStatus();
        } catch (e) {
          AppLogger.error('心跳检测失败: $e');
        }
      }
    });
  }

  void _scheduleReconnect() {
    if (_reconnectAttempts >= _maxReconnectAttempts) {
      AppLogger.error('达到最大重连次数，停止重连');
      return;
    }
    
    _reconnectTimer?.cancel();
    _reconnectAttempts++;
    
    final delay = Duration(seconds: _reconnectAttempts * 2);
    AppLogger.info('${delay.inSeconds}秒后尝试重连 (第 $_reconnectAttempts 次)');
    
    _reconnectTimer = Timer(delay, () async {
      if (!_isConnected && _currentDevice != null && _deviceToken != null) {
        await connectToRK3588(_currentDevice!, _deviceToken!);
      }
    });
  }

  void _handleWebSocketMessage(Map<String, dynamic> message) {
    final type = message['type'];
    switch (type) {
      case 'status':
        _currentStatus = EdgeStatus.fromJson(message);
        _isPlaying = _currentStatus?.isPlaying ?? false;
        _volume = _currentStatus?.volume ?? 75;
        _currentStyle = _parseStyle(_currentStatus?.currentStyle ?? '');
        break;
      case 'command_ack':
        AppLogger.info('命令确认: ${message['command_id']} - ${message['success']}');
        break;
      case 'meter':
        break;
      case 'key_event':
        AppLogger.info('键盘事件: ${message['key']}');
        break;
      case 'device_health':
        AppLogger.info('设备健康状态: ${message['status']}');
        break;
    }
  }

  MusicStyle _parseStyle(String style) {
    switch (style.toLowerCase()) {
      case 'breaking': return MusicStyle.breaking;
      case 'popping': return MusicStyle.popping;
      case 'locking': return MusicStyle.locking;
      case 'house': return MusicStyle.house;
      default: return MusicStyle.hiphop;
    }
  }

  Future<void> disconnect() async {
    _heartbeatTimer?.cancel();
    _reconnectTimer?.cancel();
    _reconnectAttempts = 0;
    
    try {
      await _webSocketChannel?.sink.close();
      _webSocketChannel = null;
    } catch (e) {
      AppLogger.error('关闭 WebSocket 失败: $e');
    }
    
    _currentDevice = null;
    _currentStatus = null;
    _deviceToken = null;
    _updateConnectionStatus(false);
    AppLogger.info('已断开 RK3588 连接');
  }

  Future<bool> sendCommand(String command, Map<String, dynamic> payload) async {
    if (!_isConnected || _webSocketChannel == null) {
      return _sendCommandHttp(command, payload);
    }

    try {
      final message = jsonEncode({
        'type': 'command',
        'command_id': _generateCommandId(),
        'command': command,
        'payload': payload,
      });
      _webSocketChannel?.sink.add(message);
      return true;
    } catch (e) {
      AppLogger.error('发送 WebSocket 命令失败: $e');
      return _sendCommandHttp(command, payload);
    }
  }

  Future<bool> _sendCommandHttp(String command, Map<String, dynamic> payload) async {
    try {
      // Map high-level commands to edge-agent REST endpoints
      final endpointMap = {
        'play': '/play',
        'pause': '/pause',
        'resume': '/resume',
        'stop': '/pause',
        'next': '/next',
        'previous': '/next', // edge-agent 暂无 prev，退化为 next
        'seek': '/seek',
        'trigger_sfx': '/trigger',
        'set_energy': '/energy',
        'switch_style': '/style',
        'start_loop': '/loop',
        'stop_loop': '/loop',
        'emergency_stop': '/pause',
      };
      final endpoint = endpointMap[command] ?? '/trigger';
      final response = await _dio.post(endpoint, data: payload);
      return response.statusCode == 200;
    } catch (e) {
      AppLogger.error('发送 HTTP 命令失败: $e');
      return false;
    }
  }

  String _generateCommandId() {
    return DateTime.now().millisecondsSinceEpoch.toString().substring(5);
  }

  /// 播放指定歌曲。
  /// - 若提供 [songId]，则发 `/play {song_id, start_at_sec}` 启动新曲；
  /// - 若未提供，则视为「继续播放」，发 `/resume`（之前已加载的曲目）。
  Future<bool> play({int? songId, double startAtSec = 0.0}) async {
    _isPlaying = true;
    if (songId != null) {
      return await sendCommand('play', {
        'song_id': songId,
        'start_at_sec': startAtSec,
      });
    }
    // 无 songId：触发 resume（暂停后再播放）
    return await _sendCommandHttp('resume', {});
  }

  Future<bool> pause() async {
    _isPlaying = false;
    return await sendCommand('pause', {});
  }

  Future<bool> stop() async {
    _isPlaying = false;
    return await sendCommand('stop', {});
  }

  Future<bool> nextTrack() async {
    return await sendCommand('next', {});
  }

  Future<bool> previousTrack() async {
    return await sendCommand('previous', {});
  }

  Future<bool> setVolume(int level) async {
    if (level < 0 || level > 100) {
      AppLogger.error('音量值必须在 0-100 之间');
      return false;
    }
    _volume = level;
    return await sendCommand('set_volume', {'level': level});
  }

  Future<bool> increaseVolume({int step = 5}) async {
    final newLevel = (_volume + step).clamp(0, 100);
    return await setVolume(newLevel);
  }

  Future<bool> decreaseVolume({int step = 5}) async {
    final newLevel = (_volume - step).clamp(0, 100);
    return await setVolume(newLevel);
  }

  Future<int?> getVolume() async {
    return _volume;
  }

  Future<bool> seekTo(int positionMs) async {
    return await sendCommand('seek', {'position_ms': positionMs});
  }

  Future<bool> setEnergyMode(EnergyMode mode) async {
    _currentEnergyMode = mode;
    return await sendCommand('set_energy', {'mode': mode.name});
  }

  Future<bool> setMusicStyle(MusicStyle style, {bool triggerNext = false}) async {
    _currentStyle = style;
    return await sendCommand('switch_style', {
      'style': style.name,
      'trigger_next': triggerNext,
      'fallback_strategy': 'clean_blend',
    });
  }

  Future<bool> startLoop({int durationMs = 30000}) async {
    return await sendCommand('start_loop', {'duration_ms': durationMs});
  }

  Future<bool> stopLoop() async {
    return await sendCommand('stop_loop', {});
  }

  Future<bool> cutToNext({CutMode mode = CutMode.clean_blend}) async {
    return await sendCommand('next', {
      'strategy': mode.name,
      'energy': 'none',
    });
  }

  /// 加花 / 音效：把音效名映射到 RK3588 audio-engine 的 trigger key (1-9)。
  /// audio-engine 当前实现：
  ///   key=0 暂停/继续；1-3 单次加花 (ha/scratch/horn)；
  ///   4-6 循环加花 (drum/bass/hat loop)；7-9 stem 特效。
  static const Map<String, int> _sfxIdToKey = {
    'applause': 1, 'ha': 1,
    'scratch': 2,
    'airhorn': 3, 'horn': 3, 'boom': 3,
    'drumroll': 4, 'drum': 4, 'drum_loop': 4,
    'bass': 5, 'bass_loop': 5,
    'hat': 6, 'hat_loop': 6,
    'mute_vocals': 7, 'vocals': 7,
    'solo_drums': 8,
    'lpf': 9, 'filter': 9,
  };

  Future<bool> triggerSoundEffect(String sfxId, {double gain = 0.5}) async {
    final key = _sfxIdToKey[sfxId.toLowerCase()] ?? 1;
    return await triggerKey(key);
  }

  /// 直接触发 audio-engine trigger key (0-9)。
  Future<bool> triggerKey(int key) async {
    return await sendCommand('trigger_sfx', {'key': key});
  }

  Future<bool> emergencyStop() async {
    AppLogger.warning('紧急停止命令已发送');
    return await sendCommand('emergency_stop', {});
  }

  Future<EdgeStatus?> getStatus() async {
    try {
      final response = await _dio.get('/state');
      final data = response.data;
      _currentStatus = EdgeStatus.fromJson(data);
      return _currentStatus;
    } catch (e) {
      AppLogger.error('获取状态失败: $e');
      return null;
    }
  }

  Future<RK3588DeviceInfo> addManualDevice(String ipAddress, String deviceName) async {
    if (!ipAddress.startsWith('http://') && !ipAddress.startsWith('https://')) {
      ipAddress = 'http://$ipAddress';
    }
    // 仅检查 host[:port] 段是否已带端口（避免被 scheme 的 ':' 误判）
    final schemeSepIdx = ipAddress.indexOf('://');
    final hostPart = schemeSepIdx >= 0 ? ipAddress.substring(schemeSepIdx + 3) : ipAddress;
    final hostNoPath = hostPart.split('/').first;
    if (!hostNoPath.contains(':')) {
      ipAddress = '$ipAddress:9000';
    }
    
    return RK3588DeviceInfo(
      deviceId: 'manual-${DateTime.now().millisecondsSinceEpoch}',
      name: deviceName.isEmpty ? 'RK3588 Device' : deviceName,
      localUrl: ipAddress,
      lastConnectedTime: DateTime.now().millisecondsSinceEpoch,
    );
  }

  Future<bool> testConnection(String baseUrl) async {
    try {
      final testDio = Dio();
      testDio.options.connectTimeout = Duration(seconds: 3);
      testDio.options.receiveTimeout = Duration(seconds: 3);
      final response = await testDio.get('$baseUrl/api/edge/info');
      return response.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  Future<List<RK3588DeviceInfo>> getCloudDeviceList(String userToken) async {
    try {
      final response = await _dio.get(
        'https://harbeat.com/api/devices',
        options: Options(headers: {'Authorization': 'Bearer $userToken'}),
      );
      final devices = response.data['devices'] as List?;
      if (devices == null) return [];
      return devices.map((d) => RK3588DeviceInfo.fromJson(d)).toList();
    } catch (e) {
      AppLogger.error('获取云端设备列表失败: $e');
      return [];
    }
  }

  Future<Map<String, dynamic>?> getCachedPlaylist() async {
    try {
      final response = await _dio.get('/api/edge/cache/playlist');
      return response.data;
    } catch (e) {
      AppLogger.error('获取缓存歌单失败: $e');
      return null;
    }
  }

  Future<bool> syncCache() async {
    try {
      final response = await _dio.post('/api/edge/cache/sync');
      return response.statusCode == 200;
    } catch (e) {
      AppLogger.error('同步缓存失败: $e');
      return false;
    }
  }

  void dispose() {
    _heartbeatTimer?.cancel();
    _reconnectTimer?.cancel();
    disconnect();
  }
}
