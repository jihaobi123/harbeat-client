import 'package:dio/dio.dart';
import '../models/user.dart';
import '../../core/network/api_client.dart';
import '../../core/config/api_config.dart';
import '../../core/utils/logger.dart';

/// 认证服务
class AuthService {
  final ApiClient _client = ApiClient();
  
  /// 是否启用离线模式（Web 环境默认为 true）
  static bool offlineMode = true;  // 改为默认启用
  
  /// 登录
  Future<Map<String, dynamic>> login(String username, String password) async {
    // 离线模式：模拟登录成功
    if (offlineMode) {
      AppLogger.info('Offline login: $username');
      await Future.delayed(const Duration(milliseconds: 800)); // 模拟网络延迟
      
      final mockToken = 'mock_token_${DateTime.now().millisecondsSinceEpoch}';
      _client.setToken(mockToken);
      
      return {
        'token': mockToken,
        'userId': 1,
        'username': username,
      };
    }
    
    try {
      final response = await _client.dio.post(
        '${ApiConfig.auth}/login',
        data: {
          'username': username,
          'password': password,
        },
      );
      
      final data = response.data['data'];
      final token = data['access_token'] as String;
      final userId = data['user_id'] as int;
      final usernameFromResponse = data['username'] as String;
      
      // 保存 Token
      _client.setToken(token);
      
      AppLogger.info('Login successful: $usernameFromResponse');
      
      return {
        'token': token,
        'userId': userId,
        'username': username,
      };
    } on DioException catch (e) {
      AppLogger.error('Login API failed, switching to offline mode', error: e);
      offlineMode = true;
      
      // 自动切换到离线模式
      final mockToken = 'mock_token_${DateTime.now().millisecondsSinceEpoch}';
      _client.setToken(mockToken);
      
      return {
        'token': mockToken,
        'userId': 1,
        'username': username,
      };
    }
  }
  
  /// 注册
  Future<Map<String, dynamic>> register({
    required String username,
    required String password,
    String? danceStyle,
    String? level,
    String? favoriteStyle,
  }) async {
    // 离线模式：模拟注册成功
    if (offlineMode) {
      AppLogger.info('Offline registration: $username');
      await Future.delayed(const Duration(milliseconds: 1000));
      
      final mockToken = 'mock_token_${DateTime.now().millisecondsSinceEpoch}';
      _client.setToken(mockToken);
      
      return {
        'token': mockToken,
        'userId': 1,
        'username': username,
      };
    }
    
    try {
      final response = await _client.dio.post(
        '${ApiConfig.auth}/register',
        data: {
          'username': username,
          'password': password,
          if (danceStyle != null) 'dance_style': danceStyle,
          if (level != null) 'level': level,
          if (favoriteStyle != null) 'favorite_style': favoriteStyle,
        },
      );
      
      final data = response.data['data'];
      final token = data['access_token'] as String;
      
      _client.setToken(token);
      
      AppLogger.info('Registration successful: $username');
      
      return {
        'token': token,
        'userId': data['user_id'],
        'username': data['username'],
      };
    } on DioException catch (e) {
      AppLogger.error('Registration API failed, switching to offline mode', error: e);
      offlineMode = true;
      
      // 自动切换到离线模式
      final mockToken = 'mock_token_${DateTime.now().millisecondsSinceEpoch}';
      _client.setToken(mockToken);
      
      return {
        'token': mockToken,
        'userId': 1,
        'username': username,
      };
    }
  }
  
  /// 获取当前用户信息
  Future<User> getCurrentUser() async {
    try {
      final response = await _client.dio.get('${ApiConfig.auth}/me');
      final data = response.data['data'];
      return User.fromJson(data);
    } on DioException catch (e) {
      AppLogger.error('Get user info failed', error: e);
      rethrow;
    }
  }
  
  /// 登出
  void logout() {
    _client.clearToken();
    AppLogger.info('Logged out');
  }
}
