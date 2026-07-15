"""WebUI entry point for Git Multi-Sync Center configuration editor.

Usage:
    python webui.py                  # 生产模式 (默认): API + 托管 frontend/dist SPA, 端口 8765
    python webui.py --mode dev       # 开发模式: 仅启动 API (8765), 前端由 vite dev (5173) 代理
    python webui.py --port 8080
    python webui.py --config /path/to/sync.yaml
"""
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.webui.main import create_app

ROOT = Path(__file__).resolve().parent


def build_prod_app(config_path: str | None) -> FastAPI:
    app = create_app(config_path=config_path)
    dist = ROOT / "frontend" / "dist"
    if dist.is_dir():
        # SPA fallback: 所有非 /api 路径回退到 index.html
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")
    else:
        print(f"[warn] {dist} 不存在，未挂载前端静态文件（仅 API 可用）")
    return app


def main():
    parser = argparse.ArgumentParser(description="WebUI config editor")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--config", default=None, help="Path to sync.yaml")
    parser.add_argument("--mode", choices=["dev", "prod"], default="prod",
                        help="dev=仅API; prod=API+托管前端 (default: prod)")
    args = parser.parse_args()

    app = create_app(config_path=args.config) if args.mode == "dev" else build_prod_app(args.config)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
