"""Mirror strategy: force-push source onto target (existing behavior)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from src.git_helper import (
    GitError,
    clone_or_fetch,
    get_head_sha,
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
    """Standard mirror sync: bare-clone target, check conflict, push."""

    def __init__(
        self,
        force_push: bool = False,
    ) -> None:
        self.force_push = force_push

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
            pushed.append(target_url)

            return StrategyResult(
                success=True,
                targets_pushed=pushed,
                deleted=deleted,
                message="ok",
            )
        except (GitError, subprocess.CalledProcessError) as e:
            raise SyncError(f"mirror sync failed: {e}") from e
        finally:
            shutil.rmtree(target_bare_dir, ignore_errors=True)
