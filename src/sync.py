"""Sync engine: executes a single TopologyEntry (source -> [targets]).

For each topology entry:
  1. Resolve source/target URLs and credentials
  2. Clone or update source
  3. For each target:
     a. Clone or update target
     b. Compare HEAD SHAs
     c. If both have unique commits beyond a common ancestor -> raise SyncError
     d. Otherwise, push source branch to target
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import Endpoint, TopologyEntry
from src.git_helper import (
    GitError,
    clone_or_fetch,
    get_head_sha,
    push_branch,
)
from src.platform import build_url

if TYPE_CHECKING:
    from src.credential import Credential


class SyncError(Exception):
    """Raised when a sync task fails."""


@dataclass
class SyncResult:
    success: bool
    entry_name: str
    source: str
    targets_pushed: list[str]
    message: str = ""


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
        # No common ancestor; both have unique commits
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


def _resolve_credentials(endpoint: Endpoint, creds: dict[str, "Credential"]) -> str | None:
    """Pick the appropriate credential value for the endpoint's auth method."""
    cred = creds.get(endpoint.platform)
    if cred is None:
        return None
    if endpoint.auth == "pat":
        return cred.pat
    return cred.ssh_key


def sync_topology_entry(
    entry: TopologyEntry,
    creds: dict[str, "Credential"],
    work_dir: Path,
    force_push: bool = False,
    url_overrides: dict[str, str] | None = None,
) -> SyncResult:
    """Execute a single topology entry: fetch source, push to all targets.

    Args:
        entry: The TopologyEntry to execute.
        creds: Mapping platform -> Credential.
        work_dir: A working directory for clones.
        force_push: Whether to allow non-fast-forward pushes (from settings).
        url_overrides: Optional mapping platform -> URL. Used by tests to inject
            local bare repos. In production, URLs are built from build_url().

    Raises:
        SyncError: On any failure (missing creds, conflict, git errors).
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Check source credentials
    src_cred_value = _resolve_credentials(entry.source, creds)
    if entry.source.platform not in creds or not (
        (entry.source.auth == "pat" and src_cred_value)
        or (entry.source.auth == "ssh" and src_cred_value)
    ):
        raise SyncError(
            f"missing credentials for source platform {entry.source.platform!r}"
        )

    # Resolve source URL
    if url_overrides and entry.source.platform in url_overrides:
        source_url = url_overrides[entry.source.platform]
    else:
        source_url = build_url(
            entry.source.platform,
            entry.source.owner,
            entry.source.repo,
            entry.source.auth,
            token=src_cred_value,
        )

    source_clone_dir = work_dir / f"src_{entry.name}"
    try:
        clone_or_fetch(source_url, source_clone_dir, entry.source.branch)
    except GitError as e:
        raise SyncError(f"failed to fetch source: {e}") from e

    source_sha = get_head_sha(source_clone_dir, entry.source.branch)
    if source_sha is None:
        raise SyncError(
            f"source branch {entry.source.branch!r} not found on {entry.source.platform}"
        )

    pushed: list[str] = []

    for target in entry.targets:
        # Check target credentials
        tgt_cred_value = _resolve_credentials(target, creds)
        if target.platform not in creds or not (
            (target.auth == "pat" and tgt_cred_value)
            or (target.auth == "ssh" and tgt_cred_value)
        ):
            raise SyncError(
                f"missing credentials for target platform {target.platform!r}"
            )

        # Resolve target URL
        if url_overrides and target.platform in url_overrides:
            target_url = url_overrides[target.platform]
        else:
            target_url = build_url(
                target.platform,
                target.owner,
                target.repo,
                target.auth,
                token=tgt_cred_value,
            )

        target_clone_dir = work_dir / f"tgt_{entry.name}_{target.platform}"
        # We use a bare clone to fetch target state without checkout conflicts
        target_bare_dir = work_dir / f"tgtbare_{entry.name}_{target.platform}"
        try:
            clone_or_fetch(target_url, target_bare_dir, target.branch)
        except GitError as e:
            # If the target branch is missing (e.g. empty target repo), treat as
            # "no target SHA" and continue: this is a first-time sync, not a
            # conflict. We only re-raise on a real fetch failure (e.g. auth).
            stderr = str(e).lower()
            if "not found" in stderr or "couldn't find remote ref" in stderr:
                target_sha = None
            else:
                shutil.rmtree(target_bare_dir, ignore_errors=True)
                raise SyncError(
                    f"failed to fetch target {target.platform}:{target.owner}/{target.repo}: {e}"
                ) from e
        else:
            target_sha = get_head_sha(target_bare_dir, target.branch)

        # Check for conflict
        ancestor = _merge_base(source_clone_dir, source_sha, target_sha) if target_sha else None
        if check_conflict(source_sha, target_sha, ancestor):
            raise SyncError(
                f"conflict on entry {entry.name!r}: both source and target have "
                f"diverged (source={source_sha[:7]}, target={target_sha[:7] if target_sha else 'none'})"
            )

        # Push from source clone to target
        try:
            subprocess.run(
                ["git", "remote", "remove", "target"], cwd=source_clone_dir, capture_output=True
            )
            subprocess.run(
                ["git", "remote", "add", "target", target_url],
                cwd=source_clone_dir, capture_output=True, check=True
            )
            push_branch(source_clone_dir, "target", entry.source.branch, force=force_push)
            pushed.append(f"{target.platform}:{target.owner}/{target.repo}#{target.branch}")
        except GitError as e:
            raise SyncError(
                f"failed to push to {target.platform}:{target.owner}/{target.repo}: {e}"
            ) from e
        finally:
            shutil.rmtree(target_bare_dir, ignore_errors=True)

    return SyncResult(
        success=True,
        entry_name=entry.name,
        source=f"{entry.source.platform}:{entry.source.owner}/{entry.source.repo}#{entry.source.branch}",
        targets_pushed=pushed,
        message="ok",
    )
