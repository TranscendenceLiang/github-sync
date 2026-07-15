# WebUI（Svelte 5 SPA）

基于 FastAPI 纯 API + Svelte 5 单页应用（SPA）的 Web 控制台，用于可视化配置与校验同步规则。

## 架构

WebUI 已从「FastAPI + Jinja2 + 原生 JS」迁移为「FastAPI 纯 API + Svelte 5 SPA」。后端仅暴露 API（`/api/config`、`/api/validate`、`/api/health`），不再渲染模板，也不再内置 StaticFiles；生产模式下由 uvicorn 直接托管构建产物 `frontend/dist/` 作为 SPA 根。

开发模式:
```
┌─────────────┐   /api/*    ┌──────────────┐
│ Vite Dev    │ ──proxy──►  │ FastAPI       │
│ Server      │             │ (port 8765)   │
│ (port 5173) │             └──────────────┘
└─────────────┘
```

生产模式:
```
┌──────────────────────────────────────────┐
│  uvicorn (port 8765)                      │
│  ┌──────────────┐  ┌──────────────────┐  │
│  │ FastAPI API   │  │ StaticFiles      │  │
│  │ /api/config   │  │ / → frontend/dist │  │
│  │ /api/validate │  └──────────────────┘  │
│  │ /api/health  │                           │
│  └──────────────┘                           │
└──────────────────────────────────────────┘
```

## 本地开发

```bash
# 1) 后端 API (终端 A)
uv run --with fastapi --with uvicorn --with PyYAML --with GitPython python webui.py --mode dev --port 8765
# 2) 前端 dev server (终端 B)
cd frontend && pnpm install && pnpm dev
# 打开 http://localhost:5173   ← 注意：Windows 上 vite 绑定 localhost(IPv6)，用 localhost 而非 127.0.0.1
```

说明：Vite 开发服务器通过 `vite.config` 中的 proxy 配置，将 `/api/*` 请求转发到后端的 8765 端口，因此开发环境下不会出现跨域（CORS）问题。

## 生产构建/启动

```bash
cd frontend && pnpm build     # 生成 frontend/dist
uv run --with fastapi --with uvicorn --with PyYAML --with GitPython python webui.py   # 默认 prod：单端口 8765 同时托管 API 与前端
# 打开 http://localhost:8765
```

`webui.py` 默认以 `prod` 模式启动；prod 模式会在 8765 端口同时托管 FastAPI API 与 `frontend/dist/` 静态资源。若需显式指定，可加 `--mode prod`。

## 测试

```bash
# 前端单测 (Vitest)
cd frontend && pnpm rebuild esbuild && pnpm test
# 后端单测 (pytest, 经 uv)
uv run --with pytest --with pytest-asyncio --with PyYAML --with GitPython --with fastapi --with httpx python -m pytest tests/ -q
```

注意：`pnpm rebuild esbuild` 需要执行一次，因为 pnpm v10 默认禁止 esbuild 的 postinstall 构建脚本，会导致 esbuild 二进制缺失而测试失败。

## 依赖管理

- 前端依赖使用 **pnpm** 管理：清单为 `frontend/package.json`，锁定文件为 `frontend/pnpm-lock.yaml`。
- 后端依赖见仓库根目录 `requirements.txt`（包含 `fastapi`、`uvicorn`、`pyyaml`、`gitpython`、`httpx`、`pytest` 等）。
- 前端所有命令统一使用 `pnpm`，**禁止**使用 `npm`。

## 端口说明

- API 端口：**8765**（FastAPI / uvicorn）。
- Vite 开发服务器端口：**5173**。
