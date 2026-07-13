# 同步 Release 功能设计

日期: 2026-07-13

## 1. 背景

Git Multi-Sync Center 当前只同步 git 分支（以及随 `git push --mirror` 一起推送的 tag 引用）。但平台上的 **Release 对象**（关联的 tag 名、标题、描述、草稿/预发布状态）和 **附件资产**（二进制文件）是存于平台数据库、走 REST API 的数据，git 同步不会触及。

需求：在分支同步完成后，额外把源平台的 release（元数据 + 附件资产）同步到各目标平台，做到「多平台发布信息一致」。

已确认的关键决策：
1. **范围**：全量同步 = 发布元数据 + 附件资产（二进制文件）。
2. **触发**：配置项开关 `settings.sync_releases`（默认关），单条 entry 可覆盖。
3. **平台**：四平台全覆盖（github / gitee / cnb / gitcode），无 release API 的平台优雅降级（跳过 + 告警）。
4. **资产策略**：可配置单文件大小上限（默认 50MB），超限跳过 + 告警；单个资产失败不阻断其他资产与其他目标。
5. **子集筛选**：通过 `release_filter` 支持 `all` / `latest[:N]` / `pattern`(glob) / `tags`(白名单) + `include_drafts`，在写入前过滤，顺带省去被过滤 release 的资产下载带宽。

## 2. 配置变更

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

### 字段说明

| 字段 | 层级 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `sync_releases` | settings | bool | `false` | 全局总开关 |
| `sync_releases` | entry | bool | 继承 settings | 条目级覆盖 |
| `release_asset_max_size_mb` | settings | int | `50` | 单附件大小上限（MB） |
| `release_filter` | settings | mapping | `all` | 全局默认筛选 |
| `release_filter` | entry | mapping | 继承 settings | 条目级覆盖 |
| `release_filter.mode` | — | str | `all` | `all` \| `latest` \| `pattern` \| `tags` |
| `release_filter.latest_count` | — | int | `1` | `latest` 模式取最近 N 个（按发布时间） |
| `release_filter.pattern` | — | str | 无 | `pattern` 模式 fnmatch glob，匹配 `tag_name` |
| `release_filter.tags` | — | list[str] | 无 | `tags` 模式显式白名单 |
| `release_filter.include_drafts` | — | bool | `false` | 是否包含草稿 release |

生效解析（沿用 `mode` 的覆盖模式）：`entry.sync_releases if entry.sync_releases is not None else settings.sync_releases`；`release_filter` 同理，entry 级有则覆盖、无则继承。

## 3. 架构设计

### 3.1 新增模块 `src/release_sync.py`

抽象 `ReleaseClient` 统一各平台差异；数据用 `ReleaseInfo` / `AssetInfo` 承载；`sync_releases()` 负责源→目标的编排。

```python
@dataclass
class AssetInfo:
    name: str
    size: int
    download_url: str
    asset_id: str | None = None

@dataclass
class ReleaseInfo:
    tag_name: str
    name: str | None
    body: str | None
    draft: bool
    prerelease: bool
    release_id: str | None = None
    assets: list[AssetInfo] = field(default_factory=list)

@dataclass
class ReleaseFilter:
    mode: str = "all"            # all | latest | pattern | tags
    latest_count: int = 1
    pattern: str | None = None
    tags: list[str] | None = None
    include_drafts: bool = False

class ReleaseSyncError(Exception):
    """Raised when a release sync task fails (carries platform/repo context)."""

class ReleaseClient(ABC):
    @abstractmethod
    def list_releases(self, owner, repo, token) -> list[ReleaseInfo]: ...
    @abstractmethod
    def get_release_by_tag(self, owner, repo, tag, token) -> ReleaseInfo | None: ...
    @abstractmethod
    def create_release(self, owner, repo, token, info: ReleaseInfo) -> ReleaseInfo: ...
    @abstractmethod
    def update_release(self, owner, repo, token, info: ReleaseInfo) -> ReleaseInfo: ...
    @abstractmethod
    def download_asset(self, asset: AssetInfo, token, dest: Path) -> Path: ...
    @abstractmethod
    def upload_asset(self, owner, repo, token, release_id, path: Path, name: str) -> AssetInfo: ...

# 平台注册表
RELEASE_CLIENTS: dict[str, type[ReleaseClient]] = {
    "github": GitHubReleaseClient,
    "gitee": GiteeReleaseClient,
    "cnb": CNBReleaseClient,
    "gitcode": GitCodeReleaseClient,
}

def supports_releases(platform: str) -> bool:
    """True 表示该平台已实现可用的 release API；否则优雅跳过。"""
    return platform in RELEASE_CLIENTS

def filter_releases(releases: list[ReleaseInfo], rf: ReleaseFilter) -> list[ReleaseInfo]:
    """在写入前过滤：先剔除草稿（除非 include_drafts），再按 mode 筛选。"""

def sync_releases(entry, creds, settings) -> ReleaseSyncResult:
    """编排：拉源 release → 按 filter 过滤 → 逐 target 创建/更新 + 同步资产。"""
```

所有客户端用 `subprocess.run(["curl", ...])` 调平台 REST API，沿用 `auto_create.py` 风格（无第三方库，PAT 认证）。

### 3.2 各平台 API 调用

| 平台 | list | create | update | 资产上传 |
|------|------|--------|--------|----------|
| github | `GET /repos/{o}/{r}/releases` (Bearer) | `POST .../releases` body `{tag_name,name,body,draft,prerelease}` | `PATCH .../releases/{id}` | 下载 `browser_download_url`(带 token)；上传 `POST .../releases/{id}/assets?name=`(octet-stream) |
| gitee | `GET /api/v5/repos/{o}/{r}/releases?access_token=` | `POST .../releases` (access_token + body) | `PATCH .../releases/{id}` | 上传 `POST .../releases/{id}/attach_files`(multipart) |
| cnb | 实现期验证端点；若不支持则 `supports_releases` 返回 False | 同上尽力而为 | 同上 | 同上 |
| gitcode | 实现期验证（API v5 类 Gitee）；若不支持则跳过 | 同上 | 同上 | 同上 |

GitHub / Gitee 完整实现；CNB / GitCode 实现期验证端点，确认无 API 时 `supports_releases()` 对该平台返回 False → 跳过 + 告警。

### 3.3 挂载点：集成到 sync 流程

在 `sync_topology_entry()` 的「target 分支同步循环」**之后**，若 `sync_releases` 生效则调用 `sync_releases()`：

```
for target in entry.targets:
    strategy.sync(...)          # 现有分支同步
...
# 分支同步完成后：
if effective_sync_releases:
    rel_result = sync_releases(entry, creds, cfg.settings)
    # 汇入 SyncResult（releases_created / updated / skipped, assets_uploaded / skipped）
```

release 同步只走 API，不依赖已 clone 的工作目录；结果汇入 `SyncResult`，由 `main.py` 打印摘要并计入 `failed`。

### 3.4 `release_filter` 过滤逻辑

`filter_releases()` 在拉取源 release 之后、任何写入之前执行：
1. 若 `not include_drafts`：剔除 `draft == True` 的 release。
2. 按 `mode`：
   - `all` → 全量返回；
   - `latest` → 按发布时间倒序取前 `latest_count` 个；
   - `pattern` → 用 `fnmatch.fnmatch(r.tag_name, rf.pattern)` 匹配；
   - `tags` → 仅保留 `tag_name` 在 `rf.tags` 白名单内的。

被过滤掉的 release 不会触发任何资产下载，节省带宽。

### 3.5 同步流程与幂等

- **范围**：源上所有已发布 release + prerelease；草稿默认跳过（`include_drafts` 可开启）。
- **幂等**：对每个源 release（按 `tag_name` 唯一），用 `get_release_by_tag` 查目标：
  - 无 → `create_release`；
  - 有 → `update_release` 刷新 `name` / `body` / `draft` / `prerelease`。
- **附件**：对 release 下每个 asset，若 `size > release_asset_max_size_mb * 1MB` → 跳过 + 告警；否则下载到临时目录再上传目标。目标已有同名 asset 则跳过（免重复上传）。
- **失败隔离**：单个 asset 下载 / 上传失败 → 记 skipped + 告警，继续其他 asset 与其他 target；仅当整条 target 的 release API 不可用才跳过该 target。

## 4. 错误处理

| 场景 | 行为 |
|------|------|
| 源平台不支持 release API | warn + 跳过整个 entry 的 release 同步，不计入 failed |
| 目标平台不支持 release API | warn + 跳过该 target，继续其他 target |
| `release_filter` 排除的 release | 不下载其资产、不写入 |
| 资产 `size > cap` | skip + warn，继续 |
| 资产下载 / 上传失败 | skip + warn（失败隔离），继续其他资产 / target |
| create / update API 失败 | `ReleaseSyncError` → 计入 failed（target 级致命） |
| 目标已存在同 tag release | `update_release`（幂等） |
| draft 且 `include_drafts=false` | 过滤掉 |

## 5. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/release_sync.py` | 新增 | `ReleaseClient` 及四平台实现、`ReleaseInfo` / `AssetInfo` / `ReleaseFilter`、`ReleaseSyncError`、`sync_releases`、`filter_releases`、`supports_releases` |
| `src/config.py` | 修改 | `SyncSettings` 新增 `sync_releases` / `release_asset_max_size_mb` / `release_filter`；`TopologyEntry` 新增 `sync_releases` / `release_filter`；解析逻辑 |
| `src/sync.py` | 修改 | 分支同步后调用 `sync_releases`；`SyncResult` 增加 release 相关字段 |
| `src/main.py` | 修改 | 打印 release 同步摘要，致命失败计入 `failed` |
| `tests/test_release_sync.py` | 新增 | 各 client 单测（mock `subprocess.run` 验证 curl）、`filter_releases`、`supports_releases` 降级、资产大小上限、失败隔离 |
| `docs/README.md` | 修改 | 配置 schema 与 Behavior 章节补充（实现阶段） |

## 6. 测试计划

- **单测**（仿 `test_auto_create.py`）：mock `subprocess.run`，验证 GitHub / Gitee client 的 curl 命令、URL、header、body；资产超限跳过；`supports_releases` 降级逻辑；`filter_releases` 四种 mode + `include_drafts`。
- **集成测**：用 mock HTTP server 或 mock client，验证「源 2 release（含 1 草稿）→ 经 filter 后目标新建 + 更新 + 资产隔离」整链；验证 target 级 API 不可用时的跳过与告警。
