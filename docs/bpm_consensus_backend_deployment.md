# BPM 三引擎共识模块：后端部署说明

## 1. 交付范围

本模块将曲库分析入口 `app.modules.library.analysis.analyze_audio_file()`
中的 BPM 路径升级为三路并行分析：

1. Beat This `final0`：输出 beat/downbeat 网格并从 beat 间隔计算 BPM；
2. All-In-One `harmonix-fold0`：输出 BPM、beat/downbeat 和结构信息；
3. Essentia `RhythmExtractor2013(multifeature)`：保留原有分析路径。

三路只负责 BPM 共识。Key、能量、段落、Cue、舞池画像等现有分析流程不变。

## 2. 共识规则

- 默认将相差不超过 `2.0 BPM` 的结果视为同一组；
- 三路同组：输出三者中位数；
- 两路同组：输出两者中位数；
- 三路完全分裂：保留 Essentia 结果，并设置 `beat_needs_review=true`；
- 某一路失败：其余线路继续返回结果，但设置降级复核标记；
- 三路全部失败：回退至原有 librosa beat tracker；
- 不自动把半拍/双拍折算为同一票，例如 70 与 140 仍是不同结果。

最终 `beat_points` 取自距离共识 BPM 最近的获胜引擎，避免 BPM 与节拍网格
来自不同速度层级。

## 3. 代码和依赖

核心文件：

- `app/modules/library/analysis.py`
- `requirements.txt`
- `tests/test_bpm_consensus.py`

固定依赖版本：

```text
essentia==2.1b6.dev1177
beat-this==1.1.0
all-in-one-infer==3.1.0
```

Dockerfile 会先安装 CPU 版 PyTorch/Torchaudio，再安装上述分析依赖。GPU 部署时，
后端人员应按照目标 CUDA/JetPack 环境替换 Dockerfile 中的 PyTorch 安装命令，
不要同时安装 CPU 和 CUDA 两套 PyTorch。

## 4. 环境变量

```dotenv
BPM_ENABLE_BEAT_THIS=true
BPM_ENABLE_ALL_IN_ONE=true
BPM_ENABLE_ESSENTIA=true
BPM_CONSENSUS_TOLERANCE=2.0

BPM_BEAT_THIS_MODEL=final0
BPM_BEAT_THIS_DEVICE=cpu

BPM_ALL_IN_ONE_MODEL=harmonix-fold0
# 空值表示自动选择 CUDA -> MPS -> CPU
BPM_ALL_IN_ONE_DEVICE=
```

建议 Beat This 保持 CPU，All-In-One 使用可用加速器，使两条 PyTorch 路径能够
与 CPU Essentia 真正并行，同时减少单块 GPU 的显存竞争。

灰度或故障回退：将任意 `BPM_ENABLE_*` 设置为 `false` 后重启 API 容器即可关闭
对应线路。关闭 Beat This 与 All-In-One、仅保留 Essentia，即可恢复原分析策略。

## 5. 模型缓存与首次启动

首次分析会下载以下权重：

- Beat This `final0`；
- All-In-One `harmonix-fold0`；
- Demucs `htdemucs`（All-In-One 的源分离前置模型）。

`docker-compose.yml` 已将 `/root/.cache` 挂载到 `model_cache` 命名卷，容器重建后
无需重新下载。生产环境出网受限时，应在镜像构建机或部署机预热缓存：

```bash
python -c "from beat_this.inference import load_checkpoint; load_checkpoint('final0')"
python -c "from allin1_infer.models.loaders import load_pretrained_model; load_pretrained_model('harmonix-fold0', device='cpu')"
python -c "from demucs_infer.pretrained import get_model; get_model('htdemucs')"
```

如采用离线镜像，请在同一用户下执行预热，并把其 `~/.cache` 内容复制进运行镜像
或挂载到容器 `/root/.cache`。

## 6. Docker Compose 部署

```bash
git fetch origin
git checkout feature/bpm-three-engine-consensus
cp .env.example .env
# 编辑数据库、JWT 和 BPM_* 配置
docker compose build app
docker compose up -d app redis nginx
docker compose logs -f app
```

All-In-One 包含 Demucs 分离，资源消耗明显高于原 Essentia 路径。建议生产节点：

- 8 GB RAM 或以上；
- 4 CPU 核最低，8 核推荐；
- 模型缓存至少预留 5 GB；
- 有 CUDA GPU 时优先把 `BPM_ALL_IN_ONE_DEVICE=cuda`；
- 当前 Compose 将 API 容器内存上限提高至 8 GB。

CPU 环境可以运行，但一首 3～5 分钟歌曲可能需要数分钟。Apple Silicon MPS 实测
《RINGA LINGA》三路完整分析约 44 秒，具体速度以部署硬件为准。

## 7. 接口与返回数据

现有接口不变：

```http
POST /api/library/songs/{song_id}/analyze
```

最终 BPM 仍写入 `library_songs.bpm`。投票明细写入现有 JSON 字段
`library_songs.beat_confidence_details`：

```json
{
  "selected_bpm_engine": "all_in_one:harmonix-fold0",
  "bpm_consensus": {
    "votes": {
      "beat_this": 69.767,
      "all_in_one": 140.0,
      "essentia": 140.817
    },
    "bpm": 140.409,
    "winning_engines": ["all_in_one", "essentia"],
    "agreement_count": 2,
    "available_count": 3,
    "status": "majority",
    "needs_review": false,
    "tolerance": 2.0,
    "errors": {}
  }
}
```

因此本次交付不需要数据库迁移。

状态含义：

| status | 含义 |
|---|---|
| `unanimous` | 三路落在同一 BPM 组 |
| `majority` | 三路可用，其中两路形成多数 |
| `degraded_agreement` | 只有部分线路可用且至少两路一致 |
| `no_majority` | 没有两路一致，需人工复核 |

## 8. 验证命令

```bash
python -m py_compile app/modules/library/analysis.py
pytest -q tests/test_bpm_consensus.py
pytest -q tests
```

部署后的单文件冒烟测试：

```bash
python - <<'PY'
import json
from app.modules.library.analysis import analyze_audio_file

result = analyze_audio_file('/absolute/path/to/test.wav')
print(json.dumps({
    'bpm': result['bpm'],
    'engines': result['beat_engines_used'],
    'needs_review': result['beat_needs_review'],
    'consensus': result['beat_confidence_details'].get('bpm_consensus'),
}, indent=2))
PY
```

验收要求：

- `beat_engines_used` 正常情况下包含三个引擎；
- `bpm_consensus.available_count == 3`；
- `errors` 为空；
- 两路一致时 `status == "majority"`；
- 容器重启后不重复下载模型权重。

## 9. 常见故障

### All-In-One 下载失败

检查容器能否访问 Hugging Face，并确认 `/root/.cache` 可写；受限网络环境使用第5节
的离线预热方案。临时恢复服务可设置 `BPM_ENABLE_ALL_IN_ONE=false`。

### CUDA/MPS 内存不足

将 `BPM_ALL_IN_ONE_DEVICE=cpu`，或关闭 All-In-One。Beat This 默认在 CPU，不会占用
All-In-One 的 GPU 显存。

### MP3 解码或 TorchCodec 报错

模块会先把已解码音频写成临时 PCM WAV 后交给 All-In-One，避免直接依赖其 MP3
解码链。仍失败时检查系统 `ffmpeg` 和 `libsndfile`；Dockerfile 已安装这两项。

### 三路结果长期分裂

读取 `beat_confidence_details.bpm_consensus.votes` 和 `errors`。不要仅修改最终 BPM；
应先确定产品采用的主拍层级，再决定是否增加半拍/双拍语义规则。
