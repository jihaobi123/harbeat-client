// GENERATED CODE - DO NOT MODIFY BY HAND
part of 'song.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

Song _$SongFromJson(Map<String, dynamic> json) => Song(
      id: json['id'] as int,
      title: json['title'] as String,
      artist: json['artist'] as String,
      audioUrl: json['audio_url'] as String?,
      duration: (json['duration'] as num?)?.toDouble(),
      bpm: json['bpm'] as int?,
      key: json['key'] as String?,
      energy: json['energy'] as String?,
      style: json['style'] as String?,
      tags: json['tags'] != null 
          ? List<String>.from(json['tags'] as List) 
          : null,
      createdAt: json['created_at'] != null 
          ? DateTime.parse(json['created_at'] as String) 
          : null,
    );

Map<String, dynamic> _$SongToJson(Song instance) => <String, dynamic>{
      'id': instance.id,
      'title': instance.title,
      'artist': instance.artist,
      'audio_url': instance.audioUrl,
      'duration': instance.duration,
      'bpm': instance.bpm,
      'key': instance.key,
      'energy': instance.energy,
      'style': instance.style,
      'tags': instance.tags,
      'created_at': instance.createdAt?.toIso8601String(),
    };
