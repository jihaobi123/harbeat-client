import 'dart:async';

import 'package:audio_service/audio_service.dart';
import 'package:flutter/foundation.dart';
import 'package:just_audio/just_audio.dart';

class PlayerTrack {
  const PlayerTrack({
    required this.title,
    required this.artist,
    this.songId,
    this.originalUrl,
    this.stemUrls = const {},
    this.activeSource = 'original',
    this.bpm,
  });

  final String title;
  final String artist;
  final String? songId;
  final String? originalUrl;
  final Map<String, String> stemUrls;
  final String activeSource;
  final int? bpm;

  String? get sourceUrl {
    if (activeSource == 'original') return originalUrl;
    return stemUrls[activeSource];
  }

  bool get hasPlayableSource => sourceUrl != null && sourceUrl!.isNotEmpty;

  List<String> get availableSources {
    final values = <String>['original'];
    for (final entry in stemUrls.entries) {
      if (entry.value.isNotEmpty) values.add(entry.key);
    }
    return values;
  }

  PlayerTrack copyWith({
    String? title,
    String? artist,
    String? songId,
    String? originalUrl,
    Map<String, String>? stemUrls,
    String? activeSource,
    int? bpm,
  }) {
    return PlayerTrack(
      title: title ?? this.title,
      artist: artist ?? this.artist,
      songId: songId ?? this.songId,
      originalUrl: originalUrl ?? this.originalUrl,
      stemUrls: stemUrls ?? this.stemUrls,
      activeSource: activeSource ?? this.activeSource,
      bpm: bpm ?? this.bpm,
    );
  }
}

class PlayerController extends ChangeNotifier {
  PlayerController() {
    _playerStateSubscription = _audioPlayer.playerStateStream.listen((state) {
      _processingState = state.processingState;
      _isPlaying = state.playing;
      notifyListeners();
    });

    _positionSubscription = _audioPlayer.positionStream.listen((position) {
      _position = position;
      notifyListeners();
    });

    _durationSubscription = _audioPlayer.durationStream.listen((duration) {
      _duration = duration;
      notifyListeners();
    });
  }

  final AudioPlayer _audioPlayer = AudioPlayer();

  PlayerTrack? _currentTrack;
  bool _isPlaying = false;
  bool _isLoading = false;
  ProcessingState _processingState = ProcessingState.idle;
  Duration _position = Duration.zero;
  Duration? _duration;
  String? _errorMessage;

  StreamSubscription<PlayerState>? _playerStateSubscription;
  StreamSubscription<Duration>? _positionSubscription;
  StreamSubscription<Duration?>? _durationSubscription;

  PlayerTrack? get currentTrack => _currentTrack;
  bool get isPlaying => _isPlaying;
  bool get hasTrack => _currentTrack != null;
  bool get isLoading => _isLoading;
  bool get isBuffering => _processingState == ProcessingState.loading || _processingState == ProcessingState.buffering;
  bool get hasPlayableSource => _currentTrack?.hasPlayableSource ?? false;
  Duration get position => _position;
  Duration? get duration => _duration;
  String? get errorMessage => _errorMessage;
  List<String> get availableSources => _currentTrack?.availableSources ?? const ['original'];
  String get activeSource => _currentTrack?.activeSource ?? 'original';

  Future<void> setTrack(PlayerTrack track, {bool play = false}) async {
    _currentTrack = track;
    _errorMessage = null;
    _position = Duration.zero;
    _duration = null;
    notifyListeners();

    await _loadCurrentSource(play: play);
  }

  Future<void> _loadCurrentSource({bool play = false}) async {
    final track = _currentTrack;
    if (track == null) return;

    if (!track.hasPlayableSource) {
      _isPlaying = false;
      notifyListeners();
      return;
    }

    _isLoading = true;
    notifyListeners();

    try {
      await _audioPlayer.setAudioSource(
        AudioSource.uri(
          Uri.parse(track.sourceUrl!),
          tag: MediaItem(
            id: track.songId ?? track.sourceUrl!,
            title: track.title,
            artist: track.artist,
          ),
        ),
      );
      if (play) {
        await _audioPlayer.play();
      }
    } catch (error) {
      _errorMessage = error.toString();
      _isPlaying = false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> seek(Duration position) async {
    try {
      await _audioPlayer.seek(position);
    } catch (error) {
      _errorMessage = error.toString();
      notifyListeners();
    }
  }

  Future<void> switchSource(String source) async {
    final track = _currentTrack;
    if (track == null || source == track.activeSource) return;

    final resumePlayback = _audioPlayer.playing;
    final previousPosition = _position;
    _currentTrack = track.copyWith(activeSource: source);
    notifyListeners();

    await _loadCurrentSource(play: false);
    if (previousPosition > Duration.zero) {
      await seek(previousPosition);
    }
    if (resumePlayback) {
      await togglePlayback();
    }
  }

  void updateStemUrls(Map<String, String> stemUrls) {
    final track = _currentTrack;
    if (track == null) return;
    _currentTrack = track.copyWith(stemUrls: stemUrls);
    notifyListeners();
  }

  Future<void> togglePlayback() async {
    if (_currentTrack == null || !_currentTrack!.hasPlayableSource) return;

    try {
      if (_audioPlayer.playing) {
        await _audioPlayer.pause();
      } else {
        await _audioPlayer.play();
      }
    } catch (error) {
      _errorMessage = error.toString();
      notifyListeners();
    }
  }

  Future<void> stop() async {
    await _audioPlayer.stop();
    _isPlaying = false;
    _position = Duration.zero;
    notifyListeners();
  }

  @override
  void dispose() {
    _playerStateSubscription?.cancel();
    _positionSubscription?.cancel();
    _durationSubscription?.cancel();
    _audioPlayer.dispose();
    super.dispose();
  }
}
