# SongFormer 全标签纠正器：标注、训练和上线

## 目标

SongFormer 继续提供段落边界和八类原始概率。HarBeat 的小型线性分类器只调整名称，不允许移动边界。原始标签、候选概率、纠正建议和最终标签全部分层保存。

标签集合固定为：

- `intro`（前奏）
- `verse`（主歌）
- `chorus`（副歌）
- `bridge`（桥段）
- `instrumental`（器乐段）
- `outro`（尾奏）
- `silence`（静音）
- `pre-chorus`（预副歌）

## 当前数据划分

- 开发集：`style_reference_v0/audio` 下 13 个风格、共 65 首。
- 锁定测试集：EDM 抽样目录中的 8 首。
- 所有交叉验证按歌曲分组，绝不随机拆分同一首歌的段落。
- 8 首测试歌只在模型、特征和阈值锁定后评估一次。

## 人工只需要做什么

启动本地标注页：

```bash
/Users/xueyawen/xywfiles/harbeat/harbeat-client/.venv/bin/python \
  scripts/section_label_workbench.py \
  /Users/xueyawen/xywfiles/harbeat/section_relabel_v1/annotations.json
```

浏览器中逐段操作：

- 标签正确：按 `A`。
- 标签错误：按数字 `1`–`8` 选择正确标签。
- 无法确定：按 `U`，该段不进入训练。
- 边界本身有问题：按 `B`，该段不进入标签训练。
- 空格播放当前段落；页面也可以播放整首歌和前后文。

大部分正确段落只需按一次 `A`。标注结果每次点击后立即原子写入 `annotations.json`，中断后可继续。
每次保存前都会执行与训练脚本相同的数据结构校验，并把上一次有效文件备份为
`annotations.backup.json`。因此标注页能保存的数据，训练脚本就能读取；字段缺失、非法标签、
概率维度错误、时间边界错误和互相矛盾的标注会在保存时直接拒绝。

## 标注口径

- `chorus`：整首歌主要 hook 或记忆点，通常在旋律、歌词或编曲上重复；强度高不是充分条件。
- `verse`：承担叙事，重复时歌词通常变化；长主歌后半段即使能量增强，也不因此自动变成副歌。
- `pre-chorus`：连接主歌与副歌并产生推进，通常直接出现在副歌之前。
- `bridge`：通常在中后段出现的一次性对比材料，之后返回主歌或副歌。
- `instrumental`：没有持续主唱；短促喊声、采样或背景和声不一定否定器乐段。
- `intro` / `outro`：分别承担开场和收束功能，不能只按音色判断。
- `silence`：没有有效音乐活动，不是普通的低能量段落。

对不确定段落不要强行选择。所有人工修改段、低信心段，以及随机 10%–20% 的“接受原标签”段应由第二人复核。

## 训练

标注完成后，可先独立检查数据（正式训练也会再次执行同一检查）：

```bash
/Users/xueyawen/xywfiles/harbeat/harbeat-client/.venv/bin/python \
  scripts/validate_section_relabel_dataset.py \
  /Users/xueyawen/xywfiles/harbeat/section_relabel_v1/annotations.json \
  --require-audio \
  --require-development-complete \
  --require-test-complete
```

然后运行：

```bash
/Users/xueyawen/xywfiles/harbeat/harbeat-client/.venv/bin/python \
  scripts/train_section_relabeler.py \
  --dataset /Users/xueyawen/xywfiles/harbeat/section_relabel_v1/annotations.json \
  --model-output config/model_validation/songformer_section_relabeler_v1.json \
  --report-output /Users/xueyawen/xywfiles/harbeat/section_relabel_v1/training_report.json
```

训练脚本自动完成：

1. 过滤不确定、边界错误和默认低信心段落。
2. 在 65 首开发歌上做五折歌曲级交叉验证。
3. 搜索正则化强度。
4. 从交叉验证预测选择“至少 10 次修改且修改准确率至少 90%”的安全覆盖阈值。
5. 在全部开发集上训练最终模型。
6. 导出纯 JSON 权重；正式推理只依赖 NumPy，不依赖 scikit-learn。
7. 只有 8 首测试歌全部审核时，才生成一次锁定测试结果；`U`、`B` 和默认的低信心段
   会计入已审核，但明确列为排除项，不会导致测试集永远无法完成。

重点查看报告中的：

- `fixed_errors`：原来错误、现在修好的段落数。
- `introduced_errors`：原来正确、现在改错的段落数。
- `net_gain`：前两项之差，必须大于零。
- `override_precision`：自动修改中正确修改的比例。
- `macro_f1`：避免只提升常见标签、损害稀有标签。

## 影子模式与正式启用

默认配置：

```dotenv
SECTION_RELABELER_ENABLED=true
SECTION_RELABELER_SHADOW_MODE=true
```

影子模式会保存纠正器建议和概率，但产品标签仍保持 SongFormer，适合真实歌曲复核。验证通过后改为：

```dotenv
SECTION_RELABELER_SHADOW_MODE=false
```

模型不存在、JSON损坏、特征版本不一致或置信度不足时，系统均自动保留 SongFormer 标签。删除或移走模型文件即可完全回退。

## 发布门槛

- 所有段落 `start/end` 与 SongFormer 完全一致。
- 开发集交叉验证和锁定测试集的 `net_gain` 都大于零。
- 总准确率不下降，Macro F1 不下降。
- `chorus` 的 F1 或召回率提高。
- 自动修改准确率至少达到 90%，且修改样本不能过少。
- 影子模式的新歌抽检继续保持正净收益后再正式启用。
