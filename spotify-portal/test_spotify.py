import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()
client_id = os.environ.get("SPOTIPY_CLIENT_ID", "").strip()
client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET", "").strip()
redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()

auth_manager = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope="playlist-read-private playlist-read-collaborative",
    open_browser=False
)

# ==========================================
# 👇 核心杀招：拿到网址后，直接粘贴进下面这个双引号里！
# ==========================================
my_redirected_url = "http://127.0.0.1:8888/callback?code=AQC16Ee4Q3SazbmQH95en64dG9Puo5FCt_s_whI2W3ZzgPu1vgrf4xHFJbyrng9PnbGbmR9urJkmcWr1coj_dGUPTFJS1ZfltLuNmBK5paEhKeoz7RYWZCf0avi7uG67msmHC3kvg8GA4o91vjCbvBJ3cuVvbU6SZ-vmaGvFQqf3OU4e1xMY6p6I91ny1orMWGf40mFHnB1u5ejxdoP2qT_6tsLBFdnQVdcGAptA3S8AvvGIlPw"


if my_redirected_url == "":
    print("\n🌍 【第一步】请复制下面这个网址，到浏览器里打开并点击同意：")
    print("👉", auth_manager.get_authorize_url())
    print("\n⏳ 拿到以 127.0.0.1 开头的网址后，把它粘贴到代码的 my_redirected_url 里，然后再运行一次！")
else:
    print("\n🌍 【第二步】正在验证你的授权码...")
    try:
        # 手动提取 code 并生成永久的 .cache 缓存文件
        code = auth_manager.parse_response_code(my_redirected_url)
        auth_manager.get_access_token(code)
        
        # 验证是否真的通了
        sp = spotipy.Spotify(auth_manager=auth_manager)
        results = sp.playlist_items("37i9dQZF1DX186v583rmzp", limit=1)
        track_name = results['items'][0]['track']['name']
        print(f"\n🎉 彻底通关！授权文件 (.cache) 已永久保存！")
        print(f"🎵 成功拿到歌曲: 【{track_name}】")
        print("🚀 现在你可以放心地去运行 python ingest.py 进货了！")
    except Exception as e:
        print(f"\n❌ 验证失败: {e}")