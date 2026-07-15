"""Tests for auto_create module (repo creation via curl)."""
import json
import subprocess
from pathlib import Path

import pytest

from src.auto_create import CreateRepoRequest, create_repo, CreateRepoError


def test_create_repo_github(tmp_path):
    """GitHub: POST /user/repos with Bearer token."""
    call_log = []
    original_run = subprocess.run

    def _mock_run(args, **kwargs):
        call_log.append(args)
        # Return a fake successful response
        class FakeProc:
            returncode = 0
            stdout = '{"id": 1, "name": "test"}'
            stderr = ""
        return FakeProc()

    subprocess.run = _mock_run
    try:
        create_repo(CreateRepoRequest(
            platform="github",
            owner="myorg",
            repo="test-repo",
            visibility="private",
            token="ghp_token123",
        ))
    finally:
        subprocess.run = original_run

    assert len(call_log) == 1
    cmd = " ".join(call_log[0])
    assert "curl" in cmd
    assert "api.github.com/user/repos" in cmd
    assert "Authorization: Bearer ghp_token123" in cmd
    assert "test-repo" in cmd


def test_create_repo_cnb(tmp_path):
    """CNB: POST /{owner}/-/repos with name + visibility (slug goes in path)."""
    call_log = []
    original_run = subprocess.run

    def _mock_run(args, **kwargs):
        call_log.append(args)
        class FakeProc:
            returncode = 0
            stdout = '{"id": 1}'
            stderr = ""
        return FakeProc()

    subprocess.run = _mock_run
    try:
        create_repo(CreateRepoRequest(
            platform="cnb",
            owner="myorg",
            repo="test-repo",
            visibility="private",
            token="cnb_token123",
        ))
    finally:
        subprocess.run = original_run

    cmd = " ".join(call_log[0])
    assert "api.cnb.cool/myorg/-/repos" in cmd
    assert "myorg" in cmd  # slug in path
    assert "test-repo" in cmd


def test_create_repo_gitee(tmp_path):
    """Gitee: POST /api/v5/user/repos with access_token in body."""
    call_log = []
    original_run = subprocess.run

    def _mock_run(args, **kwargs):
        call_log.append(args)
        class FakeProc:
            returncode = 0
            stdout = '{"id": 1}'
            stderr = ""
        return FakeProc()

    subprocess.run = _mock_run
    try:
        create_repo(CreateRepoRequest(
            platform="gitee",
            owner="myorg",
            repo="test-repo",
            visibility="public",
            token="gitee_token123",
        ))
    finally:
        subprocess.run = original_run

    cmd = " ".join(call_log[0])
    assert "gitee.com/api/v5/user/repos" in cmd


def test_create_repo_gitcode(tmp_path):
    """GitCode: POST /api/v5/user/repos with access_token query param."""
    call_log = []
    original_run = subprocess.run

    def _mock_run(args, **kwargs):
        call_log.append(args)
        class FakeProc:
            returncode = 0
            stdout = '{"id": 1}'
            stderr = ""
        return FakeProc()

    subprocess.run = _mock_run
    try:
        create_repo(CreateRepoRequest(
            platform="gitcode",
            owner="myorg",
            repo="test-repo",
            visibility="public",
            token="gc_token123",
        ))
    finally:
        subprocess.run = original_run

    cmd = " ".join(call_log[0])
    assert "api.gitcode.com/api/v5/user/repos" in cmd
    assert "visibility" in cmd
    assert "public" in cmd


def test_create_repo_api_failure(tmp_path):
    """API returns non-zero exit code -> CreateRepoError."""
    original_run = subprocess.run

    def _mock_run(args, **kwargs):
        class FakeProc:
            returncode = 1
            stdout = ""
            stderr = "404 Not Found"
        return FakeProc()

    subprocess.run = _mock_run
    try:
        with pytest.raises(CreateRepoError, match="404"):
            create_repo(CreateRepoRequest(
                platform="github",
                owner="o", repo="r", visibility="private", token="t",
            ))
    finally:
        subprocess.run = original_run


def test_create_repo_unsupported_platform(tmp_path):
    """Unknown platform -> CreateRepoError."""
    with pytest.raises(CreateRepoError, match="unsupported platform"):
        create_repo(CreateRepoRequest(
            platform="gitlab",
            owner="o", repo="r", visibility="private", token="t",
        ))
