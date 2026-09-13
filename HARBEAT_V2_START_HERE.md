# HarBeat 第二版：开发统一入口

更新：2026-09-13。**第二版指整个系统，不只是手机，也不是重写已有预处理。**
已有 BPM、分轨、鼓组、段落、人声模块及部分数据库代码继续复用。
第二版业务连接层仍需补齐，不能把“预处理完成”等同于“手机选歌到 RK 已全部打通”。

## 当前代码已经怎样分区

- **正式预处理：[`preprocessing/`](preprocessing/README.md)**。第一批 9 个入口/发布实现，加第二批 20 个共享引擎实现；部署脚本已改，线上未切换。
- **离线评测和风格训练：[`research/`](research/README.md)**。24 个研究脚本已从 scripts 移走。
- 业务后端留在 [`app/`](app/README.md)，共享分析引擎已迁出；MDX23C 继续在 `music_analysis/drum_analysis/`，没有复制第二份模型实现。
- **[代码地图](docs/repository/README.md)** 包含两批逐文件迁移表；原静态清单是第一批整理时的快照，不是实时部署清单。
- **[部署位置](docs/repository/deployment-map.md)** 区分设备职责、上次核对的线上位置与尚未部署的新源码。
- **[当前 modules 清单](modules/REGISTRY.md)**：旧预处理/分轨包已移除，其余 11 个模块同步已核对的远端后续实现；具体采用边界见 [处置表](docs/repository/module-decisions.md)。不是完整新 APK/RK 集成版本。

本次只整理仓库源码，未切换 Jetson 线上部署，也没有继续设计 APK 接口。
新后端按新 APK 和当前预处理合同重构，不要求兼容旧手机 API；新 APK 源码待用户上传，旧 mobile 不作为新 App 的依据。

当前代码所在远端分支：`archive/music-analysis-history-20260830`。
这个名字有历史原因，但本分支包含现行预处理；不要因 `archive` 字样删除它，也不要从旧 `main` 判断最新能力。
本次不覆盖 `main`、不改默认分支、不删除历史分支。

```bash
git clone --single-branch --branch archive/music-analysis-history-20260830 \
  https://github.com/jihaobi123/harbeat-client.git harbeat-v2
cd harbeat-v2
```

## 按职责阅读

| 负责人 | 从哪里开始 | 边界 |
|---|---|---|
| 后端负责人 | [第二版后端交接与实施顺序](docs/v2/backend-owner-handoff.md) | 手机业务接口、Jetson/数据库、服务端资产授权/同步任务；不写 RK 音频引擎 |
| 混音 / RK 负责人 | [预处理数据消费入口](docs/v2/preprocess-consumer.md) | 获取完整版本化资源；混音算法与 RK 实现由用户负责 |
| 前端负责人 | 后端交接中的接口草案与联调验收 | 新 APK 是仓库外独立提供的前端产物，不以旧 `mobile/` API 为约束 |
| 分析模块维护者 | [代码分层与清理记录](docs/repository/README.md) | 只从当前入口运行；研究实验不自动替代正式模型 |

## 系统分工

手机选歌 → 阿里云 HTTPS 入口 → Jetson 业务 API / 数据库

Jetson 预处理 → NAS 不可变分析结果及音轨

RK 经手机热点主动领取任务 → 经公网入口下载获准资源 → 本地校验、混音、播放

手机热点只是网络接入，不要求手机 App 下载音轨再转发。
戒指/手环与 RK 的控制不属于后端负责人的任务。

## 当前算法与合同

- 正式段落：SongFormer；All-In-One 仍参与 BPM/Beat/Downbeat，段落只作明确标记的失败回退。
- 分轨：Demucs；鼓组子轨：MDX23C；当前曲库导入关闭 ADTOF。
- 人声时间段：Demucs vocals → Silero VAD。它标记时间，不重新分离人声，也不保证歌唱边界已获人工验收。
- 风格取用户目录标签；不新增自动风格判定。段落分类器实验不作为默认输出。
- 第二版复用 `same_style_track_preprocess 1.2.0`、人声报告 `harbeat_vocal_activity 1.0.0`，**产品第二版不等于所有 JSON 改成 2.0**。

权威数据合同：[基础预处理](docs/same_style_preprocess_handoff_v1.md)、[人声增补](docs/jetson_vocal_activity_handoff_v1.md)。
文件名带 `v1` 不代表这两份发布合同已废弃；旧业务开工草案 `docs/backend-handoff-v1/` 则仅作历史参考。

截至本次只读核对，NAS 基础曲库 157 首已发布（均带 degraded 状态，需看具体质量标记），Silero 报告 157 首已生成并通过交付校验。生成成功不等于准确率验证完成。

## 本轮清理范围

此前归档两个旧分析入口；第一批迁移 33 个实现，第二批迁移 21 个共享实现（20 个分析实现和 1 个命令工具），更新调用与测试。
第三批去掉 modules 的两套重复旧分析包，保留唯一正式预处理，其他 11 个模块采用已核对的后续实现。旧源码仍可从 Git 历史恢复，不再在当前目录保留第二份。
没有清空实验数据目录、删除模型/训练数据、重跑歌曲或改动线上服务。
完整远端盘点见 [审计记录](docs/repository-audit-20260913/README.md)。
