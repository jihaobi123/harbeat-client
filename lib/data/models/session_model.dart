import 'package:flutter/material.dart';
import 'package:harbeat_app/core/config/theme_config.dart';

class SessionModel {
  final String id;
  final String deviceId;
  final String deviceName;
  final DateTime startTime;
  DateTime? endTime;
  final List<SessionEvent> events;
  final String? playlistId;
  final String? playlistName;

  SessionModel({
    required this.id,
    required this.deviceId,
    required this.deviceName,
    required this.startTime,
    this.endTime,
    this.events = const [],
    this.playlistId,
    this.playlistName,
  });

  int get totalEvents => events.length;
  Duration get duration => endTime != null ? endTime!.difference(startTime) : Duration.zero;
  String get durationText {
    if (endTime == null) return '进行中';
    final diff = duration;
    if (diff.inHours > 0) {
      return '${diff.inHours}小时${diff.inMinutes % 60}分钟';
    }
    return '${diff.inMinutes}分钟';
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'deviceId': deviceId,
      'deviceName': deviceName,
      'startTime': startTime.toIso8601String(),
      'endTime': endTime?.toIso8601String(),
      'events': events.map((e) => e.toJson()).toList(),
      'playlistId': playlistId,
      'playlistName': playlistName,
    };
  }

  factory SessionModel.fromJson(Map<String, dynamic> json) {
    return SessionModel(
      id: json['id'] as String,
      deviceId: json['deviceId'] as String,
      deviceName: json['deviceName'] as String,
      startTime: DateTime.parse(json['startTime'] as String),
      endTime: json['endTime'] != null ? DateTime.parse(json['endTime'] as String) : null,
      events: (json['events'] as List<dynamic>?)?.map((e) => SessionEvent.fromJson(e as Map<String, dynamic>)).toList() ?? [],
      playlistId: json['playlistId'] as String?,
      playlistName: json['playlistName'] as String?,
    );
  }

  SessionModel copyWith({
    String? id,
    String? deviceId,
    String? deviceName,
    DateTime? startTime,
    DateTime? endTime,
    List<SessionEvent>? events,
    String? playlistId,
    String? playlistName,
  }) {
    return SessionModel(
      id: id ?? this.id,
      deviceId: deviceId ?? this.deviceId,
      deviceName: deviceName ?? this.deviceName,
      startTime: startTime ?? this.startTime,
      endTime: endTime ?? this.endTime,
      events: events ?? this.events,
      playlistId: playlistId ?? this.playlistId,
      playlistName: playlistName ?? this.playlistName,
    );
  }
}

class SessionEvent {
  final String id;
  final String type;
  final DateTime timestamp;
  final Map<String, dynamic>? data;
  final String description;

  SessionEvent({
    required this.id,
    required this.type,
    required this.timestamp,
    this.data,
    required this.description,
  });

  String get timeText => '${timestamp.hour.toString().padLeft(2, '0')}:${timestamp.minute.toString().padLeft(2, '0')}';

  Color get eventColor {
    switch (type) {
      case 'play':
      case 'start_session':
        return ThemeConfig.accentSuccess;
      case 'pause':
      case 'stop':
      case 'emergency_stop':
        return ThemeConfig.accentRed;
      case 'next':
      case 'switch_style':
        return ThemeConfig.accentOrange;
      case 'trigger_sfx':
        return ThemeConfig.accentGreen;
      default:
        return ThemeConfig.textLight.withOpacity(0.6);
    }
  }

  IconData get eventIcon {
    switch (type) {
      case 'play':
        return Icons.play_arrow;
      case 'pause':
        return Icons.pause;
      case 'stop':
      case 'emergency_stop':
        return Icons.stop;
      case 'next':
        return Icons.skip_next;
      case 'switch_style':
        return Icons.music_note;
      case 'trigger_sfx':
        return Icons.spatial_audio_off;
      case 'start_session':
        return Icons.start;
      case 'end_session':
        return Icons.stop_circle;
      default:
        return Icons.event;
    }
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'type': type,
      'timestamp': timestamp.toIso8601String(),
      'data': data,
      'description': description,
    };
  }

  factory SessionEvent.fromJson(Map<String, dynamic> json) {
    return SessionEvent(
      id: json['id'] as String,
      type: json['type'] as String,
      timestamp: DateTime.parse(json['timestamp'] as String),
      data: json['data'] as Map<String, dynamic>?,
      description: json['description'] as String,
    );
  }
}
