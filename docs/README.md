# Git Multi-Sync Center

A centralized Git repository sync system using GitHub Actions. Synchronize
branches between GitHub, Gitee, CNB, and GitCode — manually, on push, or on
a schedule.

## Features

- **Multi-platform**: GitHub, Gitee, CNB, GitCode
- **Free topology**: any-to-any, one-to-many, configurable per endpoint
- **Mixed auth**: SSH key or Personal Access Token per endpoint
- **Three trigger modes**: manual (`workflow_dispatch`), automatic (`repository_dispatch`), scheduled (cron)
- **Conflict-safe**: errors out if both source and target have diverged
- **YAML-driven**: all sync rules in one config file

## Quick Start

1. **Create a new GitHub repository** to host this sync center (private recommended).

2. **Copy the contents of this repo** into your new repository.

3. **Configure GitHub Secrets** in *Settings → Secrets and variables → Actions*:

   | Secret | Required When | Description |
   |--------|---------------|-------------|
   | `SSH_KEY_GITHUB` | Using SSH for GitHub | SSH private key with repo access |
   | `TOKEN_GITHUB` | Using PAT for GitHub | Personal Access Token |
   | `SSH_KEY_GITEE` | Using SSH for Gitee | SSH private key |
   | `TOKEN_GITEE` | Using PAT for Gitee | Personal Access Token |
   | `TOKEN_CNB` | Always (CNB only supports PAT) | Personal Access Token |
   | `SSH_KEY_GITCODE` | Using SSH for GitCode | SSH private key |
   | `TOKEN_GITCODE` | Using PAT for GitCode | Personal Access Token |
   | `SYNC_DISPATCH_TOKEN` | Using automatic triggers | PAT to call `repository_dispatch` API |

   Notes:
   - Each platform uses **one credential for all its repos**.
   - SSH and PAT are interchangeable for GitHub, Gitee, GitCode. CNB requires PAT.

4. **Edit `config/sync.yaml`** to define your sync topology. See the example below.

5. **Trigger a sync**:
   - *Manual*: go to Actions → Sync Repositories → Run workflow
   - *Scheduled*: edit the cron in `.github/workflows/sync.yml`
   - *Automatic*: source repos call the center via `repository_dispatch` (see below)

## Config Schema

```yaml
sync:
  settings:
    auto_create: false        # Reserved; not yet implemented
    force_push: false         # Allow non-fast-forward pushes
    delete_remote: false      # Delete target branches that no longer exist on source
    mode: mirror                  # mirror | rebase
    preserve_files:               # rebase 模式保留的目标特有文件
      - .cnb.yml

  topology:
    - name: "github-to-cnb"
      mode: rebase                # 覆盖全局设置（可选）
      preserve_files:             # 覆盖全局列表（可选）
        - .cnb.yml
        - Dockerfile
      source:
        platform: github                # github | gitee | cnb | gitcode
        owner: myorg
        repo: myproject
        branch: main
        auth: ssh                       # ssh (default) | pat
      targets:
        - platform: cnb
          owner: myorg
          repo: myproject
          branch: main
```

### One-to-Many (broadcast)

```yaml
- name: "broadcast"
  source:
    platform: github
    owner: myorg
    repo: myproject
    branch: main
    auth: ssh
  targets:
    - { platform: gitee, owner: myorg, repo: myproject, branch: main, auth: ssh }
    - { platform: gitcode, owner: myorg, repo: myproject, branch: main, auth: pat }
    - { platform: cnb, owner: myteam, repo: myproject, branch: main, auth: pat }
```

## Automatic Triggers (from source repos)

In each source repository, add `.github/workflows/trigger-sync.yml`:

```yaml
name: Trigger Center Sync
on:
  push:
    branches: [main]

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger
        run: |
          curl -X POST \
            -H "Authorization: token ${{ secrets.SYNC_DISPATCH_TOKEN }}" \
            https://api.github.com/repos/YOUR-ORG/multi-sync-center/dispatches \
            -d '{"event_type": "sync-triggered"}'
```

Configure `SYNC_DISPATCH_TOKEN` in the source repo (same PAT as in the center).

## Behavior

- **One-way only**: source → targets. Bi-directional sync is not supported.
- **Conflict detection (default)**: if both source and target have advanced past
  their merge base, sync **fails** with a clear error. Resolve manually — or set
  `force_push: true` to skip the check and push with `--force` (the target's
  divergent commits are overwritten). Use `force_push` only when you intend to
  make the target match the source exactly.
- **`force_push`**: when `true`, the divergence/conflict check is skipped and the
  source branch is force-pushed. When `false` (default), a diverged target aborts
  the sync.
- **`delete_remote`**: when `true`, after pushing, any branch that *already
  existed* on the target (before this sync) but is **not** the branch being
  synced is deleted from the target. This makes the target a strict mirror of the
  synced branch. The branch you are syncing is never deleted. **DANGEROUS** — opt
  in only when you want to discard stale target branches. Defaults to `false`.
- **No auto-create (`auto_create`)**: reserved for a future release; target
  repositories must exist today. Set them up beforehand.
- **No Releases sync**: only branches and tags.

### Rebase 模式

设置 `mode: rebase` 后，源的提交会在目标当前状态之上重放（rebase），而非直接覆盖。

**适用场景：** 从 GitHub 同步到 CNB 时保留 `.cnb.yml` 等平台特有配置文件。

**行为：**
- 源的提交按顺序应用到目标分支之上
- 目标特有的文件（源没有的文件）自然保留
- `preserve_files` 列表中的文件会在 rebase 前后做备份/恢复，防止源意外删除或覆盖
- Rebase 冲突时跳过该条目，不中止整体流程
- **注意：** `force_push` 和 `delete_remote` 设置在 rebase 模式下被忽略 — push 始终使用 `--force`（因为 rebase 改写历史），分支清理由 rebase 机制自身保证。

## Limitations

- **Multiple SSH platforms**: the workflow writes SSH key to `~/.ssh/id_rsa`
  (one key per host). If you configure SSH for both GitHub and Gitee, only
  the first key is written. Workaround: use PAT for one of them.
- **Target must exist**: `auto_create` is reserved for a future release.

## Development

```bash
pip install -r requirements.txt
pytest
```

## Architecture

See `docs/superpowers/specs/2026-06-19-multi-sync-center-design.md` for the
full design document.