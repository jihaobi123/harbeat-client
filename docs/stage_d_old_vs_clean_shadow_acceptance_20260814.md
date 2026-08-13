# 阶段 D 新旧影子环境对照验收

日期：2026-08-14

## 结论

阶段 D 已通过。clean 环境在不接管生产播放、不写生产数据库、不复制旧 venv/代码/模型缓存的条件下，完成真实 PostgreSQL、全库 v2、四种规划、两首歌 WAV/meta、Demucs 四 stem、热点同步、RK prepare/schedule 和任务幂等验证。

当前仍不是生产交付版：

```text
production_ready = false
cleanup_authorized = false
```

## 验收结果

| 项目 | 结果 | 判定 |
|---|---:|---|
| PostgreSQL 歌单解析 | 23/23 | 通过 |
| 当前全库 v2 + 实体音频 | 43/43 | 通过 |
| 单首真实重算 | 95.187s，62/20 候选 | 通过 |
| 生产 DB 前后摘要 | 完全一致 | 通过 |
| default/fast/energy/style 新旧规划 | 关键字段全部相同 | 通过 |
| 新旧 WAV | SHA256 相同，样本最大差 0 | 通过 |
| clean 热态新 pair 渲染 | 2.571s | 通过 |
| clean 冷启动渲染 | 27.377s | 阶段 E 必须预热 |
| 显式 clean 模型 Demucs | 4/4，10.609s | 通过 |
| 热点 WAV/meta 同步 | 2/2，0.378s | 通过 |
| RK prepare | 0.095s | 通过 |
| RK schedule 提前量 | 10.029s | 通过 |
| RK 触发误差 | 0.002ms | 通过 |
| 重复 schedule | 幂等复用 | 通过 |
| 生产 RK 影响 | 9000 前后均 200 | 无影响 |

## 关键处理

- PostgreSQL 只读；强制重算只写 clean `analysis-overrides`。
- 数据库旧软链接路径在运行时解析为 NAS 真实路径，并强制限制在资产根目录内。
- NVIDIA Torch 使用官方 wheel 与 SHA256；torchaudio 从官方固定提交构建。
- Demucs runner 强制传入显式 `--repo`；测试使用独立 HOME/cache，未读取旧模型缓存。
- RK 影子 schedule 使用本地样本时钟执行，但未创建 sounddevice stream。

## 下一门禁

阶段 E 每次只切换一个服务，并保留旧服务回滚开关。冷启动 render 的 27.377 秒不能直接进入手机快切路径，必须通过长驻 worker 启动预热消除；完成后再做手机和实体按键 E2E。

原始机器证据位于 `deploy/clean-environment/evidence/stage-d/`，汇总结论位于 `deploy/clean-environment/stage-d-acceptance-v0.3.0.json`。
