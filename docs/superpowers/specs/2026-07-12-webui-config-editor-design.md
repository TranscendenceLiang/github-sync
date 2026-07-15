# WebUI 配置编辑器设计

日期: 2026-07-12 (修订: 2026-07-14)

## 1. 背景

当前 Git Multi-Sync Center 的配置通过手动编辑 `config/sync.yaml` 完成。用户需要一种更直观的方式管理同步条目，包括查看、新增、编辑、删除 topology 条目及其端点参数，以及修改全局设置。

本设计的目标是提供一个 **本地运行的 WebUI**，在不改变现有 Python 同步引擎的前提下，让配置管理更友好。

## 2. 架构设计

### 2.1 整体架构

```
┌──────────────────────────────────────┐
│       终端: python webui.py           │
│           │ uvicorn                   │
│           ▼                           │
│    ┌──────────────┐                  │
│    │  FastAPI App  │                  │
│    │  / → index    │──────────▶ config│
│    │  /api/config  │◀────────── sync. │
│    │  /api/save    │          yaml    │
│    └──────┬───────┘                  │
│           │ Jinja2                   │
│           ▼                          │
│    ┌──────────────┐                  │
│    │ 模板+静态文件  │                  │
│    └──────────────┘                  │
└──────────────────────────────────────┘
```

### 2.2 组件说明

| 组件 | 职责 | 文件 |
|------|------|------|
| **入口** | CLI 启动 uvicorn，加载配置路径 | `webui.py` |
| **路由层** | 页面渲染（GET /）、配置 API（GET/POST /api/config）、校验 API（POST /api/validate） | `src/webui/main.py` |
| **配置服务** | 加载/保存 YAML 配置，复用 `src/config.py` 的 dataclass 定义和校验逻辑 | `src/webui/main.py`（同文件） |
| **模板层** | Jinja2 单页模板，渲染整个编辑器界面 | `src/webui/templates/index.html` |
| **静态资源** | 手写 CSS + 原生 JS | `src/webui/static/style.css`、`src/webui/static/app.js` |

### 2.3 项目文件结构

```
webui.py                        # 入口: python webui.py [--port PORT] [--config PATH]
src/
  webui/
    __init__.py                 # 空
    main.py                     # FastAPI app 工厂 + API 路由
    templates/
      index.html                # 主页面
    static/
      style.css                 # 全部样式
      app.js                    # 前端交互逻辑
```

### 2.4 零额外依赖

- Python 端：仅 `fastapi`（将加入 `requirements.txt` 可选组）
- 前端：纯 HTML + CSS + 原生 JS，无框架、无 npm、无图标库

## 3. API 设计

| 方法 | 路径 | 请求体 | 响应 | 说明 |
|------|------|--------|------|------|
| `GET` | `/` | — | HTML | 渲染主页面 |
| `GET` | `/api/config` | — | `SyncConfig` JSON | 返回当前完整配置 |
| `POST` | `/api/config` | `SyncConfig` JSON | `{"ok": true}` 或 `{"ok": false, "error": "..."}` | 校验并保存到 YAML 文件 |
| `POST` | `/api/validate` | `SyncConfig` JSON | `{"ok": true}` 或 `{"ok": false, "error": "..."}` | 校验但不保存 |

**关键约定：**
- API 返回/接受的 JSON 是 `SyncConfig` 内部结构（`settings` + `topology`），不包含 `sync:` 外层包装
- 后端在保存时自动添加 `sync:` 顶层 key 写入 YAML
- 加载时自动剥离 `sync:` 层，返回内部结构

### 3.1 配置 JSON 结构

API 返回/接受的 JSON 结构与 `src/config.py` 的 dataclass 一致：

```json
{
  "settings": {
    "auto_create": false,
    "force_push": false,
    "delete_remote": false,
    "mode": "mirror",
    "preserve_files": [".cnb.yml"],
    "sync_releases": false,
    "release_asset_max_size_mb": 50,
    "release_filter": {
      "mode": "all",
      "latest_count": 1,
      "pattern": null,
      "tags": null,
      "include_drafts": false
    }
  },
  "topology": [
    {
      "name": "github-to-cnb",
      "mode": "rebase",
      "preserve_files": [".cnb.yml", "Dockerfile"],
      "sync_releases": true,
      "release_filter": {
        "mode": "latest",
        "latest_count": 3,
        "pattern": "v*",
        "tags": ["v1.0", "v2.0"],
        "include_drafts": false
      },
      "source": {
        "platform": "github",
        "owner": "myorg",
        "repo": "myproject",
        "branch": "main",
        "branches": null,
        "auth": "ssh",
        "auto_create": false,
        "visibility": "private"
      },
      "targets": [
        {
          "platform": "cnb",
          "owner": "myorg",
          "repo": "myproject",
          "branch": "main",
          "branches": null,
          "auth": "pat",
          "auto_create": true,
          "visibility": "private"
        }
      ]
    }
  ]
}
```

### 3.2 ReleaseFilter 结构

`ReleaseFilter` 是 `src/release_sync.py` 中定义的数据类，嵌入到 `SyncSettings` 和 `TopologyEntry` 中：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mode` | string | `"all"` | 过滤模式: all / latest / pattern / tags |
| `latest_count` | int | 1 | mode=latest 时取最新 N 个 release |
| `pattern` | string | null | mode=pattern 时的正则表达式 |
| `tags` | list[string] | null | mode=tags 时的标签列表 |
| `include_drafts` | bool | false | 是否包含草稿 release |

## 4. UI 设计

### 4.1 页面布局

```
┌──────────────────────────────────────────────────┐
│  Git Multi-Sync Center  ·  配置管理              │
│  ⚙ 全局设置  │  + 新增同步条目                   │
├──────────────┬───────────────────────────────────┤
│              │  ┌─────────────────────────────┐  │
│  同步条目列表  │  │ [条目名称输入框]            │  │
│              │  │ 模式: ○ mirror  ○ rebase    │  │
│  ┌──────────┐│  │                             │  │
│  │▶ github..││  │  源端点                    │  │
│  │  cipher.. ││  │  平台 ▼  所有者 _______   │  │
│  │  (空占位) ││  │  仓库 ___  分支 _______   │  │
│  │          ││  │  分支模式: ○单分支 ●多分支  │  │
│  └──────────┘│  │  分支: [main] [feat] [+添加]│  │
│              │  │  认证: ○ SSH  ○ PAT        │  │
│              │  ├─────────────────────────────┤  │
│              │  │  目标端点                   │  │
│              │  │  ┌─ 1 ────────────────────┐ │  │
│              │  │  │ 平台 ▼ 所有者 _______  │ │  │
│              │  │  │ 仓库 ___ 分支 _______  │ │  │
│              │  │  │ 分支模式: ○单分支 ●多分│ │  │
│              │  │  │ 分支: [main] [feat] [+添│ │  │
│              │  │  │ 认证: ○SSH ○PAT        │ │  │
│              │  │  │ ☐auto_create 可见性:[▼]│ │  │
│              │  │  └── [删除] ─────────────┘ │  │
│              │  │  [+ 添加目标]              │  │
│              │  │                             │  │
│              │  │  ┌─ Release 同步设置 (折叠)┐│  │
│              │  │  │ ☐ 启用 Release 同步    ││  │
│              │  │  │ ┌─ Release 过滤 ──────┐││  │
│              │  │  │ │ 模式: [latest ▼]    │││  │
│              │  │  │ │ 最新N个: [3]        │││  │
│              │  │  │ │ 正则: [v*]          │││  │
│              │  │  │ │ 标签: [v1] [v2] [+添]│││  │
│              │  │  │ │ ☐ 包含草稿          │││  │
│              │  │  │ └────────────────────┘││  │
│              │  │  └───────────────────────┘│  │
│              │  │                             │  │
│              │  │  [删除此条目]               │  │
│              │  └─────────────────────────────┘  │
├──────────────┴───────────────────────────────────┤
│  [✓ 校验配置]  [💾 保存]  [↻ 刷新]              │
└──────────────────────────────────────────────────┘
```

### 4.2 交互细节

- **左侧条目列表**：当前选中条目高亮显示，点击切换编辑。每条目显示名称和简要摘要（平台简写）
- **全局设置**：点击 ⚙ 按钮展开/收起面板，包含 `auto_create`、`force_push`、`delete_remote`、`mode`、`preserve_files`、`sync_releases`、`release_asset_max_size_mb`、`release_filter`
- **新增条目**：顶部「+ 新增同步条目」按钮，左侧列表新增空白条目卡片，右侧进入编辑
- **删除条目**：条目编辑区底部「删除此条目」按钮，点击弹出确认对话框
- **目标端点**：每个目标卡片底部有「删除」按钮；全局「+ 添加目标」在目标列表底部
- **分支模式切换**：Endpoint 编辑区提供「单分支」/「多分支」单选切换。单分支模式显示文本输入框；多分支模式显示标签式列表（可添加/删除）。切换时自动清空另一模式的值，保证 `branch` 与 `branches` 互斥约束
- **Release 设置**：条目编辑区底部可折叠的「Release 同步设置」面板。条目级 `sync_releases` 为 `null` 时继承全局设置；条目级 `release_filter` 为 `null` 时继承全局设置。前端在保存时，如果值与全局一致，发送 `null` 以保持 YAML 简洁
- **保存流程**：前端收集表单数据为 JSON → `POST /api/config` → 后端复用 `config.py` 校验 → 写 YAML → 返回 `{"ok": true}` 或错误信息
- **YAML 预览**：保存前弹窗展示将要生成的 YAML 内容，用户确认后写入
- **未保存修改**：前端通过变量追踪修改状态，离开页面前弹窗提醒

### 4.3 响应式

- 窗口宽度 ≥ 750px：左右两栏布局
- 窗口宽度 < 750px：上下布局，条目列表变为顶部横向滚动或下拉选择

## 5. 错误处理

| 场景 | 处理方式 |
|------|---------|
| `config/sync.yaml` 不存在 | 首次启动时自动创建默认配置（全局设置=默认值，topology 为空列表） |
| YAML 格式错误 | API 返回具体错误信息，前端在页面顶部显示红色错误条 |
| 校验失败（缺少必填字段） | 复用 `src/config.py.ConfigError`，前端在页面顶部显示错误信息 |
| 重复条目名称 | 保存时检测，返回明确错误提示 |
| `branch` 和 `branches` 同时提供 | 前端在切换模式时自动清空另一值；后端再次校验，返回明确错误 |
| `branches` 为空列表 | 前端禁用「多分支」模式下的保存按钮；后端返回 `branches must not be empty` |
| `release_filter.mode` 无效 | 前端下拉框限制可选值；后端返回校验错误 |
| `release_filter.latest_count` 非整数 | 前端使用数字输入框限制；后端返回类型错误 |
| `release_filter.tags` 为空列表 | 前端在 tags 模式下至少要求一个标签 |
| `release_asset_max_size_mb` 非整数 | 前端使用数字输入框；后端返回类型错误 |
| 未保存修改 | 前端通过变量追踪修改状态，离开页面前弹窗提醒 |
| 端口被占用 | `webui.py` 入口检测失败，提示用户通过 `--port` 指定其他端口 |

## 6. 测试方案

| 类型 | 覆盖范围 |
|------|---------|
| 单元测试 | `GET /api/config` 返回正确 JSON；`POST /api/config` 保存并写文件；`POST /api/validate` 校验逻辑；包含 `branches` 字段的条目保存和重新加载；包含 `release_filter` 的条目保存和重新加载；`branch`/`branches` 互斥校验；`release_filter` 各 mode 的校验；边界：配置文件不存在、YAML 格式错误、重复名称 |
| 集成测试 | 使用 FastAPI `TestClient`，完整流程：加载空配置 → 添加条目（含 branches） → 保存 → 重新加载验证一致性；创建含 `release_filter` 的条目 → 保存 → 重新加载 |
| 边界测试 | `release_filter` 各 mode 组合（all/latest/pattern/tags）；`branches` 含多个分支名；`sync_releases` 全局 vs 条目级覆盖 |
| 手动测试 | 浏览器打开 `http://localhost:8765`，实际操作增删改查 |

测试文件：`tests/test_webui.py`，使用 `pytest` + `httpx`（FastAPI TestClient 依赖）。

## 7. 入口设计

`webui.py`:

```python
"""WebUI entry point for Git Multi-Sync Center configuration editor.

Usage:
    python webui.py                  # default port 8765
    python webui.py --port 8080      # custom port
    python webui.py --config /path/to/sync.yaml
"""
```

默认绑定 `127.0.0.1:8765`，仅本地访问（安全考虑，因为配置包含令牌/密钥路径等敏感信息）。

## 8. 未包含的功能（明确不实现）

- **用户认证/登录**：本地工具，不做
- **密钥管理**：不管理 GitHub Secrets，只编辑本地 YAML 配置
- **远程部署**：不涉及 Actions workflow 的修改
- **同步执行**：不触发同步，只编辑配置
- **配置历史/回滚**：不实现，依赖 git 版本管理
