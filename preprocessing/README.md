# 正式预处理：从这里开发和调用

此目录保存正式预处理的编排、发布、人声检测和运行入口，不是另写一套模型。
2026-09-13 从散落的 app/scripts/experiments 中迁入 9 个实现，参数、结果格式和分析算法不变。

## 目录

```text
preprocessing/
  publisher.py                 单曲编排、Demucs调用、MDX调用、NAS发布
  vocal_activity.py            已有vocals → Silero人声时间标记
  runners/
    songformer.py              SongFormer隔离运行器
  cli/
    run_same_style_preprocess.py  分析一首歌，发布基础结果并补人声
    import_same_style_library.py  ZIP曲库导入、记录目录标签与进度
    backfill_vocal_activity.py    给已发布歌曲补人声报告
    validate_vocal_activity.py    检查报告、版本关联、文件指纹
    export_vocal_activity_bundle.py 打包人声增补文件
    finalize_vocal_activity.py    完成整批验证、打包和交付回执
```

## 如何调用

在仓库根目录、现有预处理 Python 环境下运行：

```bash
python -m preprocessing.cli.run_same_style_preprocess --help
python -m preprocessing.cli.import_same_style_library --help
python -m preprocessing.cli.backfill_vocal_activity --help
```

Jetson 运维使用 `deploy/jetson/` 的包装脚本，它们已指向新目录。
这里只调整仓库源码，没有切换线上 release 或重启线上任务。
新版本部署必须包含整个 `preprocessing/`，不能只拷贝旧 app/scripts 目录。

程序调用接口：

```python
from preprocessing.publisher import PreprocessConfig, run_same_style_preprocess
from preprocessing.vocal_activity import publish_vocal_activity
```

底层 `run_same_style_preprocess` 发布基础结果；单曲 CLI 随后显式调用人声发布器。
不要把基础结果成功当成人声阶段一定成功。当前曲库禁用 ADTOF 时继续显式传 `--disable-adtof`，本次不改默认配置或缓存版本。

## 哪些实现仍是共享依赖

| 能力 | 目前实际实现 | 为什么这次不一起搬 |
|---|---|---|
| BPM、Beat、小节、段落结果整合 | `app/modules/library/analysis.py` | 旧业务后台和其他评测也在用；本次只将正式 SongFormer 运行器拆出 |
| 轨道特征分析 | `app/modules/library/stem_analysis.py` 及关联特征模块 | 多个业务调用，需单独做后续模块拆分验证 |
| MDX23C | `music_analysis/drum_analysis/mdx23c_separator.py` | 已是独立模块，不为换目录而复制一份 |
| 发布数据格式 | `contracts/schemas/analysis/` | 保持已有消费者兼容，不改 schema 版本 |

因此这不是可以只拷贝单个目录就安装的独立发行包。部署仍需要上述共享模块、现有模型环境和 schemas。
本目录不直接使用数据库；歌曲目录与业务数据库的衔接不属于这次代码搬迁。

## 旧路径的处理

旧 `scripts/run_same_style_preprocess.py` 等 6 个 CLI、旧 app 中 2 个模块、旧 SongFormer 路径仍可调用，但只转发到本目录。
新代码不要继续从旧路径导入。转发保留模块身份，旧调用方和新调用方不会各加载一份业务实现。
完整对应表见 [迁移清单](../docs/repository/moves-20260913.json)。

研究和比较模型请去 [research](../research/README.md)，不要从正式入口自动加载它们。
