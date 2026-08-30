# 音乐风格参考曲库：数据集基础审计

> 源文件：外部提供的 `音乐风格参考曲库.zip`（音频不进入 Git；用下方 SHA-256 核对版本）
> 生成时间：2026-08-28T17:39:31.064346+00:00

## 结论

- 有效音频：65 首；当前类别：13；目标类别：21。
- 每类歌曲数范围：5～5。
- 总时长：4.33 小时。
- 缺失类别：soul_neo_soul, rnb, drill, moombahton, memphis_trap, rage, uk_garage, trap_soul。
- 文件名提示 Remix/Mix/Edit/Instrumental 等版本风险：2 首。
- 重复主艺人组：2 个；已通过艺人分组 Fold 隔离。
- 当前所有文件夹标签均标为 `unreviewed`；不能在片段纯度审计前当成干净真值。

## 类别分布

| 类别 | 歌曲数 | 艺人组数 | Fold分布 |
|---|---:|---:|---|
| `afro_afrobeats` | 5 | 4 | F0:1, F1:2, F2:1, F3:1 |
| `amapiano` | 5 | 5 | F0:1, F1:1, F2:2, F3:1 |
| `baile_funk` | 5 | 5 | F0:2, F1:1, F2:1, F3:1 |
| `boombap` | 5 | 5 | F0:1, F1:2, F2:1, F3:1 |
| `breakbeat` | 5 | 5 | F0:2, F1:1, F2:1, F3:1 |
| `dancehall` | 5 | 5 | F0:1, F1:1, F2:1, F3:2 |
| `disco` | 5 | 5 | F0:1, F1:1, F2:1, F3:2 |
| `funk` | 5 | 4 | F0:2, F1:1, F2:1, F3:1 |
| `grime_uk_hiphop` | 5 | 5 | F0:2, F1:1, F2:1, F3:1 |
| `house` | 5 | 5 | F0:1, F1:1, F2:2, F3:1 |
| `jazz_hiphop` | 5 | 5 | F0:1, F1:2, F2:1, F3:1 |
| `jersey_club` | 5 | 5 | F0:1, F1:1, F2:1, F3:2 |
| `trap` | 5 | 5 | F0:1, F1:1, F2:2, F3:1 |

## 重复艺人组

- `bruno mars`：Bruno Mars - 24K Magic (1)；Bruno Mars - Treasure (1)
- `tyla`：Tyla - Truth or Dare；Tyla - Water

## 后续验证约束

1. Fold 是完整歌曲和主艺人级别，后续所有片段必须继承歌曲 Fold。
2. 文件名、艺人名、目录标签不得进入模型输入。
3. `unreviewed` 歌曲在完成片段纯度和外部标签审计前只能用于弱监督实验。
4. 只有 A/B 级歌曲可进入最终原型训练；C 级和争议样本只用于压力测试。
5. 当前只允许训练 13 类原型，不得把缺失 8 类解释为负样本或类外识别能力。
