# 团队开发文档 · 手机 App（负责人 C）

> 自包含实现规范。基础与协议见 [cypher-feature-flows.md](cypher-feature-flows.md)。

## 0. 你的目标
一个 Flutter App，MC 拿着它走完赛前 → 现场 → 结束。**App 不做任何音频处理**，只发命令、显示状态、按钮触觉反馈。

## 0.1 工作环境
- 仓库：本仓库 `mobile/` 目录（已有 scaffold，branch `origin/codex/dev-flutter-native-mobile`）
- Flutter ≥ 3.19，Dart ≥ 3.3
- 测试机：Android 真机 + iOS 真机（开发周期内只保证 Android）
- 依赖：`dio`、`flutter_riverpod`、`freezed` + `json_serializable`、`web_socket_channel`、`go_router`

## 0.2 任务总览

| # | 任务 | 完工标志 |
|---|---|---|
| T1 | 双链路 API 客户端 | JetsonClient + RkClient 两套，自动选路 |
| T2 | 协议模型生成（freezed） | 协议 P1~P8 全部有 Dart 类 |
| T3 | Riverpod 状态层 | playback / set / sync 三类 Notifier |
| T4 | 4 个页面 + 路由 | 登录 / 赛前 / 现场 / 复盘 |
| T5 | 现场页 3×3 按键栅格 + 触觉反馈 | 按下 < 80ms 看到 UI 闪 + 收到 RK ack |

---

## 项目结构

```
mobile/lib/src/
  api/
    jetson_client.dart       通过 Dio 访问 Jetson（走云端或直连）
    rk_client.dart           访问 RK3588：REST + WebSocket
    api_config.dart          env 切换：local / staging / prod
  models/                    P1~P8 freezed 生成
    song_status.dart
    mix_plan.dart
    asset_manifest.dart
    control_command.dart
    playback_state.dart
    key_event.dart
    session_event.dart
    device_info.dart
  state/
    auth_provider.dart
    library_provider.dart
    set_provider.dart        当前 playlist + MixPlan
    sync_provider.dart       sync 进度
    playback_provider.dart   订阅 RK WS 的 PlaybackState
  pages/
    login_page.dart
    prep_page.dart           赛前
    live_page.dart           现场
    replay_page.dart         复盘
  widgets/
    nine_key_grid.dart
    transport_bar.dart
    sync_progress.dart
    song_tile.dart
  app.dart                   GoRouter + ProviderScope
```

---

## T1 双链路客户端

### JetsonClient
- baseUrl 来自 `api_config.dart`：
  - prod: `https://harbeat.example.com/api`
  - local: `http://192.168.x.x:8000/api`
- 自动 attach `Authorization: Bearer <token>`
- 超时 3s（cypher-feature §5 铁律）
- 失败时通过 Riverpod 全局错误流提示，不抛崩 UI

```dart
class JetsonClient {
  final Dio _dio;
  JetsonClient(this._dio);

  Future<List<SongStatus>> searchLibrary({String q='', bool onlyReady=true}) async {
    final r = await _dio.get('/library/search', queryParameters:{'q':q,'only_ready':onlyReady});
    return (r.data as List).map(SongStatus.fromJson).toList();
  }
  Future<int> uploadSong(File file) async { /* multipart */ }
  Future<SongStatus> getSongStatus(int id) async { ... }
  Stream<MixPlan> djMixStream(int playlistId) async* { /* SSE 解析 */ }
  Future<AssetManifest> getManifest(int playlistId, String planId) async { ... }
  Future<void> uploadSessionEvents(String sid, List<SessionEvent> evts) async { ... }
}
```

SSE 实现：用 Dio `responseType: ResponseType.stream`，按行 `\n\n` 切，解析 `event: ...\ndata: {...}`。

### RkClient
- baseUrl：现场连 LAN（`http://192.168.x.x:9000`），赛前未到现场时通过云网关 `https://harbeat.example.com/edge/<rk_id>`
- 自动探测：启动时并发 ping 两条路径，谁先 200 用谁，每 30s 重选

```dart
class RkClient {
  Future<void> play(int songId, {double startAt=0}) async { ... }
  Future<void> pause() async { ... }
  Future<void> resume() async { ... }
  Future<void> next() async { ... }
  Future<void> seek(double sec) async { ... }
  Future<void> trigger(int key) async { ... }   // key 0~9
  Future<void> loadPlan(MixPlan plan, AssetManifest manifest) async { ... }
  Stream<PlaybackState> watchPlayback() async* { /* WS */ }
  Stream<DeviceInfo> watchDevice() async* { /* 同一 WS 不同 type */ }
  Stream<double> watchSyncProgress() async* { /* 同上 */ }
}
```

WS 实现：`WebSocketChannel.connect`，断线 1s 重连（cypher §5 铁律 3）。

---

## T2 协议模型

每个协议 P1~P8 → 一个 freezed dataclass。例：

```dart
@freezed
class PlaybackState with _$PlaybackState {
  const factory PlaybackState({
    required int ts,
    required bool playing,
    required bool paused,
    required int? currentSongId,
    required double positionSec,
    int? nextSongId,
    double? nextTransitionInSec,
    @Default([]) List<int> activeLoops,
    String? activeStemFx,
  }) = _PlaybackState;
  factory PlaybackState.fromJson(Map<String,dynamic> j) => _$PlaybackStateFromJson(j);
}
```

字段命名遵循 JSON Schema 的 snake_case，用 `@JsonKey(name:'...')` 映射到 camelCase。

`build_runner build --delete-conflicting-outputs` 生成代码。

---

## T3 Riverpod 状态层

```dart
final authProvider = StateNotifierProvider<AuthNotifier, AuthState>(...);
final libraryProvider = AsyncNotifierProvider<LibraryNotifier, List<SongStatus>>(...);
final currentSetProvider = StateNotifierProvider<SetNotifier, SetState>(...);
   // SetState { playlistId, songs, mixPlan, manifest, planId }
final syncProvider = StreamProvider<double>((ref) => ref.read(rkClientProvider).watchSyncProgress());
final playbackProvider = StreamProvider<PlaybackState>((ref) => ref.read(rkClientProvider).watchPlayback());
final deviceProvider = StreamProvider<DeviceInfo>(...);
```

**关键：现场页 UI 不直接调 RkClient，由 LiveNotifier 包一层做 optimistic 更新。**

```dart
class LiveNotifier extends Notifier<LiveUiState> {
  Future<void> trigger(int key) async {
    state = state.copyWith(lastPressedKey: key, lastPressedAt: DateTime.now());
    HapticFeedback.mediumImpact();           // 立刻震动
    try {
      await ref.read(rkClientProvider).trigger(key);  // 后台发请求
    } catch (_) {
      state = state.copyWith(lastPressError: 'RK 无响应');
    }
  }
}
```

---

## T4 4 个页面

### LoginPage
- Form：账号 + 密码
- Submit → `JetsonClient.login()` → 存 token (FlutterSecureStorage) → push `/prep`

### PrepPage（赛前）
布局：上 AppBar、左侧曲库列表（搜索 + 上传按钮）、右侧 Set 区（当前 playlist 列表 + Plan 按钮 + Sync 按钮）。

行为：
- 搜索框 400ms debounce → `searchLibrary(onlyReady:true)`
- 列表 `SongStatus` 显示状态 chip：ready 绿 / 其它灰
- 拖动加入 Set
- 点 "Plan This Set" → `djMixStream` → 逐步替换 `currentSetProvider.mixPlan`，UI 显示当前 plan + score
- 点 "Sync to RK" → `RkClient.loadPlan` → 跳转隐藏 sync 进度条监听 `syncProvider`，到 100% 解锁 "Start Live"
- 点 "Start Live" → push `/live`

### LivePage（现场，最重要）
栅格 3×3 按键 + 顶部 transport bar + 底部 progress。

```
+-------------------------------------------+
| ◀ Set #1   "Track A - Foo"   02:14/03:00  |
| ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ |
| ↓ Next: Track B in 0:46 (equal_power 8s) |
+-------------------------------------------+
| [1 ha!]    [2 scratch] [3 horn]           |
| [4 drum*]  [5 bass*]   [6 hat*]           |
| [7 mute V] [8 solo D]  [9 LPF]            |
+-------------------------------------------+
|   ⏸ Pause/Resume        ⏭ Hold to Next   |
+-------------------------------------------+
```

每个按键：
- 高度尽量大（>= 100dp），手指误触小
- 按下 `trigger(N)` + `HapticFeedback.mediumImpact()` + 高亮闪 150ms
- 4/5/6 在 `playbackProvider.activeLoops` 包含时显示 "ON"
- 7/8/9 在 `activeStemFx` 期间显示倒计时圈

Pause/Resume：根据 `playbackProvider.paused` 切换图标。
Hold to Next：GestureDetector `onLongPressStart` + 500ms 计时器，到时调 `next()`，避免误触。

顶部 transport bar：
- 当前歌 title / artist 从 currentSet 找
- 进度条 = `positionSec / duration`
- "Next in X" = `nextTransitionInSec`

底部 toast：若 `RkClient` 连接断 / device temp > 80℃ / xrun > 0，红色横幅。

### ReplayPage（复盘）
- 选 session → `GET /api/sessions/{id}/events`
- 时间轴显示 key_press / transition 标记
- 最简版本：纯文字 list 即可，图形可后做

---

## T5 现场页 9 键栅格细节

文件：`widgets/nine_key_grid.dart`

```dart
class NineKeyGrid extends ConsumerWidget {
  Widget build(context, ref) {
    final state = ref.watch(liveProvider);
    final playback = ref.watch(playbackProvider).value;
    return GridView.count(
      crossAxisCount: 3, mainAxisSpacing: 8, crossAxisSpacing: 8,
      children: List.generate(9, (i) {
        final key = i+1;
        final active = (key>=4 && key<=6 && playback?.activeLoops.contains(key)==true)
                    || (playback?.activeStemFx == _stemFxNameFor(key));
        return _Btn(
          label: LABELS[key],
          active: active,
          recentlyPressed: state.lastPressedKey == key
                          && DateTime.now().difference(state.lastPressedAt) < Duration(milliseconds: 150),
          onTap: () => ref.read(liveProvider.notifier).trigger(key),
        );
      }),
    );
  }
}
```

`LABELS` 表与 cypher-feature-flows §4.B4 表一致。

---

## 错误 / 离线行为

| 场景 | UI |
|---|---|
| Jetson 不可达 | 赛前页顶 banner "云端断开"；现场页正常 |
| RK 不可达 | 现场页所有按钮变灰 + 红色 banner "现场盒离线"；硬件键仍可用，App 不影响 |
| 上传中 / 分析中歌 | 灰色 + 旋转图标 + 文字 `pending|bpm_done|...` |
| sync 进度 | 不到 100% "Start Live" 禁用 |
| 长按 NEXT 不足 0.5s | toast "长按继续切歌" |

---

## 路由

```dart
final router = GoRouter(routes:[
  GoRoute(path:'/', redirect:(_,__) => hasToken ? '/prep' : '/login'),
  GoRoute(path:'/login', builder: ...),
  GoRoute(path:'/prep',  builder: ...),
  GoRoute(path:'/live',  builder: ...),
  GoRoute(path:'/replay/:sid', builder:...),
]);
```

---

## 完工自检
- [ ] 登录成功跳赛前页，token 持久化
- [ ] 搜索框 debounce 不超过 1 个并发请求
- [ ] "Plan" 30s 内看到第一个 plan 显示
- [ ] "Sync" 进度从 0 到 100，期间 "Start Live" 禁用
- [ ] 现场页 9 键全部按下 < 80ms 看到闪烁 + 触觉
- [ ] 拔 RK 网线，现场页变灰 banner 红，5s 内自动恢复
- [ ] WS 断后自动重连，断网期间 UI 不崩
- [ ] 长按 NEXT 0.5s 才切歌；短按不响应
- [ ] iOS / Android 真机各跑一次 30min 现场，无内存增长
