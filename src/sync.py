"""Sync engine: executes a single TopologyEntry (source -> [targets]).

For each topology entry:
  1. Resolve source/target URLs and credentials
  2. Clone or update source
  3. Delegate to the appropriate SyncStrategy (mirror, rebase, etc.) for each target
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import Endpoint, TopologyEntry
from src.git_helper import GitError, clone_or_fetch, get_head_sha
from src.platform import build_url
from src.strategies.base import (
    SyncError,
    StrategyResult,
    SyncStrategy,
    check_conflict,
    _merge_base,
)
from src.auto_create import CreateRepoRequest, create_repo, CreateRepoError
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
    delete_remote: bool = False,
    preserve_files: list[str] | None = None,
    work_dir: Path | None = None,
) -> SyncStrategy:
    """Create the appropriate SyncStrategy for the given mode."""
    if mode == "mirror":
        return MirrorStrategy(force_push=force_push, delete_remote=delete_remote)
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
) -> SyncResult:
    """Execute a single topology entry: fetch source, push to all targets.

    Args:
        entry: The TopologyEntry to execute.
        creds: Mapping platform -> Credential.
        work_dir: A working directory for clones.
        force_push: When True, skip the divergence/conflict check and push with
            ``--force``, overwriting any commits the target has that the source
            does not. When False (default), a diverged target aborts the sync.
        delete_remote: When True, after pushing, delete any branch that already
            existed on the target (before this sync) but is not the branch being
            synced. Effectively makes the target a strict mirror of the synced
            branch. No-ops unless the target already had branches other than the
            synced one. DANGEROUS: opt in only when you intend to discard stale
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

    # Check source credentials.
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

    # Resolve sync strategy
    strategy = _resolve_strategy(
        mode,
        force_push=force_push,
        delete_remote=delete_remote,
        preserve_files=preserve_files,
        work_dir=work_dir,
    )

    pushed: list[str] = []
    deleted: list[str] = []
    skipped: list[str] = []
    restored: list[str] = []

    for target in entry.targets:
        # Check target credentials.
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

        # Delegate to strategy
        try:
            result = strategy.sync(
                source_dir=source_clone_dir,
                target_url=target_url,
                branch=entry.source.branch,
            )
        except SyncError as e:
            # Auto-create: if the target repo doesn't exist and auto_create
            # is enabled, create the repo and retry once.
            if _should_auto_create(target, e, tgt_cred_value):
                _create_target_repo(target, tgt_cred_value)
                result = strategy.sync(
                    source_dir=source_clone_dir,
                    target_url=target_url,
                    branch=entry.source.branch,
                )
            else:
                raise

        # Format results with full target identifiers for callers.
        # Strategy returns raw URLs/names; sync_topology_entry adds context.
        tgt_id = f"{target.platform}:{target.owner}/{target.repo}"
        if result.success:
            pushed.append(f"{tgt_id}#{target.branch}")
        deleted.extend(f"{tgt_id}#{d}" for d in result.deleted)
        if result.skipped:
            skipped.append(tgt_id)
        restored.extend(result.restored)

    return SyncResult(
        success=True,
        entry_name=entry.name,
        source=f"{entry.source.platform}:{entry.source.owner}/{entry.source.repo}#{entry.source.branch}",
        targets_pushed=pushed,
        deleted=deleted,
        skipped=skipped,
        restored=restored,
        message="ok",
    )


def _should_auto_create(target: Endpoint, error: SyncError, tgt_cred: str | None) -> bool:
    """Return True if this error indicates a missing repo and auto_create is enabled."""
    if not target.auto_create:
        return False
    if not tgt_cred:
        return False  # Need a token to create repos
    msg = str(error).lower()
    # Include local-path keywords (used in tests with url_overrides) in addition
    # to remote-URL keywords so the auto-create path works regardless of transport.
    return any(kw in msg for kw in (
        "not found",
        "repository not found",
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
