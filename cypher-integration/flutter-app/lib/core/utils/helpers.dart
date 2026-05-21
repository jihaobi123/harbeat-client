import 'package:logger/logger.dart';

class AppLogger {
  static final Logger _logger = Logger(
    printer: PrettyPrinter(
      methodCount: 0,
      errorMethodCount: 5,
      lineLength: 80,
      colors: true,
      printEmojis: true,
      printTime: true,
    ),
  );

  static void debug(String message) {
    _logger.d(message);
  }

  static void info(String message) {
    _logger.i(message);
  }

  static void warning(String message) {
    _logger.w(message);
  }

  static void error(String message, {Object? error, StackTrace? stackTrace}) {
    _logger.e(message, error: error, stackTrace: stackTrace);
  }

  static void verbose(String message) {
    _logger.v(message);
  }
}

class TimeFormatter {
  static String formatSeconds(int seconds) {
    final minutes = seconds ~/ 60;
    final secs = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}';
  }

  static String formatMilliseconds(int milliseconds) {
    return formatSeconds(milliseconds ~/ 1000);
  }

  static String formatDuration(Duration duration) {
    return formatSeconds(duration.inSeconds);
  }
}

class AppHaptics {
  static Future<void> light() async {
    try {
      await FlutterHaptics.light();
    } catch (e) {}
  }

  static Future<void> medium() async {
    try {
      await FlutterHaptics.medium();
    } catch (e) {}
  }

  static Future<void> heavy() async {
    try {
      await FlutterHaptics.heavy();
    } catch (e) {}
  }

  static Future<void> selection() async {
    try {
      await FlutterHaptics.selection();
    } catch (e) {}
  }
}

class FlutterHaptics {
  static Future<void> light() async {}
  static Future<void> medium() async {}
  static Future<void> heavy() async {}
  static Future<void> selection() async {}
}
