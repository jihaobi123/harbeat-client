import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:mobile/src/app.dart';
import 'package:mobile/src/dj_control_page.dart';
import 'package:mobile/src/live_models.dart';
import 'package:mobile/src/sync_worker_client.dart';

void main() {
  test('default base url is configured', () {
    expect(defaultBaseUrl, isNotEmpty);
  });

  test('token storage key stays stable', () {
    expect(tokenStorageKey, 'harbeat_token');
  });

  test('fast-cut prewarm waits for the automatic pair to be ready', () {
    expect(
      shouldScheduleManualCutPrewarm(
        liveStarted: true,
        isDefaultPreset: true,
        transitionIndex: 1,
        liveIndex: 1,
        defaultPairPrepared: false,
        manualTransitionPending: false,
        targetPreviewPreparing: false,
      ),
      isFalse,
    );
    expect(
      shouldScheduleManualCutPrewarm(
        liveStarted: true,
        isDefaultPreset: true,
        transitionIndex: 1,
        liveIndex: 1,
        defaultPairPrepared: true,
        manualTransitionPending: false,
        targetPreviewPreparing: false,
      ),
      isTrue,
    );
    expect(
      shouldScheduleManualCutPrewarm(
        liveStarted: true,
        isDefaultPreset: true,
        transitionIndex: 1,
        liveIndex: 1,
        defaultPairPrepared: true,
        manualTransitionPending: false,
        targetPreviewPreparing: true,
      ),
      isFalse,
    );
  });

  test('manual transition task parses committed and terminal states', () {
    final scheduled = ManualTransitionTask.fromJson({
      'transition_id': 'manual-test-1',
      'pair_id': 'pair-1',
      'state': 'scheduled',
      'planned_from_at_sec': 15.0,
      'timings': {'rk_sync_sec': 1.25},
    });
    final failed = ManualTransitionTask.fromJson({
      'transition_id': 'manual-test-2',
      'pair_id': 'pair-2',
      'state': 'failed',
      'error': {'code': 'pair_download_failed'},
    });
    final prewarmed = ManualTransitionTask.fromJson({
      'transition_id': 'prewarm-test-1',
      'pair_id': 'pair-3',
      'state': 'prewarmed',
      'result': {'action': 'default_render_prewarmed'},
    });

    expect(scheduled.isCommitted, isTrue);
    expect(scheduled.isTerminal, isFalse);
    expect(scheduled.timings['rk_sync_sec'], 1.25);
    expect(failed.isCommitted, isFalse);
    expect(failed.isTerminal, isTrue);
    expect(failed.error?['code'], 'pair_download_failed');
    expect(prewarmed.isCommitted, isFalse);
    expect(prewarmed.isTerminal, isTrue);
    expect(prewarmed.result?['action'], 'default_render_prewarmed');
  });

  test('RK playback confirms a manual transition without task polling', () {
    final transitionPlayback = LivePlaybackState.fromJson({
      'playing': true,
      'current_song_id': 'render-buffer',
      'position_sec': 1.2,
      'duration_sec': 6.5,
      'last_transition': {
        'transition_id': 'manual-test-3',
        'action': 'default_render_playback',
      },
    });
    final resumedTarget = LivePlaybackState.fromJson({
      'playing': true,
      'current_song_id': 'song-2',
      'position_sec': 42.0,
      'duration_sec': 180.0,
      'last_transition': {'action': 'default_render_resume'},
    });

    expect(
      playbackConfirmsManualTransition(
        transitionPlayback,
        transitionId: 'manual-test-3',
        targetSongId: 'song-2',
      ),
      isTrue,
    );
    expect(
      playbackConfirmsManualTransition(
        resumedTarget,
        transitionId: 'manual-test-3',
        targetSongId: 'song-2',
      ),
      isTrue,
    );
  });

  test('sync recovers when RK accepts a request before POST timeout', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    var planId = '';
    var startedAt = DateTime.fromMillisecondsSinceEpoch(0);
    var postCount = 0;
    final subscription = server.listen((request) async {
      request.response.headers.contentType = ContentType.json;
      if (request.method == 'POST' && request.uri.path == '/sync') {
        postCount += 1;
        final body = jsonDecode(await utf8.decoder.bind(request).join()) as Map;
        planId = body['plan_id']?.toString() ?? '';
        startedAt = DateTime.now();
        await Future<void>.delayed(const Duration(milliseconds: 90));
        try {
          request.response.write(jsonEncode({'ok': true}));
          await request.response.close();
        } catch (_) {
          // The test client intentionally times out before this response.
        }
        return;
      }
      if (request.method == 'GET' && request.uri.path == '/status') {
        final complete =
            DateTime.now().difference(startedAt) >=
            const Duration(milliseconds: 120);
        request.response.write(
          jsonEncode({
            'running': !complete,
            'plan_id': planId,
            'total': 2,
            'downloaded': complete ? 2 : 0,
            'completed': complete ? 2 : 0,
            'percent': complete ? 100 : 0,
            'errors': <String>[],
          }),
        );
        await request.response.close();
        return;
      }
      request.response.statusCode = HttpStatus.notFound;
      await request.response.close();
    });

    try {
      final client = SyncWorkerClient(
        baseUrl: 'http://${server.address.address}:${server.port}',
      );
      final status = await client.syncAndWait(
        tracks: const [],
        defaultMixPairs: const [
          {'pair_id': 'pair-timeout-recovery'},
        ],
        planId: 'rolling-pair-test',
        timeout: const Duration(seconds: 2),
        startRequestTimeout: const Duration(milliseconds: 20),
        statusRequestTimeout: const Duration(milliseconds: 200),
        pollInterval: const Duration(milliseconds: 20),
      );

      expect(status.completedAll, isTrue);
      expect(status.planId, 'rolling-pair-test');
      expect(postCount, 1);
    } finally {
      await subscription.cancel();
      await server.close(force: true);
    }
  });
}
