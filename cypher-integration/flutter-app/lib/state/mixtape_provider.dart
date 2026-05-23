import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 待混音清单中的一条歌曲（来自本地库 / fangpi 搜索 / 歌单解析）
class MixtapeItem {
  final String? librarySongId;
  final int? songId;
  final String title;
  final String artist;
  final String? musicId;
  final String source; // "library" | "fangpi" | "kuwo" | "url"
  final List<String> tags;
  final String segment; // intro/build/verse/drop/bridge/outro/all

  const MixtapeItem({
    this.librarySongId,
    this.songId,
    required this.title,
    this.artist = 'Unknown',
    this.musicId,
    this.source = 'library',
    this.tags = const [],
    this.segment = 'all',
  });

  String get displayLabel =>
      '$title · $artist${segment == 'all' ? '' : '  [$segment]'}';

  MixtapeItem copyWith({String? segment, List<String>? tags}) => MixtapeItem(
        librarySongId: librarySongId,
        songId: songId,
        title: title,
        artist: artist,
        musicId: musicId,
        source: source,
        tags: tags ?? this.tags,
        segment: segment ?? this.segment,
      );

  Map<String, dynamic> toImportPayload() => {
        'title': title,
        'artist': artist,
        if (musicId != null) 'music_id': musicId,
        'source': source == 'library' ? 'fangpi' : source,
        if (librarySongId != null) 'library_song_id': librarySongId,
        if (songId != null) 'song_id': songId,
        'segment': segment,
        'tags': tags,
      };
}

class MixtapeNotifier extends Notifier<List<MixtapeItem>> {
  @override
  List<MixtapeItem> build() {
    ref.keepAlive();
    return const [];
  }

  void add(MixtapeItem item) {
    // 去重：library_song_id / music_id / title+artist
    final dup = state.any((x) =>
        (item.librarySongId != null && x.librarySongId == item.librarySongId) ||
        (item.musicId != null && x.musicId == item.musicId) ||
        (item.librarySongId == null &&
            item.musicId == null &&
            x.title == item.title &&
            x.artist == item.artist));
    if (dup) return;
    state = [...state, item];
  }

  void addAll(Iterable<MixtapeItem> items) {
    for (final item in items) {
      add(item);
    }
  }

  void removeAt(int index) {
    if (index < 0 || index >= state.length) return;
    final next = [...state];
    next.removeAt(index);
    state = next;
  }

  void clear() => state = const [];

  /// 用新对象替换指定位置的条目（保留顺序）。用于异步导入完成后回填 UUID。
  void replaceAt(int index, MixtapeItem next) {
    if (index < 0 || index >= state.length) return;
    final list = [...state];
    list[index] = next;
    state = list;
  }

  /// 复制条目并附加 UUID / songId，用于在导入回填时方便构造副本。
  static MixtapeItem withIds(
    MixtapeItem src, {
    String? librarySongId,
    int? songId,
  }) => MixtapeItem(
        librarySongId: librarySongId ?? src.librarySongId,
        songId: songId ?? src.songId,
        title: src.title,
        artist: src.artist,
        musicId: src.musicId,
        source: src.source,
        tags: src.tags,
        segment: src.segment,
      );

  void updateSegment(int index, String segment) {
    if (index < 0 || index >= state.length) return;
    final next = [...state];
    next[index] = next[index].copyWith(segment: segment);
    state = next;
  }

  void move(int oldIndex, int newIndex) {
    if (oldIndex < 0 || oldIndex >= state.length) return;
    if (newIndex < 0 || newIndex >= state.length) return;
    final next = [...state];
    final item = next.removeAt(oldIndex);
    next.insert(newIndex, item);
    state = next;
  }
}

final mixtapeProvider =
    NotifierProvider<MixtapeNotifier, List<MixtapeItem>>(() => MixtapeNotifier());
