"""Release sync engine: sync release metadata + assets across platforms via REST APIs."""
from __future__ import annotations

import fnmatch
import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AssetInfo:
    name: str
    size: int  # bytes
    download_url: str
    asset_id: str | None = None


@dataclass
class ReleaseInfo:
    tag_name: str
    name: str | None = None
    body: str | None = None
    draft: bool = False
    prerelease: bool = False
    release_id: str | None = None
    assets: list[AssetInfo] = field(default_factory=list)
    published_at: str | None = None  # ISO string, used for `latest` ordering


@dataclass
class ReleaseFilter:
    mode: str = "all"  # all | latest | pattern | tags
    latest_count: int = 1
    pattern: str | None = None
    tags: list[str] | None = None
    include_drafts: bool = False


@dataclass
class ReleaseSyncResult:
    releases_created: int = 0
    releases_updated: int = 0
    releases_skipped: int = 0
    assets_uploaded: int = 0
    assets_skipped: int = 0
    warnings: list[str] = field(default_factory=list)  # non-fatal (skip-level)
    errors: list[str] = field(default_factory=list)      # fatal (target-level)


class ReleaseSyncError(Exception):
    """Carries platform/repo context for a failed release API call."""


class ReleaseClient(ABC):
    """Abstract base for per-platform release API clients (registered in later Tasks)."""

    platform: str = ""

    @abstractmethod
    def list_releases(self, owner, repo, token) -> list[ReleaseInfo]:
        ...

    @abstractmethod
    def get_release_by_tag(self, owner, repo, tag, token) -> ReleaseInfo | None:
        ...

    @abstractmethod
    def create_release(self, owner, repo, token, info: ReleaseInfo) -> ReleaseInfo:
        ...

    @abstractmethod
    def update_release(self, owner, repo, token, info: ReleaseInfo) -> ReleaseInfo:
        ...

    @abstractmethod
    def download_asset(self, asset: AssetInfo, token, dest: Path) -> Path:
        ...

    @abstractmethod
    def upload_asset(self, owner, repo, token, release_id, path: Path, name: str) -> AssetInfo:
        ...


def filter_releases(releases: list[ReleaseInfo], rf: ReleaseFilter) -> list[ReleaseInfo]:
    out = [r for r in releases if (not r.draft) or rf.include_drafts]  # 全局 draft 门控
    if rf.mode == "all":
        return out
    if rf.mode == "latest":
        ordered = sorted(out, key=lambda r: r.published_at or "", reverse=True)  # None -> "" treated as oldest
        return ordered[: max(1, rf.latest_count)]  # at least 1
    if rf.mode == "pattern":
        if not rf.pattern:
            return out
        return [r for r in out if fnmatch.fnmatch(r.tag_name, rf.pattern)]
    if rf.mode == "tags":
        if not rf.tags:
            return out
        wanted = set(rf.tags)
        return [r for r in out if r.tag_name in wanted]
    raise ValueError(f"unknown filter mode: {rf.mode!r}")


RELEASE_CLIENTS: dict[str, type[ReleaseClient]] = {}


def supports_releases(platform: str) -> bool:
    return platform in RELEASE_CLIENTS


def _curl_json(args: list[str]) -> tuple[int, str]:
    # 返回 (returncode, 原始 stdout 文本)
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout


def _json_list(text: str) -> list:
    return json.loads(text) if text.strip().startswith("[") else []


def _json_obj(text: str) -> dict:
    return json.loads(text) if text.strip().startswith("{") else {}


def _asset_from_json(a: dict) -> "AssetInfo":
    return AssetInfo(
        name=a.get("name", ""),
        size=int(a.get("size", 0)),
        download_url=a.get("browser_download_url", "") or a.get("download_url", ""),
        asset_id=str(a.get("id")) if a.get("id") is not None else None,
    )


def _release_from_json(it: dict, fallback_tag: str = "") -> "ReleaseInfo":
    return ReleaseInfo(
        tag_name=it.get("tag_name", fallback_tag),
        name=it.get("name"),
        body=it.get("body"),
        draft=bool(it.get("draft", False)),
        prerelease=bool(it.get("prerelease", False)),
        release_id=str(it.get("id")) if it.get("id") is not None else None,
        published_at=it.get("published_at") or it.get("created_at"),
        assets=[_asset_from_json(a) for a in it.get("assets", [])],
    )


class GitHubReleaseClient(ReleaseClient):
    platform = "github"

    def _hdr(self, token: str) -> list[str]:
        return ["-H", f"Authorization: Bearer {token}", "-H", "Content-Type: application/json"]

    def list_releases(self, owner, repo, token):
        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url] + self._hdr(token))
        if rc != 0:
            raise ReleaseSyncError(f"github list_releases failed (rc={rc})")
        return [_release_from_json(it) for it in _json_list(out)]

    def get_release_by_tag(self, owner, repo, tag, token):
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url] + self._hdr(token))
        if rc != 0:
            raise ReleaseSyncError(f"github get_release_by_tag {tag} failed (rc={rc}): {out}")
        it = _json_obj(out)
        if not it or "id" not in it:
            return None  # 404 / 不存在
        return _release_from_json(it, fallback_tag=tag)

    def create_release(self, owner, repo, token, info):
        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        body = json.dumps({
            "tag_name": info.tag_name, "name": info.name, "body": info.body,
            "draft": info.draft, "prerelease": info.prerelease,
        })
        rc, out = _curl_json(["curl", "-s", "-X", "POST", url, "--data", body] + self._hdr(token))
        if rc != 0:
            raise ReleaseSyncError(f"github create_release {info.tag_name} failed: {out}")
        it = _json_obj(out)
        info.release_id = str(it.get("id"))
        return info

    def update_release(self, owner, repo, token, info):
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/{info.release_id}"
        body = json.dumps({"name": info.name, "body": info.body,
                           "draft": info.draft, "prerelease": info.prerelease})
        rc, out = _curl_json(["curl", "-s", "-X", "PATCH", url, "--data", body] + self._hdr(token))
        if rc != 0:
            raise ReleaseSyncError(f"github update_release {info.tag_name} failed: {out}")
        return info

    def download_asset(self, asset, token, dest):
        rc, out = _curl_json([
            "curl", "-s", "-L", "-H", f"Authorization: Bearer {token}",
            "-o", str(dest), asset.download_url,
        ])
        if rc != 0:
            raise ReleaseSyncError(f"github download_asset {asset.name} failed: {out}")
        return dest

    def upload_asset(self, owner, repo, token, release_id, path, name):
        url = f"https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?name={name}"
        rc, out = _curl_json([
            "curl", "-s", "-X", "POST", url,
            "-H", f"Authorization: Bearer {token}",
            "-H", "Content-Type: application/octet-stream",
            "--data-binary", f"@{path}",
        ])
        if rc != 0:
            raise ReleaseSyncError(f"github upload_asset {name} failed: {out}")
        it = _json_obj(out)
        return AssetInfo(name=it.get("name", name), size=int(it.get("size", 0)),
                         download_url=it.get("browser_download_url", ""), asset_id=str(it.get("id")))


RELEASE_CLIENTS["github"] = GitHubReleaseClient


class GiteeReleaseClient(ReleaseClient):
    platform = "gitee"

    def _base(self, owner, repo):
        return f"https://gitee.com/api/v5/repos/{owner}/{repo}"

    def list_releases(self, owner, repo, token):
        url = f"{self._base(owner, repo)}/releases?access_token={token}&per_page=100"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url])
        if rc != 0:
            raise ReleaseSyncError(f"gitee list_releases failed (rc={rc})")
        return [_release_from_json(it) for it in _json_list(out)]

    def get_release_by_tag(self, owner, repo, tag, token):
        url = f"{self._base(owner, repo)}/releases/tags/{tag}?access_token={token}"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url])
        if rc != 0:
            raise ReleaseSyncError(f"gitee get_release_by_tag {tag} failed (rc={rc}): {out}")
        it = _json_obj(out)
        if not it or "id" not in it:
            return None
        return _release_from_json(it, fallback_tag=tag)

    def create_release(self, owner, repo, token, info):
        # Gitee has no draft field; only prerelease is supported.
        url = f"{self._base(owner, repo)}/releases?access_token={token}"
        body = json.dumps({
            "access_token": token, "tag_name": info.tag_name, "name": info.name,
            "body": info.body, "prerelease": info.prerelease,
        })
        rc, out = _curl_json(["curl", "-s", "-X", "POST", url, "--data", body])
        if rc != 0:
            raise ReleaseSyncError(f"gitee create_release {info.tag_name} failed: {out}")
        info.release_id = str(_json_obj(out).get("id"))
        return info

    def update_release(self, owner, repo, token, info):
        # Gitee has no draft field; only prerelease is supported.
        url = f"{self._base(owner, repo)}/releases/{info.release_id}?access_token={token}"
        body = json.dumps({"name": info.name, "body": info.body, "prerelease": info.prerelease})
        rc, out = _curl_json(["curl", "-s", "-X", "PATCH", url, "--data", body])
        if rc != 0:
            raise ReleaseSyncError(f"gitee update_release {info.tag_name} failed: {out}")
        return info

    def download_asset(self, asset, token, dest):
        url = asset.download_url
        if "access_token" not in url:
            url = url + ("&" if "?" in url else "?") + f"access_token={token}"
        rc, out = _curl_json(["curl", "-s", "-L", "-o", str(dest), url])
        if rc != 0:
            raise ReleaseSyncError(f"gitee download_asset {asset.name} failed: {out}")
        return dest

    def upload_asset(self, owner, repo, token, release_id, path, name):
        url = f"{self._base(owner, repo)}/releases/{release_id}/attach_files?access_token={token}"
        rc, out = _curl_json(["curl", "-s", "-X", "POST", url, "-F", f"file=@{path}"])
        if rc != 0:
            raise ReleaseSyncError(f"gitee upload_asset {name} failed: {out}")
        it = _json_obj(out)
        data = it.get("data", it)
        if isinstance(data, list):
            data = data[0] if data else {}
        return _asset_from_json(data)


RELEASE_CLIENTS["gitee"] = GiteeReleaseClient


class CNBReleaseClient(ReleaseClient):
    platform = "cnb"

    def _base(self, owner, repo):
        return f"https://api.cnb.cool/{owner}/{repo}"

    def list_releases(self, owner, repo, token):
        url = f"{self._base(owner, repo)}/releases"
        rc, out = _curl_json(["curl", "-s", "-X", "GET", url,
                              "-H", f"Authorization: Bearer {token}"])
        if rc != 0:
            raise ReleaseSyncError(f"cnb list_releases failed (rc={rc})")
        it = _json_obj(out)
        if "message" in it:
            return []  # 平台不支持 release API -> 优雅降级为空
        items = it.get("data", it if isinstance(it, list) else [])
        return [_release_from_json(r) for r in items]

    def get_release_by_tag(self, owner, repo, tag, token):
        for r in self.list_releases(owner, repo, token):
            if r.tag_name == tag:
                return r
        return None

    def create_release(self, owner, repo, token, info):
        import json
        url = f"{self._base(owner, repo)}/releases"
        body = json.dumps({"tag_name": info.tag_name, "name": info.name,
                           "body": info.body, "draft": info.draft, "prerelease": info.prerelease})
        rc, out = _curl_json(["curl", "-s", "-X", "POST", url,
                              "-H", f"Authorization: Bearer {token}",
                              "-H", "Content-Type: application/json", "--data", body])
        if rc != 0:
            raise ReleaseSyncError(f"cnb create_release {info.tag_name} failed: {out}")
        info.release_id = str(_json_obj(out).get("id"))
        return info

    def update_release(self, owner, repo, token, info):
        import json
        url = f"{self._base(owner, repo)}/releases/{info.release_id}"
        body = json.dumps({"name": info.name, "body": info.body,
                           "draft": info.draft, "prerelease": info.prerelease})
        rc, out = _curl_json(["curl", "-s", "-X", "PATCH", url,
                              "-H", f"Authorization: Bearer {token}",
                              "-H", "Content-Type: application/json", "--data", body])
        if rc != 0:
            raise ReleaseSyncError(f"cnb update_release {info.tag_name} failed: {out}")
        return info

    def download_asset(self, asset, token, dest):
        rc, out = _curl_json(["curl", "-s", "-L", "-H", f"Authorization: Bearer {token}",
                             "-o", str(dest), asset.download_url])
        if rc != 0:
            raise ReleaseSyncError(f"cnb download_asset {asset.name} failed: {out}")
        return dest

    def upload_asset(self, owner, repo, token, release_id, path, name):
        url = f"{self._base(owner, repo)}/releases/{release_id}/assets"
        rc, out = _curl_json(["curl", "-s", "-X", "POST", url,
                              "-H", f"Authorization: Bearer {token}",
                              "-F", f"file=@{path}"])
        if rc != 0:
            raise ReleaseSyncError(f"cnb upload_asset {name} failed: {out}")
        return _asset_from_json(_json_obj(out))


class GitCodeReleaseClient(GiteeReleaseClient):
    """GitCode 的 release API 与 Gitee v5 近似；复用 Gitee 实现并确保端点前缀正确。"""
    platform = "gitcode"

    def _base(self, owner, repo):
        return f"https://api.gitcode.com/api/v5/repos/{owner}/{repo}"


RELEASE_CLIENTS["cnb"] = CNBReleaseClient
RELEASE_CLIENTS["gitcode"] = GitCodeReleaseClient
