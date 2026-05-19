import 'package:flutter/material.dart';

/// 波形绘制器（占位实现）
class WaveformPainter extends CustomPainter {
  final List<double> waveformData;
  final double position;
  final Color color;
  final Color playedColor;
  
  const WaveformPainter({
    required this.waveformData,
    required this.position,
    this.color = Colors.grey,
    this.playedColor = Colors.blue,
  });
  
  @override
  void paint(Canvas canvas, Size size) {
    // 简单的占位实现
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;
    
    if (waveformData.isEmpty) return;
    
    final barWidth = size.width / waveformData.length;
    final midY = size.height / 2;
    
    for (int i = 0; i < waveformData.length; i++) {
      final x = i * barWidth + barWidth / 2;
      final barHeight = waveformData[i] * size.height * 0.8;
      final isPlayed = (i / waveformData.length) <= position;
      
      paint.color = isPlayed ? playedColor : color;
      canvas.drawLine(
        Offset(x, midY - barHeight / 2),
        Offset(x, midY + barHeight / 2),
        paint,
      );
    }
  }
  
  @override
  bool shouldRepaint(covariant WaveformPainter oldDelegate) {
    return oldDelegate.waveformData != waveformData ||
        oldDelegate.position != position;
  }
}
