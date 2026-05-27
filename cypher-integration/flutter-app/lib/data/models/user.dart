/// 简单的用户模型
class User {
  final int id;
  final String username;
  final String? danceStyle; // hiphop/breaking/popping/locking
  final String? level; // beginner/intermediate/advanced
  final String? favoriteStyle;
  
  const User({
    required this.id,
    required this.username,
    this.danceStyle,
    this.level,
    this.favoriteStyle,
  });
}
