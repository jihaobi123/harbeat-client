import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/config/theme_config.dart';
import 'routing/app_router.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  SystemChrome.setSystemUIOverlayStyle(
    SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      systemNavigationBarColor: ThemeConfig.backgroundSecondary,
      systemNavigationBarIconBrightness: Brightness.light,
    ),
  );

  runApp(
    const ProviderScope(
      child: HarBeatApp(),
    ),
  );
}

class HarBeatApp extends ConsumerWidget {
  const HarBeatApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'HARIBEAT',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: ThemeConfig.accentGreen,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: ThemeConfig.backgroundPrimary,
        appBarTheme: AppBarTheme(
          backgroundColor: ThemeConfig.backgroundPrimary,
          elevation: 0,
          centerTitle: false,
        ),
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: ThemeConfig.accentGreen,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: ThemeConfig.backgroundPrimary,
      ),
      themeMode: ThemeMode.dark,
      routerConfig: router,
    );
  }
}
