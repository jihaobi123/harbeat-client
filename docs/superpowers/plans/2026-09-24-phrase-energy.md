# 乐句保护与能量 EQ Implementation Plan

> For agentic workers: use executing-plans for bounded implementation and requesting-code-review for independent review. User has authorized execution; no additional design approval required.

**Goal:** 在 20 首曲库提供可追溯乐句／拍点预处理与独立的新实时 EQ 对照，不覆盖 V3.1。

**Architecture:** Python 纯数据预处理 → 带来源指纹的独立 catalog → TypeScript 规划器 → 同一计划的固定/能量 EQ 渲染 → 时间轴与日志。既有素材、旧规划器和偏好数据保持原样。

**Tech Stack:** Python/pytest, TypeScript/Vitest, React, Web Audio, FFmpeg, Jetson/NAS, nginx relay.

- [x] 1. 新增 `analysis_platform/phrase_alignment.py` 和 `tests/test_phrase_alignment.py`。先用跨拍尾音、短换气合并、证据冲突、缺失拍点四种夹具验证失败，再实现 `analyze_alignment(track, signals)`。输出 bars、phrases、exits、conflicts、source、bandFrames；单位为原曲秒、dBFS，lastBeat 与 endDownbeat 分列。
- [x] 2. 新增 `scripts/build_phrase_corpus.py`，按 V31 原有 20 首、来源报告哈希和音频指纹读取，补充预处理，复用音频与旧入口；必要时生成含人声开始前的 1/2/4 小节原曲入口。预制只做单曲变速。输出到独立目录，验证每个片段 SHA 和时长，不改旧 catalog。
- [x] 3. 新增 `web/src/phrase/planner.ts`、`automation.ts` 和测试。验证 A 在 tailEnd 前 gain=1、不会向前截尾、B 的第一句按变速映射、人声间距限额、固定/动态使用同一选点、动态衰减有界且随频谱变化，缺证据拒绝动态执行。
- [x] 4. 在 `LiveTransport` 增加可选 automation 分支，旧分支保持原样。控制点使用音频时钟提前排程，退出/恢复/暂停/取消沿用生命周期。日志记录实际自动化与对应能量采样依据。补测试覆盖旧版未变与新版 gain/EQ 时序。
- [x] 5. 新建 `web/src/phrase/PhraseLab.tsx`，独立 `v32-candidate-20260924`，按相同源请求对照 V3.1 / 乐句+固定EQ / 乐句+动态EQ；实时请求、源片段查看、预处理与增益/EQ时间轴、失败原因、独立反馈、完整日志导出。分析平台增加入口与派生证据显示。
- [x] 6. Jetson 执行补算，保留完整覆盖统计；自动检查所有已生成计划的保护范围与数据绑定，浏览器执行固定/动态各一组实际转场，核对音频线程事件与日志。执行产品前端和 Python 相关测试。最后独立代码复核、部署独立目录、保留回退与反馈、提交推送 GitHub。

验收边界：没有人工或歌词真值时不得使用“句尾已确认”；候选为空必须展示原因；不声称模型精度与音质已经通过人工验收。旧版本与旧偏好必须保持可用。
