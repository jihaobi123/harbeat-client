# KPOP 小节第一拍验证（2026-08-26）

## 结论

- 样本：用户提供的 KPOP.zip 中随机抽取的 10 首完整歌曲。
- 判定窗口：预测 downbeat 与参考点误差不超过 ±70 ms 视为匹配。
- 当前三路：Beat This `final0`、All-In-One `harmonix-all`、madmom-infer `RNN+DBN(4/4)`。
- 额外候选：BeatNet+ `generic_main + offline DBN`，仅作为专项对照，不参与当前产品投票。
- 10 首中 7 首三路高度一致；`I Need U`、`Love Shot`、`Shut Down` 出现重大冲突。
- 当前三路两两 F1 的宏平均分别为 0.8872、0.7956、0.7918，但这是**模型一致率，不是人工真值准确率**。
- 以模型一致、BPM/小节周期约束和节拍重音证据组成的临时裁决参考计算，当前公开输出的宏 F1 约为 **0.8781**。该数字仍含模型辅助标注，不能作为最终人工真值准确率。
- 按整首歌是否可无需复核直接使用统计，当前稳定通过为 **7/10（70%）**；1 首部分可用，2 首不应自动放行。

## 已完成的模块修正

测试结论已落实到共识模块：

- downbeat 路线必须通过最终 BPM + 4/4 对应的小节周期校验；
- 周期偏差超过 12% 的路线不再参与多数投票；
- 相同周期但相差整数拍时输出 `phase_conflict`；
- 获胜组中优先采用覆盖前两个小节的路线；
- `I Need U` 改选 Beat This，避免 All-In-One 跳过前奏；
- `Love Shot` 改选 Beat This并标记相位冲突；
- `Shut Down` 淘汰周期不合法的 All-In-One 与 Beat This，选择 madmom并强制复核；
- BeatNet+ 不加入生产普通投票，仅保留本次对照结论。

## 逐首结果

| 歌曲 | 三路最低 F1 | 结果 | 主要问题 |
|---|---:|---|---|
| ANTIFRAGILE | 0.9938 | 通过 | 仅首尾点数量差异 |
| Attention | 0.9542 | 通过 | 前奏存在少量额外/漏检点 |
| FANCY | 0.9871 | 通过 | 轻微首尾差异 |
| HISTORY | 0.9948 | 通过 | 三路稳定 |
| How You Like That | 0.8962 | 通过 | Beat This 在部分段落漏小节 |
| I Need U | 0.3380 | 部分通过/需复核 | madmom 错选双倍节拍层级；All-In-One 跳过约前 12 秒 |
| Love Shot | 0.5902 | 不通过 | Beat This 与 All-In-One 相差半个小节；当前代码无多数仍默认 All-In-One |
| Lovesick Girls | 0.9798 | 通过 | 三路稳定 |
| Shut Down | 0.0000 | 不通过 | BPM 三路分别约 214/73/110；当前选择的 All-In-One 小节周期与最终 110 BPM 不相容 |
| YES or YES | 0.9854 | 通过 | 三路稳定 |

## 关键故障

### I Need U

- 最终 BPM 约 79，正确 4/4 小节周期应约 3.04 秒。
- Beat This 与 All-In-One 在主体部分一致（F1 0.8649）。
- madmom 输出约 1.52 秒一个“小节”，实际是把半小节当成完整小节。
- 当前 All-In-One 输出从 12.38 秒开始，前奏小节缺失。

### Love Shot

- 最终 BPM 约 73，小节周期约 3.29 秒。
- Beat This 与 All-In-One 的周期都合理，但相位相差约 1.64 秒，即两拍/半小节。
- 当前状态为 `no_majority`，代码仍选择 All-In-One；重音与和声变化证据更支持 Beat This 相位。
- 必须通过点击轨人工确认，不能自动宣称正确。

### Shut Down

- BPM 共识最终选择 Essentia 约 110 BPM，4/4 小节周期应约 2.18 秒。
- 当前 downbeat 却选择 All-In-One，间隔约 3.27 秒，对应约 73 BPM，与最终 BPM 自相矛盾。
- BeatNet+ 能得到约 2.18 秒的小节周期；madmom 也得到该周期，但两者相位不同。
- 说明现有投票缺少“BPM—拍号—小节周期一致性”硬约束。

## BeatNet+ 对照结果

BeatNet+ 官方提供的离线 DBN 路线可在当前样本运行，但不能作为普通第四票：

- 对 `Shut Down` 的 110 BPM 层级判断有价值；
- 对 ANTIFRAGILE、FANCY、HISTORY、How You Like That、Love Shot 等出现整段相位偏移；
- 对 `I Need U` 和 `Love Shot` 也经常把半小节当成一小节；
- 因此只适合作为三路冲突时的诊断证据。

## 下一步规则建议

1. 先用最终 BPM 和拍号计算期望小节周期；与期望周期相差超过 12% 的 downbeat 路线直接淘汰。
2. 检测 `0.5x / 1.5x / 2x` 小节周期错误，不能只看 ±70 ms 的逐点匹配。
3. 两条路线周期一致但相位相差 1–3 拍时，状态改为 `phase_conflict`，禁止默认选择 All-In-One。
4. 加入前奏覆盖率：第一条 downbeat 晚于两个期望小节时降级，避免 `I Need U` 前 12 秒缺失。
5. BeatNet+ 仅在 BPM 三路无多数或周期全部不合法时运行，不进入普通多数投票。
6. 最终准确率必须用人工点击轨确认后的时间轴重新计算 Precision、Recall、F1。

## 产物

- `raw/<歌曲>/<engine>.json`：当前三路逐点时间轴。
- `beatnet_plus/<歌曲>.json`：BeatNet+ 对照时间轴。
- `raw/summary.json`：逐首两两 ±70 ms 指标。
- `audit_clips/*.wav`：冲突歌曲前 45 秒点击轨；900 Hz 为普通拍，1800 Hz 为小节第一拍。
- `scripts/validate_downbeats.py`：可重复运行的隔离测试与点击轨生成工具。
