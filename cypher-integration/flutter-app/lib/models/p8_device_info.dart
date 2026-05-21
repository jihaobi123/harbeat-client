class DeviceInfo {
  final int ts;
  final double cpuPercent;
  final int memUsedMb;
  final double tempC;
  final double diskFreeGb;
  final int audioXrunCount;
  final bool jetsonReachable;
  final String? wifiSsid;

  DeviceInfo({
    required this.ts,
    required this.cpuPercent,
    required this.memUsedMb,
    required this.tempC,
    required this.diskFreeGb,
    required this.audioXrunCount,
    required this.jetsonReachable,
    this.wifiSsid,
  });

  factory DeviceInfo.fromJson(Map<String, dynamic> json) {
    return DeviceInfo(
      ts: json['ts'] ?? DateTime.now().millisecondsSinceEpoch,
      cpuPercent: (json['cpu_percent'] as num?)?.toDouble() ?? 0.0,
      memUsedMb: json['mem_used_mb'] ?? 0,
      tempC: (json['temp_c'] as num?)?.toDouble() ?? 0.0,
      diskFreeGb: (json['disk_free_gb'] as num?)?.toDouble() ?? 0.0,
      audioXrunCount: json['audio_xrun_count'] ?? 0,
      jetsonReachable: json['jetson_reachable'] ?? true,
      wifiSsid: json['wifi_ssid'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'type': 'device_info',
      'ts': ts,
      'cpu_percent': cpuPercent,
      'mem_used_mb': memUsedMb,
      'temp_c': tempC,
      'disk_free_gb': diskFreeGb,
      'audio_xrun_count': audioXrunCount,
      'jetson_reachable': jetsonReachable,
      'wifi_ssid': wifiSsid,
    };
  }

  bool get isOverheating => tempC > 80;
  bool get hasAudioIssues => audioXrunCount > 0;
  bool get hasWarning => isOverheating || hasAudioIssues || !jetsonReachable;
}
