"""WebUI entry point for Git Multi-Sync Center configuration editor.

Usage:
    python webui.py                  # default port 8765
    python webui.py --port 8080      # custom port
    python webui.py --config /path/to/sync.yaml
"""
from __future__ import annotations

import argparse

import uvicorn

from src.webui.main import create_app


def main():
    parser = argparse.ArgumentParser(description="WebUI config editor")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--config", default=None, help="Path to sync.yaml")
    args = parser.parse_args()

    app = create_app(config_path=args.config)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
