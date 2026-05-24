# HarBeat Automix — 项目上下文（给 AI 读）

## 1. 项目概要

**目标：** 做一个智能 DJ 自动混音系统。给定两首歌（A→B），系统自动分析音频、分离 stems、选择最佳混音策略、生成过渡方案，最后在 RK3588 嵌入式设备上实时播放。

**当前测试歌单：**
- 歌 A：Drake - Nice For What（93 BPM, Camelot 4A, 约 3:30）
- 歌 B：The Weeknd / Playboi Carti / Madonna - Popular（83.3 BPM, Camelot 7A, 约 4:18）

---

## 2. 硬件架构

```
┌─────────────────────────────────────────────────────┐
│  Jetson Orin (192.168.5.100:8000)                  │
│  - FastAPI 服务                                     │
│  - 歌曲上传、分析、Demucs stem 分离                 │
│  - JWT auth（注册/登录）                            │
│  - Stream API：下载 stems (wav)                     │
│  - SSH: cat@192.168.5.100                          │
└──────────────┬──────────────────────────────────────┘
               │ 网络
┌──────────────▼──────────────────────────────────────┐
│  RK3588 Edge (192.168.5.17:9000)                   │
│  - 实时音频引擎（Python/sounddevice）               │
│  - 双 Deck 架构 + MixPlan 自动 crossfade            │
│  - 9 键 HID 加花                                   │
│  - SSH: cat@192.168.5.17  密码: temppwd            │
│  - 代码路径: /home/cat/cypher/                     │
│    - audio-engine/engine.py        ← 核心引擎      │
│    - audio-engine/strategy_selector.py ← 策略选择器 │
│    - edge-agent/run.py             ← API 服务      │
│    - edge-agent/models.py          ← Pydantic 模型 │
│    - input-daemon/main.py          ← 物理按键      │
│    - venvs/edge/bin/python         ← Python 环境   │
└─────────────────────────────────────────────────────┘
```

---

## 3. SSH 连接信息

| 设备 | 地址 | 用户 | 密码 | 端口 |
|------|------|------|------|------|
| Jetson | 192.168.5.100 | cat | （服务用，SSH 不一定需要）| 22 |
| RK3588 | 192.168.5.17 | cat | temppwd | 22 |

**本地 Mac → RK3588 部署：** 用 paramiko SFTP：
```python
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('192.168.5.17', username='cat', password='temppwd', timeout=15)
sftp = c.open_sftp()
sftp.put('/local/path/engine.py', '/home/cat/cypher/audio-engine/engine.py')
sftp.close()
c.close()
```

**RK3588 进程管理：**
```
# 查看进程
ps aux | grep -E "python.*engine|cypher" | grep -v grep

# 主要进程：
# - /home/cat/cypher/input-daemon/main.py      (PID ~946)
# - /home/cat/cypher/edge-agent/run.py         (PID ~119975)
# - /home/cat/cypher/audio-engine/main.py      (按需启动)

# 重启引擎（kill 后 edge-agent 会自动重启它）
pkill -f "audio.engine"
```

---

## 4. RK3588 API 端点

Base URL: `http://192.168.5.17:9000`

| 端点 | 方法 | 请求体 | 说明 |
|------|------|--------|------|
| `/health` | GET | - | 健康检查、同步状态、当前歌曲 |
| `/state` | GET | - | 播放状态（position_sec, playing, current_song_id） |
| `/play` | POST | `{"song_id": "xxx", "start_at_sec": 0.0}` | 开始播放 |
| `/xfade` | POST | `{"to_song_id": "xxx", "fade_sec": 20.645, "to_at_sec": 32.16, "style": "vocal_handoff"}` | 触发过渡 |
| `/load_plan` | POST | `{"mix_plan": {...}, "manifest": {...}}` | 加载混音计划 |
| `/pause` | POST | - | 暂停/恢复 |
| `/seek` | POST | `{"sec": 30.0}` | 跳转 |
| `/trigger` | POST | `{"key": 0-9}` | 加花/音效 |
| `/deck_eq` | POST | `{"deck": "a", "low_db": 0, "mid_db": 0, "hi_db": 0}` | 3-band EQ |
| `/prefetch` | POST | `{"song_ids": ["id1", "id2"]}` | 预缓存歌曲 |
| `/stems/solo` | POST | `{"stem": "vocals"}` 或 `{"stem": null}` | 独奏某个 stem |

### 可用的 style 预设（xfade 的 style 参数）：

**Stem-aware（需要 stems 文件）：**
- `vocal_handoff` — A 乐器淡出→B 乐器分阶段进入→人声在拍子边界硬切
- `bass_swap` — 贝斯先换，其他 stem 正常交叉
- `drum_swap` — 鼓先换
- `vocal_ducking` — A 人声被压缩，B 人声淡入

**Non-stem（整轨处理）：**
- `smooth` — 等功率 cos/sin 交叉淡变
- `blend` — 平滑混合
- `power` — 激进功率曲线
- `filter` — EQ 滤波扫频
- `echo_out` — A 带反馈延迟退出
- `fade` — 简单线性淡变
- `rise` — HPF 升起进入
- `melt` — 梦幻溶解
- `wave` — 脉冲调制交叉
- `cut` — 0.05 比例硬切
- `slam` — 前段 A→短暂静默→B 硬进

---

## 5. 策略选择器（strategy_selector.py）— 重点

**位置：** `/home/cat/cypher/audio-engine/strategy_selector.py`（已部署）

**入口函数：** `select_preset(song_a, song_b, a_out_start, a_out_end, b_in_cue, stems_available) -> dict`

**输入参数：**
```python
song_a/b = {
    "cues": [{"time": 0.0, "label": "Intro"}, ...],  # 段落标记
    "camelot": 4,        # Camelot 调号 1-12
    "energy": 0.7,       # 能量值 0-1
    "bpm": 93.0
}
a_out_start = 144.615   # A 过渡起始秒
a_out_end = 165.26      # A 过渡结束秒
b_in_cue = 32.16        # B 切入秒
stems_available = True  # 是否有 stems 文件
```

**评分维度（权重）：**
1. **人声活跃度** — 0.35。过渡窗口中 A/B 的人声活跃度
2. **贝斯/鼓对齐** — 0.20。贝斯和鼓在窗口内的活跃度
3. **调性兼容性** — 0.20。Camelot 轮盘距离（0=同调最佳, 1=邻居, 7=互补五度, 其他=紧张）
4. **能量匹配** — 0.15。两首歌能量水平的差距
5. **Stem 可用性** — 0.10。没有 stems 时 stem-aware preset 直接得 0 分

**段落推断逻辑（`_classify_window`）：**
- 如果过渡窗口内有 cue 标记，直接用该 cue 的段落类型
- 如果没有 cue 落入窗口，从前后 cue 推断：
  - Intro→Chorus 之间 → Verse
  - Chorus→Bridge 之间 → Verse
  - Bridge→Chorus 之间 → Build
  - Chorus→Outro 之间 → Chorus
  - Verse→Chorus 之间 → Build
- 每个段落类型有预定义的 stem 活跃度：`SECTION_PROFILES`

**段落 Stem 活跃度定义（当前值）：**
```
Intro:     vocals=0.1, drums=0.4, bass=0.4, other=0.5
Verse:     vocals=0.9, drums=0.7, bass=0.8, other=0.6
Chorus:    vocals=1.0, drums=1.0, bass=1.0, other=1.0
Bridge:    vocals=0.5, drums=0.6, bass=0.6, other=0.7
Outro:     vocals=0.3, drums=0.4, bass=0.4, other=0.5
Breakdown: vocals=0.2, drums=0.2, bass=0.3, other=0.4
Build:     vocals=0.4, drums=0.9, bass=0.8, other=0.7
Drop:      vocals=0.6, drums=1.0, bass=1.0, other=1.0
```

**当前输出结构：**
```python
{
    "selected": "vocal_handoff",
    "score": 0.570,
    "reasons": ["A vocals active (90%)...", "key neighbor...", ...],
    "rankings": [  # Top 5
        {"preset": "vocal_handoff", "score": 0.570, "reasons": [...]},
        {"preset": "bass_swap", "score": 0.500, "reasons": [...]},
        ...
    ],
    "window_analysis": {
        "a": {"sections": ["Chorus"], "activity": {"vocals": 1.0, ...}},
        "b": {"sections": ["Verse"], "activity": {"vocals": 0.9, ...}}
    },
    "compatibility": {
        "camelot_distance": 3,
        "camelot_quality": "ok",
        "energy_gap": 0.12
    }
}
```

**需细化的问题：**
1. `SECTION_PROFILES` 的活跃度值是硬编码估计值，不是从实际音频分析得出的
2. 段落推断只有有限几种模式，覆盖不了所有歌曲结构
3. B 窗口的结束时间计算为 `b_in_cue + (a_out_end - a_out_start)`，假设 A/B 窗口等长
4. 各 preset 的评分逻辑比较粗糙，阈值和加分项都是手动调的
5. 没有考虑 BPM 差异对过渡质量的影响
6. 没有利用 Jetson 返回的实际 stem 能量/频谱数据（如果有的话）

---

## 6. vocal_handoff 预设 — 当前硬切设计（v3，已部署并测试）

**设计理念：** A 非人声乐器先淡出→B 乐器分阶段进入（在人声切换前搭好伴奏床）→在 45% 处硬切人声

**engine.py 中的实现（`_stem_gains` 方法，约 982-1013 行）：**

```
进度 x (0→1):
  A 非人声: cos(x/0.25 * π/2)  0→25%, 之后为 0
  A 人声:   1.0  (x<0.45), 0.0 (x≥0.45)  ← 硬切
  B 鼓:     0→sin((x-0.20)/0.25 * π/2)  20→45% 进入
  B 贝斯:   0→sin((x-0.35)/0.15 * π/2)  35→50% 进入
  B 其他:   0→sin((x-0.40)/0.15 * π/2)  40→55% 进入
  B 人声:   0.0 (x<0.45), 1.0 (x≥0.45)  ← 硬切
```

**DSP 效果（`_apply_style_effects`，约 1300-1307 行）：**
- A 人声：echo 反馈延迟（自然衰减感）
- B 整体：HPF 扫频 800Hz→30Hz（逐渐打开频段）

**硬切位置选择（0.45）：** 约在过渡中段偏前。A 人声持续到 45%（约 9.3 秒），此时 B 鼓已播了 5 秒、贝斯 2 秒、其他乐器 1 秒——B 的伴奏 bed 已经搭好，人声切换听起来自然。

**离线渲染验证：** `/tmp/render_vocal_handoff_v2.py` — 渲染到 `/tmp/demo_vocal_handoff_v2.wav`

---

## 7. 歌曲数据（本机 Mac 和 RK3588 上都有）

| | Song ID | 文件 |
|---|---------|------|
| A (Nice For What) | `30c6f9a895aa4eacacd78c308a526388` | `/tmp/stems/A/original.wav` 及 stems |
| B (Popular) | `6ba641ecb9fe4eadaf2bb6b75b541b49` | `/tmp/stems/B/original.wav` 及 stems |

**关键时间点（Nice For What→Popular）：**
- A_OUT_START = 144.615s（Drake 的 clean chorus 开始）
- A_OUT_END = 165.26s（chorus 结束后）
- B_IN_CUE = 32.16s（The Weeknd 的 Verse 开始）
- 过渡时长 = 20.645s

**Beat Grid：**
- A: offset=0.099s, interval=0.645161s (93 BPM)
- B: offset=?, interval=? (83.3 BPM)

---

## 8. 本地关键文件路径

| 文件 | 说明 |
|------|------|
| `/tmp/harbeat-mix-quality/cypher-integration/rk3588-edge/audio-engine/engine.py` | 核心引擎（本地副本） |
| `/tmp/harbeat-mix-quality/cypher-integration/rk3588-edge/audio-engine/strategy_selector.py` | 策略选择器（本地副本） |
| `/tmp/harbeat-mix-quality/cypher-integration/rk3588-edge/edge-agent/models.py` | API 模型 |
| `/tmp/render_vocal_handoff_v2.py` | 离线渲染脚本 |
| `/tmp/render_vocal_handoff.py` | 旧版渲染脚本（v1 曲线） |
| `/tmp/render_stem_aware.py` | stem-aware 渲染 |
| `/tmp/stems/A/` | 歌 A stems（vocals/drums/bass/other/original.wav） |
| `/tmp/stems/B/` | 歌 B stems |
| `/tmp/pipeline_v3.py` | 流水线脚本（上传/分析/同步/播放） |
| `/tmp/pipeline_vocal_handoff.py` | vocal_handoff 计划生成 |
| `/tmp/sync-worker/main.py` | RK3588 同步 worker 源码 |

---

## 9. 当前进度和待办

**已完成：**
- [x] Jetson 分析 + stem 分离
- [x] RK3588 同步（manifest 格式：`{"tracks": [{"song_id": str, "files": {"original": {url, size, format}, "stems": {"vocals": ...}}}]}`)
- [x] vocal_handoff 预设：从渐退→分层进入→硬切人声，已部署测试通过
- [x] 策略选择器基础框架：段落推断 + 14 preset 评分
- [x] 离线渲染脚本（与引擎曲线一致）

**待细化（你的任务）：**
- [x] **策略选择器**的评分逻辑需要更精准——已加入 double vocal / bass conflict / drum bridge / key / BPM / energy / stem gate
- [x] 段落推断覆盖更多歌曲结构（Pre-chorus, Hook, Tag, Solo 等）
- [x] BPM 差异作为评分因子（93→83.3 跨了约 10 BPM）
- [x] 更多 preset（如 instrumental_only、vocal_solo_intro 等）
- [x] 考虑利用 Jetson 分析返回的更多数据（支持 stem_activity_windows / stem_energy_windows / segments / sections）

---

## 10. 快速测试命令

```bash
# 1. 健康检查
curl -s http://192.168.5.17:9000/health | python3 -m json.tool

# 2. 播放 A，4 秒后触发硬切 vocal_handoff
curl -s -X POST http://192.168.5.17:9000/play \
  -H 'Content-Type: application/json' \
  -d '{"song_id":"30c6f9a895aa4eacacd78c308a526388","start_at_sec":144.615}'

sleep 4

curl -s -X POST http://192.168.5.17:9000/xfade \
  -H 'Content-Type: application/json' \
  -d '{"to_song_id":"6ba641ecb9fe4eadaf2bb6b75b541b49","fade_sec":20.645,"to_at_sec":32.16,"style":"vocal_handoff"}'

# 3. 查看状态
curl -s http://192.168.5.17:9000/state | python3 -m json.tool

# 4. 离线渲染（本机 Mac）
cd /tmp && python3 render_vocal_handoff_v2.py

# 5. 部署 engine.py 到 RK3588 + 重启引擎
python3 -c "
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('192.168.5.17', username='cat', password='temppwd', timeout=15)
sftp = c.open_sftp()
sftp.put('/tmp/harbeat-mix-quality/cypher-integration/rk3588-edge/audio-engine/engine.py', '/home/cat/cypher/audio-engine/engine.py')
sftp.put('/tmp/harbeat-mix-quality/cypher-integration/rk3588-edge/audio-engine/strategy_selector.py', '/home/cat/cypher/audio-engine/strategy_selector.py')
sftp.close()
stdin, stdout, stderr = c.exec_command('pkill -f audio.engine')
print(stdout.read().decode())
c.close()
"
```

---

## 11. 2026-05-24 本轮 Codex 改动

### 11.1 策略选择器升级

文件：`/tmp/harbeat-mix-quality/cypher-integration/rk3588-edge/audio-engine/strategy_selector.py`

已将 selector 从 cue-only 粗评分升级成可读取 Jetson 实测分析数据的评分器。

支持输入：
- `cues`
- `sections`
- `segments`
- `stem_activity_windows`
- `stem_energy_windows`
- `analysis_windows`

支持结构标签：
- Intro
- Verse
- PreChorus / Pre-chorus / pre_chorus
- Chorus
- Hook
- Drop
- Bridge
- Breakdown
- Build
- Outro
- Tag
- Solo
- Instrumental
- Acapella

新增/细化评分维度：
- `double_vocal_risk`：A vocal 与 B vocal 同时活跃的风险
- `bass_conflict_risk`：A bass 与 B bass 同时活跃的风险
- `drum_bridge_score`：两首歌鼓组是否能撑住节奏桥
- `camelot_quality`：perfect / neighbor / complementary / ok / tense
- `bpm_quality`：locked / comfortable / wide / risky
- `energy_gap`
- `stems_available` gate：没有完整 stems 时 stem-aware preset 直接归零

`select_preset(...)` 现在返回：
- `selected`
- `score`
- `rankings` Top 7
- `window_analysis`
- `compatibility`
- `risks`
- `fallback`

Nice For What -> Popular 样例测试结果：
- 有 stems：选择 `vocal_handoff`
- 无 stems：选择 `blend`

### 11.2 RK 引擎新增可执行 preset

文件：`/tmp/harbeat-mix-quality/cypher-integration/rk3588-edge/audio-engine/engine.py`

修复：
- `vocal_handoff` 之前没有进入 `want_stems` 集合，可能导致请求了 stem-aware style 却没加载 stems，随后被降级成 `blend`。现在统一使用 `STEM_AWARE_STYLES`。
- stem-aware 过渡现在优先加载原始 stems；non-stem 过渡才使用 `original.rb.*.wav` beatmatch render。原因是当前 rubberband 只预渲染整轨 original，不能携带四个 stem。后续如果要 stem-aware 也严格 tempo-shift，需要对 `vocals/drums/bass/other` 四轨同步生成 beatmatched stems bundle。

新增常量：
```python
STEM_AWARE_STYLES = {
    "bass_swap",
    "drum_swap",
    "vocal_ducking",
    "vocal_handoff",
    "instrumental_only",
    "vocal_solo_intro",
}
```

新增 preset：
- `instrumental_only`：过渡窗口内两边 vocal 都 mute，只交接 drums/bass/other；适合无明显人声的段落。
- `vocal_solo_intro`：A 人声保留在上层，B 的 drums/bass/other 先搭伴奏床，B vocal 等 transition 结束后回到正常播放。
- `echo_freeze`：non-stem 安全过渡，用 A echo/freeze 掩盖 key/BPM/vocal 冲突，B 延迟进入。

降级规则：
- `bass_swap` -> `filter`
- `vocal_ducking` -> `blend`
- `drum_swap` -> `power`
- `vocal_handoff` -> `blend`
- `instrumental_only` -> `filter`
- `vocal_solo_intro` -> `echo_out`

### 11.3 Edge API 模型放开 style

文件：`/tmp/harbeat-mix-quality/cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py`

`XfadeRequest.style` 新增：
- `instrumental_only`
- `vocal_solo_intro`
- `echo_freeze`

### 11.4 本地验证命令

```bash
cd /tmp/harbeat-mix-quality

python3 -m py_compile \
  cypher-integration/rk3588-edge/audio-engine/strategy_selector.py \
  cypher-integration/rk3588-edge/audio-engine/engine.py \
  cypher-integration/rk3588-edge/edge-agent/edge_agent/models.py
```

Nice -> Popular selector smoke test：
```bash
cd /tmp/harbeat-mix-quality
python3 - <<'PY'
import sys, json
sys.path.insert(0, 'cypher-integration/rk3588-edge/audio-engine')
from strategy_selector import select_preset
A = {
    'bpm': 93.0, 'camelot': 4, 'energy': 0.78,
    'cues': [{'time': 0, 'label': 'Intro'}, {'time': 32, 'label': 'Verse'}, {'time': 72, 'label': 'Chorus'}, {'time': 144.615, 'label': 'Chorus'}, {'time': 165.26, 'label': 'Outro'}],
    'stem_activity_windows': [{'start': 144.615, 'end': 165.26, 'label': 'Chorus', 'vocals': 0.9, 'drums': 0.95, 'bass': 0.9, 'other': 0.85}],
}
B = {
    'bpm': 99.0, 'camelot': 3, 'energy': 0.72,
    'cues': [{'time': 0, 'label': 'Intro'}, {'time': 32.16, 'label': 'Verse'}, {'time': 64, 'label': 'Hook'}],
    'stem_activity_windows': [{'start': 32.16, 'end': 52.805, 'label': 'Verse', 'vocals': 0.8, 'drums': 0.85, 'bass': 0.8, 'other': 0.75}],
}
print(json.dumps(select_preset(A, B, 144.615, 165.26, 32.16, True), ensure_ascii=False, indent=2))
print(json.dumps(select_preset(A, B, 144.615, 165.26, 32.16, False), ensure_ascii=False, indent=2))
PY
```

### 11.5 下一步建议

1. 把 Jetson 实际分析输出中的 `stem_activity_windows` 接入 selector，不要只传 cue label。
2. 用 `/tmp/stems/A` 和 `/tmp/stems/B` 离线渲染比较：
   - `blend`
   - `vocal_handoff`
   - `bass_swap`
   - `vocal_solo_intro`
   - `echo_freeze`
3. 部署到 RK 后重点试听 `vocal_handoff`，确认修复后的 stem 预加载生效。
4. 如果 Popular 的真实 BPM/key 与本文档不一致，以 Jetson 实测结果为准。截图里显示过 `99 BPM / 3A`，本文档上方旧值是 `83.3 BPM / 7A`，需要用实际音频重新确认。
5. 下一层质量优化：给 stem-aware transition 增加四 stem 同步 rubberband 预渲染，否则 stem-aware 优先保证分轨控制，non-stem 优先保证 tempo match。

### 11.6 RK 部署状态

已通过 SFTP 部署到 RK3588 `192.168.5.17`：
- `/home/cat/cypher/audio-engine/engine.py`
- `/home/cat/cypher/audio-engine/strategy_selector.py`
- `/home/cat/cypher/edge-agent/edge_agent/models.py`

已重启：
- `cypher-audio-engine`
- `cypher-edge-agent`

已清理一个旧的手动 `nohup` audio-engine 进程，当前只保留 systemd 管理的：
- `/home/cat/cypher/audio-engine/main.py`
- `/home/cat/cypher/edge-agent/run.py`

部署后验证：
- RK `/health` 返回 `ok: true`、`audio_ready: true`
- RK 远端 `py_compile` 通过
- OpenAPI schema 已包含 `vocal_handoff`、`instrumental_only`、`vocal_solo_intro`、`echo_freeze`
