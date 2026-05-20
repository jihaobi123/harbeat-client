import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../presentation/pages/device_connection_page.dart';
import 'live_page.dart';
import '../presentation/pages/library_page.dart';
import '../presentation/pages/discovery_page.dart';

class MainPage extends ConsumerStatefulWidget {
  const MainPage({super.key});

  @override
  ConsumerState<MainPage> createState() => _MainPageState();
}

class _MainPageState extends ConsumerState<MainPage> {
  int _selectedIndex = 1; // 默认显示 AI DJ控制台

  static const List<Widget> _pages = [
    DeviceConnectionPage(),
    LivePage(),
    LibraryPage(),
    DiscoveryPage(),
  ];

  static const List<BottomNavigationBarItem> _navItems = [
    BottomNavigationBarItem(
      icon: Icon(Icons.bluetooth),
      label: '设备',
    ),
    BottomNavigationBarItem(
      icon: Icon(Icons.music_controller),
      label: 'DJ',
    ),
    BottomNavigationBarItem(
      icon: Icon(Icons.library_music),
      label: '曲库',
    ),
    BottomNavigationBarItem(
      icon: Icon(Icons.explore),
      label: '推荐',
    ),
  ];

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _pages[_selectedIndex],
      bottomNavigationBar: BottomNavigationBar(
        items: _navItems,
        currentIndex: _selectedIndex,
        onTap: _onItemTapped,
        type: BottomNavigationBarType.fixed,
        selectedItemColor: Theme.of(context).colorScheme.primary,
        unselectedItemColor: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
      ),
    );
  }
}