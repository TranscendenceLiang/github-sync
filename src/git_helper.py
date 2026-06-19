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
