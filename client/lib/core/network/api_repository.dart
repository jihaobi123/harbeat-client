import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final apiRepoProvider = Provider((ref) => ApiRepository());

class TrackDto {
  final int id;
  final String filename;
  final String originalUrl;
  final double? bpm;
  final String? musicKey;
  final String? vocalsUrl;
  final String? drumsUrl;
  final String? bassUrl;
  final String? otherUrl;

  const TrackDto({
    required this.id,
    required this.filename,
    required this.originalUrl,
    this.bpm,
    this.musicKey,
    this.vocalsUrl,
    this.drumsUrl,
    this.bassUrl,
    this.otherUrl,
  });

  factory TrackDto.fromJson(Map<String, dynamic> json) {
    return TrackDto(
      id: json['id'] as int,
      filename: json['filename'] as String,
      originalUrl: json['original_url'] as String,
      bpm: (json['bpm'] as num?)?.toDouble(),
      musicKey: json['music_key'] as String?,
      vocalsUrl: json['vocals_url'] as String?,
      drumsUrl: json['drums_url'] as String?,
      bassUrl: json['bass_url'] as String?,
      otherUrl: json['other_url'] as String?,
    );
  }
}

class CuePointDto {
  final int id;
  final String cueType;
  final double startTime;
  final double? endTime;
  final String? name;

  const CuePointDto({
    required this.id,
    required this.cueType,
    required this.startTime,
    this.endTime,
    this.name,
  });

  factory CuePointDto.fromJson(Map<String, dynamic> json) {
    return CuePointDto(
      id: json['id'] as int,
      cueType: json['cue_type'] as String,
      startTime: (json['start_time'] as num).toDouble(),
      endTime: (json['end_time'] as num?)?.toDouble(),
      name: json['name'] as String?,
    );
  }
}

class ApiRepository {
  final Dio _dio = Dio(BaseOptions(baseUrl: 'http://10.0.2.2:8000'));

  String resolveMediaUrl(String path) {
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    return '${_dio.options.baseUrl}$path';
  }

  Future<List<TrackDto>> fetchTracks() async {
    final response = await _dio.get('/api/music/tracks');
    final items = (response.data['data'] as List<dynamic>? ?? []);
    return items.map((item) => TrackDto.fromJson(item as Map<String, dynamic>)).toList();
  }

  Future<TrackDto> fetchTrack(int trackId) async {
    final response = await _dio.get('/api/music/tracks/$trackId');
    return TrackDto.fromJson(response.data['data'] as Map<String, dynamic>);
  }

  Future<int> startSession({required int userId, required String mode}) async {
    final response = await _dio.post('/api/sessions/start', data: {
      'user_id': userId,
      'mode': mode,
    });
    return response.data['data']['session_id'] as int;
  }

  Future<void> reportEvent(int sessionId, String eventType, String eventValue) async {
    try {
      await _dio.post('/api/sessions/event', data: {
        'session_id': sessionId,
        'event_type': eventType,
        'event_value': eventValue,
        'timestamp': DateTime.now().toIso8601String(),
      });
    } catch (e) {
      print('report event failed: $e');
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
      await _dio.post('/api/music/cues', data: {
        'user_id': userId,
        'track_id': trackId,
        'cue_type': cueType,
        'start_time': startTime,
        'end_time': endTime,
        'name': name,
      });
    } catch (e) {
      print('save cue failed: $e');
    }
  }

  Future<List<CuePointDto>> fetchCuePoints({
    required int userId,
    required int trackId,
  }) async {
    final response = await _dio.get('/api/music/$trackId/cues', queryParameters: {
      'user_id': userId,
    });
    final items = (response.data['data'] as List<dynamic>? ?? []);
    return items.map((item) => CuePointDto.fromJson(item as Map<String, dynamic>)).toList();
  }
}
