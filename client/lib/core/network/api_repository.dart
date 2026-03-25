import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

// 定义一个基础网络响应模型
class StandardResponse {
  final int code;
  final String message;
  final dynamic data;

  StandardResponse({required this.code, required this.message, this.data});

  factory StandardResponse.fromJson(Map<String, dynamic> json) {
    return StandardResponse(
      code: json['code'] as int,
      message: json['message'] as String,
      data: json['data'],
    );
  }
}

class ApiRepository {
  // 注意：在模拟器里访问电脑后端，必须用 10.0.2.2
  static const String _baseDomain = 'http://10.0.2.2:8000';
  final Dio _dio = Dio(BaseOptions(baseUrl: _baseDomain));

  // ==========================================
  // 👇 恢复之前的老功能：保存Cue点、埋点日志
  // ==========================================

  Future<void> reportEvent(int userId, String eventType, String detail) async {
    try {
      await _dio.post('/logs/event', data: {
        "user_id": userId,
        "event_type": eventType,
        "detail": detail,
      });
    } catch (e) {
      print("上报失败: $e");
    }
  }

  Future<void> saveCuePoint({
    required int userId,
    required int trackId,
    required String cueType,
    required double startTime,
    double? endTime,
    String? name,
  }) async {
    try {
      await _dio.post('/practice/cue', data: {
        "user_id": userId,
        "track_id": trackId,
        "cue_type": cueType,
        "start_time": startTime,
        "end_time": endTime,
        "name": name,
      });
    } catch (e) {
      print("保存点位失败: $e");
    }
  }

  // ==========================================
  // 👇 新增功能：BPM 分析、AI 音轨分离
  // ==========================================

  Future<Map<String, dynamic>> uploadAndAnalyzeBpm(String filePath) async {
    try {
      final formData = FormData.fromMap({
        'file': await MultipartFile.fromFile(filePath, filename: 'upload_practice.mp3'),
      });

      final response = await _dio.post('/api/music/analyze', data: formData);
      final standardResp = StandardResponse.fromJson(response.data);

      if (standardResp.code == 0) {
        return standardResp.data as Map<String, dynamic>;
      } else {
        throw Exception("后端分析失败: ${standardResp.message}");
      }
    } catch (e) {
      print("BPM 分析失败: $e");
      return {"bpm": 125.0, "key": "A Minor", "track_id": 999, "error": e.toString()};
    }
  }

  Future<Map<String, dynamic>> splitStemsByTrackId(int trackId) async {
    try {
      final response = await _dio.post(
        '/api/music/split',
        queryParameters: {'track_id': trackId},
      );
      
      final standardResp = StandardResponse.fromJson(response.data);

      if (standardResp.code == 0) {
        final stemsData = standardResp.data as Map<String, dynamic>;
        // 拼接绝对路径
        return {
          'vocals': '$_baseDomain${stemsData['vocals_url']}',
          'drums': '$_baseDomain${stemsData['drums_url']}',
          'bass': '$_baseDomain${stemsData['bass_url']}',
          'other': '$_baseDomain${stemsData['other_url']}',
        };
      } else {
        throw Exception("后端拆轨失败: ${standardResp.message}");
      }
    } catch (e) {
      print("音轨分离失败: $e");
      return {
        "status": "error",
        "message": "音轨分离失败（模拟）",
        "vocals": "fake_vocals_url",
        "drums": "fake_drums_url",
        "bass": "fake_bass_url",
        "other": "fake_other_url"
      };
    }
  }
}

final apiRepoProvider = Provider((ref) => ApiRepository());