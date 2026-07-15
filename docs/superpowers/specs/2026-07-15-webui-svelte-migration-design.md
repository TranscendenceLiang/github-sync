# WebUI Svelte SPA 迁移设计

日期: 2026-07-15

## 1. 背景

当前 WebUI 使用 FastAPI + Jinja2 模板 + 手写原生 JS 实现。实践中暴露出以下问题：

- **Jinja2 模板形同虚设**：模板中几乎没有服务端渲染变量，纯属多一层抽象
- **手写原生 JS 易出 bug**：事件绑定、状态管理、表单收集全在一个文件，排查困难
- **无热更新**：改前端代码需要手动重启 Python 服务，反馈慢
- **前后端耦合**：前端 bug 和后端 bug 的排查路径不同，增加认知负担

目标是将 WebUI 改造为 **FastAPI 纯 API 后端 + Svelte SPA 前端** 的架构。

## 2. 架构设计

### 2.1 整体架构

```
开发模式:
┌─────────────┐   /api/*    ┌──────────────┐
│ Vite Dev    │ ──proxy──►  │ FastAPI       │
│ Server      │             │ (port 8765)   │
│ (port 5173) │             │               │
└─────────────┘             └──────────────┘

生产模式:
┌──────────────────────────────────────────┐
│  uvicorn (port 8765)                      │
│  ┌──────────────┐  ┌──────────────────┐  │
│  │ FastAPI API   │  │ StaticFiles      │  │
│  │ /api/config   │  │ / → frontend/dist │  │
│  │ /api/validate │  └──────────────────┘  │
│  └──────────────┘                         │
└──────────────────────────────────────────┘
```

## 3. 组件设计

### 3.1 后端改造

`src/webui/main.py` 精简为纯 API：

- 去掉 `Jinja2Templates`、`StaticFiles` 导入
- 去掉 `GET /` 路由（不再渲染模板）
- 保留 `GET /api/config`、`POST /api/config`、`POST /api/validate`
- 新增 `GET /api/health` 健康检查端点

`webui.py` 入口改造：
- 开发模式：只启动 API（端口 8765）
- 生产模式：挂载 `frontend/dist/` 为静态文件，SPA 路由 fallback

### 3. 前端组件设计

```
frontend/src/
├── main.js                 # Svelte 入口
├── App.svelte              # 根组件，布局框架
├── api/
│   └── config.js           # fetch 封装：getConfig, saveConfig, validateConfig
├── components/
│   ├── EntryList.svelte    # 左侧同步条目列表
│   ├── EntryEditor.svelte  # 右侧条目编辑表单
│   ├── EndpointForm.svelte # 端点表单（源/目标复用）
│   ├── SettingsPanel.svelte # 全局设置面板
│   ├── ReleaseFilter.svelte # Release 过滤子表单
│   ├── YamlPreview.svelte   # YAML 预览对话框
│   └── ConfirmDialog.svelte # 确认对话框
└── stores/
    └── config.js            # Svelte store 管理配置状态
```

### 3.1 组件树

```
App.svelte
├── SettingsPanel.svelte
│   └── ReleaseFilter.svelte
├── EntryList.svelte
├── EntryEditor.svelte
│   ├── EndpointForm.svelte (source)
│   ├── EndpointForm.svelte (targets, 可多个)
│   └── ReleaseFilter.svelte
├── YamlPreview.svelte
├── ConfirmDialog.svelte
└── StatusBar.svelte
```

### 3.2 状态管理

使用 Svelte writable store 管理配置状态：

```js
// stores/config.js
export const config = writable(null);       // 完整配置对象
export const selectedIndex = writable(-1);  // 当前选中的条目索引
export const dirty = writable(false);       // 未保存修改标记
```

### 3.3 API 调用封装

`frontend/src/api/config.js` 封装所有后端 API 调用，和当前 `app.js` 中的 `apiGet`/`apiPost` 对应。

## 4. 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 前端框架 | Svelte | 轻量、编译后无 runtime、适合小项目 |
| 构建工具 | Vite | Svelte 官方推荐，HMR 开箱即用 |
| 生产托管 | FastAPI 挂载静态文件 | 单端口部署，保持现有启动方式不变 |
| API 代理 | Vite proxy 配置 | 开发时前后端端口分离，避免 CORS 问题 |
| 状态管理 | Svelte writable store | 无需引入 Pinia/Redux，项目规模足够小 |
| HTTP 请求 | 原生 fetch | 无需引入 axios，API 调用简单 |

## 5. 迁移步骤

- [ ] 删除 `src/webui/templates/`
- [ ] 删除 `src/webui/static/`
- [ ] `src/webui/main.py` 去掉 Jinja2Templates、StaticFiles 导入
- [ ] `webui.py` 生产模式挂载 SPA 静态文件
- [ ] 更新 `.gitignore` 添加 `frontend/dist/`、`frontend/node_modules/`
