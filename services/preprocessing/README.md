# Jetson 完整预处理

这里保存 Jetson 实际发布目录 `same-style-preprocess-a268a5c-vocal-20260913` 的源码，原发布提交为 `a268a5c04791ee506bbf22a3e66557dcdd0272d2`。来源及每个文件的 SHA256 在 [SOURCE_INVENTORY.json](SOURCE_INVENTORY.json)。原发布标记不能代替完整校验；人声增补等部署文件以该清单为准。

包括基础节奏/调性/能量、SongFormer 段落、Demucs 四轨、MDX23C 鼓组、鼓组特征、Silero 人声时间区间和 NAS 原子发布。补充风格、情绪、和弦及可视化由仓库根目录的 `analysis_platform` 承担。

## 运行边界

这是一个独立 Python 源码根，先进入本目录。不要把本目录的 `app` 与仓库根的 `app` 同时放入同一进程的导入路径。保留这层隔离是为了保持现有部署行为，后续统一包名必须另做迁移测试。

使用 Jetson 的独立模型环境，按 [环境说明](deploy/JETSON_SETUP.md) 安装适配设备的 PyTorch/CUDA、FFmpeg 和模型。`requirements.txt` 是原运行依赖清单，不是已锁定的跨硬件安装包。原目录内的 `vendor/` 是安装后的 jsonschema 等第三方包，已排除；请通过依赖安装获取，包括它们的二进制轮子。

单曲入口（替换路径）：

```bash
cd services/preprocessing
/path/to/jetson-venv/bin/python scripts/run_same_style_preprocess.py \
  /path/to/song.wav --track-id track-example \
  --title 'Example' --style-label 'Hip Hop' \
  --root /path/to/nas/preprocess --device cuda --disable-adtof
```

本批次保留原来禁用 ADTOF 的运行选择；MDX23C 鼓组分离仍运行。不要把降级鼓事件当成完整模型检测。

- [完整预处理合同与字段](docs/same_style_preprocess_handoff_v1.md)
- [人声时间轴补充合同](docs/jetson_vocal_activity_handoff_v1.md)
- [批量曲库入口](scripts/import_same_style_library.py)
- [预处理实现](app/modules/library/same_style_preprocess.py)
- [人声发布实现](app/modules/library/vocal_activity.py)

调用方通过 `latest.json → manifest.json → _SUCCESS.json` 和 SHA256 读取已发布结果。重新分析创建新运行，不覆盖旧结果。模型权重、歌曲和服务器环境文件不在本目录中。
