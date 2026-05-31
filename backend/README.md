# Serenita 后端

> 文档状态：当前代码说明 / 后端模块参考
>
> 当前用途：说明当前 FastAPI 后端的代码结构、API 范围、存储边界和运行方式。产品范围仍以 `docs/releases/v0.1.0/` 的当前执行文档为准。

Serenita 后端是一个 FastAPI 分层单体应用。当前实现覆盖 `v0.1.0` 的账号认证、账号设置、模型服务、首页对话、收藏，以及报告占位接口。

## 代码结构

```text
backend/app/
  api/              HTTP 路由、请求解析、响应组装
  application/      产品用例和业务流程
  agent_runtime/    未来 Agent 编排、工具、记忆、技能和事件
  providers/        大模型服务适配器
  repositories/     SQLite 和 JSONL 持久化适配
  storage/          路径、SQLite、JSONL、密钥辅助能力
  schemas/          共享请求/响应结构预留；当前多数请求/响应模型仍在 api/*.py 内
  core/             配置、错误、安全、时间工具
```

当前实现仍保持一个可部署的 FastAPI 应用。未来报告分析、综合分析和生活建议 Agent 应放在 `agent_runtime/agents/` 下，前端只调用业务接口，不直接感知 Agent 内部。

部分 `application/` 和 `repositories/` 模块仍在迁移过程中；`backend/app/api/auth.py`、`backend/app/api/model_providers.py` 和 `backend/app/api/favorites.py` 目前仍包含一部分有效业务逻辑。阅读代码时不要只看空壳 service/repository。

## 后端负责什么

- 校验登录态和当前账号。
- 保证账号之间的数据隔离。
- 保存账号、会话、模型配置、上传资源和收藏数据。
- 管理模型服务配置、API key、连接测试和远端模型列表。
- 校验对话请求中的模型、推理强度、文件资源和历史引用。
- 在流式接口中调用已配置模型服务生成回答。
- 记录会话时间线、思考过程、助手回答、取消和失败状态。
- 提供报告占位接口，但当前不做报告解析或入库。

## 当前 API 范围

- `POST /api/auth/sign_up`、`POST /api/auth/sign_in`、`GET /api/auth/session`、`POST /api/auth/sign_out`
- `PATCH /api/auth/account`、`PATCH /api/auth/password`
- `GET /api/model-providers`、`POST /api/model-providers`、`PATCH /api/model-providers/{provider_id}`
- `POST /api/model-providers/{provider_id}/test`
- `GET /api/model-providers/{provider_id}/models`
- `POST /api/models`、`GET /api/models`、`DELETE /api/models/{model_id:path}`；`GET /api/model-defaults`、`PATCH /api/model-defaults`
- `/api/conversations` 下的上下文资源上传、发送、重新生成、流式生成/回放、`GET /api/conversations/{session_id}/turns/{turn_id}` 轮次查询、取消、列表、详情、删除和活动路径切换
- `/api/favorites` 下的收藏列表、详情、创建、编辑、删除和批量删除
- `GET /api/reports`，当前只返回空列表

## 开发

后端运行要求 Python 3.13+；仓库根目录的 `.python-version` 当前为 `3.13`。

在仓库根目录安装依赖：

```bash
uv sync
```

运行后端测试：

```bash
uv run python -m unittest discover -s tests -v
```

启动 API：

```bash
uv run uvicorn backend.app.main:create_app --factory --reload
```

API 标题是 `Serenita API`，版本是 `0.1.0`。CORS 允许本地 Vite 地址 `http://127.0.0.1:5170-5179` 和 `http://localhost:5170-5179`。

## 存储

可以通过 `SERENITA_DATA_ROOT` 指定数据目录。未配置时，运行时文件写入仓库根目录下的 `serenita_files/`。

主要存储结构：

```text
serenita_files/
  all_users/auth/auth_info.db
  all_users/auth/{account}/session.json
  {account}/config/config.db
  {account}/conversations/db_storage/sessions.db
  {account}/conversations/sessions/{session_id}.jsonl
  {account}/conversations/attachments/{session_id}/{resource_id}.{ext}
  {account}/favorites/db_storage/favorites.db
```

认证存储支持从旧目录 `all_users/login/key_info.db` 迁移到 `all_users/auth/auth_info.db`。会话时间线支持从旧日期分层路径迁移为 `conversations/sessions/{session_id}.jsonl`。模型存储包含旧版 `capabilities_json`、旧默认模型表和旧 API key 字段的迁移逻辑。

账号私有 `config.db` 中的模型能力使用拆分列保存：`supports_text`、`file_mime_types`、`thinking_modes`、`supports_tool_calling`、`supports_json_output`、`context_window_tokens` 和 `max_output_tokens`。`model_default_settings` 只允许 `chat`、`title`、`vision_parse`、`compact` 四类用途。

## 运行边界

- `api/` 负责 HTTP 协议层：参数解析、依赖注入、响应返回。
- `application/` 应承载业务流程；部分模块还在从 `api/` 迁移过来。
- `repositories/` 和 `storage/` 负责文件与数据库细节。
- `providers/` 负责模型服务连接、模型列表、非流式和流式对话调用。
- `agent_runtime/` 是未来 AI 工作流边界，当前不直接暴露给前端。

## 当前对话能力边界

发送消息时，后端会校验账号归属、模型可用性、推理强度、文件资源和历史引用，然后创建 `streaming` 轮次。当前真实首页对话只接受账号的 `chat` 默认模型：请求可以不传 `model_id`，由后端回退到 `chat` 默认模型；如果传入 `model_id`，必须与当前 `chat` 默认模型一致。前端订阅 `GET /api/conversations/streams/{stream_id}` 后，后端才调用已配置 provider 的 `/chat/completions`，并使用 `stream=true` 返回 SSE 事件。

完成后，后端会持久化可选的 `thinking_process`、最终 `assistant_message`，并根据完整问答更新会话标题。标题优先使用 `title` 默认模型生成；未配置时回退 `chat` 默认模型；模型调用失败或未配置标题模型时使用本地标题清洗规则兜底。

文件上传会保存到账号自己的会话目录，并按 `chat` 默认模型和 `vision_parse` 默认模型能力校验。单文件上限为 20MB；当前允许登记图片、PDF、音频、视频以及旧版文档/表格 MIME，但发送给模型前还会同时校验模型 `file_mime_types` 和 provider adapter 原生附件能力。仅上传文件但尚未发送消息时，上传接口会创建草稿会话和资源记录；草稿会话可读取详情但不会进入会话列表。发送时，若 `chat` 模型原生支持附件 MIME，后端直接转发给 `chat` 模型；若 `chat` 模型不支持但 `vision_parse` 模型支持，后端直接调用视觉解析模型并把附件作为原生输入发送，由 `vision_parse` 生成本轮回答；两者都不支持时拒绝上传或发送。

上传资源默认 24 小时过期。资源发送前保持 `pending`，发送成功写入时间线后标记为 `attached`；已过期或已删除资源不能继续作为上下文发送。
