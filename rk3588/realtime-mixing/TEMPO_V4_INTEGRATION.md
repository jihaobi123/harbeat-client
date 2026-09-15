# RK 实时混音：接入原 vocal_v4 变速处理

2026-09-14 实现/验收记录，2026-09-15 随源码交付。本文替代上一版“只有原速淡变”的能力说明。控制协议仍为 `harbeat.control.v1`，HTTP 地址仍为 RK 本机 `http://127.0.0.1:9130`。这是历史验证记录，不代表读取本文时设备仍处于同一播放状态；交付与外部依赖见 [README](README.md)。

## 本次“效果相同”指什么

复用用户压缩包中未修改的 `harbeat/tempo.py`、`build_transition_plan`、`order_tracks`、`choose_entry_cue`、`overlap_seconds` 和 `render_segment`，不是另写一个简化变速公式。

| 项目 | 当前行为 |
| --- | --- |
| 默认歌曲顺序 | 原 vocal_v4 的人声感知排序；指定未播放歌曲仍可覆盖下一首 |
| 入歌速度 | 使用原 BPM 兼容判断、半拍/倍拍关系、playback_rate；原方案不变速的组合继续原速 |
| 音高保持变速 | 原 FFmpeg atempo 链；实际处理音频，不只是返回一个 rate 字段 |
| 恢复速度 | 变速入歌头部后拼接原速尾部，和推荐脚本一致 |
| 淡变长度 | 使用原 overlap_seconds 规则，不再所有组合固定 12 秒；规则支持 12/14/16/18 秒 |
| 淡变曲线 | 原 FFmpeg tri 线性曲线，RK 使用逐采样增益，不再每 512 帧固定一个增益 |
| 曲目增益 | 原脚本的 0.74，直接由原渲染函数处理 |
| 最后一首 | 使用原最后一首的裁切和 8 秒结尾淡出处理 |
| 手动切歌 | 仍按用户要求选择未来最近候选点，不强行套用离线固定出歌时间 |

**不宣称整场输出文件逐字节一致。**手动切歌改变了出歌时刻；默认自动出歌尽量沿用原脚本选择，但仍受“未来、准备余量和足够剩余音频”的实时安全限制。现场音效、暂停也会改变整场声音。相同输入片段与相同转场参数下，验证的是 PCM 混合效果接近原脚本参考。

原推荐脚本本身没有实现 16 小节连续平滑回速，因此本次没有把它描述成已实现；沿用的是原脚本实际的“变速头部 + 原速尾部”。它也不是重新估计每一拍相位的精密锁拍器。

## 为什么仍是实时混音

准备阶段只生成每首歌可能用到的独立入歌版本，位于 `/home/cat/harbeat-mixing-v1/tempo-assets-v1/`。它们不是把 A、B 提前混合好的串烧文件。

播放时才依据当前进度、按键和下一首选择，把两份音频交给 RK 双 Deck，在声卡回调中进行淡变。按暂停会同时暂停两路和淡变进度，继续时恢复；未到候选点前 next 只安排计划。

索引位于 `reports/tempo_assets_v1.json`：order 为默认顺序，starts 为首曲版本，pairs 为 56 个有向歌曲组合，assets 为去重后的音频及哈希；每个 pair 含普通入歌 song_id 和最后一首专用 final_song_id。

每次更换预处理 manifest、原渲染代码或参数，要重新准备，不复用不匹配缓存。准备命令依次为 `venv/bin/python prepare_tempo.py`、`venv/bin/python prepare_tempo_final.py`，成功后在暂停状态重启控制服务。不要在演出中重建索引。NAS 原始资产、原算法包和旧原速实现都保留。

## 时间字段：不要混用

变速或从 22.02 秒入歌后，播放器计时不再等于原曲计时。

| 字段 | 含义 |
| --- | --- |
| state.source_position_sec | 原曲时间，给界面定位段落/小节使用 |
| state.engine.position_sec | 当前准备音频的播放时间，诊断字段 |
| pending.from_at_sec / to_at_sec | A 的原曲出歌点 / B 的原曲入歌点，保持原接口语义 |
| pending.from_playback_at_sec / to_playback_at_sec | 实际送给播放器的时间；B 准备音频从 0 开始 |
| pending.entry_rate | 原算法计划速度比，不代表整首都以该速度播放 |
| pending.head_output_seconds | atempo 实际输出头部长度；rate 与 1 差小于原脚本阈值时为 0 |
| pending.restore_mode | v4_head_then_original_tail |
| pending.incoming_asset_sha256 | 实际使用的准备音频哈希 |

时间转换使用实际 WAV 帧数计算头部长度，避免把名义 16 秒当作 atempo 一定恰好输出 16 秒。进入原速尾部后使用精确的时间偏移；变速头部内部映射是线性的定位近似，不用于宣称语音或节拍逐样本对齐。

capabilities.playback_mode 为 live_dual_deck_vocal_v4_tempo，tempo_stretch 为 true，smooth_16_bar_restore 为 false。原有开始、暂停、切歌、手势 JSON 不变。

## 缓存和实时边界

准备版本另有最多 10 份 / 1 GiB 的 PCM 缓存。启动前预读默认 8 首所需版本；特殊指定下一首可能需要预读一个不同版本，随后按准备完成时的实际位置重新选点。

正在播放和已加载到另一 Deck 的两份音频不可淘汰。旧缓存的释放在准备线程执行，不在声卡回调中释放整首数组。磁盘版本使用不可变哈希 ID；原 rtv1 缓存与 rtv2 缓存分别限制。

现有引擎保留限幅器防止叠加音效爆音；本次无音效对比中它没有触发额外压缩。不能据此保证任意音效叠加都和离线原曲一样响。

## 源码与服务

- prepare_tempo.py / prepare_tempo_final.py：调用原渲染代码生成单曲版本及映射索引。
- tempo_control.py：复用原排序/配对参数，转换原曲时间与准备音频时间，选择最近安全候选。
- realtime.py：原速版本保留；serve --tempo 才启用新控制器。
- engine-patch/engine.py：准备版本缓存、采样级淡变起止和增益；未修改硬件识别代码。
- control_api.py：既有协议不变，通过状态返回当前能力。
- verify_tempo_pcm.py：逐样本对比原 FFmpeg tri 参考。
- verify_realtime_live.py --http --tempo：在实际声卡上测试控制和 7 次转场。

cat 用户服务 harbeat-realtime-v1 已配置 serve --tempo。服务本身不自动播放；戒指/手环原网关仍由硬件负责人接入统一接口。

## 回退

原速控制逻辑保留在 realtime.py；管理员在用户服务中去掉 --tempo 并重启，可恢复原速模式。新 API 根据运行模式报告能力，不把原速模式说成支持变速。

修改前引擎完整备份：`/home/cat/harbeat-mixing-v1/engine-patch/engine.before-tempo.py`。暂停后运行 `venv/bin/python install_tempo_engine.py --rollback`，再重启 cypher-audio-engine.service。回退脚本校验文件哈希，避免覆盖别人的后续改动。原始更早版本备份也没有删除。

## 本次实际验收

| 验收 | 结果 |
| --- | --- |
| 控制、接口、时间映射和候选选择单元测试 | Mac / RK 各 46 项通过 |
| RK 原曲/变速缓存测试 | 12 项通过，包括不淘汰当前两路音频 |
| 7 对 PCM 与原 FFmpeg tri 参考对比 | 全通过，最大采样误差 0.0000319481，约一个 16 位量化单位 |
| 第一轮实际声卡 HTTP 模拟 | 62 项通过，7 次转场，XRUN 增量 0 |
| 第二轮实际声卡 HTTP 模拟，含最后一首专用资产 | 62 项通过，7 次转场，XRUN 增量 0 |
| 最后一首结尾 | 实际播放末尾 9 秒并到达结束状态，XRUN 增量 0 |

默认顺序实际配对的入歌速度计划依次为 1.0、0.96、0.958588957、1.0、0.999300210、1.0、1.0。0.999300210 与 1 的差小于原脚本 0.002 阈值，因此按原脚本不执行变速；不能把计划字段值当作每首都变速的证明。两处显著变速都已进入真实播放器并参与 PCM 对比。

本次普通入歌版本去重后 28 份，加入最后一首版本后共 48 份，覆盖 56 个有向歌曲组合。没有提前混合整段 mixtape。

报告保留在 RK reports/ 和本地 verification/：

- realtime_tempo_http_test-1789393858.json：第一轮。
- realtime_tempo_http_test-1789394285.json：含最后一首处理的第二轮。
- tempo_pcm_comparison.json：7 对采样对比。
- tempo_end_test.json：结束行为。
- tempo_unit_tests.log：46 + 12 项测试。
- tempo_assets_v1.json：实际资产和原曲时间映射。

对比音频在 RK `reports/tempo-pcm-comparison/`，每对含 `*_v4_reference.wav` 和 `*_rk_callback.wav`。比较使用相同准备音频和相同出歌时刻，验证了实际 callback 与原 acrossfade 执行效果。发现并修正了一个浮点转整数造成的单采样位置偏差后，7 对均通过。

说明：转场测试用了诊断 seek，**不是整场连续不间断试听，也没有完成真实戒指/手环识别验收**。实物识别、外放听感和长时间性能仍需单独验收。测试结束已暂停并清空测试会话，服务保留可用，不自动继续播放。

部署引擎 SHA256：`5aa430a104bab79a4b14499740106514e90838e8596e23f847916309f4abfd21`。
