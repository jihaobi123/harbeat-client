# SongFormer 段落与小节运行方案

## 职责边界

- SongFormer 是正式的功能段落来源，输出前奏、主歌、副歌、预副歌、桥段、器乐段和尾奏。
- Beat This、All-In-One、madmom 继续提供 Beat、Downbeat、BPM 与拍号证据。
- All-In-One 的段落只在 SongFormer 不可用时作为显式回退；两套段落不会融合。
- 产品 Bar 1 从 SongFormer 前奏结束后的第一个可靠 Downbeat 开始，后续按照真实 Beat 序列和检测拍号计数。

## 本地自动发现

开发机存在以下文件时，核心分析会自动使用隔离的 SongFormer 运行环境：

```text
.runtime/songformer-venv/bin/python
.runtime/songformer-src/
.runtime/songformer-muq/
experiments/run_songformer_isolated.py
```

特征缓存和推理清单默认写入：

```text
.runtime/songformer-analysis/
```

缓存键包含音频绝对路径、文件大小和修改时间，音频内容替换后会重新计算。

## 部署配置

生产环境可用独立命令覆盖自动发现：

```bash
SECTION_ENABLE_SONGFORMER=true
SECTION_SONGFORMER_COMMAND='python /opt/harbeat/scripts/run_songformer_isolated.py {audio} --out-dir {output_dir}'
SECTION_SONGFORMER_WORK_DIR=/opt/harbeat/cache/songformer-analysis
SECTION_SONGFORMER_SOURCE_ROOT=/opt/harbeat/models/SongFormer
SECTION_SONGFORMER_MUQ_MODEL=/opt/harbeat/models/MuQ-MuLan-large
SECTION_SONGFORMER_DEVICE=cuda
SECTION_SONGFORMER_PRECISION=float32
SECTION_SONGFORMER_TIMEOUT_SEC=1800
SECTION_FALLBACK_ALL_IN_ONE=true
```

命令以 `shell=False` 执行，支持 `{audio}` 和 `{output_dir}` 两个占位符。默认运行器将模型依次加载，避免 MusicFM、MuQ、SongFormer 与 All-In-One 同时驻留显存。

## 输出语义

正常使用 SongFormer：

```json
{
  "section_analysis": {
    "source": "songformer_functional_segments",
    "authoritative_model": "songformer",
    "fallback_used": false
  }
}
```

SongFormer 失败而启用回退：

```json
{
  "section_analysis": {
    "source": "all_in_one_fallback_functional_segments",
    "authoritative_model": "songformer",
    "fallback_used": true,
    "error": "SongFormer错误原因"
  }
}
```

回退状态必须保留，不能把 All-In-One 结果伪装成 SongFormer 结果。

## 小节规则

1. 合并歌曲开头连续的 SongFormer `intro` 段。
2. 在前奏结束处允许小范围时间容差，选择其后第一个共识 Downbeat。
3. 将该 Downbeat 吸附到最近的真实 Beat，作为 Bar 1 Beat 1。
4. 按检测到的每小节拍数，从 Beat 序列每 3 拍或 4 拍生成后续 Bar。
5. 原生 Downbeat 保留为相位校验，不允许单个中途误报改变整首歌的小节编号。

当前默认 madmom 同时建模 3 拍和 4 拍小节。混合拍号歌曲仍属于未验证能力，应标记人工复核。
