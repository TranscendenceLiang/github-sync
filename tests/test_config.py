"""Tests for YAML config loading and validation."""
import textwrap
from pathlib import Path

import pytest

from src.config import (
    SyncConfig,
    SyncSettings,
    TopologyEntry,
    Endpoint,
    load_config,
    ConfigError,
)


def test_load_minimal_config(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            auto_create: false
            force_push: false
            delete_remote: false
          topology: []
    """))
    cfg = load_config(cfg_file)
    assert isinstance(cfg, SyncConfig)
    assert cfg.settings.auto_create is False
    assert cfg.settings.force_push is False
    assert cfg.settings.delete_remote is False
    assert cfg.topology == []


def test_load_full_config(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            auto_create: false
            force_push: false
            delete_remote: true
          topology:
            - name: "github-to-gitee"
              source:
                platform: github
                owner: myorg
                repo: myproject
                branch: main
                auth: ssh
              targets:
                - platform: gitee
                  owner: myorg
                  repo: myproject
                  branch: main
                  auth: ssh
            - name: "broadcast"
              source:
                platform: github
                owner: myorg
                repo: myproject
                branch: develop
                auth: pat
              targets:
                - platform: gitee
                  owner: myorg
                  repo: myproject
                  branch: develop
                  auth: ssh
                - platform: cnb
                  owner: myteam
                  repo: myproject
                  branch: develop
                  auth: pat
    """))
    cfg = load_config(cfg_file)
    assert len(cfg.topology) == 2

    first = cfg.topology[0]
    assert isinstance(first, TopologyEntry)
    assert first.name == "github-to-gitee"
    assert first.source.platform == "github"
    assert first.source.auth == "ssh"
    assert first.source.branch == "main"
    assert len(first.targets) == 1
    assert first.targets[0].platform == "gitee"

    second = cfg.topology[1]
    assert second.source.auth == "pat"
    assert len(second.targets) == 2
    assert second.targets[1].platform == "cnb"
    assert second.targets[1].auth == "pat"


def test_load_config_defaults(tmp_path):
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
    cfg = load_config(cfg_file)
    assert cfg.settings.auto_create is False
    assert cfg.settings.force_push is False
    assert cfg.settings.delete_remote is False
    # auth defaults to ssh
    assert cfg.topology[0].source.auth == "ssh"
    assert cfg.topology[0].targets[0].auth == "ssh"


def test_load_config_missing_sync_key_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text("foo: bar\n")
    with pytest.raises(ConfigError, match="sync"):
        load_config(cfg_file)


def test_load_config_topology_not_list_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text("sync:\n  topology: notalist\n")
    with pytest.raises(ConfigError, match="topology must be a list"):
        load_config(cfg_file)


def test_load_config_topology_entry_missing_name(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - source:
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
    with pytest.raises(ConfigError, match="name"):
        load_config(cfg_file)


def test_load_config_endpoint_missing_required_field(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: x
              source:
                platform: github
                owner: o
                branch: main
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
    """))
    with pytest.raises(ConfigError, match="repo"):
        load_config(cfg_file)


def test_load_config_targets_empty_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: x
              source:
                platform: github
                owner: o
                repo: r
                branch: main
              targets: []
    """))
    with pytest.raises(ConfigError, match="at least one target"):
        load_config(cfg_file)


def test_load_config_invalid_auth_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: x
              source:
                platform: github
                owner: o
                repo: r
                branch: main
                auth: bogus
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
    """))
    with pytest.raises(ConfigError, match="auth"):
        load_config(cfg_file)


def test_load_config_with_mode_and_preserve(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            mode: rebase
            preserve_files:
              - .cnb.yml
          topology:
            - name: "x"
              mode: rebase
              preserve_files:
                - .cnb.yml
                - Dockerfile
              source:
                platform: github
                owner: o
                repo: r
                branch: main
              targets:
                - platform: cnb
                  owner: o
                  repo: r
                  branch: main
    """))
    cfg = load_config(cfg_file)
    assert cfg.settings.mode == "rebase"
    assert cfg.settings.preserve_files == [".cnb.yml"]
    assert cfg.topology[0].mode == "rebase"
    assert cfg.topology[0].preserve_files == [".cnb.yml", "Dockerfile"]


def test_load_config_mode_default_mirror(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source: {platform: github, owner: o, repo: r, branch: main}
              targets: [{platform: gitee, owner: o, repo: r, branch: main}]
    """))
    cfg = load_config(cfg_file)
    assert cfg.settings.mode == "mirror"
    assert cfg.topology[0].mode is None


def test_load_config_invalid_mode_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            mode: merge
          topology: []
    """))
    with pytest.raises(ConfigError, match="mode"):
        load_config(cfg_file)


def test_load_config_invalid_entry_mode_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              mode: foo
              source: {platform: github, owner: o, repo: r, branch: main}
              targets: [{platform: gitee, owner: o, repo: r, branch: main}]
    """))
    with pytest.raises(ConfigError, match="mode"):
        load_config(cfg_file)


def test_load_config_preserve_files_not_list_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          settings:
            preserve_files: ".cnb.yml"
          topology: []
    """))
    with pytest.raises(ConfigError, match="preserve_files"):
        load_config(cfg_file)


def test_load_config_with_auto_create_and_visibility(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source: {platform: github, owner: o, repo: r, branch: main}
              targets:
                - platform: cnb
                  owner: myorg
                  repo: myrepo
                  branch: main
                  auto_create: true
                  visibility: public
    """))
    cfg = load_config(cfg_file)
    t = cfg.topology[0].targets[0]
    assert t.auto_create is True
    assert t.visibility == "public"


def test_load_config_auto_create_defaults(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source: {platform: github, owner: o, repo: r, branch: main}
              targets: [{platform: gitee, owner: o, repo: r, branch: main}]
    """))
    cfg = load_config(cfg_file)
    t = cfg.topology[0].targets[0]
    assert t.auto_create is False
    assert t.visibility == "private"


def test_load_config_invalid_visibility_raises(tmp_path):
    cfg_file = tmp_path / "sync.yaml"
    cfg_file.write_text(textwrap.dedent("""\
        sync:
          topology:
            - name: "x"
              source: {platform: github, owner: o, repo: r, branch: main}
              targets:
                - platform: cnb
                  owner: o
                  repo: r
                  branch: main
                  visibility: secret
    """))
    with pytest.raises(ConfigError, match="visibility"):
        load_config(cfg_file)
