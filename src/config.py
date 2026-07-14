"""YAML configuration loader and validator.

Schema:

sync:
  settings:
    auto_create: false      # Reserved, not yet implemented
    force_push: false
    delete_remote: false

  topology:
    - name: "unique-name"
      source:
        platform: github    # github | gitee | cnb | gitcode
        owner: myorg
        repo: myproject
        branch: main
        auth: ssh           # ssh (default) | pat
      targets:
        - platform: gitee
          owner: myorg
          repo: myproject
          branch: main
          auth: ssh
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.platform import SUPPORTED_PLATFORMS
from src.release_sync import ReleaseFilter


class ConfigError(Exception):
    """Raised when configuration is invalid."""


@dataclass
class SyncSettings:
    auto_create: bool = False
    force_push: bool = False
    delete_remote: bool = False
    mode: str = "mirror"
    preserve_files: list[str] | None = None
    sync_releases: bool = False
    release_asset_max_size_mb: int = 50
    release_filter: ReleaseFilter = field(default_factory=ReleaseFilter)


@dataclass
class Endpoint:
    platform: str
    owner: str
    repo: str
    branch: str | None = None
    branches: list[str] | None = None
    auth: str = "ssh"
    auto_create: bool = False
    visibility: str = "private"

    def __post_init__(self) -> None:
        if self.platform not in SUPPORTED_PLATFORMS:
            raise ConfigError(
                f"unsupported platform {self.platform!r}; "
                f"must be one of {sorted(SUPPORTED_PLATFORMS)}"
            )
        if self.branch is not None and self.branches is not None:
            raise ConfigError(
                f"'branch' and 'branches' are mutually exclusive "
                f"(got branch={self.branch!r}, branches={self.branches!r})"
            )
        if self.branches is not None and len(self.branches) == 0:
            raise ConfigError("'branches' must not be empty")
        if self.auth not in ("ssh", "pat"):
            raise ConfigError(f"auth must be 'ssh' or 'pat', got {self.auth!r}")
        if self.visibility not in ("public", "private"):
            raise ConfigError(
                f"visibility must be 'public' or 'private', got {self.visibility!r}"
            )


@dataclass
class TopologyEntry:
    name: str
    source: Endpoint
    targets: list[Endpoint] = field(default_factory=list)
    mode: str | None = None
    preserve_files: list[str] | None = None
    sync_releases: bool | None = None
    release_filter: ReleaseFilter | None = None

    def __post_init__(self) -> None:
        if not self.targets:
            raise ConfigError(f"topology entry {self.name!r}: at least one target required")


@dataclass
class SyncConfig:
    settings: SyncSettings
    topology: list[TopologyEntry]


def _parse_endpoint(data: Any, ctx: str) -> Endpoint:
    if not isinstance(data, dict):
        raise ConfigError(f"{ctx}: expected mapping, got {type(data).__name__}")
    required = ("platform", "owner", "repo")
    missing = [k for k in required if k not in data]
    if missing:
        raise ConfigError(f"{ctx}: missing required field(s): {', '.join(missing)}")
    branch = data.get("branch")
    branches = data.get("branches")
    if branch is not None and branches is not None:
        raise ConfigError(f"{ctx}: 'branch' and 'branches' are mutually exclusive")
    if branches is not None:
        if not isinstance(branches, list) or not all(isinstance(b, str) for b in branches):
            raise ConfigError(f"{ctx}: 'branches' must be a list of strings")
        if len(branches) == 0:
            raise ConfigError(f"{ctx}: 'branches' must not be empty")
    try:
        return Endpoint(
            platform=str(data["platform"]).lower(),
            owner=str(data["owner"]),
            repo=str(data["repo"]),
            branch=str(branch) if branch is not None else None,
            branches=[str(b) for b in branches] if branches is not None else None,
            auth=str(data.get("auth", "ssh")).lower(),
            auto_create=bool(data.get("auto_create", False)),
            visibility=str(data.get("visibility", "private")).lower(),
        )
    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"{ctx}: invalid endpoint: {e}") from e


def _parse_entry(data: Any) -> TopologyEntry:
    if not isinstance(data, dict):
        raise ConfigError(f"topology entry: expected mapping, got {type(data).__name__}")
    if "name" not in data:
        raise ConfigError("topology entry missing 'name'")
    name = str(data["name"])
    source = _parse_endpoint(data.get("source"), f"topology[{name}].source")
    targets_raw = data.get("targets", [])
    if not isinstance(targets_raw, list):
        raise ConfigError(f"topology[{name}].targets must be a list")
    targets = [_parse_endpoint(t, f"topology[{name}].targets[{i}]") for i, t in enumerate(targets_raw)]

    mode = data.get("mode")
    if mode is not None:
        mode = str(mode).lower()
        if mode not in ("mirror", "rebase"):
            raise ConfigError(f"topology[{name}].mode must be 'mirror' or 'rebase', got {mode!r}")

    pf_raw = data.get("preserve_files")
    preserve_files = None
    if pf_raw is not None:
        if not isinstance(pf_raw, list) or not all(isinstance(f, str) for f in pf_raw):
            raise ConfigError(f"topology[{name}].preserve_files must be a list of strings")
        preserve_files = [str(f) for f in pf_raw]

    rf_raw = data.get("release_filter")
    release_filter = _parse_release_filter(rf_raw) if rf_raw is not None else None
    sync_releases = data.get("sync_releases", None)
    if sync_releases is not None:
        sync_releases = bool(sync_releases)

    return TopologyEntry(
        name=name, source=source, targets=targets, mode=mode,
        preserve_files=preserve_files,
        sync_releases=sync_releases,
        release_filter=release_filter,
    )


def _parse_release_filter(data: Any) -> ReleaseFilter:
    if data is None:
        return ReleaseFilter()
    if not isinstance(data, dict):
        raise ConfigError("release_filter must be a mapping")
    mode = str(data.get("mode", "all")).lower()
    if mode not in ("all", "latest", "pattern", "tags"):
        raise ConfigError(
            f"release_filter.mode must be one of all|latest|pattern|tags, got {mode!r}"
        )
    try:
        latest_count = int(data.get("latest_count", 1))
    except (TypeError, ValueError) as e:
        raise ConfigError(
            f"release_filter.latest_count must be an integer, got {data.get('latest_count')!r}"
        ) from e
    pattern = data.get("pattern")
    tags = data.get("tags")
    if tags is not None and (not isinstance(tags, list) or not all(isinstance(t, str) for t in tags)):
        raise ConfigError("release_filter.tags must be a list of strings")
    include_drafts = bool(data.get("include_drafts", False))
    return ReleaseFilter(
        mode=mode,
        latest_count=latest_count,
        pattern=pattern,
        tags=tags,
        include_drafts=include_drafts,
    )


def _parse_settings(data: Any) -> SyncSettings:
    if data is None:
        return SyncSettings()
    if not isinstance(data, dict):
        raise ConfigError("settings must be a mapping")
    mode = str(data.get("mode", "mirror")).lower()
    if mode not in ("mirror", "rebase"):
        raise ConfigError(f"settings.mode must be 'mirror' or 'rebase', got {mode!r}")
    pf_raw = data.get("preserve_files")
    preserve_files = None
    if pf_raw is not None:
        if not isinstance(pf_raw, list) or not all(isinstance(f, str) for f in pf_raw):
            raise ConfigError("settings.preserve_files must be a list of strings")
        preserve_files = [str(f) for f in pf_raw]
    try:
        release_asset_max_size_mb = int(data.get("release_asset_max_size_mb", 50))
    except (TypeError, ValueError) as e:
        raise ConfigError(
            f"release_asset_max_size_mb must be an integer, got {data.get('release_asset_max_size_mb')!r}"
        ) from e
    return SyncSettings(
        auto_create=bool(data.get("auto_create", False)),
        force_push=bool(data.get("force_push", False)),
        delete_remote=bool(data.get("delete_remote", False)),
        mode=mode,
        preserve_files=preserve_files,
        sync_releases=bool(data.get("sync_releases", False)),
        release_asset_max_size_mb=release_asset_max_size_mb,
        release_filter=_parse_release_filter(data.get("release_filter")),
    )


def load_config(path: str | Path) -> SyncConfig:
    """Load and validate a sync config from a YAML file."""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML: {e}") from e

    if not isinstance(raw, dict) or "sync" not in raw:
        raise ConfigError("config must have top-level 'sync' key")
    sync = raw["sync"]
    if not isinstance(sync, dict):
        raise ConfigError("'sync' must be a mapping")

    settings = _parse_settings(sync.get("settings"))
    topo_raw = sync.get("topology", [])
    if not isinstance(topo_raw, list):
        raise ConfigError("topology must be a list")

    # Reject duplicate names
    names = [t.get("name") for t in topo_raw if isinstance(t, dict)]
    seen: set[str] = set()
    for n in names:
        if n in seen:
            raise ConfigError(f"duplicate topology name: {n!r}")
        seen.add(n)

    topology = [_parse_entry(t) for t in topo_raw]
    return SyncConfig(settings=settings, topology=topology)