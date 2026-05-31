# 前端与后端职责边界

> 文档状态：技术参考 / 工程理解参考
>
> 当前用途：用最直白的方式说明 Serenita 前端和后端各自负责什么，帮助第一次读代码的人建立全局地图。

## 一句话版本

前端负责“用户看到什么、点什么、输入什么、页面怎么变化”。后端负责“这件事能不能做、真正怎么做、数据怎么保存、账号之间怎么隔离”。

前端不直接读数据库，不直接调用大模型。后端不负责像素级界面，也不负责浏览器里的弹窗、按钮和布局。

## 前端负责什么

前端代码主要在 `frontend/`。

前端负责：

- 登录、注册、主工作台、收藏页和账号设置页的界面。
- 浏览器路由，例如 `/sign_in`、`/sign_up`、`/`、`/chat/{session_id}`、`/favorites`、`/setting`。
- 左侧栏、首页/报告/生活场景、原始文件占位视图、输入框、模型选择、推理强度选择。
- 用户消息、思考过程、助手回答、流式增量和错误提示的展示。
- 上传文件入口、待发送附件提示、历史消息选中文本引用；可根据所选模型的 `file_mime_types` 做前端入口启停和待发送附件过滤。
- 复制、收藏、取消收藏、重新生成、停止生成、删除会话、分支切换等按钮行为。
- 把用户操作转换成后端 API 请求。
- 管理前端 API 调用方式：常规请求使用 `fetch`，上传使用 `XMLHttpRequest` 以便展示进度，流式响应使用 `fetch` 读取 `ReadableStream` 并解析 SSE 事件块。
- 在浏览器 localStorage 中保存当前浏览器会话 token，并把旧 key 迁移到新 key；当前不在 localStorage/sessionStorage 持久化对话草稿、API key 或数据库可信元数据。

前端当前主要文件：

| 文件 | 作用 |
| --- | --- |
| `frontend/src/App.tsx` | 顶层 session 恢复、路由保护和页面拼装 |
| `frontend/src/app/` | 患者工作台外壳、侧栏、浏览器路由 helper 和响应式侧栏状态 |
| `frontend/src/features/auth/` | 登录、注册、会话恢复和退出 |
| `frontend/src/features/conversations/` | 首页对话、侧栏场景入口、消息、输入区、流式生成、附件、引用和分支 |
| `frontend/src/features/favorites/` | 收藏列表、详情、标签编辑和批量操作 |
| `frontend/src/features/settings/` | 账号资料、密码安全、模型提供方、默认模型和模型管理 |
| `frontend/src/api/*.ts` | 后端接口客户端，按认证、模型、对话、收藏等领域拆分 |
| `frontend/src/api/sessionToken.ts` | 浏览器 localStorage session token 读写与旧 key 迁移 |
| `frontend/src/styles/` | 样式 token、基础样式、外壳、各 feature 样式和响应式规则 |
| `frontend/src/styles.css` | 兼容入口，只引入 `styles/index.css` |
| `frontend/src/components/SecretInput.tsx` | 密码/API key 显示隐藏输入组件 |
| `frontend/src/components/MarkdownContent.tsx` | 助手回答和收藏快照的 Markdown 展示 |
| `frontend/src/components/icons.tsx` | 工作台、设置、收藏等通用图标 |

## 后端负责什么

后端代码主要在 `backend/`。

后端负责：

- 注册、登录、退出登录和 session 校验。
- 判断当前请求属于哪个账号，并保护账号之间的数据隔离。
- 保存账号资料、模型服务配置和默认模型用途、API key、已添加模型。
- 测试模型服务连接，获取远端模型列表，归一化模型能力，并保存前端选择后提交的模型能力字段。
- 校验发送消息时的模型、推理强度、文件资源和历史消息引用。
- 在流式接口中调用已配置模型服务生成回答。
- 保存会话索引、JSONL 时间线、上传附件、轮次状态和活动分支路径。
- 保存收藏快照、标签和收藏来源。
- 提供无账号数据读取的报告占位接口；当前不做正式报告解析、OCR 或入库。
- 处理本地数据根目录、旧存储结构迁移、SQLite schema 初始化和模型能力迁移。

后端当前主要文件：

| 文件 | 作用 |
| --- | --- |
| `backend/app/main.py` | 创建 FastAPI 应用，注册路由，启动时执行模型能力迁移 |
| `backend/app/api/auth.py` | 注册、登录、退出、session、改用户名、改密码 |
| `backend/app/api/model_providers.py` | 模型服务配置、连接测试、远端模型列表、模型增删和默认模型用途 |
| `backend/app/api/conversations.py` | 对话相关 HTTP 路由 |
| `backend/app/application/conversation_service.py` | 对话核心业务：校验、创建轮次、流式生成、取消、标题生成 |
| `backend/app/application/model_provider_service.py` | 对话生成时读取账号模型配置并调用 provider |
| `backend/app/repositories/conversation_repository.py` | 会话 SQLite 和 JSONL 时间线读写 |
| `backend/app/model_capabilities.py` | 模型能力字段、默认模型用途表和旧 schema 迁移 |
| `backend/app/providers/*.py` | OpenRouter、DeepSeek、阿里云百炼等模型服务适配 |
| `backend/app/api/favorites.py` | 收藏列表、详情、创建、编辑和删除 |
| `backend/app/api/reports.py` | 报告占位接口，当前只返回空列表 |
| `backend/app/storage/*.py` | 数据目录、SQLite 连接、JSONL 写入等底层工具 |

## 一次对话怎么流动

1. 用户在前端输入问题并点击发送。
2. 前端调用 `POST /api/conversations/messages`。
3. 后端校验登录态、会话、模型、推理强度、文件和引用；当前首页对话只能使用账号的 `chat` 默认模型，前端提交其它 `model_id` 会被后端拒绝。
4. 后端写入用户消息，创建一个 `streaming` 轮次，并返回 `stream_id`。
5. 前端用 `GET /api/conversations/streams/{stream_id}` 订阅 SSE 流，当前实现通过 `fetch` 携带 `Authorization` 并读取 `ReadableStream`。
6. 后端在这个流式接口里调用模型服务的 `/chat/completions`。
7. 后端把模型返回的思考增量和正文增量通过 SSE 发给前端。
8. 前端实时把增量显示在消息气泡里。
9. 模型结束后，后端把可选 `thinking_process` 和最终 `assistant_message` 写入时间线。
10. 后端更新会话标题、最近消息摘要和活动路径。
11. 前端刷新会话列表和当前会话详情。

## 模型配置怎么流动

1. 前端设置页读取 `GET /api/model-providers`、`GET /api/models` 和 `GET /api/model-defaults`。
2. 前端保存模型服务的官网地址、API 地址和 API key；后端写入当前账号私有 `config.db`，API key 不进入 localStorage。
3. 连接测试使用表单中的临时 `base_url` 和 `api_key`，测试动作本身不额外持久化配置。
4. 获取远端模型列表时，后端使用当前账号已保存的模型服务配置请求厂商 `GET {base_url}/models`，并通过 provider adapter 归一化能力字段。
5. 添加模型时，前端提交被选中远端模型的归一化能力字段；后端校验 provider 已配置，把模型和能力字段写入 `models` 表。
6. 默认模型按用途写入 `model_default_settings`；首页对话只接受 `chat` 默认模型，会话标题生成优先用 `title` 默认模型，没有时回退到 `chat` 默认模型。

## 文件上传怎么流动

1. 用户在前端选择文件。
2. 前端调用 `POST /api/conversations/context-resources` 上传文件，当前实现使用 `XMLHttpRequest` 携带 `Authorization` 并回传上传进度。
3. 后端先执行基础 MIME allowlist 和 20MB 单文件上限校验。
4. 前端随上传提交当前选择的 `model_id`；后端保存前校验该模型必须是账号 `chat` 默认模型，并确认附件 MIME 可由 `chat` 模型原生处理，或可由账号 `vision_parse` 默认模型原生解析。
5. 后端保存原始文件、记录 MIME、大小、哈希、资源状态和约 24 小时过期时间。
6. 仅上传文件时，后端只创建草稿会话、磁盘文件和 `conversation_resources` 记录，不立即追加 `file_upload` 到会话 JSONL。
7. 用户发送消息时，前端只提交 `resource_id`。
8. 后端根据 `resource_id` 找到可信文件元数据，并校验文件属于当前账号和当前会话。
9. 后端再次校验附件 MIME 可由 `chat` 模型原生处理，或可由账号 `vision_parse` 默认模型原生解析；发送成功时才追加 `file_upload` 和 `user_message` 时间线记录。
10. 流式生成时，若 `chat` 模型支持附件 MIME，后端读取附件正文并编码成 provider 原生 content part 发给 `chat`；若 `chat` 模型不支持但 `vision_parse` 模型支持，后端把附件原文发给 `vision_parse`，由视觉解析模型生成本轮回答。
11. 如果用户只上传文件但还没有发送消息，前端可保留返回的草稿 `session_id` 和待发送资源；后端会让草稿详情可读，但不会把它放进最近会话列表。

当前版本不做报告入库或结构化字段抽取；多模态附件只作为本轮对话上下文发给 `chat` 或 `vision_parse`，不写入报告列表。

## 收藏怎么流动

1. 用户点击助手回答上的收藏按钮。
2. 前端调用 `POST /api/favorites`，提交来源会话 ID 和来源消息 ID。
3. 后端校验来源消息属于当前账号，且是可收藏的助手回答。
4. 后端保存收藏快照、摘要、标题和标签。
5. 即使原会话后来被删除，收藏详情仍能展示快照。

## 账号和安全边界

- 前端可以显示当前账号，但不能作为权限判断来源。
- 后端必须从 session token 定位当前账号。
- 后端所有需登录接口都只能访问当前账号的数据。
- 前端 API 基址来自 `VITE_API_BASE_URL`，未配置时默认为 `/api`；本地开发由 Vite 把 `/api` 代理到 `http://127.0.0.1:8000`。
- 前端当前使用 localStorage key `serenita_auth_session_token` 保存登录返回的明文 token，并在读取旧 key `serenita_session_token` 时自动迁移；请求主链路通过 `Authorization: Bearer ...` 发送。后端同时设置和接受同名 HttpOnly cookie，并兼容旧 cookie 名；cookie 是同源/兼容辅助通道。
- API key 存在账号私有 `config.db`，用于回填设置表单；前端不得把 API key 写入 localStorage。
- 文件路径、MIME、大小和哈希以后端登记记录为准，前端提交的文件元数据不可信。

## 当前容易误解的点

- `frontend/src/App.tsx` 是薄入口，不代表前端负责业务可信判断；可信权限、数据隔离和模型调用仍全部以后端为准。
- 一些 `application/` 和 `repositories/` 文件仍是空壳或半迁移状态，不能只看文件名判断职责是否已经完全落地；例如账号设置资料/密码的有效接口在 `backend/app/api/auth.py`，`backend/app/api/account_settings.py` 当前只是空路由占位。
- `backend/app/api/auth.py`、`backend/app/api/model_providers.py` 和 `backend/app/api/favorites.py` 当前仍包含一部分业务和存储初始化逻辑，尚未完全下沉到 service/repository。
- 发送消息接口不直接等模型返回；真正的模型调用发生在流式接口被订阅时。
- 报告、生活和原始文件入口在 `v0.1.0` 仍是占位，不是正式业务能力。
