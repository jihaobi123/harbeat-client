# style_reference_v0 方法与复现路径

## 数据和隔离

- 源 ZIP SHA-256：`1ef55ef33439fecef1db939f0e64015d06ec24b2f575f2d0db58432d746584c5`；原文件未修改。
- 65 首、13 类；缺失目标类：drill, memphis_trap, moombahton, rage, rnb, soul_neo_soul, trap_soul, uk_garage。
- 使用 StratifiedGroupKFold 四折；group=primary_artist，歌曲及其全部片段继承同一 Fold。
- 文件名、艺人、目录和旧风格规则分数不进入模型矩阵。

## 切片和输入

- 首选 Downbeat 对齐的 16 小节窗、8 小节步长；Downbeat 需复核或不稳定时改用 30 秒窗、15 秒步长。
- 嵌入：Discogs-EffNet，输出 `PartitionedCall:1`，1280 维，模型 SHA-256 `3ed9af50d5367c0b9c795b294b00e7599e4943244f4cbd376869f3bfc87721b1`。
- 技术路线：65 个纯音频连续特征；完整字段见 `feature_schema.json`。
- 片段只是弱观察；最终指标全部按歌曲聚合后计算。

## 模型和判定

- 比较嵌入最近邻、嵌入 LogReg/SVM、技术 LogReg/SVM、融合 LogReg/SVM。
- 每折只用训练 Fold 拟合 StandardScaler、PCA 与分类头。
- 单项技术特征也逐一重复同样的艺人隔离四折，结果见 `technical_feature_accuracy.csv`。
- 片段 core/supporting/neutral/conflicting 来自折外一致性筛查，不等同人工真值。

## 复现命令

```bash
python scripts/build_style_reference_dataset.py --zip <source.zip> --output-dir <style_reference_v0>
python scripts/extract_style_embeddings.py --dataset-dir <style_reference_v0> --model <discogs-effnet-bs64-1.pb> --resume
python scripts/train_style_model.py --dataset-dir <style_reference_v0>
python scripts/evaluate_style_model.py --dataset-dir <style_reference_v0> --effnet-model <discogs-effnet-bs64-1.pb>
```
