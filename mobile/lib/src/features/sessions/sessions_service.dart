import '../../core/network/api_client.dart';
import 'models.dart';

class SessionsService {
  SessionsService({ApiClient? client}) : _client = client ?? ApiClient();

  final ApiClient _client;

  Future<int> startSession({
    required int userId,
    required String mode,
  }) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/sessions/start',
      body: {'user_id': userId, 'mode': mode},
      parser: (json) => json as Map<String, dynamic>,
    );
    return data['session_id'] as int? ?? 0;
  }

  Future<bool> logSessionEvent({
    required int sessionId,
    required String eventType,
    String? eventValue,
  }) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/sessions/event',
      body: {
        'session_id': sessionId,
        'event_type': eventType,
        'event_value': eventValue,
        'timestamp': DateTime.now().toIso8601String(),
      },
      parser: (json) => json as Map<String, dynamic>,
    );
    return data['success'] as bool? ?? false;
  }

  Future<bool> endSession(int sessionId) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/sessions/end',
      body: {'session_id': sessionId},
      parser: (json) => json as Map<String, dynamic>,
    );
    return data['success'] as bool? ?? false;
  }

  Future<bool> logInteraction(Map<String, dynamic> payload) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/sessions/log-interaction',
      body: payload,
      parser: (json) => json as Map<String, dynamic>,
    );
    return data['success'] as bool? ?? false;
  }

  Future<List<PracticeTrack>> generatePracticeList({
    required int userId,
    int targetDuration = 30,
    String? danceStyle,
  }) async {
    final data = await _client.post<Map<String, dynamic>>(
      '/api/sessions/generate-practice-list',
      body: {
        'user_id': userId,
        'target_duration': targetDuration,
        if (danceStyle != null && danceStyle.isNotEmpty) 'dance_style': danceStyle,
      },
      parser: (json) => json as Map<String, dynamic>,
    );
    return (data['tracks'] as List<dynamic>? ?? [])
        .map((item) => PracticeTrack.fromJson(item as Map<String, dynamic>))
        .toList();
  }
}
