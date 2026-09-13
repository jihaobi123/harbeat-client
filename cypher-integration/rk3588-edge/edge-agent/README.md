# edge-agent (T1 骨架)

<!-- harbeat:reference-only -->
> **第一版历史参考 / 旧方案。第二版后续重构，预计不直接使用；个别内容如需复用，须重新确认。**
> 下文的“正式开工”“已完成”、接口字段和部署命令只描述历史版本，不是第二版实现要求或上线依据。请先读 [参考代码与重构边界](../../../docs/repository/reference-code.md)。

RK3588 现场盒控制入口：REST `:9000` + WebSocket `:9001`。

## 快速启动

```bash
cd ~/cypher/edge-agent
source ~/venvs/edge/bin/activate
pip install -r requirements.txt
python run.py
```

仅 REST（调试）：

```bash
uvicorn main:app --host 0.0.0.0 --port 9000
```

## 验证

```bash
curl http://localhost:9000/health
curl -X POST http://localhost:9000/play -H "Content-Type: application/json" -d '{"song_id":101}'
# audio-engine 未启动时返回 503

# WebSocket（需 run.py 或单独启动 ws_server）
websocat ws://localhost:9001/ws
```

## 环境变量

见 `.env.example`。`EDGE_TOKEN` 非空时，请求需带 `X-Edge-Token` 头。
