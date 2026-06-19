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

  topology:
    - name: "github-to-gitee"           # Unique name
      source:
        platform: github                # github | gitee | cnb | gitcode
        owner: myorg
        repo: myproject
        branch: main
        auth: ssh                       # ssh (default) | pat
      targets:
        - platform: gitee
          owner: myorg
          repo: myproject
          branch: main
          auth: ssh
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
- **Conflict detection**: if both source and target have advanced past their
  merge base, sync **fails** with a clear error. Resolve manually.
- **No auto-create**: target repositories must exist. Set them up beforehand.
- **No Releases sync**: only branches and tags.

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