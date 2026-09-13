# 仓库代码地图与本次实际整理

更新：2026-09-13。此文只说明代码位置和清理范围，不设计手机接口、不宣称线上已切换版本。

最新确认：**旧后端、手机、RK 和操作控制代码只作第一版参考，第二版后续重构，预计不直接使用。** 目录定位与备注清单见 [参考代码与重构边界](reference-code.md)。下文分批验证记录描述当时整理，不等于第二版业务开发完成。

## 1. 先按工作找目录

| 你要维护什么 | 现在从哪里进去 | 当前边界 |
|---|---|---|
| 正式预处理 | [preprocessing](../../preprocessing/README.md) | 9 个编排/运行实现 + 20 个共享引擎实现已迁入 |
| MDX23C 鼓组 | `music_analysis/drum_analysis/` | 已有独立实现，继续复用，不复制 |
| Web 后端和已有数据库模型 | [app](../../app/README.md) | 核心共享引擎已迁出；其余第一版参考，后续重构，不默认沿用旧表 |
| 发布数据格式 | `contracts/schemas/analysis/` | 现有预处理/人声 schema 保持不变 |
| Jetson 运行与部署 | `deploy/jetson/` | 仓库脚本改用新目录；未重启或替换线上服务 |
| 评测和风格训练 | [research](../../research/README.md) | 24 个研究脚本已从常用 scripts 目录移走 |
| 原实验数据和模型 | [experiments](../../experiments/README.md) | 保留模型、数据集、固定报告、MERT 复现入口 |
| 运维和旧命令兼容 | [scripts](../../scripts/README.md) | 标明哪些会写数据库、哪些是转发入口 |
| 独立模块 | [modules 当前清单](../../modules/REGISTRY.md) | 两个重复分析包已退役；其余 11 个为第一版实现，第二版不一定需要，全部待确认，不作必做要求 |
| 原客户端 / RK | `mobile/`、`web/`、`rk_deploy/`、`jetson/`、`cypher-integration/` | 第一版参考，入口已备注；第二版后续重构，预计不直接使用 |
| 已退役入口 | `archive/analysis-v1/` | 原 All-In-One 对比脚本和旧 RMS 补分析入口，保留可追溯副本 |
| 测试 | `tests/`、`app/tests/` | 导入路径已同步；新增目录/兼容性回归测试 |

## 2. 这次不是只新增说明文件

第一批迁移 **33 个 Python 实现**：

- 正式预处理 9 个，统一到 `preprocessing/`；旧路径只留转发，不保留第二份业务逻辑。
- 专项评测 17 个，移到 `research/evaluation/`。
- 风格研究 7 个，移到 `research/style/`。
- 更新实际调用方、测试及 Jetson 包装脚本；调整迁移文件的仓库根目录解析，保持模型/schema/数据路径正确。

逐文件对应关系见 [迁移表](moves-20260913.json)。旧提交的源码仍在 Git 历史中。
第二批另迁移 **21 个共享实现**：20 个分析/特征/校准模块到 `preprocessing/engines/`，1 个命令解析工具到 `music_analysis/command_line.py`。原 app 路径只转发，生产调用和评测导入同步，见 [引擎迁移表](moves-engines-20260913.json)。
脚本迁移仅允许导入路径、相对根目录及运行器说明文字变化；迁移时逐一与整理前源码核对，未改算法表达式。

## 3. 正式路径现在怎么串起来

1. `preprocessing/cli/run_same_style_preprocess.py` 接收一首歌及配置。
2. `preprocessing/publisher.py` 调用已有核心分析、Demucs、轨道特征和 MDX23C，校验后发布基础结果。
3. 核心分析 `preprocessing/engines/analysis.py` 调用 `preprocessing/runners/songformer.py`；仍保留 All-In-One 节奏参与和显式失败回退。
4. 单曲 CLI 再调用 `preprocessing/vocal_activity.py`，读取已发布 vocals，发布独立人声时间报告。
5. 曲库导入、补分析、校验、打包统一从 `preprocessing/cli/` 进入。

没有改变原音频时间轴、输出字段、模型阈值、算法版本号或 ADTOF 配置选择。

## 4. 哪些暂时不能直接删除

`app/modules/library/analysis.py`、`stem_analysis.py` 等旧路径仍可能被旧服务或外部脚本调用，保留为同一引擎的兼容转发，不能提前删除。
旧 RMS `analysis_vocal_patch_gpu.py` 仍有后台调用，在旧后台替换之前不能删除。
用户确认后，modules 内两个重复分析包已从当前分支移除；其余模块采用已核对的后续版本，见 [逐项处置](module-decisions.md)。旧实现保留在 Git 历史，不再双份维护。
`mobile/` 不能认定就是用户新提供 APK 的源码；本次不据此重构客户端。
模型权重、标注、历史报告、音频均不属于无用代码删除对象。

## 5. 本轮没有做的事情

- 没删除或强推 66 个历史远端分支；没有更换 GitHub 默认分支。
- 没迁移线上数据库、没改 NAS 数据、没重跑模型、没切换 Jetson release。
- 没把其他人的未提交配置、APK 删除或本地实验输出加入提交。
- 没继续编写 APK / 新后端接口任务书；这是单独的后续工作。

当前完成的是**正式预处理/研究分区、共享引擎从 app 抽离，以及 modules 旧重复包退役/后续版本同步**，不是完整 V2 后端、客户端重构或整分支合并。部署状态见 [部署说明](deployment-map.md)。

## 6. 后续如何保持整齐

- 新正式预处理 CLI 加到 `preprocessing/cli/`，不再往 experiments 或 scripts 塞完整实现。
- 新离线评测加到 `research/evaluation/`，风格训练加到 `research/style/`。
- schema 放 contracts；模型/歌曲放专用存储，不放 Python 源码目录。
- 旧兼容入口不得再增加业务函数；确认所有部署/协作者已迁移后，单独提交删除它们。
- 保留训练版本和数据划分，不借代码整理更新模型行为或伪造重新评测的报告。

第一批静态文件快照见 [code-inventory.csv](code-inventory.csv)；第二批位置变化以引擎迁移表为准。它不是实时清单，不把“静态未发现调用”当成“确定无人使用”。

## 7. 第一批验证记录（第二批记录见下节）

- 33 个迁移实现与整理前提交逐文件核对：只变更导入路径、仓库根定位和运行器说明，未改算法表达式。
- 相关回归测试 **218 passed**；其中包括发布/人声/段落、研究辅助函数、目录约束、兼容模块身份和可执行入口检查。不是整个仓库的全部测试。
- 24 个研究命令均通过 `python -m ... --help` 检查；6 对新旧正式 CLI 均能从其他工作目录启动帮助命令。
- SongFormer 新入口和旧兼容入口均在现有隔离环境通过 `--help`，未进行 GPU 模型重分析。
- 3 个 Jetson 包装脚本通过 `bash -n`；当前导航文档内部链接检查通过。
- 测试出现 3 条已有音频依赖弃用警告（aifc/audioop/sunau），无测试失败。

目录回归命令：`python -m pytest -q tests/test_repository_layout.py tests/test_analysis_entry_cleanup.py`。
正式预处理回归主要入口：`tests/test_same_style_preprocess_publisher.py`、`tests/test_vocal_activity.py`、`tests/test_songformer_sections_integration.py`。
未进行：生产数据库写入、真实新歌分析、线上部署切换或 APK 测试。

## 8. 第二批验证与后续顺序

- 21 个共享实现与整理前 `bca4f94` 对比，除导入路径和仓库根定位外内容一致。
- 相关 pytest **351 passed**，4 条已有依赖弃用/合成音频警告；不包含全仓库测试或真实 GPU 推理。
- 三个历史高重叠模块原测试：audio-preprocess 7、stem-separation 5、library-catalog 8，全部通过。原实现未修改，不代表已与正式代码合并。
- 新增引擎无 app/数据库依赖、旧新模块身份一致、配置路径正确、发布器选择正确实现的回归检查。
- 测试文件列表及未执行项目见 [可复现验证记录](engine-cleanup-validation.json)。

原定后续计划已按用户最新要求调整：先将旧 app、手机、RK 整理为参考区，不开展这些部分的重构。待新前端源码和职责确认后重新设计。远端分支合并、删除和默认分支切换需另行确认；本轮没有执行。

## 9. 第三批：用户确认去旧留新

- modules/audio-preprocess 和 modules/stem-separation 旧包退役，只留导航；当前正式预处理不变。
- 其余 11 个模块从已核对远端提交 15b8663 同步，只导入对应模块，未合并整个历史分支。
- 原始文件指纹、文本等价规则与版本记录在 modules/CURRENT.json。历史格式文件只迁移仍有正式测试引用的特征 v5 schema。
- 独立测试入口 scripts/test_current_modules.py：10 个 Python 模块共 124 项、Dart 控制逻辑 11 项、正式预处理与目录约束 85 项通过，共 12 个测试组。不是线上设备验收。
- 未删除任何线上服务、数据库表或用户数据。旧代码可按 Git 提交 3482daf 的文件路径恢复。
- 新后端不以兼容旧手机 API 为目标；新 APK 源码待用户提供，本轮不设计其接口。
- 扩展正式分析回归 358 项通过（包含上述 85 项，不能重复相加），4 条已有警告。完整命令与验证范围见 [本批验证记录](module-cleanup-validation.json)。
