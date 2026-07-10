# Rebase 同步模式设计

日期: 2026-07-10

## 1. 背景

当前 Git Multi-Sync Center 只支持 **mirror 模式**（力推送，目标与源完全一致）。当从 GitHub 同步到 CNB 时，CNB 特有的配置文件（如 `.cnb.yml`）会被源仓库的缺失覆盖。

需要新增 **rebase 模式**：将源的提交在目标当前状态之上重放（rebase），保留目标特有的文件，同时将源的变更集成进来。

## 2. 术语

| 术语 | 说明 |
|------|------|
| mirror 模式 | 现有行为：force-push 源到目标，目标完全镜像源 |
| rebase 模式 | 新增行为：将源分支 rebase 到目标分支之上，保留目标特有文件 |
| 保护文件 | 配置中声明的文件列表，rebase 前后会做备份/恢复，防止源意外删除 |

## 3. 配置变更

### 3.1 YAML Schema

```yaml
sync:
  settings:
    mode: mirror                    # 全局默认：mirror | rebase
    preserve_files:                 # 全局默认保护文件列表（rebase 模式生效）
      - .cnb.yml

  topology:
    - name: "github-ciphertalk-to-cnb"
      mode: rebase                  # 覆盖全局设置
      preserve_files:               # 覆盖式：仅保护以下文件（不合并全局列表）
        - .cnb.yml
        - Dockerfile
      source:
        platform: github
        owner: ILoveBingLu
        repo: CipherTalk
        branch: main
      targets:
        - platform: cnb
          owner: TranscendenceLiang
          repo: CipherTalk
          branch: main
```

### 3.2 Settings 合并规则

1. `entry.mode` 不为空 → 使用条目级；否则继承 `settings.mode`
2. `entry.preserve_files` 不为空 → **覆盖**全局列表；否则继承 `settings.preserve_files`
3. `mode` 仅允许两个值：`"mirror"` | `"rebase"`

### 3.3 新增/变更的 Dataclass

```python
@dataclass
class SyncSettings:
    auto_create: bool = False
    force_push: bool = False
    delete_remote: bool = False
    mode: str = "mirror"
    preserve_files: list[str] | None = None

@dataclass
class TopologyEntry:
    name: str
    source: Endpoint
    targets: list[Endpoint]
    mode: str | None = None         # None=继承全局
    preserve_files: list[str] | None = None
```

## 4. 架构设计

### 4.1 策略模式

抽取 `SyncStrategy` 接口，mirror 和 rebase 作为两种策略实现：

```
sync_topology_entry()          # 编排：校验凭证、解析 URL、clone 源
  │
  ├─ _resolve_strategy(mode)
  │   ├─ "mirror" → MirrorStrategy   (现有逻辑)
  │   └─ "rebase" → RebaseStrategy   (新增)
  │
  └─ strategy.sync()           # 每种策略自行管理目标操作
```

### 4.2 接口定义

```python
@dataclass
class StrategyResult:
    success: bool
    targets_pushed: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    skipped: bool = False            # rebase 冲突时 True
    restored: list[str] = field(default_factory=list)  # 恢复的保护文件
    message: str = ""

class SyncStrategy(ABC):
    @abstractmethod
    def sync(
        self,
        *,
        source_dir: Path,        # 已 fetch 好源分支的目录
        target_url: str,
        branch: str,
    ) -> StrategyResult:
        ...
```

### 4.3 MirrorStrategy

保持现有逻辑不变：
1. bare clone/fetch 目标
2. 冲突检测（当 `force_push=False`）
3. `push_branch` 到目标（按 `force_push` 决定是否 --force）
4. `delete_remote` 清理（按配置）

### 4.4 RebaseStrategy 流程

```
1. 完整克隆目标到独立工作目录（非 bare）
2. 添加源为 remote "source"，fetch source/<branch>
3. 备份保护文件列表到内存（路径 → bytes）
4. git checkout <branch>
5. git rebase source/<branch>
   ├─ 成功 → 继续
   └─ 失败 → git rebase --abort，返回 skipped=True
6. 恢复保护文件（字节级比对，有变化才写回）
7. 若有文件恢复 → git add + git commit "restore target-specific files: ..."
8. git push target <branch> --force
```

关键设计决策：
- **rebase 冲突时跳过**（非中止），用户可手动处理后再触发
- **push 始终 --force**，因为 rebase 改写了提交历史
- **忽略 `force_push` 和 `delete_remote` 配置**，rebase 模式下它们不适用
- 保护文件用**内容比对**，只在有实际变更时创建 restore commit
- 在**独立目录**操作，不污染源仓库的 clone

## 5. 文件保护机制

### 5.1 原理

rebase 天然会保留目标有、源没有的文件。保护列表是额外防线，防止以下情况：

1. **源删除了共有文件**：rebase 后会丢失 → 保护列表将其恢复
2. **源修改了保护文件**：rebase 后目标版本被覆盖 → 保护列表将其还原为目标版本

### 5.2 实现

```python
# 1. 备份
backups = {}
for path in self.preserve_files:
    full_path = work_dir / path
    if full_path.exists():
        backups[path] = full_path.read_bytes()

# 2. rebase ...

# 3. 恢复
restored = []
for path, content in backups.items():
    full_path = work_dir / path
    if not full_path.exists() or full_path.read_bytes() != content:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        restored.append(path)

if restored:
    git_add_commit(work_dir, restored, "restore target-specific files")
```

## 6. 错误处理

| 场景 | 行为 |
|------|------|
| rebase 冲突 | `git rebase --abort`，`skipped=True`，继续处理下一条目 |
| 克隆目标失败 | 抛出 SyncError，中断当前条目 |
| 保护文件原始不存在 | 跳过该文件（不做恢复） |
| push 失败 | 抛出 SyncError |
| 未知 mode 值 | ConfigError，启动时报错 |

## 7. 测试计划

- **单元测试**：`RebaseStrategy.sync()` 成功路径
- **单元测试**：rebase 冲突时的跳过逻辑
- **单元测试**：保护文件备份恢复（文件被删、被改、保持不变三种情况）
- **单元测试**：config 解析 mode + preserve_files
- **单元测试**：mode 校验（非法值拒绝）
- **集成测试**：完整 rebase 同步流程（使用本地 bare repo 模拟）
- **集成测试**：在 rebase 基础上源增加新提交 → 目标保留特有文件

## 8. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `config/sync.yaml` | 修改 | 示例配置添加 mode + preserve_files |
| `src/config.py` | 修改 | SyncSettings/TopologyEntry 新增字段，\_parse_settings/\_parse_entry 新增解析 |
| `src/strategies/__init__.py` | 新增 | 策略包 |
| `src/strategies/base.py` | 新增 | SyncStrategy ABC + StrategyResult |
| `src/strategies/mirror.py` | 新增 | MirrorStrategy 实现（从 sync.py 提取） |
| `src/strategies/rebase.py` | 新增 | RebaseStrategy 实现 |
| `src/sync.py` | 修改 | sync_topology_entry 按 mode 派发策略 |
| `src/main.py` | 修改 | 传递 mode + preserve_files 参数 |
| `docs/README.md` | 修改 | 文档补充 rebase 模式说明 + force_push/delete_remote 在 rebase 下被忽略 |
| `tests/` | 新增 | 对应测试文件 |
