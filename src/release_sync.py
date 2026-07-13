"""Release sync engine: sync release metadata + assets across platforms via REST APIs."""
from __future__ import annotations

import fnmatch
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AssetInfo:
    name: str
    size: int  # bytes
    download_url: str
    asset_id: str | None = None


@dataclass
class ReleaseInfo:
    tag_name: str
    name: str | None = None
    body: str | None = None
    draft: bool = False
    prerelease: bool = False
    release_id: str | None = None
    assets: list[AssetInfo] = field(default_factory=list)
    published_at: str | None = None  # ISO string, used for `latest` ordering


@dataclass
class ReleaseFilter:
    mode: str = "all"  # all | latest | pattern | tags
    latest_count: int = 1
    pattern: str | None = None
    tags: list[str] | None = None
    include_drafts: bool = False


@dataclass
class ReleaseSyncResult:
    releases_created: int = 0
    releases_updated: int = 0
    releases_skipped: int = 0
    assets_uploaded: int = 0
    assets_skipped: int = 0
    warnings: list[str] = field(default_factory=list)  # non-fatal (skip-level)
    errors: list[str] = field(default_factory=list)      # fatal (target-level)


class ReleaseSyncError(Exception):
    """Carries platform/repo context for a failed release API call."""


class ReleaseClient(ABC):
    """Abstract base for per-platform release API clients (registered in later Tasks)."""

    platform: str

    @abstractmethod
    def list_releases(self) -> list[ReleaseInfo]:
        ...

    @abstractmethod
    def create_release(self, release: ReleaseInfo) -> ReleaseInfo:
        ...


def filter_releases(releases: list[ReleaseInfo], rf: ReleaseFilter) -> list[ReleaseInfo]:
    out = [r for r in releases if (not r.draft) or rf.include_drafts]  # 全局 draft 门控
    if rf.mode == "all":
        return out
    if rf.mode == "latest":
        ordered = sorted(out, key=lambda r: r.published_at or "", reverse=True)
        return ordered[: max(1, rf.latest_count)]
    if rf.mode == "pattern":
        if not rf.pattern:
            return out
        return [r for r in out if fnmatch.fnmatch(r.tag_name, rf.pattern)]
    if rf.mode == "tags":
        if not rf.tags:
            return out
        wanted = set(rf.tags)
        return [r for r in out if r.tag_name in wanted]
    return out


RELEASE_CLIENTS: dict[str, type[ReleaseClient]] = {}


def supports_releases(platform: str) -> bool:
    return platform in RELEASE_CLIENTS
