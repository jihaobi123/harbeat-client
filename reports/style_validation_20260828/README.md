# 测试曲库 1.0：特征与 21 风格增量修正验证

## 结论

旧版 10 首第一候选全部为 Disco；本次最终第一候选分布为 Disco 4、House 3、Funk 3。
第一候选只表示 21 类内最高分，不等于歌曲只有一种风格。按完整必需证据统计，Funk
在 10 首中的 8 首被检测到，因此该曲库的 Funk 主体和 Funk 影响已保留在多标签结果中。

- 完整测试：450 passed，3 skipped；无功能失败。
- 真实曲库：10/10 分析成功。
- 需复核：7/10；其中 2 首明确属于 21 类外或邻近类别。
- 完整结果：`/tmp/harbeat-test-library-1.0-20260827-v3/results.json`。
- 逐曲报告：`/tmp/harbeat-test-library-1.0-20260827-v3/report.md`。

## 逐曲结果

| # | 曲目 | 21 类第一候选 | 达到完整检测条件的多标签 | 外部/开源参考判断 |
|---:|---|---|---|---|
| 1 | Afrika Bambaataa - Funky Heroes | House 0.898 | House、Funk | 当前音频版本模型强偏 House；保留 Funk 影响 |
| 2 | Basic Element - Night Eyes | House 0.686 | 无 | Eurodance / Euro House；`out_of_taxonomy=true` |
| 3 | Cerrone - You Only Live Once | Disco 0.888 | Disco、Funk | Nu-Disco / Disco，含 Funk/Boogie 标签 |
| 4 | Dogg Master / XL Middleton - Pop Lock Funk | Funk 0.761 | Funk、R&B | G-Funk / Modern Funk |
| 5 | Ghosthouse - Crazy in Love | Funk 0.677 | Funk | 乐队官方描述为 electro-funk |
| 6 | Look Twice - FUNK YOU UP | Funk 0.611 | Funk | Eurodance/Pop，使用 Funk 采样；`out_of_taxonomy=true` |
| 7 | Uptown Funk (Wideboys VIP Remix) | House 0.740 | Disco、Funk | 原曲 Funk-pop/Boogie；该 Remix 模型强偏 House |
| 8 | Mass Production - Turn up the Music | Disco 0.718 | Funk、House | Disco/Funk；资料称 hard boogie funk，需复核主次 |
| 9 | S Club 7 - Don't Stop Movin' | Disco 0.789 | Disco、House、Funk | Disco-oriented Dance-pop；Funk 为较弱影响 |
| 10 | Dreamgirls - One Night Only (Disco) | Disco 0.565 | Disco、House | Post-disco / Soul；模型输出很弱，未参与加分 |

## 特征反向检查

| 特征 | 最小值 | 最大值 | 均值 | 结论 |
|---|---:|---:|---:|---|
| sample_texture | 0.056 | 0.411 | 0.265 | 旧版 10/10 为 1.0 的饱和已消除 |
| low_pitched_drum | 0.000 | 0.000 | 0.000 | 普通 Kick 不再误算 Tom/Surdo；当前无专用鼓模型，保持未知倾向 |
| chord_change_activity | 0.271 | 0.725 | 0.515 | 旧版接近 0、初版修正 7/10 为 1.0；最终连续尺度不再饱和 |
| low_frequency_melody | 0.622 | 0.827 | 0.738 | 保留曲库普遍较强的旋律型低频，但不再达到 1.0 |
| rage_synth_candidate | 0.151 | 0.505 | 0.264 | 明亮电子制作不再替代 Rage Synth 必需证据 |

Bass Slide 仍有 2 首达到 1.0，均来自有声音高事件内的连续运动，不再由不同音符之间
的跨度产生；但真实精度仍需对滑音片段人工标注后计算 Precision/Recall。

## 外部参考

- Ghosthouse 官方 Bandcamp 将乐队描述为 electro-funk：
  https://ghosthousechicago.bandcamp.com/track/crazy-in-love
- Pop Lock Funk 的公开资料标记为 G-Funk/Funk：
  https://volt.fm/track/10891100/pop-lock-funk-by-dogg-master
- Mass Production 的资料将标题曲描述为 hard boogie funk，并指出 Disco/Funk 混合：
  https://soulbrother.com/shop/turn-up-the-music-2/
  https://www.allmusic.com/album/turn-up-the-music-mw0000858035
- Basic Element 的 Night Eyes 属于 Eurodance/Euro House：
  https://www.theaudiodb.com/track/33540304-Basic-Element-Night-Eyes
- Uptown Funk 原曲为 Funk-pop、Boogie、Disco-pop，Wideboys 版本是正式 Remix：
  https://en.wikipedia.org/wiki/Uptown_Funk
- Don't Stop Movin' 为 Disco-oriented Pop：
  https://en.wikipedia.org/wiki/Don%27t_Stop_Movin%27_%28S_Club_7_song%29
- One Night Only 的公开风格包含 Post-disco、Soul：
  https://en.wikipedia.org/wiki/One_Night_Only_%28song%29

## 限制

当前专用鼓转录模型未配置，节奏及打击乐语义使用频谱代理，相关可靠度上限为 0.55。
21 类中没有 Eurodance、Dance-pop、G-Funk、Electro-Funk 等独立类别，因此系统同时保存
原始模型标签、邻近映射和 `out_of_taxonomy`，不能把 21 类第一候选当作外部流派真值。
