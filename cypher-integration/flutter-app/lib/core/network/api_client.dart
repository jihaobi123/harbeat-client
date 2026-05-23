import 'package:dio/dio.dart';
import '../config/api_config.dart';
import '../utils/logger.dart';

/// API 客户端单例
class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;
  ApiClient._internal() {
    _initDio();
  }
  
  late final Dio dio;
  String? _token;
  
  void _initDio() {
    dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: Duration(seconds: ApiConfig.connectTimeout),
      receiveTimeout: Duration(seconds: ApiConfig.receiveTimeout),
      sendTimeout: Duration(seconds: ApiConfig.sendTimeout),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    ));
    
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        AppLogger.info('📤 Request: ${options.method} ${options.uri}');
        if (_token != null) {
          options.headers['Authorization'] = 'Bearer $_token';
        }
        return handler.next(options);
      },
      onResponse: (response, handler) {
        AppLogger.info('✅ Response: ${response.statusCode} ${response.requestOptions.uri}');
        return handler.next(response);
      },
      onError: (error, handler) {
        AppLogger.error('❌ Error: ${error.message}', error: error);
        return handler.next(error);
      },
    ));
  }
  
  /// 外部手动重新初始化（可选）
  void init() {}
  
  String? getToken() {
    return _token;
  }
  
  void setToken(String token) {
    _token = token;
    AppLogger.info('Token set: ${token.substring(0, 10)}...');
  }
  
  void clearToken() {
    _token = null;
    AppLogger.info('Token cleared');
  }
  
  /// 切换 API 地址（用于开发/生产环境切换）
  void switchBaseUrl(String newUrl) {
    dio.options.baseUrl = newUrl;
    AppLogger.info('Base URL switched to: $newUrl');
  }
}
