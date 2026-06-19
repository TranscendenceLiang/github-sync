# Git Multi-Sync Center

A centralized Git repository sync system using GitHub Actions.

## Quick Start

1. Create a new repository to host this center
2. Configure GitHub Secrets for your platforms (see "Configuration" below)
3. Edit `config/sync.yaml` to define your sync topology
4. Trigger via Actions tab, `repository_dispatch`, or schedule

## Configuration

### GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `SSH_KEY_GITHUB` | SSH private key for GitHub (or `TOKEN_GITHUB`) |
| `SSH_KEY_GITEE` | SSH private key for Gitee (or `TOKEN_GITEE`) |
| `TOKEN_CNB` | Personal Access Token for CNB |
| `SSH_KEY_GITCODE` | SSH private key for GitCode (or `TOKEN_GITCODE`) |
| `SYNC_DISPATCH_TOKEN` | PAT to authorize `repository_dispatch` triggers |

### Config Schema

See `config/sync.yaml` for a working example.
