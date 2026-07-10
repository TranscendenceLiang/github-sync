"""Repository auto-creation via platform REST APIs."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


class CreateRepoError(Exception):
    """Raised when repository creation fails."""


@dataclass
class CreateRepoRequest:
    platform: str   # github | gitee | cnb | gitcode
    owner: str      # Organization or user path
    repo: str       # Repository name
    visibility: str  # "public" | "private"
    token: str      # API token (PAT)


def create_repo(request: CreateRepoRequest) -> None:
    """Create a repository on the target platform via curl.

    Raises CreateRepoError on failure.
    """
    if request.platform == "github":
        url = "https://api.github.com/user/repos"
        headers = [
            "-H", f"Authorization: Bearer {request.token}",
            "-H", "Content-Type: application/json",
        ]
        body = json.dumps({
            "name": request.repo,
            "private": request.visibility == "private",
        })
    elif request.platform == "gitee":
        url = "https://gitee.com/api/v5/user/repos"
        headers = ["-H", "Content-Type: application/json"]
        body = json.dumps({
            "access_token": request.token,
            "name": request.repo,
            "private": request.visibility == "private",
        })
    elif request.platform == "cnb":
        url = "https://api.cnb.cool/repos"
        headers = [
            "-H", f"Authorization: Bearer {request.token}",
            "-H", "Content-Type: application/json",
        ]
        body = json.dumps({
            "slug": request.owner,
            "name": request.repo,
            "visibility": request.visibility,
        })
    elif request.platform == "gitcode":
        url = f"https://api.gitcode.com/api/v5/user/repos?access_token={request.token}"
        headers = ["-H", "Content-Type: application/json"]
        body = json.dumps({
            "name": request.repo,
            "path": request.repo,
        })
    else:
        raise CreateRepoError(f"unsupported platform: {request.platform!r}")

    proc = subprocess.run(
        ["curl", "-s", "-X", "POST", url] + headers + ["--data", body],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise CreateRepoError(
            f"failed to create repo on {request.platform}: "
            f"curl exit={proc.returncode}, stderr={proc.stderr.strip()}"
        )
    # Some APIs return non-zero for errors, some always return 0 with error in body.
    # Check for common error indicators in response body.
    resp = proc.stdout.strip()
    if resp and resp.startswith("{"):
        try:
            parsed = json.loads(resp)
        except json.JSONDecodeError:
            pass
        else:
            errcode = parsed.get("errcode") or parsed.get("code")
            errmsg = parsed.get("errmsg") or parsed.get("message") or parsed.get("error")
            if errcode or (errmsg and "not found" not in errmsg.lower()):
                raise CreateRepoError(
                    f"failed to create repo on {request.platform}: "
                    f"errcode={errcode}, errmsg={errmsg}"
                )
