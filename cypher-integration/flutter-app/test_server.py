#!/usr/bin/env python3
"""
HARIBEAT RK3588 模拟测试服务器
用于测试App的设备连接功能
"""

import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, List
import random
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime

app = FastAPI(title="HARIBEAT Edge API Mock", version="1.0.0")

# 日志列表
log_entries = []

def add_log(message, type="info"):
    log_entries.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": message,
        "type": type
    })
    if len(log_entries) > 100:
        log_entries.pop(0)

# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    add_log(f"{request.method} {request.url}", "req")
    try:
        body = await request.json() if request.method == "POST" else None
        if body:
            add_log(f"Body: {body}", "req")
    except:
        pass
    
    response = await call_next(request)
    add_log(f"Response: {response.status_code}", "res")
    return response

# 模拟设备状态
device_state = {
    "device_id": "rk3588-test-01",
    "name": "HARIBEAT Test Device",
    "version": "1.0.0",
    "current_track": "Test Track - HipHop Beat",
    "is_playing": False,
    "volume": 75,
    "style": "hiphop",
    "energy": "medium",
    "mic_active": True,
    "speaker_active": True,
    "keyboard_active": False,
}

# 配对码存储
pair_codes: Dict[str, dict] = {}

# WebSocket连接列表
active_connections: List[WebSocket] = []

class PairConfirmRequest(BaseModel):
    device_id: str
    pair_code: str
    client_name: str = "Test Client"
    client_type: str = "mobile"

class CommandRequest(BaseModel):
    command_id: str
    source: str = "mobile"
    session_id: str = "test-session"
    command: str
    payload: dict = {}

@app.get("/api/edge/info")
async def get_device_info():
    """获取设备信息"""
    return {
        "device_id": device_state["device_id"],
        "name": device_state["name"],
        "version": device_state["version"],
        "firmware": "latest",
        "local_url": "http://localhost:8787",
        "tailscale_url": "http://rk3588.tail99a6c4.ts.net:8787",
        "gateway_url": "https://harbeat.com/edge/rk3588-test-01",
    }

@app.get("/api/edge/status")
async def get_status():
    """获取当前状态"""
    return device_state

@app.post("/api/edge/pair/start")
async def start_pairing():
    """生成配对码"""
    code = str(random.randint(100000, 999999))
    pair_codes[code] = {
        "device_id": device_state["device_id"],
        "expires_in_sec": 60,
        "created_at": asyncio.get_event_loop().time(),
    }
    print(f"📱 生成配对码: {code}")
    return {
        "device_id": device_state["device_id"],
        "pair_code": code,
        "expires_in_sec": 60,
        "local_url": "http://localhost:8787",
        "tailscale_url": "http://rk3588.tail99a6c4.ts.net:8787",
        "gateway_url": "https://harbeat.com/edge/rk3588-test-01",
    }

@app.post("/api/edge/pair/confirm")
async def confirm_pairing(request: PairConfirmRequest):
    """确认配对"""
    if request.pair_code in pair_codes:
        del pair_codes[request.pair_code]
        print(f"✅ 配对成功! 设备ID: {request.device_id}, 客户端: {request.client_name}")
        return {
            "device_token": f"edge_token_{random.randint(100000, 999999)}",
            "expires_at": "2026-06-01T12:00:00+08:00",
            "permissions": ["control", "read_status", "trigger_sfx"],
        }
    else:
        return {"error": "无效的配对码"}, 400

@app.post("/api/edge/command")
async def send_command(request: CommandRequest):
    """处理控制命令"""
    print(f"🎮 收到命令: {request.command}")
    
    global device_state
    
    # 处理命令
    if request.command == "play":
        device_state["is_playing"] = True
        print("▶️ 开始播放")
    elif request.command == "pause":
        device_state["is_playing"] = False
        print("⏸️ 暂停播放")
    elif request.command == "next":
        device_state["current_track"] = f"Track {random.randint(1, 10)} - {request.payload.get('style', 'HipHop')} Beat"
        print(f"⏭️ 切换到: {device_state['current_track']}")
    elif request.command == "previous":
        device_state["current_track"] = f"Track {random.randint(1, 10)} - Previous"
        print(f"⏮️ 切换到上一首")
    elif request.command == "set_volume":
        device_state["volume"] = request.payload.get("volume", 75)
        print(f"🔊 音量设置为: {device_state['volume']}%")
    elif request.command == "switch_style":
        device_state["style"] = request.payload.get("style", "hiphop")
        print(f"🎵 切换风格: {device_state['style']}")
    elif request.command == "set_energy":
        device_state["energy"] = request.payload.get("mode", "medium")
        print(f"⚡ 能量模式: {device_state['energy']}")
    elif request.command == "trigger_sfx":
        sfx_id = request.payload.get("sfx_id", "boom")
        print(f"🎉 触发音效: {sfx_id}")
    elif request.command == "emergency_stop":
        device_state["is_playing"] = False
        device_state["volume"] = 0
        print("🚨 紧急停止!")
    else:
        print(f"❓ 未知命令: {request.command}")
    
    # 向所有WebSocket连接发送状态更新
    await broadcast_status()
    
    return {"status": "ok", "command_id": request.command_id}

@app.websocket("/ws/control")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket控制端点"""
    await websocket.accept()
    active_connections.append(websocket)
    print("🔌 WebSocket连接已建立")
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"📥 收到WebSocket消息: {data[:50]}...")
            # 发送状态更新
            await websocket.send_json({"type": "status", "data": device_state})
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        print("🔌 WebSocket连接已断开")

async def broadcast_status():
    """向所有连接广播状态"""
    for connection in active_connections:
        try:
            await connection.send_json({"type": "status", "data": device_state})
        except Exception as e:
            print(f"❌ 广播失败: {e}")

@app.get("/api/edge/cache/playlist")
async def get_playlist():
    """获取缓存歌单"""
    return {
        "playlists": [
            {"id": "1", "name": "测试调试歌单", "description": "用于测试的歌单", "track_count": 10},
            {"id": "2", "name": "炸场高能歌单", "description": "适合高能演出", "track_count": 15},
            {"id": "3", "name": "平稳控场歌单", "description": "平稳过渡", "track_count": 12},
            {"id": "4", "name": "街舞练舞歌单", "description": "适合练习", "track_count": 20},
            {"id": "5", "name": "轻柔背景歌单", "description": "背景音乐", "track_count": 8},
        ]
    }

@app.get("/")
async def root():
    """首页 - 显示配对码和状态"""
    current_code = list(pair_codes.keys())[0] if pair_codes else "无"
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>HARIBEAT RK3588 模拟服务器</title>
    <style>
        body {{ 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            font-family: Arial, sans-serif;
            text-align: center;
            padding: 50px;
            min-height: 100vh;
            margin: 0;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: rgba(255,255,255,0.1);
            padding: 40px;
            border-radius: 20px;
            backdrop-filter: blur(10px);
        }}
        h1 {{ color: #00ff88; }}
        .code-box {{
            background: #000;
            padding: 30px;
            border-radius: 15px;
            margin: 30px 0;
        }}
        .code {{
            font-size: 48px;
            font-weight: bold;
            letter-spacing: 10px;
            color: #ff6b35;
        }}
        .status {{
            padding: 10px 20px;
            border-radius: 25px;
            display: inline-block;
            margin: 10px;
        }}
        .status.online {{ background: #00ff88; color: #000; }}
        .status.waiting {{ background: #ff6b35; color: #000; }}
        .log {{
            background: rgba(0,0,0,0.5);
            padding: 20px;
            border-radius: 10px;
            text-align: left;
            max-height: 300px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 12px;
        }}
        .log-entry {{ margin: 5px 0; }}
        .log-time {{ color: #888; }}
        .log-req {{ color: #00ff88; }}
        .log-res {{ color: #ff6b35; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 HARIBEAT RK3588 模拟服务器</h1>
        <p>端口: 8787</p>
        <div class="status online">✅ 在线</div>
        
        <h2>🔑 当前配对码</h2>
        <div class="code-box">
            <div class="code">{current_code}</div>
        </div>
        
        <p style="color: #aaa;">点击App中的"开始配对"后，配对码会显示在这里</p>
        
        <h2>📝 操作日志</h2>
        <div class="log" id="log-container">
            {''.join([f'<div class="log-entry"><span class="log-time">[{e["time"]}]</span> <span class="log-{e["type"]}">{e["message"]}</span></div>' for e in log_entries[-20:]])}
        </div>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content, media_type="text/html")

if __name__ == "__main__":
    print("[INFO] Starting HARIBEAT Test Server...")
    print("[INFO] Listening on: http://0.0.0.0:8787")
    print("[INFO] WebSocket endpoint: ws://localhost:8787/ws/control")
    print("="*50)
    uvicorn.run(app, host="0.0.0.0", port=8787)
