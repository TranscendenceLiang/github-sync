"""Platform URL builders and constants.

Each supported Git platform has a known URL pattern for SSH and HTTPS+PAT
authentication. CNB only supports HTTPS+PAT; all others support both.
"""
from __future__ import annotations

SUPPORTED_PLATFORMS: set[str] = {"github", "gitee", "cnb", "gitcode"}

# SSH templates use {owner} and {repo}; no host substitution.
_SSH_TEMPLATES = {
    "github": "git@github.com:{owner}/{repo}.git",
    "gitee": "git@gitee.com:{owner}/{repo}.git",
    "gitcode": "git@gitcode.com:{owner}/{repo}.git",
}

# HTTPS templates use {owner}, {repo}, {token}.
_HTTPS_TEMPLATES = {
    "github": "https://x-access-token:{token}@github.com/{owner}/{repo}.git",
    "gitee": "https://{token}@gitee.com/{owner}/{repo}.git",
    "cnb": "https://cnb:{token}@cnb.cool/{owner}/{repo}",
    "gitcode": "https://{token}@gitcode.com/{owner}/{repo}.git",
}


def normalize_platform(platform: str) -> str:
    """Lowercase and trim a platform name."""
    return platform.strip().lower()


def build_url(platform: str, owner: str, repo: str, auth: str, token: str | None = None) -> str:
    """Build a clone URL for the given platform.

    Args:
        platform: One of SUPPORTED_PLATFORMS (case-insensitive).
        owner: Repository owner (user or org).
        repo: Repository name.
        auth: 'ssh' or 'pat'.
        token: Personal Access Token. Required when auth='pat'.

    Returns:
        A URL string ready for `git clone`.

    Raises:
        ValueError: For unsupported platform, invalid auth, or missing token.
    """
    p = normalize_platform(platform)
    if p not in SUPPORTED_PLATFORMS:
        raise ValueError(f"unsupported platform: {platform!r}")

    if auth not in ("ssh", "pat"):
        raise ValueError(f"auth must be 'ssh' or 'pat', got {auth!r}")

    if p == "cnb" and auth == "ssh":
        raise ValueError("CNB does not support SSH authentication")

    if auth == "pat":
        if not token:
            raise ValueError("token required for PAT auth")
        template = _HTTPS_TEMPLATES[p]
        return template.format(owner=owner, repo=repo, token=token)

    template = _SSH_TEMPLATES[p]
    return template.format(owner=owner, repo=repo)