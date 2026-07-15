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
    auto_create: false        # 全局开关，false（默认）不自动创建，可在 target 级别覆盖
    force_push: false         # Allow non-fast-forward pushes
    delete_remote: false      # Delete target branches that no longer exist on source
    mode: mirror                  # mirror | rebase
    preserve_files:               # rebase 模式保留的目标特有文件
      - .cnb.yml
    sync_releases: false          # 全局总开关：同步源平台 Release 到各目标（默认关）
    release_asset_max_size_mb: 50 # 单附件大小上限（MB），超限跳过 + 告警
    release_filter:               # 全局默认筛选（见「Release 同步」一节）
      mode: all                   # all | latest | pattern | tags
      latest_count: 1             # mode=latest 时取最近 N 个
      pattern: "v*.*.*"          # mode=pattern：fnmatch glob 匹配 tag_name
      tags: [v1.0.0, v2.0.0]      # mode=tags：显式 tag 白名单
      include_drafts: false       # 是否同步草稿 Release

  topology:
    - name: "github-to-cnb"
      mode: rebase                # 覆盖全局设置（可选）
      preserve_files:             # 覆盖全局列表（可选）
        - .cnb.yml
        - Dockerfile
      sync_releases: false        # 条目级覆盖全局总开关（可关）
      release_filter:             # 条目级覆盖全局筛选（可选）
        mode: pattern
        pattern: "v*"
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
          auto_create: true      # 覆盖全局 false
          visibility: private    # private（默认）| public
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
- **Auto-create (`auto_create`)**: when `true` and the target repository does not exist, the system creates it automatically before syncing. See [Auto-Create](#auto-create) below.
- **Releases sync (`sync_releases`)**: when `true`, source-platform releases (metadata + attachment assets) are synced to each target after branch sync. Off by default — see [Release 同步](#release-同步) below.

### Rebase 模式

设置 `mode: rebase` 后，源的提交会在目标当前状态之上重放（rebase），而非直接覆盖。

**适用场景：** 从 GitHub 同步到 CNB 时保留 `.cnb.yml` 等平台特有配置文件。

**行为：**
- 源的提交按顺序应用到目标分支之上
- 目标特有的文件（源没有的文件）自然保留
- `preserve_files` 列表中的文件会在 rebase 前后做备份/恢复，防止源意外删除或覆盖
- Rebase 冲突时跳过该条目，不中止整体流程
- **注意：** `force_push` 和 `delete_remote` 设置在 rebase 模式下被忽略 — push 始终使用 `--force`（因为 rebase 改写历史），分支清理由 rebase 机制自身保证。

### Auto-Create

设置 `auto_create: true` 后，当目标仓库不存在时，系统会自动调用平台 API 创建仓库后再执行同步。

- **GitHub**: `POST /user/repos` (Bearer token)
- **Gitee**: `POST /api/v5/user/repos` (access_token)
- **CNB**: `POST /repos` (Bearer token)
- **GitCode**: `POST /api/v5/user/repos` (access_token)

创建仓库使用 PAT 认证，即使目标平台配置了 SSH 认证。`visibility` 字段控制仓库可见性。

## Limitations

- **Multiple SSH platforms**: the workflow writes SSH key to `~/.ssh/id_rsa`
  (one key per host). If you configure SSH for both GitHub and Gitee, only
  the first key is written. Workaround: use PAT for one of them.
- **Auto-create**: set `auto_create: true` on a target to have it created automatically. See [Auto-Create](#auto-create) for details.

## Release 同步

设置 `settings.sync_releases: true` 后，分支同步完成后再把源平台的 **Release**（发布元数据 + 附件资产）同步到每个目标平台。默认关（`false`），开启前与现有行为完全一致、零影响。

- **触发时机**：在分支同步之后、按 topology 条目逐条执行。
- **四平台支持与优雅降级**：GitHub / Gitee 完整实现（列表 / 创建 / 更新 / 资产上传）。CNB / GitCode 为尽力而为（best-effort）——若该平台 release API 不可用，则告警并跳过该目标，不计入失败。
- **筛选 `release_filter`**（四种 `mode`）：
  - `all`：全量同步；
  - `latest`：按发布时间倒序取最近 `latest_count` 个；
  - `pattern`：用 `fnmatch` glob 匹配 `tag_name`；
  - `tags`：仅同步 `tags` 白名单内的 tag。
  - `include_drafts`：草稿 Release 默认**排除**（全局、在 mode 过滤之前先剔除）；设为 `true` 才同步。
  - 被过滤掉的 Release 不会触发任何资产下载，节省带宽。
- **资产同步**：单附件超过 `release_asset_max_size_mb`（默认 50MB）则跳过并告警；单个资产下载 / 上传失败仅记告警并继续其他资产与其他目标（失败隔离）。目标已有同名资产则跳过重传。
- **幂等**：按 `tag_name` 唯一标识，目标已有同 tag 的 Release 则 `update_release` 刷新，否则 `create_release`。

条目级可用 `sync_releases` / `release_filter` 覆盖全局设置（不设则继承）。

```yaml
sync:
  settings:
    sync_releases: true              # 全局总开关（默认 false）
    release_asset_max_size_mb: 50    # 单附件大小上限（MB）
    release_filter:                  # 全局默认筛选
      mode: all                      # all | latest | pattern | tags
      latest_count: 1                # mode=latest 时取最近 N 个
      pattern: "v*.*.*"             # mode=pattern：fnmatch glob 匹配 tag_name
      tags: [v1.0.0, v2.0.0]        # mode=tags：显式 tag 白名单
      include_drafts: false          # 是否同步草稿 release

  topology:
    - name: "github-to-cnb"
      sync_releases: false           # 条目级覆盖全局（可关）
      release_filter:                # 条目级覆盖全局筛选（可选）
        mode: pattern
        pattern: "v*"
      source:
        platform: github
        owner: myorg
        repo: myproject
        branch: main
      targets:
        - platform: cnb
          owner: myorg
          repo: myproject
          branch: main
```


## Development

```bash
pip install -r requirements.txt
pytest
```

## Architecture

See `docs/superpowers/specs/2026-06-19-multi-sync-center-design.md` for the
full design document.

## WebUI

Web 控制台（FastAPI 纯 API + Svelte 5 SPA）的开发、构建、测试与端口说明见
[docs/webui.md](webui.md)。