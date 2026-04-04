class AuthSession {
  AuthSession({
    required this.accessToken,
    required this.userId,
    required this.username,
  });

  final String accessToken;
  final int userId;
  final String username;

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      accessToken: json['access_token'] as String? ?? '',
      userId: json['user_id'] as int? ?? 0,
      username: json['username'] as String? ?? '',
    );
  }
}

class UserMe {
  UserMe({
    required this.id,
    required this.username,
    required this.danceStyle,
    required this.level,
    required this.favoriteStyle,
  });

  final int id;
  final String username;
  final String danceStyle;
  final String level;
  final String favoriteStyle;

  factory UserMe.fromJson(Map<String, dynamic> json) {
    return UserMe(
      id: json['id'] as int? ?? 0,
      username: json['username'] as String? ?? '',
      danceStyle: json['dance_style'] as String? ?? '',
      level: json['level'] as String? ?? '',
      favoriteStyle: json['favorite_style'] as String? ?? '',
    );
  }
}
