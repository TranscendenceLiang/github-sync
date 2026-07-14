"""End-to-end integration test using local bare repos."""
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from src.config import load_config
from src.credential import Credential
from src.main import run_sync


def test_end_to_end_single_topology(tmp_path, monkeypatch):
    # Build source and target bare repos with content
    src_bare = tmp_path / "src.git"
    dst_bare = tmp_path / "dst.git"
    work = tmp_path / "work"
    src_work = tmp_path / "src_work"
    src_bare.mkdir()
    dst_bare.mkdir()
    subprocess.run(["git", "init", "--bare", str(src_bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "--bare", str(dst_bare)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(src_bare), str(src_work)], check=True, capture_output=True)

    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t",
    })
    subprocess.run(["git", "checkout", "-b", "main"], cwd=src_work, check=True, env=env)
    (src_work / "README.md").write_text("# hello")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=src_work, check=True, env=env)

    # Write config that targets our local bare repos
    cfg = tmp_path / "sync.yaml"
    cfg.write_text(textwrap.dedent("""\
        sync:
          settings:
            auto_create: false
            force_push: false
            delete_remote: false
          topology:
            - name: "e2e"
              source:
                platform: github
                owner: o
                repo: r
                branch: main
                auth: ssh
              targets:
                - platform: gitee
                  owner: o
                  repo: r
                  branch: main
                  auth: ssh
    """))

    # Patch platform URL builder to map to our local bare repos
    import src.sync as sync_mod
    overrides = {"github": str(src_bare), "gitee": str(dst_bare)}
    # No credentials needed because we use direct URLs
    for k in [
        "SSH_KEY_GITHUB", "TOKEN_GITHUB",
        "SSH_KEY_GITEE", "TOKEN_GITEE",
        "TOKEN_CNB",
        "SSH_KEY_GITCODE", "TOKEN_GITCODE",
    ]:
        monkeypatch.delenv(k, raising=False)

    rc = run_sync(cfg, work_dir=work, url_overrides=overrides)
    assert rc == 0

    # Verify destination has the same HEAD
    dst_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=dst_bare, capture_output=True, text=True
    )
    src_head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=src_bare, capture_output=True, text=True
    )
    assert dst_head.stdout.strip() == src_head.stdout.strip()
    assert len(dst_head.stdout.strip()) == 40


def test_end_to_end_multi_branch(tmp_path, monkeypatch):
    """Multi-branch end-to-end: source has main + develop, target should get both."""
    import subprocess, os, textwrap
    from pathlib import Path
    from src.main import run_sync

    src_bare = tmp_path / "src.git"
    dst_bare = tmp_path / "dst.git"
    subprocess.run(["git", "init", "--bare", str(src_bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "--bare", str(dst_bare)], check=True, capture_output=True)

    src_work = tmp_path / "src_work"
    subprocess.run(["git", "clone", str(src_bare), str(src_work)], check=True, capture_output=True)
    env = os.environ.copy()
    env.update({"GIT_AUTHOR_NAME":"T","GIT_AUTHOR_EMAIL":"t@t","GIT_COMMITTER_NAME":"T","GIT_COMMITTER_EMAIL":"t@t"})
    subprocess.run(["git", "checkout", "-b", "main"], cwd=src_work, check=True, env=env)
    (src_work / "README.md").write_text("# hello")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=src_work, check=True, env=env)

    subprocess.run(["git", "checkout", "-b", "develop"], cwd=src_work, check=True, env=env)
    (src_work / "dev.txt").write_text("dev")
    subprocess.run(["git", "add", "."], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "dev"], cwd=src_work, check=True, env=env)
    subprocess.run(["git", "push", "-u", "origin", "develop"], cwd=src_work, check=True, env=env)

    cfg = tmp_path / "sync.yaml"
    cfg.write_text(textwrap.dedent("""\
        sync:
          settings:
            force_push: true
          topology:
            - name: "e2e-multi"
              source:
                platform: github
                owner: o
                repo: r
                branches: ["*"]
              targets:
                - platform: gitee
                  owner: o
                  repo: r
    """))

    overrides = {"github": str(src_bare), "gitee": str(dst_bare)}
    for k in ["SSH_KEY_GITHUB","TOKEN_GITHUB","SSH_KEY_GITEE","TOKEN_GITEE","TOKEN_CNB","SSH_KEY_GITCODE","TOKEN_GITCODE"]:
        monkeypatch.delenv(k, raising=False)

    rc = run_sync(cfg, work_dir=tmp_path / "work", url_overrides=overrides)
    assert rc == 0

    src_main = subprocess.run(["git", "rev-parse", "main"], cwd=src_bare, capture_output=True, text=True)
    src_dev = subprocess.run(["git", "rev-parse", "develop"], cwd=src_bare, capture_output=True, text=True)
    dst_main = subprocess.run(["git", "rev-parse", "main"], cwd=dst_bare, capture_output=True, text=True)
    dst_dev = subprocess.run(["git", "rev-parse", "develop"], cwd=dst_bare, capture_output=True, text=True)
    assert dst_main.returncode == 0
    assert dst_dev.returncode == 0
    assert dst_main.stdout.strip() == src_main.stdout.strip()
    assert dst_dev.stdout.strip() == src_dev.stdout.strip()
