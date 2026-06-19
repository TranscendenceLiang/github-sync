"""Shared pytest fixtures."""
import os
import subprocess
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
    """Factory: create a local bare repo (acts as 'remote') and a working clone.

    When called multiple times within one test, each call automatically gets
    a unique subdirectory under tmp_path so that subsequent calls don't
    collide with leftover state from earlier ones (Windows file locks and
    read-only git objects make in-place reuse unsafe).
    """
    counter = {"i": 0}

    def _make(name="repo", commits=1, branch="main"):
        counter["i"] += 1
        # Unique subdir per call so multiple calls with the same `name` don't collide.
        unique = tmp_path / f"make_{counter['i']:03d}"
        unique.mkdir(parents=True, exist_ok=True)

        # Create bare remote
        bare = unique / f"{name}.git"
        subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

        # Create working clone
        work = unique / name
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

        if commits > 0:
            subprocess.run(["git", "push", "-u", "origin", branch], cwd=work, check=True, capture_output=True, env=env)

        return {"bare": str(bare), "work": str(work), "branch": branch}

    return _make