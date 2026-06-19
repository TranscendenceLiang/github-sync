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


class ConfigError(Exception):
    """Raised when configuration is invalid."""


@dataclass
class SyncSettings:
    auto_create: bool = False
    force_push: bool = False
    delete_remote: bool = False


@dataclass
class Endpoint:
    platform: str
    owner: str
    repo: str
    branch: str
    auth: str = "ssh"

    def __post_init__(self) -> None:
        if self.platform not in SUPPORTED_PLATFORMS:
            raise ConfigError(
                f"unsupported platform {self.platform!r}; "
                f"must be one of {sorted(SUPPORTED_PLATFORMS)}"
            )
        if self.auth not in ("ssh", "pat"):
            raise ConfigError(f"auth must be 'ssh' or 'pat', got {self.auth!r}")


@dataclass
class TopologyEntry:
    name: str
    source: Endpoint
    targets: list[Endpoint] = field(default_factory=list)

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
    required = ("platform", "owner", "repo", "branch")
    missing = [k for k in required if k not in data]
    if missing:
        raise ConfigError(f"{ctx}: missing required field(s): {', '.join(missing)}")
    try:
        return Endpoint(
            platform=str(data["platform"]).lower(),
            owner=str(data["owner"]),
            repo=str(data["repo"]),
            branch=str(data["branch"]),
            auth=str(data.get("auth", "ssh")).lower(),
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
    return TopologyEntry(name=name, source=source, targets=targets)


def _parse_settings(data: Any) -> SyncSettings:
    if data is None:
        return SyncSettings()
    if not isinstance(data, dict):
        raise ConfigError("settings must be a mapping")
    return SyncSettings(
        auto_create=bool(data.get("auto_create", False)),
        force_push=bool(data.get("force_push", False)),
        delete_remote=bool(data.get("delete_remote", False)),
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