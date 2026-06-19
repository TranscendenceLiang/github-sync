"""Credential loading from environment variables / GitHub Secrets.

Each platform's credentials are stored in GitHub Secrets and exposed to the
runner as environment variables. This module loads them into a dict keyed by
platform name.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.platform import SUPPORTED_PLATFORMS

# Maps (platform, auth) -> env var name holding the secret.
_SECRET_NAMES = {
    ("github", "ssh"): "SSH_KEY_GITHUB",
    ("github", "pat"): "TOKEN_GITHUB",
    ("gitee", "ssh"): "SSH_KEY_GITEE",
    ("gitee", "pat"): "TOKEN_GITEE",
    ("cnb", "ssh"): None,  # CNB does not support SSH
    ("cnb", "pat"): "TOKEN_CNB",
    ("gitcode", "ssh"): "SSH_KEY_GITCODE",
    ("gitcode", "pat"): "TOKEN_GITCODE",
}


class CredentialError(Exception):
    """Raised when required credentials are missing."""


@dataclass
class Credential:
    """Credentials for a single platform."""
    ssh_key: str | None = None
    pat: str | None = None

    @property
    def has_ssh(self) -> bool:
        return bool(self.ssh_key)

    @property
    def has_pat(self) -> bool:
        return bool(self.pat)


def get_secret_name(platform: str, auth: str) -> str:
    """Return the env var / Secret name for the given platform + auth method."""
    key = (platform, auth)
    if key not in _SECRET_NAMES:
        raise ValueError(f"unknown platform/auth combo: {platform}/{auth}")
    name = _SECRET_NAMES[key]
    if name is None:
        raise ValueError(f"{platform} does not support auth method {auth}")
    return name


def load_credentials(required: set[str] | None = None) -> dict[str, Credential]:
    """Load all platform credentials from environment.

    Args:
        required: If given, raise CredentialError when a platform in this set
            has neither an SSH key nor a PAT set.

    Returns:
        Mapping platform -> Credential.
    """
    creds: dict[str, Credential] = {}
    for platform in SUPPORTED_PLATFORMS:
        ssh_name = _SECRET_NAMES.get((platform, "ssh"))
        ssh = os.environ.get(ssh_name, "") if ssh_name else None
        ssh = ssh or None
        pat = os.environ.get(get_secret_name(platform, "pat"), "") or None
        creds[platform] = Credential(ssh_key=ssh, pat=pat)

    if required:
        missing = [p for p in required if not (creds[p].has_ssh or creds[p].has_pat)]
        if missing:
            raise CredentialError(
                f"missing credentials for platform(s): {', '.join(missing)}. "
                f"Set the corresponding GitHub Secret (see docs/README.md)."
            )

    return creds