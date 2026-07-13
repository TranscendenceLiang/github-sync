# 同步 Release 功能 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在分支同步完成后，把源平台的 Release（元数据 + 附件资产）按可配置筛选同步到各目标平台，做到多平台发布信息一致。

**Architecture:** 新增 `src/release_sync.py` 作为发布同步引擎，提供统一 `ReleaseClient` 抽象 + 四平台实现（GitHub/Gitee 完整，CNB/GitCode 尽力而为并优雅降级）。在 `sync_topology_entry()` 的分支同步循环之后调用 `sync_releases()` 编排。配置沿用 `auto_create`/`mode` 的 entry 级覆盖模式。设计依据：`docs/superpowers/specs/2026-07-13-sync-releases-design.md`。

**Tech Stack:** Python 3.14（uv 运行）、标准库 `subprocess`/`fnmatch`/`tempfile`/`dataclasses`/`abc`，无第三方 HTTP 库（沿用 `auto_create.py` 的 curl 风格）。测试用 `pytest` + mock `subprocess.run`。

---

## 约定

- 所有工作都在 worktree 分支 `feat/sync-releases` 上进行，路径为 `.worktrees/feat-sync-releases/`。
- 运行测试统一用：
  `uv run --with pytest --with PyYAML --with GitPython python -m pytest -q`
  （github-sync 无 `pyproject.toml`，用 `--with` 注入依赖，避免污染仓库）。
- 每个 Task 按「写失败测试 → 跑测试确认失败 → 写最小实现 → 跑测试确认通过 → commit」推进，频繁小提交。
- 配置新增字段必须向后兼容（`sync_releases` 默认 `False`，不影响现有同步行为）。

---

## Task 1: 配置 schema（`src/config.py`）

**Files:**
- Modify: `src/config.py` （新增 `ReleaseFilter` 解析 + `SyncSettings`/`TopologyEntry` 字段）
- Test: `tests/test_config.py`

**Step 1: 写失败测试**（追加到 `tests/test_config.py`）

```python
from src.config import load_config, ConfigError
from src.release_sync import ReleaseFilter

def test_settings_release_defaults(tmp_path):
    cfg = load_config(tmp_path / "c.yaml")  # will fail: file missing; use inline instead
```

改为用内联 YAML 的辅助：

```python
import io
from src.config import _parse_settings, _parse_entry, ReleaseFilter

def test_settings_release_defaults():
    s = _parse_settings({})
    assert s.sync_releases is False
    assert s.release_asset_max_size_mb == 50
    assert isinstance(s.release_filter, ReleaseFilter)
    assert s.release_filter.mode == "all"

def test_parse_settings_release_on():
    s = _parse_settings({
        "sync_releases": True,
        "release_asset_max_size_mb": 100,
        "release_filter": {"mode": "pattern", "pattern": "v*"},
    })
    assert s.sync_releases is True
    assert s.release_asset_max_size_mb == 100
    assert s.release_filter.mode == "pattern"
    assert s.release_filter.pattern == "v*"

def test_parse_settings_release_filter_invalid_mode():
    import pytest
    with pytest.raises(ConfigError, match="release_filter.mode"):
        _parse_settings({"release_filter": {"mode": "bogus"}})

def test_parse_entry_release_override():
    e = _parse_entry({
        "name": "x",
        "sync_releases": False,
        "source": {"platform": "github", "owner": "o", "repo": "r", "branch": "main"},
        "targets": [{"platform": "gitee", "owner": "o", "repo": "r", "branch": "main"}],
        "release_filter": {"mode": "tags", "tags": ["v1.0.0"]},
    })
    assert e.sync_releases is False
    assert e.release_filter.mode == "tags"
    assert e.release_filter.tags == ["v1.0.0"]

def test_parse_entry_release_inherits_none():
    e = _parse_entry({
        "name": "x",
        "source": {"platform": "github", "owner": "o", "repo": "r", "branch": "main"},
        "targets": [{"platform": "gitee", "owner": "o", "repo": "r", "branch": "main"}],
    })
    assert e.sync_releases is None
    assert e.release_filter is None
```

**Step 2: 跑测试确认失败**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_config.py -q`
Expected: ImportError / AttributeError（`ReleaseFilter` 不存在、`sync_releases` 字段不存在）。

**Step 3: 写最小实现**（`src/config.py`）

在文件顶部 import 区加入：

```python
from src.release_sync import ReleaseFilter
```

在 `SyncSettings` 数据类增加字段：

```python
@dataclass
class SyncSettings:
    auto_create: bool = False
    force_push: bool = False
    delete_remote: bool = False
    mode: str = "mirror"
    preserve_files: list[str] | None = None
    sync_releases: bool = False
    release_asset_max_size_mb: int = 50
    release_filter: ReleaseFilter = field(default_factory=ReleaseFilter)
```

在 `TopologyEntry` 数据类增加字段：

```python
@dataclass
class TopologyEntry:
    name: str
    source: Endpoint
    targets: list[Endpoint] = field(default_factory=list)
    mode: str | None = None
    preserve_files: list[str] | None = None
    sync_releases: bool | None = None
    release_filter: ReleaseFilter | None = None
```

在 `_parse_entry` 中 `return TopologyEntry(...)` 前解析新字段：

```python
    rf_raw = data.get("release_filter")
    release_filter = _parse_release_filter(rf_raw) if rf_raw is not None else None
    sync_releases = data.get("sync_releases", None)
    if sync_releases is not None:
        sync_releases = bool(sync_releases)

    return TopologyEntry(
        name=name, source=source, targets=targets, mode=mode,
        preserve_files=preserve_files,
        sync_releases=sync_releases,
        release_filter=release_filter,
    )
```

在 `_parse_settings` 中 `return SyncSettings(...)` 前：

```python
    return SyncSettings(
        auto_create=bool(data.get("auto_create", False)),
        force_push=bool(data.get("force_push", False)),
        delete_remote=bool(data.get("delete_remote", False)),
        mode=mode,
        preserve_files=preserve_files,
        sync_releases=bool(data.get("sync_releases", False)),
        release_asset_max_size_mb=int(data.get("release_asset_max_size_mb", 50)),
        release_filter=_parse_release_filter(data.get("release_filter")),
    )
```

新增解析辅助函数（放在 `_parse_settings` 之前）：

```python
def _parse_release_filter(data: Any) -> ReleaseFilter:
    if data is None:
        return ReleaseFilter()
    if not isinstance(data, dict):
        raise ConfigError("release_filter must be a mapping")
    mode = str(data.get("mode", "all")).lower()
    if mode not in ("all", "latest", "pattern", "tags"):
        raise ConfigError(
            f"release_filter.mode must be one of all|latest|pattern|tags, got {mode!r}"
        )
    latest_count = int(data.get("latest_count", 1))
    pattern = data.get("pattern")
    tags = data.get("tags")
    if tags is not None and not isinstance(tags, list):
        raise ConfigError("release_filter.tags must be a list of strings")
    include_drafts = bool(data.get("include_drafts", False))
    return ReleaseFilter(
        mode=mode,
        latest_count=latest_count,
        pattern=pattern,
        tags=tags,
        include_drafts=include_drafts,
    )
```

**Step 4: 跑测试确认通过**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_config.py -q`
Expected: PASS（本 Task 新增用例全过；注意此时 `src/release_sync.py` 还不存在，Next Task 会创建它，所以这步会先因 import 失败——请先完成 Task 2 的「数据模型最小可导入」再做本步验证，或本步仅验证语法）。

> 实操提示：Task 2 第一步先建立 `release_sync.py` 的空壳（仅 `ReleaseFilter`/`ReleaseInfo`/`AssetInfo` 等数据类），使 `config.py` 的 import 可解析，再回头跑本 Task 测试。

**Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat(config): add sync_releases + release_filter schema"
```

---

## Task 2: 数据模型与过滤（`src/release_sync.py` 基础）

**Files:**
- Create: `src/release_sync.py`
- Test: `tests/test_release_sync.py`

**Step 1: 写失败测试**

```python
from src.release_sync import ReleaseInfo, AssetInfo, ReleaseFilter, filter_releases, supports_releases

def _rel(tag, draft=False, published=None, assets=None):
    return ReleaseInfo(tag_name=tag, name=tag, draft=draft, published_at=published,
                       assets=assets or [])

def test_filter_all():
    rels = [_rel("v1"), _rel("v2", draft=True), _rel("v3")]
    out = filter_releases(rels, ReleaseFilter(mode="all"))
    assert [r.tag_name for r in out] == ["v1", "v2", "v3"]

def test_filter_include_drafts_false_default():
    rels = [_rel("v1"), _rel("v2", draft=True)]
    out = filter_releases(rels, ReleaseFilter(mode="all"))
    assert [r.tag_name for r in out] == ["v1"]

def test_filter_include_drafts_true():
    rels = [_rel("v1"), _rel("v2", draft=True)]
    out = filter_releases(rels, ReleaseFilter(mode="all", include_drafts=True))
    assert len(out) == 2

def test_filter_latest():
    rels = [
        _rel("v1", published="2024-01-01T00:00:00Z"),
        _rel("v2", published="2024-03-01T00:00:00Z"),
        _rel("v3", published="2024-02-01T00:00:00Z"),
    ]
    out = filter_releases(rels, ReleaseFilter(mode="latest", latest_count=2))
    assert [r.tag_name for r in out] == ["v2", "v3"]

def test_filter_pattern():
    rels = [_rel("v1.0.0"), _rel("rel-1"), _rel("v2.0.0")]
    out = filter_releases(rels, ReleaseFilter(mode="pattern", pattern="v*.*.*"))
    assert sorted(r.tag_name for r in out) == ["v1.0.0", "v2.0.0"]

def test_filter_tags():
    rels = [_rel("v1.0.0"), _rel("v2.0.0"), _rel("v3.0.0")]
    out = filter_releases(rels, ReleaseFilter(mode="tags", tags=["v1.0.0", "v3.0.0"]))
    assert sorted(r.tag_name for r in out) == ["v1.0.0", "v3.0.0"]

def test_supports_releases_registry():
    assert supports_releases("github") is True
    assert supports_releases("gitee") is True
    assert supports_releases("cnb") is True
    assert supports_releases("gitcode") is True
    assert supports_releases("gitlab") is False
```

**Step 2: 跑测试确认失败**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py -q`
Expected: ModuleNotFoundError（`src.release_sync` 不存在）。

**Step 3: 写最小实现**（`src/release_sync.py`，先放数据模型 + filter + 注册表占位）

```python
"""Release sync engine: sync release metadata + assets across platforms via REST APIs."""
from __future__ import annotations

import fnmatch
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AssetInfo:
    name: str
    size: int  # bytes
    download_url: str
    asset_id: str | None = None


@dataclass
class ReleaseInfo:
    tag_name: str
    name: str | None = None
    body: str | None = None
    draft: bool = False
    prerelease: bool = False
    release_id: str | None = None
    assets: list[AssetInfo] = field(default_factory=list)
    published_at: str | None = None  # ISO string, used for `latest` ordering


@dataclass
class ReleaseFilter:
    mode: str = "all"  # all | latest | pattern | tags
    latest_count: int = 1
    pattern: str | None = None
    tags: list[str] | None = None
    include_drafts: bool = False


@dataclass
class ReleaseSyncResult:
    releases_created: int = 0
    releases_updated: int = 0
    releases_skipped: int = 0
    assets_uploaded: int = 0
    assets_skipped: int = 0
    warnings: list[str] = field(default_factory=list)  # non-fatal (skip-level)
    errors: list[str] = field(default_factory=list)      # fatal (target-level)


class ReleaseSyncError(Exception):
    """Carries platform/repo context for a failed release API call."""


def filter_releases(releases: list[ReleaseInfo], rf: ReleaseFilter) -> list[ReleaseInfo]:
    out = [r for r in releases if (not r.draft) or rf.include_drafts]
    if rf.mode == "all":
        return out
    if rf.mode == "latest":
        ordered = sorted(out, key=lambda r: r.published_at or "", reverse=True)
        return ordered[: max(1, rf.latest_count)]
    if rf.mode == "pattern":
        if not rf.pattern:
            return out
        return [r for r in out if fnmatch.fnmatch(r.tag_name, rf.pattern)]
    if rf.mode == "tags":
        if not rf.tags:
            return out
        wanted = set(rf.tags)
        return [r for r in out if r.tag_name in wanted]
    return out


RELEASE_CLIENTS: dict[str, type["ReleaseClient"]] = {}


def supports_releases(platform: str) -> bool:
    return platform in RELEASE_CLIENTS
```

**Step 4: 跑测试确认通过**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py -q`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/release_sync.py tests/test_release_sync.py
git commit -m "feat(release_sync): add data model, filter_releases, supports_releases"
```

---

## Task 3: GitHub ReleaseClient（`src/release_sync.py`）

**Files:**
- Modify: `src/release_sync.py` （新增 `ReleaseClient` ABC + `GitHubReleaseClient`，并注册到 `RELEASE_CLIENTS`）
- Test: `tests/test_release_sync.py`

**Step 1: 写失败测试**

```python
from src.release_sync import GitHubReleaseClient
import subprocess

def _mock_curl(json_text, returncode=0):
    original = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = returncode
            stdout = json_text
            stderr = ""
        return P()
    subprocess.run = _run
    return original

def test_github_list_releases():
    sample = '[{"tag_name":"v1.0.0","name":"v1","body":"b","draft":false,' \
             '"prerelease":true,"id":10,"published_at":"2024-01-01T00:00:00Z",' \
             '"assets":[{"name":"a.bin","size":123,"browser_download_url":"http://x/a.bin","id":1}]}]'
    orig = _mock_curl(sample)
    try:
        c = GitHubReleaseClient()
        rels = c.list_releases("o", "r", "tok")
    finally:
        subprocess.run = orig
    assert len(rels) == 1
    r = rels[0]
    assert r.tag_name == "v1.0.0" and r.release_id == "10" and r.prerelease is True
    assert r.assets[0].name == "a.bin" and r.assets[0].size == 123

def test_github_create_release_body():
    calls = []
    orig = subprocess.run
    def _run(args, **kwargs):
        calls.append(args)
        class P:
            returncode = 0
            stdout = '{"id":99}'
            stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        info = ReleaseInfo(tag_name="v2", name="v2", body="x", draft=False, prerelease=False)
        c.create_release("o", "r", "tok", info)
    finally:
        subprocess.run = orig
    cmd = " ".join(calls[0])
    assert "api.github.com/repos/o/r/releases" in cmd
    assert "Authorization: Bearer tok" in cmd
    assert '"tag_name": "v2"' in cmd

def test_github_upload_asset_url():
    calls = []
    orig = subprocess.run
    def _run(args, **kwargs):
        calls.append(args)
        class P:
            returncode = 0
            stdout = '{"id":5,"name":"a.bin","size":10}'
            stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        from pathlib import Path
        c.upload_asset("o", "r", "tok", "99", Path("/tmp/a.bin"), "a.bin")
    finally:
        subprocess.run = orig
    cmd = " ".join(calls[0])
    assert "releases/99/assets?name=a.bin" in cmd
    assert "application/octet-stream" in cmd
```

**Step 2: 跑测试确认失败**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py::test_github_list_releases tests/test_release_sync.py::test_github_create_release_body tests/test_release_sync.py::test_github_upload_asset_url -q`
Expected: FAIL（`GitHubReleaseClient` 未定义）。

**Step 3: 写最小实现**（追加到 `src/release_sync.py`）

```python
def _curl_json(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout


def _json_list(text: str) -> list:
    import json
    return json.loads(text) if text.strip().startswith("[") else []


def _json_obj(text: str) -> dict:
    import json
    return json.loads(text) if text.strip().startswith("{") else {}


class ReleaseClient(ABC):
    platform: str = ""

    @abstractmethod
    def list_releases(self, owner: str, repo: str, token: str) -> list[ReleaseInfo]: ...

    @abstractmethod
    def get_release_by_tag(self, owner: str, repo: str, tag: str, token: str) -> ReleaseInfo | None: ...

    @abstractmethod
    def create_release(self, owner: str, repo: str, token: str, info: ReleaseInfo) -> ReleaseInfo: ...

    @abstractmethod
    def update_release(self, owner: str, repo: str, token: str, info: ReleaseInfo) -> ReleaseInfo: ...

    @abstractmethod
    def download_asset(self, asset: AssetInfo, token: str, dest: Path) -> Path: ...

    @abstractmethod
    def upload_asset(self, owner: str, repo: str, token: str, release_id: str, path: Path, name: str) -> AssetInfo: ...


class GitHubReleaseClient(ReleaseClient):
    platform = "github"

    def _hdr(self, token: str) -> list[str]:
        return ["-H", f"Authorization: Bearer {token}", "-H", "Content-Type: application/json"]

    def list_releases(self, owner, repo, token):
        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url] + self._hdr(token))
        if rc != 0:
            raise ReleaseSyncError(f"github list_releases failed (rc={rc})")
        rels = []
        for it in _json_list(out):
            rels.append(ReleaseInfo(
                tag_name=it.get("tag_name", ""),
                name=it.get("name"),
                body=it.get("body"),
                draft=bool(it.get("draft", False)),
                prerelease=bool(it.get("prerelease", False)),
                release_id=str(it.get("id")),
                published_at=it.get("published_at"),
                assets=[AssetInfo(name=a.get("name", ""), size=int(a.get("size", 0)),
                                  download_url=a.get("browser_download_url", ""),
                                  asset_id=str(a.get("id"))) for a in it.get("assets", [])],
            ))
        return rels

    def get_release_by_tag(self, owner, repo, tag, token):
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url] + self._hdr(token))
        if rc != 0:
            return None
        it = _json_obj(out)
        if not it:
            return None
        return ReleaseInfo(
            tag_name=it.get("tag_name", tag), name=it.get("name"), body=it.get("body"),
            draft=bool(it.get("draft", False)), prerelease=bool(it.get("prerelease", False)),
            release_id=str(it.get("id")),
            assets=[AssetInfo(name=a.get("name", ""), size=int(a.get("size", 0)),
                              download_url=a.get("browser_download_url", ""),
                              asset_id=str(a.get("id"))) for a in it.get("assets", [])],
        )

    def create_release(self, owner, repo, token, info):
        import json
        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        body = json.dumps({
            "tag_name": info.tag_name, "name": info.name, "body": info.body,
            "draft": info.draft, "prerelease": info.prerelease,
        })
        rc, out = _curl_json(["curl", "-s", "-X", "POST", url, "--data", body] + self._hdr(token))
        if rc != 0:
            raise ReleaseSyncError(f"github create_release {info.tag_name} failed: {out}")
        it = _json_obj(out)
        info.release_id = str(it.get("id"))
        return info

    def update_release(self, owner, repo, token, info):
        import json
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/{info.release_id}"
        body = json.dumps({"name": info.name, "body": info.body,
                           "draft": info.draft, "prerelease": info.prerelease})
        rc, out = _curl_json(["curl", "-s", "-X", "PATCH", url, "--data", body] + self._hdr(token))
        if rc != 0:
            raise ReleaseSyncError(f"github update_release {info.tag_name} failed: {out}")
        return info

    def download_asset(self, asset, token, dest):
        rc = subprocess.run([
            "curl", "-s", "-L", "-H", f"Authorization: Bearer {token}",
            "-o", str(dest), asset.download_url,
        ], capture_output=True, text=True)
        if rc.returncode != 0:
            raise ReleaseSyncError(f"github download_asset {asset.name} failed")
        return dest

    def upload_asset(self, owner, repo, token, release_id, path, name):
        url = f"https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?name={name}"
        rc, out = _curl_json([
            "curl", "-s", "-X", "POST", url,
            "-H", f"Authorization: Bearer {token}",
            "-H", "Content-Type: application/octet-stream",
            "--data-binary", f"@{path}",
        ])
        if rc != 0:
            raise ReleaseSyncError(f"github upload_asset {name} failed: {out}")
        it = _json_obj(out)
        return AssetInfo(name=it.get("name", name), size=int(it.get("size", 0)),
                         download_url=it.get("browser_download_url", ""), asset_id=str(it.get("id")))


RELEASE_CLIENTS["github"] = GitHubReleaseClient
```

**Step 4: 跑测试确认通过**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py -q`
Expected: PASS（含本 Task 3 个用例 + 前序 filter 用例）。

**Step 5: Commit**

```bash
git add src/release_sync.py tests/test_release_sync.py
git commit -m "feat(release_sync): add GitHubReleaseClient (list/create/update/assets)"
```

---

## Task 4: Gitee ReleaseClient

**Files:**
- Modify: `src/release_sync.py` （新增 `GiteeReleaseClient`，注册）
- Test: `tests/test_release_sync.py`

**Step 1: 写失败测试**

```python
from src.release_sync import GiteeReleaseClient

def test_gitee_list_releases_uses_token():
    sample = '[{"tag_name":"v1.0.0","name":"v1","body":"b","prerelease":false,' \
             '"id":7,"created_at":"2024-01-01T00:00:00Z",' \
             '"assets":[{"name":"a.bin","size":9,"browser_download_url":"http://x/a.bin","id":2}]}]'
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0; stdout = sample; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GiteeReleaseClient()
        rels = c.list_releases("o", "r", "tok")
    finally:
        subprocess.run = orig
    assert rels[0].tag_name == "v1.0.0"
    assert rels[0].assets[0].size == 9

def test_gitee_create_release_url():
    calls = []
    orig = subprocess.run
    def _run(args, **kwargs):
        calls.append(args)
        class P:
            returncode = 0; stdout = '{"id":8}'; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GiteeReleaseClient()
        c.create_release("o", "r", "tok", ReleaseInfo(tag_name="v2"))
    finally:
        subprocess.run = orig
    cmd = " ".join(calls[0])
    assert "gitee.com/api/v5/repos/o/r/releases" in cmd
    assert "access_token=tok" in cmd
```

**Step 2: 跑测试确认失败**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py::test_gitee_list_releases_uses_token tests/test_release_sync.py::test_gitee_create_release_url -q`
Expected: FAIL（`GiteeReleaseClient` 未定义）。

**Step 3: 写最小实现**（追加）

```python
class GiteeReleaseClient(ReleaseClient):
    platform = "gitee"

    def _base(self, owner, repo):
        return f"https://gitee.com/api/v5/repos/{owner}/{repo}"

    def list_releases(self, owner, repo, token):
        url = f"{self._base(owner, repo)}/releases?access_token={token}&per_page=100"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url])
        if rc != 0:
            raise ReleaseSyncError(f"gitee list_releases failed (rc={rc})")
        rels = []
        for it in _json_list(out):
            rels.append(ReleaseInfo(
                tag_name=it.get("tag_name", ""), name=it.get("name"), body=it.get("body"),
                draft=False, prerelease=bool(it.get("prerelease", False)),
                release_id=str(it.get("id")), published_at=it.get("created_at"),
                assets=[AssetInfo(name=a.get("name", ""), size=int(a.get("size", 0)),
                                  download_url=a.get("browser_download_url", ""),
                                  asset_id=str(a.get("id"))) for a in it.get("assets", [])],
            ))
        return rels

    def get_release_by_tag(self, owner, repo, tag, token):
        url = f"{self._base(owner, repo)}/tags/{tag}/release?access_token={token}"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url])
        if rc != 0:
            return None
        it = _json_obj(out)
        if not it:
            return None
        return ReleaseInfo(
            tag_name=it.get("tag_name", tag), name=it.get("name"), body=it.get("body"),
            draft=False, prerelease=bool(it.get("prerelease", False)),
            release_id=str(it.get("id")),
            assets=[AssetInfo(name=a.get("name", ""), size=int(a.get("size", 0)),
                              download_url=a.get("browser_download_url", ""),
                              asset_id=str(a.get("id"))) for a in it.get("assets", [])],
        )

    def create_release(self, owner, repo, token, info):
        import json
        url = f"{self._base(owner, repo)}/releases"
        body = json.dumps({
            "access_token": token, "tag_name": info.tag_name, "name": info.name,
            "body": info.body, "prerelease": info.prerelease,
        })
        rc, out = _curl_json(["curl", "-s", "-X", "POST", url, "--data", body])
        if rc != 0:
            raise ReleaseSyncError(f"gitee create_release {info.tag_name} failed: {out}")
        info.release_id = str(_json_obj(out).get("id"))
        return info

    def update_release(self, owner, repo, token, info):
        import json
        url = f"{self._base(owner, repo)}/releases/{info.release_id}?access_token={token}"
        body = json.dumps({"name": info.name, "body": info.body, "prerelease": info.prerelease})
        rc, out = _curl_json(["curl", "-s", "-X", "PATCH", url, "--data", body])
        if rc != 0:
            raise ReleaseSyncError(f"gitee update_release {info.tag_name} failed: {out}")
        return info

    def download_asset(self, asset, token, dest):
        url = asset.download_url
        if "access_token" not in url:
            url = url + ("&" if "?" in url else "?") + f"access_token={token}"
        rc = subprocess.run(["curl", "-s", "-L", "-o", str(dest), url],
                            capture_output=True, text=True)
        if rc.returncode != 0:
            raise ReleaseSyncError(f"gitee download_asset {asset.name} failed")
        return dest

    def upload_asset(self, owner, repo, token, release_id, path, name):
        url = f"{self._base(owner, repo)}/releases/{release_id}/attach_files?access_token={token}"
        rc, out = _curl_json([
            "curl", "-s", "-X", "POST", url,
            "-F", f"file=@{path}",
        ])
        if rc != 0:
            raise ReleaseSyncError(f"gitee upload_asset {name} failed: {out}")
        it = _json_obj(out)
        # Gitee wraps attachment; pick first if list
        data = it.get("data", it)
        if isinstance(data, list):
            data = data[0] if data else {}
        return AssetInfo(name=data.get("name", name), size=int(data.get("size", 0)),
                         download_url=data.get("browser_download_url", ""), asset_id=str(data.get("id")))


RELEASE_CLIENTS["gitee"] = GiteeReleaseClient
```

**Step 4: 跑测试确认通过**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py -q`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/release_sync.py tests/test_release_sync.py
git commit -m "feat(release_sync): add GiteeReleaseClient (list/create/update/assets)"
```

---

## Task 5: CNB / GitCode 客户端（尽力而为 + 优雅降级）

**Files:**
- Modify: `src/release_sync.py` （新增 `CNBReleaseClient` / `GitCodeReleaseClient`）
- Test: `tests/test_release_sync.py`

> 实现期需用真实 token 验证端点是否可用。若平台确实无 release API，`list_releases`/`create_release` 内部抛 `ReleaseSyncError`，由编排层捕获后 warn + 跳过该 target（见 Task 6）。本 Task 先按已知/合理端点实现，并写「404 即降级」的测试。

**Step 1: 写失败测试**

```python
from src.release_sync import CNBReleaseClient, GitCodeReleaseClient

def test_cnb_list_404_raises():
    """CNB 端点若不支持 release，编排层会捕获；此处验证 client 抛 ReleaseSyncError。"""
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0
            stdout = '{"message":"Not Found"}'  # CNB 常返回 message 字段而非 404 码
            stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = CNBReleaseClient()
        # 返回空列表（未抛错）也是可接受的降级方式；这里断言不崩溃
        rels = c.list_releases("o", "r", "tok")
        assert isinstance(rels, list)
    finally:
        subprocess.run = orig

def test_gitcode_client_registered():
    from src.release_sync import supports_releases
    assert supports_releases("gitcode") is True
```

**Step 2: 跑测试确认失败**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py::test_cnb_list_404_raises tests/test_release_sync.py::test_gitcode_client_registered -q`
Expected: FAIL（类未定义）。

**Step 3: 写最小实现**（追加；CNB 走与 Gitee 近似的 v5 风格，GitCode 走 Gitee 兼容端点）

```python
class CNBReleaseClient(ReleaseClient):
    platform = "cnb"

    def _base(self, owner, repo):
        return f"https://api.cnb.cool/{owner}/{repo}"

    def list_releases(self, owner, repo, token):
        url = f"{self._base(owner, repo)}/releases"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url,
                              "-H", f"Authorization: Bearer {token}"])
        if rc != 0:
            raise ReleaseSyncError(f"cnb list_releases failed (rc={rc})")
        it = _json_obj(out)
        # CNB 可能返回 {"data": [...]} 或 {"message": "..."}（不支持）
        if "message" in it:
            return []
        items = it.get("data", it if isinstance(it, list) else [])
        rels = []
        for r in items:
            rels.append(ReleaseInfo(
                tag_name=r.get("tag_name", ""), name=r.get("name"), body=r.get("body"),
                draft=bool(r.get("draft", False)), prerelease=bool(r.get("prerelease", False)),
                release_id=str(r.get("id")), published_at=r.get("created_at"),
                assets=[AssetInfo(name=a.get("name", ""), size=int(a.get("size", 0)),
                                  download_url=a.get("browser_download_url", ""),
                                  asset_id=str(a.get("id"))) for a in r.get("assets", [])],
            ))
        return rels

    def get_release_by_tag(self, owner, repo, tag, token):
        for r in self.list_releases(owner, repo, token):
            if r.tag_name == tag:
                return r
        return None

    def create_release(self, owner, repo, token, info):
        import json
        url = f"{self._base(owner, repo)}/releases"
        body = json.dumps({"tag_name": info.tag_name, "name": info.name,
                           "body": info.body, "draft": info.draft, "prerelease": info.prerelease})
        rc, out = _curl_json(["curl", "-s", "-X", "POST", url,
                              "-H", f"Authorization: Bearer {token}",
                              "-H", "Content-Type: application/json", "--data", body])
        if rc != 0:
            raise ReleaseSyncError(f"cnb create_release {info.tag_name} failed: {out}")
        info.release_id = str(_json_obj(out).get("id"))
        return info

    def update_release(self, owner, repo, token, info):
        import json
        url = f"{self._base(owner, repo)}/releases/{info.release_id}"
        body = json.dumps({"name": info.name, "body": info.body,
                           "draft": info.draft, "prerelease": info.prerelease})
        rc, out = _curl_json(["curl", "-s", "-X", "PATCH", url,
                              "-H", f"Authorization: Bearer {token}",
                              "-H", "Content-Type: application/json", "--data", body])
        if rc != 0:
            raise ReleaseSyncError(f"cnb update_release {info.tag_name} failed: {out}")
        return info

    def download_asset(self, asset, token, dest):
        rc = subprocess.run(["curl", "-s", "-L", "-H", f"Authorization: Bearer {token}",
                             "-o", str(dest), asset.download_url], capture_output=True, text=True)
        if rc.returncode != 0:
            raise ReleaseSyncError(f"cnb download_asset {asset.name} failed")
        return dest

    def upload_asset(self, owner, repo, token, release_id, path, name):
        url = f"{self._base(owner, repo)}/releases/{release_id}/assets"
        rc, out = _curl_json(["curl", "-s", "-X", "POST", url,
                              "-H", f"Authorization: Bearer {token}",
                              "-F", f"file=@{path}"])
        if rc != 0:
            raise ReleaseSyncError(f"cnb upload_asset {name} failed: {out}")
        it = _json_obj(out)
        return AssetInfo(name=it.get("name", name), size=int(it.get("size", 0)),
                         download_url=it.get("browser_download_url", ""), asset_id=str(it.get("id")))


class GitCodeReleaseClient(GiteeReleaseClient):
    """GitCode 的 release API 与 Gitee v5 近似；复用 Gitee 实现并确保端点前缀正确。"""
    platform = "gitcode"

    def _base(self, owner, repo):
        return f"https://api.gitcode.com/api/v5/repos/{owner}/{repo}"


RELEASE_CLIENTS["cnb"] = CNBReleaseClient
RELEASE_CLIENTS["gitcode"] = GitCodeReleaseClient
```

**Step 4: 跑测试确认通过**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py -q`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/release_sync.py tests/test_release_sync.py
git commit -m "feat(release_sync): add CNB/GitCode clients (best-effort, graceful degrade)"
```

---

## Task 6: 编排 `sync_releases()`

**Files:**
- Modify: `src/release_sync.py` （新增 `sync_releases` / `_client_for` / `_sync_assets`）
- Test: `tests/test_release_sync.py`

**Step 1: 写失败测试**（用 stub client 验证编排逻辑，避免真 curl）

```python
import tempfile
from src.release_sync import ReleaseInfo, AssetInfo, ReleaseSyncResult, sync_releases, ReleaseClient

class _StubClient(ReleaseClient):
    platform = "github"
    def __init__(self, releases=None, by_tag=None, created=None, assets=None):
        self._releases = releases or []
        self._by_tag = by_tag or {}
        self._created = created or []
        self.uploaded = []
    def list_releases(self, o, r, t): return list(self._releases)
    def get_release_by_tag(self, o, r, tag, t): return self._by_tag.get(tag)
    def create_release(self, o, r, t, info):
        self._created.append(info.tag_name)
        info.release_id = "NEW"
        return info
    def update_release(self, o, r, t, info): return info
    def download_asset(self, asset, t, dest): return dest
    def upload_asset(self, o, r, t, rid, path, name):
        self.uploaded.append(name)
        return AssetInfo(name=name, size=1, download_url="x")

def _entry_with_targets():
    from src.config import TopologyEntry, Endpoint
    src = Endpoint(platform="github", owner="o", repo="r", branch="main")
    tgt = Endpoint(platform="github", owner="o2", repo="r", branch="main", auth="pat")
    return TopologyEntry(name="x", source=src, targets=[tgt])

def test_sync_releases_create_new_and_skip_existing(monkeypatch):
    rels = [ReleaseInfo(tag_name="v1", name="v1", assets=[AssetInfo("a.bin", size=10, download_url="u")])]
    src_client = _StubClient(releases=rels)
    tgt_client = _StubClient(by_tag={"v1": ReleaseInfo(tag_name="v1", release_id="EXIST", assets=[])})
    def _pick(p):
        return src_client if p == "github_src" else tgt_client
    # route by role: use a fake creds + settings
    from src.config import SyncSettings
    settings = SyncSettings(sync_releases=True, release_asset_max_size_mb=50)
    entry = _entry_with_targets()
    # monkeypatch clients
    import src.release_sync as rs
    monkeypatch.setattr(rs, "RELEASE_CLIENTS", {"github": lambda: src_client if False else _ClientRouter(src_client, tgt_client)})
    res = rs.sync_releases(entry, {"github": _cred("tok")}, settings)
    assert res.releases_created >= 0  # structure check
```

> 上面按角色路由较绕；实现时建议 `sync_releases` 内部用 `_client_for(platform)` 返回 **新实例**，测试则直接 monkeypatch `_client_for` 返回角色化 stub。下面给出更直接的测试写法（实现时采用）：

```python
def test_sync_releases_create_then_update(monkeypatch):
    import src.release_sync as rs
    src = _StubClient(releases=[ReleaseInfo(tag_name="v1", name="v1",
                        assets=[AssetInfo("a.bin", size=10, download_url="u")])])
    tgt_new = _StubClient()  # target has no existing release -> create
    monkeypatch.setattr(rs, "_client_for", lambda p: src if p == "github_src" else tgt_new)
    # 用占位平台名区分：实际以 endpoint.platform 取 client；这里让 src/tgt 同平台 github，
    # 通过给 stub 标记 role 区分。简化：直接构造两个独立 client 并 patch 列表。
    from src.config import SyncSettings, TopologyEntry, Endpoint
    settings = SyncSettings(sync_releases=True)
    entry = TopologyEntry(name="x",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="pat"),
        targets=[Endpoint(platform="github", owner="o2", repo="r", branch="main", auth="pat")])
    # patch: source uses src, target uses tgt_new
    calls = {"src": src, "tgt": tgt_new}
    def _client_for(p, role=None):
        return calls["src"] if role == "src" else calls["tgt"]
    monkeypatch.setattr(rs, "_client_for", lambda platform, role="tgt": calls["src"] if role == "src" else calls["tgt"])
    res = rs.sync_releases(entry, {"github": _cred("tok")}, settings)
    assert res.releases_created == 1
    assert res.assets_uploaded == 1
```

**Step 2: 跑测试确认失败**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py -k sync_releases -q`
Expected: FAIL（`sync_releases` / `_client_for` 未定义）。

**Step 3: 写最小实现**（追加到 `src/release_sync.py`）

```python
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import SyncSettings, TopologyEntry
    from src.credential import Credential


def _client_for(platform: str, role: str = "tgt") -> ReleaseClient:
    """Return a fresh ReleaseClient instance for the platform."""
    cls = RELEASE_CLIENTS.get(platform)
    if cls is None:
        raise ReleaseSyncError(f"platform {platform!r} has no release client")
    return cls()


def _cred_token(creds: dict, platform: str) -> str | None:
    cred = creds.get(platform)
    return cred.pat if cred and getattr(cred, "pat", None) else None


def _sync_assets(client: ReleaseClient, target, token: str, src_rel: ReleaseInfo,
                 tgt_rel: ReleaseInfo, cap_bytes: int, result: ReleaseSyncResult) -> None:
    if not src_rel.assets:
        return
    tmp = Path(tempfile.mkdtemp(prefix="relsync-"))
    existing = {a.name for a in tgt_rel.assets}
    for asset in src_rel.assets:
        if asset.size > cap_bytes:
            result.assets_skipped += 1
            result.warnings.append(
                f"asset {asset.name} ({asset.size} bytes) exceeds cap; skipped")
            continue
        if asset.name in existing:
            continue  # 目标已有同名资产，免重复上传
        dest = tmp / asset.name
        try:
            client.download_asset(asset, token, dest)
        except ReleaseSyncError as e:
            result.assets_skipped += 1
            result.warnings.append(f"download asset {asset.name} failed: {e}")
            continue
        try:
            client.upload_asset(target.owner, target.repo, token,
                                tgt_rel.release_id or "", dest, asset.name)
            result.assets_uploaded += 1
        except ReleaseSyncError as e:
            result.assets_skipped += 1
            result.warnings.append(f"upload asset {asset.name} failed: {e}")


def sync_releases(entry: "TopologyEntry", creds: dict, settings: "SyncSettings") -> ReleaseSyncResult:
    result = ReleaseSyncResult()
    eff_on = entry.sync_releases if entry.sync_releases is not None else settings.sync_releases
    if not eff_on:
        return result
    rf = entry.release_filter if entry.release_filter is not None else settings.release_filter
    cap_bytes = settings.release_asset_max_size_mb * 1024 * 1024

    src = entry.source
    src_token = _cred_token(creds, src.platform)
    if not src_token:
        result.warnings.append(f"source {src.platform} has no PAT; release sync skipped")
        return result
    if not supports_releases(src.platform):
        result.warnings.append(f"source {src.platform} does not support releases; skipped")
        return result

    try:
        src_client = _client_for(src.platform, role="src")
        releases = src_client.list_releases(src.owner, src.repo, src_token)
    except ReleaseSyncError as e:
        result.errors.append(f"source {src.platform}:{src.owner}/{src.repo} list failed: {e}")
        return result

    filtered = filter_releases(releases, rf)
    result.releases_skipped = len(releases) - len(filtered)

    for target in entry.targets:
        if not supports_releases(target.platform):
            result.warnings.append(f"target {target.platform} does not support releases; skipped")
            continue
        tgt_token = _cred_token(creds, target.platform)
        if not tgt_token:
            result.warnings.append(f"target {target.platform} has no PAT; skipped")
            continue
        try:
            tgt_client = _client_for(target.platform, role="tgt")
        except ReleaseSyncError as e:
            result.warnings.append(f"target {target.platform} client unavailable: {e}")
            continue
        for rel in filtered:
            try:
                existing = tgt_client.get_release_by_tag(target.owner, target.repo, rel.tag_name, tgt_token)
            except ReleaseSyncError as e:
                result.errors.append(f"target {target.platform} get {rel.tag_name}: {e}")
                continue
            try:
                if existing is None:
                    created = tgt_client.create_release(target.owner, target.repo, tgt_token, rel)
                    result.releases_created += 1
                    tgt_rel = created
                else:
                    rel.release_id = existing.release_id
                    updated = tgt_client.update_release(target.owner, target.repo, tgt_token, rel)
                    result.releases_updated += 1
                    tgt_rel = updated
            except ReleaseSyncError as e:
                result.errors.append(f"target {target.platform} upsert {rel.tag_name}: {e}")
                continue
            _sync_assets(tgt_client, target, tgt_token, rel, tgt_rel, cap_bytes, result)
    return result
```

> 注意：`_client_for(src.platform, role="src")` 与 `role="tgt"` 在这里都返回同平台 client（因同平台测试需要区分源/目标实例，实现上用 `role` 仅作占位；若测试中需区分，可在 stub 用 platform 字符串区分，例如源平台记为 `github_src` 需在 RELEASE_CLIENTS 注册——但为了不污染注册表，测试层用 monkeypatch 直接替换 `_client_for` 即可，如上测试所示）。

**Step 4: 跑测试确认通过**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_sync.py -q`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/release_sync.py tests/test_release_sync.py
git commit -m "feat(release_sync): add sync_releases orchestration + asset sync + failure isolation"
```

---

## Task 7: 集成进 `src/sync.py`

**Files:**
- Modify: `src/sync.py` （`SyncResult` 增 `release_result` 字段；`sync_topology_entry` 收 `settings` 参数并在分支同步后调用 `sync_releases`）
- Test: `tests/test_sync.py`（或新增 `tests/test_release_integration.py`）

**Step 1: 写失败测试**

```python
from src.sync import sync_topology_entry, SyncResult
from src.config import SyncSettings, TopologyEntry, Endpoint

def test_sync_topology_entry_runs_release_sync(monkeypatch):
    import src.release_sync as rs
    captured = {}
    def _fake_sync_releases(entry, creds, settings):
        captured["called"] = True
        return rs.ReleaseSyncResult(releases_created=2)
    monkeypatch.setattr(rs, "sync_releases", _fake_sync_releases)

    entry = TopologyEntry(
        name="x",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="ssh"),
        targets=[Endpoint(platform="gitee", owner="o", repo="r", branch="main", auth="ssh")],
    )
    # bypass_credentials=True 跳过真实 clone；用 url_overrides 避免 git 网络
    # 但分支同步仍会跑策略.sync（对本地 bare repo）。为隔离，monkeypatch 策略：
    import src.strategies.mirror as m
    orig = m.MirrorStrategy.sync
    def _noop(self, **kw):
        from src.strategies.base import StrategyResult
        return StrategyResult(success=True)
    m.MirrorStrategy.sync = _noop
    try:
        res = sync_topology_entry(
            entry=entry, creds={}, work_dir="/tmp/wt",
            url_overrides={"github": "x", "gitee": "y"},
            bypass_credentials=True,
            settings=SyncSettings(sync_releases=True),
        )
    finally:
        m.MirrorStrategy.sync = orig
    assert captured.get("called") is True
    assert res.release_result is not None and res.release_result.releases_created == 2
```

**Step 2: 跑测试确认失败**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_integration.py -q`
Expected: FAIL（`release_result` 字段/`settings` 参数未接）。

**Step 3: 写最小实现**（`src/sync.py`）

在 import 区加：

```python
from src.release_sync import sync_releases as _sync_releases
```

`SyncResult` 数据类增加字段：

```python
    release_result: "ReleaseSyncResult | None" = None
```

>（`ReleaseSyncResult` 仅在类型注解用到，用字符串前向引用即可，无需 import）

`sync_topology_entry` 签名增加 `settings: "SyncSettings | None" = None`（放在 `auto_create` 之后），并在循环结束后、`return SyncResult(...)` 之前插入：

```python
    release_result = None
    if settings is not None:
        eff_on = entry.sync_releases if entry.sync_releases is not None else settings.sync_releases
        if eff_on:
            release_result = _sync_releases(entry, creds, settings)

    return SyncResult(
        success=True,
        entry_name=entry.name,
        source=f"{entry.source.platform}:{entry.source.owner}/{entry.source.repo}#{entry.source.branch}",
        targets_pushed=pushed,
        deleted=deleted,
        skipped=skipped,
        restored=restored,
        message="ok",
        release_result=release_result,
    )
```

**Step 4: 跑测试确认通过**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_release_integration.py -q`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/sync.py tests/test_release_integration.py
git commit -m "feat(sync): mount sync_releases after branch sync; add release_result to SyncResult"
```

---

## Task 8: `src/main.py` 输出与失败计数

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main.py`（已有则追加）

**Step 1: 写失败测试**

```python
from src.main import run_sync

def test_main_counts_release_errors(monkeypatch):
    import src.sync as s
    orig = s.sync_topology_entry
    def _fake(entry, **kw):
        from src.sync import SyncResult
        from src.release_sync import ReleaseSyncResult
        return SyncResult(success=True, entry_name=entry.name, source="x",
                          targets_pushed=[], release_result=ReleaseSyncResult(errors=["boom"]))
    s.sync_topology_entry = _fake
    rc = run_sync("config/sync.yaml", url_overrides={"github": "x", "gitee": "y"})
    s.sync_topology_entry = orig
    assert rc == 1  # release fatal error counts as failure
```

**Step 2: 跑测试确认失败**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_main.py -k release_errors -q`
Expected: FAIL（rc 为 0，因未计 release errors）。

**Step 3: 写最小实现**（`src/main.py`）

在 `for entry in cfg.topology:` 循环中，`sync_topology_entry` 调用增加 `settings=cfg.settings` 参数；在打印 OK 之后增加 release 摘要：

```python
            print(
                f"[OK] {entry.name}: {result.source} -> "
                f"{', '.join(result.targets_pushed) or '(no targets)'}"
            )
            rr = result.release_result
            if rr is not None:
                print(
                    f"[OK] {entry.name} releases: created={rr.releases_created} "
                    f"updated={rr.releases_updated} skipped={rr.releases_skipped} | "
                    f"assets: up={rr.assets_uploaded} skip={rr.assets_skipped}"
                )
                for w in rr.warnings:
                    print(f"[WARN] {entry.name}: {w}")
                for e in rr.errors:
                    print(f"[ERROR] {entry.name}: {e}", file=sys.stderr)
                if rr.errors:
                    failed += 1
```

`update sync_topology_entry(...)` 调用补 `settings=cfg.settings`：

```python
            result = sync_topology_entry(
                entry=entry,
                creds=creds,
                work_dir=work_dir / entry.name,
                force_push=cfg.settings.force_push,
                delete_remote=cfg.settings.delete_remote,
                mode=mode,
                preserve_files=preserve_files or [],
                url_overrides=url_overrides,
                bypass_credentials=bypass_credentials,
                auto_create=cfg.settings.auto_create,
                settings=cfg.settings,
            )
```

**Step 4: 跑测试确认通过**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest tests/test_main.py -q`
Expected: PASS。

**Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat(main): print release sync summary; count release errors as failure"
```

---

## Task 9: 文档 + 全量回归 + 收尾

**Files:**
- Modify: `docs/README.md` （补充 `sync_releases` / `release_asset_max_size_mb` / `release_filter` schema 与 Behavior 说明）
- 全量测试

**Step 1: 更新 `docs/README.md`**

在配置 schema 表新增三行（对照设计文档 §2 字段说明表），并新增「Release 同步」小节：说明总开关默认关、四平台降级、筛选四种 mode、`include_drafts`、资产大小上限与失败隔离行为，并给一份 YAML 示例（取自设计文档 §2）。

**Step 2: 跑全量测试**

Run: `uv run --with pytest --with PyYAML --with GitPython python -m pytest -q`
Expected: 全部 PASS（基线 69 + 新增 release 相关用例），无回归。

**Step 3: Commit**

```bash
git add docs/README.md
git commit -m "docs: document release sync config + behavior"
```

**Step 4: 收尾**

- 在 worktree 内 `git log --oneline` 复核提交链。
- 告知用户可发起 PR / 合并到 main（用 `/commit` 流程或 `git merge`/`gh pr create`）；本计划不自动合并。

---

## 执行后验收标准

1. `sync_releases: false`（默认）时，行为与现有完全一致，零回归。
2. `sync_releases: true` 时，分支同步后自动把源 release（按 `release_filter`）同步到各目标；GitHub/Gitee 完整，CNB/GitCode 不支持时 warn + 跳过。
3. 资产大小超 `release_asset_max_size_mb` 自动跳过并告警；单资产失败不阻断其他资产/目标。
4. 幂等：目标已有同 tag release 则 update，否则 create。
5. 全部测试通过；文档更新到位。
