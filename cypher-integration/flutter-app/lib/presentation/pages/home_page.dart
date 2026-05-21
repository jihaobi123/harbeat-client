import 'package:flutter/material.dart';
import 'library_page.dart';
import 'player_page.dart';
import 'bluetooth_page.dart';
import 'settings_page.dart';

/// 首页（主界面）
class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  int _currentIndex = 0;
  
  final List<Widget> _pages = [
    const LibraryPage(),      // 音乐库
    const PlayerPage(),       // 播放器
    const BluetoothPage(),    // 蓝牙设置
    const SettingsPage(),     // 设置
  ];
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _pages[_currentIndex],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        type: BottomNavigationBarType.fixed,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.library_music),
            label: '音乐库',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.play_circle_filled),
            label: '播放器',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.bluetooth),
            label: '蓝牙',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.settings),
            label: '设置',
          ),
        ],
      ),
    );
  }
}
