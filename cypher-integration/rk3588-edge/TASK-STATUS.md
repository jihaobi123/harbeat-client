# Cypher RK3588 现场盒任务进度

> 代码目录：`~/cypher/`
> 更新日期：2026-05-31

## 当前结论

RK 端已经从“只能播放 demo”推进到可进入真机联调的 MVP：

- `audio-engine` 已支持双 deck、自动 crossfade、stem-aware 与 non-stem 降级。
- `edge-agent` 已提供 REST、WS、`playback_tier`、真实播放状态轮询和启动恢复 current plan。
- `sync-worker` 已实现 original + 4 stems 下载、size / sha256 校验和缺失 stem 报告。
- SessionEvent 已支持批量 flush、失败落盘、启动恢复。
- `cypher.target` 已纳入 audio-engine、edge-agent、input-daemon、sync-worker 四个服务。
- 本地 RK 服务测试已通过，仍需在真实 RK、Jetson 和 USB 声卡上完成端到端验收。

## 已实现

| 模块 | 当前能力 |
|------|----------|
| `audio-engine` | 双 deck、equal-power crossfade、MixPlan 自动切歌、`/xfade` 主动切歌、九键效果、stem FX、EQ、预加载 |
| 转场策略 | stem-aware 与 non-stem fallback；`vocal_handoff`、`bass_swap`、`drum_swap`、`echo_freeze`、`filter`、`slam` 等 preset |
| 转场连续性 | 已移除 `slam` 中间静音洞；`vocal_handoff` 已放缓 B bass 进入，避免双 bass 叠满 |
| 播放状态 | `/state` 与 WS 保留 `playback_tier`，可区分 `basic`、`non_stem`、`stem_aware` |
| `sync-worker` | `POST /sync`、`GET /status`、manifest 展开、并发下载、size / sha256 校验、相对 URL 拼接 |
| SessionEvent | `load`、`play_started`、`crossfade_start/end`、`key_press` 等事件；失败持久化到 `logs/events-buffer.jsonl` |
| Jetson 回源 | 统一读取 `JETSON_BASE_URL`、`JWT_TOKEN`、`HARBEAT_RK_TOKEN`，不再依赖写死局域网地址 |
| systemd | 四个服务与 `cypher.target`；部署脚本和 smoke test 已就绪 |

## 真机验收清单

- [ ] RK 部署前备份 `/home/cat/cypher`。
- [ ] 重启 `cypher.target`，确认四个服务均为 active。
- [ ] `GET /health`、`GET /state` 返回正常，`playback_tier` 能随转场变化。
- [ ] `/load_plan` 下载至少两首歌的 original + 4 stems，size / sha256 全部通过。
- [ ] 连续播放四首歌，确认每次衔接无戛然而止、无长静音、无双 bass 叠满。
- [ ] 用 stems 完整曲目验证键 7/8/9；用缺 stems 曲目验证 non-stem fallback。
- [ ] 手动断开 Jetson 网络，确认 SessionEvent 落盘；恢复网络后确认补发。
- [ ] Jetson 能查询 `load`、`play_started`、`crossfade_start/end`、`key_press`。

## 后续增强

| 项目 | 优先级 | 说明 |
|------|--------|------|
| 真机四首连续试听 | P0 | 当前最重要的听感验收 |
| 真 manifest 压测 | P0 | 关注大文件耗时、失败诊断和缓存完整性 |
| ffmpeg 统一转码策略 | P1 | original 保留服务端格式，stems 仍以 44100 stereo WAV 为主 |
| HTTP Range 断点续传 | P1 | 大曲库同步时降低失败成本 |
| Time-stretch 分级 | P1 | 近 BPM 走 beatmatch，风险 pair 自动退到 echo / cut / slam |
| LPF 扫频优化 | P2 | 从简化滤波升级为更自然的 sweep |
| 云网关 `/edge/rk-001` | P2 | 非现场局域网路径，可后补 |

## 相关文件

| 用途 | 路径 |
|------|------|
| 总览 | `~/cypher/README.md` |
| 联调说明 | `~/cypher/HANDOFF.md` |
| audio-engine | `~/cypher/audio-engine/engine.py` |
| edge-agent | `~/cypher/edge-agent/main.py` |
| sync-worker | `~/cypher/sync-worker/main.py` |
| systemd | `~/cypher/deploy/` |

以仓库代码和真机验收结果为准。
