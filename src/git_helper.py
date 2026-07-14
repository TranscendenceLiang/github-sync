"""Low-level git operations.

Wraps the git CLI for clone, fetch, push, and HEAD lookup. This module is
intentionally thin: SyncEngine composes these primitives.
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.credential import Credential

from src.config import ConfigError


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


def clone_or_fetch(
    url: str,
    dest: Path,
    branch: str | None = None,
    single_branch: bool = True,
) -> Path:
    """Clone the URL into dest, or fetch+checkout if dest already exists.

    When ``single_branch`` is True (default) and a ``branch`` is given,
    only that branch is fetched.  Set ``single_branch=False`` to fetch all
    branches (full clone).

    Always returns dest.
    """
    dest = Path(dest)
    if (dest / ".git").is_dir():
        if branch:
            _run(["git", "fetch", "origin", branch], cwd=dest)
            _run(["git", "checkout", branch], cwd=dest)
            _run(["git", "reset", "--hard", f"origin/{branch}"], cwd=dest)
        else:
            _run(["git", "fetch", "--all"], cwd=dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        args = ["git", "clone"]
        if single_branch and branch:
            args += ["--branch", branch, "--single-branch"]
        args += [url, str(dest)]
        _run(args)
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


def list_remote_branches(repo: Path, remote: str = "origin") -> list[str]:
    """Return remote branch names (without the ``remote/`` prefix).

    HEAD symrefs (``origin/HEAD -> origin/main``) are skipped. Returns an
    empty list if the remote has no branches or the lookup fails.
    """
    repo = Path(repo)
    proc = subprocess.run(
        ["git", "branch", "-r", "--list", f"{remote}/*"],
        cwd=repo, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return []
    branches: list[str] = []
    prefix = f"{remote}/"
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or " -> " in line:
            continue
        if line.startswith(prefix):
            branches.append(line[len(prefix):])
    return branches


def list_remote_branches_url(url: str) -> list[str]:
    """List branch names on a remote URL via ``git ls-remote --heads``.

    Unlike :func:`list_remote_branches`, this does not require a local clone
    and sees *every* branch on the remote (a single-branch clone would hide
    the rest). Returns an empty list on failure.
    """
    proc = subprocess.run(
        ["git", "ls-remote", "--heads", url],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return []
    branches: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        ref = line.split("\t")[-1]
        if ref.startswith("refs/heads/"):
            branches.append(ref[len("refs/heads/"):])
    return branches


def resolve_branches(netloc_patterns: list[str], url: str) -> list[str]:
    """Match remote branches against glob patterns.

    Returns sorted, deduplicated branch names. Raises ConfigError if no
    remote branches match any pattern.
    """
    all_remote = list_remote_branches_url(url)
    matched: set[str] = set()
    for pattern in netloc_patterns:
        for branch in all_remote:
            if fnmatch.fnmatch(branch, pattern):
                matched.add(branch)
    if not matched:
        raise ConfigError(
            f"no remote branches matched patterns {netloc_patterns} "
            f"(remote has {len(all_remote)} branch(es))"
        )
    return sorted(matched)


def delete_remote_branch(repo: Path, remote: str, branch: str) -> None:
    """Delete a branch on the given remote."""
    _run(["git", "push", "--delete", remote, branch], cwd=Path(repo))
