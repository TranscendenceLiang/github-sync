# Rebase 同步模式实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 mirror 模式基础上，新增 rebase 同步模式，将源提交在目标当前状态之上重放，并通过保护文件列表保留目标特有配置。

**Architecture:** 策略模式（SyncStrategy ABC），MirrorStrategy 封装现有 force-push 逻辑，RebaseStrategy 实现 rebase + 文件保护。`sync_topology_entry` 根据 `mode` 参数派发到对应策略。

**Tech Stack:** Python 3.11, git CLI, pytest

## Global Constraints

- `mode` 仅允许两个值：`"mirror"` | `"rebase"`
- Rebase 模式下忽略 `force_push` 和 `delete_remote` 配置（文档中说明）
- `preserve_files` 在 topology 条目级为**覆盖式**（不合并全局列表）
- Rebase 冲突时跳过该条目（不中止整个流程）
- Rebase 模式下 push 始终 `--force`
- 保护文件恢复使用字节级比对，仅在内容变化时创建 restore commit

---

### Task 1: Config — 新增 mode + preserve_files 字段

**Files:**
- Modify: `src/config.py` (dataclasses + parser)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `SyncSettings.mode: str = "mirror"`, `SyncSettings.preserve_files: list[str] | None = None`
- Produces: `TopologyEntry.mode: str | None = None`, `TopologyEntry.preserve_files: list[str] | None = None`
- Produces: config validation: mode 必须是 "mirror" 或 "rebase"，否则 ConfigError

- [ ] **Step 1: 更新 dataclass 定义**

```python
# src/config.py

@dataclass
class SyncSettings:
    auto_create: bool = False
    force_push: bool = False
    delete_remote: bool = False
    mode: str = "mirror"
    preserve_files: list[str] | None = None

@dataclass
class TopologyEntry:
    name: str
    source: Endpoint
    targets: list[Endpoint] = field(default_factory=list)
    mode: str | None = None
    preserve_files: list[str] | None = None
```

- [ ] **Step 2: 更新 `_parse_settings` 解析 mode + preserve_files**

```python
# src/config.py, _parse_settings

def _parse_settings(data: Any) -> SyncSettings:
    if data is None:
        return SyncSettings()
    if not isinstance(data, dict):
        raise ConfigError("settings must be a mapping")
    mode = str(data.get("mode", "mirror")).lower()
    if mode not in ("mirror", "rebase"):
        raise ConfigError(f"settings.mode must be 'mirror' or 'rebase', got {mode!r}")
    pf_raw = data.get("preserve_files")
    preserve_files = None
    if pf_raw is not None:
        if not isinstance(pf_raw, list) or not all(isinstance(f, str) for f in pf_raw):
            raise ConfigError("settings.preserve_files must be a list of strings")
        preserve_files = [str(f) for f in pf_raw]
    return SyncSettings(
        auto_create=bool(data.get("auto_create", False)),
        force_push=bool(data.get("force_push", False)),
        delete_remote=bool(data.get("delete_remote", False)),
        mode=mode,
        preserve_files=preserve_files,
    )
```

- [ ] **Step 3: 更新 `_parse_entry` 解析条目级 mode + preserve_files**

```python
# src/config.py, _parse_entry

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

    mode = data.get("mode")
    if mode is not None:
        mode = str(mode).lower()
        if mode not in ("mirror", "rebase"):
            raise ConfigError(f"topology[{name}].mode must be 'mirror' or 'rebase', got {mode!r}")

    pf_raw = data.get("preserve_files")
    preserve_files = None
    if pf_raw is not None:
        if not isinstance(pf_raw, list) or not all(isinstance(f, str) for f in pf_raw):
            raise ConfigError(f"topology[{name}].preserve_files must be a list of strings")
        preserve_files = [str(f) for f in pf_raw]

    return TopologyEntry(name=name, source=source, targets=targets, mode=mode, preserve_files=preserve_files)
```

- [ ] **Step 4: 写测试**

```python
# tests/test_config.py, append

def test_load_config_with_mode_and_preserve(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            mode: rebase
            preserve_files:
              - .cnb.yml
          topology:
            - name: "x"
              mode: rebase
              preserve_files:
                - .cnb.yml
                - Dockerfile
              source:
                platform: github
                owner: o
                repo: r
                branch: main
              targets:
                - platform: cnb
                  owner: o
                  repo: r
                  branch: main
    """))
    cfg = load_config(cfg_file)
    assert cfg.settings.mode == "rebase"
    assert cfg.settings.preserve_files == [".cnb.yml"]
    assert cfg.topology[0].mode == "rebase"
    assert cfg.topology[0].preserve_files == [".cnb.yml", "Dockerfile"]

def test_load_config_mode_default_mirror(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source: {platform: github, owner: o, repo: r, branch: main}
              targets: [{platform: gitee, owner: o, repo: r, branch: main}]
    """))
    cfg = load_config(cfg_file)
    assert cfg.settings.mode == "mirror"
    assert cfg.topology[0].mode is None

def test_load_config_invalid_mode_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            mode: merge
          topology: []
    """))
    with pytest.raises(ConfigError, match="mode"):
        load_config(cfg_file)

def test_load_config_invalid_entry_mode_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              mode: foo
              source: {platform: github, owner: o, repo: r, branch: main}
              targets: [{platform: gitee, owner: o, repo: r, branch: main}]
    """))
    with pytest.raises(ConfigError, match="mode"):
        load_config(cfg_file)

def test_load_config_preserve_files_not_list_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            preserve_files: ".cnb.yml"
          topology: []
    """))
    with pytest.raises(ConfigError, match="preserve_files"):
        load_config(cfg_file)
```

- [ ] **Step 5: 运行测试验证通过**

```bash
pytest tests/test_config.py -v
Expected: all tests PASS
```

- [ ] **Step 6: 提交**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat(config): add mode and preserve_files fields"
```

---

### Task 2: 重构 — 将公共函数移到 base + 创建策略基础设施

> ⚠️ **需要先完成 Task 1**（config 中新字段在此任务才使用）

**Files:**
- Create: `src/strategies/__init__.py`
- Create: `src/strategies/base.py` — **包含从 `sync.py` 移入的 `SyncError`、`check_conflict`、`_merge_base`**
- Create: `src/strategies/mirror.py`
- Modify: `src/sync.py` — 从 `base.py` 导入公共函数（re-export 保持向后兼容）
- Test: `tests/test_sync.py` — 现有测试验证 backward compat

**Interfaces:**
- Produces: `SyncError` (moved from sync.py)
- Produces: `check_conflict(source_sha, target_sha, ancestor_sha) → bool` (moved from sync.py)
- Produces: `_merge_base(local_repo, ref_a, ref_b) → str | None` (moved from sync.py)
- Produces: `StrategyResult` dataclass
- Produces: `SyncStrategy` ABC with `sync(*, source_dir, target_url, branch) → StrategyResult`
- Produces: `MirrorStrategy(force_push, delete_remote)` — extracted mirror logic
- Consumes: `sync_topology_entry` accepts `mode: str = "mirror"` param

> **为什么移动 `SyncError` / `check_conflict` / `_merge_base`？** 避免循环导入：`sync.py` → `strategies/mirror.py` → `sync.py`。

- [ ] **Step 1: 创建策略包和基类（含从 sync.py 移入的公共函数）**

```python
# src/strategies/__init__.py
"""Sync strategy implementations: mirror, rebase, and future strategies."""
```

```python
# src/strategies/base.py
"""Abstract base for all sync strategies + shared utilities (moved from sync.py)."""
from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SyncError(Exception):
    """Raised when a sync task fails."""


@dataclass
class StrategyResult:
    success: bool
    targets_pushed: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    skipped: bool = False
    restored: list[str] = field(default_factory=list)
    message: str = ""


class SyncStrategy(ABC):
    @abstractmethod
    def sync(
        self,
        *,
        source_dir: Path,
        target_url: str,
        branch: str,
    ) -> StrategyResult:
        ...


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
```

- [ ] **Step 2: 更新 `sync.py` 从 `base.py` 导入并 re-export**

```python
# src/sync.py 顶部替换原有 SyncError / check_conflict / _merge_base 定义

from src.strategies.base import (
    SyncError,
    StrategyResult,
    SyncStrategy,
    check_conflict,
    _merge_base,
)

# 保持向后兼容 — 现有测试 from src.sync import SyncError, check_conflict 仍可用
# SyncError 和 check_conflict 现在从 strategies.base 导入，但它们仍可通过 src.sync 访问
```

删除 `sync.py` 中原有的 `SyncError` 类、`check_conflict` 函数、`_merge_base` 函数定义（它们已移到 `strategies/base.py`）。

- [ ] **Step 3: 创建 MirrorStrategy**

```python
# src/strategies/mirror.py
"""Mirror strategy: force-push source onto target (existing behavior)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from src.git_helper import (
    GitError,
    clone_or_fetch,
    delete_remote_branch,
    get_head_sha,
    list_remote_branches_url,
    push_branch,
)
from src.strategies.base import (
    SyncError,
    StrategyResult,
    SyncStrategy,
    check_conflict,
    _merge_base,
)


def _sanitize_url(url: str) -> str:
    """Turn a URL into a short safe directory name."""
    safe = re.sub(r"[^a-zA-Z0-9]", "_", url)
    return safe[-60:] if len(safe) > 60 else safe


class MirrorStrategy(SyncStrategy):
    """Standard mirror sync: bare-clone target, check conflict, push.

    When *force_push* is True the conflict check is skipped. When
    *delete_remote* is True, any pre-existing target branch other than the
    one being synced is deleted from the target after the push.
    """

    def __init__(
        self,
        force_push: bool = False,
        delete_remote: bool = False,
    ) -> None:
        self.force_push = force_push
        self.delete_remote = delete_remote

    def sync(
        self,
        *,
        source_dir: Path,
        target_url: str,
        branch: str,
    ) -> StrategyResult:
        pushed: list[str] = []
        deleted: list[str] = []

        target_bare_dir = source_dir.parent / f"tgtbare_{_sanitize_url(target_url)}"
        try:
            try:
                clone_or_fetch(target_url, target_bare_dir, branch)
            except GitError as e:
                stderr = str(e).lower()
                if "not found" in stderr or "couldn't find remote ref" in stderr:
                    target_sha = None
                else:
                    raise SyncError(f"failed to fetch target: {e}") from e
            else:
                target_sha = get_head_sha(target_bare_dir, branch)

            # Capture branches before push (for delete_remote)
            target_branches_before = (
                list_remote_branches_url(target_url) if self.delete_remote else []
            )

            # Conflict check (skipped when force_push)
            source_sha = get_head_sha(source_dir, branch)
            ancestor = _merge_base(source_dir, source_sha or branch, target_sha) if target_sha else None
            if not self.force_push and check_conflict(source_sha, target_sha, ancestor):
                raise SyncError(
                    f"conflict: both source and target have diverged "
                    f"(source={source_sha[:7] if source_sha else 'none'}, "
                    f"target={target_sha[:7] if target_sha else 'none'})"
                )

            # Push
            subprocess.run(["git", "remote", "remove", "target"], cwd=source_dir, capture_output=True)
            subprocess.run(["git", "remote", "add", "target", target_url], cwd=source_dir, capture_output=True, check=True)
            push_branch(source_dir, "target", branch, force=self.force_push)

            # delete_remote cleanup
            if self.delete_remote and target_branches_before:
                for tb in target_branches_before:
                    if tb == branch:
                        continue
                    try:
                        delete_remote_branch(source_dir, "target", tb)
                        deleted.append(tb)
                    except GitError as e:
                        raise SyncError(f"failed to delete stale branch {tb!r}: {e}") from e

            return StrategyResult(
                success=True,
                targets_pushed=[target_url],
                deleted=deleted,
                message="ok",
            )
        except (GitError, subprocess.CalledProcessError) as e:
            raise SyncError(f"mirror sync failed: {e}") from e
        finally:
            shutil.rmtree(target_bare_dir, ignore_errors=True)
```

- [ ] **Step 4: 更新 `sync_topology_entry` — 接受 mode 参数并派发**

```python
# src/sync.py

def _resolve_strategy(
    mode: str,
    force_push: bool = False,
    delete_remote: bool = False,
    preserve_files: list[str] | None = None,
    work_dir: Path | None = None,
) -> SyncStrategy:
    if mode == "mirror":
        return MirrorStrategy(force_push=force_push, delete_remote=delete_remote)
    # "rebase" will be handled in Task 3
    raise SyncError(f"unknown sync mode: {mode}")

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
    # ... 1-5: source creds, URL, clone, SHA (不变) ...

    strategy = _resolve_strategy(mode, force_push=force_push, delete_remote=delete_remote,
                                  preserve_files=preserve_files, work_dir=work_dir)

    pushed: list[str] = []
    deleted: list[str] = []

    for target in entry.targets:
        # target creds check (不变) ...
        # target URL resolve (不变) ...

        # 委托策略执行
        result = strategy.sync(
            source_dir=source_clone_dir,
            target_url=target_url,
            branch=entry.source.branch,
        )
        pushed.extend(result.targets_pushed)
        deleted.extend(result.deleted)

    return SyncResult(
        success=True,
        entry_name=entry.name,
        source=f"{entry.source.platform}:{entry.source.owner}/{entry.source.repo}#{entry.source.branch}",
        targets_pushed=pushed,
        deleted=deleted,
        message="ok",
    )
```

- [ ] **Step 5: 运行测试验证不破坏**

```bash
pytest tests/test_sync.py -v
Expected: all tests PASS (mode defaults to "mirror", MirrorStrategy has same behavior as before)
```

- [ ] **Step 6: 提交**

```bash
git add src/strategies/ src/sync.py
git commit -m "refactor(sync): extract MirrorStrategy via strategy pattern, move shared functions to base"
```

---

### Task 3: RebaseStrategy

**Files:**
- Create: `src/strategies/rebase.py`
- Test: `tests/test_rebase_strategy.py`

**Interfaces:**
- Produces: `RebaseStrategy(preserve_files, work_dir)` implements `SyncStrategy.sync()`
- Produces: Complete rebase flow with file preservation

- [ ] **Step 1: 写测试 — rebase 成功路径**

```python
# tests/test_rebase_strategy.py
"""Tests for RebaseStrategy."""
import os
import subprocess
from pathlib import Path

import pytest

from src.config import Endpoint
from src.strategies.rebase import RebaseStrategy


def test_rebase_strategy_happy_path(tmp_path):
    """Source has new commits, target has a unique file; rebase preserves it."""
    # Setup: source repo with commits
    src_bare = tmp_path / "src.git"
    subprocess.run(["git", "init", "--bare", str(src_bare)], check=True, capture_output=True)
    src_work = tmp_path / "src_work"
    subprocess.run(["git", "clone", str(src_bare), str(src_work)], check=True, capture_output=True)

    env = os.environ.copy()
    env.update({"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t.com",
                "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t.com"})

    (src_work / "README.md").write_text("# source")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=src_work, check=True, capture_output=True, env=env)

    # New source-only commit
    (src_work / "new.txt").write_text("new")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "new"], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "origin", "main"], cwd=src_work, check=True, capture_output=True, env=env)

    # Setup: target repo with unique file .cnb.yml
    tgt_bare = tmp_path / "tgt.git"
    subprocess.run(["git", "init", "--bare", str(tgt_bare)], check=True, capture_output=True)
    tgt_work = tmp_path / "tgt_work"
    subprocess.run(["git", "clone", str(tgt_bare), str(tgt_work)], check=True, capture_output=True)

    (tgt_work / "README.md").write_text("# target")
    (tgt_work / ".cnb.yml").write_text("pipeline: foo")
    subprocess.run(["git", "add", "."], cwd=tgt_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "target init"], cwd=tgt_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=tgt_work, check=True, capture_output=True, env=env)

    # Execute: clone source to a "fetched" directory (as sync_topology_entry does)
    src_clone = tmp_path / "src_clone"
    subprocess.run(["git", "clone", str(src_bare), str(src_clone)], check=True, capture_output=True)

    strategy = RebaseStrategy(
        preserve_files=[".cnb.yml"],
        work_dir=tmp_path / "rebase_work",
    )

    result = strategy.sync(
        source_dir=src_clone,
        target_url=str(tgt_bare),
        branch="main",
    )

    assert result.success is True
    assert result.skipped is False
    # .cnb.yml should still exist on target
    tgt_check = tmp_path / "tgt_check"
    subprocess.run(["git", "clone", str(tgt_bare), str(tgt_check)], check=True, capture_output=True)
    assert (tgt_check / ".cnb.yml").exists()
    assert (tgt_check / ".cnb.yml").read_text() == "pipeline: foo"
    # Source's new commit should be present
    assert (tgt_check / "new.txt").read_text() == "new"
    # README from source (rebase replays source on top of target)
    # After rebase: we start from target's state (has "# target"),
    # then replay source's commits on top. Source's "init" changed README to "# source".
    # Source's commit order: init (# source), new (new.txt)
    # So after rebase, README should be "# source" (source version wins via replay)
    assert (tgt_check / "README.md").read_text() == "# source"
```

- [ ] **Step 2: 写测试 — rebase 冲突时跳过**

```python
# tests/test_rebase_strategy.py, append

def test_rebase_strategy_conflict_skips(tmp_path):
    """When rebase has conflicts, strategy returns skipped=True, no push."""
    # Source modifies the same file that target also modified -> conflict
    src_bare = tmp_path / "src.git"
    subprocess.run(["git", "init", "--bare", str(src_bare)], check=True, capture_output=True)
    src_work = tmp_path / "src_work"
    subprocess.run(["git", "clone", str(src_bare), str(src_work)], check=True, capture_output=True)

    env = os.environ.copy()
    env.update({"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t.com",
                "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t.com"})

    (src_work / "conflict.txt").write_text("source version")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "src commit"], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=src_work, check=True, capture_output=True, env=env)

    # Target has conflicting version of same file
    tgt_bare = tmp_path / "tgt.git"
    subprocess.run(["git", "init", "--bare", str(tgt_bare)], check=True, capture_output=True)
    tgt_work = tmp_path / "tgt_work"
    subprocess.run(["git", "clone", str(tgt_bare), str(tgt_work)], check=True, capture_output=True)

    (tgt_work / "conflict.txt").write_text("target version")
    subprocess.run(["git", "add", "."], cwd=tgt_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "tgt commit"], cwd=tgt_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=tgt_work, check=True, capture_output=True, env=env)

    src_clone = tmp_path / "src_clone"
    subprocess.run(["git", "clone", str(src_bare), str(src_clone)], check=True, capture_output=True)

    strategy = RebaseStrategy(work_dir=tmp_path / "rebase_work")
    result = strategy.sync(
        source_dir=src_clone,
        target_url=str(tgt_bare),
        branch="main",
    )
    assert result.success is False
    assert result.skipped is True
```

- [ ] **Step 3: 写测试 — 保护文件被源删除后恢复**

```python
# tests/test_rebase_strategy.py, append

def test_rebase_strategy_preserve_file_restored(tmp_path):
    """Source deletes a file that is in preserve_files; strategy restores it."""
    src_bare = tmp_path / "src.git"
    subprocess.run(["git", "init", "--bare", str(src_bare)], check=True, capture_output=True)
    src_work = tmp_path / "src_work"
    subprocess.run(["git", "clone", str(src_bare), str(src_work)], check=True, capture_output=True)

    env = os.environ.copy()
    env.update({"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t.com",
                "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t.com"})

    # Source has both README and .cnb.yml originally
    (src_work / "README.md").write_text("# proj")
    (src_work / ".cnb.yml").write_text("pipeline: old")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=src_work, check=True, capture_output=True, env=env)

    # Source deletes .cnb.yml in a later commit
    subprocess.run(["git", "rm", ".cnb.yml"], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "remove cnb"], cwd=src_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "origin", "main"], cwd=src_work, check=True, capture_output=True, env=env)

    # Target still has .cnb.yml with different content
    tgt_bare = tmp_path / "tgt.git"
    subprocess.run(["git", "init", "--bare", str(tgt_bare)], check=True, capture_output=True)
    tgt_work = tmp_path / "tgt_work"
    subprocess.run(["git", "clone", str(tgt_bare), str(tgt_work)], check=True, capture_output=True)

    (tgt_work / "README.md").write_text("# target")
    (tgt_work / ".cnb.yml").write_text("pipeline: custom")
    subprocess.run(["git", "add", "."], cwd=tgt_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "target init"], cwd=tgt_work, check=True, capture_output=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=tgt_work, check=True, capture_output=True, env=env)

    src_clone = tmp_path / "src_clone"
    subprocess.run(["git", "clone", str(src_bare), str(src_clone)], check=True, capture_output=True)

    strategy = RebaseStrategy(
        preserve_files=[".cnb.yml"],
        work_dir=tmp_path / "rebase_work",
    )
    result = strategy.sync(
        source_dir=src_clone,
        target_url=str(tgt_bare),
        branch="main",
    )

    assert result.success is True
    assert ".cnb.yml" in result.restored

    # Verify target has the original .cnb.yml content
    tgt_check = tmp_path / "tgt_check"
    subprocess.run(["git", "clone", str(tgt_bare), str(tgt_check)], check=True, capture_output=True)
    assert (tgt_check / ".cnb.yml").read_text() == "pipeline: custom"
```

- [ ] **Step 4: 实现 RebaseStrategy**

```python
# src/strategies/rebase.py
"""Rebase strategy: replay source commits on top of target, preserving target-specific files."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from src.strategies.base import StrategyResult, SyncStrategy


class RebaseError(Exception):
    """Raised when a rebase operation fails irrecoverably."""


def _sanitize_url(url: str) -> str:
    """Turn a URL into a short safe directory name."""
    import re
    safe = re.sub(r"[^a-zA-Z0-9]", "_", url)
    return safe[-60:] if len(safe) > 60 else safe


class RebaseStrategy(SyncStrategy):
    """Rebase source onto target, preserving target-specific files.

    The strategy:
    1. Full-clone the target into a temp working directory
    2. Add source as a remote, fetch source/<branch>
    3. Backup *preserve_files* before rebase
    4. ``git rebase source/<branch>`` (skip on conflict)
    5. Restore backed-up files if changed/deleted
    6. ``git push --force``  the rebased branch to target

    ``force_push`` and ``delete_remote`` settings are ignored — push is
    always ``--force`` (rebase rewrites history) and branch pruning is
    out of scope for this strategy.
    """

    def __init__(
        self,
        preserve_files: list[str] | None = None,
        work_dir: Path | None = None,
    ) -> None:
        self.preserve_files = preserve_files or []
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()

    def sync(
        self,
        *,
        source_dir: Path,
        target_url: str,
        branch: str,
    ) -> StrategyResult:
        import os
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "Git Sync",
            "GIT_AUTHOR_EMAIL": "git-sync@local",
            "GIT_COMMITTER_NAME": "Git Sync",
            "GIT_COMMITTER_EMAIL": "git-sync@local",
        })

        rebase_dir = self.work_dir / f"rebase_{_sanitize_url(target_url)}"
        if rebase_dir.exists():
            shutil.rmtree(rebase_dir)
        rebase_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Clone target (full clone, need working tree for rebase)
            _run(["git", "clone", target_url, str(rebase_dir)], cwd=self.work_dir)

            # 2. Add source remote and fetch
            _run(["git", "remote", "add", "source", str(source_dir)], cwd=rebase_dir)
            _run(["git", "fetch", "source", branch], cwd=rebase_dir)

            # 3. Backup protected files
            backups: dict[str, bytes] = {}
            for path in self.preserve_files:
                full = rebase_dir / path
                if full.exists():
                    backups[path] = full.read_bytes()

            # 4. Checkout + rebase
            _run(["git", "checkout", branch], cwd=rebase_dir)
            proc = subprocess.run(
                ["git", "rebase", f"source/{branch}"],
                cwd=rebase_dir, capture_output=True, text=True,
            )
            if proc.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], cwd=rebase_dir, capture_output=True)
                return StrategyResult(
                    success=False,
                    skipped=True,
                    message=f"rebase conflict on {branch}: {proc.stderr.strip()}",
                )

            # 5. Restore protected files
            restored: list[str] = []
            for path, content in backups.items():
                full = rebase_dir / path
                if not full.exists() or full.read_bytes() != content:
                    full.parent.mkdir(parents=True, exist_ok=True)
                    full.write_bytes(content)
                    restored.append(path)

            # 6. Commit restored files (if any)
            if restored:
                _run(["git", "add"] + restored, cwd=rebase_dir)
                _run(
                    ["git", "commit", "-m", f"restore target-specific files: {', '.join(restored)}"],
                    cwd=rebase_dir,
                )

            # 7. Push
            _run(["git", "remote", "add", "target", target_url], cwd=rebase_dir)
            _run(["git", "push", "--force", "target", branch], cwd=rebase_dir)

            return StrategyResult(
                success=True,
                targets_pushed=[target_url],
                restored=restored,
                message="ok",
            )

        finally:
            shutil.rmtree(rebase_dir, ignore_errors=True)


def _run(args: list[str], cwd: Path | None = None) -> None:
    """Run a command; raise RebaseError on failure."""
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RebaseError(
            f"command failed: {' '.join(args)}\n  stderr: {proc.stderr.strip()}"
        )
```

- [ ] **Step 5: 在 `_resolve_strategy` 中注册 rebase**

```python
# src/sync.py, _resolve_strategy

from src.strategies.rebase import RebaseStrategy

def _resolve_strategy(
    mode: str,
    force_push: bool = False,
    delete_remote: bool = False,
    preserve_files: list[str] | None = None,
    work_dir: Path | None = None,
) -> SyncStrategy:
    if mode == "mirror":
        return MirrorStrategy(force_push=force_push, delete_remote=delete_remote)
    elif mode == "rebase":
        return RebaseStrategy(preserve_files=preserve_files, work_dir=work_dir)
    raise SyncError(f"unknown sync mode: {mode}")
```

更新 `sync_topology_entry` 传递 `work_dir` 给 `_resolve_strategy`：

```python
strategy = _resolve_strategy(
    mode,
    force_push=force_push,
    delete_remote=delete_remote,
    preserve_files=preserve_files,
    work_dir=work_dir,
)
```

- [ ] **Step 6: 运行测试**

```bash
pytest tests/test_rebase_strategy.py -v
Expected: all tests PASS
```

```bash
pytest tests/test_sync.py -v
Expected: all tests PASS (backward compatibility)
```

- [ ] **Step 7: 提交**

```bash
git add src/strategies/rebase.py src/sync.py tests/test_rebase_strategy.py
git commit -m "feat(sync): add RebaseStrategy with file preservation"
```

---

### Task 4: 集成到 main.py + 更新示例配置

**Files:**
- Modify: `src/main.py`
- Modify: `config/sync.yaml`

**Interfaces:**
- Consumes: `sync_topology_entry` now accepts `mode` and `preserve_files`

- [ ] **Step 1: 更新 `main.py` 传递新参数**

```python
# src/main.py, run_sync()

for entry in cfg.topology:
    # Resolve mode: entry-level overrides global
    mode = entry.mode or cfg.settings.mode
    preserve_files = entry.preserve_files if entry.preserve_files is not None else cfg.settings.preserve_files

    print(f"[INFO] syncing topology entry: {entry.name} (mode={mode})")
    try:
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
        )
```

- [ ] **Step 2: 更新 `config/sync.yaml` 示例**

```yaml
# config/sync.yaml
sync:
  settings:
    auto_create: false
    force_push: true
    delete_remote: true
    mode: mirror                    # 全局默认: mirror | rebase
    preserve_files:                 # 全局默认保护文件列表（rebase 模式使用）
      - .cnb.yml

  topology:
    - name: "github-qwenpaw-to-cnb"
      source:
        platform: github
        owner: TranscendenceLiang
        repo: QwenPaw
        branch: main
        auth: pat
      targets:
        - platform: cnb
          owner: TranscendenceLiang
          repo: test
          branch: main
          auth: pat

    - name: "github-ciphertalk-to-cnb"
      mode: rebase                   # 条目级覆盖: 使用 rebase
      preserve_files:                # 覆盖全局: 仅保护以下文件
        - .cnb.yml
        - Dockerfile
      source:
        platform: github
        owner: ILoveBingLu
        repo: CipherTalk
        branch: main
        auth: pat
      targets:
        - platform: cnb
          owner: TranscendenceLiang
          repo: CipherTalk
          branch: main
          auth: pat
```

- [ ] **Step 3: 提交**

```bash
git add src/main.py config/sync.yaml
git commit -m "feat(main): wire up mode and preserve_files, update config example"
```

---

### Task 5: 文档

**Files:**
- Modify: `docs/README.md`

- [ ] **Step 1: 在 Config Schema 中补充 mode + preserve_files**

在 `docs/README.md` 的 Config Schema 示例中添加新字段：

```yaml
sync:
  settings:
    auto_create: false
    force_push: false
    delete_remote: false
    mode: mirror                  # mirror | rebase
    preserve_files:               # rebase 模式保留的目标特有文件
      - .cnb.yml

  topology:
    - name: "github-to-cnb"
      mode: rebase                # 覆盖全局设置（可选）
      preserve_files:             # 覆盖全局列表（可选）
        - .cnb.yml
        - Dockerfile
      source:
        platform: github
        owner: myorg
        repo: myproject
        branch: main
      targets:
        - platform: cnb
          owner: myorg
          repo: myproject
          branch: main
```

- [ ] **Step 2: 在 Behavior 章节补充 rebase 模式说明**

添加到 `docs/README.md` 的 Behavior 章节：

```markdown
### Rebase 模式

设置 `mode: rebase` 后，源的提交会在目标当前状态之上重放（rebase），而非直接覆盖。

**适用场景：** 从 GitHub 同步到 CNB 时保留 `.cnb.yml` 等平台特有配置文件。

**行为：**
- 源的提交按顺序应用到目标分支之上
- 目标特有的文件（源没有的文件）自然保留
- `preserve_files` 列表中的文件会在 rebase 前后做备份/恢复，防止源意外删除或覆盖
- Rebase 冲突时跳过该条目，不中止整体流程
- **注意：** `force_push` 和 `delete_remote` 设置在 rebase 模式下被忽略 — push 始终使用 `--force`（因为 rebase 改写历史），分支清理由 rebase 机制自身保证。
```

- [ ] **Step 3: 提交**

```bash
git add docs/README.md
git commit -m "docs: add rebase mode documentation"
```
