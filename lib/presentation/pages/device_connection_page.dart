import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/config/theme_config.dart';
import '../../core/services/hardware_service.dart';
import '../../core/services/session_service.dart';
import '../../core/utils/logger.dart';
import '../../core/utils/helpers.dart';
import '../../state/providers.dart';

class DeviceConnectionPage extends ConsumerStatefulWidget {
  final void Function(WidgetRef ref)? onConnected;
  
  const DeviceConnectionPage({super.key, this.onConnected});

  @override
  ConsumerState<DeviceConnectionPage> createState() => _DeviceConnectionPageState();
}

class _DeviceConnectionPageState extends ConsumerState<DeviceConnectionPage> {
  final _hardwareService = HardwareService();
  final _pairCodeController = TextEditingController();
  final _ipAddressController = TextEditingController();
  final _deviceNameController = TextEditingController();
  
  ConnectionStatus _status = ConnectionStatus.disconnected;
  bool _isScanning = false;
  bool _showManualAdd = false;
  bool _mockMode = false;
  String? _errorMessage;
  
  List<RK3588DeviceInfo> _devices = [];
  List<RK3588DeviceInfo> _historyDevices = [];
  RK3588DeviceInfo? _selectedDevice;
  String? _deviceToken;

  @override
  void initState() {
    super.initState();
    _loadHistory();
    _scanDevices();
  }

  void _loadHistory() {
    _historyDevices = _hardwareService.connectionHistory;
  }

  @override
  void dispose() {
    _pairCodeController.dispose();
    _ipAddressController.dispose();
    _deviceNameController.dispose();
    super.dispose();
  }

  Future<void> _scanDevices() async {
    setState(() {
      _isScanning = true;
      _status = ConnectionStatus.disconnected;
      _errorMessage = null;
    });

    try {
      final localDevices = await _hardwareService.scanLocalDevices();
      _loadHistory();
      
      setState(() {
        _devices = localDevices;
        _isScanning = false;
        if (localDevices.isNotEmpty) {
          _selectedDevice = localDevices.first;
        }
      });
    } catch (e) {
      setState(() {
        _isScanning = false;
        _errorMessage = '扫描失败: $e';
      });
    }
  }

  Future<void> _addManualDevice() async {
    final ip = _ipAddressController.text.trim();
    final name = _deviceNameController.text.trim();
    
    if (ip.isEmpty) {
      setState(() {
        _errorMessage = '请输入IP地址';
      });
      return;
    }
    
    final deviceName = name.isEmpty ? 'RK3588 Device' : name;
    
    setState(() {
      _isScanning = true;
    });
    
    final newDevice = await _hardwareService.addManualDevice(ip, deviceName);
    
    final isConnected = await _hardwareService.testConnection(newDevice.localUrl);
    
    if (!mounted) return;
    
    setState(() {
      _isScanning = false;
      if (isConnected) {
        _devices.insert(0, newDevice);
        _selectedDevice = newDevice;
        _showManualAdd = false;
        _ipAddressController.clear();
        _deviceNameController.clear();
        _showSnackBar('✅ 连接测试成功！', ThemeConfig.accentSuccess);
      } else {
        _devices.insert(0, newDevice);
        _selectedDevice = newDevice;
        _errorMessage = '连接测试失败，但设备已添加';
        _showSnackBar('⚠️ 设备已添加，但连接测试失败', Colors.orange);
      }
    });
  }

  Future<void> _directConnect() async {
    final ip = _ipAddressController.text.trim();
    if (ip.isEmpty) {
      setState(() { _errorMessage = '请输入IP地址'; });
      return;
    }

    String url = ip.contains(':') ? 'http://$ip' : 'http://$ip:9000';

    setState(() {
      _status = ConnectionStatus.connecting;
      _isScanning = true;
      _errorMessage = null;
    });

    final testOk = await _hardwareService.testConnection(url);
    if (!testOk) {
      if (!mounted) return;
      setState(() {
        _status = ConnectionStatus.error;
        _isScanning = false;
        _errorMessage = '连接测试失败，请检查网络和IP地址';
      });
      _showSnackBar('❌ 连接测试失败', ThemeConfig.accentRed);
      return;
    }

    final device = await _hardwareService.addManualDevice(ip, 'RK3588 Device');
    _selectedDevice = device;

    final confirmResult = await _hardwareService.confirmPairing(
      device.deviceId, '000000', url,
    );

    String token = confirmResult?['device_token'] ?? 'direct-token-${DateTime.now().millisecondsSinceEpoch}';

    final success = await _hardwareService.connectToRK3588(device, token);

    if (!mounted) return;

    if (success) {
      final rkClient = ref.read(rkClientProvider);
      await rkClient.connect(url, token: token);

      setState(() {
        _status = ConnectionStatus.connected;
        _isScanning = false;
        _devices.insert(0, device);
        _showManualAdd = false;
      });

      await SessionService().startSession(
        deviceId: device.deviceId,
        deviceName: device.name,
      );
      widget.onConnected?.call(ref);
      _showSnackBar('✅ RK3588 连接成功！', ThemeConfig.accentSuccess);
    } else {
      setState(() {
        _status = ConnectionStatus.error;
        _isScanning = false;
        _errorMessage = '连接失败，请检查设备状态';
      });
      _showSnackBar('❌ 连接失败', ThemeConfig.accentRed);
    }
  }

  Future<void> _testSelectedDevice() async {
    if (_selectedDevice == null) return;
    
    setState(() {
      _isScanning = true;
    });
    
    final isConnected = await _hardwareService.testConnection(_selectedDevice!.localUrl);
    
    setState(() {
      _isScanning = false;
    });
    
    if (isConnected) {
      _showSnackBar('✅ 连接测试成功！', ThemeConfig.accentSuccess);
    } else {
      _showSnackBar('❌ 连接测试失败，请检查网络', ThemeConfig.accentRed);
    }
  }

  Future<void> _startPairing(RK3588DeviceInfo device) async {
    setState(() {
      _selectedDevice = device;
      _status = ConnectionStatus.connecting;
      _errorMessage = null;
    });

    AppHaptics.medium();
    
    final pairInfo = await _hardwareService.fetchDevicePairInfo(device.localUrl);
    if (pairInfo != null) {
      setState(() {
        _selectedDevice = pairInfo;
        _pairCodeController.clear();
        _status = ConnectionStatus.connecting;
      });
    } else {
      setState(() {
        _status = ConnectionStatus.error;
        _errorMessage = '获取配对信息失败，请确保设备在线';
      });
    }
  }

  Future<void> _confirmPairing() async {
    if (_selectedDevice == null) return;
    
    final pairCode = _pairCodeController.text.trim();
    if (pairCode.isEmpty || pairCode.length != 6) {
      setState(() {
        _errorMessage = '请输入6位配对码';
      });
      return;
    }

    setState(() {
      _status = ConnectionStatus.connecting;
      _errorMessage = null;
    });

    AppHaptics.medium();
    
    final result = await _hardwareService.confirmPairing(
      _selectedDevice!.deviceId,
      pairCode,
      _selectedDevice!.localUrl,
    );

    if (result != null && result['device_token'] != null) {
      _deviceToken = result['device_token'];
      await _connectToDevice(result['device_token']);
    } else {
      setState(() {
        _status = ConnectionStatus.error;
        _errorMessage = '配对失败，请检查配对码';
      });
      _showSnackBar('❌ 配对失败', ThemeConfig.accentRed);
    }
  }

  Future<void> _connectToDevice(String deviceToken) async {
    if (_selectedDevice == null && !_mockMode) return;

    setState(() {
      _status = ConnectionStatus.connecting;
    });

    if (_mockMode) {
      final rkClient = ref.read(rkClientProvider);
      rkClient.setMockMode(true);
      await rkClient.connect(_ipAddressController.text.trim());
      
      setState(() {
        _status = ConnectionStatus.connected;
      });
      await SessionService().startSession(
        deviceId: 'mock-device-001',
        deviceName: '模拟 RK3588',
      );
      widget.onConnected?.call(ref);
      _showSnackBar('✅ 模拟 RK3588 连接成功', ThemeConfig.accentPurple);
      return;
    }

    final success = await _hardwareService.connectToRK3588(_selectedDevice!, deviceToken);

    if (success) {
      // 同步设置 rkClientProvider 的连接状态
      final rkClient = ref.read(rkClientProvider);
      // 使用设备本地URL，因为它一定有效
      await rkClient.connect(_selectedDevice!.localUrl, token: deviceToken);
      
      setState(() {
        _status = ConnectionStatus.connected;
      });
      await SessionService().startSession(
        deviceId: _selectedDevice!.deviceId,
        deviceName: _selectedDevice!.name,
      );
      widget.onConnected?.call(ref);
      _showSnackBar('✅ RK3588 设备连接成功', ThemeConfig.accentSuccess);
    } else {
      setState(() {
        _status = ConnectionStatus.error;
        _errorMessage = '连接失败，请检查网络或设备状态';
      });
      _showSnackBar('❌ 连接失败', ThemeConfig.accentRed);
    }
  }

  Future<void> _disconnect() async {
    AppHaptics.light();
    await SessionService().endSession();
    await _hardwareService.disconnect();
    
    setState(() {
      _status = ConnectionStatus.disconnected;
      _selectedDevice = null;
      _deviceToken = null;
    });
    
    _showSnackBar('设备已断开', ThemeConfig.backgroundSecondary);
  }

  void _showSnackBar(String message, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: color,
        duration: Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ThemeConfig.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: ThemeConfig.backgroundPrimary,
        elevation: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '现场音响连接',
              style: TextStyle(
                color: ThemeConfig.textLight,
                fontSize: ThemeConfig.fontSizeXXLarge,
                fontWeight: FontWeight.bold,
              ),
            ),
            Text(
              '连接 RK3588 边缘设备',
              style: TextStyle(
                color: ThemeConfig.textLight.withOpacity(0.7),
                fontSize: ThemeConfig.fontSizeSmall,
              ),
            ),
          ],
        ),
        actions: [
          if (_status == ConnectionStatus.connected)
            IconButton(
              icon: Icon(Icons.power_settings_new, color: ThemeConfig.accentRed),
              onPressed: _disconnect,
              tooltip: '断开连接',
            ),
          IconButton(
            icon: Icon(Icons.refresh, color: ThemeConfig.textLight),
            onPressed: _isScanning ? null : _scanDevices,
            tooltip: '刷新',
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: EdgeInsets.all(ThemeConfig.spacingMedium),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildStatusCard(),
            SizedBox(height: ThemeConfig.spacingMedium),
            _buildMockModeSection(),
            SizedBox(height: ThemeConfig.spacingMedium),
            
            if (_historyDevices.isNotEmpty && _devices.isNotEmpty) ...[
              _buildHistorySection(),
              SizedBox(height: ThemeConfig.spacingLarge),
            ],
            
            _buildManualAddSection(),
            
            SizedBox(height: ThemeConfig.spacingLarge),
            _buildDeviceListSection(),
            if (_status == ConnectionStatus.connecting && _selectedDevice != null)
              _buildPairingSection(),
            if (_mockMode && _status != ConnectionStatus.connected)
              _buildMockConnectSection(),
          ],
        ),
      ),
    );
  }

  Widget _buildMockModeSection() {
    return Container(
      padding: EdgeInsets.all(ThemeConfig.spacingMedium),
      decoration: BoxDecoration(
        color: ThemeConfig.accentPurple.withOpacity(0.1),
        borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
        border: Border.all(color: ThemeConfig.accentPurple.withOpacity(0.3), width: 2),
      ),
      child: Row(
        children: [
          Switch(
            value: _mockMode,
            onChanged: (value) {
              setState(() {
                _mockMode = value;
              });
              if (_mockMode) {
                final rkClient = ref.read(rkClientProvider);
                rkClient.setMockMode(true);
                _showSnackBar('✅ 已启用模拟模式 - 无需真实设备', ThemeConfig.accentPurple);
              }
            },
            activeColor: ThemeConfig.accentPurple,
          ),
          SizedBox(width: ThemeConfig.spacingSmall),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '模拟 RK3588 模式',
                  style: TextStyle(
                    color: ThemeConfig.accentPurple,
                    fontSize: ThemeConfig.fontSizeMedium,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  '用于测试，无需真实硬件设备',
                  style: TextStyle(
                    color: ThemeConfig.textLight.withOpacity(0.7),
                    fontSize: ThemeConfig.fontSizeSmall,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusCard() {
    IconData icon;
    String text;
    Color color;

    switch (_status) {
      case ConnectionStatus.connected:
        icon = Icons.check_circle;
        text = 'RK3588 已连接';
        color = ThemeConfig.accentSuccess;
        break;
      case ConnectionStatus.connecting:
        icon = Icons.sync;
        text = '连接中...';
        color = ThemeConfig.accentOrange;
        break;
      case ConnectionStatus.error:
        icon = Icons.error;
        text = '连接失败';
        color = ThemeConfig.accentRed;
        break;
      case ConnectionStatus.disconnected:
      default:
        icon = Icons.wifi_off;
        text = '未连接';
        color = ThemeConfig.textLight.withOpacity(0.5);
    }

    return Container(
      padding: EdgeInsets.all(ThemeConfig.spacingLarge),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
        border: Border.all(color: color.withOpacity(0.3), width: 2),
      ),
      child: Row(
        children: [
          _status == ConnectionStatus.connecting
              ? SizedBox(
                  width: 32,
                  height: 32,
                  child: CircularProgressIndicator(strokeWidth: 2, valueColor: AlwaysStoppedAnimation(color)),
                )
              : Icon(icon, color: color, size: 32),
          SizedBox(width: ThemeConfig.spacingMedium),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  text,
                  style: TextStyle(color: color, fontSize: ThemeConfig.fontSizeMedium, fontWeight: FontWeight.bold),
                ),
                if (_status == ConnectionStatus.connected && _selectedDevice != null)
                  Text(
                    '设备: ${_selectedDevice!.name}',
                    style: TextStyle(color: color.withOpacity(0.7), fontSize: ThemeConfig.fontSizeSmall),
                  ),
                if (_errorMessage != null && _status == ConnectionStatus.error)
                  Text(
                    _errorMessage!,
                    style: TextStyle(color: color.withOpacity(0.7), fontSize: ThemeConfig.fontSizeSmall),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHistorySection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(Icons.history, color: ThemeConfig.accentOrange, size: 20),
            SizedBox(width: 8),
            Text(
              '最近连接',
              style: TextStyle(
                color: ThemeConfig.textLight,
                fontSize: ThemeConfig.fontSizeLarge,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
        SizedBox(height: ThemeConfig.spacingMedium),
        ...(_historyDevices.take(3).map((device) => _buildHistoryCard(device))),
      ],
    );
  }

  Widget _buildHistoryCard(RK3588DeviceInfo device) {
    return GestureDetector(
      onTap: () {
        setState(() {
          _selectedDevice = device;
        });
      },
      child: Container(
        margin: EdgeInsets.only(bottom: ThemeConfig.spacingSmall),
        padding: EdgeInsets.all(ThemeConfig.spacingMedium),
        decoration: BoxDecoration(
          color: ThemeConfig.backgroundSecondary.withOpacity(0.2),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
          border: Border.all(color: ThemeConfig.backgroundSecondary.withOpacity(0.3)),
        ),
        child: Row(
          children: [
            Icon(Icons.history, color: ThemeConfig.textLight.withOpacity(0.5), size: 20),
            SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    device.name,
                    style: TextStyle(
                      color: ThemeConfig.textLight,
                      fontSize: ThemeConfig.fontSizeMedium,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    device.localUrl,
                    style: TextStyle(
                      color: ThemeConfig.textLight.withOpacity(0.5),
                      fontSize: ThemeConfig.fontSizeSmall,
                    ),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right, color: ThemeConfig.textLight.withOpacity(0.3)),
          ],
        ),
      ),
    );
  }

  Widget _buildManualAddSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                onPressed: () {
                  setState(() {
                    _showManualAdd = !_showManualAdd;
                  });
                },
                icon: Icon(_showManualAdd ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down),
                label: Text(_showManualAdd ? '收起' : '手动添加设备'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: ThemeConfig.accentGreen,
                  foregroundColor: ThemeConfig.textLight,
                  padding: EdgeInsets.symmetric(vertical: ThemeConfig.spacingMedium),
                ),
              ),
            ),
          ],
        ),
        
        if (_showManualAdd) ...[
          SizedBox(height: ThemeConfig.spacingMedium),
          Container(
            padding: EdgeInsets.all(ThemeConfig.spacingMedium),
            decoration: BoxDecoration(
              color: ThemeConfig.backgroundSecondary.withOpacity(0.2),
              borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
              border: Border.all(color: ThemeConfig.accentOrange.withOpacity(0.3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '手动配置设备',
                  style: TextStyle(
                    color: ThemeConfig.textLight,
                    fontSize: ThemeConfig.fontSizeMedium,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                SizedBox(height: ThemeConfig.spacingMedium),
                
                TextField(
                  controller: _ipAddressController,
                  style: TextStyle(color: ThemeConfig.textLight),
                  decoration: InputDecoration(
                    hintText: '例如: 192.168.1.101',
                    hintStyle: TextStyle(color: ThemeConfig.textLight.withOpacity(0.5)),
                    labelText: '设备IP地址',
                    labelStyle: TextStyle(color: ThemeConfig.textLight.withOpacity(0.7)),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                      borderSide: BorderSide(color: ThemeConfig.backgroundSecondary),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                      borderSide: BorderSide(color: ThemeConfig.backgroundSecondary.withOpacity(0.5)),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                      borderSide: BorderSide(color: ThemeConfig.accentOrange, width: 2),
                    ),
                  ),
                ),
                
                SizedBox(height: ThemeConfig.spacingMedium),
                
                TextField(
                  controller: _deviceNameController,
                  style: TextStyle(color: ThemeConfig.textLight),
                  decoration: InputDecoration(
                    hintText: '自定义设备名称 (可选)',
                    hintStyle: TextStyle(color: ThemeConfig.textLight.withOpacity(0.5)),
                    labelText: '设备名称',
                    labelStyle: TextStyle(color: ThemeConfig.textLight.withOpacity(0.7)),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                      borderSide: BorderSide(color: ThemeConfig.backgroundSecondary),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                      borderSide: BorderSide(color: ThemeConfig.backgroundSecondary.withOpacity(0.5)),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                      borderSide: BorderSide(color: ThemeConfig.accentOrange, width: 2),
                    ),
                  ),
                ),
                
                SizedBox(height: ThemeConfig.spacingMedium),
                
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        onPressed: _isScanning ? null : _addManualDevice,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: ThemeConfig.accentOrange,
                          foregroundColor: ThemeConfig.textLight,
                          padding: EdgeInsets.symmetric(vertical: ThemeConfig.spacingMedium),
                        ),
                        child: _isScanning
                            ? SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation(ThemeConfig.textLight),
                                ),
                              )
                            : Text(
                                '添加并测试',
                                style: TextStyle(fontSize: ThemeConfig.fontSizeMedium, fontWeight: FontWeight.bold),
                              ),
                      ),
                    ),
                    SizedBox(width: ThemeConfig.spacingSmall),
                    Expanded(
                      child: ElevatedButton(
                        onPressed: _isScanning ? null : _directConnect,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: ThemeConfig.accentGreen,
                          foregroundColor: ThemeConfig.textLight,
                          padding: EdgeInsets.symmetric(vertical: ThemeConfig.spacingMedium),
                        ),
                        child: Text(
                          '直接连接',
                          style: TextStyle(fontSize: ThemeConfig.fontSizeMedium, fontWeight: FontWeight.bold),
                        ),
                      ),
                    ),
                  ],
                ),

                SizedBox(height: ThemeConfig.spacingSmall),
                Text(
                  '提示: 默认端口为9000，如果不同请带上端口号',
                  style: TextStyle(
                    color: ThemeConfig.textLight.withOpacity(0.5),
                    fontSize: ThemeConfig.fontSizeSmall,
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildDeviceListSection() {
    if (_devices.isEmpty && !_isScanning) {
      return Center(
        child: Column(
          children: [
            Icon(Icons.wifi_find, size: 64, color: ThemeConfig.textLight.withOpacity(0.3)),
            SizedBox(height: ThemeConfig.spacingMedium),
            Text(
              '未发现设备',
              style: TextStyle(
                color: ThemeConfig.textLight.withOpacity(0.5),
                fontSize: ThemeConfig.fontSizeLarge,
                fontWeight: FontWeight.bold,
              ),
            ),
            SizedBox(height: ThemeConfig.spacingSmall),
            Text(
              '点击右上角刷新搜索，或手动添加设备',
              style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.4)),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      );
    }

    if (_isScanning && _devices.isEmpty) {
      return Center(
        child: Column(
          children: [
            CircularProgressIndicator(valueColor: AlwaysStoppedAnimation(ThemeConfig.accentOrange)),
            SizedBox(height: ThemeConfig.spacingMedium),
            Text(
              '正在扫描局域网...',
              style: TextStyle(
                color: ThemeConfig.textLight.withOpacity(0.7),
                fontSize: ThemeConfig.fontSizeMedium,
              ),
            ),
            SizedBox(height: ThemeConfig.spacingSmall),
            Text(
              '这可能需要几秒钟',
              style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.4)),
            ),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '可用设备 (${_devices.length})',
          style: TextStyle(
            color: ThemeConfig.textLight,
            fontSize: ThemeConfig.fontSizeLarge,
            fontWeight: FontWeight.bold,
          ),
        ),
        SizedBox(height: ThemeConfig.spacingMedium),
        ...(_devices.map((device) => _buildDeviceCard(device))),
      ],
    );
  }

  Widget _buildDeviceCard(RK3588DeviceInfo device) {
    final isSelected = _selectedDevice?.localUrl == device.localUrl;
    
    return GestureDetector(
      onTap: () {
        setState(() {
          _selectedDevice = device;
        });
      },
      child: Container(
        margin: EdgeInsets.only(bottom: ThemeConfig.spacingMedium),
        padding: EdgeInsets.all(ThemeConfig.spacingLarge),
        decoration: BoxDecoration(
          color: isSelected 
              ? ThemeConfig.accentGreen.withOpacity(0.15)
              : ThemeConfig.backgroundSecondary.withOpacity(0.2),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
          border: Border.all(
            color: isSelected ? ThemeConfig.accentGreen : ThemeConfig.backgroundSecondary.withOpacity(0.3),
            width: isSelected ? 2 : 1,
          ),
        ),
        child: Column(
          children: [
            Row(
              children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    color: isSelected ? ThemeConfig.accentGreen : ThemeConfig.backgroundSecondary,
                    borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                  ),
                  child: Icon(
                    Icons.router,
                    color: ThemeConfig.textLight,
                    size: 24,
                  ),
                ),
                SizedBox(width: ThemeConfig.spacingMedium),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        device.name,
                        style: TextStyle(
                          color: ThemeConfig.textLight,
                          fontSize: ThemeConfig.fontSizeMedium,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        device.deviceId,
                        style: TextStyle(
                          color: ThemeConfig.textLight.withOpacity(0.6),
                          fontSize: ThemeConfig.fontSizeSmall,
                        ),
                      ),
                    ],
                  ),
                ),
                if (isSelected)
                  Icon(Icons.check_circle, color: ThemeConfig.accentGreen, size: 24),
              ],
            ),
            SizedBox(height: ThemeConfig.spacingMedium),
            Row(
              children: [
                Expanded(
                  child: Container(
                    padding: EdgeInsets.all(ThemeConfig.spacingSmall),
                    decoration: BoxDecoration(
                      color: ThemeConfig.backgroundSecondary.withOpacity(0.3),
                      borderRadius: BorderRadius.circular(ThemeConfig.radiusSmall),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.network_check, size: 14, color: ThemeConfig.textLight.withOpacity(0.5)),
                        SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            device.localUrl.replaceFirst('http://', ''),
                            style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.6), fontSize: ThemeConfig.fontSizeSmall),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
            SizedBox(height: ThemeConfig.spacingMedium),
            
            Row(
              children: [
                _buildTestButton(device),
                SizedBox(width: ThemeConfig.spacingSmall),
                Expanded(
                  child: GestureDetector(
                    onTap: () => _startPairing(device),
                    child: Container(
                      padding: EdgeInsets.symmetric(vertical: ThemeConfig.spacingMedium),
                      decoration: BoxDecoration(
                        color: ThemeConfig.accentOrange,
                        borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                        boxShadow: ThemeConfig.buttonShadow,
                      ),
                      child: Text(
                        '开始配对',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: ThemeConfig.textLight,
                          fontSize: ThemeConfig.fontSizeMedium,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTestButton(RK3588DeviceInfo device) {
    return GestureDetector(
      onTap: _isScanning ? null : _testSelectedDevice,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: ThemeConfig.spacingMedium, vertical: ThemeConfig.spacingMedium),
        decoration: BoxDecoration(
          color: ThemeConfig.backgroundSecondary.withOpacity(0.5),
          borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.flash_on, size: 18, color: ThemeConfig.accentOrange),
            SizedBox(width: 4),
            Text(
              '测试',
              style: TextStyle(
                color: ThemeConfig.textLight,
                fontSize: ThemeConfig.fontSizeSmall,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPairingSection() {
    return Container(
      margin: EdgeInsets.only(top: ThemeConfig.spacingLarge),
      padding: EdgeInsets.all(ThemeConfig.spacingLarge),
      decoration: BoxDecoration(
        color: ThemeConfig.backgroundSecondary.withOpacity(0.2),
        borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
        border: Border.all(color: ThemeConfig.accentOrange.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '设备配对',
            style: TextStyle(
              color: ThemeConfig.textLight,
              fontSize: ThemeConfig.fontSizeLarge,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: ThemeConfig.spacingMedium),
          Text(
            '请在 RK3588 屏幕上获取配对码，然后输入下方:',
            style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.7)),
          ),
          SizedBox(height: ThemeConfig.spacingLarge),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _pairCodeController,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: ThemeConfig.textLight,
                    fontSize: ThemeConfig.fontSizeLarge,
                    letterSpacing: 8,
                  ),
                  keyboardType: TextInputType.number,
                  maxLength: 6,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: InputDecoration(
                    hintText: '------',
                    hintStyle: TextStyle(color: ThemeConfig.textLight.withOpacity(0.3), letterSpacing: 8),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                      borderSide: BorderSide(color: ThemeConfig.accentOrange),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                      borderSide: BorderSide(color: ThemeConfig.accentOrange, width: 2),
                    ),
                    counterText: '',
                  ),
                ),
              ),
              SizedBox(width: ThemeConfig.spacingMedium),
              GestureDetector(
                onTap: _confirmPairing,
                child: Container(
                  padding: EdgeInsets.symmetric(horizontal: ThemeConfig.spacingLarge, vertical: ThemeConfig.spacingMedium),
                  decoration: BoxDecoration(
                    color: ThemeConfig.accentOrange,
                    borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                    boxShadow: ThemeConfig.buttonShadow,
                  ),
                  child: Text(
                    '确认',
                    style: TextStyle(
                      color: ThemeConfig.textLight,
                      fontSize: ThemeConfig.fontSizeMedium,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMockConnectSection() {
    return Container(
      margin: EdgeInsets.only(top: ThemeConfig.spacingLarge),
      padding: EdgeInsets.all(ThemeConfig.spacingLarge),
      decoration: BoxDecoration(
        color: ThemeConfig.accentPurple.withOpacity(0.15),
        borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
        border: Border.all(color: ThemeConfig.accentPurple.withOpacity(0.4), width: 2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '模拟设备连接',
            style: TextStyle(
              color: ThemeConfig.accentPurple,
              fontSize: ThemeConfig.fontSizeLarge,
              fontWeight: FontWeight.bold,
            ),
          ),
          SizedBox(height: ThemeConfig.spacingMedium),
          Text(
            '无需配对码，一键连接到模拟 RK3588 设备:',
            style: TextStyle(color: ThemeConfig.textLight.withOpacity(0.7)),
          ),
          SizedBox(height: ThemeConfig.spacingLarge),
          GestureDetector(
            onTap: () async {
              await _connectToDevice('mock-token');
            },
            child: Container(
              width: double.infinity,
              padding: EdgeInsets.symmetric(vertical: ThemeConfig.spacingMedium),
              decoration: BoxDecoration(
                color: ThemeConfig.accentPurple,
                borderRadius: BorderRadius.circular(ThemeConfig.radiusMedium),
                boxShadow: ThemeConfig.buttonShadow,
              ),
              child: Text(
                '连接模拟设备',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: ThemeConfig.textLight,
                  fontSize: ThemeConfig.fontSizeMedium,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
