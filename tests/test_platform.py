"""Tests for platform URL building."""
import pytest

from src.platform import build_url, SUPPORTED_PLATFORMS, normalize_platform


def test_supported_platforms_contains_expected():
    assert "github" in SUPPORTED_PLATFORMS
    assert "gitee" in SUPPORTED_PLATFORMS
    assert "cnb" in SUPPORTED_PLATFORMS
    assert "gitcode" in SUPPORTED_PLATFORMS


def test_build_url_github_ssh():
    url = build_url("github", "myorg", "myrepo", auth="ssh")
    assert url == "git@github.com:myorg/myrepo.git"


def test_build_url_github_pat():
    url = build_url("github", "myorg", "myrepo", auth="pat", token="ghp_xxx")
    assert url == "https://x-access-token:ghp_xxx@github.com/myorg/myrepo.git"


def test_build_url_gitee_ssh():
    url = build_url("gitee", "myorg", "myrepo", auth="ssh")
    assert url == "git@gitee.com:myorg/myrepo.git"


def test_build_url_gitee_pat():
    url = build_url("gitee", "myorg", "myrepo", auth="pat", token="gt_xxx")
    assert url == "https://gt_xxx@gitee.com/myorg/myrepo.git"


def test_build_url_cnb_pat():
    url = build_url("cnb", "myorg", "myrepo", auth="pat", token="cnb_xxx")
    assert url == "https://cnb:cnb_xxx@cnb.cool/myorg/myrepo"


def test_build_url_cnb_ssh_raises():
    # CNB does not support SSH
    with pytest.raises(ValueError, match="CNB does not support SSH"):
        build_url("cnb", "myorg", "myrepo", auth="ssh")


def test_build_url_cnb_missing_token_raises():
    with pytest.raises(ValueError, match="token required"):
        build_url("cnb", "myorg", "myrepo", auth="pat", token=None)


def test_build_url_gitcode_ssh():
    url = build_url("gitcode", "myorg", "myrepo", auth="ssh")
    assert url == "git@gitcode.com:myorg/myrepo.git"


def test_build_url_gitcode_pat():
    url = build_url("gitcode", "myorg", "myrepo", auth="pat", token="gc_xxx")
    assert url == "https://gc_xxx@gitcode.com/myorg/myrepo.git"


def test_build_url_unknown_platform_raises():
    with pytest.raises(ValueError, match="unsupported platform"):
        build_url("unknown", "o", "r", auth="ssh")


def test_build_url_pat_missing_token_raises():
    with pytest.raises(ValueError, match="token required"):
        build_url("github", "myorg", "myrepo", auth="pat", token=None)


def test_normalize_platform_case_insensitive():
    assert normalize_platform("GitHub") == "github"
    assert normalize_platform("GITEE") == "gitee"
    assert normalize_platform("CNB") == "cnb"