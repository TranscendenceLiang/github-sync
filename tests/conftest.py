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
