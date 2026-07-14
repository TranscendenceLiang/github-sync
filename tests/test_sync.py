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


def test_sync_topology_entry_multi_branch(tmp_path, make_local_repo):
    src_base = make_local_repo(commits=1, branch="main")
    src_bare = Path(src_base["bare"])
    src_work = Path(src_base["work"])
    env = os.environ.copy()
    env.update({"GIT_AUTHOR_NAME":"T","GIT_AUTHOR_EMAIL":"t@t","GIT_COMMITTER_NAME":"T","GIT_COMMITTER_EMAIL":"t@t"})
    subprocess.run(["git", "checkout", "-b", "develop"], cwd=src_work, check=True, env=env)
    (src_work / "dev.txt").write_text("dev")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "dev"], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "develop"], cwd=src_work, check=True, env=env)

    dst_bare = tmp_path / "dest.git"
    subprocess.run(["git", "init", "--bare", str(dst_bare)], check=True, capture_output=True)

    creds = {"github": Credential(ssh_key="k", pat=None),
             "gitee": Credential(ssh_key="k", pat=None)}
    entry = TopologyEntry(
        name="multi",
        source=Endpoint(platform="github", owner="o", repo="r", branches=["*"]),
        targets=[Endpoint(platform="gitee", owner="o", repo="r")],
    )

    result = sync_topology_entry(
        entry=entry, creds=creds, work_dir=tmp_path / "work",
        url_overrides={"github": str(src_bare), "gitee": str(dst_bare)},
        bypass_credentials=True,
    )

    assert result.success is True
    assert "main" in result.branches_synced
    assert "develop" in result.branches_synced
    assert subprocess.run(["git", "rev-parse", "main"], cwd=dst_bare, capture_output=True).returncode == 0
    assert subprocess.run(["git", "rev-parse", "develop"], cwd=dst_bare, capture_output=True).returncode == 0


def test_sync_topology_entry_multi_branch_partial_failure(tmp_path, make_local_repo):
    src_base = make_local_repo(commits=1, branch="main")
    src_bare = Path(src_base["bare"])
    src_work = Path(src_base["work"])
    env = os.environ.copy()
    env.update({"GIT_AUTHOR_NAME":"T","GIT_AUTHOR_EMAIL":"t@t","GIT_COMMITTER_NAME":"T","GIT_COMMITTER_EMAIL":"t@t"})
    subprocess.run(["git", "checkout", "-b", "develop"], cwd=src_work, check=True, env=env)
    (src_work / "dev.txt").write_text("dev")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "dev"], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "develop"], cwd=src_work, check=True, env=env)

    # Target has conflicting main
    dst_bare = tmp_path / "dest.git"
    subprocess.run(["git", "init", "--bare", str(dst_bare)], check=True, capture_output=True)
    dst_work = tmp_path / "dst_work"
    subprocess.run(["git", "clone", str(dst_bare), str(dst_work)], check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=dst_work, check=True, env=env)
    (dst_work / "conflict.txt").write_text("conflict")
    subprocess.run(["git", "add", "."], cwd=dst_work, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "tgt"], cwd=dst_work, check=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=dst_work, check=True, env=env)

    creds = {"github": Credential(ssh_key="k", pat=None),
             "gitee": Credential(ssh_key="k", pat=None)}
    entry = TopologyEntry(
        name="partial",
        source=Endpoint(platform="github", owner="o", repo="r", branches=["*"]),
        targets=[Endpoint(platform="gitee", owner="o", repo="r")],
    )

    result = sync_topology_entry(
        entry=entry, creds=creds, work_dir=tmp_path / "work",
        force_push=False,
        url_overrides={"github": str(src_bare), "gitee": str(dst_bare)},
        bypass_credentials=True,
    )

    assert "main" in [b for b, _ in result.branches_failed]
    assert "develop" in result.branches_synced


def test_sync_topology_entry_legacy_branch_unaffected(tmp_path, make_local_repo):
    src = make_local_repo(commits=2, branch="main")
    dst = make_local_repo(commits=0, branch="main")

    creds = {"github": Credential(ssh_key="k", pat=None),
             "gitee": Credential(ssh_key="k", pat=None)}
    entry = TopologyEntry(
        name="legacy",
        source=Endpoint(platform="github", owner="o", repo="r", branch="main"),
        targets=[Endpoint(platform="gitee", owner="o", repo="r", branch="main")],
    )

    result = sync_topology_entry(
        entry=entry, creds=creds, work_dir=tmp_path / "work",
        url_overrides={"github": str(src["bare"]), "gitee": str(dst["bare"])},
    )

    assert result.success is True
    assert result.branches_synced == ["main"]
    assert result.branches_failed == []
