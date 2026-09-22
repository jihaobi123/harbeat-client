# V3 局部风格与持续能量筛选

本模块在原始分析旁边生成 `mixProfile`，不修改原有曲线、SongFormer 段落、拍点、人声区间、规则标签和人工标签。V3 淡化、EQ、速度素材、缓存截止时间和音频线程计时保持原逻辑。

## 输入与部署

输入为现有实时 `catalog.json` 与完整预处理报告；新增档案必须绑定同一个 master SHA256。原始报告的文件哈希、模型文件哈希、补充模型侧车哈希及来源时间区间进入日志。没有模型或测量时，普通“下一首”仍可使用原有执行规则，风格／能量请求不会用整曲标签或相对曲线替代。

```sh
# 在仓库根目录、现有模型解释器中运行；输出目录与输入分开。
ANALYSIS_TF_BACKEND=python python -m scripts.build_mix_profiles \
  --catalog /path/existing/catalog.json --reports /path/reports \
  --output /path/new/catalog.json --sidecars /path/new/sidecars \
  --audio-root /path/preprocess --models-dir /path/models \
  --embedding-cache-dir /path/cache --infer
```

不加 `--infer` 时只读取已经存在的同身份侧车，否则显示原有粗粒度候选并标记待确认。`build_realtime_assets` 已自动附加基础档案；精确局部风格通过上述第二步补算。模型分析在 Jetson 独立任务中运行，不修改主服务环境。现阶段新增可试听演示覆盖原 V3 六首；不据此宣称 NAS 全曲库已经补算完成。

## 按原始乐段与交接窗口对齐

- 段落直接引用原有起止时间和索引，截到实际试听素材时长。名称与边界仍是待核对候选。
- 每个 B 接入窗口分别记录进入区间、接管后16秒、覆盖的原始段落，以及4组连续4秒的能量测量。
- Discogs400 直接分析这些原曲区间，原始400类分数保存于侧车。重叠窗口的全局平均没有用于选歌。
- 短于8秒、模型第一名低于0.10、第一二名差低于0.015，或有效patch少于3的区间为“待确认”。这些阈值是实验规则，不是准确率或统计置信度。
- 进入片段可以待确认；当用户指定风格时，接管后完整16秒必须有符合目标的局部第一候选。没有足够证据就拒绝这一个窗口，保留当前播放。

## 能量比较的明确口径

之前的曲内相对能量保留作诊断。新的统一标尺是原曲的数字满刻度 RMS 功率（dBFS），直接从既有50ms测量在线性功率域计算窗口；0.5秒序列仅供展示。它能比较信号强弱；它不是已经通过听感实验标定的“兴奋度”，也不能替代鼓密度、节奏或情绪判断。

每个可执行退出候选单独比较：A 实际混入点前4秒，与 B 正文接管后4组4秒。二者沿用相同 V3 主增益；比较没有施加改变响度的额外增益。升／降请求要求每组至少增／减1dB，同时任何一组不得跳变超过6dB。16秒不完整、测量覆盖低于98%、标尺不同或来源不符时拒绝。固定阈值应随试听数据调整，不能当作通用听感定律。

这是用于规划的原曲窗口预测，不是对混音输出、声卡或蓝牙的实际测量。用户在16秒内再次发出请求会重新规划，不能把持续性预测理解为强制保持播放16秒。

## 联合筛选与日志

`Intent` 可以同时携带 `style`、`energy=up/down/any` 与指定歌曲。候选先满足原有素材、变速范围、拍点、等待期限、人声证据和可用正文条件，再检查局部风格和能量持续性。排序仍沿用 V3 人为规则，整曲同风格项只保留小权重加分，不代替局部风格硬筛选。

逐次日志新增 A/B 具体测量区间、四个差值、进入／接管风格候选与待确认理由、来源与规则版本。失败候选保留原始 A 混入／退出时刻及证据；同一类排除原因可以聚合计数，但 samples 保留具体候选。原有计划时间／音频线程观察时间仍保留。

## 验证

- Python：`python -m pytest tests/test_mix_profiles.py tests/test_analysis_styles.py tests/test_realtime_assets.py -q`
- 网页：`npm --prefix web test -- --run src/realtime --no-cache`
- 构建：`npm --prefix web run build:live`
- 真实目录遍历：`LIVE_CATALOG=/path/catalog.json LIVE_AUDIT_OUTPUT=/path/audit.json npm --prefix web test -- --run src/realtime/realCatalog.test.ts --no-cache`

真实曲目遍历只验证规则、来源与可执行候选，不证明风格准确或混音更好听。最终选择效果需要试听核对。
