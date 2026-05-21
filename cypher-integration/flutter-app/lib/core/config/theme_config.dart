import 'package:flutter/material.dart';

/// HARIBEAT 主题配置 - 街头嘻哈风格
class ThemeConfig {
  // ==================== 全局基础色 ====================
  
  /// 主背景色（深灰）- 防反光，适配现场强光
  static const Color backgroundPrimary = Color(0xFF666363);
  
  /// 辅助背景色（浅灰）- 卡片、模块背景
  static const Color backgroundSecondary = Color(0xFF888888);
  
  /// 文字 / 深色元素（纯黑）- 高对比度
  static const Color textDark = Color(0xFF010101);
  
  /// 白色文字 / 高光 - 保证可读性
  static const Color textLight = Color(0xFFFFFFFF);

  // ==================== 功能色（与按钮功能强绑定）====================
  
  /// 主高亮 / 选中态（青绿色）- 选中的歌单、已选按钮
  static const Color accentGreen = Color(0xFF2B756C);
  
  /// 强调行动色（亮橙色）- "炸一点"等强氛围按钮
  static const Color accentOrange = Color(0xFFFF7D00);
  
  /// 警示 / 状态色（红色）- 连接失败、异常提示
  static const Color accentRed = Color(0xFFFF3B30);
  
  /// 连接成功色（绿色）- 设备已连接、播放正常
  static const Color accentSuccess = Color(0xFF34C759);
  
  /// 紫色强调色（模拟模式、特殊按钮）
  static const Color accentPurple = Color(0xFF8B5CF6);

  // ==================== 按钮功能色 ====================
  
  /// 基础播放类按钮（白色底）
  static const Color btnPlayPause = Colors.white;
  
  /// 氛围切换类按钮（橙色高亮）
  static const Color btnAtmosphere = accentOrange;
  
  /// 循环控制类按钮（青绿色）
  static const Color btnLoop = accentGreen;
  
  /// 人声控音类按钮（蓝色）
  static const Color btnVoice = Color(0xFF4A90E2);

  // ==================== 渐变效果 ====================
  
  /// 主背景渐变
  static const LinearGradient backgroundGradient = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [
      Color(0xFF666363),
      Color(0xFF555555),
    ],
  );

  // ==================== 阴影效果 ====================
  
  /// 按钮阴影
  static List<BoxShadow> buttonShadow = [
    BoxShadow(
      color: Colors.black.withOpacity(0.3),
      blurRadius: 8,
      offset: const Offset(0, 4),
    ),
  ];
  
  /// 卡片阴影
  static List<BoxShadow> cardShadow = [
    BoxShadow(
      color: Colors.black.withOpacity(0.2),
      blurRadius: 6,
      offset: const Offset(0, 3),
    ),
  ];

  // ==================== 圆角规范 ====================
  
  /// 小圆角（图标、标签）
  static const double radiusSmall = 8.0;
  
  /// 中圆角（按钮、卡片）
  static const double radiusMedium = 16.0;
  
  /// 大圆角（大按钮、模态框）
  static const double radiusLarge = 24.0;

  // ==================== 间距规范 ====================
  
  /// 小间距
  static const double spacingSmall = 8.0;
  
  /// 中间距
  static const double spacingMedium = 16.0;
  
  /// 大间距
  static const double spacingLarge = 24.0;
  
  /// 超大间距
  static const double spacingXLarge = 32.0;

  // ==================== 字体规范 ====================
  
  /// 超小号文字（说明文字）
  static const double fontSizeXS = 12.0;
  
  /// 小号文字（次要信息）
  static const double fontSizeSmall = 14.0;
  
  /// 中号文字（正文）
  static const double fontSizeMedium = 16.0;
  
  /// 大号文字（标题）
  static const double fontSizeLarge = 20.0;
  
  /// 超大号文字（按钮文字）
  static const double fontSizeXLarge = 24.0;
  
  /// 特大号文字（主标题）
  static const double fontSizeXXLarge = 32.0;
}
