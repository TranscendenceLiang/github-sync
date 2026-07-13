"""Tests for release_sync module (data model + filter_releases)."""
from pathlib import Path

from src.release_sync import (
    AssetInfo,
    GitHubReleaseClient,
    ReleaseFilter,
    ReleaseInfo,
    ReleaseSyncError,
    filter_releases,
    supports_releases,
)


def _rel(tag, draft=False, published=None, assets=None):
    return ReleaseInfo(
        tag_name=tag,
        name=tag,
        draft=draft,
        published_at=published,
        assets=assets or [],
    )


def test_filter_all():
    """mode=all + 默认 include_drafts=False 剔除草稿（返回全部非草稿 release）。"""
    releases = [
        _rel("v1.0.0", published="2024-01-01"),
        _rel("v2.0.0", draft=True, published="2024-02-01"),
    ]
    rf = ReleaseFilter(mode="all")
    result = filter_releases(releases, rf)
    assert len(result) == 1
    assert result[0].tag_name == "v1.0.0"


def test_filter_all_include_drafts():
    """mode=all + include_drafts=True 返回所有 release（含草稿）。"""
    releases = [
        _rel("v1.0.0", published="2024-01-01"),
        _rel("v2.0.0", draft=True, published="2024-02-01"),
    ]
    rf = ReleaseFilter(mode="all", include_drafts=True)
    result = filter_releases(releases, rf)
    assert len(result) == 2


def test_filter_include_drafts_false_default():
    """Default behaviour (subsetting mode) drops drafts."""
    releases = [
        _rel("v1.0.0", published="2024-01-01"),
        _rel("v2.0.0", draft=True, published="2024-02-01"),
    ]
    rf = ReleaseFilter(mode="latest", latest_count=10)
    result = filter_releases(releases, rf)
    assert len(result) == 1
    assert result[0].tag_name == "v1.0.0"


def test_filter_include_drafts_true():
    """include_drafts=True keeps drafts in subsetting modes."""
    releases = [
        _rel("v1.0.0", published="2024-01-01"),
        _rel("v2.0.0", draft=True, published="2024-02-01"),
    ]
    rf = ReleaseFilter(mode="latest", latest_count=10, include_drafts=True)
    result = filter_releases(releases, rf)
    assert len(result) == 2


def test_filter_latest():
    """latest_count=2 returns two most-recent by published_at desc."""
    releases = [
        _rel("v1.0.0", published="2024-01-01"),
        _rel("v2.0.0", published="2024-03-01"),
        _rel("v3.0.0", published="2024-02-01"),
    ]
    rf = ReleaseFilter(mode="latest", latest_count=2)
    result = filter_releases(releases, rf)
    assert [r.tag_name for r in result] == ["v2.0.0", "v3.0.0"]


def test_filter_pattern():
    """pattern uses fnmatch against tag_name."""
    releases = [
        _rel("v1.2.3", published="2024-01-01"),
        _rel("v2.0.0", published="2024-02-01"),
        _rel("nightly", published="2024-03-01"),
    ]
    rf = ReleaseFilter(mode="pattern", pattern="v*.*.*")
    result = filter_releases(releases, rf)
    assert sorted(r.tag_name for r in result) == ["v1.2.3", "v2.0.0"]


def test_filter_tags():
    """tags whitelist selects only matching tags."""
    releases = [
        _rel("v1.0.0", published="2024-01-01"),
        _rel("v2.0.0", published="2024-02-01"),
        _rel("v3.0.0", published="2024-03-01"),
    ]
    rf = ReleaseFilter(mode="tags", tags=["v1.0.0", "v3.0.0"])
    result = filter_releases(releases, rf)
    assert sorted(r.tag_name for r in result) == ["v1.0.0", "v3.0.0"]


def test_supports_releases_registry():
    """Unknown platform must not be claimed as supported."""
    assert supports_releases("gitlab") is False


def test_filter_unknown_mode_raises():
    import pytest
    with pytest.raises(ValueError, match="unknown filter mode"):
        filter_releases([_rel("v1")], ReleaseFilter(mode="bogus"))


def test_filter_pattern_none_returns_all():
    rels = [_rel("v1.0.0"), _rel("rel-x")]
    rf = ReleaseFilter(mode="pattern", pattern=None)
    assert len(filter_releases(rels, rf)) == 2


def test_filter_tags_none_returns_all():
    rels = [_rel("v1.0.0"), _rel("v2.0.0")]
    rf = ReleaseFilter(mode="tags", tags=None)
    assert len(filter_releases(rels, rf)) == 2


import subprocess


def _mock_curl(json_text, returncode=0):
    original = subprocess.run
    def _run(args, **kwargs):
        class P:
            stdout = json_text
            stderr = ""
        P.returncode = returncode
        return P()
    subprocess.run = _run
    return original


def test_github_list_releases():
    sample = '[{"tag_name":"v1.0.0","name":"v1","body":"b","draft":false,' \
             '"prerelease":true,"id":10,"published_at":"2024-01-01T00:00:00Z",' \
             '"assets":[{"name":"a.bin","size":123,"browser_download_url":"http://x/a.bin","id":1}]}]'
    orig = _mock_curl(sample)
    try:
        c = GitHubReleaseClient()
        rels = c.list_releases("o", "r", "tok")
    finally:
        subprocess.run = orig
    assert len(rels) == 1
    r = rels[0]
    assert r.tag_name == "v1.0.0" and r.release_id == "10" and r.prerelease is True
    assert r.assets[0].name == "a.bin" and r.assets[0].size == 123


def test_github_create_release_body():
    calls = []
    orig = subprocess.run
    def _run(args, **kwargs):
        calls.append(args)
        class P:
            returncode = 0
            stdout = '{"id":99}'
            stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        info = ReleaseInfo(tag_name="v2", name="v2", body="x", draft=False, prerelease=False)
        c.create_release("o", "r", "tok", info)
    finally:
        subprocess.run = orig
    cmd = " ".join(calls[0])
    assert "api.github.com/repos/o/r/releases" in cmd
    assert "Authorization: Bearer tok" in cmd
    assert '"tag_name": "v2"' in cmd


def test_github_upload_asset_url():
    calls = []
    orig = subprocess.run
    def _run(args, **kwargs):
        calls.append(args)
        class P:
            returncode = 0
            stdout = '{"id":5,"name":"a.bin","size":10}'
            stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        c.upload_asset("o", "r", "tok", "99", __import__("pathlib").Path("/tmp/a.bin"), "a.bin")
    finally:
        subprocess.run = orig
    cmd = " ".join(calls[0])
    assert "releases/99/assets?name=a.bin" in cmd
    assert "application/octet-stream" in cmd


def test_github_create_release_sets_id():
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0; stdout = '{"id":99}'; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        info = ReleaseInfo(tag_name="v2", name="v2", body="x")
        res = c.create_release("o", "r", "tok", info)
    finally:
        subprocess.run = orig
    assert res.release_id == "99"

def test_github_get_release_by_tag_found():
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0
            stdout = '{"tag_name":"v1","name":"v1","id":10,"assets":[{"name":"a.bin","size":5,"browser_download_url":"u","id":1}]}'
            stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        r = c.get_release_by_tag("o", "r", "v1", "tok")
    finally:
        subprocess.run = orig
    assert r is not None and r.release_id == "10" and r.assets[0].name == "a.bin"

def test_github_get_release_by_tag_not_found():
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0; stdout = '{"message":"Not Found"}'; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        r = c.get_release_by_tag("o", "r", "missing", "tok")
    finally:
        subprocess.run = orig
    assert r is None

def test_github_get_release_by_tag_transport_error():
    import pytest
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 1; stdout = ""; stderr = "boom"
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        with pytest.raises(ReleaseSyncError):
            c.get_release_by_tag("o", "r", "v1", "tok")
    finally:
        subprocess.run = orig

def test_github_update_release():
    calls = []
    orig = subprocess.run
    def _run(args, **kwargs):
        calls.append(args)
        class P:
            returncode = 0; stdout = '{"id":10}'; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        info = ReleaseInfo(tag_name="v1", name="new", body="b", release_id="10")
        c.update_release("o", "r", "tok", info)
    finally:
        subprocess.run = orig
    cmd = " ".join(calls[0])
    assert "releases/10" in cmd and "PATCH" in cmd
    assert '"name": "new"' in cmd and '"body": "b"' in cmd

def test_github_download_asset_ok():
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0; stdout = ""; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        dest = Path("/tmp/relsync_a.bin")
        res = c.download_asset(AssetInfo("a.bin", 1, "http://x/a.bin"), "tok", dest)
    finally:
        subprocess.run = orig
    assert res == dest

def test_github_download_asset_fail():
    import pytest
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 1; stdout = "err"; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GitHubReleaseClient()
        with pytest.raises(ReleaseSyncError):
            c.download_asset(AssetInfo("a.bin", 1, "http://x/a.bin"), "tok", Path("/tmp/x"))
    finally:
        subprocess.run = orig
