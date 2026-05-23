/// API 配置管理
class ApiConfig {
  // 生产环境：阿里云 ECS 网关（转发到 Jetson）
  static const String productionUrl = 'http://8.136.120.255';

  // Jetson Tailscale 直连（仅限 Tailscale 网络内）
  static const String jetsonDirectUrl = 'http://100.87.142.21:8000';

  // RK3588 默认地址（局域网直连，快链路）
  // - :9000 是老的 edge-control（WebSocket 控制面）
  // - :9100 是新的 sync-worker（FastAPI，缓存/同步面）
  static const String rk3588DefaultUrl = 'http://192.168.43.7:9000';
  static const String rk3588SyncWorkerUrl = 'http://192.168.43.7:9100';
  
  // 本地测试环境（Windows 本机）
  static const String localTestUrl = 'http://localhost:8000';
  
  // 当前使用的 baseUrl（运行时动态切换）
  static String baseUrl = 'http://8.136.120.255';
  
  // Dio 超时配置（秒）
  static const int connectTimeout = 30;  // 连接超时 30 秒
  static const int receiveTimeout = 30;  // 接收超时 30 秒
  static const int sendTimeout = 30;     // 发送超时 30 秒
  
  // ==================== API 端点 ====================
  
  // 认证相关
  static const String auth = '/api/auth';
  static const String users = '/api/users';
  
  // 音乐相关
  static const String library = '/api/library';
  static const String music = '/api/music';
  static const String stream = '/api/stream';
  
  // 歌单相关
  static const String playlists = '/api/playlists';
  
  // 会话相关
  static const String sessions = '/api/sessions';
  
  // 推荐相关
  static const String recommendations = '/api/recommendations';
  
  // 防皮相关
  static const String fangpi = '/api/fangpi';
  
  // 用户资料
  static const String profiles = '/api/profiles';
  
  // 硬件控制（新增）
  static const String hardware = '/api/hardware';
  
  // 健康检查
  static const String health = '/health';
  
  // ==================== 完整 URL 构造器 ====================
  static String url(String path) => '$baseUrl$path';
  
  // ==================== 快捷方法 ====================
  
  /// 获取音乐流地址
  static String streamUrl(int songId, {String? token}) {
    final url = '$baseUrl$stream/$songId';
    if (token != null) {
      return '$url?token=$token';
    }
    return url;
  }
  
  /// 切换环境
  static void switchToProduction() {
    baseUrl = productionUrl;
  }
  
  static void switchToDevelopment() {
    baseUrl = jetsonDirectUrl;
  }
  
  static void switchToLocalTest() {
    baseUrl = localTestUrl;
  }
}
