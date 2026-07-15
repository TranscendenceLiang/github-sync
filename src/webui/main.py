"""FastAPI app factory and API routes for the WebUI config editor."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import (
    SyncConfig,
    SyncSettings,
    TopologyEntry,
    Endpoint,
    load_config,
    dump_config,
    ConfigError,
)
from src.release_sync import ReleaseFilter


def _default_config() -> dict:
    """Return a default config dict (empty topology, default settings)."""
    return {
        "settings": {
            "auto_create": False,
            "force_push": False,
            "delete_remote": False,
            "mode": "mirror",
            "preserve_files": None,
            "sync_releases": False,
            "release_asset_max_size_mb": 50,
            "release_filter": {
                "mode": "all",
                "latest_count": 1,
                "pattern": None,
                "tags": None,
                "include_drafts": False,
            },
        },
        "topology": [],
    }


def _dataclass_to_dict(obj) -> dict:
    """Recursively convert a dataclass tree to plain dicts for JSON serialization."""
    from dataclasses import is_dataclass, asdict
    if is_dataclass(obj):
        result = {}
        for field_name in obj.__dataclass_fields__:
            val = getattr(obj, field_name)
            if val is not None:
                result[field_name] = _dataclass_to_dict(val)
        return result
    if isinstance(obj, list):
        return [_dataclass_to_dict(item) for item in obj]
    return obj


def _strip_sync_wrapper(cfg: SyncConfig) -> dict:
    """Convert SyncConfig to plain dict without 'sync:' wrapper."""
    return _dataclass_to_dict(cfg)


def _rebuild_config(data: dict) -> SyncConfig:
    """Rebuild a SyncConfig from a plain dict (inverse of _strip_sync_wrapper)."""
    settings_data = data.get("settings", {})
    topology_data = data.get("topology", [])

    # Build settings
    rf_data = settings_data.get("release_filter")
    release_filter = ReleaseFilter(
        mode=rf_data.get("mode", "all") if rf_data else "all",
        latest_count=rf_data.get("latest_count", 1) if rf_data else 1,
        pattern=rf_data.get("pattern") if rf_data else None,
        tags=rf_data.get("tags") if rf_data else None,
        include_drafts=rf_data.get("include_drafts", False) if rf_data else False,
    ) if rf_data else ReleaseFilter()

    settings = SyncSettings(
        auto_create=settings_data.get("auto_create", False),
        force_push=settings_data.get("force_push", False),
        delete_remote=settings_data.get("delete_remote", False),
        mode=settings_data.get("mode", "mirror"),
        preserve_files=settings_data.get("preserve_files"),
        sync_releases=settings_data.get("sync_releases", False),
        release_asset_max_size_mb=settings_data.get("release_asset_max_size_mb", 50),
        release_filter=release_filter,
    )

    topology = []
    for item in topology_data:
        source_data = item.get("source", {})
        targets_data = item.get("targets", [])
        source = Endpoint(
            platform=source_data.get("platform", ""),
            owner=source_data.get("owner", ""),
            repo=source_data.get("repo", ""),
            branch=source_data.get("branch"),
            branches=source_data.get("branches"),
            auth=source_data.get("auth", "ssh"),
            auto_create=source_data.get("auto_create", False),
            visibility=source_data.get("visibility", "private"),
        )
        targets = [
            Endpoint(
                platform=t.get("platform", ""),
                owner=t.get("owner", ""),
                repo=t.get("repo", ""),
                branch=t.get("branch"),
                branches=t.get("branches"),
                auth=t.get("auth", "ssh"),
                auto_create=t.get("auto_create", False),
                visibility=t.get("visibility", "private"),
            )
            for t in item.get("targets", [])
        ]

        rf_data = item.get("release_filter")
        release_filter = None
        if rf_data is not None:
            release_filter = ReleaseFilter(
                mode=rf_data.get("mode", "all"),
                latest_count=rf_data.get("latest_count", 1),
                pattern=rf_data.get("pattern"),
                tags=rf_data.get("tags"),
                include_drafts=rf_data.get("include_drafts", False),
            )

        topology.append(TopologyEntry(
            name=item.get("name", ""),
            source=source,
            targets=targets,
            mode=item.get("mode"),
            preserve_files=item.get("preserve_files"),
            sync_releases=item.get("sync_releases"),
            release_filter=release_filter,
        ))

    return SyncConfig(settings=settings, topology=topology)


def create_app(config_path: str | None = None) -> FastAPI:
    app = FastAPI(title="Git Multi-Sync Center Config Editor")

    resolved_path = Path(config_path) if config_path else (Path.cwd() / "config" / "sync.yaml")

    # Mount static files
    import importlib.resources as res
    static_dir = res.files("src.webui") / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates = Jinja2Templates(directory=str(res.files("src.webui") / "templates"))

    @app.get("/")
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/api/config")
    async def get_config():
        try:
            cfg = load_config(resolved_path)
            return _strip_sync_wrapper(cfg)
        except FileNotFoundError:
            return _default_config()
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    @app.post("/api/config")
    async def save_config(data: dict):
        try:
            cfg = _rebuild_config(data)
            dump_config(cfg, resolved_path)
            return {"ok": True}
        except ConfigError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    @app.post("/api/validate")
    async def validate_config(data: dict):
        try:
            _rebuild_config(data)
            return {"ok": True}
        except ConfigError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    return app
