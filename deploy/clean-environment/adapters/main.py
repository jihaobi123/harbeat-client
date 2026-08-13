from __future__ import annotations

import argparse
from pathlib import Path

from .config import AdapterConfig, JETSON_SERVICES, RK_SERVICES
from .jetson_app import create_jetson_app
from .rk_app import create_rk_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    config = AdapterConfig.load(args.config, expected_service=args.service)
    import uvicorn

    if config.service in JETSON_SERVICES:
        app = create_jetson_app(config)
    elif config.service in RK_SERVICES:
        app = create_rk_app(config)
    else:
        raise SystemExit(f"service adapter not implemented: {config.service}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
