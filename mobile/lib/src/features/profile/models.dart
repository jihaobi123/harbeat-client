class UserProfile {
  UserProfile({
    required this.favoriteStyle,
    this.avgBpmPreference,
    this.energyPreference,
    this.vocalPreference,
    this.groovePreference,
  });

  final String favoriteStyle;
  final int? avgBpmPreference;
  final String? energyPreference;
  final String? vocalPreference;
  final String? groovePreference;

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      favoriteStyle: json['favorite_style'] as String? ?? '',
      avgBpmPreference: json['avg_bpm_preference'] as int?,
      energyPreference: json['energy_preference'] as String?,
      vocalPreference: json['vocal_preference'] as String?,
      groovePreference: json['groove_preference'] as String?,
    );
  }
}
