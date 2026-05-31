# Serenita

> 文档状态：当前代码说明 / 项目入口
> 当前用途：概览当前 `v0.1.0` 实现、运行方式和文档入口。

Serenita 是面向患者的 AI 健康工作台。当前 `v0.1.0` 代码聚焦第一个可用闭环：注册、登录、配置模型服务、在首页对话、通过历史列表或 `/chat/{session_id}` 恢复会话，以及把有价值的 AI 回答收藏起来。

## 当前实现

- 后端：FastAPI 分层单体，代码位于 `backend/app`。
- 前端：React + Vite 单页患者工作台，代码位于 `frontend/`。
- 运行环境：Python 3.13+、Node.js/npm。
- 存储：本地文件系统 + SQLite，默认根目录为 `SERENITA_DATA_ROOT`，未配置时使用仓库根目录下的 `serenita_files/`。
- 当前执行范围：`docs/releases/v0.1.0/`。
- 下一规划范围：`docs/releases/v0.2.0/`。
- 长期草案范围：`docs/releases/v1.0.0-draft/`。

## 前后端职责

前端负责用户看见和操作的部分：页面路由、工作台布局、账号设置页、输入框、消息展示、流式显示、收藏和分支操作。前端通过 `frontend/src/api/` 调用后端接口，不直接读写数据库，也不直接调用模型服务。

后端负责业务判断和数据：账号登录态、权限隔离、模型服务配置、对话校验、流式调用模型、会话时间线、上传文件、收藏快照和本地数据库。后端是数据可信源。

更详细的边界说明见 [前端与后端职责边界](docs/shared/frontend-backend-responsibilities.md)。

## 本地运行

在仓库根目录安装后端依赖：

```bash
uv sync
```

启动后端 API：

```bash
uv run uvicorn backend.app.main:create_app --factory --reload
```

安装并启动前端：

```bash
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。Vite 开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 测试

在仓库根目录运行 Python 测试：

```bash
uv run python -m unittest discover -s tests -v
```

构建前端：

```bash
cd frontend
npm run build
```

运行前端静态契约测试：

```bash
cd frontend
npm test
```

## 重要运行说明

- 登录态 token 可通过 `Authorization: Bearer ...` 或 `serenita_auth_session_token` Cookie 传给后端。
- 前端在本地开发时也会把 token 存在 localStorage 的 `serenita_auth_session_token` 中。
- 模型服务 API key 存在每个账号自己的 `config.db` 中，不写入前端 localStorage。
- 当前对话服务会校验模型和文件能力，持久化消息，并在流式接口被消费时调用已配置模型服务的 OpenAI-compatible chat completion 接口。上传和真实发送均以账号的 `chat` 默认模型为后端最终校验；请求中带 `model_id` 时必须等于当前 `chat` 默认模型。
- 登录后进入工作台会同时拉取会话、收藏、已添加模型和默认模型；如果当前路径不是 `/chat/{session_id}` 且已有历史会话，前端会打开最近一条会话。点击“开启新对话”才会进入新的空白对话草稿。
- 上传文件会保存并按当前 `chat` 模型和 `vision_parse` 模型能力校验。发送时，若 `chat` 模型原生支持附件 MIME，后端直接转发给 `chat` 模型；若 `chat` 模型不支持但 `vision_parse` 模型支持，后端直接调用视觉解析模型并把附件作为原生输入发送，由 `vision_parse` 生成本轮回答；两者都不支持时拒绝上传或发送。
- 仅上传文件但尚未发送消息的草稿会话不会进入最近会话列表；发送首条消息后才显示在历史中。
- 报告和生活在 `v0.1.0` 仍是占位入口；`GET /api/reports` 返回空列表。

## 文档

先读 [docs/README.md](docs/README.md)，再读当前 `v0.1.0` 的 PRD、技术设计和验收清单：

- [v0.1.0 PRD 索引](docs/releases/v0.1.0/prd/README.md)
- [v0.1.0 技术设计索引](docs/releases/v0.1.0/technical/README.md)
- [v0.1.0 验收清单](docs/releases/v0.1.0/acceptance.md)
