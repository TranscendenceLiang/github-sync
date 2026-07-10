"""Entry point for the sync engine.

Reads the config, loads credentials from env, and iterates the topology.
Returns 0 on success, non-zero on failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

from src.config import load_config, ConfigError
from src.credential import load_credentials, CredentialError
from src.sync import sync_topology_entry, SyncError


def run_sync(
    config_path: str | Path,
    work_dir: str | Path = "repos",
    url_overrides: dict[str, str] | None = None,
) -> int:
    """Execute the full sync workflow. Returns process exit code."""
    config_path = Path(config_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load config (propagate ConfigError so callers can distinguish)
    cfg = load_config(config_path)

    # 2. Determine which platforms are required by the topology.
    # url_overrides acts as a credential bypass for those platforms (used in
    # tests to inject local bare repos without real auth).
    required: set[str] = set()
    for entry in cfg.topology:
        if not url_overrides or entry.source.platform not in url_overrides:
            required.add(entry.source.platform)
        for t in entry.targets:
            if not url_overrides or t.platform not in url_overrides:
                required.add(t.platform)

    # 3. Load credentials
    try:
        creds = load_credentials(required=required)
    except CredentialError as e:
        print(f"[ERROR] credentials: {e}", file=sys.stderr)
        return 3

    # 4. Execute each topology entry
    # When url_overrides is set, the test/integration escape hatch is in
    # effect: bypass the credential-availability check (the override is the
    # credential). Production code never sets url_overrides.
    bypass_credentials = bool(url_overrides)
    failed = 0
    for entry in cfg.topology:
        # Resolve mode: entry-level overrides global
        mode = entry.mode or cfg.settings.mode
        preserve_files = entry.preserve_files if entry.preserve_files is not None else cfg.settings.preserve_files

        print(f"[INFO] syncing topology entry: {entry.name} (mode={mode})")
        try:
            result = sync_topology_entry(
                entry=entry,
                creds=creds,
                work_dir=work_dir / entry.name,
                force_push=cfg.settings.force_push,
                delete_remote=cfg.settings.delete_remote,
                mode=mode,
                preserve_files=preserve_files or [],
                url_overrides=url_overrides,
                bypass_credentials=bypass_credentials,
                auto_create=cfg.settings.auto_create,
            )
            print(
                f"[OK] {entry.name}: {result.source} -> "
                f"{', '.join(result.targets_pushed) or '(no targets)'}"
            )
        except SyncError as e:
            print(f"[FAIL] {entry.name}: {e}", file=sys.stderr)
            failed += 1
        except Exception as e:
            print(f"[FAIL] {entry.name}: unexpected error: {e}", file=sys.stderr)
            failed += 1

    return 0 if failed == 0 else 1


def main(
    config_path: str | Path = "config/sync.yaml",
    work_dir: str | Path = "repos",
) -> int:
    """Entry point. Returns 0 on success, non-zero on failure."""
    try:
        return run_sync(config_path=config_path, work_dir=work_dir)
    except ConfigError as e:
        print(f"[ERROR] config: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())