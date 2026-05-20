#!/usr/bin/env python3
"""
RK3588 模拟服务器 - 用于测试 HARBEAT App

这个服务器模拟 RK3588 现场盒的 API，让手机可以通过网络连接到电脑进行测试。

使用方法：
1. 确保安装了依赖：pip install fastapi uvicorn websockets python-dotenv
2. 运行服务器：python mock_rk3588_server.py
3. 在手机 App 中连接到电脑的 IP 地址（默认端口 9000）

API 接口：
- GET /api/edge/info - 设备信息
- POST /play - 播放歌曲
- POST /pause - 暂停播放
- POST /resume - 继续播放
- POST /next - 下一首
- POST /seek - 跳转位置
- POST /trigger - 触发按键
- POST /load_plan - 加载计划
- WebSocket /ws/control - 实时状态推送
"""

import asyncio
import json
import random
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

app = FastAPI(title="RK3588 Mock Server", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 模拟状态
class PlaybackState(BaseModel):
    state: str = "idle"  # idle, playing, paused
    current_song_id: Optional[int] = None
    current_position_sec: float = 0.0
    current_bpm: float = 120.0
    duration_sec: float = 180.0

class DeviceInfo(BaseModel):
    device_id: str = "mock-rk-001"
    model: str = "RK3588-MOCK"
    status: str = "connected"
    battery: int = 100
    cpu_pct: float = 25.0
    mem_mb: int = 2048

playback_state = PlaybackState()
device_info = DeviceInfo()
active_connections = []

# API 端点
@app.get("/api/edge/info")
async def get_edge_info():
    """返回设备信息"""
    return {
        "device_id": device_info.device_id,
        "model": device_info.model,
        "status": device_info.status,
        "battery": device_info.battery,
        "cpu_pct": device_info.cpu_pct,
        "mem_mb": device_info.mem_mb,
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/api/edge/pair/start")
async def pair_start():
    """开始配对"""
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "pairing_code": "123456",
            "expires_in": 120,
        }
    }

@app.post("/play")
async def play(song_id: Optional[int] = None, start_at_sec: float = 0.0):
    """播放歌曲"""
    playback_state.state = "playing"
    playback_state.current_song_id = song_id or random.randint(1, 100)
    playback_state.current_position_sec = start_at_sec
    playback_state.duration_sec = random.uniform(120, 300)
    playback_state.current_bpm = random.uniform(100, 160)
    
    await broadcast_state_update()
    
    print(f"🎵 [播放] 歌曲 #{playback_state.current_song_id} | BPM: {playback_state.current_bpm:.0f}")
    return {"success": True, "message": f"Playing song {playback_state.current_song_id}"}

@app.post("/pause")
async def pause():
    """暂停播放"""
    if playback_state.state == "playing":
        playback_state.state = "paused"
        await broadcast_state_update()
        print(f"⏸️ [暂停] 歌曲 #{playback_state.current_song_id}")
    return {"success": True, "message": "Paused"}

@app.post("/resume")
async def resume():
    """继续播放"""
    if playback_state.state == "paused":
        playback_state.state = "playing"
        await broadcast_state_update()
        print(f"▶️ [继续] 歌曲 #{playback_state.current_song_id}")
    return {"success": True, "message": "Resumed"}

@app.post("/next")
async def next_song():
    """下一首"""
    playback_state.current_song_id = random.randint(1, 100)
    playback_state.current_position_sec = 0.0
    playback_state.duration_sec = random.uniform(120, 300)
    playback_state.current_bpm = random.uniform(100, 160)
    
    await broadcast_state_update()
    
    print(f"➡️ [下一首] 歌曲 #{playback_state.current_song_id} | BPM: {playback_state.current_bpm:.0f}")
    return {"success": True, "message": f"Playing song {playback_state.current_song_id}"}

@app.post("/seek")
async def seek(sec: float):
    """跳转到指定位置"""
    old_pos = playback_state.current_position_sec
    playback_state.current_position_sec = max(0.0, min(sec, playback_state.duration_sec))
    await broadcast_state_update()
    print(f"⏩ [跳转] {old_pos:.1f}s -> {playback_state.current_position_sec:.1f}s")
    return {"success": True, "position_sec": playback_state.current_position_sec}

@app.post("/trigger")
async def trigger(key: int):
    """触发按键"""
    fx_names = {1: "ha!", 2: "scratch", 3: "horn", 4: "drum", 5: "bass", 6: "hat", 7: "mute V", 8: "solo D", 9: "LPF"}
    fx_name = fx_names.get(key, f"key_{key}")
    print(f"🎛️ [加花] 触发音效: {fx_name} (key={key})")
    return {"success": True, "key": key, "latency_ms": random.randint(10, 50)}

@app.post("/load_plan")
async def load_plan(mix_plan: Dict[str, Any], manifest: Dict[str, Any]):
    """加载计划"""
    track_count = len(mix_plan.get("playlist", []))
    print(f"📋 [加载计划] {track_count} 首歌曲")
    return {"success": True, "plan_loaded": True, "track_count": track_count}

# WebSocket 实时推送
async def broadcast_state_update():
    """向所有连接的客户端广播状态更新"""
    message = json.dumps({
        "type": "playback_state",
        "state": playback_state.state,
        "current_song_id": playback_state.current_song_id,
        "current_position_sec": playback_state.current_position_sec,
        "current_bpm": playback_state.current_bpm,
        "duration_sec": playback_state.duration_sec,
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    disconnected = []
    for conn in active_connections:
        try:
            await conn.send_text(message)
        except Exception:
            disconnected.append(conn)
    
    for conn in disconnected:
        active_connections.remove(conn)

@app.websocket("/ws/control")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """WebSocket 控制端点"""
    await websocket.accept()
    active_connections.append(websocket)
    print(f"新客户端连接: {len(active_connections)} 个活跃连接")
    
    # 发送初始状态
    await websocket.send_text(json.dumps({
        "type": "device_info",
        "device_id": device_info.device_id,
        "model": device_info.model,
        "status": device_info.status,
        "battery": device_info.battery,
    }))
    
    await websocket.send_text(json.dumps({
        "type": "playback_state",
        "state": playback_state.state,
        "current_song_id": playback_state.current_song_id,
        "current_position_sec": playback_state.current_position_sec,
        "current_bpm": playback_state.current_bpm,
        "duration_sec": playback_state.duration_sec,
    }))
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"收到消息: {data}")
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        print(f"客户端断开连接: {len(active_connections)} 个活跃连接")

# 模拟播放进度更新
async def simulate_playback():
    """模拟播放进度更新"""
    while True:
        await asyncio.sleep(0.5)
        if playback_state.state == "playing":
            playback_state.current_position_sec += 0.5
            if playback_state.current_position_sec >= playback_state.duration_sec:
                # 自动播放下一首
                playback_state.current_song_id = random.randint(1, 100)
                playback_state.current_position_sec = 0.0
                playback_state.duration_sec = random.uniform(120, 300)
            await broadcast_state_update()

@app.on_event("startup")
async def startup_event():
    """启动时开始模拟播放"""
    # 启动时自动播放一首歌曲
    playback_state.state = "playing"
    playback_state.current_song_id = random.randint(1, 100)
    playback_state.current_position_sec = 0.0
    playback_state.duration_sec = 185.0
    playback_state.current_bpm = 120.0
    
    asyncio.create_task(simulate_playback())
    print("RK3588 模拟服务器启动完成！")
    print("🎵 自动开始播放歌曲 #{} | BPM: {}".format(playback_state.current_song_id, int(playback_state.current_bpm)))
    print("请确保手机和电脑在同一局域网内")
    print("手机连接地址格式: http://<电脑IP>:9000")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000, log_level="info")