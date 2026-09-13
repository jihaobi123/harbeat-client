# 第一版跨端集成代码：仅供参考，后续重构

<!-- harbeat:reference-only -->
两个历史集成目录均预计不直接用于第二版：

- [flutter-app](flutter-app/README.md)：旧 Flutter 服务/数据模型，不是已确认的新 APK 源码。
- [rk3588-edge](rk3588-edge/README.md)：旧 RK 服务、音频引擎、资源同步与实体控制实现。

保留这些代码用于了解历史设计和评估可复用片段，不将旧 HTTP/WS、MixPlan、按键或预渲染协议作为第二版要求。新业务 API 和 RK 操作需另行重构、确认。

来源文档中的设备路径、端口和“已完成”状态均为历史记录，不能当作当前部署事实。见 [参考代码说明](../docs/repository/reference-code.md)。
