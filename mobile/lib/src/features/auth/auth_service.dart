import '../../core/network/api_client.dart';
import 'models.dart';

class AuthService {
  AuthService({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<AuthSession> login({
    required String username,
    required String password,
  }) {
    return _client.post<AuthSession>(
      '/api/auth/login',
      body: {
        'username': username,
        'password': password,
      },
      parser: (json) => AuthSession.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<AuthSession> register({
    required String username,
    required String password,
    required String danceStyle,
    required String level,
    required String favoriteStyle,
  }) {
    return _client.post<AuthSession>(
      '/api/auth/register',
      body: {
        'username': username,
        'password': password,
        'dance_style': danceStyle,
        'level': level,
        'favorite_style': favoriteStyle,
      },
      parser: (json) => AuthSession.fromJson(json as Map<String, dynamic>),
    );
  }

  Future<UserMe> getMe() {
    return _client.get<UserMe>(
      '/api/auth/me',
      parser: (json) => UserMe.fromJson(json as Map<String, dynamic>),
    );
  }
}
