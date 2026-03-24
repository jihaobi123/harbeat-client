import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

// 引入我们刚刚写好的 UI 界面
import 'ui/practice_player_screen.dart';

void main() {
  // ProviderScope 是 Riverpod 的核心，必须包在整个 App 的最外层
  runApp(const ProviderScope(child: MyApp()));
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Street DJ MVP',
      // 取消右上角的 Debug 标签，让界面看起来更清爽
      debugShowCheckedModeBanner: false, 
      theme: ThemeData(
        // 把整体主题设置为暗色调，符合街舞和 DJ 的酷炫风格
        brightness: Brightness.dark,
        primarySwatch: Colors.teal,
        scaffoldBackgroundColor: Colors.black,
      ),
      // 👇 这就是所谓的“挂载到根路由”！将首页指定为我们的练习播放器界面
      home: const PracticePlayerScreen(), 
    );
  }
}