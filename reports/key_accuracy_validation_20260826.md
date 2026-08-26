# KPOP 调性识别10首试验报告（2026-08-26）

## 结论

本报告是10首小样本试验，不代表整个 KPOP 曲库的最终准确率。

在7首具有相对可靠外部参考值的歌曲上，采用24类“主音 + 大小调”完全一致标准：

| 路线 | 正确数 | 严格准确率 |
|---|---:|---:|
| libKeyFinder 主链路 | 5/7 | 71.4% |
| Essentia KeyExtractor | 7/7 | 100.0% |
| madmom CNN | 7/7 | 100.0% |
| 本地 CQT/CENS | 4/7 | 57.1% |
| HarBeat 最终裁决 | 7/7 | 100.0% |

另外3首（ANTIFRAGILE、FANCY、HISTORY）的公开资料对调性存在明显冲突，未计入严格准确率。
如果采用本文的暂定人工判定并继续排除具有段落调性变化的 FANCY，则9首暂定结果为：
libKeyFinder 7/9、Essentia 9/9、madmom 9/9、CQT/CENS 4/9、最终裁决9/9。

不能据此宣称系统已达到真实生产准确率100%。目前的合理结论是：双验证器在该小样本上
有效纠正了主链路，但必须扩展至至少50–100首人工标注曲库再决定生产阈值。

## 抽样方法

- 来源：用户提供的 `KPOP.zip`；
- 压缩包内有效音频84首；
- 为避免乱码文件名影响外部检索，从52首纯英文文件名歌曲中抽样；
- 固定随机种子：`20260826`；
- 样本数：10；
- 所有引擎分析同一份本地音频，而不是只按歌曲名称查询数据库。

## 逐曲结果

`*` 表示参考值存在公开来源冲突；`—` 表示该曲不计入严格准确率。

| 歌曲 | 外部参考 | libKeyFinder | Essentia | madmom CNN | CQT/CENS | 最终裁决 | 严格计分 |
|---|---|---|---|---|---|---|---|
| ANTIFRAGILE – LE SSERAFIM | F minor / 4A* | F minor / 4A | F minor / 4A | F minor / 4A | C# minor / 12A | F minor / 4A | — |
| Attention – NewJeans | Bb minor / 3A | Bb minor / 3A | Bb minor / 3A | Bb minor / 3A | Bb minor / 3A | Bb minor / 3A | 全部正确 |
| FANCY – TWICE | C minor ↔ Eb major* | Bb major / 6B | Eb major / 5B | Eb major / 5B | Bb minor / 3A | Eb major / 5B | — |
| HISTORY – EXO-K | G# minor / 1A* | G# minor / 1A | G# minor / 1A | G# minor / 1A | F# minor / 11A | G# minor / 1A | — |
| How You Like That – BLACKPINK | D# minor / 2A | D# minor / 2A | D# minor / 2A | D# minor / 2A | D# minor / 2A | D# minor / 2A | 全部正确 |
| I Need U – BTS | F minor / 4A | F minor / 4A | F minor / 4A | F minor / 4A | F minor / 4A | F minor / 4A | 全部正确 |
| Love Shot – EXO | C minor / 5A | G minor / 6A | C minor / 5A | C minor / 5A | F minor / 4A | C minor / 5A | 主链路错误，裁决正确 |
| Lovesick Girls – BLACKPINK | F# major / 2B | D# minor / 2A | F# major / 2B | F# major / 2B | D# minor / 2A | F# major / 2B | 主链路误判相对小调，裁决正确 |
| Shut Down – BLACKPINK | Bb minor / 3A | Bb minor / 3A | Bb minor / 3A | Bb minor / 3A | Bb minor / 3A | Bb minor / 3A | 全部正确 |
| YES or YES – TWICE | F# major / 2B | F# major / 2B | F# major / 2B | F# major / 2B | F# minor / 11A | F# major / 2B | CQT错误，其余正确 |

## 主链路分段稳定性

libKeyFinder 对每首分别分析整曲、去除前后10%的主体、中央90秒。10首歌曲的三段结果全部
一致，因此本次样本的 libKeyFinder 内部稳定率为10/10。该指标只说明结果对所选时间段稳定，
不代表答案正确；Love Shot 和 Lovesick Girls 正是“稳定但错误”的例子。

## 外部参考值与争议处理

- Attention：[SongBPM](https://songbpm.com/%40newjeans/attention-kuYbYfx7oT) 与
  [Musicstax](https://musicstax.com/fr/playlist/newjeans-discography/1aKi75MooLoMmtGMsqYvhc)
  均为 Bb minor。
- How You Like That：[Musicnotes](https://www.musicnotes.com/sheetmusic/blackpink/how-you-like-that/MN0213412)
  原出版调为 D# minor；[Hooktheory](https://www.hooktheory.com/theorytab/view/blackpink/how-you-like-that)
  显示 D# minor/Phrygian 系列段落，[Chordify](https://chordify.net/chords/blackpink-how-you-like-that-m-v-blackpink)
  也给出 Eb minor。
- I Need U：[公开作曲资料](https://en.wikipedia.org/wiki/I_Need_U_%28BTS_song%29)记录为 F minor。
- Love Shot：[公开作曲资料](https://en.wikipedia.org/wiki/Love_Shot)记录为 C minor。
- Lovesick Girls：[作曲资料](https://en.wikipedia.org/wiki/Lovesick_Girls)、
  [SongBPM](https://songbpm.com/%40blackpink/lovesick-girls) 与
  [Hooktheory](https://www.hooktheory.com/theorytab/view/blackpink/lovesick-girls)全曲分析支持 F# major；部分乐谱以相对
  小调 Eb/D# minor 记谱，因此它也是重要的“相对大小调误判”测试样本。
- Shut Down：[作曲资料](https://en.wikipedia.org/wiki/Shut_Down_%28Blackpink_song%29)及
  [乐谱说明](https://www.kokomu.jp/sheet-music/shut-down-blackpink-rom-kor-180048)均支持 Bb minor。
- YES or YES：[Musicnotes](https://www.musicnotes.com/sheetmusic/twice/yes-or-yes/MN0202767_D3)
  标注原出版调为 F# major。
- ANTIFRAGILE：[Hooktheory](https://www.hooktheory.com/theorytab/view/le-sserafim/antifragile)
  的旋律/和声分析为 F minor，但[部分元数据资料](https://en.wikipedia.org/wiki/Antifragile_%28song%29)
  写作 Bb minor，
  因此不纳入严格统计。
- FANCY：[Hooktheory](https://www.hooktheory.com/theorytab/view/twice/fancy)
  将大部分段落分析为 C minor、预副歌为 Eb major；其他自动数据库还给出
  F minor，无法合理压成唯一24类标签，因此不纳入严格统计。
- HISTORY：[Chordify](https://chordify.net/chords/exo-songs/history-chords)的和弦中心为 G# minor，
  但[部分元数据网站](https://songbpm.com/%40exo-k)给出 C#/Db major，因此不纳入
  严格统计。

## 观察与后续优化

1. Essentia 与 madmom 在10首上完全一致，证明此次验证器输出稳定，但样本量不足以证明它们
   在大曲库上总是正确。
2. libKeyFinder 适合作为速度稳定的 DJ 主链路，但不能无条件作为最终答案；本次有两首可靠
   样本被两个验证器共同纠正。
3. CQT/CENS 在相对大小调、平行大小调和邻近调上误判较多，应继续保持为冲突辅助，不应进入
   常规平权投票。
4. 系统需要允许 `ambiguous` 或多个段落调性，不能强迫 FANCY 这类歌曲只有一个绝对正确标签。
5. 下一轮应建立至少50–100首人工标注集，并分别报告 exact、relative、parallel、fifth 和
   MIREX weighted score。
