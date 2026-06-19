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
