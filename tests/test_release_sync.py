"""Tests for release_sync module (data model + filter_releases)."""
from pathlib import Path

from src.release_sync import (
    AssetInfo,
    CNBReleaseClient,
    GiteeReleaseClient,
    GitHubReleaseClient,
    GitCodeReleaseClient,
    ReleaseClient,
    ReleaseFilter,
    ReleaseInfo,
    ReleaseSyncError,
    ReleaseSyncResult,
    filter_releases,
    supports_releases,
    sync_releases,
)
from src.credential import Credential
from src.config import SyncSettings, TopologyEntry, Endpoint


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

def test_gitee_list_releases_uses_token():
    sample = '[{"tag_name":"v1.0.0","name":"v1","body":"b","prerelease":false,' \
             '"id":7,"created_at":"2024-01-01T00:00:00Z",' \
             '"assets":[{"name":"a.bin","size":9,"browser_download_url":"http://x/a.bin","id":2}]}]'
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0; stdout = sample; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GiteeReleaseClient()
        rels = c.list_releases("o", "r", "tok")
    finally:
        subprocess.run = orig
    assert rels[0].tag_name == "v1.0.0"
    assert rels[0].assets[0].size == 9

def test_gitee_create_release_url():
    calls = []
    orig = subprocess.run
    def _run(args, **kwargs):
        calls.append(args)
        class P:
            returncode = 0; stdout = '{"id":8}'; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GiteeReleaseClient()
        res = c.create_release("o", "r", "tok", ReleaseInfo(tag_name="v2"))
    finally:
        subprocess.run = orig
    cmd = " ".join(calls[0])
    assert "gitee.com/api/v5/repos/o/r/releases" in cmd
    assert "access_token=tok" in cmd
    assert res.release_id == "8"

def test_gitee_update_release():
    calls = []
    orig = subprocess.run
    def _run(args, **kwargs):
        calls.append(args)
        class P:
            returncode = 0; stdout = '{"id":10}'; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GiteeReleaseClient()
        info = ReleaseInfo(tag_name="v1", name="new", body="b", release_id="10")
        c.update_release("o", "r", "tok", info)
    finally:
        subprocess.run = orig
    cmd = " ".join(calls[0])
    assert "gitee.com/api/v5/repos/o/r/releases/10" in cmd and "PATCH" in cmd
    assert '"name": "new"' in cmd and '"body": "b"' in cmd

def test_gitee_get_release_by_tag_not_found():
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0; stdout = '{"message":"404 Not Found"}'; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GiteeReleaseClient()
        r = c.get_release_by_tag("o", "r", "missing", "tok")
    finally:
        subprocess.run = orig
    assert r is None

def test_gitee_get_release_by_tag_transport_error():
    import pytest
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 1; stdout = ""; stderr = "boom"
        return P()
    subprocess.run = _run
    try:
        c = GiteeReleaseClient()
        with pytest.raises(ReleaseSyncError):
            c.get_release_by_tag("o", "r", "v1", "tok")
    finally:
        subprocess.run = orig

def test_gitee_download_asset_appends_token():
    calls = []
    orig = subprocess.run
    def _run(args, **kwargs):
        calls.append(args)
        class P:
            returncode = 0; stdout = ""; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GiteeReleaseClient()
        c.download_asset(AssetInfo("a.bin", 1, "http://x/a.bin"), "tok", Path("/tmp/g.bin"))
    finally:
        subprocess.run = orig
    cmd = " ".join(calls[0])
    assert "access_token=tok" in cmd

def test_gitee_upload_asset():
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0
            stdout = '{"data":{"name":"a.bin","size":10,"download_url":"http://x/a.bin","id":3}}'
            stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = GiteeReleaseClient()
        a = c.upload_asset("o", "r", "tok", "10", Path("/tmp/a.bin"), "a.bin")
    finally:
        subprocess.run = orig
    assert a.name == "a.bin" and a.size == 10
    assert a.download_url == "http://x/a.bin" and a.asset_id == "3"


def test_cnb_list_returns_empty_on_message():
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0; stdout = '{"message":"Not Found"}'; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = CNBReleaseClient()
        rels = c.list_releases("o", "r", "tok")
    finally:
        subprocess.run = orig
    assert rels == []

def test_cnb_list_transport_error_raises():
    import pytest
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 1; stdout = ""; stderr = "boom"
        return P()
    subprocess.run = _run
    try:
        c = CNBReleaseClient()
        with pytest.raises(ReleaseSyncError):
            c.list_releases("o", "r", "tok")
    finally:
        subprocess.run = orig

def test_cnb_list_parses_releases():
    sample = '{"data":[{"tag_name":"v1","name":"v1","id":1,"created_at":"2024-01-01","assets":[{"name":"a.bin","size":3,"browser_download_url":"u","id":9}]}]}'
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0; stdout = sample; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = CNBReleaseClient()
        rels = c.list_releases("o", "r", "tok")
    finally:
        subprocess.run = orig
    assert len(rels) == 1 and rels[0].release_id == "1" and rels[0].assets[0].size == 3

def test_gitcode_client_registered():
    assert supports_releases("gitcode") is True

def test_gitcode_inherits_gitee_base():
    c = GitCodeReleaseClient()
    assert c._base("o", "r") == "https://api.gitcode.com/api/v5/repos/o/r"
    # 继承 Gitee 的 6 个方法
    for m in ("list_releases", "get_release_by_tag", "create_release",
              "update_release", "download_asset", "upload_asset"):
        assert callable(getattr(c, m, None))


def test_cnb_create_release_sets_id():
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0; stdout = '{"id":42}'; stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = CNBReleaseClient()
        info = ReleaseInfo(tag_name="v1", name="v1")
        res = c.create_release("o", "r", "tok", info)
    finally:
        subprocess.run = orig
    assert res.release_id == "42"

def test_cnb_upload_asset():
    orig = subprocess.run
    def _run(args, **kwargs):
        class P:
            returncode = 0
            stdout = '{"name":"a.bin","size":7,"download_url":"http://x/a.bin","id":5}'
            stderr = ""
        return P()
    subprocess.run = _run
    try:
        c = CNBReleaseClient()
        a = c.upload_asset("o", "r", "tok", "1", Path("/tmp/a.bin"), "a.bin")
    finally:
        subprocess.run = orig
    assert a.download_url == "http://x/a.bin" and a.asset_id == "5"


class _StubClient(ReleaseClient):
    platform = "github"
    def __init__(self, releases=None, by_tag=None):
        self._releases = releases or []
        self._by_tag = by_tag or {}
        self.uploaded = []
    def list_releases(self, o, r, t):
        return list(self._releases)
    def get_release_by_tag(self, o, r, tag, t):
        return self._by_tag.get(tag)
    def create_release(self, o, r, t, info):
        info.release_id = "NEW"
        return info
    def update_release(self, o, r, t, info):
        return info
    def download_asset(self, asset, t, dest):
        return dest
    def upload_asset(self, o, r, t, rid, path, name):
        self.uploaded.append(name)
        return AssetInfo(name=name, size=1, download_url="x")


def _entry(src_platform="github", tgt_platform="github", src_auth="pat", tgt_auth="pat"):
    src = Endpoint(platform=src_platform, owner="o", repo="r", branch="main", auth=src_auth)
    tgt = Endpoint(platform=tgt_platform, owner="o2", repo="r", branch="main", auth=tgt_auth)
    return TopologyEntry(name="x", source=src, targets=[tgt])


def test_sync_releases_create_new_and_upload_asset(monkeypatch):
    src_client = _StubClient(releases=[ReleaseInfo(tag_name="v1", name="v1",
                        assets=[AssetInfo("a.bin", size=10, download_url="u")])])
    tgt_client = _StubClient()  # 目标无既有 release
    def _pick(platform, role="tgt"):
        return src_client if role == "src" else tgt_client
    monkeypatch.setattr("src.release_sync._client_for", _pick)
    settings = SyncSettings(sync_releases=True)
    res = sync_releases(_entry(), {"github": Credential(pat="tok")}, settings)
    assert res.releases_created == 1
    assert res.assets_uploaded == 1


def test_sync_releases_update_existing_skips_asset(monkeypatch):
    rel = ReleaseInfo(tag_name="v1", name="v1", assets=[AssetInfo("a.bin", size=10, download_url="u")])
    src_client = _StubClient(releases=[rel])
    tgt_client = _StubClient(by_tag={"v1": ReleaseInfo(tag_name="v1", release_id="EXIST",
                                    assets=[AssetInfo("a.bin", size=10, download_url="u")])})
    def _pick(platform, role="tgt"):
        return src_client if role == "src" else tgt_client
    monkeypatch.setattr("src.release_sync._client_for", _pick)
    settings = SyncSettings(sync_releases=True)
    res = sync_releases(_entry(), {"github": Credential(pat="tok")}, settings)
    assert res.releases_updated == 1
    assert res.assets_uploaded == 0  # 同名资产已存在，跳过上传


def test_sync_releases_asset_size_cap_skip(monkeypatch):
    src_client = _StubClient(releases=[ReleaseInfo(tag_name="v1",
                        assets=[AssetInfo("big.bin", size=999 * 1024 * 1024, download_url="u")])])
    tgt_client = _StubClient()
    def _pick(platform, role="tgt"):
        return src_client if role == "src" else tgt_client
    monkeypatch.setattr("src.release_sync._client_for", _pick)
    settings = SyncSettings(sync_releases=True, release_asset_max_size_mb=50)
    res = sync_releases(_entry(), {"github": Credential(pat="tok")}, settings)
    assert res.releases_created == 1
    assert res.assets_skipped == 1
    assert res.assets_uploaded == 0


def test_sync_releases_disabled_by_default(monkeypatch):
    src_client = _StubClient(releases=[ReleaseInfo(tag_name="v1")])
    monkeypatch.setattr("src.release_sync._client_for", lambda p, role="tgt": src_client)
    settings = SyncSettings(sync_releases=False)  # 默认关
    res = sync_releases(_entry(), {"github": Credential(pat="tok")}, settings)
    assert res.releases_created == 0 and res.releases_updated == 0


def test_sync_releases_source_list_error_recorded(monkeypatch):
    class _Bad(ReleaseClient):
        platform = "github"
        def list_releases(self, o, r, t):
            raise ReleaseSyncError("boom")
        def get_release_by_tag(self, o, r, tag, t): return None
        def create_release(self, o, r, t, info): return info
        def update_release(self, o, r, t, info): return info
        def download_asset(self, asset, t, dest): return dest
        def upload_asset(self, o, r, t, rid, path, name): return AssetInfo(name=name, size=1, download_url="x")
    monkeypatch.setattr("src.release_sync._client_for", lambda p, role="tgt": _Bad())
    settings = SyncSettings(sync_releases=True)
    res = sync_releases(_entry(), {"github": Credential(pat="tok")}, settings)
    assert res.errors and "list failed" in res.errors[0]


def test_sync_releases_target_unsupported_warns(monkeypatch):
    src_client = _StubClient(releases=[ReleaseInfo(tag_name="v1")])
    monkeypatch.setattr("src.release_sync._client_for", lambda p, role="tgt": src_client)
    monkeypatch.setattr("src.release_sync.supports_releases", lambda p: False)  # 模拟目标不支持
    settings = SyncSettings(sync_releases=True)
    res = sync_releases(_entry(), {"github": Credential(pat="tok")}, settings)
    assert any("does not support releases" in w for w in res.warnings)
