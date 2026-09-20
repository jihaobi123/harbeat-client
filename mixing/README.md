# V3 混音与复现

保留同事原始算法的函数体，并用 SHA256 拒绝加载被意外修改的版本。V3 的速度、进出歌点、低频和中频处理没有在本次整理中调整。

- `vendor/colleague_demo_v1/`：原始算法与六首 Future Bass 冻结计划。
- `vendor/harbeat_v4/harbeat/`：用户提供的 V4 纯算法辅助库。供新曲目读取 Manifest、调性和鼓组评分使用。
- `analysis_platform/demo_v3.py`：校验、加载原始渲染函数、绑定来源与编译冻结计划。
- `analysis_platform/colleague_policy.py`：同事排歌规则；缺失的拍网格助手使用实际记录的 bar 适配，明确保留差异说明。
- `recipes/`：历史演示入口；V3 和 Hip-Hop 已支持从当前 checkout 运行，其他旧版配方仅供审计。

先建立仓库根 `analysis_platform/requirements.txt` 所述独立环境，并安装 FFmpeg。

## 复现六首 Future Bass

准备 `sources.json`，包含六首原曲的 `title`、`audio_sha256`、`path`。也接受原 V1 计划的 `{ "tracks": [...] }` 格式。相对音频路径以这个 JSON 所在目录解析；必须与冻结计划的音频身份一致。

```bash
.venv-lab/bin/python mixing/recipes/render_demo_v3.py \
  --sources /path/to/sources.json --output /path/to/new-result
```

可增加 `--reference /path/to/colleague-original.mp3`，核对原始 MP3 身份并比较解码后的样本和文件哈希。没有提供参照时，报告明确记录 `not_provided`。不同 FFmpeg/编码器版本可能产生不同文件；参照验证不能省略。

输出 WAV、MP3、五段转场试听、冻结计划、实际调用参数、命令、响度、采样长度与参照比较。拒绝覆盖已有不同计划。

## 对 NAS 已分析曲目运行 Hip-Hop 配方

数据目录采用：

```text
my-set/
  inputs/inputs.json
  inputs/reports/<report_id>.json
  inputs/audio/<source-file>
  style-audit.json
```

`inputs.json` 为数组，每项含 `report_id`、`relative_path`（相对 inputs）、`sha256`、`report_file_sha256`。报告需保留原平台结构：`documents.core`、来源一致的人声区间和风格模型记录。本配方按原演示要求检查，筛出六首有效曲目，否则报错；它不是任意数量的通用排歌接口。

```bash
.venv-lab/bin/python mixing/recipes/render_hiphop_v3.py --data-dir /path/to/my-set --plan-only
.venv-lab/bin/python mixing/recipes/render_hiphop_v3.py --data-dir /path/to/my-set
.venv-lab/bin/python mixing/recipes/build_hiphop_v3_review.py --data-dir /path/to/my-set
```

输出到 `listen/`，中间音频在 `work/`。保留全部路线、拒绝原因、报告快照、选点、人声判定、变速/EQ 参数、命令和试听页。构建报告还需要原曲库扫描的 `style-audit.json`。这些是真实曲库数据，另存 NAS，不提交 GitHub。

## 版本边界

V3 是离线渲染；[在线模块说明](ONLINE.md) 单独列出实时控制与播放器。V2 与 V3 人声判定、选点和 EQ 不同，不能混用同一个版本名称。

原同事交付缺少 `phrase_mix` 辅助模块，因此新歌曲规划使用明确标记的原始小节网格适配器；渲染函数保持原版。待确认段落、降级鼓组和调速风险继续保留在报告里。

[来源说明](NOTICE.md) · [原 V3 验证记录](../analysis_platform/DEMO_V3.md) · [Hip-Hop 验证记录](../analysis_platform/HIPHOP_V3.md)
