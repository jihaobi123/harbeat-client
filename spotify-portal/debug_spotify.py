import os
import json
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# 1. 基础环境
load_dotenv()
client_id = os.environ.get("SPOTIPY_CLIENT_ID", "").strip()
client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET", "").strip()
redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()

# 2. 读取你已经成功的本地授权
auth_manager = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope="playlist-read-private playlist-read-collaborative",
    open_browser=False
)
sp = spotipy.Spotify(auth_manager=auth_manager)

# 3. 你那个“死活读不出来”的歌单
playlist_id = "3DcwABMe5Wl142ItmS7oCZ"

print(f"🕵️ 正在向 Spotify 发送原始请求，目标歌单: {playlist_id} ...")

try:
    # 只请求最核心的字段，拿前3首歌的数据看看结构
    results = sp.playlist_items(playlist_id, limit=3)
    
    print("\n📦 ================= Spotify 原始返回数据 X光片 ================= 📦\n")
    # 把 JSON 数据格式化输出，强行看清它的底裤
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("\n📦 ============================================================== 📦")
    
    items = results.get('items', [])
    print(f"\n📊 统计结论：接口告诉你里面有 {len(items)} 条内容。")
    
except Exception as e:
    print(f"\n❌ 请求被拦截，真实死因: {e}")