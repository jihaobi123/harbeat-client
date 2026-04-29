"""Download ChromaDB's ONNX model manually (faster than letting ChromaDB do it)."""
import urllib.request, tarfile, os

url = "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
dest = "/root/.cache/chroma/onnx_models/all-MiniLM-L6-v2"
tar_path = os.path.join(dest, "onnx.tar.gz")
os.makedirs(dest, exist_ok=True)

# Remove partial download
if os.path.exists(tar_path):
    sz = os.path.getsize(tar_path)
    if sz > 50_000_000:  # >50MB means likely already downloaded
        print(f"onnx.tar.gz already exists ({sz / 1024 / 1024:.1f} MB), skipping download")
    else:
        print(f"Removing partial download ({sz / 1024 / 1024:.1f} MB)")
        os.remove(tar_path)

if not os.path.exists(tar_path) or os.path.getsize(tar_path) < 50_000_000:
    print(f"Downloading ONNX model from {url} ...")
    urllib.request.urlretrieve(url, tar_path)

fsize = os.path.getsize(tar_path)
print(f"File size: {fsize / 1024 / 1024:.1f} MB")

# Check if already extracted
extracted = os.path.join(dest, "onnx")
if os.path.isdir(extracted) and os.path.exists(os.path.join(extracted, "model.onnx")):
    print("Already extracted, done!")
else:
    print("Extracting...")
    with tarfile.open(tar_path) as tar:
        tar.extractall(dest)
    print("Extracted!")

print("Contents:", os.listdir(dest))
if os.path.isdir(extracted):
    print("Model files:", os.listdir(extracted))
