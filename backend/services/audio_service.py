import librosa
import numpy as np
import subprocess
import os

# 定义本地模拟 NAS 的路径
NAS_RAW_DIR = "uploads/raw"
NAS_STEMS_DIR = "uploads/stems"
os.makedirs(NAS_RAW_DIR, exist_ok=True)
os.makedirs(NAS_STEMS_DIR, exist_ok=True)

def analyze_audio_service(file_path: str) -> dict:
    """P0: 分析 BPM 和 Key"""
    y, sr = librosa.load(file_path, sr=None)
    
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = round(float(tempo[0] if isinstance(tempo, (np.ndarray, list)) else tempo), 2)
    
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)
    
    keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    key = keys[np.argmax(chroma_mean)]
    
    return {"bpm": bpm, "key": key, "tags": [f"BPM:{bpm}", f"Key:{key}"]}

def separate_stems_service(file_path: str) -> dict:
    """P1: 将音乐拆分为独立音轨，并返回可访问的相对 URL"""
    command = ["demucs", "-n", "htdemucs", "-o", NAS_STEMS_DIR, file_path]
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if process.returncode == 0:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        # 组装网络可访问的 URL 前缀 (利用 FastAPI 的静态文件代理)
        url_prefix = f"/uploads/stems/htdemucs/{base_name}"
        
        return {
            "status": "success",
            "stems": {
                "vocals_url": f"{url_prefix}/vocals.wav",
                "drums_url": f"{url_prefix}/drums.wav",
                "bass_url": f"{url_prefix}/bass.wav",
                "other_url": f"{url_prefix}/other.wav",
            }
        }
    else:
        try:
            error_msg = process.stderr.decode('utf-8')
        except UnicodeDecodeError:
            error_msg = process.stderr.decode('gbk', errors='replace')
        print(f"【Demucs 真实报错信息】: {error_msg}")
        raise Exception(error_msg)
