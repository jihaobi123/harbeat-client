# RK3588 实时混音：戒指、手环负责人入口

2026-09-15。发布仓库：`jihaobi123/harbeat-client`，分支：`codex/rk-realtime-mixing-v4`。这是独立评审分支，不代表已合并 main。

## 请先读这三份

1. [负责人接入任务](../rk3588/realtime-mixing/WEARABLE_HANDOFF.md)：你需要完成的按键/手势映射、蓝牙网关转发、状态反馈、去重和实物验收。
2. [完整接口说明](../rk3588/realtime-mixing/CONTROL_INTERFACE_V1.md)：HTTP 地址、动作、JSON 字段、响应、错误、时间单位。
3. [源码及部署说明](../rk3588/realtime-mixing/README.md)：文件作用、RK 路径、外部依赖、测试、安装和回退边界。

## 可直接转发给负责人的说明

混音端已经提供开始/继续、暂停、下一首、风格选择和四个手势音效入口。请在 RK 本机的蓝牙网关中，将手环按键和戒指已识别手势转换成 `harbeat.control.v1` JSON，发送到 `http://127.0.0.1:9130/v1/device-events`。不要在固件中计算切歌点，也不要同时向新旧播放器双发。

当前只接入 EDM 8 首：下一首会在最近的未来候选点执行变速入歌及双路淡变；stop 等同暂停。其他风格和新的音效素材尚未接入。真实蓝牙/姿态识别及设备反馈由你完成，模拟通过不等于实物验收通过。

固件和现有网关仍在 `zhanghangming-gif/harbeat-wear`；本次只把 RK 混音实现与说明发布在 harbeat-client，未修改设备仓库或正在播放的 RK 服务。旧 NDJSON Engine IPC 与此 HTTP 接口不同，适配方法见负责人文档。

## 获取代码

新建一个本地目录拉取，避免覆盖你现有工作：

```bash
git clone --single-branch --branch codex/rk-realtime-mixing-v4 https://github.com/jihaobi123/harbeat-client.git harbeat-rk-mixing-review
cd harbeat-rk-mixing-review/rk3588/realtime-mixing
python3.11 -m unittest test_deployment test_realtime test_control_api test_tempo test_tempo_control
```

53 项单元测试不需要硬件或音乐。音乐/分轨/变速资产、完整原算法发布包和 Cypher 工程没有上传 Git；只做现有 RK 网关联调不必重新安装引擎。访问私有仓库时仍需要 GitHub 仓库读取权限。

历史实机验证和限制见 [验证记录](../rk3588/realtime-mixing/VERIFICATION.md)。本次不负责替硬件负责人修改固件或接入代码。
