# 团队开发文档 · Jetson 后端（负责人 A）

> 自包含实现规范。读完直接动工。基础与协议见 [cypher-feature-flows.md](cypher-feature-flows.md)、运行时见 [current-web-runtime.md](current-web-runtime.md)。

## 0. 你的目标
让 Jetson 提供 cypher 场景所需的全部远程接口，并把现有"5 首 280s 才能出 MixPlan"的性能问题降到 60s 内。

## 0.1 工作环境
- 机器：Jetson Orin NX（家里），IP `100.87.142.21`（Tailscale），LAN 视拓扑
- 代码：`/home/mark/harbeat/`
- venv：`~/venvs/harbeat/`
- 服务：`systemctl --user status harbeat.service`（uvicorn :8000）
- 数据库：本地 PostgreSQL :5432，库名见 `app/shared/db.py`
- 重启：`sudo systemctl restart harbeat.service`（注意 onnxruntime 在 ARM 不稳，见 `/memories/repo/jetson-restart-trick.md`）

## 0.2 你要交付 5 个任务

| # | 任务 | 改动文件 | 完工标志 |
|---|---|---|---|
| T1 | 歌曲分析状态机 + 状态查询接口 | `app/modules/library/*`, DB migration | App 能轮询到 ready 状态 |
| T2 | MixPlan AssetManifest 接口 | `app/modules/playlists/*` | B 能拿到包含 sha256 的清单 |
| T3 | GrooveEngine 提速到 60s 内 + SSE 流式 | `app/modules/playlists/groove_adapter.py` 等 | 5 首歌首个 plan < 60s |
| T4 | SessionEvent 批量入库 | 新建 `app/modules/sessions/*` | B 上报数据可存可查 |
| T5 | 现场盒透传网关 | `deploy/cloud_gateway/app/main.py` | App 经云端访问 RK |

---

## T1 歌曲分析状态机

### 数据库改动

在 `library_songs` 表（或当前歌曲表，名字看 `app/modules/library/models.py`）加列：

```sql
ALTER TABLE library_songs
  ADD COLUMN IF NOT EXISTS analysis_status TEXT NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS analysis_error  TEXT,
  ADD COLUMN IF NOT EXISTS analyzed_at     TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_lib_songs_status ON library_songs(analysis_status);
```

写入 `app/main.py` 的 `_migrate_add_missing_columns()` 以便自动执行。

状态取值：`pending | bpm_done | beats_done | stems_done | embed_done | ready | failed`。

### 流水线落点

在当前后台分析任务（搜 `analyzeSong`、`_schedule_pending_analyses`、`analyze_song_background` 等）的每一阶段结束时 UPDATE 该字段：

```
librosa 完 → bpm_done
beatnet 完 → beats_done
demucs 完  → stems_done
clap 完    → embed_done
全部入库   → ready
异常       → failed + analysis_error=str(e)
```

### 新接口

```
GET /api/library/songs/{song_id}/status
返回: SongStatus (协议 P1)
```

实现在 `app/modules/library/router.py`，复用现有 `get_library_song`，添加上面字段。

```
GET /api/library/search?q=&only_ready=true&limit=50
```
在现有 search 接口加 `only_ready: bool = False` 参数，True 时 WHERE `analysis_status='ready'`。

### 优先级队列（推荐做但不阻塞 MVP）
后台任务用 Redis list `harbeat:analysis:queue:high` 和 `:normal`。`POST /api/music/upload?priority=high` 走 high 队列。Worker 先 BLPOP high。

### 验证
```bash
curl -X POST -F "file=@a.mp3" http://localhost:8000/api/music/upload -H "Authorization: Bearer $T"
# {"song_id": 999, "analysis_status": "pending"}
curl http://localhost:8000/api/library/songs/999/status -H "Authorization: Bearer $T"
# 持续轮询，~4min 后 status="ready"
curl 'http://localhost:8000/api/library/search?q=&only_ready=true' -H "Authorization: Bearer $T"
```

---

## T2 MixPlan 与 AssetManifest

### 新接口

```
GET /api/playlists/{playlist_id}/mix-plan/latest
返回: MixPlan (协议 P2)，从 DB / Redis 取最近一次生成结果

GET /api/playlists/{playlist_id}/manifest?plan_id=...
返回: AssetManifest (协议 P3)
```

实现位置：`app/modules/playlists/router.py` 新增 endpoint，`service.py` 加 `build_manifest(plan_id)`。

`build_manifest` 逻辑：
1. 取 plan 涉及的所有 song_id
2. 对每首歌：
   - `original`: 路径 = NAS 上原文件，url = `/api/stream/{id}/audio`
   - 4 stems: url = `/api/stream/{id}/stem/{vocals|drums|bass|other}`
   - `size`: `os.path.getsize`
   - `sha256`: 缓存到表 `library_songs.original_sha256` / `stems_sha256_json`，首次计算后存库，下次直接读
3. 拒绝非 ready 歌：`analysis_status != 'ready'` → 整个接口 409

### 验证
```bash
curl 'http://localhost:8000/api/playlists/42/manifest?plan_id=abc' \
  -H "Authorization: Bearer $T" | jq '.tracks[0]'
```

---

## T3 GrooveEngine 提速到 60s（最重的任务）

### 现状

`app/modules/playlists/groove_adapter.py` 的 `run_groove_engine_plan()` 对 5 首歌跑全排列（5! = 120）+ 全对评分。耗时 ~280s。

### 改造分 3 步

**Step 3.1 Redis 缓存 pair score**

每对 (song_a, song_b) 的 transition 评分（GrooveEngine 内部用 BPM/key/能量算的相容性）存：
```
key:   harbeat:pair_score:{min(a,b)}:{max(a,b)}
value: JSON {"score": 0.87, "best_transition": {...}, "v": 1}
TTL:   30 天
```

封装：
```python
# app/modules/playlists/groove_adapter.py
def _cached_pair_score(a_id, b_id):
    key = f"harbeat:pair_score:{min(a_id,b_id)}:{max(a_id,b_id)}"
    if (raw := redis.get(key)): return json.loads(raw)
    score = _compute_pair_score(a_id, b_id)  # 现有计算函数
    redis.setex(key, 30*86400, json.dumps(score))
    return score
```

**Step 3.2 用 greedy + 2-opt 代替全排列**

```python
def order_tracks(tracks):
    # 1. 起点选 BPM 最接近全队中位数的
    start = pick_median_bpm(tracks)
    # 2. greedy: 每次选 pair_score 最高的未访问邻居
    order = [start]
    while len(order) < len(tracks):
        last = order[-1]
        best = max(unvisited, key=lambda t: _cached_pair_score(last.id, t.id)["score"])
        order.append(best)
    # 3. 2-opt 优化：随机选 i,j 翻转 order[i:j]，若总分提升则采用，跑 50 轮
    for _ in range(50):
        order = try_2opt_swap(order)
    return order
```

5 首歌：缓存命中后 4 对 pair score 读 Redis；首次冷启动算 10 对 × 2~3s = 30s；之后 2-opt 全用缓存 < 5s。

**Step 3.3 SSE 流式返回**

```
POST /api/playlists/{id}/dj-mix-stream
Content-Type: text/event-stream
返回流：
  event: plan_partial   data: { MixPlan, score: 0.72 }   ← greedy 完毕，~30s
  event: plan_better    data: { MixPlan, score: 0.81 }   ← 2-opt 中
  event: plan_final     data: { MixPlan, score: 0.85 }   ← 完成
```

FastAPI 用 `StreamingResponse(generator(), media_type="text/event-stream")`。

旧接口 `POST /api/playlists/{id}/dj-mix` 保留同步版本（内部超时设 90s）。

### 验证
```bash
time curl -N -X POST http://localhost:8000/api/playlists/42/dj-mix-stream \
  -H "Authorization: Bearer $T"
# 期望：30s 内看到第一个 event: plan_partial
```

---

## T4 SessionEvent 入库

### DB
```sql
CREATE TABLE IF NOT EXISTS session_events (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  rk_id TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  type TEXT NOT NULL,
  data JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON session_events(session_id, ts);
```

### 接口

```
POST /api/sessions/{session_id}/events
Body: { "rk_id": "rk-001", "events": [P7 SessionEvent.events ...] }
返回: { "accepted": N }
```

批量 INSERT。无 auth 也行（内网/网关已挡），但推荐加 RK 共享 secret 校验 header `X-RK-Token`。

```
GET /api/sessions/{session_id}/events?type=key_press&limit=500
```

返回归档查询。

---

## T5 现场盒透传网关

`deploy/cloud_gateway/app/main.py` 加：

```python
RK_REGISTRY = {  # 简单实现：环境变量配
  "rk-001": os.getenv("RK001_BASE_URL", "http://100.x.x.x:9000"),
}

@app.api_route("/edge/{rk_id}/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH"])
async def proxy_edge(rk_id, path, request):
    base = RK_REGISTRY.get(rk_id)
    if not base: raise HTTPException(404)
    return await _proxy_to(base, path, request)  # 复用现有 proxy 函数
```

确保转发 body、保留 Authorization。WebSocket 路径 `/edge/{rk_id}/ws/*` 用 FastAPI WS proxy（需要 httpx-ws 或手写双向 pump）。

### 验证
```bash
curl https://harbeat.example.com/edge/rk-001/health
# 透传到 RK 的 /health
```

---

## 完工自检
- [ ] 上传一首新歌，4min 内 status 从 pending 变 ready
- [ ] search `?only_ready=true` 不返回未 ready 歌
- [ ] 5 首 playlist `/dj-mix-stream` 30s 内拿第一个 plan，60s 内拿 final
- [ ] `/manifest` 返回的 sha256 与 `sha256sum` 命令一致
- [ ] B 用 `/edge/rk-001/play` 能透传到 RK 真机
- [ ] `/sessions/{id}/events` POST 100 条耗时 < 200ms
