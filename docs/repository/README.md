# 仓库代码地图与本次实际整理

更新：2026-09-13。此文只说明代码位置和清理范围，不设计手机接口、不宣称线上已切换版本。

## 1. 先按工作找目录

| 你要维护什么 | 现在从哪里进去 | 当前边界 |
|---|---|---|
| 正式预处理 | [preprocessing](../../preprocessing/README.md) | 9 个编排、发布、运行器/CLI 实现已迁入 |
| MDX23C 鼓组 | `music_analysis/drum_analysis/` | 已有独立实现，继续复用，不复制 |
| Web 后端和已有数据库模型 | `app/` | 仍有旧业务路由和共享分析引擎，未宣称是完整第二版业务接口 |
| 发布数据格式 | `contracts/schemas/analysis/` | 现有预处理/人声 schema 保持不变 |
| Jetson 运行与部署 | `deploy/jetson/` | 仓库脚本改用新目录；未重启或替换线上服务 |
| 评测和风格训练 | [research](../../research/README.md) | 24 个研究脚本已从常用 scripts 目录移走 |
| 原实验数据和模型 | [experiments](../../experiments/README.md) | 保留模型、数据集、固定报告、MERT 复现入口 |
| 运维和旧命令兼容 | [scripts](../../scripts/README.md) | 标明哪些会写数据库、哪些是转发入口 |
| 独立模块抽取版本 | `modules/` | 历史模块化基线，并非默认生产运行时；不与当前实现同时当作权威 |
| 原客户端 / RK | `mobile/`、`web/`、`rk_deploy/`、`jetson/`、`cypher-integration/` | 保留给原维护者；不属于本次分析清理的删除范围 |
| 已退役入口 | `archive/analysis-v1/` | 原 All-In-One 对比脚本和旧 RMS 补分析入口，保留可追溯副本 |
| 测试 | `tests/`、`app/tests/` | 导入路径已同步；新增目录/兼容性回归测试 |

## 2. 这次不是只新增说明文件

已迁移 **33 个 Python 实现**：

- 正式预处理 9 个，统一到 `preprocessing/`；旧路径只留转发，不保留第二份业务逻辑。
- 专项评测 17 个，移到 `research/evaluation/`。
- 风格研究 7 个，移到 `research/style/`。
- 更新实际调用方、测试及 Jetson 包装脚本；调整迁移文件的仓库根目录解析，保持模型/schema/数据路径正确。

逐文件对应关系见 [迁移表](moves-20260913.json)。旧提交的源码仍在 Git 历史中。
脚本迁移仅允许导入路径、相对根目录及运行器说明文字变化；迁移时逐一与整理前源码核对，未改算法表达式。

## 3. 正式路径现在怎么串起来

1. `preprocessing/cli/run_same_style_preprocess.py` 接收一首歌及配置。
2. `preprocessing/publisher.py` 调用已有核心分析、Demucs、轨道特征和 MDX23C，校验后发布基础结果。
3. 核心分析 `app/modules/library/analysis.py` 调用 `preprocessing/runners/songformer.py`；仍保留 All-In-One 节奏参与和显式失败回退。
4. 单曲 CLI 再调用 `preprocessing/vocal_activity.py`，读取已发布 vocals，发布独立人声时间报告。
5. 曲库导入、补分析、校验、打包统一从 `preprocessing/cli/` 进入。

没有改变原音频时间轴、输出字段、模型阈值、算法版本号或 ADTOF 配置选择。

## 4. 哪些暂时不能直接删除

`app/modules/library/analysis.py` 和 `stem_analysis.py` 仍被业务后台及测试调用，保留为共享实现；不是重复复制到新目录。
旧 RMS `analysis_vocal_patch_gpu.py` 仍有后台调用，在旧后台替换之前不能删除。
`modules/` 是另一批独立抽取代码，有自己的基线和测试；需各负责人核对后再决定是否退役，不能按“重复文件名”批量删。
`mobile/` 不能认定就是用户新提供 APK 的源码；本次不据此重构客户端。
模型权重、标注、历史报告、音频均不属于无用代码删除对象。

## 5. 本轮没有做的事情

- 没删除或强推 66 个历史远端分支；没有更换 GitHub 默认分支。
- 没迁移线上数据库、没改 NAS 数据、没重跑模型、没切换 Jetson release。
- 没把其他人的未提交配置、APK 删除或本地实验输出加入提交。
- 没继续编写 APK / 新后端接口任务书；这是单独的后续工作。

因此本轮完成的是**当前分支的正式预处理与研究代码分区**，不是所有历史分支和所有产品模块的合并重写。

## 6. 后续如何保持整齐

- 新正式预处理 CLI 加到 `preprocessing/cli/`，不再往 experiments 或 scripts 塞完整实现。
- 新离线评测加到 `research/evaluation/`，风格训练加到 `research/style/`。
- schema 放 contracts；模型/歌曲放专用存储，不放 Python 源码目录。
- 旧兼容入口不得再增加业务函数；确认所有部署/协作者已迁移后，单独提交删除它们。
- 保留训练版本和数据划分，不借代码整理更新模型行为或伪造重新评测的报告。

完整静态文件清单见 [code-inventory.csv](code-inventory.csv)。它记录目录分区，不把“静态未发现调用”当成“确定无人使用”。

## 7. 本轮验证记录

- 33 个迁移实现与整理前提交逐文件核对：只变更导入路径、仓库根定位和运行器说明，未改算法表达式。
- 相关回归测试 **218 passed**；其中包括发布/人声/段落、研究辅助函数、目录约束、兼容模块身份和可执行入口检查。不是整个仓库的全部测试。
- 24 个研究命令均通过 `python -m ... --help` 检查；6 对新旧正式 CLI 均能从其他工作目录启动帮助命令。
- SongFormer 新入口和旧兼容入口均在现有隔离环境通过 `--help`，未进行 GPU 模型重分析。
- 3 个 Jetson 包装脚本通过 `bash -n`；当前导航文档内部链接检查通过。
- 测试出现 3 条已有音频依赖弃用警告（aifc/audioop/sunau），无测试失败。

目录回归命令：`python -m pytest -q tests/test_repository_layout.py tests/test_analysis_entry_cleanup.py`。
正式预处理回归主要入口：`tests/test_same_style_preprocess_publisher.py`、`tests/test_vocal_activity.py`、`tests/test_songformer_sections_integration.py`。
未进行：生产数据库写入、真实新歌分析、线上部署切换或 APK 测试。
