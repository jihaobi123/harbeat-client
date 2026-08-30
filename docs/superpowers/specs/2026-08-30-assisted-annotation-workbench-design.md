# HarBeat 辅助标注工作台 V1 设计

日期：2026-08-30  
状态：批准实施  
适用范围：工作流 B 的首批 20–30 首 Pilot 歌曲

## 1. 目标

V1 要把制作人的工作从“对着 JSON 或表格逐项填写”改成“听歌、框选小节、确认或修正系统候选”。页面最终保存的不是界面状态，而是符合 `harbeat.annotation_record` 1.0.0 的标注记录。

首批只做三类真值：

- 粗粒度 Section；
- `drums`、`vocal`、`bass`、`melody` 四类元素状态；
- 由 `entering`、`ending` 表达的元素进入和结束事件。

Rap、808、细鼓件、Groove 语义和全部 69 项特征不放进这个版本。它们需要另一套标签说明，提前塞进页面只会拖慢 Pilot。

## 2. 标签和判断口径

Section 使用已经写入开发合同的六个值：

```text
intro
main
build
breakdown
outro
unknown
```

Raveform 等外部数据保留原始细标签，同时映射到 V1：

| 外部标签 | HarBeat V1 |
|---|---|
| intro、ambient-intro | intro |
| buildup、build-up | build |
| drop、cooldown、bridge、verse、chorus、instrumental | main |
| breakdown、ambient-breakdown | breakdown |
| outro、ambient-outro | outro |
| 其他或无法判断 | unknown |

元素状态使用：

```text
absent
background
foreground
entering
ending
unknown
```

候选只能帮助标注，不能自动成为人工真值。制作人确认后，记录的 `annotation_status` 才从 `candidate` 变为 `annotated`。训练默认仍只读取后续复核产生的 `reviewed` 或 `adjudicated`。

## 3. 页面操作

制作人进入“标注工作台”后先选一首歌。页面加载音频、Bar 时间轴、现有分析候选和已经保存的标注。

主要操作如下：

1. 播放或循环试听目标片段；
2. 选择开始和结束 Bar；
3. 为所选范围设置 Section；
4. 选择一个元素，为所选范围设置状态；
5. 接受系统候选，或将无法判断的范围标为 `unknown`；
6. 保存。发生并发修改时，页面提示重新加载，不静默覆盖同事的结果。

时间范围使用左闭右开区间：`start_bar_index` 包含，`end_bar_index` 不包含。秒数取对应 Bar 的开始时间和结束时间。页面不允许自由输入秒数，避免破坏统一时间轴。

## 4. 后端结构

新增独立的 `app.modules.annotations` 模块，不继续扩大 `library.router`。

```text
app/modules/annotations/
├── candidates.py       # 把现有 BarFeature、phrase_map 转成候选
├── public_datasets.py  # 外部标签到 HarBeat 标签的确定性映射
├── schemas.py          # API 请求和响应模型
├── service.py          # 工作区组装、保存和版本检查
├── store.py            # 原子写入 JSON 文件
└── router.py           # 鉴权后的 GET/PUT 接口
```

候选来源：

- Bar 时间轴：`build_canonical_timeline()`；
- Section：现有 `phrase_map`，随后可接 Raveform 导入；
- Drums、Vocal、Bass：`stem_activity_windows` 聚合后的 Bar activity；
- Melody：没有直接证据时保持 `unknown`，不把 Demucs 的 `other` 冒充旋律。

活动分数到候选状态的阈值只用于预标注：

```text
activity < 0.15       -> absent
0.15 <= activity < .65 -> background
activity >= 0.65      -> foreground
```

相邻 Bar 从低活动变为明显活动时建议 `entering`，反向变化时建议 `ending`。候选的来源和阈值版本要写进 `candidate_source`。

## 5. 保存方式

Pilot 期间不用新建数据库表。标注是训练数据资产，按 Dataset Version 写到独立目录更容易归档和检查：

```text
data/annotations/
└── bar-understanding-1.0.0/
    └── <track_id>.json
```

每个文件保存：

- Dataset Version；
- Track ID；
- Timeline 指纹；
- 单调递增的 Revision；
- `AnnotationRecord V1` 数组；
- 更新时间。

写入使用临时文件加原子替换。保存请求必须带客户端看到的 Revision；版本不一致返回 409。Timeline 指纹变化时拒绝把旧标注原地对齐，要求新建 Dataset Version。

## 6. API

```text
GET /api/annotations/tracks/{track_id}/workspace
PUT /api/annotations/tracks/{track_id}/workspace
```

GET 返回歌曲信息、Bar 列表、候选、已保存标注、Revision 和 Timeline 警告。

PUT 接收 Dataset Version、Revision 和完整标注数组。后端重新校验：

- Track ID 与 URL 一致；
- Bar 和秒数在当前时间轴内；
- Task ID、Section 和元素状态属于 V1；
- AnnotationRecord 符合 JSON Schema；
- 用户拥有该歌曲。

## 7. 公开数据导入

V1 先实现 Raveform Section 的纯转换器，不在仓库里保存第三方音频或整套数据。转换器接受 Raveform 的 track/section JSON，输出 `candidate` 状态的 `AnnotationRecord V1`。原始标签写进 `candidate_source`，用于追踪映射。

外部数据的标签许可和音频许可分开登记。只有 `commercial_training_allowed=true` 且音频来源经过确认的数据，才能进入生产训练清单。

## 8. 验收

V1 通过以下条件才算完成：

- 有 Beat Grid 的歌曲能打开工作区；
- 没有可靠 Beat Grid 时明确失败，不伪造 Bar；
- Section 和三类有证据的元素显示候选；
- 制作人能给连续 Bar 批量设置标签；
- 保存结果通过 `annotation_record_v1.schema.json`；
- 两个浏览器窗口不会静默互相覆盖；
- 页面构建通过，后端相关测试通过；
- 用固定样例完成一次加载、修改、保存、重载闭环。

## 9. Pilot 后再做

Pilot 结束后再决定是否增加波形缩放、快捷键、多人复核、双盲仲裁、MERT 不确定性采样和更多公开数据导入器。先记录制作人完成一首歌所需时间，以及被修改的候选比例，再决定下一轮投入。
