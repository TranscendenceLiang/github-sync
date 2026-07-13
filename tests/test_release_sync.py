"""Tests for release_sync module (data model + filter_releases)."""
from src.release_sync import (
    AssetInfo,
    ReleaseFilter,
    ReleaseInfo,
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
