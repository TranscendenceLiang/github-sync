"""API tests for the WebUI config editor."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import webui as webui_mod
from src.webui.main import create_app


@pytest.fixture
def app(tmp_path):
    """Fresh app with an empty topology config file."""
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(
        "sync:\n"
        "  settings:\n"
        "    auto_create: false\n"
        "    force_push: false\n"
        "    delete_remote: false\n"
        "    mode: mirror\n"
        "  topology: []\n"
    )
    return create_app(config_path=str(cfg_file))


@pytest.fixture
def client(app):
    """AsyncClient wired to the app."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_config_returns_defaults(client):
    """GET /api/config on an empty topology returns defaults."""
    r = await client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "settings" in data
    assert "topology" in data
    assert data["topology"] == []


@pytest.mark.asyncio
async def test_save_and_reload_config(client, tmp_path):
    """POST a config then GET it back; fields must be preserved."""
    payload = {
        "settings": {
            "auto_create": False,
            "force_push": True,
            "delete_remote": False,
            "mode": "rebase",
            "preserve_files": None,
            "sync_releases": True,
            "release_asset_max_size_mb": 100,
            "release_filter": {
                "mode": "all",
                "latest_count": 5,
                "pattern": None,
                "tags": None,
                "include_drafts": False,
            },
        },
        "topology": [
            {
                "name": "my-repo",
                "source": {
                    "platform": "github",
                    "owner": "myorg",
                    "repo": "myrepo",
                    "branch": "main",
                    "auth": "ssh",
                    "auto_create": False,
                    "visibility": "private",
                },
                "targets": [
                    {
                        "platform": "cnb",
                        "owner": "myorg",
                        "repo": "myrepo-mirror",
                        "branch": "main",
                        "auth": "ssh",
                        "auto_create": False,
                        "visibility": "private",
                    }
                ],
            }
        ],
    }

    r = await client.post("/api/config", json=payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = await client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert data["settings"]["mode"] == "rebase"
    assert data["settings"]["sync_releases"] is True
    assert data["settings"]["release_asset_max_size_mb"] == 100
    assert len(data["topology"]) == 1
    assert data["topology"][0]["name"] == "my-repo"
    assert data["topology"][0]["source"]["platform"] == "github"
    assert data["topology"][0]["source"]["branch"] == "main"


@pytest.mark.asyncio
async def test_validate_endpoint(client):
    """POST /api/validate with a valid empty config returns ok=True."""
    r = await client.post("/api/validate", json={"settings": {}, "topology": []})
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_validate_rejects_invalid(client):
    """Mutually exclusive branch+branches on an endpoint returns 400."""
    r = await client.post(
        "/api/validate",
        json={
            "settings": {},
            "topology": [
                {
                    "name": "bad-entry",
                    "source": {
                        "platform": "github",
                        "owner": "org",
                        "repo": "repo",
                        "branch": "main",
                        "branches": ["main", "develop"],
                        "auth": "ssh",
                        "auto_create": False,
                        "visibility": "private",
                    },
                    "targets": [
                        {
                            "platform": "github",
                            "owner": "org2",
                            "repo": "repo2",
                            "auth": "ssh",
                            "auto_create": False,
                            "visibility": "private",
                        }
                    ],
                }
            ],
        },
    )
    assert r.status_code == 400
    assert "mutually exclusive" in r.json()["error"]


@pytest.mark.asyncio
async def test_save_with_branches(client, tmp_path):
    """Config with branches (no branch) is preserved round-trip."""
    payload = {
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
        "topology": [
            {
                "name": "multi-branch",
                "source": {
                    "platform": "github",
                    "owner": "org",
                    "repo": "repo",
                    "branch": None,
                    "branches": ["main", "develop", "feature-x"],
                    "auth": "ssh",
                    "auto_create": False,
                    "visibility": "private",
                },
                "targets": [
                    {
                        "platform": "github",
                        "owner": "org2",
                        "repo": "repo2",
                        "auth": "ssh",
                        "auto_create": False,
                        "visibility": "private",
                    }
                ],
            }
        ],
    }

    r = await client.post("/api/config", json=payload)
    assert r.status_code == 200

    r = await client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    entry = data["topology"][0]
    assert entry["source"]["branch"] is None
    assert entry["source"]["branches"] == ["main", "develop", "feature-x"]


@pytest.mark.asyncio
async def test_save_with_release_filter(client, tmp_path):
    """sync_releases + release_filter fields survive a save/reload cycle."""
    payload = {
        "settings": {
            "auto_create": False,
            "force_push": False,
            "delete_remote": False,
            "mode": "mirror",
            "preserve_files": None,
            "sync_releases": True,
            "release_asset_max_size_mb": 25,
            "release_filter": {
                "mode": "tags",
                "latest_count": 1,
                "pattern": None,
                "tags": ["v1.0", "v2.0"],
                "include_drafts": True,
            },
        },
        "topology": [],
    }

    r = await client.post("/api/config", json=payload)
    assert r.status_code == 200

    r = await client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert data["settings"]["sync_releases"] is True
    assert data["settings"]["release_asset_max_size_mb"] == 25
    rf = data["settings"]["release_filter"]
    assert rf["mode"] == "tags"
    assert rf["tags"] == ["v1.0", "v2.0"]
    assert rf["include_drafts"] is True


@pytest.mark.asyncio
async def test_get_config_when_file_missing(tmp_path):
    """App with a non-existent config path returns defaults, not 400."""
    app = create_app(config_path=str(tmp_path / "nonexistent.yaml"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "settings" in data
    assert "topology" in data


@pytest.mark.asyncio
async def test_full_round_trip(client, tmp_path):
    """End-to-end: create entry with branches + release_filter, save, reload, verify."""
    payload = {
        "settings": {
            "auto_create": True,
            "force_push": False,
            "delete_remote": True,
            "mode": "mirror",
            "preserve_files": [".cnb.yml"],
            "sync_releases": True,
            "release_asset_max_size_mb": 50,
            "release_filter": {
                "mode": "all",
                "latest_count": 1,
                "pattern": None,
                "tags": None,
                "include_drafts": False,
            },
        },
        "topology": [
            {
                "name": "full-test",
                "source": {
                    "platform": "github", "owner": "a", "repo": "b",
                    "branch": None, "branches": ["main", "dev"],
                    "auth": "ssh", "auto_create": False, "visibility": "private",
                },
                "targets": [
                    {
                        "platform": "cnb", "owner": "a", "repo": "b",
                        "branch": "main", "branches": None,
                        "auth": "pat", "auto_create": True, "visibility": "private",
                    },
                    {
                        "platform": "gitee", "owner": "a", "repo": "b",
                        "branch": "mirror", "branches": None,
                        "auth": "ssh", "auto_create": False, "visibility": "public",
                    },
                ],
                "mode": "rebase",
                "preserve_files": [".cnb.yml", "Dockerfile"],
                "sync_releases": True,
                "release_filter": {
                    "mode": "pattern",
                    "latest_count": 1,
                    "pattern": "v*",
                    "tags": None,
                    "include_drafts": False,
                },
            }
        ],
    }

    # Save
    r = await client.post("/api/config", json=payload)
    assert r.status_code == 200, r.text

    # Reload
    r2 = await client.get("/api/config")
    assert r2.status_code == 200
    data = r2.json()

    # Verify settings
    assert data["settings"]["auto_create"] is True
    assert data["settings"]["preserve_files"] == [".cnb.yml"]

    # Verify topology
    entry = data["topology"][0]
    assert entry["name"] == "full-test"
    assert entry["source"]["branches"] == ["main", "dev"]
    assert entry["source"]["branch"] is None
    assert len(entry["targets"]) == 2
    assert entry["targets"][0]["platform"] == "cnb"
    assert entry["targets"][1]["platform"] == "gitee"
    assert entry["mode"] == "rebase"
    assert entry["sync_releases"] is True
    assert entry["release_filter"]["mode"] == "pattern"
    assert entry["release_filter"]["pattern"] == "v*"


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """GET /api/health returns ok status."""
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_index_route_removed(client):
    """GET / no longer serves a template; must 404."""
    r = await client.get("/")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_spa_root_served_in_prod(tmp_path, monkeypatch):
    """Prod mode build_prod_app mounts frontend/dist as SPA root and keeps /api/*."""
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>SPA</body></html>")
    # Redirect webui.ROOT so build_prod_app finds our fake dist.
    monkeypatch.setattr(webui_mod, "ROOT", tmp_path)
    app = webui_mod.build_prod_app(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/")
        assert r.status_code == 200
        assert "SPA" in r.text
        # API routes must still be reachable (not swallowed by the mount).
        r2 = await c.get("/api/health")
        assert r2.status_code == 200
        assert r2.json() == {"status": "ok"}
