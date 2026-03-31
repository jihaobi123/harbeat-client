# ---- Stage 1: Build web frontend ----
FROM node:20-slim AS web-builder
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ .
RUN npm run build

# ---- Stage 2: Python API + built frontend ----
FROM python:3.12-slim

WORKDIR /app

# Install system deps for librosa (libsndfile)
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copy built web frontend
COPY --from=web-builder /web/dist /app/web/dist

# Create upload directory
RUN mkdir -p /app/data/music-files

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

