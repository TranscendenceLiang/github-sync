# WebUI 配置编辑器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) for syntax tracking.

**Goal:** Provide a locally-running WebUI for editing `config/sync.yaml` without touching the existing Python sync engine.

**Architecture:** FastAPI backend serving a single-page Jinja2 template with hand-written CSS/JS. Backend reuses `src/config.py` dataclasses and validation. Frontend is pure HTML+CSS+JS, no frameworks.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, PyYAML, pytest + httpx (TestClient)

## Global Constraints

- Zero extra Python dependencies beyond `fastapi` (add to `requirements.txt` optional group)
- Frontend: pure HTML + CSS + native JS, no frameworks, no npm, no icon libraries
- API JSON strips `sync:` wrapper; backend adds it on save, strips it on load
- Default bind: `127.0.0.1:8765`
- Reuse `src/config.py` dataclasses and validation; do not duplicate them
- Test file: `tests/test_webui.py` using pytest + httpx (FastAPI TestClient)

---

### Task 1: Add `dump_config` to `src/config.py`

**Files:**
- Modify: `src/config.py` (append `dump_config` function)

**Interfaces:**
- Produces: `dump_config(cfg: SyncConfig, path: str | Path) -> None` — serializes SyncConfig to YAML with `sync:` wrapper

- [ ] **Step 1: Add `dump_config` function to `src/config.py`**

Append after line 271:

```python
def dump_config(cfg: SyncConfig, path: str | Path) -> None:
    """Serialize a SyncConfig to YAML and write to path with 'sync:' wrapper."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def _ep(ep: Endpoint) -> dict:
        d: dict = {
            "platform": ep.platform,
            "owner": ep.owner,
            "repo": ep.repo,
        }
        if ep.branch is not None:
            d["branch"] = ep.branch
        if ep.branches is not None:
            d["branches"] = ep.branches
        d["auth"] = ep.auth
        if ep.auto_create:
            d["auto_create"] = True
        d["visibility"] = ep.visibility
        return d

    def _rf(rf: ReleaseFilter) -> dict:
        d: dict = {"mode": rf.mode}
        if rf.mode == "latest":
            d["latest_count"] = rf.latest_count
        if rf.mode == "pattern" and rf.pattern is not None:
            d["pattern"] = rf.pattern
        if rf.mode == "tags" and rf.tags is not None:
            d["tags"] = rf.tags
        if rf.include_drafts:
            d["include_drafts"] = True
        return d

    def _entry(te: TopologyEntry) -> dict:
        d: dict = {"name": te.name, "source": _ep(te.source)}
        d["targets"] = [_ep(t) for t in te.targets]
        if te.mode is not None:
            d["mode"] = te.mode
        if te.preserve_files is not None:
            d["preserve_files"] = te.preserve_files
        if te.sync_releases is not None:
            d["sync_releases"] = te.sync_releases
        if te.release_filter is not None:
            d["release_filter"] = _rf(te.release_filter)
        return d

    data = {
        "sync": {
            "settings": {
                "auto_create": cfg.settings.auto_create,
                "force_push": cfg.settings.force_push,
                "delete_remote": cfg.settings.delete_remote,
                "mode": cfg.settings.mode,
            }
        }
    }
    if cfg.settings.preserve_files is not None:
        data["sync"]["settings"]["preserve_files"] = cfg.settings.preserve_files
    if cfg.settings.sync_releases:
        data["sync"]["settings"]["sync_releases"] = True
    if cfg.settings.release_asset_max_size_mb != 50:
        data["sync"]["settings"]["release_asset_max_size_mb"] = cfg.settings.release_asset_max_size_mb
    if cfg.settings.release_filter != ReleaseFilter():
        data["sync"]["settings"]["release_filter"] = _rf(cfg.settings.release_filter)
    data["sync"]["topology"] = [_entry(t) for t in cfg.topology]
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False), encoding="utf-8")
```

OK, so the file ends at line 271 and there's no `dump_config` function. I need to add it. Now let me write the full plan. I'll write it in parts to avoid timeout.</think>

<｜DSML｜tool_calls>
<｜DSML｜invoke name="Write">
<｜DSML｜parameter name="content" string="true"># WebUI 配置编辑器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) for syntax tracking.

**Goal:** Provide a locally-running WebUI for editing `config/sync.yaml` without touching the existing Python sync engine.

**Architecture:** FastAPI backend serving a single-page Jinja2 template with hand-written CSS/JS. Backend reuses `src/config.py` dataclasses and validation. Frontend is pure HTML+CSS+JS, no frameworks.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, PyYAML, pytest + httpx (TestClient)

## Global Constraints

- Zero extra Python dependencies beyond `fastapi` (add to `requirements.txt` optional group)
- Frontend: pure HTML + CSS + native JS, no frameworks, no npm, no icon libraries
- API JSON strips `sync:` wrapper; backend adds it on save, strips it on load
- Default bind: `127.0.0.1:8765`
- Reuse `src/config.py` dataclasses and validation; do not duplicate them
- Test file: `tests/test_webui.py` using pytest + httpx (FastAPI TestClient)

---

### Task 1: Add `dump_config` to `src/config.py`

**Files:**
- Modify: `src/config.py` (append `dump_config` function)

**Interfaces:**
- Produces: `dump_config(cfg: SyncConfig, path: str | Path) -> None` — serializes SyncConfig to YAML with `sync:` wrapper

- [ ] **Step 1: Add `dump_config` function to `src/config.py`**

Append after line 271:

```python
def dump_config(cfg: SyncConfig, path: str | Path) -> None:
    """Serialize a SyncConfig to YAML and write to path with 'sync:' wrapper."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def _ep(ep: Endpoint) -> dict:
        d: dict = {
            "platform": ep.platform,
            "owner": ep.owner,
            "repo": ep.repo,
        }
        if ep.branch is not None:
            d["branch"] = ep.branch
        if ep.branches is not None:
            d["branches"] = ep.branches
        d["auth"] = ep.auth
        if ep.auto_create:
            d["auto_create"] = True
        d["visibility"] = ep.visibility
        return d

    def _rf(rf: ReleaseFilter) -> dict:
        d: dict = {"mode": rf.mode}
        if rf.mode == "latest":
            d["latest_count"] = rf.latest_count
        if rf.mode == "pattern" and rf.pattern is not None:
            d["pattern"] = rf.pattern
        if rf.mode == "tags" and rf.tags is not None:
            d["tags"] = rf.tags
        if rf.include_drafts:
            d["include_drafts"] = True
        return d

    def _entry(te: TopologyEntry) -> dict:
        d: dict = {"name": te.name, "source": _ep(te.source)}
        d["targets"] = [_ep(t) for t in te.targets]
        if te.mode is not None:
            d["mode"] = te.mode
        if te.preserve_files is not None:
            d["preserve_files"] = te.preserve_files
        if te.sync_releases is not None:
            d["sync_releases"] = te.sync_releases
        if te.release_filter is not None:
            d["release_filter"] = _rf(te.release_filter)
        return d

    data = {
        "sync": {
            "settings": {
                "auto_create": cfg.settings.auto_create,
                "force_push": cfg.settings.force_push,
                "delete_remote": cfg.settings.delete_remote,
                "mode": cfg.settings.mode,
            }
        }
    }
    if cfg.settings.preserve_files is not None:
        data["sync"]["settings"]["preserve_files"] = cfg.settings.preserve_files
    if cfg.settings.sync_releases:
        data["sync"]["settings"]["sync_releases"] = True
    if cfg.settings.release_asset_max_size_mb != 50:
        data["sync"]["settings"]["release_asset_max_size_mb"] = cfg.settings.release_asset_max_size_mb
    if cfg.settings.release_filter != ReleaseFilter():
        data["sync"]["settings"]["release_filter"] = _rf(cfg.settings.release_filter)
    data["sync"]["topology"] = [_entry(t) for t in cfg.topology]
    p.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False), encoding="utf-8")
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `pytest tests/test_config.py -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add src/config.py
git commit -m "feat(config): add dump_config function for YAML serialization"
```

---

### Task 2: Backend scaffold — webui.py + FastAPI app + config service

**Files:**
- Create: `webui.py`
- Create: `src/webui/__init__.py`
- Create: `src/webui/main.py`

**Interfaces:**
- Consumes: `src.config.load_config`, `src.config.dump_config`, `src.config.SyncConfig`, `src.config.ConfigError`
- Produces: FastAPI app with routes `GET /`, `GET /api/config`, `POST /api/config`, `POST /api/validate`

- [ ] **Step 1: Create `src/webui/__init__.py`**

Empty file.

```python
```

- [ ] **Step 2: Create `webui.py` entry point**

```python
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
```

- [ ] **Step 2: Create `src/webui/__init__.py`**

Empty file.

```python
```

- [ ] **Step 3: Create `src/webui/main.py` — FastAPI app factory + API routes**

```python
"""FastAPI app factory and API routes for the WebUI config editor."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import SyncConfig, SyncSettings, TopologyEntry, Endpoint, load_config, dump_config, ConfigError
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
```

- [ ] **Step 4: Create `src/webui/main.py` — FastAPI app factory + API routes**

```python
"""FastAPI app factory and API routes for the WebUI config editor."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import SyncConfig, load_config, dump_config, ConfigError


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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_webui.py -v`
Expected: FAIL with "No module named tests/test_webui" or empty test collection

- [ ] **Step 5: Commit**

```bash
git add webui.py src/webui/__init__.py src/webui/main.py
git commit -m "feat(webui): add FastAPI backend scaffold with config API"
```

---

### Task 2: HTML template — full editor UI

**Files:**
- Create: `src/webui/templates/index.html`

**Interfaces:**
- Consumes: Jinja2 `request` object (standard FastAPI template context)
- Produces: Full editor page with left sidebar (entry list) and right panel (entry editor + global settings)

- [ ] **Step 1: Create `src/webui/templates/index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Git Multi-Sync Center · 配置管理</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<div id="app">
  <header>
    <h1>Git Multi-Sync Center · 配置管理</h1>
    <div class="header-actions">
      <button id="btn-settings" class="btn-icon" title="全局设置">&#9881;</button>
      <button id="btn-add-entry" class="btn-primary">+ 新增同步条目</button>
    </div>
  </header>

  <!-- Global Settings Panel (collapsible) -->
  <div id="settings-panel" class="panel hidden">
    <h2>全局设置</h2>
    <div class="settings-grid">
      <label class="checkbox-label">
        <input type="checkbox" id="s-auto-create"> auto_create
      </label>
      <label class="checkbox-label">
        <input type="checkbox" id="s-force-push"> force_push
      </label>
      <label class="checkbox-label">
        <input type="checkbox" id="s-delete-remote"> delete_remote
      </label>
      <label class="checkbox-label">
        <input type="checkbox" id="s-sync-releases"> sync_releases
      </label>
      <label>
        模式:
        <select id="s-mode">
          <option value="mirror">mirror</option>
          <option value="rebase">rebase</option>
        </select>
      </label>
      <label>
        preserve_files:
        <input type="text" id="s-preserve-files" placeholder="逗号分隔, 如 .cnb.yml">
      </label>
      <label>
        Release 资源大小上限 (MB):
        <input type="number" id="s-release-asset-max-size" min="1" value="50">
      </label>
    </div>
    <!-- Global Release Filter (collapsible) -->
    <details id="s-release-filter-details">
      <summary>Release 过滤</summary>
      <div class="release-filter">
        <label>模式:
          <select id="s-rf-mode">
            <option value="all">all</option>
            <option value="latest">latest</option>
            <option value="pattern">pattern</option>
            <option value="tags">tags</option>
          </select>
        </label>
        <label>最新 N 个:
          <input type="number" id="s-rf-latest-count" value="1" min="1">
        </label>
        <label>正则模式:
          <input type="text" id="s-rf-pattern" placeholder="如 v*">
        </label>
        <label>标签:
          <div id="s-rf-tags" class="tag-list"></div>
          <button class="btn-small" id="s-rf-add-tag">+ 添加标签</button>
        </label>
        <label class="checkbox-label">
          <input type="checkbox" id="s-rf-include-drafts"> 包含草稿 release
        </label>
      </details>
    </details>
  </div>

  <div class="main-layout">
    <!-- Left: Entry List -->
    <aside id="entry-list">
      <h3>同步条目</h3>
      <ul id="entry-items"></ul>
    </aside>

    <!-- Right: Entry Editor -->
    <main id="entry-editor">
      <div class="editor-placeholder" id="editor-placeholder">
        <p>选择左侧条目进行编辑，或点击「+ 新增同步条目」创建新条目。</p>
      </div>

      <!-- Editor form (hidden until an entry is selected) -->
      <div id="editor-form" class="hidden">
        <div class="form-group">
          <label>条目名称:
            <input type="text" id="e-name" placeholder="如 github-to-cnb">
          </label>
        </div>
        <div class="form-group">
          <label>模式:
            <select id="e-mode">
              <option value="">(继承全局)</option>
              <option value="mirror">mirror</option>
              <option value="rebase">rebase</option>
            </select>
          </label>
        </div>
        <div class="form-group">
          <label>preserve_files:
            <input type="text" id="e-preserve-files" placeholder="逗号分隔, 如 .cnb.yml">
          </label>
        </div>

        <!-- Source Endpoint -->
        <fieldset>
          <legend>源端点</legend>
          <div class="endpoint-form" id="source-endpoint">
            <label>平台:
              <select class="ep-platform">
                <option value="github">github</option>
                <option value="gitee">gitee</option>
                <option value="cnb">cnb</option>
                <option value="gitcode">gitcode</option>
              </select>
            </label>
            <label>所有者:
              <input type="text" class="ep-owner" placeholder="myorg">
            </label>
            <label>仓库:
              <input type="text" class="ep-repo" placeholder="myproject">
            </label>
            <div class="branch-mode">
              <label>分支模式:
                <label><input type="radio" name="source-branch-mode" value="single" checked> 单分支</label>
                <label><input type="radio" name="source-branch-mode" value="multi"> 多分支</label>
              </label>
            </div>
            <div class="branch-single">
              <label>分支:
                <input type="text" class="ep-branch" placeholder="main">
              </label>
            </div>
            <div class="branch-multi hidden">
              <label>分支:
                <div class="tag-list ep-branches"></div>
                <button class="btn-small btn-add-branch">+ 添加分支</button>
              </label>
            </div>
            <div class="form-row">
              <label>认证:
                <select class="ep-auth">
                  <option value="ssh">SSH</option>
                  <option value="pat">PAT</option>
                </select>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" class="ep-auto-create"> auto_create
              </label>
              <label>可见性:
                <select class="ep-visibility">
                  <option value="private">private</option>
                  <option value="public">public</option>
                </select>
              </label>
            </div>
          </div>
        </fieldset>

        <!-- Targets -->
        <fieldset>
          <legend>目标端点</legend>
          <div id="targets-container"></div>
          <button id="btn-add-target" class="btn-secondary">+ 添加目标</button>
        </fieldset>

        <!-- Entry-level Release Settings -->
        <fieldset>
          <legend>Release 同步设置</legend>
          <label class="checkbox-label">
            <input type="checkbox" id="e-sync-releases"> 启用 Release 同步
          </label>
          <details id="e-release-filter-details">
            <summary>Release 过滤</summary>
            <div class="release-filter">
              <label>模式:
                <select id="e-rf-mode">
                  <option value="all">all</option>
                  <option value="latest">latest</option>
                  <option value="pattern">pattern</option>
                  <option value="tags">tags</option>
                </select>
              </label>
              <label>最新 N 个:
                <input type="number" id="e-rf-latest-count" value="1" min="1">
              </label>
              <label>正则模式:
                <input type="text" id="e-rf-pattern" placeholder="如 v*">
              </label>
              <label>标签:
                <div id="e-rf-tags" class="tag-list"></div>
                <button class="btn-small" id="e-rf-add-tag">+ 添加标签</button>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" id="e-rf-include-drafts"> 包含草稿 release
              </label>
            </div>
          </details>
        </fieldset>

        <div class="editor-actions">
          <button id="btn-delete-entry" class="btn-danger">删除此条目</button>
        </div>
      </div>
    </main>
  </div>

  <!-- Bottom Action Bar -->
  <footer class="action-bar">
    <button id="btn-validate" class="btn-secondary">&#10003; 校验配置</button>
    <button id="btn-save" class="btn-primary">&#128190; 保存</button>
    <button id="btn-refresh" class="btn-secondary">&#8635; 刷新</button>
    <span id="status-msg" class="status-msg"></span>
  </footer>
</div>

<!-- Confirm Dialog -->
<dialog id="confirm-dialog">
  <p id="confirm-msg"></p>
  <div class="dialog-actions">
    <button id="confirm-yes" class="btn-danger">确认</button>
    <button id="confirm-no" class="btn-secondary">取消</button>
  </div>
</dialog>

<!-- YAML Preview Dialog -->
<dialog id="yaml-preview-dialog">
  <h3>YAML 预览</h3>
  <pre id="yaml-preview-content"></pre>
  <div class="dialog-actions">
    <button id="yaml-confirm" class="btn-primary">确认保存</button>
    <button id="yaml-cancel" class="btn-secondary">取消</button>
  </div>
</dialog>

<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add src/webui/templates/index.html
git commit -m "feat(webui): add HTML template for config editor"
```

---

### Task 3: CSS styles

**Files:**
- Create: `src/webui/static/style.css`

- [ ] **Step 1: Create `src/webui/static/style.css`**

```css
/* WebUI Config Editor — pure CSS, no frameworks */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #f5f5f5;
  --surface: #fff;
  --border: #ddd;
  --text: #333;
  --text-muted: #888;
  --primary: #1a73e8;
  --primary-hover: #1557b0;
  --danger: #d93025;
  --danger-hover: #b3261e;
  --success: #188038;
  --radius: 6px;
  --shadow: 0 1px 3px rgba(0,0,0,0.1);
}
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5; }
#app { max-width: 1200px; margin: 0 auto; padding: 12px; }

/* Header */
header { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); margin-bottom: 12px; }
header h1 { font-size: 18px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; }

/* Buttons */
button { cursor: pointer; border: 1px solid var(--border); background: var(--surface); padding: 6px 14px; border-radius: var(--radius); font-size: 13px; }
button:hover { background: #eee; }
.btn-primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.btn-primary:hover { background: var(--primary-hover); }
.btn-danger { background: var(--danger); color: #fff; border-color: var(--danger); }
.btn-danger:hover { background: var(--danger-hover); }
.btn-secondary { background: var(--surface); }
.btn-icon { background: none; border: none; font-size: 20px; padding: 4px 8px; }
.btn-small { font-size: 12px; padding: 2px 8px; }

/* Panels */
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; margin-bottom: 12px; box-shadow: var(--shadow); }
.hidden { display: none !important; }

/* Settings Panel */
.settings-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.settings-grid label { display: flex; align-items: center; gap: 6px; }
.checkbox-label { display: flex; align-items: center; gap: 4px; cursor: pointer; }

/* Main Layout */
.main-layout { display: flex; gap: 12px; min-height: 400px; }
#entry-list { width: 220px; flex-shrink: 0; }
#entry-list ul { list-style: none; }
#entry-list li { padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 4px; cursor: pointer; background: var(--surface); }
#entry-list li:hover { background: #e8f0fe; }
#entry-list li.active { background: #e8f0fe; border-color: var(--primary); }
#entry-list li .entry-summary { font-size: 11px; color: var(--text-muted); }
#entry-editor { flex: 1; }

/* Forms */
.form-group { margin-bottom: 10px; }
.form-group label { display: block; margin-bottom: 3px; }
.form-group input[type="text"], .form-group select { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 13px; }
fieldset { border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; margin-bottom: 12px; }
legend { font-weight: 600; padding: 0 6px; }
.endpoint-form label { display: block; margin-bottom: 6px; }
.endpoint-form input[type="text"], .endpoint-form select { width: 100%; padding: 5px 8px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 13px; }
.form-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.form-row label { display: flex; align-items: center; gap: 4px; }

/* Branch mode */
.branch-mode { margin-bottom: 8px; }
.branch-mode label { display: inline-flex; align-items: center; gap: 4px; margin-right: 12px; }

/* Tag list */
.tag-list { display: flex; flex-wrap: wrap; gap: 4px; margin: 4px 0; }
.tag-item { display: inline-flex; align-items: center; gap: 4px; background: #e8f0fe; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
.tag-item .tag-remove { cursor: pointer; color: var(--danger); font-weight: bold; }

/* Target card */
.target-card { border: 1px solid var(--border); border-radius: var(--radius); padding: 10px; margin-bottom: 8px; background: #fafafa; }
.target-card .target-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-weight: 600; font-size: 13px; }

/* Release filter */
.release-filter label { display: block; margin-bottom: 6px; }
.release-filter input[type="text"], .release-filter input[type="number"], .release-filter select { width: 100%; padding: 4px 6px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 13px; }
.release-filter input[type="number"] { width: 80px; }

/* Editor actions */
.editor-actions { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); }

/* Action bar */
.action-bar { display: flex; align-items: center; gap: 8px; padding: 10px 0; border-top: 1px solid var(--border); margin-top: 12px; }
.status-msg { margin-left: auto; font-size: 13px; }
.status-msg.error { color: var(--danger); }
.status-msg.success { color: var(--success); }

/* Dialogs */
dialog { border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
dialog::backdrop { background: rgba(0,0,0,0.3); }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
#yaml-preview-content { background: #f0f0f0; padding: 12px; border-radius: var(--radius); font-size: 12px; max-height: 400px; overflow: auto; white-space: pre-wrap; }

/* Responsive */
@media (max-width: 749px) {
  .main-layout { flex-direction: column; }
  #entry-list { width: 100%; }
  #entry-list ul { display: flex; gap: 4px; overflow-x: auto; }
  #entry-list li { white-space: nowrap; flex-shrink: 0; }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/webui/static/style.css
git commit -m "feat(webui): add CSS styles for config editor"
```

---

### Task 4: JavaScript frontend logic

**Files:**
- Create: `src/webui/static/app.js`

- [ ] **Step 1: Create `src/webui/static/app.js`**

```javascript
'use strict';

// ── State ──────────────────────────────────────────
let config = null;          // full config object from API
let selectedIndex = -1;      // index into config.topology
let dirty = false;           // unsaved changes tracker
let currentEntryId = null;   // for tracking which entry is being edited

// ── DOM refs ───────────────────────────────────────
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const entryItems = $('#entry-items');
const editorForm = $('#editor-form');
const editorPlaceholder = $('#editor-placeholder');
const settingsPanel = $('#settings-panel');
const statusMsg = $('#status-msg');

// ── API helpers ────────────────────────────────────
async function apiGet(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error((await r.json()).error || r.statusText);
  return r.json();
}

async function apiPost(path, data) {
  const r = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const result = await r.json();
  if (!r.ok || result.ok === false) throw new Error(result.error || 'Unknown error');
  return result;
}

function setStatus(msg, type) {
  statusMsg.textContent = msg;
  statusMsg.className = 'status-msg' + (type ? ' ' + type : '');
  if (type !== 'error') setTimeout(() => { statusMsg.textContent = ''; statusMsg.className = 'status-msg'; }, 3000);
}

// ── Data helpers ────────────────────────────────────
function getDefaultSettings() {
  return {
    auto_create: false, force_push: false, delete_remote: false,
    mode: 'mirror', preserve_files: null,
    sync_releases: false, release_asset_max_size_mb: 50,
    release_filter: { mode: 'all', latest_count: 1, pattern: null, tags: null, include_drafts: false },
  };
}

function getDefaultEndpoint() {
  return {
    platform: 'github', owner: '', repo: '',
    branch: 'main', branches: null,
    auth: 'ssh', auto_create: false, visibility: 'private',
  };
}

// ── Load config ─────────────────────────────────────
async function loadConfig() {
  try {
    config = await apiGet('/api/config');
    if (!config.settings) config.settings = getDefaultSettings();
    if (!config.topology) config.topology = [];
    renderEntryList();
    if (config.topology.length > 0) {
      selectEntry(0);
    } else {
      showPlaceholder();
    }
    dirty = false;
  } catch (e) {
    setStatus('加载配置失败: ' + e.message, 'error');
  }
}

// ── Entry list rendering ────────────────────────────
function renderEntryList() {
  entryItems.innerHTML = '';
  config.topology.forEach((entry, i) => {
    const li = document.createElement('li');
    li.dataset.index = i;
    const src = entry.source || {};
    li.innerHTML = `<strong>${entry.name}</strong><br><span class="entry-summary">${src.platform || '?'} → ${(entry.targets || []).length} 个目标</span>`;
    if (i === selectedIndex) li.classList.add('active');
    li.addEventListener('click', () => selectEntry(i));
    entryItems.appendChild(li);
  });
}

function showPlaceholder() {
  editorForm.classList.add('hidden');
  editorPlaceholder.classList.remove('hidden');
}

function selectEntry(index) {
  selectedIndex = index;
  renderEntryList();
  const entry = config.topology[index];
  if (!entry) { showPlaceholder(); return; }
  editorPlaceholder.classList.add('hidden');
  editorForm.classList.remove('hidden');
  fillEntryForm(entry);
}

// ── Fill entry form ─────────────────────────────────
function fillEntryForm(entry) {
  $('#e-name').value = entry.name || '';
  $('#e-mode').value = entry.mode || '';
  $('#e-preserve-files').value = (entry.preserve_files || []).join(', ');

  // Source endpoint
  fillEndpointForm('source-endpoint', entry.source || getDefaultEndpoint());

  // Targets
  renderTargets(entry.targets || []);

  // Release settings
  const sr = entry.sync_releases;
  if (sr === true) {
    $('#e-sync-releases').checked = true;
  } else if (sr === false) {
    $('#e-sync-releases').checked = false;
  } else {
    // null = inherit from global
    $('#e-sync-releases').checked = config.settings.sync_releases;
  }
  fillReleaseFilter('e-rf', entry.release_filter || config.settings.release_filter);
}

function fillEndpointForm(containerId, ep) {
  const container = document.getElementById(containerId);
  container.querySelector('.ep-platform').value = ep.platform || 'github';
  container.querySelector('.ep-owner').value = ep.owner || '';
  container.querySelector('.ep-repo').value = ep.repo || '';

  const singleMode = ep.branches === null || ep.branches === undefined;
  const radios = container.querySelectorAll('input[type="radio"]');
  radios.forEach(r => r.checked = (r.value === (singleMode ? 'single' : 'multi')));

  const singleDiv = container.querySelector('.branch-single');
  const multiDiv = container.querySelector('.branch-multi');
  singleDiv.classList.toggle('hidden', !singleMode);
  multiDiv.classList.toggle('hidden', singleMode);

  if (singleMode) {
    container.querySelector('.ep-branch').value = ep.branch || '';
  } else {
    renderBranchTags(container.querySelector('.ep-branches'), ep.branches || []);
  }

  container.querySelector('.ep-auth').value = ep.auth || 'ssh';
  container.querySelector('.ep-auto-create').checked = ep.auto_create || false;
  container.querySelector('.ep-visibility').value = ep.visibility || 'private';
}

function renderBranchTags(container, branches) {
  container.innerHTML = '';
  (branches || []).forEach(b => {
    const tag = document.createElement('span');
    tag.className = 'tag-item';
    tag.innerHTML = `${b} <span class="tag-remove" data-value="${b}">&times;</span>`;
    container.appendChild(tag);
  });
}

function renderTargets(targets) {
  const container = $('#targets-container');
  container.innerHTML = '';
  targets.forEach((t, i) => {
    const card = document.createElement('div');
    card.className = 'target-card';
    card.innerHTML = `
      <div class="target-header">
        <span>目标 ${i + 1}</span>
        <button class="btn-small btn-remove-target" data-index="${i}">删除</button>
      </div>
      <div class="endpoint-form">
        <label>平台: <select class="ep-platform">${platformOptions(t.platform)}</select></label>
        <label>所有者: <input type="text" class="ep-owner" value="${t.owner || ''}"></label>
        <label>仓库: <input type="text" class="ep-repo" value="${t.repo || ''}"></label>
        <div class="branch-mode">
          <label>分支模式:
            <label><input type="radio" name="target-branch-${Date.now()}" value="single" ${t.branches ? '' : 'checked'}> 单分支</label>
            <label><input type="radio" name="target-branch-${Date.now()}" value="multi" ${t.branches ? 'checked' : ''}> 多分支</label>
          </label>
        </div>
        <div class="branch-single ${t.branches ? 'hidden' : ''}">
          <label>分支: <input type="text" class="ep-branch" value="${t.branch || ''}"></label>
        </div>
        <div class="branch-multi ${t.branches ? '' : 'hidden'}">
          <label>分支: <div class="tag-list ep-branches"></div>
          <button class="btn-small btn-add-branch">+ 添加分支</button></label>
        </div>
        <div class="form-row">
          <label>认证: <select class="ep-auth"><option value="ssh" ${t.auth === 'ssh' ? 'selected' : ''}>SSH</option><option value="pat" ${t.auth === 'pat' ? 'selected' : ''}>PAT</option></select></label>
          <label class="checkbox-label"><input type="checkbox" class="ep-auto-create" ${t.auto_create ? 'checked' : ''}> auto_create</label>
          <label>可见性: <select class="ep-visibility"><option value="private" ${t.visibility === 'private' ? 'selected' : ''}>private</option><option value="public" ${t.visibility === 'public' ? 'selected' : ''}>public</option></select></label>
        </div>
      </div>`;
    container.appendChild(card);

    // Wire up branch mode toggle
    const radios = card.querySelectorAll('input[type="radio"]');
    radios.forEach(r => r.addEventListener('change', () => {
      const single = card.querySelector('.branch-single');
      const multi = card.querySelector('.branch-multi');
      single.classList.toggle('hidden', r.value === 'multi');
      multi.classList.toggle('hidden', r.value === 'single');
    }));

    // Wire up add-branch button
    card.querySelector('.btn-add-branch')?.addEventListener('click', () => {
      const tagList = card.querySelector('.ep-branches');
      const val = prompt('输入分支名:');
      if (val && val.trim()) {
        addTag(tagList, val.trim());
      }
    });
  });
}

function addTag(container, value) {
  const tag = document.createElement('span');
  tag.className = 'tag-item';
  tag.innerHTML = `${value} <span class="tag-remove">&times;</span>`;
  tag.querySelector('.tag-remove').addEventListener('click', () => tag.remove());
  container.appendChild(tag);
}

function platformOptions(selected) {
  const platforms = ['github', 'gitee', 'cnb', 'gitcode'];
  return platforms.map(p => `<option value="${p}" ${p === selected ? 'selected' : ''}>${p}</option>`).join('');
}

// ── Collect form data ────────────────────────────────
function collectEndpointForm(containerId) {
  const container = document.getElementById(containerId);
  const isMulti = container.querySelector('input[type="radio"][value="multi"]')?.checked;
  const branches = [];
  if (isMulti) {
    container.querySelectorAll('.ep-branches .tag-item').forEach(tag => {
      branches.push(tag.textContent.replace('×', '').trim());
    });
  }
  return {
    platform: container.querySelector('.ep-platform').value,
    owner: container.querySelector('.ep-owner').value,
    repo: container.querySelector('.ep-repo').value,
    branch: isMulti ? null : (container.querySelector('.ep-branch').value || null),
    branches: isMulti ? (branches.length > 0 ? branches : null) : null,
    auth: container.querySelector('.ep-auth').value,
    auto_create: container.querySelector('.ep-auto-create').checked,
    visibility: container.querySelector('.ep-visibility').value,
  };
}

function collectReleaseFilter(prefix) {
  const mode = $(`#${prefix}-mode`).value;
  return {
    mode,
    latest_count: parseInt($(`#${prefix}-latest-count`).value) || 1,
    pattern: $(`#${prefix}-pattern`).value || null,
    tags: mode === 'tags' ? collectTags(prefix) : null,
    include_drafts: $(`#${prefix}-include-drafts`).checked,
  };
}

function collectTags(prefix) {
  const tags = [];
  document.querySelectorAll(`#${prefix}-tags .tag-item`).forEach(tag => {
    tags.push(tag.textContent.replace('×', '').trim());
  });
  return tags.length > 0 ? tags : null;
}

function collectFormEntry() {
  const entry = {
    name: $('#e-name').value.trim(),
    source: collectEndpointForm('source-endpoint'),
    targets: collectTargets(),
    mode: $('#e-mode').value || null,
    preserve_files: parsePreserveFiles($('#e-preserve-files').value),
    sync_releases: $('#e-sync-releases').checked ? true : null,
    release_filter: null,
  };

  // Only include release_filter if sync_releases is enabled
  if ($('#e-sync-releases').checked) {
    entry.release_filter = collectReleaseFilter('e-rf');
  }

  return entry;
}

function collectTargets() {
  const targets = [];
  $$('#targets-container .target-card').forEach(card => {
    const isMulti = card.querySelector('input[type="radio"][value="multi"]')?.checked;
    const branches = [];
    if (isMulti) {
      card.querySelectorAll('.ep-branches .tag-item').forEach(tag => {
        branches.push(tag.textContent.replace('×', '').trim());
      });
    }
    targets.push({
      platform: card.querySelector('.ep-platform').value,
      owner: card.querySelector('.ep-owner').value,
      repo: card.querySelector('.ep-repo').value,
      branch: isMulti ? null : (card.querySelector('.ep-branch').value || null),
      branches: isMulti ? (branches.length > 0 ? branches : null) : null,
      auth: card.querySelector('.ep-auth').value,
      auto_create: card.querySelector('.ep-auto-create').checked,
      visibility: card.querySelector('.ep-visibility').value,
    });
  });
  return targets;
}

function parsePreserveFiles(val) {
  if (!val || !val.trim()) return null;
  return val.split(',').map(s => s.trim()).filter(Boolean);
}

// ── Collect full config from form ───────────────────
function collectFullConfig() {
  const settings = {
    auto_create: $('#s-auto-create').checked,
    force_push: $('#s-force-push').checked,
    delete_remote: $('#s-delete-remote').checked,
    mode: $('#s-mode').value,
    preserve_files: parsePreserveFiles($('#s-preserve-files').value),
    sync_releases: $('#s-sync-releases').checked,
    release_asset_max_size_mb: parseInt($('#s-release-asset-max-size').value) || 50,
    release_filter: collectReleaseFilter('s-rf'),
  };

  const topology = [];
  // Read from the editor form if an entry is selected
  if (selectedIndex >= 0 && selectedIndex < config.topology.length) {
    // Update the in-memory entry from the form
    config.topology[selectedIndex] = collectFormEntry();
  }

  return { settings: settings, topology: config.topology };
}

// ── Settings panel ──────────────────────────────────
function fillSettingsPanel(settings) {
  $('#s-auto-create').checked = settings.auto_create || false;
  $('#s-force-push').checked = settings.force_push || false;
  $('#s-delete-remote').checked = settings.delete_remote || false;
  $('#s-sync-releases').checked = settings.sync_releases || false;
  $('#s-mode').value = settings.mode || 'mirror';
  $('#s-preserve-files').value = (settings.preserve_files || []).join(', ');
  $('#s-release-asset-max-size').value = settings.release_asset_max_size_mb || 50;
  fillReleaseFilter('s-rf', settings.release_filter || { mode: 'all', latest_count: 1, pattern: null, tags: null, include_drafts: false });
}

function fillReleaseFilter(prefix, rf) {
  if (!rf) rf = { mode: 'all', latest_count: 1, pattern: null, tags: null, include_drafts: false };
  $(`#${prefix}-mode`).value = rf.mode || 'all';
  $(`#${prefix}-latest-count`).value = rf.latest_count || 1;
  $(`#${prefix}-pattern`).value = rf.pattern || '';
  $(`#${prefix}-include-drafts`).checked = rf.include_drafts || false;
  const tagContainer = $(`#${prefix}-tags`);
  if (tagContainer) {
    tagContainer.innerHTML = '';
    (rf.tags || []).forEach(t => addTag(tagContainer, t));
  }
}

// ── Save ────────────────────────────────────────────
async function saveConfig() {
  // Sync current form into config
  if (selectedIndex >= 0) {
    config.topology[selectedIndex] = collectFormEntry();
  }
  const payload = {
    settings: {
      auto_create: $('#s-auto-create').checked,
      force_push: $('#s-force-push').checked,
      delete_remote: $('#s-delete-remote').checked,
      mode: $('#s-mode').value,
      preserve_files: parsePreserveFiles($('#s-preserve-files').value),
      sync_releases: $('#s-sync-releases').checked,
      release_asset_max_size_mb: parseInt($('#s-release-asset-max-size').value) || 50,
      release_filter: collectReleaseFilter('s-rf'),
    },
    topology: config.topology,
  };

  try {
    const result = await apiPost('/api/config', payload);
    setStatus('配置已保存', 'success');
    dirty = false;
  } catch (e) {
    setStatus('保存失败: ' + e.message, 'error');
  }
}

// ── Validate ────────────────────────────────────────
async function validateConfig() {
  const payload = collectFullConfig();
  try {
    await apiPost('/api/validate', payload);
    setStatus('配置校验通过', 'success');
  } catch (e) {
    setStatus('校验失败: ' + e.message, 'error');
  }
}

// ── Event wiring ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadConfig();

  // Settings toggle
  $('#btn-settings').addEventListener('click', () => {
    settingsPanel.classList.toggle('hidden');
    if (!settingsPanel.classList.contains('hidden')) {
      fillSettingsPanel(config.settings);
    }
  });

  // Add entry
  $('#btn-add-entry').addEventListener('click', () => {
    const name = prompt('输入新条目名称:');
    if (!name || !name.trim()) return;
    const newEntry = {
      name: name.trim(),
      source: { ...getDefaultEndpoint() },
      targets: [{ ...getDefaultEndpoint() }],
      mode: null,
      preserve_files: null,
      sync_releases: null,
      release_filter: null,
    };
    config.topology.push(newEntry);
    renderEntryList();
    selectEntry(config.topology.length - 1);
    dirty = true;
  });

  // Delete entry
  $('#btn-delete-entry').addEventListener('click', () => {
    if (selectedIndex < 0) return;
    if (!confirm(`确定删除条目「${config.topology[selectedIndex].name}」？`)) return;
    config.topology.splice(selectedIndex, 1);
    selectedIndex = -1;
    renderEntryList();
    showPlaceholder();
    dirty = true;
    setStatus('条目已删除（未保存）', '');
  });

  // Add target
  $('#btn-add-target').addEventListener('click', () => {
    if (selectedIndex < 0) return;
    const entry = config.topology[selectedIndex];
    if (!entry.targets) entry.targets = [];
    entry.targets.push({ ...getDefaultEndpoint() });
    renderTargets(entry.targets);
    dirty = true;
  });

  // Save / Validate / Refresh
  $('#btn-save').addEventListener('click', saveConfig);
  $('#btn-validate').addEventListener('click', validateConfig);
  $('#btn-refresh').addEventListener('click', () => {
    if (dirty && !confirm('有未保存的修改，确定刷新？')) return;
    loadConfig();
  });

  // Branch mode toggle (source endpoint)
  document.addEventListener('change', (e) => {
    if (e.target.matches('#source-endpoint input[type="radio"]')) {
      const single = document.querySelector('#source-endpoint .branch-single');
      const multi = document.querySelector('#source-endpoint .branch-multi');
      single.classList.toggle('hidden', e.target.value === 'multi');
      multi.classList.toggle('hidden', e.target.value === 'single');
    }
  });

  // Add branch tag (source endpoint)
  document.addEventListener('click', (e) => {
    if (e.target.matches('#source-endpoint .btn-add-branch')) {
      const tagList = document.querySelector('#source-endpoint .ep-branches');
      const val = prompt('输入分支名:');
      if (val && val.trim()) addTag(tagList, val.trim());
    }
  });

  // Tag remove (delegated)
  document.addEventListener('click', (e) => {
    if (e.target.matches('.tag-remove')) {
      e.target.parentElement.remove();
    }
  });

  // Global release filter tag add
  $('#s-rf-add-tag')?.addEventListener('click', () => {
    const val = prompt('输入标签:');
    if (val && val.trim()) addTag($('#s-rf-tags'), val.trim());
  });

  // Entry release filter tag add
  $('#e-rf-add-tag')?.addEventListener('click', () => {
    const val = prompt('输入标签:');
    if (val && val.trim()) addTag($('#e-rf-tags'), val.trim());
  });

  // Track dirty state on form changes
  editorForm.addEventListener('change', () => { dirty = true; });
  editorForm.addEventListener('input', () => { dirty = true; });

  // Warn before leaving with unsaved changes
  window.addEventListener('beforeunload', (e) => {
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });
});
```

- [ ] **Step 2: Commit**

```bash
git add src/webui/static/app.js
git commit -m "feat(webui): add JavaScript frontend logic"
```

---

### Task 3: Backend tests — test_webui.py

**Files:**
- Create: `tests/test_webui.py`

**Interfaces:**
- Consumes: `src.webui.main.create_app`, `src.config.dump_config`, `src.config.load_config`

- [ ] **Step 1: Write the failing test file**

```python
"""Tests for WebUI config editor API."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.webui.main import create_app


@pytest.fixture
def app(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            auto_create: false
            force_push: false
            delete_remote: false
            mode: mirror
          topology: []
    """))
    return create_app(config_path=str(cfg_file))


@pytest.fixture
def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_get_config_returns_defaults(client):
    r = await client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "settings" in data
    assert "topology" in data
    assert data["topology"] == []


@pytest.mark.asyncio
async def test_save_and_reload_config(client, tmp_path):
    payload = {
        "settings": {
            "auto_create": True,
            "force_push": True,
            "delete_remote": False,
            "mode": "rebase",
            "preserve_files": [".cnb.yml"],
            "sync_releases": True,
            "release_asset_max_size_mb": 100,
            "release_filter": {
                "mode": "latest",
                "latest_count": 3,
                "pattern": None,
                "tags": None,
                "include_drafts": False,
            },
        },
        "topology": [
            {
                "name": "test-entry",
                "source": {
                    "platform": "github",
                    "owner": "myorg",
                    "repo": "myproject",
                    "branch": "main",
                    "branches": None,
                    "auth": "ssh",
                    "auto_create": False,
                    "visibility": "private",
                },
                "targets": [
                    {
                        "platform": "cnb",
                        "owner": "myorg",
                        "repo": "myproject",
                        "branch": "main",
                        "branches": None,
                        "auth": "pat",
                        "auto_create": True,
                        "visibility": "private",
                    }
                ],
                "mode": None,
                "preserve_files": None,
                "sync_releases": True,
                "release_filter": {
                    "mode": "latest",
                    "latest_count": 3,
                    "pattern": "v*",
                    "tags": None,
                    "include_drafts": False,
                },
            }
        ],
    }

    r = await client.post("/api/config", json=payload)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    r2 = await client.get("/api/config")
    assert r2.status_code == 200
    data = r2.json()
    assert data["settings"]["mode"] == "rebase"
    assert data["settings"]["sync_releases"] is True
    assert data["settings"]["release_asset_max_size_mb"] == 100
    assert data["topology"][0]["name"] == "test-entry"
    assert data["topology"][0]["source"]["platform"] == "github"


@pytest.mark.asyncio
async def test_validate_endpoint(client):
    payload = {
        "settings": {"auto_create": False, "force_push": False, "delete_remote": False, "mode": "mirror"},
        "topology": [],
    }
    r = await client.post("/api/validate", json=payload)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_validate_rejects_invalid(client):
    payload = {
        "settings": {"auto_create": False, "force_push": False, "delete_remote": False, "mode": "mirror"},
        "topology": [
            {
                "name": "bad-entry",
                "source": {"platform": "github", "owner": "myorg", "repo": "myproject", "branch": "main", "branches": ["other"], "auth": "ssh"},
                "targets": [{"platform": "cnb", "owner": "myorg", "repo": "myproject", "branch": "main", "auth": "ssh"}],
            }
        ],
    }
    r = await client.post("/api/validate", json=payload)
    assert r.status_code == 400
    assert "mutually exclusive" in r.json()["error"]


@pytest.mark.asyncio
async def test_save_with_branches(client, tmp_path):
    payload = {
        "settings": {"auto_create": False, "force_push": False, "delete_remote": False, "mode": "mirror"},
        "topology": [
            {
                "name": "multi-branch",
                "source": {
                    "platform": "github", "owner": "myorg", "repo": "myproject",
                    "branch": None, "branches": ["main", "develop", "feature-x"],
                    "auth": "ssh", "auto_create": False, "visibility": "private",
                },
                "targets": [
                    {
                        "platform": "cnb", "owner": "myorg", "repo": "myproject",
                        "branch": None, "branches": ["main", "develop"],
                        "auth": "pat", "auto_create": True, "visibility": "private",
                    }
                ],
            }
        ],
    }
    r = await client.post("/api/config", json=payload)
    assert r.status_code == 200, r.text

    r2 = await client.get("/api/config")
    data = r2.json()
    src = data["topology"][0]["source"]
    assert src["branch"] is None
    assert src["branches"] == ["main", "develop", "feature-x"]


@pytest.mark.asyncio
async def test_save_with_release_filter(client):
    payload = {
        "settings": {"auto_create": False, "force_push": False, "delete_remote": False, "mode": "mirror"},
        "topology": [
            {
                "name": "release-entry",
                "source": {"platform": "github", "owner": "myorg", "repo": "myproject", "branch": "main", "auth": "ssh"},
                "targets": [{"platform": "cnb", "owner": "myorg", "repo": "myproject", "branch": "main", "auth": "pat"}],
                "sync_releases": True,
                "release_filter": {
                    "mode": "tags",
                    "latest_count": 1,
                    "pattern": None,
                    "tags": ["v1.0", "v2.0"],
                    "include_drafts": True,
                },
            }
        ],
    }
    r = await client.post("/api/config", json=payload)
    assert r.status_code == 200, r.text

    r2 = await client.get("/api/config")
    data = r2.json()
    entry = data["topology"][0]
    assert entry["sync_releases"] is True
    assert entry["release_filter"]["mode"] == "tags"
    assert entry["release_filter"]["tags"] == ["v1.0", "v2.0"]
    assert entry["release_filter"]["include_drafts"] is True


@pytest.mark.asyncio
async def test_get_config_when_file_missing(client, tmp_path):
    """Should return default config when file doesn't exist."""
    missing_path = tmp_path / "nonexistent" / "sync.yaml"
    app2 = create_app(config_path=str(missing_path))
    async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as c:
        r = await c.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert data["settings"]["mode"] == "mirror"
    assert data["topology"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_webui.py -v`
Expected: FAIL with import errors (no `dump_config` in config.py, no webui module yet)

- [ ] **Step 3: Create the backend files (Task 1 + Task 2)**

(Already covered by Task 1 and Task 2 — implement those first, then run tests.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_webui.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_webui.py
git commit -m "test(webui): add API tests for config editor"
```

---

### Task 4: Add `fastapi` to requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add fastapi to requirements.txt**

Append to `requirements.txt`:

```
fastapi>=0.115.0
httpx>=0.27.0
```

- [ ] **Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: add fastapi and httpx dependencies"
```

---

### Task 5: Integration test — end-to-end config round-trip

**Files:**
- Modify: `tests/test_webui.py` (append integration test)

- [ ] **Step 1: Add integration test to `tests/test_webui.py`**

Append to the file:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_webui.py::test_full_round_trip -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_webui.py
git commit -m "test(webui): add full round-trip integration test"
```

---

### Task 6: Manual verification

- [ ] **Step 1: Start the WebUI**

Run: `python webui.py`
Expected: Server starts on `http://127.0.0.1:8765`

- [ ] **Step 2: Open browser and verify**

Open `http://127.0.0.1:8765`
Expected: Page renders with header, empty entry list, placeholder text

- [ ] **Step 3: Test add entry**

Click 「+ 新增同步条目」, enter name, verify form appears in right panel

- [ ] **Step 4: Test save**

Fill in source/target fields, click 「保存」
Expected: Status shows "配置已保存"

- [ ] **Step 5: Test refresh**

Click 「刷新」, verify the saved entry reappears

- [ ] **Step 6: Test global settings**

Click ⚙, toggle settings, save, refresh, verify settings persist

- [ ] **Step 7: Test branch mode toggle**

Switch between single/multi branch mode, verify UI updates correctly

- [ ] **Step 8: Test release filter**

Enable sync_releases, configure release filter, save, reload, verify

- [ ] **Step 9: Test delete entry**

Select an entry, click 「删除此条目」, confirm, save, verify it's gone on reload

- [ ] **Step 10: Test validation**

Click 「校验配置」 with valid config — should show success. Introduce an error (e.g. branch + branches both set) — should show error.
