# ---- Stage 1: Build web frontend ----
FROM node:20-slim AS web-builder
WORKDIR /web
RUN npm config set registry https://registry.npmmirror.com
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ .
RUN npm run build

# ---- Stage 2: Python API + built frontend ----
FROM python:3.12-slim

WORKDIR /app

# Use China mirrors for apt (Debian Trixie)
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true

# Install system deps for librosa (libsndfile) + rubberband (professional time-stretch)
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 ffmpeg rubberband-cli && rm -rf /var/lib/apt/lists/*

# Use China mirrors for pip + install CPU-only torch (much smaller)
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 5 --no-deps \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.6.0+cpu torchaudio==2.6.0+cpu && \
    pip install --no-cache-dir --timeout 300 --retries 5 \
    -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    -r requirements.txt

# Optional: madmom for enhanced beat/downbeat RNN detection (falls back to librosa if unavailable)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && pip install --no-cache-dir \
       -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
       cython madmom \
    ; apt-get purge -y --auto-remove gcc \
    ; rm -rf /var/lib/apt/lists/*

COPY . .

# Copy built web frontend
COPY --from=web-builder /web/dist /app/web/dist

# Create upload directory
RUN mkdir -p /app/data/music-files

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

