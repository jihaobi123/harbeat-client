# ---- Stage 0: Build libKeyFinder + keyfinder-cli ----
FROM debian:trixie-slim AS keyfinder-builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git pkg-config libfftw3-dev \
    libavcodec-dev libavformat-dev libavutil-dev libswresample-dev && \
    rm -rf /var/lib/apt/lists/*
RUN git clone --branch 2.2.8 --depth 1 https://github.com/mixxxdj/libkeyfinder.git /src/libkeyfinder && \
    cmake -S /src/libkeyfinder -B /src/libkeyfinder/build -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX=/opt/keyfinder -DCMAKE_INSTALL_LIBDIR=lib && \
    cmake --build /src/libkeyfinder/build --parallel && \
    cmake --install /src/libkeyfinder/build
RUN git clone https://github.com/evanpurkhiser/keyfinder-cli.git /src/keyfinder-cli && \
    git -C /src/keyfinder-cli checkout 8958d9219fda8a48952da365d19752e43ee81f63 && \
    cmake -S /src/keyfinder-cli -B /src/keyfinder-cli/build -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/opt/keyfinder -DCMAKE_PREFIX_PATH=/opt/keyfinder && \
    cmake --build /src/keyfinder-cli/build --parallel && \
    cmake --install /src/keyfinder-cli/build && \
    mkdir -p /opt/keyfinder/licenses/libkeyfinder /opt/keyfinder/licenses/keyfinder-cli && \
    cp /src/libkeyfinder/LICENSE /opt/keyfinder/licenses/libkeyfinder/ && \
    cp /src/keyfinder-cli/LICENSE /opt/keyfinder/licenses/keyfinder-cli/

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

# Install system deps for librosa (libsndfile)
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 ffmpeg libfftw3-3 && rm -rf /var/lib/apt/lists/*

COPY --from=keyfinder-builder /opt/keyfinder /opt/keyfinder
ENV PATH="/opt/keyfinder/bin:${PATH}" \
    LD_LIBRARY_PATH="/opt/keyfinder/lib:${LD_LIBRARY_PATH}"

# Use China mirrors for pip + install CPU-only torch (much smaller)
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 5 --no-deps \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.6.0+cpu torchaudio==2.6.0+cpu && \
    pip install --no-cache-dir --timeout 300 --retries 5 \
    -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    -r requirements.txt

COPY . .

# Copy built web frontend
COPY --from=web-builder /web/dist /app/web/dist

# Create upload directory
RUN mkdir -p /app/data/music-files

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
