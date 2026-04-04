// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:harbeat_mobile/src/app.dart';
import 'package:harbeat_mobile/src/features/auth/auth_controller.dart';
import 'package:harbeat_mobile/src/features/player/player_controller.dart';

void main() {
  testWidgets('renders HarBeat login shell', (WidgetTester tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AuthController()),
          ChangeNotifierProvider(create: (_) => PlayerController()),
        ],
        child: const HarbeatApp(),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.textContaining('Har'), findsWidgets);
  });
}
