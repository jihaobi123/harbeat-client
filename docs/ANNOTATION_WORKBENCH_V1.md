# HarBeat 音乐段落标注工作台 V1

- 版本：1.0.0
- Dataset Version：`bar-understanding-1.0.0`
- 面向人员：音乐制作人、标签负责人、算法人员
- 当前用途：首批 20–30 首 Pilot 歌曲

## 1. 这套工具解决什么问题

制作人不需要直接改 JSON，也不用手算每一段的起止秒数。工作台会读取歌曲现有的 Beat、Downbeat、段落分析和分轨活动，先生成按小节对齐的建议。制作人听完对应片段后，只需框选连续小节，再确认或修改标签。

V1 只处理三类信息：

1. 歌曲的粗粒度段落；
2. 鼓、人声、贝斯、旋律在每段里的状态；
3. 元素的进入和结束。

这些标签先把“每个小节、每个 8 拍里有什么”这件事做扎实。Rap、808、细鼓件和全部 69 项特征留到 Pilot 之后，避免制作人一开始就面对过长的表单。

## 2. 开始前要准备什么

歌曲必须已经进入 HarBeat 曲库，并且至少有可用的 Beat Grid。没有 Beat Grid 时，工作台会明确报错，不会按固定 BPM 猜小节。

系统已有的数据会这样使用：

| 已有分析 | 在页面中的作用 |
|---|---|
| Beat、Downbeat、拍号 | 建立唯一的小节边界 |
| `phrase_map` | 给出段落建议 |
| `stem_activity_windows` | 给出鼓、人声、贝斯状态建议 |
| 没有直接旋律证据 | 旋律保持 `unknown` |

后端默认把标注保存在 `./data/annotations`。可以在 `.env` 中修改：

```env
ANNOTATION_DIR=./data/annotations
```

Docker Compose 已把 `/app/data/annotations` 挂到独立的 `annotation_data` Volume。更新容器或重启服务不会丢失标注。删除 Volume 会删除数据，执行 `docker compose down -v` 前必须另行备份。

## 3. 制作人的操作顺序

登录 Web 后，从左侧进入“标注工作台”。

1. 选择一首已经分析过的歌曲；
2. 在播放器中试听，必要时打开“循环所选”；
3. 第一次点击一个小节作为起点，第二次点击另一个小节作为终点；
4. 给这段设置 Section；
5. 分别选择鼓、人声、贝斯、旋律，设置它们的状态；
6. 对可靠的系统建议，可以直接点“采用系统建议”；
7. 完成后点“保存本首歌曲”。

页面中的范围对人显示为“第 3–6 小节”，保存时使用左闭右开区间 `[2, 6)`。也就是说，索引 2 包含在内，索引 6 不包含在内。秒数由系统根据同一套 Bar 时间轴填写，页面不提供自由输入。

有未保存修改时，歌曲选择框会锁住，防止误切歌曲。保存成功后，页面会显示新的 Revision。

## 4. 标签口径

### 4.1 Section

| 标签 | 制作人判断口径 |
|---|---|
| `intro` | 开场，为主体内容做铺垫 |
| `main` | 主体内容，包括 Drop、Verse、Chorus 等 V1 暂不细分的段落 |
| `build` | 明显积累张力、准备进入下一段 |
| `breakdown` | 能量或编配明显抽离的间歇段 |
| `outro` | 收尾，准备结束或退出歌曲 |
| `unknown` | 听过后仍无法稳定判断 |

### 4.2 元素状态

| 标签 | 制作人判断口径 |
|---|---|
| `absent` | 这一范围内没有该元素 |
| `background` | 元素存在，但不是听感主体 |
| `foreground` | 元素明显处于前景 |
| `entering` | 元素在这里开始进入 |
| `ending` | 元素在这里结束或退出 |
| `unknown` | 证据不足，暂时不能确定 |

`entering` 和 `ending` 不是独立的自由时间点，而是落在统一 Bar 范围上的状态。V1 先用这种方式服务后续混音；需要拍内精细事件时，再增加 event 级标注。

## 5. 系统建议和人工真值的边界

页面里的建议不是答案。数据状态必须按下面的顺序理解：

```text
candidate → annotated → reviewed / adjudicated
```

- `candidate`：来自公开数据或现有分析，只能帮助制作人；
- `annotated`：制作人已经听过并确认或修改；
- `reviewed`：另一位负责人完成复核；
- `adjudicated`：出现分歧后，指定负责人给出最终结论；
- `rejected`：该记录不能使用。

当前页面只能保存 `annotated`，标注人由后端根据登录账号填写，浏览器不能自行声明“已复核”或冒用其他标注人。正式监督训练默认只读取 `reviewed` 和 `adjudicated`。如果 Pilot 阶段为了快速看趋势临时使用 `annotated`，实验报告必须单独写明，不能把结果当作正式模型结论。

## 6. 文件和版本

每首歌对应一个文件：

```text
data/annotations/
└── bar-understanding-1.0.0/
    └── <track_id>.json
```

文件中包含 Track ID、Dataset Version、Timeline 指纹、Revision、更新时间和 `AnnotationRecord V1` 数组。保存时会先取得这首歌的文件锁，再完成读取、Revision 校验和原子替换。这样既能避免只写了一半，也能阻止两个同时到达的请求都以为自己保存成功。

如果 Beat、Downbeat、拍号或小节边界发生变化，Timeline 指纹也会变化。系统会拒绝把旧标注直接覆盖到新时间轴上。此时应建立新的 Dataset Version，并明确迁移或重标，不能改掉旧文件假装没有发生变化。

两个浏览器窗口打开同一首歌时，都从相同 Revision 开始。第一个窗口保存后，第二个窗口继续保存会收到 409 冲突。第二位制作人应重新加载，再决定如何合并，系统不会默认以最后一次保存为准。

## 7. API

工作台使用两个鉴权接口：

```text
GET /api/annotations/tracks/{track_id}/workspace
PUT /api/annotations/tracks/{track_id}/workspace
```

GET 返回歌曲、统一 Bar 列表、系统建议、已保存记录、Revision 和时间轴警告。PUT 接收完整标注集，并重新检查歌曲归属、任务类型、标签、Bar 范围、秒数和 Revision。

常见失败：

| 状态 | 含义 | 处理方式 |
|---|---|---|
| 403 | 当前账号不拥有这首歌 | 切换账号或确认曲库归属 |
| 404 | 曲库里找不到这首歌 | 重新选择或导入歌曲 |
| 409 | Revision 或 Timeline 已变化 | 重新加载，不要强行覆盖 |
| 422 | 没有 Beat Grid，或标注不符合合同 | 先修复分析结果或标注内容 |

## 8. Raveform 导入

仓库只提供元数据转换器，不会下载第三方音频，也不会把整套外部数据提交进仓库。

```bash
python scripts/import_raveform_annotations.py \
  --input /path/to/raveform-track.json \
  --output /path/to/raveform-candidates.jsonl \
  --dataset-version raveform-import-1.0.0
```

转换器接受 `start`、`start_sec` 或 `time`。缺少结束时间时，优先使用下一段的开始时间，最后一段使用歌曲时长。输出记录全部是 `candidate`，并在 `candidate_source` 中保留 Raveform 版本和原始标签。

外部标签会映射到 V1 的粗粒度标签。原始细标签不会丢，但映射结果不能直接当作 HarBeat 金标准。数据许可和音频许可要分别登记；没有确认商业训练权的数据不能进入生产训练清单。

## 9. 两人协作建议

首批 20–30 首歌按固定顺序推进：

1. 标签负责人先挑 3 首有代表性的歌，与制作人一起标；
2. 两人对 Section 和元素状态的边界案例达成一致，并把例子补进 Label Guide；
3. 制作人完成剩余歌曲的第一轮 `annotated`；
4. 标签负责人抽查候选修改率高、`unknown` 多、Timeline 有警告的歌曲；
5. 复核完成后再生成不可变 Dataset Manifest；
6. 算法人员用这个快照建立 MERT 离线缓存和第一版 Linear Probe。

建议每天记录三项数字：每首歌标注耗时、系统建议被修改的比例、`unknown` 的比例。这三项比一开始追求 69 项全覆盖更能说明工作台和标签口径是否有效。

## 10. 验收命令

后端相关测试：

```bash
python -m pytest \
  app/tests/test_annotation_public_datasets.py \
  app/tests/test_annotation_candidates.py \
  app/tests/test_annotation_store.py \
  app/tests/test_annotation_service.py \
  app/tests/test_annotation_router.py \
  app/tests/test_bar_feature_adapter.py \
  app/tests/test_music_analysis_contracts.py -q
```

前端状态测试和生产构建：

```bash
cd web
npm test
npm run build
```

一首固定样例完成“加载、框选、修改、保存、重新加载”后，且保存内容仍通过 `annotation_record_v1.schema.json`，V1 的单曲闭环才算通过。
