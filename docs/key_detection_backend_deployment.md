# HarBeat 调性识别后端部署说明

## 1. 目标架构

HarBeat 以 libKeyFinder 为主链路，同时执行 Essentia KeyExtractor 与
madmom CNNKeyRecognitionProcessor 两条验证链路。现有 CQT/CENS 算法仅在主链路不可用或
多路冲突时执行。

```text
音频文件
  ├─ libKeyFinder（主链路：整曲 + 主体 + 中央片段）
  ├─ Essentia KeyExtractor（验证）
  └─ madmom CNN（独立 Python 3.10 验证）
                    ↓
             24 类标准化与裁决
                    ↓
       key / camelot_key / key_profile
```

异名同音会统一，例如 `Eb minor` 与 `D# minor` 均标准化为 `D# minor / 2A`。

## 2. 裁决规则

| 情况 | 输出 |
|---|---|
| libKeyFinder 与至少一个验证器一致 | libKeyFinder，`primary_confirmed` |
| Essentia 与 madmom 一致且同时反对主链路 | 验证器结果，`validators_override_primary` |
| 三路全部不同 | 调用 CQT/CENS；匹配的一路胜出，标记低可信 |
| libKeyFinder 不可用 | 两个验证器一致则输出；否则由 CQT/CENS 辅助 |
| 可选引擎全部失败 | CQT/CENS 单路降级，标记低可信 |

`key_confidence` 是裁决可信度，不冒充 libKeyFinder 自身的概率。libKeyFinder CLI
没有提供校准概率；其整曲/分段一致性另存于 `route_stability`。

## 3. libKeyFinder 部署

项目根目录的 `Dockerfile` 已固定构建：

- libKeyFinder `2.2.8`；
- keyfinder-cli commit `8958d9219fda8a48952da365d19752e43ee81f63`；
- CLI 使用 Camelot 输出：`keyfinder-cli -n camelot AUDIO_FILE`。

构建并检查：

```bash
docker build -t harbeat-client:key-consensus .
docker run --rm harbeat-client:key-consensus keyfinder-cli --help
```

macOS 开发机可先安装库，再构建 CLI：

```bash
brew install libkeyfinder ffmpeg cmake
git clone https://github.com/evanpurkhiser/keyfinder-cli.git
cmake -S keyfinder-cli -B keyfinder-cli/build
cmake --build keyfinder-cli/build
sudo cmake --install keyfinder-cli/build
```

确认任意歌曲能返回 `1A` 到 `12B`：

```bash
keyfinder-cli -n camelot /absolute/path/to/song.mp3
```

## 4. madmom CNN 独立环境

madmom 0.16.1 不适合直接加载进项目的 Python 3.12 进程。使用 Python 3.10
建立独立虚拟环境，并通过 JSON 命令适配器调用：

```bash
python3.10 -m venv /opt/harbeat-madmom
/opt/harbeat-madmom/bin/pip install "setuptools<81" wheel "cython<3" "numpy<1.24" "scipy<1.11"
/opt/harbeat-madmom/bin/pip install --no-build-isolation madmom==0.16.1
export KEY_MADMOM_COMMAND="/opt/harbeat-madmom/bin/python /app/scripts/madmom_key_cli.py"
```

启动服务前检查：

```bash
$KEY_MADMOM_COMMAND /absolute/path/to/song.mp3
```

预期得到单行 JSON：

```json
{"key":"Eb minor","confidence":0.31,"candidates":[...]}
```

如果部署阶段暂时没有准备 madmom 环境，可设置 `KEY_ENABLE_MADMOM=false`。系统仍能运行，
但只剩 libKeyFinder + Essentia，准确率验收时不能标记为完整三路版本。

## 5. 环境变量

```dotenv
KEY_ENABLE_LIBKEYFINDER=true
KEYFINDER_CLI=keyfinder-cli
KEYFINDER_ENABLE_SEGMENTS=true
KEYFINDER_TIMEOUT_SECONDS=180
KEY_ENABLE_ESSENTIA=true
KEY_ENABLE_MADMOM=true
KEY_MADMOM_COMMAND=/opt/harbeat-madmom/bin/python /app/scripts/madmom_key_cli.py
KEY_MADMOM_TIMEOUT_SECONDS=180
```

## 6. 返回结构

```json
{
  "key": "D# minor",
  "camelot_key": "2A",
  "key_confidence": 0.95,
  "key_profile": {
    "primary_engine": "libkeyfinder",
    "selected_engine": "libkeyfinder",
    "decision": "primary_confirmed",
    "confidence_level": "high",
    "needs_review": false,
    "route_results": {
      "libkeyfinder": {
        "key": "D# minor",
        "camelot_key": "2A",
        "route_stability": 1.0,
        "segment_results": [
          {"segment": "full", "camelot": "2A"},
          {"segment": "body", "camelot": "2A"},
          {"segment": "center", "camelot": "2A"}
        ]
      },
      "essentia": {"key": "D# minor", "camelot_key": "2A"},
      "madmom": {"key": "D# minor", "camelot_key": "2A"}
    },
    "errors": {}
  }
}
```

后端与前端必须保留 `route_results`、`decision`、`needs_review` 和 `errors`，否则无法对
KPOP 标注集逐路统计准确率和定位误判。

## 7. 验收要求

1. 用有人工真值的 KPOP 测试集，不用三个模型的多数结果反向充当真值。
2. 异名同音统一后，以 24 类“主音 + 大小调”完全一致作为正确。
3. 分别统计 libKeyFinder、Essentia、madmom、最终裁决四组准确率。
4. 单独统计相对大小调、平行大小调、五度关系和转调歌曲。
5. `needs_review=true` 的歌曲必须进入人工复核列表。

## 8. 许可证

libKeyFinder 和 keyfinder-cli 均为 GPL-3.0 系列许可。分发包含它们的 Docker 镜像或将其
链接到闭源产品前，必须由后端/法务确认源码提供、许可证文本和衍生作品义务。项目镜像会
保留上游许可证文本；独立进程部署能降低工程耦合，但不能自动消除 GPL 合规义务。
