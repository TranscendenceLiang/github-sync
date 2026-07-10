# 自动创建目标仓库 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 sync 过程中，当目标仓库不存在且 `auto_create: true` 时自动创建仓库。

**Architecture:** 新增 `src/auto_create.py` 封装各平台创建仓库的 API 调用（curl）。在 `sync_topology_entry` 中捕获策略抛出的 "not found" 错误，调用 `create_repo()` 创建仓库后重试。每个 `Endpoint` 新增 `auto_create` 和 `visibility` 字段。

**Tech Stack:** Python 3.11, curl, pytest

## Global Constraints

- `auto_create` 在 Endpoint 层级覆盖 settings 全局设置
- `visibility` 只在 Endpoint 层级设置，默认 `"private"`
- API 调用统一使用 `subprocess.run(["curl", ...])`，不用外部库
- 创建仓库使用 PAT（Personal Access Token），即使目标平台 auth 配置为 ssh

---

### Task 1: Config — Endpoint 新增 auto_create + visibility 字段

**Files:**
- Modify: `src/config.py` (Endpoint dataclass + _parse_endpoint)

**Interfaces:**
- Produces: `Endpoint.auto_create: bool = False`
- Produces: `Endpoint.visibility: str = "private"`

- [ ] **Step 1: 更新 Endpoint dataclass**

```python
# src/config.py

@dataclass
class Endpoint:
    platform: str
    owner: str
    repo: str
    branch: str
    auth: str = "ssh"
    auto_create: bool = False
    visibility: str = "private"

    def __post_init__(self) -> None:
        if self.platform not in SUPPORTED_PLATFORMS:
            raise ConfigError(...)
        if self.auth not in ("ssh", "pat"):
            raise ConfigError(...)
        if self.visibility not in ("public", "private"):
            raise ConfigError(
                f"visibility must be 'public' or 'private', got {self.visibility!r}"
            )
```

- [ ] **Step 2: 更新 `_parse_endpoint` 解析新字段**

```python
# src/config.py, _parse_endpoint

def _parse_endpoint(data: Any, ctx: str) -> Endpoint:
    ...
    try:
        return Endpoint(
            platform=str(data["platform"]).lower(),
            owner=str(data["owner"]),
            repo=str(data["repo"]),
            branch=str(data["branch"]),
            auth=str(data.get("auth", "ssh")).lower(),
            auto_create=bool(data.get("auto_create", False)),
            visibility=str(data.get("visibility", "private")).lower(),
        )
    ...
```

- [ ] **Step 3: 写测试**

```python
# tests/test_config.py, append

def test_load_config_with_auto_create_and_visibility(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source: {platform: github, owner: o, repo: r, branch: main}
              targets:
                - platform: cnb
                  owner: myorg
                  repo: myrepo
                  branch: main
                  auto_create: true
                  visibility: public
    """))
    cfg = load_config(cfg_file)
    t = cfg.topology[0].targets[0]
    assert t.auto_create is True
    assert t.visibility == "public"

def test_load_config_auto_create_defaults(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source: {platform: github, owner: o, repo: r, branch: main}
              targets: [{platform: gitee, owner: o, repo: r, branch: main}]
    """))
    cfg = load_config(cfg_file)
    t = cfg.topology[0].targets[0]
    assert t.auto_create is False
    assert t.visibility == "private"

def test_load_config_invalid_visibility_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source: {platform: github, owner: o, repo: r, branch: main}
              targets:
                - platform: cnb
                  owner: o
                  repo: r
                  branch: main
                  visibility: secret
    """))
    with pytest.raises(ConfigError, match="visibility"):
        load_config(cfg_file)
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_config.py -v
Expected: all tests PASS
```

- [ ] **Step 5: 提交（注意：可能还在 feat/rebase-mode 分支上）**

```bash
git checkout -b feat/auto-create 2>/dev/null || true
git add src/config.py tests/test_config.py
git commit -m "feat(config): add auto_create and visibility fields to Endpoint"
```

---

### Task 2: auto_create 模块

**Files:**
- Create: `src/auto_create.py`
- Create: `tests/test_auto_create.py`

**Interfaces:**
- Produces: `CreateRepoRequest(platform, owner, repo, visibility, token)`
- Produces: `CreateRepoError(Exception)`
- Produces: `create_repo(request: CreateRepoRequest) -> None` — 调用各平台 API

- [ ] **Step 1: 写测试 — 验证 create_repo 调用逻辑（mock curl）**

```python
# tests/test_auto_create.py
"""Tests for auto_create module (repo creation via curl)."""
import json
import subprocess
from pathlib import Path

import pytest

from src.auto_create import CreateRepoRequest, create_repo, CreateRepoError


def test_create_repo_github(tmp_path):
    """GitHub: POST /user/repos with Bearer token."""
    call_log = []
    original_run = subprocess.run

    def _mock_run(args, **kwargs):
        call_log.append(args)
        # Return a fake successful response
        class FakeProc:
            returncode = 0
            stdout = '{"id": 1, "name": "test"}'
            stderr = ""
        return FakeProc()

    subprocess.run = _mock_run
    try:
        create_repo(CreateRepoRequest(
            platform="github",
            owner="myorg",
            repo="test-repo",
            visibility="private",
            token="ghp_token123",
        ))
    finally:
        subprocess.run = original_run

    assert len(call_log) == 1
    cmd = call_log[0]
    assert "curl" in cmd
    assert "api.github.com/user/repos" in cmd
    assert "Authorization: Bearer ghp_token123" in cmd
    assert "test-repo" in json.dumps(" ".join(cmd))


def test_create_repo_cnb(tmp_path):
    """CNB: POST /repos with slug + name + visibility."""
    call_log = []

    def _mock_run(args, **kwargs):
        call_log.append(args)
        class FakeProc:
            returncode = 0
            stdout = '{"id": 1}'
            stderr = ""
        return FakeProc()

    subprocess.run = _mock_run
    try:
        create_repo(CreateRepoRequest(
            platform="cnb",
            owner="myorg",
            repo="test-repo",
            visibility="private",
            token="cnb_token123",
        ))
    finally:
        subprocess.run = original_run

    cmd = " ".join(call_log[0])
    assert "api.cnb.cool/repos" in cmd
    assert "myorg" in cmd  # slug
    assert "test-repo" in cmd


def test_create_repo_gitee(tmp_path):
    """Gitee: POST /api/v5/user/repos with access_token in body."""
    call_log = []

    def _mock_run(args, **kwargs):
        call_log.append(args)
        class FakeProc:
            returncode = 0
            stdout = '{"id": 1}'
            stderr = ""
        return FakeProc()

    subprocess.run = _mock_run
    try:
        create_repo(CreateRepoRequest(
            platform="gitee",
            owner="myorg",
            repo="test-repo",
            visibility="public",
            token="gitee_token123",
        ))
    finally:
        subprocess.run = original_run

    cmd = " ".join(call_log[0])
    assert "gitee.com/api/v5/user/repos" in cmd


def test_create_repo_gitcode(tmp_path):
    """GitCode: POST /api/v5/user/repos with access_token query param."""
    call_log = []

    def _mock_run(args, **kwargs):
        call_log.append(args)
        class FakeProc:
            returncode = 0
            stdout = '{"id": 1}'
            stderr = ""
        return FakeProc()

    subprocess.run = _mock_run
    try:
        create_repo(CreateRepoRequest(
            platform="gitcode",
            owner="myorg",
            repo="test-repo",
            visibility="public",
            token="gc_token123",
        ))
    finally:
        subprocess.run = original_run

    cmd = " ".join(call_log[0])
    assert "api.gitcode.com/api/v5/user/repos" in cmd


def test_create_repo_api_failure(tmp_path):
    """API returns non-zero exit code -> CreateRepoError."""
    def _mock_run(args, **kwargs):
        class FakeProc:
            returncode = 1
            stdout = ""
            stderr = "404 Not Found"
        return FakeProc()

    subprocess.run = _mock_run
    try:
        with pytest.raises(CreateRepoError, match="404"):
            create_repo(CreateRepoRequest(
                platform="github",
                owner="o", repo="r", visibility="private", token="t",
            ))
    finally:
        subprocess.run = original_run


def test_create_repo_unsupported_platform(tmp_path):
    """Unknown platform -> CreateRepoError."""
    with pytest.raises(CreateRepoError, match="unsupported platform"):
        create_repo(CreateRepoRequest(
            platform="gitlab",
            owner="o", repo="r", visibility="private", token="t",
        ))
```

- [ ] **Step 2: 运行测试 — 验证失败（TDD RED）**

```bash
pytest tests/test_auto_create.py -v
Expected: ImportError or similar (module doesn't exist yet)
```

- [ ] **Step 3: 实现 create_repo**

```python
# src/auto_create.py
"""Repository auto-creation via platform REST APIs."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


class CreateRepoError(Exception):
    """Raised when repository creation fails."""


@dataclass
class CreateRepoRequest:
    platform: str   # github | gitee | cnb | gitcode
    owner: str      # Organization or user path
    repo: str       # Repository name
    visibility: str  # "public" | "private"
    token: str      # API token (PAT)


def create_repo(request: CreateRepoRequest) -> None:
    """Create a repository on the target platform via curl.

    Raises CreateRepoError on failure.
    """
    if request.platform == "github":
        url = "https://api.github.com/user/repos"
        headers = [
            "-H", f"Authorization: Bearer {request.token}",
            "-H", "Content-Type: application/json",
        ]
        body = json.dumps({
            "name": request.repo,
            "private": request.visibility == "private",
        })
    elif request.platform == "gitee":
        url = "https://gitee.com/api/v5/user/repos"
        headers = ["-H", "Content-Type: application/json"]
        body = json.dumps({
            "access_token": request.token,
            "name": request.repo,
            "private": request.visibility == "private",
        })
    elif request.platform == "cnb":
        url = "https://api.cnb.cool/repos"
        headers = [
            "-H", f"Authorization: Bearer {request.token}",
            "-H", "Content-Type: application/json",
        ]
        body = json.dumps({
            "slug": request.owner,
            "name": request.repo,
            "visibility": request.visibility,
        })
    elif request.platform == "gitcode":
        url = f"https://api.gitcode.com/api/v5/user/repos?access_token={request.token}"
        headers = ["-H", "Content-Type: application/json"]
        body = json.dumps({
            "name": request.repo,
            "path": request.repo,
        })
    else:
        raise CreateRepoError(f"unsupported platform: {request.platform!r}")

    proc = subprocess.run(
        ["curl", "-s", "-X", "POST", url] + headers + ["--data", body],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise CreateRepoError(
            f"failed to create repo on {request.platform}: "
            f"curl exit={proc.returncode}, stderr={proc.stderr.strip()}"
        )
    # Some APIs return non-zero for errors, some always return 0 with error in body.
    # Check for common error indicators in response body.
    resp = proc.stdout.strip()
    if resp and resp.startswith("{"):
        try:
            parsed = json.loads(resp)
        except json.JSONDecodeError:
            pass
        else:
            errcode = parsed.get("errcode") or parsed.get("code")
            errmsg = parsed.get("errmsg") or parsed.get("message") or parsed.get("error")
            if errcode or (errmsg and "not found" not in errmsg.lower()):
                raise CreateRepoError(
                    f"failed to create repo on {request.platform}: "
                    f"errcode={errcode}, errmsg={errmsg}"
                )
```

- [ ] **Step 4: 运行测试 — 验证通过**

```bash
pytest tests/test_auto_create.py -v
Expected: all tests PASS
```

- [ ] **Step 5: 提交**

```bash
git add src/auto_create.py tests/test_auto_create.py
git commit -m "feat(auto_create): add repo creation via platform APIs"
```

---

### Task 3: 集成到 sync 流程

**Files:**
- Modify: `src/sync.py`
- Test: `tests/test_sync.py` (新增测试)

- [ ] **Step 1: 写集成测试**

```python
# tests/test_sync.py, append

def test_sync_topology_entry_auto_create_retries_push(tmp_path, make_local_repo, monkeypatch):
    """When push fails with 'not found' and auto_create=True, repo is created and push retried."""
    from src.auto_create import CreateRepoRequest

    src = make_local_repo(commits=2, branch="main")
    src_bare = Path(src["bare"])
    dst_bare = tmp_path / "nonexistent.git"
    # Do NOT init dst_bare — simulate non-existent target

    creds = {
        "github": Credential(ssh_key="k", pat=None),
        "cnb": Credential(ssh_key=None, pat="cnb_token"),
    }

    # Create a target endpoint with auto_create=True
    entry = TopologyEntry(
        name="auto",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="ssh"),
        targets=[Endpoint(
            platform="cnb", owner="myorg", repo="myrepo",
            branch="main", auth="pat",
            auto_create=True, visibility="private",
        )],
    )

    # Mock create_repo to actually create the bare repo
    created_repos = set()
    def mock_create_repo(req: CreateRepoRequest):
        if req.platform == "cnb":
            subprocess.run(["git", "init", "--bare", str(dst_bare)], check=True, capture_output=True)
            created_repos.add(req.repo)

    import src.sync as sync_module
    monkeypatch.setattr(sync_module, "create_repo", mock_create_repo)

    result = sync_topology_entry(
        entry=entry,
        creds=creds,
        work_dir=tmp_path / "work",
        force_push=True,
        url_overrides={"github": str(src_bare), "cnb": str(dst_bare)},
    )

    assert result.success is True
    assert "myrepo" in created_repos
    # Verify dst has the source's content
    dst_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=dst_bare, capture_output=True, text=True
    )
    src_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=src_bare, capture_output=True, text=True
    )
    assert dst_head.stdout.strip() == src_head.stdout.strip()


def test_sync_topology_entry_auto_create_disabled_still_fails(tmp_path, make_local_repo):
    """When auto_create=False, missing target repo still raises SyncError."""
    src = make_local_repo(commits=2, branch="main")
    src_bare = Path(src["bare"])
    dst_bare = tmp_path / "nonexistent.git"
    # dst does not exist

    creds = {
        "github": Credential(ssh_key="k", pat=None),
        "cnb": Credential(ssh_key=None, pat="cnb_token"),
    }

    entry = TopologyEntry(
        name="noauto",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="ssh"),
        targets=[Endpoint(
            platform="cnb", owner="myorg", repo="myrepo",
            branch="main", auth="pat",
            auto_create=False,  # disabled
        )],
    )

    with pytest.raises(SyncError, match="not found|failed|mirror sync failed"):
        sync_topology_entry(
            entry=entry,
            creds=creds,
            work_dir=tmp_path / "work",
            force_push=True,
            url_overrides={"github": str(src_bare), "cnb": str(dst_bare)},
        )
```

- [ ] **Step 2: 运行测试 — 验证失败（TDD RED）**

```bash
pytest tests/test_sync.py::test_sync_topology_entry_auto_create_retries_push -v
Expected: FAIL (auto_create not implemented)
```

- [ ] **Step 3: 在 sync.py 中集成 auto_create**

```python
# src/sync.py
# 新增 import
from src.auto_create import CreateRepoRequest, create_repo, CreateRepoError


def sync_topology_entry(
    entry: TopologyEntry,
    creds: dict[str, "Credential"],
    work_dir: Path,
    force_push: bool = False,
    delete_remote: bool = False,
    mode: str = "mirror",
    preserve_files: list[str] | None = None,
    url_overrides: dict[str, str] | None = None,
    bypass_credentials: bool = False,
) -> SyncResult:
    # ... (source setup unchanged) ...

    for target in entry.targets:
        # ... target creds, URL resolve unchanged ...

        # Delegate to strategy
        try:
            result = strategy.sync(
                source_dir=source_clone_dir,
                target_url=target_url,
                branch=entry.source.branch,
            )
        except SyncError as e:
            # Auto-create: if the target repo doesn't exist and auto_create
            # is enabled, create the repo and retry once.
            if _should_auto_create(target, e, tgt_cred_value):
                _create_target_repo(target, tgt_cred_value)
                result = strategy.sync(
                    source_dir=source_clone_dir,
                    target_url=target_url,
                    branch=entry.source.branch,
                )
            else:
                raise

        # ... result formatting unchanged ...


def _should_auto_create(target: Endpoint, error: SyncError, tgt_cred: str | None) -> bool:
    """Return True if this error indicates a missing repo and auto_create is enabled."""
    if not target.auto_create:
        return False
    if not tgt_cred:
        return False  # Need a token to create repos
    msg = str(error).lower()
    return any(kw in msg for kw in ("not found", "repository not found", "couldn't find"))


def _create_target_repo(target: Endpoint, tgt_cred: str | None) -> None:
    """Create a repository for the given target endpoint."""
    request = CreateRepoRequest(
        platform=target.platform,
        owner=target.owner,
        repo=target.repo,
        visibility=target.visibility,
        token=tgt_cred or "",
    )
    try:
        create_repo(request)
    except CreateRepoError as e:
        raise SyncError(
            f"failed to auto-create repo on {target.platform}:{target.owner}/{target.repo}: {e}"
        ) from e
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_sync.py -v
Expected: ALL PASS (including 2 new auto_create tests)
```

```bash
pytest tests/ -v
Expected: ALL PASS
```

- [ ] **Step 5: 提交**

```bash
git add src/sync.py tests/test_sync.py
git commit -m "feat(sync): auto-create target repo when missing and auto_create enabled"
```

---

### Task 4: 集成到 main.py + 更新配置

**Files:**
- Modify: `src/main.py`
- Modify: `config/sync.yaml`

- [ ] **Step 1: main.py — auto_create 和 visibility 由 config 直通 sync**

当前 `sync_topology_entry` 接收 `target` 参数（`Endpoint`），其中已包含 `auto_create` 和 `visibility`。`_create_target_repo` 内部直接从 `target` 对象读取这些字段，所以 main.py **不需要额外传参**。

检查 `main.py` 确认没有需要修改的地方 — `sync_topology_entry(entry=entry, ...)` 已经把整个 entry（含 targets）传过去了。

- [ ] **Step 2: 更新示例配置**

```yaml
# config/sync.yaml
sync:
  settings:
    auto_create: true           # 启用自动创建（默认 false）
    ...

  topology:
    - name: "github-ciphertalk-to-cnb"
      mode: rebase
      ...
      targets:
        - platform: cnb
          owner: TranscendenceLiang
          repo: CipherTalk
          branch: main
          auth: pat
          auto_create: true
          visibility: private
```

- [ ] **Step 3: 提交**

```bash
git add config/sync.yaml
git commit -m "chore(config): enable auto_create in example config"
```

---

### Task 5: 文档

**Files:**
- Modify: `docs/README.md`

- [ ] **Step 1: 在 Config Schema 中补充 auto_create + visibility**

```yaml
sync:
  settings:
    auto_create: false    # 全局开关
    ...

  topology:
    - name: "example"
      source: ...
      targets:
        - platform: cnb
          owner: myorg
          repo: myproject
          branch: main
          auto_create: true      # 覆盖全局
          visibility: private    # private (默认) | public
```

- [ ] **Step 2: 在 Behavior 章节添加说明**

```markdown
### Auto-Create

设置 `auto_create: true` 后，当目标仓库不存在时，系统会自动调用平台 API 创建仓库后再执行同步。

- **GitHub**: `POST /user/repos` (Bearer token)
- **Gitee**: `POST /api/v5/user/repos` (access_token)
- **CNB**: `POST /repos` (Bearer token)
- **GitCode**: `POST /api/v5/user/repos` (access_token)

创建仓库使用 PAT 认证，即使目标平台配置了 SSH 认证。`visibility` 字段控制仓库可见性。
```

- [ ] **Step 3: 提交**

```bash
git add docs/README.md
git commit -m "docs: add auto-create configuration and behavior"
```
