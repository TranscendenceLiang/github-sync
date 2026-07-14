"""Sync engine: executes a single TopologyEntry (source -> [targets]).

For each topology entry:
  1. Resolve source/target URLs and credentials
  2. Clone or update source
  3. Delegate to the appropriate SyncStrategy (mirror, rebase, etc.) for each target
"""
from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import Endpoint, TopologyEntry
from src.git_helper import (
    GitError,
    clone_or_fetch,
    get_head_sha,
    list_remote_branches_url,
    delete_remote_branch,
    resolve_branches,
)
from src.platform import build_url
from src.strategies.base import (
    SyncError,
    StrategyResult,
    SyncStrategy,
    check_conflict,
    _merge_base,
)
from src.auto_create import CreateRepoRequest, create_repo, CreateRepoError
import src.release_sync as _release_sync
from src.strategies.mirror import MirrorStrategy
from src.strategies.rebase import RebaseStrategy

if TYPE_CHECKING:
    from src.credential import Credential


@dataclass
class SyncResult:
    success: bool
    entry_name: str
    source: str
    targets_pushed: list[str]
    deleted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    message: str = ""
    release_result: "ReleaseSyncResult | None" = None
    branches_synced: list[str] = field(default_factory=list)
    branches_failed: list[tuple[str, str]] = field(default_factory=list)


def _resolve_credentials(endpoint: Endpoint, creds: dict[str, "Credential"]) -> str | None:
    """Pick the appropriate credential value for the endpoint's auth method."""
    cred = creds.get(endpoint.platform)
    if cred is None:
        return None
    if endpoint.auth == "pat":
        return cred.pat
    return cred.ssh_key


def _resolve_strategy(
    mode: str,
    force_push: bool = False,
    preserve_files: list[str] | None = None,
    work_dir: Path | None = None,
) -> SyncStrategy:
    """Create the appropriate SyncStrategy for the given mode."""
    if mode == "mirror":
        return MirrorStrategy(force_push=force_push)
    elif mode == "rebase":
        return RebaseStrategy(preserve_files=preserve_files, work_dir=work_dir)
    raise SyncError(f"unknown sync mode: {mode}")


def sync_topology_entry(
    entry: TopologyEntry,
    creds: dict[str, "Credential"],
    work_dir: Path,
    force_push: bool = False,
    delete_remote: bool = False,
    mode: str = "mirror",
    preserve_files: list[str] | None = None,
    url_overrides: dict[str, str] | None = None,
    bypass_credentials: bool = False,
    auto_create: bool = False,
    settings: "SyncSettings | None" = None,
) -> SyncResult:
    """Execute a single topology entry: fetch source, push to all targets.

    When the source uses ``branches``, every matched branch is synced
    independently.  Each branch is pushed to every target using
    ``target.branch`` when set, or the source branch name when not.

    Args:
        entry: The TopologyEntry to execute.
        creds: Mapping platform -> Credential.
        work_dir: A working directory for clones.
        force_push: When True, skip the divergence/conflict check and push with
            ``--force``, overwriting any commits the target has that the source
            does not. When False (default), a diverged target aborts the sync.
        delete_remote: When True, after pushing all branches, delete any branch
            that already existed on the target but is NOT in the resolved branch
            list.  DANGEROUS: opt in only when you intend to discard stale
            target branches.
        mode: Sync strategy mode. "mirror" (default) force-pushes source onto
            target. "rebase" replays source commits on top of target.
        preserve_files: Files to preserve during rebase mode (unused in mirror).
        url_overrides: Optional mapping platform -> URL. Used by tests to inject
            local bare repos. In production, URLs are built from build_url().
        bypass_credentials: If True, skip the credential-availability check for
            all platforms. Use only when callers have already validated that
            url_overrides (or some other mechanism) provides a usable URL.
            This is the integration-test escape hatch.

    Raises:
        SyncError: On any failure (missing creds, conflict, git errors).
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # ---- Check source credentials ----
    src_cred_value = _resolve_credentials(entry.source, creds)
    if not bypass_credentials and (
        entry.source.platform not in creds
        or not (
            (entry.source.auth == "pat" and src_cred_value)
            or (entry.source.auth == "ssh" and src_cred_value)
        )
    ):
        raise SyncError(
            f"missing credentials for source platform {entry.source.platform!r}"
        )

    # ---- Resolve source URL ----
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

    # ---- Clone source (full or single-branch) ----
    source_clone_dir = work_dir / f"src_{entry.name}"
    try:
        if entry.source.branches:
            clone_or_fetch(source_url, source_clone_dir, single_branch=False)
        else:
            clone_or_fetch(source_url, source_clone_dir, entry.source.branch)
    except GitError as e:
        raise SyncError(f"failed to fetch source: {e}") from e

    # ---- Resolve branch list ----
    if entry.source.branches:
        try:
            resolved_branches = resolve_branches(entry.source.branches, source_url)
        except Exception as e:
            raise SyncError(f"failed to resolve branches: {e}") from e
    else:
        resolved_branches = [entry.source.branch]

    # ---- Resolve strategy (no delete_remote — handled at entry level) ----
    strategy = _resolve_strategy(
        mode,
        force_push=force_push,
        preserve_files=preserve_files,
        work_dir=work_dir,
    )

    pushed: list[str] = []
    deleted: list[str] = []
    skipped: list[str] = []
    restored: list[str] = []
    branches_synced: list[str] = []
    branches_failed: list[tuple[str, str]] = []

    # Resolve target credentials and URLs once (before branch loop).
    target_infos: list[tuple[Endpoint, str, str | None]] = []  # (target, url, cred_value)
    for target in entry.targets:
        tgt_cred_value = _resolve_credentials(target, creds)
        if not bypass_credentials and (
            target.platform not in creds
            or not (
                (target.auth == "pat" and tgt_cred_value)
                or (target.auth == "ssh" and tgt_cred_value)
            )
        ):
            raise SyncError(
                f"missing credentials for target platform {target.platform!r}"
            )
        if url_overrides and target.platform in url_overrides:
            t_url = url_overrides[target.platform]
        else:
            t_url = build_url(
                target.platform,
                target.owner,
                target.repo,
                target.auth,
                token=tgt_cred_value,
            )
        target_infos.append((target, t_url, tgt_cred_value))

    # Compute per-target branch lists
    target_branch_list: list[list[str]] = []
    for tgt, tgt_url, _ in target_infos:
        if tgt.branches:
            # Match target patterns against source's resolved branches
            tgt_list = [b for b in resolved_branches
                        if any(fnmatch.fnmatch(b, p) for p in tgt.branches)]
            target_branch_list.append(tgt_list)
        elif tgt.branch:
            target_branch_list.append([tgt.branch])
        else:
            # Inherit source's resolved branches
            target_branch_list.append(resolved_branches)

    for branch in resolved_branches:
        # Get source SHA for this branch
        source_sha = get_head_sha(source_clone_dir, branch)
        if source_sha is None:
            if entry.source.branches:
                branches_failed.append((branch, f"branch {branch!r} not found on source"))
                continue
            else:
                raise SyncError(
                    f"source branch {branch!r} not found on {entry.source.platform}"
                )

        # Ensure the branch exists as a local ref so push can find it.
        # After a full clone only the default branch has a local tracking
        # branch; other branches are remote-only (origin/<name>).
        if entry.source.branches:
            subprocess.run(
                ["git", "checkout", branch],
                cwd=source_clone_dir, capture_output=True, check=True,
            )

        synced_targets = 0
        for tgt_idx, (tgt, target_url, tgt_cred_value) in enumerate(target_infos):
            # Check if this branch is in the target's allowed list
            tgt_branches_for_this_target = target_branch_list[tgt_idx]
            if branch not in tgt_branches_for_this_target:
                continue  # skip branches not in target's branch list

            target_branch = branch  # always use source branch name (same-name mapping)

            # Delegate to strategy
            try:
                result = strategy.sync(
                    source_dir=source_clone_dir,
                    target_url=target_url,
                    branch=target_branch,
                )
            except SyncError as e:
                # Auto-create: if the target repo doesn't exist and auto_create
                # is enabled, create the repo and retry once.
                if _should_auto_create(tgt, e, tgt_cred_value, default_auto_create=auto_create):
                    _create_target_repo(tgt, tgt_cred_value)
                    try:
                        result = strategy.sync(
                            source_dir=source_clone_dir,
                            target_url=target_url,
                            branch=target_branch,
                        )
                    except SyncError as retry_err:
                        if entry.source.branches:
                            branches_failed.append((branch, str(retry_err)))
                            continue
                        else:
                            raise
                elif entry.source.branches:
                    # Multi-branch mode: record failure and continue with
                    # remaining branches.
                    branches_failed.append((branch, str(e)))
                    continue
                else:
                    # Single-branch mode: preserve legacy raise behaviour.
                    raise

            # success path
            synced_targets += 1

            # Format results with full target identifiers for callers.
            tgt_id = f"{tgt.platform}:{tgt.owner}/{tgt.repo}"
            if result.success:
                pushed.append(f"{tgt_id}#{target_branch}")
            deleted.extend(f"{tgt_id}#{d}" for d in result.deleted)
            if result.skipped:
                skipped.append(tgt_id)
            restored.extend(result.restored)

        if synced_targets > 0:
            branches_synced.append(branch)

    # ---- delete_remote cleanup (outer loop) ----
    if delete_remote:
        for tgt_idx, (tgt, tgt_url, _) in enumerate(target_infos):
            try:
                all_target_branches = list_remote_branches_url(tgt_url)
            except Exception:
                continue
            stale = [b for b in all_target_branches if b not in set(target_branch_list[tgt_idx])]
            if stale:
                subprocess.run(
                    ["git", "remote", "remove", "del_rm"],
                    cwd=source_clone_dir, capture_output=True,
                )
                subprocess.run(
                    ["git", "remote", "add", "del_rm", tgt_url],
                    cwd=source_clone_dir, capture_output=True, check=True,
                )
                for sb in stale:
                    try:
                        delete_remote_branch(source_clone_dir, "del_rm", sb)
                        deleted.append(f"{tgt.platform}:{tgt.owner}/{tgt.repo}#{sb}")
                    except GitError:
                        pass  # best-effort deletion

    # ---- Release sync (unchanged) ----
    release_result = None
    if settings is not None:
        eff_on = entry.sync_releases if entry.sync_releases is not None else settings.sync_releases
        if eff_on:
            release_result = _release_sync.sync_releases(entry, creds, settings)

    # Determine success: at least one branch synced, or source branch list was empty
    source_label = f"{entry.source.platform}:{entry.source.owner}/{entry.source.repo}"
    if entry.source.branches:
        source_label += f"#({','.join(resolved_branches)})"
    else:
        source_label += f"#{entry.source.branch}"

    return SyncResult(
        success=len(branches_synced) > 0,
        entry_name=entry.name,
        source=source_label,
        targets_pushed=pushed,
        deleted=deleted,
        skipped=skipped,
        restored=restored,
        message="ok",
        release_result=release_result,
        branches_synced=branches_synced,
        branches_failed=branches_failed,
    )


def _should_auto_create(target: Endpoint, error: SyncError, tgt_cred: str | None, default_auto_create: bool = False) -> bool:
    """Return True if this error indicates a missing repo and auto_create is enabled."""
    if not (target.auto_create or default_auto_create):
        return False
    if not tgt_cred:
        return False  # Need a token to create repos
    msg = str(error).lower()
    # Include local-path keywords (used in tests with url_overrides) in addition
    # to remote-URL keywords so the auto-create path works regardless of transport.
    return any(kw in msg for kw in (
        "not found",
        "couldn't find",
        "does not appear to be a git repository",
        "could not read from remote repository",
    ))


def _create_target_repo(target: Endpoint, tgt_cred: str | None) -> None:
    """Create a repository for the given target endpoint."""
    request = CreateRepoRequest(
        platform=target.platform,
        owner=target.owner,
        repo=target.repo,
        visibility=target.visibility,
        token=tgt_cred or "",
    )
    try:
        create_repo(request)
    except CreateRepoError as e:
        raise SyncError(
            f"failed to auto-create repo on {target.platform}:{target.owner}/{target.repo}: {e}"
        ) from e
