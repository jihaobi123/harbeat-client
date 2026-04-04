class FangpiSong {
  FangpiSong({
    required this.id,
    required this.title,
    required this.artist,
    required this.url,
    this.source,
  });

  final String id;
  final String title;
  final String artist;
  final String url;
  final String? source;

  factory FangpiSong.fromJson(Map<String, dynamic> json) {
    return FangpiSong(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      url: json['url'] as String? ?? '',
      source: json['source'] as String?,
    );
  }
}

class ParsedPlaylistTrack {
  ParsedPlaylistTrack({
    required this.title,
    required this.artist,
    required this.album,
    required this.duration,
  });

  final String title;
  final String artist;
  final String album;
  final int duration;

  factory ParsedPlaylistTrack.fromJson(Map<String, dynamic> json) {
    return ParsedPlaylistTrack(
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      album: json['album'] as String? ?? '',
      duration: json['duration'] as int? ?? 0,
    );
  }
}

class ParsedPlaylist {
  ParsedPlaylist({
    required this.name,
    required this.platform,
    required this.tracks,
  });

  final String name;
  final String platform;
  final List<ParsedPlaylistTrack> tracks;

  factory ParsedPlaylist.fromJson(Map<String, dynamic> json) {
    return ParsedPlaylist(
      name: json['name'] as String? ?? '',
      platform: json['platform'] as String? ?? '',
      tracks: (json['tracks'] as List<dynamic>? ?? [])
          .map((item) => ParsedPlaylistTrack.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class BatchSearchCandidate {
  BatchSearchCandidate({
    required this.id,
    required this.title,
    required this.artist,
    required this.url,
    this.source,
  });

  final String id;
  final String title;
  final String artist;
  final String url;
  final String? source;

  factory BatchSearchCandidate.fromJson(Map<String, dynamic> json) {
    return BatchSearchCandidate(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      url: json['url'] as String? ?? '',
      source: json['source'] as String?,
    );
  }
}

class BatchSearchResultItem {
  BatchSearchResultItem({
    required this.title,
    required this.artist,
    required this.found,
    required this.candidates,
  });

  final String title;
  final String artist;
  final bool found;
  final List<BatchSearchCandidate> candidates;

  factory BatchSearchResultItem.fromJson(Map<String, dynamic> json) {
    return BatchSearchResultItem(
      title: json['title'] as String? ?? '',
      artist: json['artist'] as String? ?? '',
      found: json['found'] as bool? ?? false,
      candidates: (json['candidates'] as List<dynamic>? ?? [])
          .map((item) => BatchSearchCandidate.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}
