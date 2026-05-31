# audio-engine (MVP)

Unix socket 音频播放服务，供 edge-agent 调用。

## 启动

```bash
source ~/venvs/edge/bin/activate
pip install -r ~/cypher/audio-engine/requirements.txt
python ~/cypher/audio-engine/main.py
```

### 选择声卡（LubanCat 板载 / USB / HDMI）

```bash
# 查看设备编号
python -c "import sounddevice as sd; print(sd.query_devices())"

# 指定输出（示例）
export CYPHER_AUDIO_DEVICE=6      # pulse → 板载 ES8388 耳机孔（默认）
export CYPHER_AUDIO_DEVICE=1      # HDMI
export CYPHER_AUDIO_DEVICE="USB"  # 插入 USB 声卡后
```

## 测试曲目

```bash
python ~/cypher/audio-engine/scripts/make_test_wav.py
# 生成 ~/cypher/cache/101/original.wav（440Hz，5 秒）
```

## 验证

```bash
# 直接调 socket
python -c "
import json,socket,struct
s=socket.socket(socket.AF_UNIX); s.connect('/tmp/cypher-audio.sock')
b=json.dumps({'cmd':'play','song_id':101}).encode()
s.sendall(struct.pack('>I',len(b))+b)
print(s.recv(4096))
"

# 经 edge-agent
curl -X POST http://localhost:9000/play -H 'Content-Type: application/json' -d '{"song_id":101}'
```

## 自动切歌（双 deck + crossfade）

1. 确保 `cache/101/`、`cache/102/` 均有 `original.wav`
2. 重启 audio-engine
3. 加载演示 MixPlan 并播放：

```bash
bash ~/cypher/audio-engine/scripts/load_demo_plan.sh
# 101 播约 4 秒后 8s crossfade 到 102（等你下课）
```

或手动：

```bash
curl -X POST http://localhost:9000/load_plan -H "Content-Type: application/json" \
  -d @~/cypher/plans/demo_101_102.json
curl -X POST http://localhost:9000/play -H "Content-Type: application/json" -d '{"song_id":101}'
```

支持协议：`tracks`+`transitions`（P2）或 `playlist`+`transition_plan`（Jetson）。

`POST /next` 可手动触发下一首 crossfade。

## 命令

| cmd | 说明 |
|-----|------|
| ping | 健康检查 |
| play | `song_id`, `start_at_sec` |
| pause / resume / seek / next / stop | 播放控制 |
| load_plan | 加载 MixPlan，按时间点自动 crossfade |
| trigger | 九键加花 0-9 |

缺 `cache/<id>/original.wav` 返回 `code: 409`。
