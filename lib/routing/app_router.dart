import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../pages/login_page.dart';
import '../pages/prep_page.dart';
import '../pages/live_page.dart';
import '../pages/replay_page.dart';
import '../state/providers.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  return GoRouter(
    initialLocation: '/',
    redirect: (context, state) {
      final isAuthenticated = authState.isAuthenticated;
      final isLoginPage = state.matchedLocation == '/login';

      if (!isAuthenticated && !isLoginPage) {
        return '/login';
      }
      if (isAuthenticated && isLoginPage) {
        return '/prep';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/',
        redirect: (_, __) => '/login',
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginPage(),
      ),
      GoRoute(
        path: '/prep',
        builder: (context, state) => const PrepPage(),
      ),
      GoRoute(
        path: '/live',
        builder: (context, state) => const LivePage(),
      ),
      GoRoute(
        path: '/replay/:sessionId',
        builder: (context, state) {
          final sessionId = state.pathParameters['sessionId'];
          return ReplayPage(key: ValueKey(sessionId));
        },
      ),
      GoRoute(
        path: '/replay',
        builder: (context, state) => const ReplayPage(),
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(
        child: Text('页面未找到: ${state.matchedLocation}'),
      ),
    ),
  );
});
