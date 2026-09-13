# 正式预处理已经统一，不在这里维护第二份源码

唯一正式实现：[preprocessing](../../preprocessing/README.md)。

- BPM、Beat、小节、SongFormer 段落整合：[共享分析引擎](../../preprocessing/engines/README.md)。
- 发布、批量导入、人声报告：`preprocessing/publisher.py`、`preprocessing/cli/`、`preprocessing/vocal_activity.py`。
- 对外结果格式：`contracts/schemas/analysis/`。

本目录原有的 `harbeat_audio_preprocess` 旧实现、旧测试及打包配置已退役，不再作为可安装包。不要将历史 `dj_structure_v2` 候选结构当成当前 SongFormer 的替代品。
旧源码可从提交 `3482daf` 的同路径恢复；没有删除 Git 历史或远端标签，也没有修改线上 release。
