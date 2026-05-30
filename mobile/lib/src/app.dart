import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';
import 'home_page.dart';
import 'models.dart';

const String defaultBaseUrl = String.fromEnvironment(
  'HARBEAT_BASE_URL',
  defaultValue: 'http://8.136.120.255',
);

const String tokenStorageKey = 'harbeat_token';
const String rkBaseUrlStorageKey = 'harbeat_rk_base_url';
const String apiBaseUrlStorageKey = 'harbeat_api_base_url';
const String defaultRkBaseUrl = '192.168.43.7:9000';

class HarBeatApp extends StatelessWidget {
  const HarBeatApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'HarBeat',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFE85A2A),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF5EDE3),
        cardTheme: const CardThemeData(
          color: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(12)),
            side: BorderSide(color: Color(0xFFE0D6CC)),
          ),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF1A1A1A),
          foregroundColor: Colors.white,
          elevation: 0,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFFE85A2A),
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          ),
        ),
        textTheme: const TextTheme(
          headlineMedium: TextStyle(fontWeight: FontWeight.w800, color: Color(0xFF1A1A1A)),
          bodyLarge: TextStyle(color: Color(0xFF1A1A1A)),
          bodyMedium: TextStyle(color: Color(0xFF333333)),
          bodySmall: TextStyle(color: Color(0xFF666666)),
        ),
        useMaterial3: true,
      ),
      home: const RootPage(),
    );
  }
}

class RootPage extends StatefulWidget {
  const RootPage({super.key});

  @override
  State<RootPage> createState() => _RootPageState();
}

class _RootPageState extends State<RootPage> {
  HarBeatApiClient _apiClient = HarBeatApiClient(baseUrl: defaultBaseUrl);
  String _apiBaseUrl = defaultBaseUrl;
  SessionBundle? _session;
  DashboardData? _dashboard;
  bool _booting = true;
  bool _loadingDashboard = false;
  String? _error;
  String _rkBaseUrl = defaultRkBaseUrl;

  @override
  void initState() {
    super.initState();
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    setState(() {
      _booting = true;
      _error = null;
    });

    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(tokenStorageKey);
    final rkUrl = prefs.getString(rkBaseUrlStorageKey);
    final apiUrl = prefs.getString(apiBaseUrlStorageKey);
    if (apiUrl != null && apiUrl.isNotEmpty) {
      _apiBaseUrl = apiUrl;
      _apiClient = HarBeatApiClient(baseUrl: apiUrl);
    }
    if (rkUrl != null && rkUrl.isNotEmpty) {
      _rkBaseUrl = rkUrl;
    }
    if (token == null || token.isEmpty) {
      setState(() {
        _session = null;
        _dashboard = null;
        _booting = false;
      });
      return;
    }

    try {
      final profile = await _apiClient.getMe(token);
      _session = SessionBundle(token: token, profile: profile);
      await _loadDashboard();
    } catch (error) {
      await prefs.remove(tokenStorageKey);
      setState(() {
        _session = null;
        _dashboard = null;
        _booting = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _loadDashboard() async {
    final session = _session;
    if (session == null) return;

    setState(() {
      _loadingDashboard = true;
      _error = null;
    });

    try {
      final dashboard = await _apiClient.loadDashboard(
        token: session.token,
        userId: session.profile.id,
      );
      setState(() {
        _dashboard = dashboard;
        _loadingDashboard = false;
        _booting = false;
      });
    } catch (error) {
      setState(() {
        _loadingDashboard = false;
        _booting = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _handleAuthenticated(AuthResult authResult) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(tokenStorageKey, authResult.token);
    setState(() {
      _session = SessionBundle(token: authResult.token, profile: authResult.profile);
      _dashboard = null;
    });
    await _loadDashboard();
  }

  Future<void> _logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(tokenStorageKey);
    setState(() {
      _session = null;
      _dashboard = null;
      _error = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_booting) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    if (_session == null) {
      return AuthPage(
        apiClient: _apiClient,
        initialError: _error,
        onAuthenticated: _handleAuthenticated,
      );
    }

    return HomePage(
      apiClient: _apiClient,
      session: _session!,
      rkBaseUrl: _rkBaseUrl,
      apiBaseUrl: _apiBaseUrl,
      onApiBaseUrlChanged: (url) async {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString(apiBaseUrlStorageKey, url);
        setState(() {
          _apiBaseUrl = url;
          _apiClient = HarBeatApiClient(baseUrl: url);
          _dashboard = null;
        });
        await _loadDashboard();
      },
      onRkBaseUrlChanged: (url) async {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString(rkBaseUrlStorageKey, url);
        setState(() => _rkBaseUrl = url);
      },
      data: _dashboard,
      loading: _loadingDashboard,
      error: _error,
      onRefresh: _loadDashboard,
      onLogout: _logout,
    );
  }
}

class AuthPage extends StatefulWidget {
  const AuthPage({
    super.key,
    required this.apiClient,
    required this.onAuthenticated,
    this.initialError,
  });

  final HarBeatApiClient apiClient;
  final Future<void> Function(AuthResult authResult) onAuthenticated;
  final String? initialError;

  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _registerMode = false;
  bool _submitting = false;
  String? _error;
  String _danceStyle = 'hiphop';
  String _level = 'beginner';

  @override
  void initState() {
    super.initState();
    _error = widget.initialError;
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
    });

    try {
      late final AuthPayload payload;
      if (_registerMode) {
        payload = await widget.apiClient.register(
          username: _usernameController.text.trim(),
          password: _passwordController.text,
          danceStyle: _danceStyle,
          level: _level,
          favoriteStyle: _danceStyle,
        );
      } else {
        payload = await widget.apiClient.login(
          username: _usernameController.text.trim(),
          password: _passwordController.text,
        );
      }

      final profile = await widget.apiClient.getMe(payload.accessToken);
      await widget.onAuthenticated(AuthResult(token: payload.accessToken, profile: profile));
    } catch (error) {
      setState(() {
        _error = error.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _submitting = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'HarBeat',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                                fontWeight: FontWeight.w800,
                                color: Theme.of(context).colorScheme.primary,
                              ),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          '原生移动端登录与首页',
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 20),
                        SegmentedButton<bool>(
                          segments: const [
                            ButtonSegment<bool>(value: false, label: Text('登录')),
                            ButtonSegment<bool>(value: true, label: Text('注册')),
                          ],
                          selected: {_registerMode},
                          onSelectionChanged: (value) {
                            setState(() {
                              _registerMode = value.first;
                              _error = null;
                            });
                          },
                        ),
                        const SizedBox(height: 20),
                        if (_error != null) ...[
                          Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                          const SizedBox(height: 12),
                        ],
                        TextFormField(
                          controller: _usernameController,
                          decoration: const InputDecoration(
                            labelText: '用户名',
                            border: OutlineInputBorder(),
                          ),
                          validator: (value) =>
                              value == null || value.trim().isEmpty ? '请输入用户名' : null,
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _passwordController,
                          obscureText: true,
                          decoration: const InputDecoration(
                            labelText: '密码',
                            border: OutlineInputBorder(),
                          ),
                          validator: (value) {
                            if (value == null || value.isEmpty) return '请输入密码';
                            if (_registerMode && value.length < 6) return '注册密码至少 6 位';
                            return null;
                          },
                        ),
                        if (_registerMode) ...[
                          const SizedBox(height: 16),
                          DropdownButtonFormField<String>(
                            value: _danceStyle,
                            decoration: const InputDecoration(
                              labelText: '舞种',
                              border: OutlineInputBorder(),
                            ),
                            items: const [
                              'hiphop',
                              'jazz',
                              'breaking',
                              'popping',
                              'locking',
                              'waacking',
                              'house',
                              'krump',
                              'other',
                            ].map((item) => DropdownMenuItem(value: item, child: Text(item))).toList(),
                            onChanged: (value) => setState(() => _danceStyle = value ?? 'hiphop'),
                          ),
                          const SizedBox(height: 16),
                          DropdownButtonFormField<String>(
                            value: _level,
                            decoration: const InputDecoration(
                              labelText: '水平',
                              border: OutlineInputBorder(),
                            ),
                            items: const [
                              DropdownMenuItem(value: 'beginner', child: Text('beginner')),
                              DropdownMenuItem(value: 'intermediate', child: Text('intermediate')),
                              DropdownMenuItem(value: 'advanced', child: Text('advanced')),
                            ],
                            onChanged: (value) => setState(() => _level = value ?? 'beginner'),
                          ),
                        ],
                        const SizedBox(height: 24),
                        FilledButton(
                          onPressed: _submitting ? null : _submit,
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            child: Text(_submitting ? '提交中...' : _registerMode ? '注册并进入' : '登录'),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          '接口地址: ${widget.apiClient.baseUrl}',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
