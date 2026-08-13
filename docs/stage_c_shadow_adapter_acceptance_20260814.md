# 阶段 C 影子 Adapter 验收

日期：2026-08-14

## 结果

| 设备 | 业务测试 | 独立进程 health | 生产服务影响 |
|---|---:|---:|---|
| Jetson | 5/5 | 5/5 | 未修改、未重启 |
| RK3588 | 3/3 | 4/4 | 旧 9000/9100 前后均健康 |

Jetson 影子端口为 `18001-18005`。RK 影子端口为 `19000-19002`、`19100`，音频使用 `/tmp/harbeat-shadow-audio.sock`。测试结束后影子进程已退出。

## 已接通

- catalog：歌单 ID 到 LibrarySong ID 的严格解析。
- analysis：`dj_structure_v2` 版本、候选来源和持久化边界。
- planning：default、fast、energy、style 统一 planning facade；快切测试真实使用 v2 候选。
- render：真实 renderer 调用入口及资产目录约束。
- stem：真实 Demucs 调用入口及输入/输出目录约束。
- sync：现有干净 FastAPI 下载/cache adapter。
- edge：v2/v7 请求校验、priority pair-only sync 请求和幂等任务接受。
- audio：独立 Unix socket 的 ping/state 生命周期。
- input：0-9/音量按键语义和 audio wire frame。

## 尚未通过

当前只是影子 adapter 可运行，不是生产切换完成。以下仍需阶段 D-F 验收：真实 PostgreSQL、全库分析、Demucs 四 stem、两首歌真实渲染、新旧输出对比、弱热点同步、RK prepare/schedule、Flutter 与实体按键 E2E。

因此当前保持：

```text
production_ready = false
cleanup_authorized = false
```
