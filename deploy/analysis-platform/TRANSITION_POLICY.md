# Jetson 接歌规划器

规划器部署在 `/home/mark/harbeat-listen-imports/code/transition-policy-v1`。Jetson 导入任务在完成节拍、段落和分离人声分析后，把接歌证据写到任务目录的 `transition-cues.json`。记录绑定曲目、原曲、分轨和分析版本，只保存时间标记及来源。网易云下载任务可以用已核验的歌曲 ID 取同步歌词。上传音频和缺少同版本歌词的曲目使用分离人声证据。

曲对规划器核对 `result.json` 中的音频指纹，再读取同版本的接歌证据。它会先避开人声中段、短换气和尾音，再参考 SongFormer 的段落标签，对前奏或器乐入口和段落末端排序。两首的分轨复核仍使用已有门槛。

```sh
cd ~/harbeat-listen-imports/code/transition-policy-v1
python3 -m analysis_platform.transition_policy_cli \
  /path/to/A/result.json /path/to/B/result.json \
  --a-reference 170.2 --b-entry 25.8
```

两项选点参数是已有方案在原曲上的秒数，可省略。也可以传入第三个位置参数 `B-lyrics.json`，其中包含与 B 录音对应的 `masterSha256` 和同步歌词 `lrc`。给已有任务补证据时，可运行 `python3 -m analysis_platform.transition_cues /path/to/result.json --lyrics /path/to/lyrics.json`。缺歌词时省略 `--lyrics`。

如果 B 有额外复核的前奏拍点，规划器会读取 B 任务目录的 `transition-intro-beats.json`。旧版本的补测会被跳过，保留原拍网格。

- 前奏长叠要求连续实测小节，逐拍偏差不超过 65 ms。A 尾句和 B 起唱使用各自的声学时间。
- 提前收尾要求 A 最后一段人声已释放，B 有足够干净的前奏，并有可对应的局部实测拍点。
- 两种前奏方案都不可用时，可提供歌词短接候选。伴奏频段重叠和入场电平由渲染阶段复核和调整。
- `candidate` 表示可复核的计划。客户端需要渲染或播放验收后才可使用新计划。`fallback` 表示由原播放策略继续处理。

正式播放器读取已发布的曲对批准记录。新曲导入时自动生成单曲证据，曲对复核和批准记录发布仍单独执行。

曲对复核使用 `harbeat-mobile` 仓库中的 `tools/review_transition_pair.ts`。在该仓库安装 `vendor/realtime-v3` 的锁定依赖后，从仓库根目录构建 Node 复核脚本：

```sh
npm ci --prefix vendor/realtime-v3
vendor/realtime-v3/node_modules/.bin/esbuild tools/review_transition_pair.ts \
  --bundle --platform=node --target=node20 --outfile=review.cjs
```

将 `review.cjs` 放到 Jetson 规划器目录。Jetson 环境还需能导入本仓库的 `metric_mix`，并能访问对应版本的设备执行清单、分析报告和 NAS 音频。
