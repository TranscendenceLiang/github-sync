"""Smoke tests for the main entry point."""
import textwrap
from pathlib import Path

import pytest

from src.main import run_sync


def test_run_sync_empty_topology(tmp_path, monkeypatch):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            auto_create: false
            force_push: false
            delete_remote: false
          topology: []
    """))
    # No credentials needed for empty topology
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)

    result = run_sync(cfg_file, work_dir=tmp_path / "work")
    assert result == 0


def test_run_sync_missing_config_raises(tmp_path, monkeypatch):
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(Exception):
        run_sync(tmp_path / "missing.yaml", work_dir=tmp_path / "work")


def test_run_sync_returns_nonzero_on_failure(tmp_path, monkeypatch):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source:
                platform: github
                owner: o
                repo: r
                branch: main
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
    """))
    # No credentials set
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SYNC_FAKE", "1")  # marker
    # main() catches the error and returns non-zero
    from src.main import main
    rc = main(config_path=cfg_file, work_dir=tmp_path / "work")
    assert rc != 0