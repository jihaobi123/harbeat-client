# 来源与模型授权

设计参考：sereinlover/computable-beauty，提交 `ffe161a928b5ba46182fe66dbc1f5a1ecc259766`：
https://github.com/sereinlover/computable-beauty/tree/ffe161a928b5ba46182fe66dbc1f5a1ecc259766

本模块重新实现报告、图表、粗糙度和重复分组；未复制该项目的四维固定审美分数、段落命名启发式或 LLM “已验证”标记。其源码 Apache-2.0 授权不代表模型具有同样授权。

可选 Essentia 模型由 Music Technology Group 发布：
https://essentia.upf.edu/models/

- `msd-musicnn-1.pb` / `deam-msd-musicnn-2.pb`
- `discogs-effnet-bs64-1.pb`
- `genre_discogs400-discogs-effnet-1.pb` 及同名 metadata JSON（400 个细分类别，原始 sigmoid 分数）
- `mtg_jamendo_instrument-discogs-effnet-1.pb` 及同名 metadata JSON

这些预训练模型按官方模型库 CC BY-NC-SA 4.0 条款用于研究试验；商业产品应先取得适用授权。Essentia 软件本身还有其独立许可。模型和推理软件都作为可选外部依赖，未纳入默认主分析运行时。下载命令要求显式接受研究许可；下载 manifest 及运行报告保存模型文件哈希。

粗糙度采用 Sethares 风格临界带峰对公式，与 Essentia Dissonance 的实现、量纲和数值不完全相同。重复分组基于 chroma/RMS 的平均链接聚类，只有相似性含义，没有曲式名称或审美结论。

## Chord timeline (2026-09-19)

Uses official madmom 0.16.1 DeepChroma and CRF through an isolated Python 3.10 interpreter. Original project integration code is independently written; `computable-beauty` supplied the capability comparison, not a copied aesthetic scoring pipeline. Output preserves N and uncovered intervals. Bundled madmom model files use CC-BY-NC-SA-4.0, independently of the code's BSD license; this continues the authorized research installation. Actual model SHA256 values are stored per result.

The original HarBeat pure functions are frozen in `core_source_snapshot.py` with source-file hashes to reproduce existing feature definitions without importing production services. Supplemental stereo LUFS uses pyloudnorm 0.1.1 (MIT); RMS percentile range is not EBU LRA.
