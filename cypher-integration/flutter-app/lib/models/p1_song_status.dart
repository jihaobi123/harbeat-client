enum AnalysisStatus {
  pending,
  analyzing,
  ready,
  failed,
}

class SongStatus {
  final String songId;
  final String title;
  final String artist;
  final double durationSec;
  final double bpm;
  final String key;
  final AnalysisStatus analysisStatus;
  final String? analysisError;
  final DateTime? analyzedAt;
  final bool hasStems;

  SongStatus({
    required this.songId,
    required this.title,
    required this.artist,
    required this.durationSec,
    required this.bpm,
    required this.key,
    required this.analysisStatus,
    this.analysisError,
    this.analyzedAt,
    this.hasStems = false,
  });

  factory SongStatus.fromJson(Map<String, dynamic> json) {
    return SongStatus(
      songId: json['song_id'] ?? '',
      title: json['title'] ?? '',
      artist: json['artist'] ?? '',
      durationSec: (json['duration_sec'] as num?)?.toDouble() ?? 0.0,
      bpm: (json['bpm'] as num?)?.toDouble() ?? 0.0,
      key: json['key'] ?? '',
      analysisStatus: _parseAnalysisStatus(json['analysis_status']),
      analysisError: json['analysis_error'],
      analyzedAt: json['analyzed_at'] != null
          ? DateTime.parse(json['analyzed_at'])
          : null,
      hasStems: json['has_stems'] ?? false,
    );
  }

  static AnalysisStatus _parseAnalysisStatus(String? status) {
    switch (status) {
      case 'pending':
        return AnalysisStatus.pending;
      case 'analyzing':
      case 'bpm_done':
      case 'beats_done':
      case 'stems_done':
      case 'embed_done':
        return AnalysisStatus.analyzing;
      case 'ready':
      case 'completed':
        return AnalysisStatus.ready;
      case 'failed':
      case 'error':
        return AnalysisStatus.failed;
      default:
        return AnalysisStatus.pending;
    }
  }

  Map<String, dynamic> toJson() {
    return {
      'song_id': songId,
      'title': title,
      'artist': artist,
      'duration_sec': durationSec,
      'bpm': bpm,
      'key': key,
      'analysis_status': analysisStatus.name,
      'analysis_error': analysisError,
      'analyzed_at': analyzedAt?.toIso8601String(),
      'has_stems': hasStems,
    };
  }

  bool get isReady => analysisStatus == AnalysisStatus.ready;
  bool get isAnalyzing => analysisStatus == AnalysisStatus.analyzing;
}
