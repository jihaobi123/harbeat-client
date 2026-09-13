# 给混音 / RK 协作者：第二版预处理结果入口

本文只规定读取预处理结果，不规定接歌算法、排序策略或实时音频引擎。
代码分支：`archive/music-analysis-history-20260830`；入口：[第二版总览](../../HARBEAT_V2_START_HERE.md)。

## 1. 读取位置

Jetson 的实际根目录：`HARBEAT_PREPROCESS_ROOT=/mnt/nas/harbeat/preprocess`。
离线交付包解压后，把此变量设置为包含 `published/` 的目录即可；不要硬编码 Jetson 绝对路径。

| 范围 | 基础索引 | 人声增补索引 |
|---|---|---|
| EDM 原 8 首冻结交付 | `published/indexes/edm_8_handoff_v1.json` | `published/indexes/edm_8_vocal_activity_v1.json` |
| 全曲库 | `published/indexes/style_library_v1.json` | `published/indexes/style_library_vocal_activity_v1.json` |

这些是存储相对路径，不是已公开的下载 URL。现有方式是获准的只读挂载或离线包；
第二版公网鉴权下载适配层尚待后端实现，不能仅凭本文从任意电脑访问 NAS。
访问授权单独交付，不把 SSH 私钥、NAS 密码或带密钥的共享链接放入 Git。

## 2. 一首歌可以得到什么

| 内容 | 位置 / 字段 | 含义 |
|---|---|---|
| 身份与版本 | 索引 `items[]`、Manifest 的 `track_id` / `analysis_run_id` | 按 ID 和版本关联，不按标题关联 |
| 原曲、风格 | Manifest `source` | 原始文件信息、时长、目录人工风格标签 |
| BPM | `analysis.tempo` | BPM、置信/稳定性及需复核状态 |
| Beat / 小节 | `analysis.beat_grid` | `beats_ms`、`downbeats_ms`、`bars_ms`、拍号 |
| 段落 | `analysis.sections` | 段落区间和标签、来源及回退状态 |
| 其他摘要 | `analysis.key`、`energy`、`drum_groups`、`transition_windows` | 按完整 schema 读取；包含质量限制，不是最终接歌指令 |
| 原曲音频 | `assets.master` | 标准化交付音频，作为公共时间轴 |
| 四轨 | `assets.stems` | vocals / drums / bass / other |
| 五个鼓组子轨 | `assets.drum_stems` | kick / snare / hihat / tom / cymbal；MDX23C 输出，不是拆出独立 808 或开闭镲的承诺 |
| 人声时间段 | 独立 `vocal_activity.json` 的 `intervals[]` | Silero 在已有 vocals 上检测，整数毫秒、`[start_ms,end_ms)` |

完整音频通常为原曲 + 四轨 + 五鼓轨，共 10 个文件；部分失败时不得用空文件代替。
每个已发布资产提供相对 `storage_key`、`sha256`、`size_bytes`、时长、采样率、声道等字段。
精确嵌套、可空性和类型以 [基础 Schema](../../contracts/schemas/analysis/same-style-track-preprocess-v1.schema.json) 和
[人声 Schema](../../contracts/schemas/analysis/vocal-activity-v1.schema.json) 为准。

## 3. 正确消费顺序

1. 读取基础索引，选择目标风格和歌曲。冻结交付直接使用索引的 `manifest_storage_key`；不要再用最新 `latest.json` 替换该 run。
2. 读取对应 run 的 `manifest.json` 和同级 `_SUCCESS.json`，核对身份、schema、Manifest SHA256。
3. 逐项读取 Manifest 指向的资产；校验大小和 SHA256，禁止悄悄转码后仍使用原 hash。
4. 人声增补按 `track_id`、`analysis_run_id`、基础 Manifest SHA256 和 vocals SHA256 精确关联；校验报告和同级成功标记。
5. 全部必要资产验证后才交给混音引擎。保留源报告，不把 `latest` 解析作为播放中的动态行为。

时间从原曲 0 开始。不要删掉前奏再把时间重新从 0 计算；也不要用段落起点替代人声时间基准。
保存歌曲资源时保持 `published/...` 相对结构，离线与 NAS 读取逻辑一致。

## 4. 限制必须透传

- 基础 `degraded` 需检查具体 `quality_flags` 与模块状态，不等于文件一定缺失，也不能抹掉当成完美结果。
- Silero `ready` 表示生成和校验成功；`needs_review=true` 不代表已经人工确认唱歌出现位置。
- `ready` 且 `intervals=[]` 是未检出；失败不是无人声。
- Pair score 有代码/合同，但未完成真实 70%/85% 阈值校准，不作为已验收排序规则。

截至 2026-09-13 本次核对，全库 157 首基础已发布、人声报告 157 首验证通过，共 3088 个检出区间；这是完成数量，不是模型准确率。
EDM 8 首原音频包不自动包含后补人声报告，需要同时取其人声增补包/索引。

详细已有合同：[基础预处理与目录](../same_style_preprocess_handoff_v1.md)、[人声字段与读取示例](../jetson_vocal_activity_handoff_v1.md)。
