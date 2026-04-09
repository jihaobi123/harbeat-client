import 'package:flutter_test/flutter_test.dart';

import 'package:mobile/src/app.dart';

void main() {
  test('default base url is configured', () {
    expect(defaultBaseUrl, isNotEmpty);
  });

  test('token storage key stays stable', () {
    expect(tokenStorageKey, 'harbeat_token');
  });
}
