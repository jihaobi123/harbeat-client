class AssetManifest {
  final String? planId;
  final int playlistId;
  final List<ManifestTrack> tracks;

  AssetManifest({
    this.planId,
    required this.playlistId,
    required this.tracks,
  });

  factory AssetManifest.fromJson(Map<String, dynamic> json) {
    return AssetManifest(
      planId: json['plan_id'],
      playlistId: json['playlist_id'] ?? 0,
      tracks: (json['tracks'] as List?)
              ?.map((t) => ManifestTrack.fromJson(t))
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'plan_id': planId,
      'playlist_id': playlistId,
      'tracks': tracks.map((t) => t.toJson()).toList(),
    };
  }
}

class ManifestTrack {
  final int songId;
  final String librarySongId;
  final String title;
  final String artist;
  final double durationSec;
  final double bpm;
  final String key;
  final ManifestFiles files;

  ManifestTrack({
    required this.songId,
    required this.librarySongId,
    required this.title,
    required this.artist,
    required this.durationSec,
    required this.bpm,
    required this.key,
    required this.files,
  });

  factory ManifestTrack.fromJson(Map<String, dynamic> json) {
    return ManifestTrack(
      songId: json['song_id'] ?? 0,
      librarySongId: json['library_song_id'] ?? '',
      title: json['title'] ?? '',
      artist: json['artist'] ?? '',
      durationSec: (json['duration_sec'] as num?)?.toDouble() ?? 0.0,
      bpm: (json['bpm'] as num?)?.toDouble() ?? 0.0,
      key: json['key'] ?? '',
      files: ManifestFiles.fromJson(json['files'] ?? {}),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'song_id': songId,
      'library_song_id': librarySongId,
      'title': title,
      'artist': artist,
      'duration_sec': durationSec,
      'bpm': bpm,
      'key': key,
      'files': files.toJson(),
    };
  }
}

class ManifestFiles {
  final ManifestFile original;
  final Map<String, ManifestFile> stems;

  ManifestFiles({
    required this.original,
    required this.stems,
  });

  factory ManifestFiles.fromJson(Map<String, dynamic> json) {
    return ManifestFiles(
      original: ManifestFile.fromJson(json['original'] ?? {}),
      stems: (json['stems'] as Map<String, dynamic>?)?.map(
            (key, value) => MapEntry(key, ManifestFile.fromJson(value)),
          ) ??
          {},
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'original': original.toJson(),
      'stems': stems.map((key, value) => MapEntry(key, value.toJson())),
    };
  }
}

class ManifestFile {
  final String url;
  final int size;
  final String sha256;
  final String? format;

  ManifestFile({
    required this.url,
    required this.size,
    required this.sha256,
    this.format,
  });

  factory ManifestFile.fromJson(Map<String, dynamic> json) {
    return ManifestFile(
      url: json['url'] ?? '',
      size: json['size'] ?? 0,
      sha256: json['sha256'] ?? '',
      format: json['format'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'url': url,
      'size': size,
      'sha256': sha256,
      if (format != null) 'format': format,
    };
  }
}
