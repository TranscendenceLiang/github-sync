"""Abstract base for all sync strategies + shared utilities (moved from sync.py)."""
from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


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
