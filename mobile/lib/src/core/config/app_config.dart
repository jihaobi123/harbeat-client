class AppConfig {
  const AppConfig._();

  // Replace with your computer's LAN IP for local device testing.
  static const String apiBaseUrl = 'http://180.85.206.252:8000';

  static const Duration requestTimeout = Duration(seconds: 20);
}
