#!/usr/bin/env python3
"""
HarBeat 歌单导入诊断脚本
========================
用于在服务器/容器内逐步诊断"导入歌单全部失败"的问题。

使用方法:
  方法1: 在服务器宿主机上运行（需要 httpx）
    pip install httpx
    python3 diagnose_download.py

  方法2: 在 Docker 容器内运行
    docker exec -it harbeat-api python diagnose_download.py

  方法3: 复制到容器再运行
    docker cp diagnose_download.py harbeat-api:/app/
    docker exec -it harbeat-api python /app/diagnose_download.py

每一步会详细打印结果，帮助定位是哪个环节出了问题。
"""
import asyncio
import json
import os
import platform
import re
import sys

# ═══════════════════════════════════════════════════════════════
# STEP 0: 环境检查
# ═══════════════════════════════════════════════════════════════
def step0_env():
    print("=" * 60)
    print("STEP 0: 环境信息")
    print("=" * 60)
    print(f"  Python:    {sys.version}")
    print(f"  Platform:  {platform.platform()}")
    print(f"  CWD:       {os.getcwd()}")
    
    # 检查 git 分支
    try:
        import subprocess
        branch = subprocess.check_output(["git", "branch", "--show-current"], text=True, stderr=subprocess.DEVNULL).strip()
        last_commit = subprocess.check_output(["git", "log", "--oneline", "-1"], text=True, stderr=subprocess.DEVNULL).strip()
        print(f"  Git分支:   {branch}")
        print(f"  最新提交:  {last_commit}")
    except Exception:
        print(f"  Git:       不可用")
    
    # 检查 httpx 版本
    try:
        import httpx
        print(f"  httpx:     {httpx.__version__}")
    except ImportError:
        print("  httpx:     ❌ 未安装！运行 pip install httpx")
        sys.exit(1)
    
    # 检查关键文件
    service_path = "app/modules/fangpi/service.py"
    if os.path.exists(service_path):
        with open(service_path, "r", encoding="utf-8") as f:
            content = f.read()
        has_clean_query = 'clean_query = re.sub' in content
        has_title_matches = 'def _title_matches' in content
        has_kuwo_fallback = 'Fallback: search Kuwo by title' in content
        print(f"\n  代码检查:")
        print(f"    fangpi特殊字符修复:  {'✅' if has_clean_query else '❌ 旧代码'}")
        print(f"    标题匹配过滤器:      {'✅' if has_title_matches else '❌ 旧代码'}")
        print(f"    Kuwo fallback修复:   {'✅' if has_kuwo_fallback else '❌ 旧代码'}")
        if not (has_clean_query and has_title_matches and has_kuwo_fallback):
            print(f"\n  ⚠️  服务器代码不是最新版！需要先更新代码:")
            print(f"      git fetch --all")
            print(f"      git checkout feature/superpowered-player")
            print(f"      git pull")
    else:
        print(f"  service.py: 找不到（当前不在项目根目录）")
    
    print()


# ═══════════════════════════════════════════════════════════════
# STEP 1: DNS + 网络连通性
# ═══════════════════════════════════════════════════════════════
async def step1_network():
    import httpx
    print("=" * 60)
    print("STEP 1: 网络连通性测试")
    print("=" * 60)
    
    targets = [
        ("fangpi.net 主页",   "https://www.fangpi.net/", "GET"),
        ("fangpi.net 搜索API", "https://www.fangpi.net/api/s", "POST"),
        ("Kuwo 搜索API",      "https://search.kuwo.cn/r.s?ft=music&rn=1&all=test", "GET"),
        ("Kuwo 音频API",      "https://antiserver.kuwo.cn/anti.s?type=convert_url3&rid=28709224&format=mp3&response=url", "GET"),
    ]
    
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    for name, url, method in targets:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
                if method == "POST":
                    resp = await client.post(url, data={"keyword": "test"}, headers={"User-Agent": ua})
                else:
                    resp = await client.get(url, headers={"User-Agent": ua})
                status = resp.status_code
                body_preview = resp.text[:100].replace("\n", " ")
                print(f"  {'✅' if status < 400 else '❌'} {name}")
                print(f"     URL: {url[:70]}")
                print(f"     Status: {status}, Body: {body_preview}")
        except Exception as e:
            print(f"  ❌ {name}")
            print(f"     URL: {url[:70]}")
            print(f"     Error: {e}")
    print()


# ═══════════════════════════════════════════════════════════════
# STEP 2: Fangpi 搜索测试
# ═══════════════════════════════════════════════════════════════
async def step2_fangpi_search():
    import httpx
    print("=" * 60)
    print("STEP 2: Fangpi 搜索测试")
    print("=" * 60)
    
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    base = "https://www.fangpi.net"
    
    queries = [
        ("Juicy",                    "简单查询"),
        ("Nuthin But A G Thang",     "正常查询"),
        ("Juicy The Notorious B.I.G.", "含句号(.)的查询"),
    ]
    
    for query, desc in queries:
        print(f"\n  --- {desc}: '{query}' ---")
        
        # 清理特殊字符（修复逻辑）
        clean_query = re.sub(r'[./"\\]', ' ', query)
        clean_query = re.sub(r'\s+', ' ', clean_query).strip()
        print(f"  清理后: '{clean_query}'")
        
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
                # POST
                r1 = await client.post(f"{base}/api/s", data={"keyword": clean_query},
                    headers={"User-Agent": ua, "Referer": f"{base}/"})
                print(f"  POST /api/s => {r1.status_code}")
                
                search_path = None
                try:
                    body = r1.json()
                    if body.get("code") == 1 and body.get("data", {}).get("u"):
                        search_path = body["data"]["u"]
                        print(f"  API返回路径: {search_path}")
                except:
                    print(f"  API返回非JSON: {r1.text[:100]}")
                
                if search_path:
                    search_url = f"{base}{search_path}"
                else:
                    from urllib.parse import quote
                    search_url = f"{base}/s/{quote(clean_query, safe='')}"
                
                # GET
                r2 = await client.get(search_url, headers={"User-Agent": ua, "Referer": f"{base}/"})
                matches = re.findall(r'href="/music/(\d+)"[^>]*?title="([^"]+)"', r2.text)
                print(f"  GET {search_url[:60]}... => {r2.status_code}, 匹配数={len(matches)}")
                if matches:
                    print(f"  前3个结果: {[(m[0], m[1][:30]) for m in matches[:3]]}")
                if r2.status_code >= 400:
                    print(f"  ⚠️  搜索页返回 {r2.status_code}!")
        except Exception as e:
            print(f"  ❌ 异常: {e}")
    
    print()


# ═══════════════════════════════════════════════════════════════
# STEP 3: Kuwo 搜索测试
# ═══════════════════════════════════════════════════════════════
async def step3_kuwo_search():
    import httpx
    print("=" * 60)
    print("STEP 3: Kuwo 搜索测试")
    print("=" * 60)
    
    ua = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/116.0 Mobile Safari/537.36"
    
    query = "Juicy The Notorious B.I.G."
    print(f"  查询: '{query}'")
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            resp = await client.get("https://search.kuwo.cn/r.s",
                params={"ft": "music", "rformat": "json", "encoding": "utf8", "rn": "5", "pn": "0", "all": query},
                headers={"User-Agent": ua, "Referer": "https://m.kuwo.cn/"})
            print(f"  Status: {resp.status_code}")
            ids = re.findall(r"['\"]MUSICRID['\"]:\s*['\"]MUSIC_(\d+)['\"]", resp.text)
            names = re.findall(r"['\"]NAME['\"]\s*:\s*['\"]([^'\"]*)['\"]", resp.text)
            print(f"  找到 {len(ids)} 个结果")
            for i in range(min(3, len(ids))):
                name = names[i].replace("&nbsp;", " ").replace("&amp;", "&") if i < len(names) else "?"
                print(f"    [{i}] id={ids[i]}, title={name}")
    except Exception as e:
        print(f"  ❌ 异常: {e}")
    
    print()


# ═══════════════════════════════════════════════════════════════
# STEP 4: Fangpi 音频URL获取
# ═══════════════════════════════════════════════════════════════
async def step4_fangpi_audio():
    import httpx
    print("=" * 60)
    print("STEP 4: Fangpi 音频URL获取")
    print("=" * 60)
    
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    base = "https://www.fangpi.net"
    
    # 先搜一个确定存在的歌
    print("  先搜索 'Juicy' 获取fangpi ID...")
    fangpi_id = None
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            r1 = await client.post(f"{base}/api/s", data={"keyword": "Juicy"},
                headers={"User-Agent": ua, "Referer": f"{base}/"})
            body = r1.json()
            search_path = body.get("data", {}).get("u", "")
            if search_path:
                r2 = await client.get(f"{base}{search_path}",
                    headers={"User-Agent": ua, "Referer": f"{base}/"})
                m = re.search(r'href="/music/(\d+)"', r2.text)
                if m:
                    fangpi_id = m.group(1)
    except Exception as e:
        print(f"  搜索失败: {e}")
    
    if not fangpi_id:
        print("  ❌ 未找到任何fangpi歌曲ID，跳过")
        print()
        return
    
    print(f"  使用 fangpi_id={fangpi_id}")
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            # 获取歌曲页面
            resp = await client.get(f"{base}/music/{fangpi_id}",
                headers={"User-Agent": ua, "Referer": f"{base}/"})
            print(f"  GET /music/{fangpi_id} => {resp.status_code}")
            
            # 提取 play_id
            m = re.search(r"window\.appData\s*=\s*JSON\.parse\('(.+?)'\)", resp.text)
            if not m:
                print(f"  ❌ 无法找到 window.appData")
                print(f"     页面前500字符: {resp.text[:500]}")
                return
            
            raw = m.group(1).encode("utf-8").decode("unicode_escape")
            data = json.loads(raw)
            play_id = data.get("play_id", "")
            print(f"  play_id={play_id}")
            
            # 获取播放URL
            r2 = await client.post(f"{base}/api/play-url", data={"id": play_id},
                headers={"User-Agent": ua, "Referer": f"{base}/music/{fangpi_id}"})
            print(f"  POST /api/play-url => {r2.status_code}")
            print(f"  Response: {r2.text[:300]}")
            
            body = r2.json()
            audio_url = body.get("data", {}).get("url", "")
            if audio_url:
                print(f"  ✅ 音频URL: {audio_url[:80]}...")
            else:
                print(f"  ❌ 未获取到音频URL")
    except Exception as e:
        print(f"  ❌ 异常: {e}")
    
    print()


# ═══════════════════════════════════════════════════════════════
# STEP 5: Kuwo 音频URL获取
# ═══════════════════════════════════════════════════════════════
async def step5_kuwo_audio():
    import httpx
    print("=" * 60)
    print("STEP 5: Kuwo 音频URL获取 + 下载测试")
    print("=" * 60)
    
    ua_download = "okhttp/3.10.0"
    music_id = "28709224"  # Nuthin But A G Thang
    
    print(f"  Kuwo music_id={music_id}")
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            resp = await client.get(
                f"https://antiserver.kuwo.cn/anti.s?type=convert_url3&rid={music_id}&format=mp3&response=url",
                headers={"User-Agent": ua_download})
            print(f"  Status: {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")
            
            audio_url = None
            try:
                body = resp.json()
                audio_url = body.get("url", "")
            except:
                if resp.text.strip().startswith("http"):
                    audio_url = resp.text.strip()
            
            if audio_url:
                print(f"  ✅ 音频URL: {audio_url[:80]}...")
                
                # 尝试下载前 100KB
                print(f"  尝试下载...")
                resp2 = await client.get(audio_url, headers={
                    "User-Agent": ua_download,
                    "Range": "bytes=0-102400",
                })
                print(f"  下载 Status: {resp2.status_code}")
                print(f"  Content-Type: {resp2.headers.get('content-type', '?')}")
                print(f"  下载大小: {len(resp2.content)} bytes")
                
                if len(resp2.content) > 1000:
                    print(f"  ✅ 下载正常")
                else:
                    print(f"  ❌ 下载内容过小")
                    print(f"  内容: {resp2.text[:200]}")
            else:
                print(f"  ❌ 未获取到音频URL")
    except Exception as e:
        print(f"  ❌ 异常: {e}")
    
    print()


# ═══════════════════════════════════════════════════════════════
# STEP 6: 实际 API 端点测试（如果在容器/服务器上运行）
# ═══════════════════════════════════════════════════════════════
async def step6_api_test():
    import httpx
    print("=" * 60)
    print("STEP 6: 后端 API 端点测试")
    print("=" * 60)
    
    base_urls = ["http://localhost:8000", "http://127.0.0.1:8000"]
    api_base = None
    
    for base in base_urls:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{base}/health")
                if r.status_code == 200:
                    api_base = base
                    print(f"  ✅ 后端可达: {base}")
                    break
        except:
            pass
    
    if not api_base:
        print("  ⚠️  后端API不可达（在非服务器环境下正常）")
        print()
        return
    
    # 测试搜索 API
    print(f"\n  测试 /api/fangpi/search ...")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{api_base}/api/fangpi/search",
                json={"query": "Juicy"})
            print(f"  Status: {r.status_code}")
            data = r.json()
            songs = data.get("data", {}).get("songs", [])
            print(f"  结果数: {len(songs)}")
            if songs:
                for s in songs[:3]:
                    print(f"    {s['title'][:30]} - {s.get('artist','')[:20]} (id={s['id']}, source={s.get('source','?')})")
    except Exception as e:
        print(f"  ❌ 异常: {e}")
    
    # 测试 batch-search API
    print(f"\n  测试 /api/fangpi/batch-search ...")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{api_base}/api/fangpi/batch-search",
                json={"songs": [
                    {"title": "Juicy", "artist": "The Notorious B.I.G."},
                    {"title": "Elevate", "artist": "Jigmastas"},
                ]})
            print(f"  Status: {r.status_code}")
            data = r.json()
            results = data.get("data", {}).get("results", [])
            for res in results:
                found = res.get("found", False)
                candidates = res.get("candidates", [])
                best = candidates[0] if candidates else {}
                print(f"    {res['title'][:25]}: found={found}, best={best.get('title','N/A')[:25]} (source={best.get('source','?')}, id={best.get('id','?')})")
    except Exception as e:
        print(f"  ❌ 异常: {e}")
    
    # 测试 parse-playlist API
    print(f"\n  测试 /api/fangpi/parse-playlist (网易云) ...")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{api_base}/api/fangpi/parse-playlist",
                json={"url": "https://music.163.com/playlist?id=25672837"})
            print(f"  Status: {r.status_code}")
            data = r.json()
            tracks = data.get("data", {}).get("tracks", [])
            name = data.get("data", {}).get("name", "?")
            print(f"  歌单名: {name}, 歌曲数: {len(tracks)}")
    except Exception as e:
        print(f"  ❌ 异常: {e}")
    
    print()


# ═══════════════════════════════════════════════════════════════
# STEP 7: 完整下载流程 E2E 测试
# ═══════════════════════════════════════════════════════════════
async def step7_e2e():
    import httpx
    print("=" * 60)
    print("STEP 7: 端到端下载测试 (不经过后端API)")
    print("=" * 60)
    
    ua_browser = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ua_download = "okhttp/3.10.0"
    base = "https://www.fangpi.net"
    
    title = "Juicy"
    artist = "The Notorious B.I.G."
    print(f"  目标: {title} - {artist}")
    
    # Search fangpi
    clean_q = re.sub(r'[./"\\]', ' ', f"{title} {artist}")
    clean_q = re.sub(r'\s+', ' ', clean_q).strip()
    print(f"  搜索(清理后): '{clean_q}'")
    
    fangpi_id = None
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
            r1 = await client.post(f"{base}/api/s", data={"keyword": clean_q},
                headers={"User-Agent": ua_browser, "Referer": f"{base}/"})
            body = r1.json()
            search_path = body.get("data", {}).get("u")
            if search_path:
                r2 = await client.get(f"{base}{search_path}",
                    headers={"User-Agent": ua_browser, "Referer": f"{base}/"})
                for m in re.finditer(r'href="/music/(\d+)"[^>]*?title="([^"]+)"', r2.text):
                    t = m.group(2).replace("&nbsp;", " ").replace("&#039;", "'").split(" - ")[0].strip()
                    if "juicy" in t.lower():
                        fangpi_id = m.group(1)
                        print(f"  ✅ Fangpi匹配: id={fangpi_id}, title={t}")
                        break
    except Exception as e:
        print(f"  Fangpi搜索异常: {e}")
    
    if not fangpi_id:
        print(f"  ⚠️  Fangpi未匹配，尝试Kuwo...")
    
    # Get audio URL
    audio_url = None
    if fangpi_id:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
                resp = await client.get(f"{base}/music/{fangpi_id}",
                    headers={"User-Agent": ua_browser, "Referer": f"{base}/"})
                m = re.search(r"window\.appData\s*=\s*JSON\.parse\('(.+?)'\)", resp.text)
                if m:
                    raw = m.group(1).encode("utf-8").decode("unicode_escape")
                    data = json.loads(raw)
                    play_id = data.get("play_id", "")
                    if play_id:
                        r2 = await client.post(f"{base}/api/play-url", data={"id": play_id},
                            headers={"User-Agent": ua_browser, "Referer": f"{base}/music/{fangpi_id}"})
                        body = r2.json()
                        audio_url = body.get("data", {}).get("url")
                        if audio_url:
                            print(f"  ✅ Fangpi音频URL: {audio_url[:60]}...")
        except Exception as e:
            print(f"  Fangpi音频获取异常: {e}")
    
    # Kuwo fallback
    if not audio_url:
        print(f"  尝试Kuwo fallback...")
        ua_mobile = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/116.0 Mobile Safari/537.36"
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=12) as client:
                resp = await client.get("https://search.kuwo.cn/r.s",
                    params={"ft": "music", "rformat": "json", "encoding": "utf8", "rn": "5", "pn": "0", "all": f"{title} {artist}"},
                    headers={"User-Agent": ua_mobile, "Referer": "https://m.kuwo.cn/"})
                ids = re.findall(r"['\"]MUSICRID['\"]:\s*['\"]MUSIC_(\d+)['\"]", resp.text)
                if ids:
                    resp2 = await client.get(
                        f"https://antiserver.kuwo.cn/anti.s?type=convert_url3&rid={ids[0]}&format=mp3&response=url",
                        headers={"User-Agent": ua_download})
                    try:
                        body = resp2.json()
                        audio_url = body.get("url")
                    except:
                        if resp2.text.strip().startswith("http"):
                            audio_url = resp2.text.strip()
                    if audio_url:
                        print(f"  ✅ Kuwo音频URL: {audio_url[:60]}...")
        except Exception as e:
            print(f"  Kuwo fallback异常: {e}")
    
    if not audio_url:
        print(f"  ❌ 最终结果: 无法获取任何音频URL")
        return
    
    # Download
    print(f"  下载测试...")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(audio_url, headers={"User-Agent": ua_download})
            size = len(resp.content)
            print(f"  Status: {resp.status_code}, Size: {size} bytes ({size//1024} KB)")
            print(f"  Content-Type: {resp.headers.get('content-type', '?')}")
            if size >= 200000:
                print(f"  ✅ 下载成功！文件大小正常")
            else:
                print(f"  ❌ 文件过小（<200KB），可能是VIP限制")
                print(f"  内容前100字节: {resp.content[:100]}")
    except Exception as e:
        print(f"  ❌ 下载异常: {e}")
    
    print()


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════
async def main():
    print("\n" + "🔍 " * 20)
    print("  HarBeat 歌单导入诊断工具")
    print("🔍 " * 20 + "\n")
    
    step0_env()
    await step1_network()
    await step2_fangpi_search()
    await step3_kuwo_search()
    await step4_fangpi_audio()
    await step5_kuwo_audio()
    await step6_api_test()
    await step7_e2e()
    
    print("=" * 60)
    print("诊断完成！请将以上输出发给开发者分析。")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
