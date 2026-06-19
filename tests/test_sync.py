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


def test_sync_topology_entry_empty_target(tmp_path, make_local_repo):
    """First-time sync: source has commits, target branch does not exist yet."""
    src = make_local_repo(commits=2, branch="main")
    # Empty target: bare repo with NO commits at all on `main`
    dst_bare = tmp_path / "empty_dst.git"
    subprocess.run(["git", "init", "--bare", str(dst_bare)], check=True, capture_output=True)

    src_bare = Path(src["bare"])

    creds = {
        "github": Credential(ssh_key="k", pat=None),
        "gitee": Credential(ssh_key="k", pat=None),
    }
    entry = TopologyEntry(
        name="first-sync",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main", auth="ssh"),
        targets=[Endpoint(platform="gitee", owner="o", repo="r", branch="main", auth="ssh")],
    )

    result = sync_topology_entry(
        entry=entry,
        creds=creds,
        work_dir=tmp_path / "work",
        url_overrides={"github": str(src_bare), "gitee": str(dst_bare)},
        bypass_credentials=True,
    )
    assert result.success is True

    # Verify the empty target now has the source's HEAD
    dst_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=dst_bare, capture_output=True, text=True
    )
    src_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=src_bare, capture_output=True, text=True
    )
    assert dst_head.stdout.strip() == src_head.stdout.strip()
