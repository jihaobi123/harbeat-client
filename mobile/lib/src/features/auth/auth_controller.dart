import 'package:flutter/foundation.dart';

import '../../core/storage/token_storage.dart';
import 'auth_service.dart';
import 'models.dart';

class AuthController extends ChangeNotifier {
  AuthController({AuthService? service}) : _service = service ?? AuthService();

  final AuthService _service;

  bool _isLoading = true;
  bool _isSubmitting = false;
  AuthSession? _session;
  UserMe? _currentUser;
  String? _errorMessage;

  bool get isLoading => _isLoading;
  bool get isSubmitting => _isSubmitting;
  bool get isAuthenticated => _session != null;
  AuthSession? get session => _session;
  UserMe? get currentUser => _currentUser;
  String? get errorMessage => _errorMessage;

  Future<void> bootstrap() async {
    _isLoading = true;
    notifyListeners();

    final token = await TokenStorage.readToken();
    if (token != null && token.isNotEmpty) {
      try {
        final me = await _service.getMe();
        _currentUser = me;
        _session = AuthSession(
          accessToken: token,
          userId: me.id,
          username: me.username,
        );
      } catch (_) {
        await TokenStorage.clear();
        _session = null;
        _currentUser = null;
      }
    }

    _isLoading = false;
    notifyListeners();
  }

  Future<bool> login({
    required String username,
    required String password,
  }) async {
    return _authenticate(() => _service.login(username: username, password: password));
  }

  Future<bool> register({
    required String username,
    required String password,
    required String danceStyle,
    required String level,
    required String favoriteStyle,
  }) async {
    return _authenticate(
      () => _service.register(
        username: username,
        password: password,
        danceStyle: danceStyle,
        level: level,
        favoriteStyle: favoriteStyle,
      ),
    );
  }

  Future<bool> _authenticate(Future<AuthSession> Function() request) async {
    _isSubmitting = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final session = await request();
      _session = session;
      await TokenStorage.saveToken(session.accessToken);
      _currentUser = await _service.getMe();
      return true;
    } catch (error) {
      _errorMessage = error.toString();
      return false;
    } finally {
      _isSubmitting = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    _session = null;
    _currentUser = null;
    await TokenStorage.clear();
    notifyListeners();
  }
}
