import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final apiRepoProvider = Provider((ref) => ApiRepository());

class ApiRepository {
  // 假设你在本地模拟器运行，10.0.2.2 是 Android 模拟器访问宿主机的 IP
  // 如果是真实手机连局域网 WiFi，请换成你电脑的局域网 IP (如 192.168.x.x)
  final Dio _dio = Dio(BaseOptions(baseUrl: 'http://10.0.2.2:8000'));

  // 1. 上报事件流水账 (埋点)
  Future<void> reportEvent(int sessionId, String eventType, String eventValue) async {
    try {
      await _dio.post('/api/sessions/event', data: {
        "session_id": sessionId,
        "event_type": eventType,
        "event_value": eventValue,
        "timestamp": DateTime.now().toIso8601String(),
      });
      print("埋点上报成功: $eventType");
    } catch (e) {
      print("埋点上报失败: $e");
    }
  }

  // 2. 持久化保存 Cue 点/A-B 段 (偏好存储)
  Future<void> saveCuePoint({
    required int userId,
    required int trackId,
    required String cueType,
    required double startTime,
    double? endTime,
  }) async {
    try {
      await _dio.post('/api/music/cues', data: {
        "user_id": userId,
        "track_id": trackId,
        "cue_type": cueType,
        "start_time": startTime,
        "end_time": endTime,
      });
      print("Cue点持久化保存成功");
    } catch (e) {
      print("Cue点保存失败: $e");
    }
  }
}
