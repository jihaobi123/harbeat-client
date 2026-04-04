import 'package:flutter/material.dart';

import '../shell/main_shell.dart';
import 'login_page.dart';

class AuthGate extends StatelessWidget {
  const AuthGate({
    super.key,
    required this.isLoading,
    required this.isAuthenticated,
  });

  final bool isLoading;
  final bool isAuthenticated;

  @override
  Widget build(BuildContext context) {
    if (isLoading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return isAuthenticated ? const MainShell() : const LoginPage();
  }
}
