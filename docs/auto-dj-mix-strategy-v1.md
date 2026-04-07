# HarBeat 自动 DJ 混音策略（可复用落地版 v1）

本文档描述当前线上可用的一版策略：
- 实时模式：用于预览与交互（Seamless Player）。
- 离线模式：输出单个成片 `final_mix.wav/mp3`。
- 过渡策略：先规则化（rule-based）+ stem-aware，不依赖 GAN。

## 1. 目标与边界

目标：
- 自动选歌、自动排歌、自动过渡。
- 过渡点尽量按拍点/乐句，避免硬切。
- 当 stem 不可用时自动降级到普通 crossfade，保证可用性。

边界：
- 当前版本以稳定可跑为优先，不做端到端生成式重混。
- 实时模式是“预览引擎”；高质量导出走离线渲染。

## 2. 系统分层（当前实现）

1. 选歌与基础处理
- 入口：`/api/playlists/generate-dj-mix-plan`
- 先基于 `style / duration / playlist / quality / diversity` 选出候选歌。
- 产出 `processed_files`（可播放音频路径）和 `playlist`。

2. 转场规划（Transition Planner）
- 文件：`app/modules/playlists/transition_planner.py`
- 核心能力：
  - BPM 兼容评分 + tempo ratio（含半倍/双倍拍容错）
  - Camelot 关系（same/relative/neighbor/clash）
  - 结构化过渡点（exit/entry beat、phase_anchor、crossfade_sec）
  - 过渡技术标签（`phrase_crossfade / eq_bass_swap / echo_style_cross`）
  - 自动化轨迹 `fx_automation`

3. 实时播放（Seamless Preview）
- 文件：`web/src/components/SeamlessPlayer.tsx`
- 核心能力：
  - 双 Deck（A/B）无缝衔接
  - 按 `transition_plan` 触发过渡
  - UI 显示 `Next mix in ...` 倒计时
  - 拖动进度条后可重新触发过渡逻辑（seek 后重启 tick）

4. 离线渲染（Final Mix Export）
- 入口：`/api/playlists/generate-dj-offline-mix`
- 文件：`app/modules/playlists/offline_renderer.py`
- 产出：`data/music-files/shared/mixes/final_mix_<user>_<ts>.wav|mp3`

## 3. 当前生产参数（默认建议）

混音计划参数：
- `strict_harmonic`: 可选（默认关闭）
- `max_tempo_shift`: `0.08`
- `diversity`: `0.35`
- `candidate_window`: `4`
- `random_seed`: 前端用 `Date.now()`，避免每次结果完全一致

离线导出参数（当前前端默认）：
- `output_format`: `wav`（优先稳定，避免 mp3 编码器缺失）
- `stem_aware`: `true`
- `auto_separate_stems`: `false`（避免导出耗时失控）
- `max_auto_stem_tracks`: `0`
- `stem_separation_timeout_sec`: `90`

## 4. Stem-aware 规则（当前已落地）

过渡重叠区内，若两首歌都具备可用 stems（至少 2 轨）：

1. `bass_swap`
- 出歌 bass 更早退出，进歌 bass 延后进入。
- 降低低频打架，增强“换歌”感。

2. `vocal_ducking`
- 过渡区压低出歌 vocals，进歌 vocals 渐进放开。
- 降低人声冲突与歌词重叠噪感。

3. `drum_soft_entry`
- 当 tempo 修正幅度较大（`|tempo_ratio-1|>0.04`）时，进歌鼓组前半段软启动。
- 避免节奏感突兀。

若 stem 不可用：
- 自动回退到 equal-power crossfade（不中断导出）。

## 5. 降级与容错策略

1. 无 stems
- 告警：`songs without usable stems, fallback to normal crossfade`
- 行为：继续渲染，不失败。

2. Demucs 路径字符问题（Windows）
- 已实现 ASCII 安全文件名重试。
- 场景：文件名含特殊空格/中文时，首次 demucs 失败会自动重试。

3. mp3 编码器缺失
- 自动探测 `libmp3lame/libshine/mp3`。
- `both` 模式下若 mp3 不可用，保留 wav 并返回警告。

4. 实时模式无倒计时/不触发转场
- 已修复 tick 循环触发链路：播放、跳曲、seek 后都会重新进入过渡判定。

## 6. 复用步骤（每次发版照做）

1. 后端
- 确保路由可用：
  - `POST /api/playlists/generate-dj-mix-plan`
  - `POST /api/playlists/generate-dj-offline-mix`
  - `GET /api/stream/mixes/{filename}`

2. 前端
- 构建 `web/dist`。
- 强刷缓存（`Ctrl+F5`）后验证：
  - 实时播放器出现 `Next mix in ...`
  - 拖动进度条可提前触发过渡
  - 离线导出可生成 `final_mix.wav`

3. 验收指标（最小集合）
- 同一参数多次生成：顺序不再完全固定（seed 变化时）
- 过渡不等待整首播完才切
- 有 stems 的歌能出现 `stem_rule_events`
- 无 stems 时仅警告，不阻塞导出

## 7. 关键代码定位

后端：
- `app/modules/playlists/service.py`
- `app/modules/playlists/transition_planner.py`
- `app/modules/playlists/offline_renderer.py`
- `app/modules/playlists/router.py`
- `app/modules/playlists/schemas.py`
- `app/modules/stream/router.py`

前端：
- `web/src/components/SessionPanel.tsx`
- `web/src/components/SeamlessPlayer.tsx`
- `web/src/api/client.ts`
- `web/src/types/index.ts`

## 8. 下一步可扩展（不影响当前复用）

- 离线模式加入 beat-grid 对齐后的分段 timestretch（当前主要依赖计划时序）。
- 引入可配置的风格化转场模板（battle/cypher/showcase）。
- 在 stem-aware 基础上增加简单冲突检测（vocal overlap score / low-end clash score）后再调节阈值。
