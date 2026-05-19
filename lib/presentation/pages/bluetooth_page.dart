import 'package:flutter/material.dart';
import '../../core/services/bluetooth_service.dart';
import '../../core/utils/logger.dart';

/// 蓝牙设置页面
class BluetoothPage extends StatefulWidget {
  const BluetoothPage({super.key});

  @override
  State<BluetoothPage> createState() => _BluetoothPageState();
}

class _BluetoothPageState extends State<BluetoothPage> {
  final BluetoothService _bluetooth = BluetoothService();
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('蓝牙设备'),
        actions: [
          IconButton(
            icon: Icon(
              _bluetooth.isScanning ? Icons.stop : Icons.refresh,
            ),
            onPressed: () {
              if (_bluetooth.isScanning) {
                _bluetooth.stopScan();
              } else {
                _startScan();
              }
            },
          ),
        ],
      ),
      body: Column(
        children: [
          // 已连接设备
          if (_bluetooth.connectedDevice != null)
            Container(
              margin: const EdgeInsets.all(16),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.green.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.green),
              ),
              child: Row(
                children: [
                  const Icon(Icons.bluetooth_connected, color: Colors.green),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          '已连接',
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.green,
                          ),
                        ),
                        Text(
                          _bluetooth.connectedDevice!.name,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () {
                      _bluetooth.disconnect();
                      setState(() {});
                    },
                  ),
                ],
              ),
            ),
          
          // 扫描状态
          if (_bluetooth.isScanning)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  const SizedBox(width: 12),
                  const Text('正在扫描...'),
                ],
              ),
            ),
          
          // 设备列表
          Expanded(
            child: _bluetooth.devices.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.bluetooth_searching,
                          size: 64,
                          color: Colors.grey[400],
                        ),
                        const SizedBox(height: 16),
                        Text(
                          '点击刷新按钮扫描设备',
                          style: TextStyle(
                            fontSize: 16,
                            color: Colors.grey[600],
                          ),
                        ),
                      ],
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    itemCount: _bluetooth.devices.length,
                    itemBuilder: (context, index) {
                      final device = _bluetooth.devices[index];
                      final isConnected = _bluetooth.connectedDevice?.id == device.id;
                      
                      return Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: ListTile(
                          leading: Icon(
                            isConnected
                                ? Icons.bluetooth_connected
                                : Icons.bluetooth,
                            color: isConnected ? Colors.green : null,
                          ),
                          title: Text(device.name),
                          subtitle: Text('信号强度: ${device.rssi} dBm'),
                          trailing: isConnected
                              ? const Chip(
                                  label: Text('已连接'),
                                  backgroundColor: Colors.green,
                                  labelStyle: TextStyle(color: Colors.white),
                                )
                              : ElevatedButton(
                                  onPressed: () => _connectToDevice(device.id),
                                  child: const Text('连接'),
                                ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
  
  Future<void> _startScan() async {
    try {
      await _bluetooth.startScan();
      if (mounted) {
        setState(() {});
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('扫描失败: $e')),
        );
      }
    }
  }
  
  Future<void> _connectToDevice(String deviceId) async {
    try {
      await _bluetooth.connectToDevice(deviceId);
      if (mounted) {
        setState(() {});
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('连接成功')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('连接失败: $e')),
        );
      }
    }
  }
}
