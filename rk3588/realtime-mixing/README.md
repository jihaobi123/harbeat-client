# RK 实时混音控制接口：戒指、手环接入入口

交付日期：2026-09-15。接口版本：`harbeat.control.v1`。播放实现：`live_dual_deck_vocal_v4_tempo`。

这是当前 RK 实时混音实现的源码交付，不是戒指/手环固件，也不是仅下载本目录就能运行的完整播放器镜像。当前目标是 **EDM 8 首测试集**。

## 负责人先读哪里

1. [给戒指、手环负责人的接入任务](WEARABLE_HANDOFF.md)：职责、动作映射、接入顺序、验收要求。
2. [HTTP 请求和返回说明](CONTROL_INTERFACE_V1.md)：字段格式、去重、错误和时间单位。
3. [变速混音实现与限制](TEMPO_V4_INTEGRATION.md)：入歌变速、双 Deck、候选点、缓存及历史验证。
4. [交付验证记录](VERIFICATION.md)：本次代码测试与此前 RK 验证分开说明。

## 代码放在哪里、在哪里运行

| 文件 | 用途 | 运行位置 |
| --- | --- | --- |
| `control_api.py` | 把网关 HTTP 事件转换为混音命令 | RK；只监听 127.0.0.1:9130 |
| `realtime.py` | 会话、暂停恢复、切歌调度、去重、原速回退 | RK；私有控制 socket |
| `tempo_control.py` | 原曲/准备音频时间映射、变速版本选择 | RK；由 realtime 加载 |
| `prepare_tempo.py` / `prepare_tempo_final.py` | 调用原 vocal_v4，生成独立单曲入歌版本和末曲版本 | RK 准备阶段，不在声卡回调执行 |
| `manage.py` / `install_data.py` / `prepare_realtime.py` | 数据校验、指定交付包导入、原曲别名准备 | RK；部署管理工具，不是硬件接口 |
| `engine-patch/engine.py` | 已部署 Cypher 音频引擎的完整审查快照，含缓存及采样级淡变修改 | RK 的独立 Cypher 工程；不是单文件独立播放器 |
| `install_tempo_engine.py` / `install_engine_patch.py` | 对指定旧版本执行有哈希保护的安装/回退 | RK；管理员维护窗口使用 |
| 两个 `.service` | cat 用户级控制服务；启动服务不自动播放 | RK systemd user |
| `simulate_control.py` | 无硬件时发送相同格式事件 | RK；start/next 等会改变实际播放 |
| `test_*.py` | 单元测试；引擎缓存测试需要 RK 原工程依赖 | 开发机或 RK，按下文分类运行 |
| `verify_*.py` | 实际引擎/PCM 对比诊断 | RK；部分会 seek、发声、暂停，勿在试听/演出中执行 |
| `verification/` | 2026-09-14 已完成验证的文本结果 | 只读证据，不是运行配置 |

当前运行目录为 `/home/cat/harbeat-mixing-v1`，原音频引擎在 `/home/cat/cypher`。手机、戒指、手环不运行这些 Python 混音代码。

## 两个仓库的分工与旧实现边界

本次源码发布在 `jihaobi123/harbeat-client` 的 `rk3588/realtime-mixing/`，分支 `codex/rk-realtime-mixing-v4`。设备固件和既有蓝牙网关仍在 `zhanghangming-gif/harbeat-wear`，没有随本次迁移或修改。

设备仓库的 [engine-ipc-v1（本次核对版本）](https://github.com/zhanghangming-gif/harbeat-wear/blob/0922af956ba23105762334596fa194f1802c818a/contracts/engine-ipc-v1.md) 保持原样：它定义的是 NDJSON Unix socket，不能把本文 HTTP JSON 原样写入旧 socket。本文只记录**新增 HTTP 适配器的实现接口**，不替换设备仓库 contracts 中的共享协议。

若后续需要修改 BLE ACK 或统一共享协议，应在 harbeat-wear 按其 `codex/shared-*` 规则另行人工评审。网关/固件接入也在设备仓库按对应分支提交。本次 harbeat-client 分支仅新增 RK 源码交付和文档入口，不改现有后端、前端、预处理模块，也不自动合并 main。

## 在开发机先检查代码（不连接 RK、不发声）

使用 Python 3.11。在本目录运行：

```bash
python3.11 -m unittest test_deployment test_realtime test_control_api test_tempo test_tempo_control
```

这组 53 项测试（46 项控制/接口/时间映射 + 7 项数据导入安全）只使用标准库与模拟后端，不需要音乐文件、蓝牙或声卡。不要用不加区分的 `test_*.py` 全发现替代：`test_engine_cache.py` 明确依赖 RK 的 `/home/cat/cypher/audio-engine` 及其 Python 音频依赖。

## 已有 RK 的负责人如何开始

只接硬件的开发者**不需要重新部署或替换引擎**。先在 RK 查询：

```bash
curl --fail --max-time 35 http://127.0.0.1:9130/v1/capabilities
curl --fail --max-time 35 http://127.0.0.1:9130/v1/state
systemctl --user status harbeat-realtime-v1 harbeat-control-api-v1 --no-pager
```

应确认 `playback_mode` 是 `live_dual_deck_vocal_v4_tempo`、`tempo_stretch` 是 true、`styles` 含 EDM。若返回错误或原速模式，先交由 RK 管理员核查，不要通过启动另一套播放器绕过。

## 新设备复现的外部依赖（没有随 Git 上传）

| 依赖 | 当前 RK 路径/要求 |
| --- | --- |
| 原 vocal_v4 算法发布包 | `releases/harbeat_mixing_algorithm_vocal_v4_20260913/`；需含 `harbeat/` 和 `scripts/render_edm_bundle_smooth_v3.py` |
| EDM 交付数据及人声补充包 | `data/edm_8_bundle/published/`；含 EDM 主索引、人声索引、manifest、成功标志及音轨 |
| 数据校验结果 | `reports/data_validation.json`，由 `manage.py validate` 生成 |
| 音频别名 | `/home/cat/cypher/cache/rtv1-*`、`rtv2-*`，由准备脚本生成 |
| 单曲变速资产和索引 | `tempo-assets-v1/` 与 `reports/tempo_assets_v1.json` |
| Cypher 工程 | `/home/cat/cypher/audio-engine`，包括 config、dsp、envelope_runner、mix_plan、socket 服务和音效素材；本目录只交付 engine.py 修改快照 |
| Python 与音频运行时 | 控制侧现有 Python 3.11 venv；引擎使用自己的环境及 NumPy/soundfile/sounddevice/PortAudio；准备阶段需要 FFmpeg 的 atempo |

路径相对本节中的 `/home/cat/harbeat-mixing-v1`，除非已写绝对路径。Git 不提供上述音乐、第三方算法发布包、完整 Cypher 工程、私钥或设备登录配置；缺少它们时不能宣称新机器已可运行。

管理员复现顺序：获得原始依赖与数据 → `manage.py validate` → `prepare_realtime.py` → `prepare_tempo.py` → `prepare_tempo_final.py` → 校验并安装引擎修改 → 安装用户服务 → 查询 capabilities → 经确认后进行发声测试。先备份现有配置；不要覆盖正在使用的报告和索引，也不要把服务文件按系统级服务安装。

两个安装脚本对应不同基线，**不是依次无脑运行**。`install_engine_patch.py` 接受原始引擎哈希 `0b9cae7c1edf504b705bd7bea23bc3340db53f5639d6152027603ccc7b812df1`；`install_tempo_engine.py` 接受中间缓存版 `f70ded3fe5f76d5d64991f74ff19809825fd605097aee4a1406463ae147db66f`。当前快照哈希为 `5aa430a104bab79a4b14499740106514e90838e8596e23f847916309f4abfd21`。不匹配就停止并人工合并，不移除校验。脚本使用 assert，请勿以 `python -O` 运行；它们不负责暂停或重启服务。

## 本版明确没有完成的事

- 没有替硬件负责人修改 BLE 接收、物理按键编号、姿态分类器、LED/屏幕提示和 ACK。
- 其他风格资源未接入，只有 EDM 可用；没有 energy、scrub、音量、连续姿态参数接口。
- 当前手势触发已有 one-shot 音效，不是连续手势驱动 DSP，也不是新音效包。
- 无公网鉴权、跨重启持久去重、端到端硬实时延迟保证。
- 实物蓝牙重连、准确率、误触发、整场连续试听仍需联调验收。
