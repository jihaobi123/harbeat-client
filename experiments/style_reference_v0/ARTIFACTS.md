# 13 类风格实验二进制产物

本目录保存 2026-08-29/30 的 65 首、13 类原型实验快照，供算法合作者审计和复现实验。它不是生产模型发布目录。

## 文件在哪里

| 产物 | 路径 | 内容 |
|---|---|---|
| 汇总 Embedding | `embeddings/segment_features.npz` | 872 个片段的 1280 维 Discogs-EffNet embedding，以及同片段 65 项技术特征 |
| 单曲 Embedding | `embeddings/tracks/*.npz` | 65 个匿名 track_id 对应的逐片段缓存 |
| 预训练编码器 | `models/pretrained/discogs-effnet-bs64-1.pb` | 未修改的 Discogs-EffNet TensorFlow GraphDef 权重 |
| 权重元数据 | `models/pretrained/discogs-effnet-bs64-1.json` | 官方输入、输出、作者和训练信息 |
| Embedding 分类器 | `models/embedding_classifier/model.joblib` | 冻结 embedding 上训练的小型分类头 |
| 融合分类器 | `models/fusion_classifier/model.joblib` | embedding 与 65 项技术特征的实验分类头 |
| 技术特征分类器 | `models/technical_classifier/model.joblib` | 仅 65 项技术特征的实验分类头 |
| 折外预测 | `models/oof_segment_predictions.npz` | 7 条路线对 872 个片段的四折折外概率 |
| 完整校验值 | `SHA256SUMS` | 上述文件和 65 个单曲缓存的 SHA-256 |

原始 65 首歌曲音频和 ZIP 不在这里，也没有上传 GitHub。Embedding 文件只包含匿名片段 ID 和数值数组，不包含文件名、本机路径或音频。

## 快速读取

在仓库根目录执行：

```bash
python - <<'PY'
import numpy as np

path = "experiments/style_reference_v0/embeddings/segment_features.npz"
with np.load(path, allow_pickle=False) as data:
    print(data["segment_ids"].shape)  # (872,)
    print(data["embeddings"].shape)   # (872, 1280)
    print(data["technical"].shape)    # (872, 65)
PY
```

校验全部二进制：

```bash
cd experiments/style_reference_v0
shasum -a 256 -c SHA256SUMS
```

## Joblib 使用注意

这三个 Joblib 文件由 `scikit-learn 1.9.0` 序列化。Joblib/Pickle 反序列化能够执行代码，只能加载从本仓库可信提交取得、且 SHA-256 校验通过的文件。不要加载来源不明的同名文件。为了避免版本不兼容，建议用 `scikit-learn 1.9.0` 和 `joblib 1.5.x`。

模型是实验快照，模型卡状态仍为 `experimental_not_approved`。不要把它直接接入产品或把当前四折结果当成独立外部测试结果。

## Discogs-EffNet 来源和许可

`discogs-effnet-bs64-1.pb` 原样取自 Universitat Pompeu Fabra Music Technology Group 的 Essentia 模型站点：

- 原始文件：<https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb>
- 官方目录：<https://essentia.upf.edu/models/feature-extractors/discogs-effnet/>
- 模型许可：<https://github.com/MTG/essentia-models/blob/master/LICENSE>
- 权利人：Universitat Pompeu Fabra，2019–2020
- 许可：Creative Commons Attribution-NonCommercial-ShareAlike 4.0（CC BY-NC-SA 4.0）
- 本仓库中的权重未修改；SHA-256：`3ed9af50d5367c0b9c795b294b00e7599e4943244f4cbd376869f3bfc87721b1`

该许可只允许非商业用途。商业产品、商业服务或无法确定是否属于非商业用途时，不得直接使用此权重；应向 MTG/UPF 申请商业许可或更换为许可兼容的编码器。本说明只覆盖该第三方 `.pb` 权重，不改变仓库其他代码和数据的许可。

## 与代码、报告的关系

- 提取：`scripts/extract_style_embeddings.py`
- 训练：`scripts/train_style_model.py`
- 评估：`scripts/evaluate_style_model.py`
- 数据划分：`track_splits.json`
- 特征定义：`feature_schema.json`
- 方法：`reports/methodology.md`
- 四折结果：`reports/cross_validation.md`
- 限制：`model_card.json` 和 `reports/final_assessment.md`
