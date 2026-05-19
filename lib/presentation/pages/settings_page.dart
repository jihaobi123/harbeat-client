import 'package:flutter/material.dart';
import '../../core/config/api_config.dart';
import '../../core/network/api_client.dart';
import '../../data/services/song_service.dart';
import '../../data/services/auth_service.dart';

/// 设置页面
class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  String _currentApiUrl = ApiConfig.baseUrl;
  bool _isOfflineMode = SongService.offlineMode || AuthService.offlineMode;
  
  final List<Map<String, String>> _apiOptions = [
    {
      'name': '生产环境',
      'url': ApiConfig.productionUrl,
      'desc': '阿里云 ECS (8.136.120.255)',
    },
    {
      'name': '开发环境',
      'url': ApiConfig.developmentUrl,
      'desc': '本地 RK3588 (192.168.1.100)',
    },
    {
      'name': '本地测试',
      'url': ApiConfig.localTestUrl,
      'desc': 'Windows 本机 (localhost)',
    },
  ];

  void _switchApi(String url) {
    setState(() {
      ApiConfig.baseUrl = url;
      _currentApiUrl = url;
    });
    
    // 重新初始化 API 客户端
    ApiClient().init();
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('已切换到: $url'),
        backgroundColor: Colors.green,
      ),
    );
  }

  void _toggleOfflineMode(bool value) {
    setState(() {
      _isOfflineMode = value;
      SongService.offlineMode = value;
      AuthService.offlineMode = value;
    });
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(value ? '已启用离线模式' : '已切换到在线模式'),
        backgroundColor: value ? Colors.orange : Colors.blue,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('设置'),
        centerTitle: true,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'API 服务器',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '当前: $_currentApiUrl',
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.grey[600],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          ..._apiOptions.map((option) {
            final isSelected = option['url'] == _currentApiUrl;
            return Card(
              margin: const EdgeInsets.only(bottom: 8),
              color: isSelected ? Colors.blue.shade50 : null,
              child: ListTile(
                leading: Icon(
                  isSelected ? Icons.check_circle : Icons.radio_button_unchecked,
                  color: isSelected ? Colors.blue : Colors.grey,
                ),
                title: Text(option['name']!),
                subtitle: Text(option['desc']!),
                trailing: isSelected 
                    ? const Icon(Icons.check, color: Colors.blue)
                    : null,
                onTap: () => _switchApi(option['url']!),
              ),
            );
          }).toList(),
          const SizedBox(height: 16),
          
          // 离线模式开关
          Card(
            child: SwitchListTile(
              title: const Text('离线模式'),
              subtitle: const Text('使用模拟数据，无需网络连接'),
              value: _isOfflineMode,
              onChanged: _toggleOfflineMode,
              secondary: Icon(
                _isOfflineMode ? Icons.cloud_off : Icons.cloud,
                color: _isOfflineMode ? Colors.orange : Colors.blue,
              ),
            ),
          ),
          
          const SizedBox(height: 16),
          Card(
            color: Colors.amber.shade50,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.info_outline, color: Colors.amber[700]),
                      const SizedBox(width: 8),
                      Text(
                        '提示',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: Colors.amber[700],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    '• 如果看到 "DioException"，说明 API 服务器未运行\n'
                    '• 可以开启"离线模式"使用模拟数据\n'
                    '• 超时时间已设置为 30 秒\n'
                    '• 应用会自动在 API 失败时切换到离线模式',
                    style: TextStyle(fontSize: 13),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
