from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import httpx
import os

app = FastAPI(title="HarBeat Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JETSON_BASE_URL = os.getenv("JETSON_BASE_URL", "http://100.91.30.53:8000")


@app.get("/health")
async def health():
    return {"code": 0, "message": "ok", "data": {"service": "gateway", "status": "ok"}}


@app.get("/jetson/health")
async def jetson_health():
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{JETSON_BASE_URL}/health")
            return {"code": 0, "message": "ok", "data": {"jetson": resp.json()}}
        except Exception as e:
            return {"code": 1, "message": str(e), "data": None}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_to_jetson(request: Request, path: str):
    """Proxy all unmatched routes to Jetson node."""
    async with httpx.AsyncClient(timeout=60) as client:
        url = f"{JETSON_BASE_URL}/{path}"
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length", "transfer-encoding")
        }
        body = await request.body()

        resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            params=dict(request.query_params),
            content=body,
        )

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers),
        )
