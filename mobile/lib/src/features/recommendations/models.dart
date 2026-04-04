class RecommendedSong {
  RecommendedSong({
    required this.songId,
    required this.title,
    required this.artist,
    required this.inLibrary,
  });

  final int songId;
  final String title;
  final String artist;
  final bool inLibrary;

  factory RecommendedSong.fromJson(Map<String, dynamic> json) {
    return RecommendedSong(
      songId: json['song_id'] as int? ?? 0,
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      inLibrary: json['in_library'] as bool? ?? false,
    );
  }
}

class DiscoverSongItem {
  DiscoverSongItem({
    required this.songId,
    required this.title,
    required this.artist,
    this.style,
    this.energy,
    required this.inLibrary,
  });

  final int songId;
  final String title;
  final String artist;
  final String? style;
  final String? energy;
  final bool inLibrary;

  factory DiscoverSongItem.fromJson(Map<String, dynamic> json) {
    return DiscoverSongItem(
      songId: json['song_id'] as int? ?? 0,
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      style: json['style'] as String?,
      energy: json['energy'] as String?,
      inLibrary: json['in_library'] as bool? ?? false,
    );
  }
}

class DiscoverSectionModel {
  DiscoverSectionModel({
    required this.key,
    required this.title,
    required this.icon,
    required this.description,
    required this.songs,
  });

  final String key;
  final String title;
  final String icon;
  final String description;
  final List<DiscoverSongItem> songs;

  factory DiscoverSectionModel.fromJson(Map<String, dynamic> json) {
    return DiscoverSectionModel(
      key: json['key'] as String? ?? '',
      title: json['title'] as String? ?? '',
      icon: json['icon'] as String? ?? '',
      description: json['description'] as String? ?? '',
      songs: (json['songs'] as List<dynamic>? ?? [])
          .map((item) => DiscoverSongItem.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class AddToLibraryResult {
  AddToLibraryResult({
    required this.librarySongId,
    required this.title,
    required this.artist,
  });

  final String librarySongId;
  final String title;
  final String artist;

  factory AddToLibraryResult.fromJson(Map<String, dynamic> json) {
    return AddToLibraryResult(
      librarySongId: json['library_song_id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
    );
  }
}
