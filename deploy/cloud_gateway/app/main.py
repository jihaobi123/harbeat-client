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

# RK3588 edge registry. Each entry maps rk_id → reachable base URL (Tailscale/frp).
# Extend by setting RKnnn_BASE_URL env var or editing this dict.
RK_REGISTRY: dict[str, str] = {
    "rk-001": os.getenv("RK001_BASE_URL", "http://100.91.30.54:9000"),
}


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


@app.get("/edge/registry")
async def edge_registry():
    return {"code": 0, "message": "ok", "data": {"rk_ids": list(RK_REGISTRY.keys())}}


# IMPORTANT: /edge/{rk_id}/{path:path} MUST be declared BEFORE the generic
# catchall `/{path:path}` proxy below — FastAPI matches in registration order.
@app.api_route(
    "/edge/{rk_id}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_to_rk(request: Request, rk_id: str, path: str):
    """Proxy /edge/<rk_id>/* to the specified RK3588 edge node."""
    base = RK_REGISTRY.get(rk_id)
    if not base:
        return Response(
            content=f'{{"code":1,"message":"unknown rk_id: {rk_id}","data":null}}',
            status_code=404,
            media_type="application/json",
        )
    async with httpx.AsyncClient(timeout=60) as client:
        url = f"{base.rstrip('/')}/{path}"
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length", "transfer-encoding")
        }
        body = await request.body()
        try:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                params=dict(request.query_params),
                content=body,
            )
        except httpx.RequestError as e:
            return Response(
                content=f'{{"code":1,"message":"edge unreachable: {e}","data":null}}',
                status_code=502,
                media_type="application/json",
            )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers),
        )


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
