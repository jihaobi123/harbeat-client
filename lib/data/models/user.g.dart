// GENERATED CODE - DO NOT MODIFY BY HAND
part of 'user.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

User _$UserFromJson(Map<String, dynamic> json) => User(
      id: json['id'] as int,
      username: json['username'] as String,
      danceStyle: json['dance_style'] as String?,
      level: json['level'] as String?,
      favoriteStyle: json['favorite_style'] as String?,
    );

Map<String, dynamic> _$UserToJson(User instance) => <String, dynamic>{
      'id': instance.id,
      'username': instance.username,
      'dance_style': instance.danceStyle,
      'level': instance.level,
      'favorite_style': instance.favoriteStyle,
    };
