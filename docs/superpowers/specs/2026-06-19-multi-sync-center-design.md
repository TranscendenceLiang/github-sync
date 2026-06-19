# Git 仓库中心化同步系统设计

## 1. 项目概述

**项目名称**: Git Multi-Sync Center

**项目类型**: 中心化 Git 仓库同步工具

**核心功能**: 通过 GitHub Actions 实现多个 Git 平台（GitHub、Gitee、CNB、GitCode）之间的仓库分支自由同步，支持手动、自动、定时三种触发方式。

**目标用户**: 需要在多个 Git 平台上同步代码的开发者或团队。

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│              中心化同步仓库 (Multi-Sync Center)              │
│  ┌─────────────────────────────────────────────────┐   │
│  │         GitHub Actions Workflow                  │   │
│  │  - repository_dispatch 事件接收     │   │
│  │  - workflow_dispatch 手动触发     │   │
│  │  - schedule 定时触发                  │   │
│  └─────────────────────────────────────────────────┘   │
│                         │                             │
│                         ▼                             │
│  ┌─────────────────────────────────────────────────┐   │
│  │          Sync Engine (Python)                    │   │
│  │  - 解析 YAML 配置                           │   │
│  │  - 管理认证（SSH Key / PAT）              │   │
│  │  - 执行 git 操作                      │   │
│  └─────────────────────────────────────────────────┘   │
│                         │                             │
│         ┌──────────────┼──────────────┐             │
│         ▼              ▼              ▼              │
│    ┌─────────┐   ┌─────────┐   ┌─────────┐         │
│    │ GitHub │   │ Gitee  │   │  CNB   │  ...    │
│    │SSH/PAT │   │SSH/PAT │   │ HTTPS+  │         │
│    │        │   │        │   │  PAT   │         │
│    └─────────┘   └─────────┘   └─────────┘         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 组件说明

| 组件 | 说明 |
|------|------|
| **Sync Repository** | 中心化同步仓库，存储配置和 workflow |
| **Config File** | YAML 配置文件，定义同步规则 |
| **Credential Manager** | 管理各平台的认证（SSH Key / PAT） |
| **Sync Engine** | 核心同步执行引擎 |
| **GitHub Actions** | CI/CD 触发和执行层 |

---

## 3. 功能设计

### 3.1 支持的平台

| 平台 | 认证方式 | URL 格式 | Secrets 名称 |
|------|---------|----------|------------|
| GitHub | SSH Key 或 PAT | `git@github.com:owner/repo.git` 或 `https://x-access-token:TOKEN@github.com/owner/repo.git` | `SSH_KEY_GITHUB` 或 `TOKEN_GITHUB` |
| Gitee | SSH Key 或 PAT | `git@gitee.com:owner/repo.git` 或 `https://TOKEN@gitee.com/owner/repo.git` | `SSH_KEY_GITEE` 或 `TOKEN_GITEE` |
| CNB | HTTPS + PAT | `https://cnb.cool/owner/repo.git` | `TOKEN_CNB` |
| GitCode | SSH Key 或 PAT | `git@gitcode.com:owner/repo.git` 或 `https://TOKEN@gitcode.com/owner/repo.git` | `SSH_KEY_GITCODE` 或 `TOKEN_GITCODE` |

**说明**:
- CNB 仅支持 HTTPS + Personal Access Token 认证
- 其他平台（GitHub、Gitee、GitCode）支持 **SSH Key** 或 **PAT** 两种方式
- 用户可在 YAML 中为每个端点指定使用哪种认证
- **同一平台的所有仓库共用一个密钥/令牌**（不是每个仓库单独配置）
- 私有/公开仓库均支持（SSH/PAT 均可访问私有仓库）

### 3.2 触发方式

| 触发方式 | 实现方式 | 说明 |
|---------|---------|------|
| **手动触发** | `workflow_dispatch` | 用户在 GitHub 页面手动点击运行 |
| **自动触发** | `repository_dispatch` | 其他仓库推送时通过 API 触发 |
| **定时触发** | `schedule` (cron) | 定期自动执行 |

**自动触发方式说明**:
- 用户在源仓库添加 workflow，通过 `curl` 调用 GitHub API 触发中心仓库
- 需要在中心仓库创建 `SYNC_DISPATCH_TOKEN`（PAT）作为 API 认证
- 中心仓库需要配置 `repository_dispatch` 事件接收

### 3.3 同步配置 (YAML)

```yaml
# 同步配置示例
sync:
  # 全局设置
  settings:
    auto_create: false       # 自动创建目标仓库（暂未实现，配置入口预留）
    force_push: false        # 是否强制推送
    delete_remote: false     # 是否删除远程不存在的分支

  # 同步拓扑定义
  topology:
    # 1. 从 GitHub 同步到 Gitee（一对一，SSH 认证）
    - name: "github-to-gitee"
      source:
        platform: github
        owner: myorg
        repo: myproject
        branch: main
        auth: ssh  # 可选: ssh (默认) | pat
      targets:
        - platform: gitee
          owner: myorg
          repo: myproject
          branch: main
          auth: ssh
    
    # 2. 从 GitHub 同步到 CNB（一对一，PAT 认证）
    - name: "github-to-cnb"
      source:
        platform: github
        owner: myorg
        repo: myproject
        branch: main
        auth: pat
      targets:
        - platform: cnb
          owner: myteam
          repo: myproject
          branch: main
          auth: pat  # CNB 仅支持 PAT
    
    # 3. 一对多分发（混合认证）
    - name: "github-broadcast"
      source:
        platform: github
        owner: myorg
        repo: myproject
        branch: main
        auth: ssh
      targets:
        - platform: gitee
          owner: myorg
          repo: myproject
          branch: main
          auth: ssh
        - platform: gitcode
          owner: myorg
          repo: myproject
          branch: main
          auth: pat
```

### 3.4 同步内容

- **分支 (Branches)**: 同步指定分支
- **Tags**: 同步 tags

**说明**: 不同步 Releases，因为各平台的 Releases API 不互通，仅 tags 是通用 Git 概念。

### 3.5 认证管理

通过 GitHub Secrets 存储认证信息：

| Secret 名称 | 类型 | 说明 |
|-----------|------|------|
| `SSH_KEY_GITHUB` | SSH Private Key | GitHub 平台密钥（所有 GitHub 仓库共用） |
| `TOKEN_GITHUB` | Personal Access Token | GitHub 平台令牌（所有 GitHub 仓库共用） |
| `SSH_KEY_GITEE` | SSH Private Key | Gitee 平台密钥（所有 Gitee 仓库共用） |
| `TOKEN_GITEE` | Personal Access Token | Gitee 平台令牌（所有 Gitee 仓库共用） |
| `TOKEN_CNB` | Personal Access Token | CNB 平台令牌（所有 CNB 仓库共用，仅支持 PAT） |
| `SSH_KEY_GITCODE` | SSH Private Key | GitCode 平台密钥（所有 GitCode 仓库共用） |
| `TOKEN_GITCODE` | Personal Access Token | GitCode 平台令牌（所有 GitCode 仓库共用） |
| `SYNC_DISPATCH_TOKEN` | PAT | 用于接收 repository_dispatch 触发 |

**YAML 配置认证方式**:

```yaml
sync:
  topology:
    - name: "example"
      source:
        platform: github
        owner: myorg
        repo: myproject
        branch: main
        auth: ssh       # 可选: ssh (默认) | pat
      targets:
        - platform: gitee
          owner: myorg
          repo: myproject
          branch: main
          auth: pat     # 使用 PAT 认证
```

---

## 4. 工作流程

### 4.1 触发流程

```
用户仓库 Push
    │
    ▼
源仓库 Workflow (用户自定义)
    │
    ▼
调用 GitHub API
repository_dispatch
    │
    ▼
中心仓库接收事件
    │
    ▼
GitHub Actions 启动
    │
    ▼
执行 Sync Engine
```

### 4.2 同步执行流程

```
1. 加载 YAML 配置
    │
2. 加载各平台认证信息
    │
3. 遍历拓扑定义
    │
4. 对每个同步任务:
    │ 4.1 检测源分支最新提交
    │ 4.2 检测目标分支最新提交
    │ 4.3 如果两端都有新提交 → 报错退出
    │ 4.4 拉取源分支
    │ 4.5 推送至目标分支
    │
5. 生成同步报告
```

---

## 5. 文件结构

```
.
├── .github/
│   └── workflows/
│       └── sync.yml          # 主 workflow 文件
├── src/
│   ├── sync.py               # 同步核心逻辑
│   ├── config.py             # 配置解析
│   ├── git_helper.py         # Git 操作辅助
│   └── credential.py         # 认证管理
├── config/
│   └── sync.yaml             # 同步配置文件
├── docs/
│   └── README.md             # 使用文档
├── requirements.txt          # Python 依赖
└── .gitignore
```

---

## 6. 使用方式

### 6.1 配置同步仓库

1. 创建中心同步仓库（私有或公开）
2. 在 Settings → Secrets 中配置各平台认证（按需配置，SSH/PAT 二选一或多选）：
   - `SSH_KEY_GITHUB` 或 `TOKEN_GITHUB`: GitHub 认证
   - `SSH_KEY_GITEE` 或 `TOKEN_GITEE`: Gitee 认证
   - `TOKEN_CNB`: CNB Personal Access Token（仅支持 PAT）
   - `SSH_KEY_GITCODE` 或 `TOKEN_GITCODE`: GitCode 认证
   - `SYNC_DISPATCH_TOKEN`: 触发专用 PAT
3. 编辑 `config/sync.yaml` 配置同步规则，可在每个端点指定 `auth` 方式
4. 提交更改

### 6.2 手动触发

在中心仓库的 Actions 页面，点击 "Run workflow"

### 6.3 从其他仓库自动触发

在源仓库添加 `.github/workflows/trigger-sync.yml`：

```yaml
name: Trigger Sync
on:
  push:
    branches: [main]

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger center sync
        run: |
          curl -X POST \
            -H "Authorization: token ${{ secrets.SYNC_DISPATCH_TOKEN }}" \
            https://api.github.com/repos/your-org/multi-sync-center/dispatches \
            -d '{"event_type": "sync-triggered"}'
```

需要在源仓库配置 `SYNC_DISPATCH_TOKEN` Secret（与中心仓库同一个 PAT）。

---

## 7. 错误处理

| 错误类型 | 处理方式 |
|---------|--------|
| 认证信息缺失（SSH Key 和 PAT 都未配置） | 报错退出，提示配置对应 Secret |
| 源仓库不存在 | 报错退出 |
| 源分支不存在 | 报错退出 |
| 目标仓库不存在 | 报错退出（auto_create 暂未实现） |
| 双向都有新提交 | 报错退出，需用户手动解决冲突 |
| 网络错误 | 重试 3 次后退出 |
| 推送失败 | 报错退出并保留错误日志 |

---

## 8. 安全性

- 认证信息仅存储在 GitHub Secrets，不提交到代码
- SSH 私钥使用 `add-to-known-host` 跳过主机验证
- 使用 `fetch-depth: 0` 完整克隆（保留所有历史）
- 支持 force push 但默认关闭
- 日志中不打印认证信息

---

## 9. 后续开发（暂不实现）

- 自动创建目标仓库（需要各平台 API Token）
- Web UI 配置界面
- 同步状态通知（飞书/钉钉/邮件）
- Pull Request 同步