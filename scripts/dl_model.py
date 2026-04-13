"""Download ONNX model for ChromaDB"""
import urllib.request
import os
import shutil

url = 'https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz'
dst = '/tmp/onnx_model.tar.gz'
final_dir = '/root/.cache/chroma/onnx_models/all-MiniLM-L6-v2'
final = os.path.join(final_dir, 'onnx.tar.gz')

print(f"Downloading {url} ...")
try:
    urllib.request.urlretrieve(url, dst)
    print(f"Downloaded to {dst}, size: {os.path.getsize(dst)}")
    os.makedirs(final_dir, exist_ok=True)
    shutil.copy2(dst, final)
    print(f"Copied to {final}")
except Exception as e:
    print(f"Error: {e}")
