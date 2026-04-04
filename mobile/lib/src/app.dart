import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/theme/app_theme.dart';
import 'features/auth/auth_controller.dart';
import 'features/auth/auth_gate.dart';

class HarbeatApp extends StatelessWidget {
  const HarbeatApp({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();

    return MaterialApp(
      title: 'HarBeat',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.darkTheme,
      home: AuthGate(
        isLoading: auth.isLoading,
        isAuthenticated: auth.isAuthenticated,
      ),
    );
  }
}
