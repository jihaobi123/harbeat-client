# 当前模块入口：不再保留两套预处理源码

2026-09-13 按“保留最新、去掉旧版”整理。本目录现在有 **11 个保留的模块包 + 2 个正式预处理导航目录**。

## 预处理只维护这一套

- BPM / Beat / 小节 / SongFormer 段落：[preprocessing/engines](../preprocessing/engines/README.md)。
- Demucs、发布、批量入库：[preprocessing](../preprocessing/README.md)。
- MDX23C：[music_analysis/drum_analysis](../music_analysis/drum_analysis/README.md)。
- Silero：`preprocessing/vocal_activity.py`。

`audio-preprocess/`、`stem-separation/` 只保留 README 导航，原有旧源码、测试、打包合同已经移除。正式代码使用的特征 v5 schema 移到 contracts，内容未改。

## 其余 11 个模块

**这 11 个模块都是第一版实现（含后续维护版本），第二版不一定需要，必须逐项确认是否采用。** 保留较新源码仅供评估，不代表它们是第二版必做功能。

确认时由对应负责人选择“不采用 / 复用并适配 / 重写”，记录决定和负责人后再安排开发。未确认前，不默认接入或部署，也不把旧接口、旧混音流程作为新 APK 或第二版后端的约束。

此备注只针对下列 11 个保留模块，不改变已明确采用的 BPM、SongFormer、Demucs、MDX23C、Silero 正式预处理方案。

逐项版本与职责见 [当前清单](REGISTRY.md)，机器记录见 [CURRENT.json](CURRENT.json)。

已核对远端 v0.2、部署 v0.3、clean-core 后续版本，选择 `rewrite/clean-core-operation-v0.4` 提交 `15b8663` 的相应模块实现替换本目录旧版本。没有合并该分支的其他目录，也没有让旧基础分析覆盖当前 SongFormer 流程。

这里的“保留”表示只保留已核对的较新源码，**不是已经完成新 APK / 新 RK 算法适配或线上部署**。新 APK 的接口不受这些模块原有的手机 API 限制。旧服务端预渲染假设也不作为 V2 后端要求。

## 测试

在已安装测试依赖的 Python 环境、仓库根目录运行：

```bash
python scripts/test_current_modules.py
python scripts/test_current_modules.py --module library-catalog
python scripts/test_current_modules.py --module preprocessing
```

每个 Python 模块在独立进程中用 pytest 收集 unittest 和 pytest 两类测试，避免漏测新增函数或同名测试冲突。Dart 控制模块需要本机 Dart；它不是新 APK 的源码或页面验收。

旧 PowerShell 测试入口现在转发到这个统一入口。历史版本不另留一套源码，可从 Git 提交 `3482daf` 或原不可变标签恢复。远端分支和标签没有删除。
