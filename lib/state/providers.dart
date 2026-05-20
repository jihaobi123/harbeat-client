import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/api/jetson_client.dart';
import '../core/api/rk_client.dart';
import '../models/models.dart';
import '../core/utils/logger.dart';

final jetsonClientProvider = Provider<JetsonClient>((ref) {
  return JetsonClient();
});

final rkClientProvider = Provider<RkClient>((ref) {
  return RkClient();
});

enum AuthStatus { initial, loading, authenticated, unauthenticated, error }

class AuthState {
  final AuthStatus status;
  final String? token;
  final String? username;
  final String? errorMessage;

  AuthState({
    this.status = AuthStatus.initial,
    this.token,
    this.username,
    this.errorMessage,
  });

  AuthState copyWith({
    AuthStatus? status,
    String? token,
    String? username,
    String? errorMessage,
  }) {
    return AuthState(
      status: status ?? this.status,
      token: token ?? this.token,
      username: username ?? this.username,
      errorMessage: errorMessage ?? this.errorMessage,
    );
  }

  bool get isAuthenticated => status == AuthStatus.authenticated;
}

class AuthNotifier extends Notifier<AuthState> {
  bool _offlineMode = false;

  @override
  AuthState build() {
    return AuthState();
  }

  Future<void> login(String username, String password) async {
    state = state.copyWith(status: AuthStatus.loading);

    try {
      final jetson = ref.read(jetsonClientProvider);
      if (_offlineMode) {
        jetson.setMockMode(true);
        await Future.delayed(const Duration(milliseconds: 800));
        final mockToken = 'mock_token_${DateTime.now().millisecondsSinceEpoch}';
        state = state.copyWith(
          status: AuthStatus.authenticated,
          token: mockToken,
          username: username,
        );
        AppLogger.info('离线登录成功: $username');
        return;
      }

      jetson.setMockMode(false);
      final response = await jetson.login(username, password);

      final token = response['access_token'];
      if (token != null) {
        jetson.setToken(token);
        state = state.copyWith(
          status: AuthStatus.authenticated,
          token: token,
          username: username,
        );
        AppLogger.info('登录成功: $username');
      } else {
        state = state.copyWith(
          status: AuthStatus.error,
          errorMessage: '登录失败：无效的响应',
        );
      }
    } catch (e) {
      AppLogger.warning('后端登录失败，切换到离线模式: $e');
      _offlineMode = true;
      final jetson = ref.read(jetsonClientProvider);
      jetson.setMockMode(true);
      await Future.delayed(const Duration(milliseconds: 800));
      final mockToken = 'mock_token_${DateTime.now().millisecondsSinceEpoch}';
      state = state.copyWith(
        status: AuthStatus.authenticated,
        token: mockToken,
        username: username,
      );
      AppLogger.info('离线登录成功: $username');
    }
  }

  void setOfflineMode(bool enabled) {
    _offlineMode = enabled;
    final jetson = ref.read(jetsonClientProvider);
    jetson.setMockMode(enabled);
  }

  void logout() {
    final jetson = ref.read(jetsonClientProvider);
    jetson.clearToken();
    state = AuthState(status: AuthStatus.unauthenticated);
  }
}

final authProvider = NotifierProvider<AuthNotifier, AuthState>(() {
  return AuthNotifier();
});

final libraryProvider = FutureProvider.family<List<SongStatus>, String?>((ref, query) async {
  final jetson = ref.read(jetsonClientProvider);
  final response = await jetson.getLibrarySongs(
    onlyReady: true,
    query: query,
  );
  final data = response['data'] as List? ?? [];
  return data.map((json) => SongStatus.fromJson(json)).toList();
});

class SetState {
  final int? playlistId;
  final List<SongStatus> songs;
  final MixPlan? mixPlan;
  final AssetManifest? manifest;
  final String? planId;
  final double syncProgress;
  final bool isSyncing;
  final bool isPlanning;

  SetState({
    this.playlistId,
    this.songs = const [],
    this.mixPlan,
    this.manifest,
    this.planId,
    this.syncProgress = 0.0,
    this.isSyncing = false,
    this.isPlanning = false,
  });

  SetState copyWith({
    int? playlistId,
    List<SongStatus>? songs,
    MixPlan? mixPlan,
    AssetManifest? manifest,
    String? planId,
    double? syncProgress,
    bool? isSyncing,
    bool? isPlanning,
  }) {
    return SetState(
      playlistId: playlistId ?? this.playlistId,
      songs: songs ?? this.songs,
      mixPlan: mixPlan ?? this.mixPlan,
      manifest: manifest ?? this.manifest,
      planId: planId ?? this.planId,
      syncProgress: syncProgress ?? this.syncProgress,
      isSyncing: isSyncing ?? this.isSyncing,
      isPlanning: isPlanning ?? this.isPlanning,
    );
  }

  bool get isReadyToLive => mixPlan != null && manifest != null && syncProgress >= 100.0;
}

class SetNotifier extends Notifier<SetState> {
  @override
  SetState build() {
    return SetState();
  }

  void setPlaylist(int playlistId) {
    state = state.copyWith(playlistId: playlistId);
  }

  void addSong(SongStatus song) {
    if (!state.songs.contains(song)) {
      state = state.copyWith(songs: [...state.songs, song]);
    }
  }

  void removeSong(SongStatus song) {
    state = state.copyWith(
      songs: state.songs.where((s) => s.songId != song.songId).toList(),
    );
  }

  Future<void> startPlanning() async {
    if (state.playlistId == null) return;

    state = state.copyWith(isPlanning: true);

    try {
      final jetson = ref.read(jetsonClientProvider);
      await for (final event in jetson.streamMixPlan(state.playlistId!)) {
        if (event['result'] != null) {
          final plan = MixPlan.fromJson(event['result']);
          state = state.copyWith(
            mixPlan: plan,
            planId: plan.planId,
            isPlanning: false,
          );
          AppLogger.info('MixPlan生成完成: ${plan.planId}');
          break;
        }
      }
    } catch (e) {
      AppLogger.error('MixPlan生成失败: $e');
      state = state.copyWith(isPlanning: false);
    }
  }

  Future<void> syncToRK() async {
    if (state.mixPlan == null || state.manifest == null) return;

    state = state.copyWith(isSyncing: true, syncProgress: 0.0);

    try {
      final rk = ref.read(rkClientProvider);
      await rk.loadPlan(state.mixPlan!.toJson(), state.manifest!.toJson());

      rk.watchSyncProgress().listen((progress) {
        state = state.copyWith(syncProgress: progress * 100);
        if (progress >= 1.0) {
          state = state.copyWith(isSyncing: false);
        }
      });
    } catch (e) {
      AppLogger.error('同步到RK失败: $e');
      state = state.copyWith(isSyncing: false);
    }
  }

  void updateSyncProgress(double progress) {
    state = state.copyWith(syncProgress: progress);
    if (progress >= 100.0) {
      state = state.copyWith(isSyncing: false);
    }
  }
}

final setProvider = NotifierProvider<SetNotifier, SetState>(() {
  return SetNotifier();
});

class PlaybackNotifier extends Notifier<PlaybackState?> {
  @override
  PlaybackState? build() {
    _subscribeToPlayback();
    return null;
  }

  void _subscribeToPlayback() {
    final rk = ref.read(rkClientProvider);
    rk.playbackStream.listen((data) {
      state = PlaybackState.fromJson(data);
    });
  }

  Future<void> play(int songId) async {
    final rk = ref.read(rkClientProvider);
    await rk.play(songId);
  }

  Future<void> pause() async {
    final rk = ref.read(rkClientProvider);
    await rk.pause();
  }

  Future<void> resume() async {
    final rk = ref.read(rkClientProvider);
    await rk.resume();
  }

  Future<void> next() async {
    final rk = ref.read(rkClientProvider);
    await rk.next();
  }

  Future<void> seek(double sec) async {
    final rk = ref.read(rkClientProvider);
    await rk.seek(sec);
  }
}

final playbackProvider = NotifierProvider<PlaybackNotifier, PlaybackState?>(() {
  return PlaybackNotifier();
});

class DeviceNotifier extends Notifier<DeviceInfo?> {
  @override
  DeviceInfo? build() {
    _subscribeToDevice();
    return null;
  }

  void _subscribeToDevice() {
    final rk = ref.read(rkClientProvider);
    rk.deviceStream.listen((data) {
      state = DeviceInfo.fromJson(data);
    });
  }
}

final deviceProvider = NotifierProvider<DeviceNotifier, DeviceInfo?>(() {
  return DeviceNotifier();
});

class LiveUiState {
  final int? lastPressedKey;
  final DateTime? lastPressedAt;
  final String? lastPressError;
  final bool isConnected;

  LiveUiState({
    this.lastPressedKey,
    this.lastPressedAt,
    this.lastPressError,
    this.isConnected = false,
  });

  LiveUiState copyWith({
    int? lastPressedKey,
    DateTime? lastPressedAt,
    String? lastPressError,
    bool? isConnected,
  }) {
    return LiveUiState(
      lastPressedKey: lastPressedKey ?? this.lastPressedKey,
      lastPressedAt: lastPressedAt ?? this.lastPressedAt,
      lastPressError: lastPressError ?? this.lastPressError,
      isConnected: isConnected ?? this.isConnected,
    );
  }

  bool isRecentlyPressed(int key) {
    if (lastPressedKey != key || lastPressedAt == null) return false;
    return DateTime.now().difference(lastPressedAt!) < const Duration(milliseconds: 150);
  }
}

class LiveNotifier extends Notifier<LiveUiState> {
  @override
  LiveUiState build() {
    return LiveUiState();
  }

  Future<void> trigger(int key) async {
    state = state.copyWith(
      lastPressedKey: key,
      lastPressedAt: DateTime.now(),
    );

    try {
      final rk = ref.read(rkClientProvider);
      await rk.trigger(key);
      state = state.copyWith(lastPressError: null);
    } catch (e) {
      state = state.copyWith(lastPressError: 'RK无响应');
    }
  }

  void setConnected(bool connected) {
    state = state.copyWith(isConnected: connected);
  }

  void clearError() {
    state = state.copyWith(lastPressError: null);
  }
}

final liveProvider = NotifierProvider<LiveNotifier, LiveUiState>(() {
  return LiveNotifier();
});
