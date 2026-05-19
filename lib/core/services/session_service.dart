import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:harbeat_app/data/models/session_model.dart';
import 'package:harbeat_app/core/utils/logger.dart';

class SessionService {
  static final SessionService _instance = SessionService._internal();
  factory SessionService() => _instance;
  SessionService._internal();

  static const String _sessionsKey = 'harbeat_sessions';
  static const String _currentSessionKey = 'harbeat_current_session';
  static const int _maxLocalSessions = 50;

  final List<SessionModel> _sessions = [];
  SessionModel? _currentSession;

  Future<void> init() async {
    await _loadSessions();
    AppLogger.info('SessionService 初始化完成，共 ${_sessions.length} 个历史会话');
  }

  Future<void> _loadSessions() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final sessionsJson = prefs.getString(_sessionsKey);
      
      if (sessionsJson != null) {
        final List<dynamic> decoded = jsonDecode(sessionsJson);
        _sessions.clear();
        _sessions.addAll(
          decoded.map((json) => SessionModel.fromJson(json as Map<String, dynamic>)),
        );
        _sessions.sort((a, b) => b.startTime.compareTo(a.startTime));
      }

      final currentSessionJson = prefs.getString(_currentSessionKey);
      if (currentSessionJson != null) {
        _currentSession = SessionModel.fromJson(
          jsonDecode(currentSessionJson) as Map<String, dynamic>,
        );
      }
    } catch (e, stackTrace) {
      AppLogger.error('加载会话历史失败: $e', error: e, stackTrace: stackTrace);
    }
  }

  Future<void> _saveSessions() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      
      final sessionsToSave = _sessions.take(_maxLocalSessions).toList();
      await prefs.setString(
        _sessionsKey,
        jsonEncode(sessionsToSave.map((s) => s.toJson()).toList()),
      );

      if (_currentSession != null) {
        await prefs.setString(
          _currentSessionKey,
          jsonEncode(_currentSession!.toJson()),
        );
      } else {
        await prefs.remove(_currentSessionKey);
      }
    } catch (e, stackTrace) {
      AppLogger.error('保存会话历史失败: $e', error: e, stackTrace: stackTrace);
    }
  }

  List<SessionModel> get sessions => List.unmodifiable(_sessions);
  SessionModel? get currentSession => _currentSession;

  Future<SessionModel> startSession({
    required String deviceId,
    required String deviceName,
    String? playlistId,
    String? playlistName,
  }) async {
    final session = SessionModel(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      deviceId: deviceId,
      deviceName: deviceName,
      startTime: DateTime.now(),
      playlistId: playlistId,
      playlistName: playlistName,
    );

    _currentSession = session;
    _sessions.insert(0, session);
    
    await _addEvent(session.id, 'start_session', '会话开始，连接设备: $deviceName');
    await _saveSessions();

    AppLogger.info('开始新会话: ${session.id}');
    return session;
  }

  Future<void> endSession() async {
    if (_currentSession == null) return;

    _currentSession = _currentSession!.copyWith(endTime: DateTime.now());
    
    await _addEvent(_currentSession!.id, 'end_session', '会话结束');
    await _saveSessions();

    AppLogger.info('结束会话: ${_currentSession!.id}');
    _currentSession = null;
  }

  Future<void> recordEvent({
    required String type,
    required String description,
    Map<String, dynamic>? data,
  }) async {
    if (_currentSession == null) return;

    await _addEvent(_currentSession!.id, type, description, data);
    await _saveSessions();
  }

  Future<void> _addEvent(
    String sessionId,
    String type,
    String description, [
    Map<String, dynamic>? data,
  ]) async {
    final event = SessionEvent(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      type: type,
      timestamp: DateTime.now(),
      data: data,
      description: description,
    );

    final index = _sessions.indexWhere((s) => s.id == sessionId);
    if (index != -1) {
      _sessions[index] = _sessions[index].copyWith(
        events: [..._sessions[index].events, event],
      );
    }

    if (_currentSession?.id == sessionId) {
      _currentSession = _currentSession!.copyWith(
        events: [..._currentSession!.events, event],
      );
    }
  }

  Future<void> clearSessions() async {
    _sessions.clear();
    _currentSession = null;
    await _saveSessions();
    AppLogger.info('已清除所有会话历史');
  }

  Future<void> deleteSession(String sessionId) async {
    _sessions.removeWhere((s) => s.id == sessionId);
    if (_currentSession?.id == sessionId) {
      _currentSession = null;
    }
    await _saveSessions();
    AppLogger.info('已删除会话: $sessionId');
  }

  List<SessionModel> getRecentSessions({int limit = 10}) {
    return _sessions.take(limit).toList();
  }

  List<SessionModel> getSessionsByDevice(String deviceId) {
    return _sessions.where((s) => s.deviceId == deviceId).toList();
  }
}
