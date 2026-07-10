"""Rebase strategy: replay source commits on top of target, preserving target-specific files."""
from __future__ import annotations

import os
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
            _run(["git", "clone", target_url, str(rebase_dir)], cwd=self.work_dir, env=env)

            # 2. Add source remote and fetch
            _run(["git", "remote", "add", "source", str(source_dir)], cwd=rebase_dir, env=env)
            _run(["git", "fetch", "source", branch], cwd=rebase_dir, env=env)

            # 3. Backup protected files
            backups: dict[str, bytes] = {}
            for path in self.preserve_files:
                full = rebase_dir / path
                if full.exists():
                    backups[path] = full.read_bytes()

            # 4. Checkout + rebase
            _run(["git", "checkout", branch], cwd=rebase_dir, env=env)
            proc = subprocess.run(
                ["git", "rebase", f"source/{branch}"],
                cwd=rebase_dir, capture_output=True, text=True, env=env,
            )
            if proc.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], cwd=rebase_dir, capture_output=True, env=env)
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
                _run(["git", "add"] + restored, cwd=rebase_dir, env=env)
                _run(
                    ["git", "commit", "-m", f"restore target-specific files: {', '.join(restored)}"],
                    cwd=rebase_dir,
                    env=env,
                )

            # 7. Push
            _run(["git", "push", "--force", "origin", branch], cwd=rebase_dir, env=env)

            return StrategyResult(
                success=True,
                targets_pushed=[target_url],
                restored=restored,
                message="ok",
            )

        finally:
            shutil.rmtree(rebase_dir, ignore_errors=True)


def _run(args: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    """Run a command; raise RebaseError on failure."""
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RebaseError(
            f"command failed: {' '.join(args)}\n  stderr: {proc.stderr.strip()}"
        )
