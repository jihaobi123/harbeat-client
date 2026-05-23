import 'dart:math' as math;
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';

/// 客户端实时合成的 5 种 DJ 现场音效：
///   - scratch  搓碟
///   - air_horn 气笛
///   - spinback 倒带
///   - siren    警报
///   - whoosh   嗖声
///
/// 全部为 44.1 kHz 单声道 16-bit PCM，包装成内存 WAV 通过 audioplayers 播放。
/// 不依赖 RK / 不依赖网络，无音乐播放时也能立即出声。
class LocalSfxService {
  LocalSfxService._();
  static final LocalSfxService instance = LocalSfxService._();

  static const int _sr = 44100;
  final Map<String, Uint8List> _cache = {};
  // 每个音效一个独立 player，避免互相截断
  final Map<String, AudioPlayer> _players = {};

  Future<void> play(String id) async {
    final wav = _cache[id] ??= _synthWav(id);
    final p = _players[id] ??= AudioPlayer()..setReleaseMode(ReleaseMode.stop);
    await p.stop();
    await p.play(BytesSource(wav));
  }

  Future<void> disposeAll() async {
    for (final p in _players.values) {
      await p.dispose();
    }
    _players.clear();
  }

  // ───────────── synthesis ─────────────

  Uint8List _synthWav(String id) {
    final samples = switch (id) {
      'scratch' => _genScratch(),
      'air_horn' => _genAirHorn(),
      'spinback' => _genSpinback(),
      'siren' => _genSiren(),
      'whoosh' => _genWhoosh(),
      _ => _genAirHorn(),
    };
    return _wrapWav(samples, _sr);
  }

  // ───── 单个音效的浮点 PCM 生成 ─────

  /// 搓碟：短促噪声片段 + 高通扫频，约 0.28s
  Float32List _genScratch() {
    const dur = 0.28;
    final n = (dur * _sr).round();
    final out = Float32List(n);
    final rand = math.Random(7);
    double y1 = 0, y2 = 0;
    for (int i = 0; i < n; i++) {
      final t = i / _sr;
      // 衰减包络
      final env = math.exp(-t * 7.0) * (1 - math.exp(-t * 80));
      // 白噪声
      final w = rand.nextDouble() * 2 - 1;
      // 高通 (单极一阶): 1500Hz cutoff 模拟扫频感
      final cutoff = 800 + 4000 * (1 - t / dur);
      final alpha = 1.0 / (1.0 + (2 * math.pi * cutoff) / _sr);
      final hp = alpha * (y1 + w - y2);
      y2 = w;
      y1 = hp;
      out[i] = (hp * env * 0.9).clamp(-1.0, 1.0);
    }
    return out;
  }

  /// 气笛：220Hz 锯齿 + 2 倍频，慢起快收，0.55s
  Float32List _genAirHorn() {
    const dur = 0.55;
    final n = (dur * _sr).round();
    final out = Float32List(n);
    const f1 = 220.0;
    const f2 = 330.0;
    for (int i = 0; i < n; i++) {
      final t = i / _sr;
      final att = 1 - math.exp(-t * 60);
      final dec = math.exp(-math.max(0, t - 0.35) * 6);
      final env = att * dec;
      // 锯齿合成 (傅里叶简化)
      double saw = 0;
      for (int k = 1; k <= 6; k++) {
        saw += math.sin(2 * math.pi * f1 * k * t) / k;
      }
      double saw2 = 0;
      for (int k = 1; k <= 4; k++) {
        saw2 += math.sin(2 * math.pi * f2 * k * t) / k;
      }
      final s = (saw * 0.5 + saw2 * 0.35) * env * 0.35;
      out[i] = s.clamp(-1.0, 1.0);
    }
    return out;
  }

  /// 倒带：音高从 1.0× 急速下滑到 0.15×，0.65s
  Float32List _genSpinback() {
    const dur = 0.65;
    final n = (dur * _sr).round();
    final out = Float32List(n);
    const baseFreq = 440.0;
    double phase = 0;
    for (int i = 0; i < n; i++) {
      final t = i / _sr;
      final p = t / dur; // 0..1
      final pitch = 1.0 - p * 0.88; // 1.0 -> 0.12
      final freq = baseFreq * pitch;
      phase += 2 * math.pi * freq / _sr;
      // 三角波感
      final s = math.sin(phase) + 0.4 * math.sin(2 * phase) + 0.15 * math.sin(3 * phase);
      // 后段轻微噪声叠加
      final env = (1 - math.exp(-t * 50)) * math.exp(-t * 2.0);
      out[i] = (s * env * 0.25).clamp(-1.0, 1.0);
    }
    return out;
  }

  /// 警报：600~1200Hz 三角调制，4Hz 速率，1.0s
  Float32List _genSiren() {
    const dur = 1.0;
    final n = (dur * _sr).round();
    final out = Float32List(n);
    double phase = 0;
    for (int i = 0; i < n; i++) {
      final t = i / _sr;
      final mod = math.sin(2 * math.pi * 4.0 * t); // -1..1
      final freq = 900 + 300 * mod;
      phase += 2 * math.pi * freq / _sr;
      final s = math.sin(phase) + 0.25 * math.sin(2 * phase);
      final env = (1 - math.exp(-t * 30)) * (t > 0.85 ? math.exp(-(t - 0.85) * 25) : 1.0);
      out[i] = (s * env * 0.28).clamp(-1.0, 1.0);
    }
    return out;
  }

  /// 嗖声：粉噪声 + 中心频率扫过 (200→4000Hz)，0.6s
  Float32List _genWhoosh() {
    const dur = 0.6;
    final n = (dur * _sr).round();
    final out = Float32List(n);
    final rand = math.Random(13);
    // 一阶共振低通 + 高通组合，cutoff 随时间扫描
    double lp = 0, hp = 0, prev = 0;
    for (int i = 0; i < n; i++) {
      final t = i / _sr;
      final p = t / dur;
      // 钟形包络
      final env = math.exp(-math.pow(p - 0.5, 2).toDouble() * 9.0);
      final w = rand.nextDouble() * 2 - 1;
      final cutoff = 200 + 3800 * p;
      final a = 1.0 - math.exp(-2 * math.pi * cutoff / _sr);
      lp = lp + a * (w - lp);
      hp = lp - prev;
      prev = lp;
      out[i] = (hp * env * 0.9).clamp(-1.0, 1.0);
    }
    return out;
  }

  // ───── WAV 封包 ─────
  Uint8List _wrapWav(Float32List pcm, int sr) {
    final n = pcm.length;
    final dataBytes = n * 2;
    final bb = BytesBuilder(copy: false);
    void w32(int v) =>
        bb.add([v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, (v >> 24) & 0xff]);
    void w16(int v) => bb.add([v & 0xff, (v >> 8) & 0xff]);
    bb.add('RIFF'.codeUnits);
    w32(36 + dataBytes);
    bb.add('WAVE'.codeUnits);
    bb.add('fmt '.codeUnits);
    w32(16); // PCM chunk size
    w16(1); // PCM format
    w16(1); // mono
    w32(sr);
    w32(sr * 2); // byte rate
    w16(2); // block align
    w16(16); // bits per sample
    bb.add('data'.codeUnits);
    w32(dataBytes);
    // 写入 int16 little endian
    final i16 = Int16List(n);
    for (int i = 0; i < n; i++) {
      final v = (pcm[i].clamp(-1.0, 1.0) * 32767).round();
      i16[i] = v;
    }
    bb.add(i16.buffer.asUint8List(i16.offsetInBytes, i16.lengthInBytes));
    return bb.toBytes();
  }
}
