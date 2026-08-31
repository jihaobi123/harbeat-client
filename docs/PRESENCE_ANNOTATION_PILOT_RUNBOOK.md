# Presence 标注 Pilot 操作说明

这份说明用于完成阶段 3 的第一轮数据闭环：Jetson 生成四轨 Stem，系统按 Bar 产出 Vocal、Drums、Bass、Melody 候选，人完成纠错后导出训练用 JSONL。

## 1. Pilot 的完成标准

第一批选 10 首歌，尽量覆盖以下情况：纯音乐、密集人声、说唱或短句人声、鼓点稀疏、贝斯较弱、旋律乐器明显，以及段落边界容易听错的歌曲。

每首歌保存前需满足：

- Vocal、Drums、Bass 都已选择“已复核”；没有出现时保留空区间，但状态仍需是“已复核”。
- Melody 可以选择“已复核”或“无法判断”，不能把 `other` Stem 的活动直接当成旋律真值。
- 每段边界都吸附到 Bar，区间使用左闭右开表示，例如 `[4, 8)` 是第 5 至第 8 小节。
- 页面显示的 Revision 已在保存后增加，刷新页面仍能看到相同结果。

## 2. 开始前检查

在 Jetson 上进入 HarBeat 仓库，确认 API 和 Worker 正常运行，并确认 `ANNOTATION_DIR` 指向持久化目录。未显式设置时使用 `./data/annotations`。

先在曲库详情页检查：

1. 歌曲分析状态为完成，并且有可靠的 downbeat 或 beat grid。
2. “音轨分离”下能播放 `vocals`、`drums`、`bass`、`other` 四个 Stem。
3. 切换 Stem 时长度一致，没有提前结束、明显错位或损坏。
4. 页面出现“元素出现区间审核”。

如果歌曲还没有 Stem，点击“开始分离”。分离成功后系统会自动尝试生成 Presence 候选；候选失败不会让 Stem 任务回滚。

## 3. 单曲审核

进入歌曲详情页后按下面的顺序操作：

1. 如果显示“这首歌还没有机器候选”，点击“生成机器候选”。
2. 先听原曲，再依次单听人声、鼓点、贝斯和 `other`。切换音源会保留当前播放位置。
3. 从 Vocal 开始逐轨检查机器色块和人工实线区间。
4. 拖过连续 Bar 可新增区间；拖动左右手柄可改边界；双击删除；按住 Shift 点击区间内部可拆分；Cmd/Ctrl 多选后可合并。
5. 点击区间会循环试听该段。再次点击相同区间停止循环。
6. 对整首歌确认后，将该元素设为“已复核”。听不清的 Melody 选择“无法判断”，不要用空区间冒充“没有旋律”。
7. 点击“保存人工修订”。出现版本冲突时刷新后重新核对，不覆盖别人的新修订。

常用快捷键：Space 播放或暂停，`[` / `]` 切换前后 Bar，Delete 删除当前区间，Cmd/Ctrl+Z 撤销，Cmd/Ctrl+S 保存。

单曲结果可用“导出 JSONL”下载。下载内容只包含状态为 `reviewed` 或 `adjudicated` 的区间。

## 4. 批量汇总 10 首 Pilot

在仓库根目录运行：

```bash
python scripts/export_presence_pilot.py \
  --annotation-dir data/annotations \
  --output outputs/presence-pilot-1.0.0.jsonl \
  --report outputs/presence-pilot-1.0.0-report.json
```

脚本会读取 `<annotation-dir>/<user-id>/<track-id>/bar-presence-1.0.0.json`，验证 bundle，再生成：

- `presence-pilot-1.0.0.jsonl`：最新人工修订里的 reviewed/adjudicated 真值；
- `presence-pilot-1.0.0-report.json`：歌曲数、Bar 数、各元素区间数、候选原样接受率、人工新增/删除/边界调整、不可用元素和待处理原因。

汇总后检查报告：

- `tracks_total` 应为 10；
- `tracks_unreviewed` 应为 0；
- Vocal、Drums、Bass 的 `unavailable_tracks` 应为 0；
- `needs_review` 中不能残留前三类的 `unknown` 或 `rejected`；
- JSONL 中不应出现 `candidate` 状态。

候选接受率只反映机器区间是否被原样保留，不等于准确率。边界调整、人工新增和删除要结合抽样复听判断。

## 5. 异常处理

### 时间轴需要复核

出现 downbeat 不足、节拍置信度低或 Bar 时间轴无效时，先修正 downbeat/beat grid，再把 `PRESENCE_DATASET_VERSION` 提升到新版本后重新生成。系统会把旧 bundle 和人工修订保存在曲目目录的 `versions/` 下，再创建 Revision 1 的新时间轴。不要为了继续标注手工伪造 Bar，也不要把旧时间轴上的区间静默搬到新时间轴。

### Stem 缺失或错位

先重跑音轨分离并确认四轨长度、采样率一致。某类 Stem 不可用时保留明确的 unavailable/unknown 状态，不导出空区间作为真值。

### Jetson 暂时离线

已经生成并保存在 API 主机上的 Stems 和标注 bundle 仍可继续审核。需要新分离的歌曲等待 Jetson 恢复，不把重计算转移到 RK3588。恢复后从失败歌曲继续，不需要重做已经保存的人工修订。

### 保存提示版本冲突

说明其他人已经保存了更高 Revision。刷新读取最新修订，重新检查自己的修改，再保存新版本。不要直接改 bundle 文件或降低 Revision。

## 6. Pilot 留档

Pilot 完成后一起保存：

- 10 首歌曲 ID 和覆盖场景；
- 批量 JSONL 与报告 JSON；
- `dataset_version`、`candidate_source`、`threshold_version`；
- 审核人和二次裁决人；
- 发现的系统性错误，例如弱贝斯漏检、鼓点泄漏到 Vocal、Melody 对 pad 过敏。

这些记录将决定下一轮先调阈值、修 Stem，还是增加标签定义，不应只保留一个“准确率”数字。
