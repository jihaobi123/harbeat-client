/// 简单的歌曲模型
class Song {
  final int id;
  final String title;
  final String artist;
  final String? audioUrl;
  final double? duration; // 秒
  final int? bpm;
  final String? key; // Camelot notation (e.g., "8A")
  final String? energy; // low/medium/high
  final String? style; // hiphop/breaking/popping
  final List<String>? tags;
  final DateTime? createdAt;
  
  const Song({
    required this.id,
    required this.title,
    required this.artist,
    this.audioUrl,
    this.duration,
    this.bpm,
    this.key,
    this.energy,
    this.style,
    this.tags,
    this.createdAt,
  });
  
  /// 格式化时长显示 (mm:ss)
  String get formattedDuration {
    if (duration == null) return '--:--';
    final minutes = duration! ~/ 60;
    final seconds = (duration! % 60).toInt();
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
  
  /// BPM 显示
  String get bpmDisplay => bpm != null ? '${bpm} BPM' : '-- BPM';
}
