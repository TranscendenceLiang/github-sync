# 自动创建目标仓库功能设计

日期: 2026-07-10

## 1. 背景

当前 Git Multi-Sync Center 要求目标仓库必须已存在。`sync.settings.auto_create` 字段已预留但未实现。需要在 push 到目标仓库失败（仓库不存在）时，自动调用平台 API 创建仓库后重试。

## 2. 配置变更

```yaml
sync:
  settings:
    auto_create: false           # 全局总开关

  topology:
    - name: "github-to-cnb"
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
          auto_create: true      # 条目级覆盖全局
          visibility: private    # 仓库可见性: private (默认) | public
```

### 字段说明

| 字段 | 层级 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `auto_create` | settings | bool | `false` | 全局开关 |
| `auto_create` | target | bool | 继承 settings | 条目级覆盖 |
| `visibility` | target | str | `"private"` | "private" \| "public" |

## 3. 架构设计

### 3.1 新增模块 `src/auto_create.py`

```python
@dataclass
class CreateRepoRequest:
    platform: str      # github | gitee | cnb | gitcode
    owner: str         # 组织路径/用户名
    repo: str          # 仓库名
    visibility: str    # "public" | "private"
    token: str         # API token

class CreateRepoError(Exception):
    """Raised when repo creation fails."""

def create_repo(request: CreateRepoRequest) -> None:
    """调用 curl 创建仓库，失败时抛出 CreateRepoError."""
```

抽象 `CreateRepoRequest` 统一各平台参数差异。`create_repo()` 用 `subprocess.run(["curl", ...])` 调用各平台 API。

### 3.2 各平台 API 调用

| 平台 | HTTP | URL | Auth | Body |
|------|------|-----|------|------|
| github | POST | `https://api.github.com/user/repos` | `Authorization: Bearer {token}` | `{"name": repo, "private": bool}` |
| gitee | POST | `https://gitee.com/api/v5/user/repos` | Body `access_token` | `{"access_token": "...", "name": repo, "private": bool}` |
| cnb | POST | `https://api.cnb.cool/repos` | `Authorization: Bearer {token}` | `{"slug": owner, "name": repo, "visibility": str}` |
| gitcode | POST | `https://api.gitcode.com/api/v5/user/repos` | Query `access_token` | `{"name": repo, "path": repo}` |

### 3.3 集成到 sync 流程

在 `sync_topology_entry()` 中，当前 push 失败的处理：

```
push_branch(...) → GitError
  └─ 如果 auto_create 且 "not found" → 调用 create_repo()
       ├─ 成功 → 重试 push_branch()
       └─ 失败 → 抛出 SyncError
```

在 `MirrorStrategy` 中，当前的 `clone_or_fetch` 已经处理了 "not found" 作为空仓库处理。但首次 push 到不存在的仓库时，需要在 `push_branch` 失败时触发创建。

具体流程：
1. `push_branch(source_clone_dir, "target", branch)` 失败 → GitError
2. 检查错误消息是否包含 "not found" / "repository not found"
3. 如果 auto_create && 错误匹配 → 调用 `create_repo()`
4. 创建成功后重试 push

## 4. 错误处理

| 场景 | 行为 |
|------|------|
| 仓库不存在 + auto_create=false | 抛出 SyncError（当前行为） |
| 仓库不存在 + auto_create=true + 创建成功 | 重试 push |
| 仓库不存在 + auto_create=true + 创建失败 | 抛出 SyncError（含 API 错误信息） |
| 仓库已存在 | 正常同步（当前行为） |
| 不支持的平台 | `CreateRepoError` 转 `SyncError` |

## 5. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/auto_create.py` | 新增 | CreateRepoRequest, create_repo(), CreateRepoError |
| `src/config.py` | 修改 | Endpoint 新增 auto_create / visibility 字段 + 解析 |
| `src/strategies/mirror.py` | 修改 | push 失败时触发 auto_create |
| `src/sync.py` | 修改 | 传递 auto_create / visibility 参数 |
| `tests/test_auto_create.py` | 新增 | auto_create 单元测试 |
