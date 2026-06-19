# Git Multi-Sync Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a centralized Git repository sync system that uses GitHub Actions to synchronize code branches between GitHub, Gitee, CNB, and GitCode platforms, configured via YAML.

**Architecture:** Centered repository approach - one sync repository contains the GitHub Actions workflow, YAML config, and Python sync engine. SSH keys / PATs are stored as GitHub Secrets. The sync engine reads the YAML topology, fetches source branches, detects conflicts, and pushes to target platforms.

**Tech Stack:**
- Python 3.11 (sync engine)
- GitHub Actions (CI/CD)
- PyYAML (config parsing)
- GitPython (git operations, with raw git CLI fallback)
- pytest (testing)

## Global Constraints

- Python 3.11+
- Each platform's credentials (SSH_KEY or TOKEN) are shared across all repos on that platform
- CNB only supports HTTPS + PAT auth (no SSH)
- Other platforms (GitHub, Gitee, GitCode) support both SSH and PAT, user-specified per endpoint
- Sync direction is one-way only: source -> target
- If both source and target have new commits, sync fails with error
- `auto_create: false` is the default; auto-creation is not implemented in this plan (config slot reserved)
- No Releases sync (only branches + tags)
- All credentials live in GitHub Secrets, never in code
- Use `fetch-depth: 0` for full clone history

## File Structure

```
multi-sync-center/
├── .github/
│   └── workflows/
│       └── sync.yml                      # Main GitHub Actions workflow
├── src/
│   ├── __init__.py
│   ├── credential.py                     # CredentialManager: loads SSH/PAT from env
│   ├── config.py                         # YAML loader + validator
│   ├── git_helper.py                     # Pure git operations (clone, push, fetch)
│   ├── platform.py                       # URL builders per platform + auth detection
│   ├── sync.py                           # SyncEngine: orchestrates one topology entry
│   └── main.py                           # Entry point: read config, iterate topology
├── config/
│   └── sync.yaml                         # Default sync configuration
├── tests/
│   ├── __init__.py
│   ├── conftest.py                       # Shared fixtures (mock git dirs)
│   ├── test_credential.py
│   ├── test_config.py
│   ├── test_platform.py
│   ├── test_git_helper.py
│   └── test_sync.py
├── docs/
│   └── README.md                         # User-facing usage docs
├── requirements.txt                      # pyyaml, GitPython, pytest
└── .gitignore
```

Each Python file has a single responsibility:
- `credential.py`: load credentials from env, build authenticated URLs
- `platform.py`: build clone URLs, identify platform, list supported platforms
- `config.py`: load and validate YAML config against schema
- `git_helper.py`: low-level git shell commands (clone, fetch, push, get HEAD)
- `sync.py`: orchestrate one sync task (source -> target with conflict detection)
- `main.py`: entry point iterating all topology entries

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `config/sync.yaml`
- Create: `docs/README.md`

**Interfaces:** None yet (this is the bootstrap task).

- [ ] **Step 1: Create requirements.txt**

```
PyYAML>=6.0
GitPython>=3.1.40
pytest>=7.4.0
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.venv/
venv/
.env
repos/
```

- [ ] **Step 3: Create src/__init__.py**

```python
"""Git Multi-Sync Center source package."""
__version__ = "0.1.0"
```

- [ ] **Step 4: Create tests/__init__.py**

```python
"""Test package."""
```

- [ ] **Step 5: Create tests/conftest.py with shared fixtures**

```python
"""Shared pytest fixtures."""
import os
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_repos_dir(tmp_path):
    """Provide a temporary directory for git operations."""
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    return repos_dir


@pytest.fixture
def make_local_repo(tmp_path):
    """Factory: create a local bare repo (acts as 'remote') and a working clone."""

    def _make(name="repo", commits=1, branch="main"):
        # Create bare remote
        bare = tmp_path / f"{name}.git"
        subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

        # Create working clone
        work = tmp_path / name
        subprocess.run(["git", "clone", str(bare), str(work)], check=True, capture_output=True)
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "Test"
        env["GIT_AUTHOR_EMAIL"] = "test@test.com"
        env["GIT_COMMITTER_NAME"] = "Test"
        env["GIT_COMMITTER_EMAIL"] = "test@test.com"
        subprocess.run(["git", "checkout", "-b", branch], cwd=work, check=True, capture_output=True, env=env)

        for i in range(commits):
            (work / f"file_{i}.txt").write_text(f"content {i}")
            subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
            subprocess.run(
                ["git", "commit", "-m", f"commit {i}"],
                cwd=work, check=True, capture_output=True, env=env
            )

        subprocess.run(["git", "push", "-u", "origin", branch], cwd=work, check=True, capture_output=True, env=env)

        return {"bare": str(bare), "work": str(work), "branch": branch}

    return _make
```

- [ ] **Step 6: Create config/sync.yaml (default placeholder)**

```yaml
# Git Multi-Sync Center - default configuration
# See docs/README.md for full schema documentation
sync:
  settings:
    auto_create: false        # Not yet implemented; config slot reserved
    force_push: false
    delete_remote: false

  topology: []
  # Example:
  # topology:
  #   - name: "github-to-gitee"
  #     source:
  #       platform: github
  #       owner: myorg
  #       repo: myproject
  #       branch: main
  #       auth: ssh
  #     targets:
  #       - platform: gitee
  #         owner: myorg
  #         repo: myproject
  #         branch: main
  #         auth: ssh
```

- [ ] **Step 7: Create docs/README.md (initial stub)**

```markdown
# Git Multi-Sync Center

A centralized Git repository sync system using GitHub Actions.

## Quick Start

1. Create a new repository to host this center
2. Configure GitHub Secrets for your platforms (see "Configuration" below)
3. Edit `config/sync.yaml` to define your sync topology
4. Trigger via Actions tab, `repository_dispatch`, or schedule

## Configuration

### GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `SSH_KEY_GITHUB` | SSH private key for GitHub (or `TOKEN_GITHUB`) |
| `SSH_KEY_GITEE` | SSH private key for Gitee (or `TOKEN_GITEE`) |
| `TOKEN_CNB` | Personal Access Token for CNB |
| `SSH_KEY_GITCODE` | SSH private key for GitCode (or `TOKEN_GITCODE`) |
| `SYNC_DISPATCH_TOKEN` | PAT to authorize `repository_dispatch` triggers |

### Config Schema

See `config/sync.yaml` for a working example.
```

- [ ] **Step 8: Install dependencies and verify pytest runs**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully.

Run: `pytest --collect-only`
Expected: "no tests ran" (no tests yet) with exit code 5.

- [ ] **Step 9: Commit**

```bash
git init
git add .
git commit -m "chore: scaffold project structure and dependencies"
```

---

## Task 2: Platform URL Builder

**Files:**
- Create: `src/platform.py`
- Test: `tests/test_platform.py`

**Interfaces:**
- Consumes: platform name, owner, repo, auth method, optional token
- Produces: clone URL string suitable for `git clone`
- Public API: `build_url(platform, owner, repo, auth, token=None) -> str`, `SUPPORTED_PLATFORMS: set[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_platform.py`:

```python
"""Tests for platform URL building."""
import pytest

from src.platform import build_url, SUPPORTED_PLATFORMS, normalize_platform


def test_supported_platforms_contains_expected():
    assert "github" in SUPPORTED_PLATFORMS
    assert "gitee" in SUPPORTED_PLATFORMS
    assert "cnb" in SUPPORTED_PLATFORMS
    assert "gitcode" in SUPPORTED_PLATFORMS


def test_build_url_github_ssh():
    url = build_url("github", "myorg", "myrepo", auth="ssh")
    assert url == "git@github.com:myorg/myrepo.git"


def test_build_url_github_pat():
    url = build_url("github", "myorg", "myrepo", auth="pat", token="ghp_xxx")
    assert url == "https://x-access-token:ghp_xxx@github.com/myorg/myrepo.git"


def test_build_url_gitee_ssh():
    url = build_url("gitee", "myorg", "myrepo", auth="ssh")
    assert url == "git@gitee.com:myorg/myrepo.git"


def test_build_url_gitee_pat():
    url = build_url("gitee", "myorg", "myrepo", auth="pat", token="gt_xxx")
    assert url == "https://gt_xxx@gitee.com/myorg/myrepo.git"


def test_build_url_cnb_pat():
    url = build_url("cnb", "myorg", "myrepo", auth="pat", token="cnb_xxx")
    assert url == "https://cnb_xxx@cnb.cool/myorg/myrepo.git"


def test_build_url_cnb_ssh_raises():
    # CNB does not support SSH
    with pytest.raises(ValueError, match="CNB does not support SSH"):
        build_url("cnb", "myorg", "myrepo", auth="ssh")


def test_build_url_cnb_missing_token_raises():
    with pytest.raises(ValueError, match="token required"):
        build_url("cnb", "myorg", "myrepo", auth="pat", token=None)


def test_build_url_gitcode_ssh():
    url = build_url("gitcode", "myorg", "myrepo", auth="ssh")
    assert url == "git@gitcode.com:myorg/myrepo.git"


def test_build_url_gitcode_pat():
    url = build_url("gitcode", "myorg", "myrepo", auth="pat", token="gc_xxx")
    assert url == "https://gc_xxx@gitcode.com/myorg/myrepo.git"


def test_build_url_unknown_platform_raises():
    with pytest.raises(ValueError, match="unsupported platform"):
        build_url("unknown", "o", "r", auth="ssh")


def test_build_url_pat_missing_token_raises():
    with pytest.raises(ValueError, match="token required"):
        build_url("github", "myorg", "myrepo", auth="pat", token=None)


def test_normalize_platform_case_insensitive():
    assert normalize_platform("GitHub") == "github"
    assert normalize_platform("GITEE") == "gitee"
    assert normalize_platform("CNB") == "cnb"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_platform.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.platform'"

- [ ] **Step 3: Implement src/platform.py**

```python
"""Platform URL builders and constants.

Each supported Git platform has a known URL pattern for SSH and HTTPS+PAT
authentication. CNB only supports HTTPS+PAT; all others support both.
"""
from __future__ import annotations

SUPPORTED_PLATFORMS: set[str] = {"github", "gitee", "cnb", "gitcode"}

# SSH templates use {owner} and {repo}; no host substitution.
_SSH_TEMPLATES = {
    "github": "git@github.com:{owner}/{repo}.git",
    "gitee": "git@gitee.com:{owner}/{repo}.git",
    "gitcode": "git@gitcode.com:{owner}/{repo}.git",
}

# HTTPS templates use {owner}, {repo}, {token}.
_HTTPS_TEMPLATES = {
    "github": "https://x-access-token:{token}@github.com/{owner}/{repo}.git",
    "gitee": "https://{token}@gitee.com/{owner}/{repo}.git",
    "cnb": "https://{token}@cnb.cool/{owner}/{repo}.git",
    "gitcode": "https://{token}@gitcode.com/{owner}/{repo}.git",
}


def normalize_platform(platform: str) -> str:
    """Lowercase and trim a platform name."""
    return platform.strip().lower()


def build_url(platform: str, owner: str, repo: str, auth: str, token: str | None = None) -> str:
    """Build a clone URL for the given platform.

    Args:
        platform: One of SUPPORTED_PLATFORMS (case-insensitive).
        owner: Repository owner (user or org).
        repo: Repository name.
        auth: 'ssh' or 'pat'.
        token: Personal Access Token. Required when auth='pat'.

    Returns:
        A URL string ready for `git clone`.

    Raises:
        ValueError: For unsupported platform, invalid auth, or missing token.
    """
    p = normalize_platform(platform)
    if p not in SUPPORTED_PLATFORMS:
        raise ValueError(f"unsupported platform: {platform!r}")

    if auth not in ("ssh", "pat"):
        raise ValueError(f"auth must be 'ssh' or 'pat', got {auth!r}")

    if p == "cnb" and auth == "ssh":
        raise ValueError("CNB does not support SSH authentication")

    if auth == "pat":
        if not token:
            raise ValueError("token required for PAT auth")
        template = _HTTPS_TEMPLATES[p]
        return template.format(owner=owner, repo=repo, token=token)

    template = _SSH_TEMPLATES[p]
    return template.format(owner=owner, repo=repo)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_platform.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/platform.py tests/test_platform.py
git commit -m "feat(platform): add URL builder for github/gitee/cnb/gitcode"
```

---

## Task 3: Credential Manager

**Files:**
- Create: `src/credential.py`
- Test: `tests/test_credential.py`

**Interfaces:**
- Consumes: `os.environ`
- Produces: a `Credential` object exposing `ssh_key` (str|None) and `pat` (str|None) per platform
- Public API: `class Credential`, `class CredentialError`, `load_credentials() -> dict[str, Credential]`

A "platform" here is the broad key. We expose helpers for both auth methods so the sync engine can decide per endpoint.

- [ ] **Step 1: Write the failing test**

Create `tests/test_credential.py`:

```python
"""Tests for credential loading from environment."""
import pytest

from src.credential import (
    Credential,
    CredentialError,
    load_credentials,
    get_secret_name,
)


def test_get_secret_name_ssh():
    assert get_secret_name("github", "ssh") == "SSH_KEY_GITHUB"
    assert get_secret_name("gitee", "ssh") == "SSH_KEY_GITEE"
    assert get_secret_name("gitcode", "ssh") == "SSH_KEY_GITCODE"


def test_get_secret_name_pat():
    assert get_secret_name("github", "pat") == "TOKEN_GITHUB"
    assert get_secret_name("gitee", "pat") == "TOKEN_GITEE"
    assert get_secret_name("cnb", "pat") == "TOKEN_CNB"
    assert get_secret_name("gitcode", "pat") == "TOKEN_GITCODE"


def test_credential_dataclass():
    c = Credential(ssh_key="key1", pat="pat1")
    assert c.ssh_key == "key1"
    assert c.pat == "pat1"
    assert c.has_ssh is True
    assert c.has_pat is True

    c2 = Credential()
    assert c2.has_ssh is False
    assert c2.has_pat is False


def test_load_credentials_missing_all_raises(monkeypatch):
    # Clear all relevant env vars
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)
    # All platforms have at least one credential configured by default in
    # our test fixture pattern; for this test we simulate "no creds for github"
    # by removing only the github env vars, and we expect the loader to still
    # succeed for other platforms. Use a stricter helper:
    with pytest.raises(CredentialError):
        load_credentials(required={"github"})


def test_load_credentials_collects_all_set(monkeypatch):
    monkeypatch.setenv("SSH_KEY_GITHUB", "k1")
    monkeypatch.setenv("TOKEN_GITEE", "t1")
    monkeypatch.setenv("TOKEN_CNB", "c1")
    monkeypatch.setenv("SSH_KEY_GITCODE", "k2")
    creds = load_credentials()
    assert creds["github"].ssh_key == "k1"
    assert creds["github"].pat is None
    assert creds["gitee"].pat == "t1"
    assert creds["gitee"].ssh_key is None
    assert creds["cnb"].pat == "c1"
    assert creds["gitcode"].ssh_key == "k2"


def test_load_credentials_required_missing_raises(monkeypatch):
    monkeypatch.delenv("SSH_KEY_GITHUB", raising=False)
    monkeypatch.delenv("TOKEN_GITHUB", raising=False)
    monkeypatch.setenv("TOKEN_GITEE", "t1")
    monkeypatch.setenv("TOKEN_CNB", "c1")
    monkeypatch.setenv("SSH_KEY_GITCODE", "k1")
    with pytest.raises(CredentialError, match="github"):
        load_credentials(required={"github"})


def test_load_credentials_returns_empty_for_unset(monkeypatch):
    # Clear all
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)
    creds = load_credentials()
    assert creds["github"] == Credential()
    assert creds["gitee"] == Credential()
    assert creds["cnb"] == Credential()
    assert creds["gitcode"] == Credential()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_credential.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.credential'"

- [ ] **Step 3: Implement src/credential.py**

```python
"""Credential loading from environment variables / GitHub Secrets.

Each platform's credentials are stored in GitHub Secrets and exposed to the
runner as environment variables. This module loads them into a dict keyed by
platform name.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.platform import SUPPORTED_PLATFORMS

# Maps (platform, auth) -> env var name holding the secret.
_SECRET_NAMES = {
    ("github", "ssh"): "SSH_KEY_GITHUB",
    ("github", "pat"): "TOKEN_GITHUB",
    ("gitee", "ssh"): "SSH_KEY_GITEE",
    ("gitee", "pat"): "TOKEN_GITEE",
    ("cnb", "ssh"): None,  # CNB does not support SSH
    ("cnb", "pat"): "TOKEN_CNB",
    ("gitcode", "ssh"): "SSH_KEY_GITCODE",
    ("gitcode", "pat"): "TOKEN_GITCODE",
}


class CredentialError(Exception):
    """Raised when required credentials are missing."""


@dataclass
class Credential:
    """Credentials for a single platform."""
    ssh_key: str | None = None
    pat: str | None = None

    @property
    def has_ssh(self) -> bool:
        return bool(self.ssh_key)

    @property
    def has_pat(self) -> bool:
        return bool(self.pat)


def get_secret_name(platform: str, auth: str) -> str:
    """Return the env var / Secret name for the given platform + auth method."""
    key = (platform, auth)
    if key not in _SECRET_NAMES:
        raise ValueError(f"unknown platform/auth combo: {platform}/{auth}")
    name = _SECRET_NAMES[key]
    if name is None:
        raise ValueError(f"{platform} does not support auth method {auth}")
    return name


def load_credentials(required: set[str] | None = None) -> dict[str, Credential]:
    """Load all platform credentials from environment.

    Args:
        required: If given, raise CredentialError when a platform in this set
            has neither an SSH key nor a PAT set.

    Returns:
        Mapping platform -> Credential.
    """
    creds: dict[str, Credential] = {}
    for platform in SUPPORTED_PLATFORMS:
        ssh = os.environ.get(get_secret_name(platform, "ssh"), "") or None
        pat = os.environ.get(get_secret_name(platform, "pat"), "") or None
        creds[platform] = Credential(ssh_key=ssh, pat=pat)

    if required:
        missing = [p for p in required if not (creds[p].has_ssh or creds[p].has_pat)]
        if missing:
            raise CredentialError(
                f"missing credentials for platform(s): {', '.join(missing)}. "
                f"Set the corresponding GitHub Secret (see docs/README.md)."
            )

    return creds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_credential.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/credential.py tests/test_credential.py
git commit -m "feat(credential): load platform credentials from env"
```

---

## Task 4: YAML Config Loader

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: a YAML file path
- Produces: a `SyncConfig` object with `settings` and `topology` attributes
- Public API: `class SyncConfig`, `class TopologyEntry`, `class Endpoint`, `class SyncSettings`, `load_config(path) -> SyncConfig`, `validate_config(cfg) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
"""Tests for YAML config loading and validation."""
import textwrap
from pathlib import Path

import pytest

from src.config import (
    SyncConfig,
    SyncSettings,
    TopologyEntry,
    Endpoint,
    load_config,
    ConfigError,
)


def test_load_minimal_config(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            auto_create: false
            force_push: false
            delete_remote: false
          topology: []
    """))
    cfg = load_config(cfg_file)
    assert isinstance(cfg, SyncConfig)
    assert cfg.settings.auto_create is False
    assert cfg.settings.force_push is False
    assert cfg.settings.delete_remote is False
    assert cfg.topology == []


def test_load_full_config(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            auto_create: false
            force_push: false
            delete_remote: true
          topology:
            - name: "github-to-gitee"
              source:
                platform: github
                owner: myorg
                repo: myproject
                branch: main
                auth: ssh
              targets:
                - platform: gitee
                  owner: myorg
                  repo: myproject
                  branch: main
                  auth: ssh
            - name: "broadcast"
              source:
                platform: github
                owner: myorg
                repo: myproject
                branch: develop
                auth: pat
              targets:
                - platform: gitee
                  owner: myorg
                  repo: myproject
                  branch: develop
                  auth: ssh
                - platform: cnb
                  owner: myteam
                  repo: myproject
                  branch: develop
                  auth: pat
    """))
    cfg = load_config(cfg_file)
    assert len(cfg.topology) == 2

    first = cfg.topology[0]
    assert isinstance(first, TopologyEntry)
    assert first.name == "github-to-gitee"
    assert first.source.platform == "github"
    assert first.source.auth == "ssh"
    assert first.source.branch == "main"
    assert len(first.targets) == 1
    assert first.targets[0].platform == "gitee"

    second = cfg.topology[1]
    assert second.source.auth == "pat"
    assert len(second.targets) == 2
    assert second.targets[1].platform == "cnb"
    assert second.targets[1].auth == "pat"


def test_load_config_defaults(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source:
                platform: github
                owner: o
                repo: r
                branch: main
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
    """))
    cfg = load_config(cfg_file)
    assert cfg.settings.auto_create is False
    assert cfg.settings.force_push is False
    assert cfg.settings.delete_remote is False
    # auth defaults to ssh
    assert cfg.topology[0].source.auth == "ssh"
    assert cfg.topology[0].targets[0].auth == "ssh"


def test_load_config_missing_sync_key_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text("foo: bar\n")
    with pytest.raises(ConfigError, match="sync"):
        load_config(cfg_file)


def test_load_config_topology_not_list_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text("sync:\n  topology: notalist\n")
    with pytest.raises(ConfigError, match="topology must be a list"):
        load_config(cfg_file)


def test_load_config_topology_entry_missing_name(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - source:
                platform: github
                owner: o
                repo: r
                branch: main
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
    """))
    with pytest.raises(ConfigError, match="name"):
        load_config(cfg_file)


def test_load_config_endpoint_missing_required_field(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: x
              source:
                platform: github
                owner: o
                branch: main
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
    """))
    with pytest.raises(ConfigError, match="repo"):
        load_config(cfg_file)


def test_load_config_targets_empty_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: x
              source:
                platform: github
                owner: o
                repo: r
                branch: main
              targets: []
    """))
    with pytest.raises(ConfigError, match="at least one target"):
        load_config(cfg_file)


def test_load_config_invalid_auth_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: x
              source:
                platform: github
                owner: o
                repo: r
                branch: main
                auth: bogus
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
    """))
    with pytest.raises(ConfigError, match="auth"):
        load_config(cfg_file)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.config'"

- [ ] **Step 3: Implement src/config.py**

```python
"""YAML configuration loader and validator.

Schema:

sync:
  settings:
    auto_create: false      # Reserved, not yet implemented
    force_push: false
    delete_remote: false

  topology:
    - name: "unique-name"
      source:
        platform: github    # github | gitee | cnb | gitcode
        owner: myorg
        repo: myproject
        branch: main
        auth: ssh           # ssh (default) | pat
      targets:
        - platform: gitee
          owner: myorg
          repo: myproject
          branch: main
          auth: ssh
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.platform import SUPPORTED_PLATFORMS


class ConfigError(Exception):
    """Raised when configuration is invalid."""


@dataclass
class SyncSettings:
    auto_create: bool = False
    force_push: bool = False
    delete_remote: bool = False


@dataclass
class Endpoint:
    platform: str
    owner: str
    repo: str
    branch: str
    auth: str = "ssh"

    def __post_init__(self) -> None:
        if self.platform not in SUPPORTED_PLATFORMS:
            raise ConfigError(
                f"unsupported platform {self.platform!r}; "
                f"must be one of {sorted(SUPPORTED_PLATFORMS)}"
            )
        if self.auth not in ("ssh", "pat"):
            raise ConfigError(f"auth must be 'ssh' or 'pat', got {self.auth!r}")


@dataclass
class TopologyEntry:
    name: str
    source: Endpoint
    targets: list[Endpoint] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.targets:
            raise ConfigError(f"topology entry {self.name!r}: at least one target required")


@dataclass
class SyncConfig:
    settings: SyncSettings
    topology: list[TopologyEntry]


def _parse_endpoint(data: Any, ctx: str) -> Endpoint:
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: expected mapping, got {type(data).__name__}")
    required = ("platform", "owner", "repo", "branch")
    missing = [k for k in required if k not in data]
    if missing:
        raise ConfigError(f"{ctx}: missing required field(s): {', '.join(missing)}")
    try:
        return Endpoint(
            platform=str(data["platform"]).lower(),
            owner=str(data["owner"]),
            repo=str(data["repo"]),
            branch=str(data["branch"]),
            auth=str(data.get("auth", "ssh")).lower(),
        )
    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"{ctx}: invalid endpoint: {e}") from e


def _parse_entry(data: Any) -> TopologyEntry:
    if not isinstance(data, dict):
        raise ConfigError(f"topology entry: expected mapping, got {type(data).__name__}")
    if "name" not in data:
        raise ConfigError("topology entry missing 'name'")
    name = str(data["name"])
    source = _parse_endpoint(data.get("source"), f"topology[{name}].source")
    targets_raw = data.get("targets", [])
    if not isinstance(targets_raw, list):
        raise ConfigError(f"topology[{name}].targets must be a list")
    targets = [_parse_endpoint(t, f"topology[{name}].targets[{i}]") for i, t in enumerate(targets_raw)]
    return TopologyEntry(name=name, source=source, targets=targets)


def _parse_settings(data: Any) -> SyncSettings:
    if data is None:
        return SyncSettings()
    if not isinstance(data, dict):
        raise ConfigError("settings must be a mapping")
    return SyncSettings(
        auto_create=bool(data.get("auto_create", False)),
        force_push=bool(data.get("force_push", False)),
        delete_remote=bool(data.get("delete_remote", False)),
    )


def load_config(path: str | Path) -> SyncConfig:
    """Load and validate a sync config from a YAML file."""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML: {e}") from e

    if not isinstance(raw, dict) or "sync" not in raw:
        raise ConfigError("config must have top-level 'sync' key")
    sync = raw["sync"]
    if not isinstance(sync, dict):
        raise ConfigError("'sync' must be a mapping")

    settings = _parse_settings(sync.get("settings"))
    topo_raw = sync.get("topology", [])
    if not isinstance(topo_raw, list):
        raise ConfigError("topology must be a list")

    # Reject duplicate names
    names = [t.get("name") for t in topo_raw if isinstance(t, dict)]
    seen: set[str] = set()
    for n in names:
        if n in seen:
            raise ConfigError(f"duplicate topology name: {n!r}")
        seen.add(n)

    topology = [_parse_entry(t) for t in topo_raw]
    return SyncConfig(settings=settings, topology=topology)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat(config): YAML config loader and validator"
```

---

## Task 5: Git Helper - Clone, Fetch, Push, HEAD

**Files:**
- Create: `src/git_helper.py`
- Test: `tests/test_git_helper.py`

**Interfaces:**
- Consumes: a `Credential`, an `Endpoint`, a working directory
- Produces: paths to local clones, HEAD commit SHA, push success/failure
- Public API:
  - `prepare_ssh_key(cred: Credential, ssh_dir: Path) -> None` - writes SSH key to disk with 600 perms and adds to ssh agent via `~/.ssh/config`
  - `clone_or_fetch(url: str, dest: Path, branch: str, ssh_dir: Path | None = None) -> Path`
  - `get_head_sha(repo: Path, branch: str) -> str | None`
  - `push_branch(repo: Path, remote: str, branch: str, force: bool = False) -> None`
  - `class GitError`

- [ ] **Step 1: Write the failing test**

Create `tests/test_git_helper.py`:

```python
"""Tests for low-level git operations."""
import os
import subprocess
from pathlib import Path

import pytest

from src.git_helper import (
    GitError,
    clone_or_fetch,
    get_head_sha,
    push_branch,
    prepare_ssh_key,
)


def test_get_head_sha_returns_commit(make_local_repo):
    repos = make_local_repo(commits=1, branch="main")
    work = Path(repos["work"])
    sha = get_head_sha(work, "main")
    assert sha is not None
    assert len(sha) == 40


def test_get_head_sha_missing_branch_returns_none(make_local_repo):
    repos = make_local_repo(commits=1, branch="main")
    work = Path(repos["work"])
    assert get_head_sha(work, "nonexistent") is None


def test_clone_or_fetch_clones_bare_url(tmp_path, make_local_repo):
    src = make_local_repo(commits=2, branch="main")
    src_bare = src["bare"]

    dest = tmp_path / "clone"
    clone_or_fetch(src_bare, dest, "main")
    assert (dest / ".git").exists()
    sha = get_head_sha(dest, "main")
    assert sha is not None
    assert len(sha) == 40


def test_clone_or_fetch_fetches_updates(tmp_path, make_local_repo):
    src = make_local_repo(commits=1, branch="main")
    src_bare = src["bare"]
    src_work = Path(src["work"])

    dest = tmp_path / "clone"
    clone_or_fetch(src_bare, dest, "main")
    old_sha = get_head_sha(dest, "main")

    # Add another commit to source
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com",
    })
    (src_work / "new.txt").write_text("new")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "second"], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "push", "origin", "main"], cwd=src_work, check=True, env=env)

    clone_or_fetch(src_bare, dest, "main")
    new_sha = get_head_sha(dest, "main")
    assert new_sha != old_sha


def test_push_branch_to_bare(tmp_path, make_local_repo):
    src = make_local_repo(commits=1, branch="main")
    src_bare = src["bare"]
    src_work = Path(src["work"])

    # Create a working clone
    dest_bare = tmp_path / "dest.git"
    subprocess.run(["git", "init", "--bare", str(dest_bare)], check=True, capture_output=True)

    dest_work = tmp_path / "dest_work"
    clone_or_fetch(src_bare, dest_work, "main")
    subprocess.run(["git", "remote", "add", "dest", str(dest_bare)], cwd=dest_work, check=True, capture_output=True)

    push_branch(dest_work, "dest", "main", force=False)
    # Verify the dest bare has main now
    out = subprocess.run(
        ["git", "rev-parse", "main"],
        cwd=dest_bare, capture_output=True, text=True
    )
    assert out.returncode == 0
    assert len(out.stdout.strip()) == 40


def test_prepare_ssh_key_writes_file(tmp_path):
    cred_ssh = type("C", (), {"ssh_key": "fake-key-content", "pat": None})()
    ssh_dir = tmp_path / "ssh"
    prepare_ssh_key(cred_ssh, ssh_dir)
    key_file = ssh_dir / "id_rsa"
    assert key_file.exists()
    assert key_file.read_text() == "fake-key-content"
    # Permissions must be 600 on POSIX; on Windows just check it exists
    if os.name != "nt":
        mode = key_file.stat().st_mode & 0o777
        assert mode == 0o600
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git_helper.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.git_helper'"

- [ ] **Step 3: Implement src/git_helper.py**

```python
"""Low-level git operations.

Wraps the git CLI for clone, fetch, push, and HEAD lookup. This module is
intentionally thin: SyncEngine composes these primitives.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.credential import Credential


class GitError(Exception):
    """Raised for any git operation failure."""


def _run(args: list[str], cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a git command. Raise GitError on non-zero return."""
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise GitError(
            f"git command failed: {' '.join(args)}\n"
            f"  exit: {proc.returncode}\n"
            f"  stderr: {proc.stderr.strip()}"
        )
    return proc


def prepare_ssh_key(cred: "Credential", ssh_dir: Path) -> Path:
    """Write the SSH key to a file in ssh_dir with 0600 perms.

    Returns the path to the key file.
    """
    if not cred.ssh_key:
        raise GitError("cannot prepare ssh key: credential has no ssh_key")
    ssh_dir.mkdir(parents=True, exist_ok=True)
    key_file = ssh_dir / "id_rsa"
    key_file.write_text(cred.ssh_key)
    if os.name != "nt":
        os.chmod(key_file, 0o600)
    return key_file


def clone_or_fetch(url: str, dest: Path, branch: str) -> Path:
    """Clone the URL into dest, or fetch+checkout if dest already exists.

    Always returns dest.
    """
    dest = Path(dest)
    if (dest / ".git").is_dir():
        # Fetch and reset to remote branch
        _run(["git", "fetch", "origin", branch], cwd=dest)
        _run(["git", "checkout", branch], cwd=dest)
        _run(["git", "reset", "--hard", f"origin/{branch}"], cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--branch", branch, "--single-branch", url, str(dest)])
    return dest


def get_head_sha(repo: Path, branch: str) -> str | None:
    """Return the SHA that the local branch points to, or None if missing.

    The branch is queried against origin/{branch} first, falling back to
    the local branch.
    """
    repo = Path(repo)
    for ref in (f"origin/{branch}", branch):
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=repo, capture_output=True, text=True
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    return None


def push_branch(repo: Path, remote: str, branch: str, force: bool = False) -> None:
    """Push a local branch to the given remote."""
    args = ["git", "push"]
    if force:
        args.append("--force")
    args += [remote, branch]
    _run(args, cwd=Path(repo))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_git_helper.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/git_helper.py tests/test_git_helper.py
git commit -m "feat(git): low-level git operations (clone, fetch, push, head)"
```

---

## Task 6: Sync Engine - Single Topology Entry

**Files:**
- Create: `src/sync.py`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: a `TopologyEntry`, a `dict[str, Credential]`, a working directory
- Produces: a `SyncResult` (success/failure, message)
- Public API:
  - `class SyncResult`
  - `class SyncError`
  - `sync_topology_entry(entry: TopologyEntry, creds: dict[str, Credential], work_dir: Path, force_push: bool = False) -> SyncResult`
  - `check_conflict(source_sha: str | None, target_sha: str | None, ancestor_sha: str | None) -> bool`

- [ ] **Step 1: Write the failing test**

Create `tests/test_sync.py`:

```python
"""Tests for the sync engine."""
import os
import subprocess
from pathlib import Path

import pytest

from src.config import Endpoint, TopologyEntry, SyncSettings
from src.credential import Credential
from src.sync import (
    SyncResult,
    SyncError,
    sync_topology_entry,
    check_conflict,
)


def test_check_conflict_no_commits():
    # Both sides empty
    assert check_conflict(None, None, None) is False


def test_check_conflict_only_source_has_commits():
    assert check_conflict("abc", None, None) is False


def test_check_conflict_only_target_has_commits():
    assert check_conflict(None, "abc", None) is False


def test_check_conflict_source_equals_target():
    assert check_conflict("abc", "abc", None) is False


def test_check_conflict_target_is_ancestor_of_source():
    # Source advanced beyond target; no conflict
    assert check_conflict("newer", "older", "older") is False


def test_check_conflict_both_advanced_diverge():
    # Both sides have unique commits -> conflict
    assert check_conflict("source_head", "target_head", "ancestor") is True


def test_sync_topology_entry_happy_path(tmp_path, make_local_repo):
    src = make_local_repo(commits=2, branch="main")
    dst = make_local_repo(commits=0, branch="main")
    # dst is empty; only push needed
    dst_bare = Path(dst["bare"])
    src_bare = Path(src["bare"])

    creds = {
        "github": Credential(ssh_key="k", pat=None),
        "gitee": Credential(ssh_key="k", pat=None),
    }

    entry = TopologyEntry(
        name="test",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="ssh"),
        targets=[Endpoint(platform="gitee", owner="o", repo="r", branch="main", auth="ssh")],
    )

    # Use url_overrides to inject local bare repos (the sync engine supports this natively)
    result = sync_topology_entry(
        entry=entry,
        creds=creds,
        work_dir=tmp_path / "work",
        url_overrides={
            "github": str(src_bare),
            "gitee": str(dst_bare),
        },
    )

    assert result.success is True
    # Verify dst now has the same HEAD as src
    dst_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=dst_bare, capture_output=True, text=True
    )
    src_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=src_bare, capture_output=True, text=True
    )
    assert dst_head.stdout.strip() == src_head.stdout.strip()


def test_sync_topology_entry_raises_on_conflict(tmp_path, make_local_repo):
    src = make_local_repo(commits=2, branch="main")
    dst = make_local_repo(commits=2, branch="main")
    # Both have diverged - this will fail at push (non-fast-forward) without force
    src_bare = Path(src["bare"])
    dst_bare = Path(dst["bare"])

    creds = {
        "github": Credential(ssh_key="k", pat=None),
        "gitee": Credential(ssh_key="k", pat=None),
    }

    entry = TopologyEntry(
        name="conflict",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="ssh"),
        targets=[Endpoint(platform="gitee", owner="o", repo="r", branch="main", auth="ssh")],
    )

    with pytest.raises(SyncError, match="conflict"):
        sync_topology_entry(
            entry=entry,
            creds=creds,
            work_dir=tmp_path / "work",
            force_push=False,
            url_overrides={"github": str(src_bare), "gitee": str(dst_bare)},
        )


def test_sync_topology_entry_missing_credentials(tmp_path, make_local_repo):
    src = make_local_repo(commits=1, branch="main")
    creds = {
        "github": Credential(ssh_key=None, pat=None),
        "gitee": Credential(ssh_key="k", pat=None),
    }
    entry = TopologyEntry(
        name="x",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="ssh"),
        targets=[Endpoint(platform="gitee", owner="o", repo="r", branch="main", auth="ssh")],
    )
    with pytest.raises(SyncError, match="github"):
        sync_topology_entry(
            entry=entry,
            creds=creds,
            work_dir=tmp_path / "work",
            url_overrides={"github": "x", "gitee": "y"},
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sync.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.sync'"

- [ ] **Step 3: Implement src/sync.py**

```python
"""Sync engine: executes a single TopologyEntry (source -> [targets]).

For each topology entry:
  1. Resolve source/target URLs and credentials
  2. Clone or update source
  3. For each target:
     a. Clone or update target
     b. Compare HEAD SHAs
     c. If both have unique commits beyond a common ancestor -> raise SyncError
     d. Otherwise, push source branch to target
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import Endpoint, TopologyEntry
from src.git_helper import (
    GitError,
    clone_or_fetch,
    get_head_sha,
    push_branch,
)
from src.platform import build_url

if TYPE_CHECKING:
    from src.credential import Credential


class SyncError(Exception):
    """Raised when a sync task fails."""


@dataclass
class SyncResult:
    success: bool
    entry_name: str
    source: str
    targets_pushed: list[str]
    message: str = ""


def check_conflict(
    source_sha: str | None,
    target_sha: str | None,
    ancestor_sha: str | None,
) -> bool:
    """Return True if both source and target have diverged from the ancestor.

    Logic:
      - If either side is missing -> no conflict
      - If both SHAs equal -> no conflict
      - If target_sha == ancestor_sha (target hasn't moved) -> no conflict
      - If source_sha == ancestor_sha (source hasn't moved) -> no conflict
      - Otherwise, both sides advanced past ancestor -> CONFLICT
    """
    if source_sha is None or target_sha is None:
        return False
    if source_sha == target_sha:
        return False
    if ancestor_sha is None:
        # No common ancestor; both have unique commits
        return True
    if source_sha == ancestor_sha or target_sha == ancestor_sha:
        return False
    return True


def _merge_base(local_repo: Path, ref_a: str, ref_b: str) -> str | None:
    """Compute the merge base of two refs in the local repo. Returns SHA or None."""
    proc = subprocess.run(
        ["git", "merge-base", ref_a, ref_b],
        cwd=local_repo, capture_output=True, text=True
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _resolve_credentials(endpoint: Endpoint, creds: dict[str, "Credential"]) -> str | None:
    """Pick the appropriate credential value for the endpoint's auth method."""
    cred = creds.get(endpoint.platform)
    if cred is None:
        return None
    if endpoint.auth == "pat":
        return cred.pat
    return cred.ssh_key


def sync_topology_entry(
    entry: TopologyEntry,
    creds: dict[str, "Credential"],
    work_dir: Path,
    force_push: bool = False,
    url_overrides: dict[str, str] | None = None,
) -> SyncResult:
    """Execute a single topology entry: fetch source, push to all targets.

    Args:
        entry: The TopologyEntry to execute.
        creds: Mapping platform -> Credential.
        work_dir: A working directory for clones.
        force_push: Whether to allow non-fast-forward pushes (from settings).
        url_overrides: Optional mapping platform -> URL. Used by tests to inject
            local bare repos. In production, URLs are built from build_url().

    Raises:
        SyncError: On any failure (missing creds, conflict, git errors).
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Check source credentials
    src_cred_value = _resolve_credentials(entry.source, creds)
    if entry.source.platform not in creds or not (
        (entry.source.auth == "pat" and src_cred_value)
        or (entry.source.auth == "ssh" and src_cred_value)
    ):
        raise SyncError(
            f"missing credentials for source platform {entry.source.platform!r}"
        )

    # Resolve source URL
    if url_overrides and entry.source.platform in url_overrides:
        source_url = url_overrides[entry.source.platform]
    else:
        source_url = build_url(
            entry.source.platform,
            entry.source.owner,
            entry.source.repo,
            entry.source.auth,
            token=src_cred_value,
        )

    source_clone_dir = work_dir / f"src_{entry.name}"
    try:
        clone_or_fetch(source_url, source_clone_dir, entry.source.branch)
    except GitError as e:
        raise SyncError(f"failed to fetch source: {e}") from e

    source_sha = get_head_sha(source_clone_dir, entry.source.branch)
    if source_sha is None:
        raise SyncError(
            f"source branch {entry.source.branch!r} not found on {entry.source.platform}"
        )

    pushed: list[str] = []

    for target in entry.targets:
        # Check target credentials
        tgt_cred_value = _resolve_credentials(target, creds)
        if target.platform not in creds or not (
            (target.auth == "pat" and tgt_cred_value)
            or (target.auth == "ssh" and tgt_cred_value)
        ):
            raise SyncError(
                f"missing credentials for target platform {target.platform!r}"
            )

        # Resolve target URL
        if url_overrides and target.platform in url_overrides:
            target_url = url_overrides[target.platform]
        else:
            target_url = build_url(
                target.platform,
                target.owner,
                target.repo,
                target.auth,
                token=tgt_cred_value,
            )

        target_clone_dir = work_dir / f"tgt_{entry.name}_{target.platform}"
        # We use a bare clone to fetch target state without checkout conflicts
        target_bare_dir = work_dir / f"tgtbare_{entry.name}_{target.platform}"
        try:
            clone_or_fetch(target_url, target_bare_dir, target.branch)
        except GitError as e:
            raise SyncError(
                f"failed to fetch target {target.platform}:{target.owner}/{target.repo}: {e}"
            ) from e

        target_sha = get_head_sha(target_bare_dir, target.branch)

        # Check for conflict
        ancestor = _merge_base(source_clone_dir, source_sha, target_sha) if target_sha else None
        if check_conflict(source_sha, target_sha, ancestor):
            raise SyncError(
                f"conflict on entry {entry.name!r}: both source and target have "
                f"diverged (source={source_sha[:7]}, target={target_sha[:7] if target_sha else 'none'})"
            )

        # Push from source clone to target
        try:
            subprocess.run(
                ["git", "remote", "remove", "target"], cwd=source_clone_dir, capture_output=True
            )
            subprocess.run(
                ["git", "remote", "add", "target", target_url],
                cwd=source_clone_dir, capture_output=True, check=True
            )
            push_branch(source_clone_dir, "target", entry.source.branch, force=force_push)
            pushed.append(f"{target.platform}:{target.owner}/{target.repo}#{target.branch}")
        except GitError as e:
            raise SyncError(
                f"failed to push to {target.platform}:{target.owner}/{target.repo}: {e}"
            ) from e
        finally:
            shutil.rmtree(target_bare_dir, ignore_errors=True)

    return SyncResult(
        success=True,
        entry_name=entry.name,
        source=f"{entry.source.platform}:{entry.source.owner}/{entry.source.repo}#{entry.source.branch}",
        targets_pushed=pushed,
        message="ok",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/sync.py tests/test_sync.py
git commit -m "feat(sync): single topology entry sync engine with conflict detection"
```

---

## Task 7: Main Entry Point

**Files:**
- Create: `src/main.py`
- Test: `tests/test_main.py` (lightweight smoke test)

**Interfaces:**
- Consumes: a config file path (default `config/sync.yaml`) and credentials in env
- Produces: exits 0 on success, non-zero on failure
- Public API: `def main() -> int`, `if __name__ == "__main__": sys.exit(main())`

- [ ] **Step 1: Write the failing test**

Create `tests/test_main.py`:

```python
"""Smoke tests for the main entry point."""
import textwrap
from pathlib import Path

import pytest

from src.main import run_sync


def test_run_sync_empty_topology(tmp_path, monkeypatch):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            auto_create: false
            force_push: false
            delete_remote: false
          topology: []
    """))
    # No credentials needed for empty topology
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)

    result = run_sync(cfg_file, work_dir=tmp_path / "work")
    assert result == 0


def test_run_sync_missing_config_raises(tmp_path, monkeypatch):
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(Exception):
        run_sync(tmp_path / "missing.yaml", work_dir=tmp_path / "work")


def test_run_sync_returns_nonzero_on_failure(tmp_path, monkeypatch):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source:
                platform: github
                owner: o
                repo: r
                branch: main
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
    """))
    # No credentials set
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SYNC_FAKE", "1")  # marker
    # main() catches the error and returns non-zero
    from src.main import main
    rc = main(config_path=cfg_file, work_dir=tmp_path / "work")
    assert rc != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.main'"

- [ ] **Step 3: Implement src/main.py**

```python
"""Entry point for the sync engine.

Reads the config, loads credentials from env, and iterates the topology.
Returns 0 on success, non-zero on failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

from src.config import load_config, ConfigError
from src.credential import load_credentials, CredentialError
from src.sync import sync_topology_entry, SyncError


def run_sync(
    config_path: str | Path,
    work_dir: str | Path = "repos",
    url_overrides: dict[str, str] | None = None,
) -> int:
    """Execute the full sync workflow. Returns process exit code."""
    config_path = Path(config_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load config
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        print(f"[ERROR] config: {e}", file=sys.stderr)
        return 2

    # 2. Determine which platforms are required by the topology
    required: set[str] = set()
    for entry in cfg.topology:
        required.add(entry.source.platform)
        for t in entry.targets:
            required.add(t.platform)

    # 3. Load credentials
    try:
        creds = load_credentials(required=required)
    except CredentialError as e:
        print(f"[ERROR] credentials: {e}", file=sys.stderr)
        return 3

    # 4. Execute each topology entry
    failed = 0
    for entry in cfg.topology:
        print(f"[INFO] syncing topology entry: {entry.name}")
        try:
            result = sync_topology_entry(
                entry=entry,
                creds=creds,
                work_dir=work_dir / entry.name,
                force_push=cfg.settings.force_push,
                url_overrides=url_overrides,
            )
            print(
                f"[OK] {entry.name}: {result.source} -> "
                f"{', '.join(result.targets_pushed) or '(no targets)'}"
            )
        except SyncError as e:
            print(f"[FAIL] {entry.name}: {e}", file=sys.stderr)
            failed += 1
        except Exception as e:
            print(f"[FAIL] {entry.name}: unexpected error: {e}", file=sys.stderr)
            failed += 1

    return 0 if failed == 0 else 1


def main(
    config_path: str | Path = "config/sync.yaml",
    work_dir: str | Path = "repos",
) -> int:
    """Entry point. Returns 0 on success, non-zero on failure."""
    return run_sync(config_path=config_path, work_dir=work_dir)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat(main): entry point with config + credentials + sync loop"
```

---

## Task 8: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/sync.yml`

**Interfaces:** GitHub Actions workflow that triggers the sync engine.

- [ ] **Step 1: Create .github/workflows/sync.yml**

```yaml
name: Sync Repositories

on:
  # Manual trigger
  workflow_dispatch:

  # Triggered by other repositories via repository_dispatch
  repository_dispatch:
    types: [sync-triggered]

  # Scheduled runs (default: every 6 hours)
  schedule:
    - cron: "7 */6 * * *"  # off-the-hour minute to avoid thundering herd

jobs:
  sync:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Prepare SSH directory
        run: |
          mkdir -p ~/.ssh
          chmod 700 ~/.ssh
          # Disable strict host key checking to allow first-time connections
          cat > ~/.ssh/config <<'EOF'
          Host *
            StrictHostKeyChecking no
            UserKnownHostsFile=/dev/null
            IdentityFile ~/.ssh/id_rsa
          EOF

      - name: Write SSH keys (if provided)
        # Only writes keys whose Secret is set; PAT-only platforms are skipped
        env:
          SSH_KEY_GITHUB: ${{ secrets.SSH_KEY_GITHUB }}
          SSH_KEY_GITEE: ${{ secrets.SSH_KEY_GITEE }}
          SSH_KEY_GITCODE: ${{ secrets.SSH_KEY_GITCODE }}
        run: |
          set -e
          for k in SSH_KEY_GITHUB SSH_KEY_GITEE SSH_KEY_GITCODE; do
            v="${!k:-}"
            if [ -n "$v" ]; then
              echo ">>> Writing $k"
              printf '%s\n' "$v" > ~/.ssh/id_rsa
              chmod 600 ~/.ssh/id_rsa
              break  # only one SSH key per host; if multiple platforms use
                     # the same host, additional setup would be required
            fi
          done

      - name: Run sync engine
        env:
          SSH_KEY_GITHUB: ${{ secrets.SSH_KEY_GITHUB }}
          TOKEN_GITHUB: ${{ secrets.TOKEN_GITHUB }}
          SSH_KEY_GITEE: ${{ secrets.SSH_KEY_GITEE }}
          TOKEN_GITEE: ${{ secrets.TOKEN_GITEE }}
          TOKEN_CNB: ${{ secrets.TOKEN_CNB }}
          SSH_KEY_GITCODE: ${{ secrets.SSH_KEY_GITCODE }}
          TOKEN_GITCODE: ${{ secrets.TOKEN_GITCODE }}
        run: |
          python -m src.main
```

- [ ] **Step 2: Note the multi-SSH-key limitation**

Add a comment to `docs/README.md` (we'll expand it in Task 9) — for now, document this caveat: when multiple SSH-only platforms are configured, only the first SSH key (`SSH_KEY_GITHUB`) is written because they all map to `~/.ssh/id_rsa`. Users who need multiple SSH platforms should use PATs for the second one, or contact us for an enhancement.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/sync.yml
git commit -m "ci: add GitHub Actions workflow for manual/scheduled/dispatch triggers"
```

---

## Task 9: User-facing Documentation

**Files:**
- Modify: `docs/README.md`

**Interfaces:** None. This is documentation.

- [ ] **Step 1: Replace docs/README.md with the full user guide**

```markdown
# Git Multi-Sync Center

A centralized Git repository sync system using GitHub Actions. Synchronize
branches between GitHub, Gitee, CNB, and GitCode — manually, on push, or on
a schedule.

## Features

- **Multi-platform**: GitHub, Gitee, CNB, GitCode
- **Free topology**: any-to-any, one-to-many, configurable per endpoint
- **Mixed auth**: SSH key or Personal Access Token per endpoint
- **Three trigger modes**: manual (`workflow_dispatch`), automatic (`repository_dispatch`), scheduled (cron)
- **Conflict-safe**: errors out if both source and target have diverged
- **YAML-driven**: all sync rules in one config file

## Quick Start

1. **Create a new GitHub repository** to host this sync center (private recommended).

2. **Copy the contents of this repo** into your new repository.

3. **Configure GitHub Secrets** in *Settings → Secrets and variables → Actions*:

   | Secret | Required When | Description |
   |--------|---------------|-------------|
   | `SSH_KEY_GITHUB` | Using SSH for GitHub | SSH private key with repo access |
   | `TOKEN_GITHUB` | Using PAT for GitHub | Personal Access Token |
   | `SSH_KEY_GITEE` | Using SSH for Gitee | SSH private key |
   | `TOKEN_GITEE` | Using PAT for Gitee | Personal Access Token |
   | `TOKEN_CNB` | Always (CNB only supports PAT) | Personal Access Token |
   | `SSH_KEY_GITCODE` | Using SSH for GitCode | SSH private key |
   | `TOKEN_GITCODE` | Using PAT for GitCode | Personal Access Token |
   | `SYNC_DISPATCH_TOKEN` | Using automatic triggers | PAT to call `repository_dispatch` API |

   Notes:
   - Each platform uses **one credential for all its repos**.
   - SSH and PAT are interchangeable for GitHub, Gitee, GitCode. CNB requires PAT.

4. **Edit `config/sync.yaml`** to define your sync topology. See the example below.

5. **Trigger a sync**:
   - *Manual*: go to Actions → Sync Repositories → Run workflow
   - *Scheduled*: edit the cron in `.github/workflows/sync.yml`
   - *Automatic*: source repos call the center via `repository_dispatch` (see below)

## Config Schema

```yaml
sync:
  settings:
    auto_create: false        # Reserved; not yet implemented
    force_push: false         # Allow non-fast-forward pushes
    delete_remote: false      # Delete target branches that no longer exist on source

  topology:
    - name: "github-to-gitee"           # Unique name
      source:
        platform: github                # github | gitee | cnb | gitcode
        owner: myorg
        repo: myproject
        branch: main
        auth: ssh                       # ssh (default) | pat
      targets:
        - platform: gitee
          owner: myorg
          repo: myproject
          branch: main
          auth: ssh
```

### One-to-Many (broadcast)

```yaml
- name: "broadcast"
  source:
    platform: github
    owner: myorg
    repo: myproject
    branch: main
    auth: ssh
  targets:
    - { platform: gitee, owner: myorg, repo: myproject, branch: main, auth: ssh }
    - { platform: gitcode, owner: myorg, repo: myproject, branch: main, auth: pat }
    - { platform: cnb, owner: myteam, repo: myproject, branch: main, auth: pat }
```

## Automatic Triggers (from source repos)

In each source repository, add `.github/workflows/trigger-sync.yml`:

```yaml
name: Trigger Center Sync
on:
  push:
    branches: [main]

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger
        run: |
          curl -X POST \
            -H "Authorization: token ${{ secrets.SYNC_DISPATCH_TOKEN }}" \
            https://api.github.com/repos/YOUR-ORG/multi-sync-center/dispatches \
            -d '{"event_type": "sync-triggered"}'
```

Configure `SYNC_DISPATCH_TOKEN` in the source repo (same PAT as in the center).

## Behavior

- **One-way only**: source → targets. Bi-directional sync is not supported.
- **Conflict detection**: if both source and target have advanced past their
  merge base, sync **fails** with a clear error. Resolve manually.
- **No auto-create**: target repositories must exist. Set them up beforehand.
- **No Releases sync**: only branches and tags.

## Limitations

- **Multiple SSH platforms**: the workflow writes SSH key to `~/.ssh/id_rsa`
  (one key per host). If you configure SSH for both GitHub and Gitee, only
  the first key is written. Workaround: use PAT for one of them.
- **Target must exist**: `auto_create` is reserved for a future release.

## Development

```bash
pip install -r requirements.txt
pytest
```

## Architecture

See `docs/superpowers/specs/2026-06-19-multi-sync-center-design.md` for the
full design document.
```

- [ ] **Step 2: Copy the design doc into the repo**

Run:
```bash
mkdir -p docs/superpowers/specs
cp /path/to/design.md docs/superpowers/specs/2026-06-19-multi-sync-center-design.md
```
(Replace `/path/to/design.md` with the actual path the user supplies at execution time.)

- [ ] **Step 3: Commit**

```bash
git add docs/README.md docs/superpowers/specs/
git commit -m "docs: user guide and reference to design doc"
```

---

## Task 10: End-to-End Integration Test

**Files:**
- Create: `tests/test_integration.py`

**Interfaces:** Tests the full path `load_config → load_credentials → sync_topology_entry` against local bare repos.

- [ ] **Step 1: Write the test**

Create `tests/test_integration.py`:

```python
"""End-to-end integration test using local bare repos."""
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from src.config import load_config
from src.credential import Credential
from src.main import run_sync


def test_end_to_end_single_topology(tmp_path, monkeypatch):
    # Build source and target bare repos with content
    src_bare = tmp_path / "src.git"
    dst_bare = tmp_path / "dst.git"
    work = tmp_path / "work"
    src_work = tmp_path / "src_work"
    src_bare.mkdir()
    dst_bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(src_bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "--bare", str(dst_bare)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(src_bare), str(src_work)], check=True, capture_output=True)

    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t",
    })
    subprocess.run(["git", "checkout", "-b", "main"], cwd=src_work, check=True, env=env)
    (src_work / "README.md").write_text("# hello")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=src_work, check=True, env=env)

    # Write config that targets our local bare repos
    cfg = tmp_path / "sync.yaml"
    cfg.write_text(textwrap.dedent("""\
        sync:
          settings:
            auto_create: false
            force_push: false
            delete_remote: false
          topology:
            - name: "e2e"
              source:
                platform: github
                owner: o
                repo: r
                branch: main
                auth: ssh
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
                  auth: ssh
    """))

    # Patch platform URL builder to map to our local bare repos
    import src.sync as sync_mod
    overrides = {"github": str(src_bare), "gitee": str(dst_bare)}
    # No credentials needed because we use direct URLs
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)

    rc = run_sync(cfg, work_dir=work, url_overrides=overrides)
    assert rc == 0

    # Verify destination has the same HEAD
    dst_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=dst_bare, capture_output=True, text=True
    )
    src_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=src_bare, capture_output=True, text=True
    )
    assert dst_head.stdout.strip() == src_head.stdout.strip()
    assert len(dst_head.stdout.strip()) == 40
```

- [ ] **Step 2: Run the integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: All tests pass across all files.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end integration test with local bare repos"
```

---

## Task 11: Final Verification

**Files:** None (verification only).

- [ ] **Step 1: Run the full test suite one more time**

Run: `pytest -v`
Expected: All tests pass.

- [ ] **Step 2: Smoke-test the CLI manually**

Run:
```bash
python -m src.main --help 2>&1 || true
PYTHONPATH=. python -c "from src.main import main; print('imports ok')"
```
Expected: `imports ok` printed. (No `--help` flag in this version; that's fine.)

- [ ] **Step 3: Verify workflow YAML parses**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/sync.yml'))"`
Expected: No output, exit 0.

- [ ] **Step 4: Confirm no secrets in tracked files**

Run: `git grep -E '(ghp_|gho_|ghu_|ghs_|ghr_|cnb_|gt_)' || echo "no secrets found"`
Expected: `no secrets found` (or only inside `tests/` mocks — verify no real values).

- [ ] **Step 5: Tag the release**

```bash
git tag v0.1.0
git log --oneline
```
Expected: 11 commits visible in `git log`.

---

## Verification (end-to-end)

After implementing all tasks, verify by:

1. **Run all tests**: `pytest -v` — all green.
2. **Lint config**: `python -c "from src.config import load_config; cfg = load_config('config/sync.yaml'); print(cfg)"`
3. **Manual GitHub Actions dry-run**: create a real GitHub repo, push this code, configure at least `TOKEN_CNB` (since CNB is the most distinctive), and a small YAML config targeting a known test repo. Run via `workflow_dispatch` and verify the destination gets the new branch.
4. **Conflict scenario**: push a divergent commit to a target, then trigger sync — expect a non-zero exit and a clear error message in the workflow log.

## Self-Review Notes

- **Spec coverage**:
  - Multi-platform (GitHub/Gitee/CNB/GitCode) → Task 2, Task 3
  - SSH + PAT auth flexibility → Task 2, Task 3
  - Manual / dispatch / scheduled triggers → Task 8
  - YAML config + topology → Task 4
  - Conflict detection → Task 6
  - GitHub Secrets storage → Task 3, Task 8
  - One platform = one credential → Task 3 (env-driven)
  - auto_create reserved (not implemented) → Task 4 (config slot), Task 9 (docs)
  - Branches + tags (no releases) → Task 6 (tags sync deferred; see note below)
  - Private + public repos → inherent in SSH/PAT support

- **Gap noted**: `git_helper.py` and `sync.py` currently only push the single configured branch. The spec mentions tags sync. **This is deferred**: the spec's first paragraph says "branches" as the primary sync unit; tags are listed as sync content in §3.4. A follow-up task should add a `push_tags` helper. For this plan, only branch sync is implemented and tested. The `delete_remote` setting is also reserved for follow-up.

- **Placeholder scan**: no `TBD`/`TODO`/etc. in code blocks. All tests are written out. Commands and expected outputs are explicit.

- **Type consistency**: `Endpoint` is used everywhere with fields `(platform, owner, repo, branch, auth)`. `Credential` has `ssh_key` and `pat`. `build_url(platform, owner, repo, auth, token=None)`. `sync_topology_entry(entry, creds, work_dir, force_push, url_overrides)`. All match across tasks.
