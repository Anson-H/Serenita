# Serenita v0.1.0 技术设计索引

> 文档状态：当前执行 / 当前执行版本
>
> 关联产品需求文档：[账号注册与登录](../prd/auth.md)、[账号设置](../prd/account-settings.md)、[首页对话](../prd/home-conversation.md)、[收藏](../prd/favorites.md)
>
> 适用对象：前端、后端、测试
>
> 文档目标：说明 v0.1.0 技术设计拆分方式、全局接口约定、模块边界和跨模块存储关系

## 1. 技术设计拆分

v0.1.0 的技术设计拆为四个模块文件：

| 模块 | 技术设计 | 主要范围 |
| --- | --- | --- |
| 账号注册与登录 | [auth.md](./auth.md) | 注册、登录、会话恢复、退出登录、登录凭证库、会话 token |
| 账号设置 | [account-settings.md](./account-settings.md) | 账号设置页、修改用户名称、修改密码、模型提供方、API key、模型列表、默认模型用途设置 |
| 首页对话 | [home-conversation.md](./home-conversation.md) | 对话接口、上下文资源、流式输出、取消生成、会话历史、分支、删除会话、报告占位接口 |
| 收藏 | [favorites.md](./favorites.md) | 我的收藏页 `/favorites`、收藏列表、收藏详情、创建收藏、编辑标签、取消收藏、批量取消收藏 |

验收标准见 [acceptance.md](../acceptance.md)，需求入口见 [prd/README.md](../prd/README.md)。

## 2. 模块化架构

| 需求模块 | 前端主要承载 | 后端主要承载 | 存储 |
| --- | --- | --- | --- |
| 账号注册与登录 | `frontend/src/App.tsx`、`frontend/src/features/auth/AuthPage.tsx`、`frontend/src/features/auth/useAuthSession.ts`、`frontend/src/api/authApi.ts`、`frontend/src/api/sessionToken.ts`、`frontend/src/components/SecretInput.tsx` | `backend/app/api/auth.py` | `all_users/auth/auth_info.db`、`all_users/auth/{account}/session.json` |
| 共享应用壳 | `frontend/src/app/WorkspaceRouteShell.tsx`、`frontend/src/app/PatientShell.tsx`、`frontend/src/app/Sidebar.tsx`、`frontend/src/app/useResponsiveSidebar.ts`、`frontend/src/app/routes.ts`、`frontend/src/app/useBrowserRoute.ts` | 无 | 无 |
| 账号设置 | `frontend/src/features/settings/SettingsWorkspacePanel.tsx`、`frontend/src/features/settings/SettingsShell.tsx`、`frontend/src/features/settings/SettingsView.tsx`、`frontend/src/api/accountSettingsApi.ts`、`frontend/src/api/modelProviderApi.ts`、`SecretInput.tsx` | `backend/app/api/auth.py`、`backend/app/api/model_providers.py`、`backend/app/application/model_provider_service.py` | `{account}/config/config.db` |
| 首页对话 | `frontend/src/features/conversations/WorkspacePage.tsx`、`frontend/src/features/conversations/ConversationWorkspaceSurface.tsx`、`frontend/src/features/conversations/HomeWorkspace.tsx`、`frontend/src/features/conversations/ConversationComposer.tsx`、`frontend/src/features/conversations/ConversationMessageBubble.tsx`、`frontend/src/features/conversations/conversationDraft.ts`、`frontend/src/features/conversations/streamingMessages.ts`、`frontend/src/features/conversations/useConversationLifecycle.ts`、`frontend/src/features/conversations/useConversationWorkspace.ts`、`frontend/src/features/conversations/useConversationMessageActions.ts`、`frontend/src/features/conversations/useConversationBranching.ts`、`frontend/src/features/conversations/useConversationAttachments.ts`、`frontend/src/features/conversations/useConversationModelControl.ts`、`frontend/src/features/conversations/useConversationLayout.ts`、`frontend/src/api/conversationApi.ts` | `backend/app/api/conversations.py`、`backend/app/application/conversation_service.py`、`backend/app/repositories/conversation_repository.py`、`backend/app/api/reports.py` | `{account}/conversations/db_storage/sessions.db`、会话 JSONL、附件目录 |
| 收藏 | `frontend/src/features/favorites/FavoritesWorkspacePanel.tsx`、`frontend/src/features/favorites/FavoritesWorkspace.tsx`、`frontend/src/features/favorites/useFavoriteWorkspace.ts`、`frontend/src/features/favorites/useFavoriteMessageActions.ts`、`frontend/src/features/favorites/useFavoriteListAlignment.ts`、`frontend/src/features/favorites/favoriteState.ts`、`frontend/src/features/favorites/favoriteTags.ts`、`frontend/src/api/favoriteApi.ts` | `backend/app/api/favorites.py` | `{account}/favorites/db_storage/favorites.db` |

## 3. 全局接口约定

- 所有需登录接口必须校验当前会话是否有效。
- 所有需登录接口只能访问当前登录 `account` 名下的数据。
- 请求中的 `account` 不得作为权限判断依据；后端以登录态定位当前账号。
- 时间字段统一使用 ISO 8601 字符串。
- 当前由业务代码主动抛出的错误通过 JSON 返回，`detail` 至少包含 `code` 和 `message`，必要时包含 `details`；FastAPI / Pydantic 的框架级参数校验错误当前仍可能返回默认 422 结构。
- 前端不得依赖供应商原始错误文本判断业务状态。
- 当前实现按账号私有库查询资源，跨账号资源通常表现为当前账号下 `NOT_FOUND`；`FORBIDDEN` 作为后续显式鉴权失败场景的预留稳定码。

## 4. 稳定错误码

下表包含当前代码已使用的稳定业务错误码和少量预留目标码；未接入限流或全局异常包装的场景不得被验收为已经实现。

| code | HTTP 状态码 | 含义 | 适用场景 |
| --- | --- | --- | --- |
| `UNAUTHORIZED` | 401 | 未登录或登录态已失效 | 所有需登录接口 |
| `FORBIDDEN` | 403 | 无权访问该资源 | 预留：显式鉴权失败 |
| `INVALID_REQUEST` | 400 | 请求参数不合法 | 缺少必填字段、格式错误 |
| `NOT_FOUND` | 404 | 资源不存在 | 会话、收藏记录、模型等不存在 |
| `CONFLICT` | 409 | 资源冲突 | 重复收藏 |
| `ACCOUNT_EXISTS` | 409 | 账号已存在 | 注册接口 |
| `SIGN_IN_FAILED` | 401 | 账号或密码错误 | 登录、修改密码 |
| `SESSION_EXPIRED` | 401 | 会话已过期 | 登录态校验 |
| `UPLOAD_FAILED` | 500 | 文件落盘或保存失败的目标稳定错误码；当前代码尚未统一包装所有文件保存异常 | 上下文资源上传 |
| `FILE_TOO_LARGE` | 413 | 文件大小超限 | 上下文资源上传 |
| `UNSUPPORTED_FILE_TYPE` | 415 | 文件类型不支持 | 上下文资源上传 |
| `MODEL_ERROR` | 502 | AI 模型或模型服务调用失败 | 对话流式事件、连接测试、添加模型弹窗 |
| `MODEL_TIMEOUT` | 504 | AI 模型或模型服务响应超时 | 连接测试、添加模型弹窗；对话流式当前归入 `MODEL_ERROR` 事件 |
| `PROVIDER_AUTH_FAILED` | 502 | 模型服务认证失败 | 连接测试、添加模型弹窗；对话流式当前归入 `MODEL_ERROR` 事件 |
| `MODEL_FILE_UNSUPPORTED` | 422 | 当前模型不支持该文件格式 | 上下文资源上传、对话请求 |
| `MODEL_ATTACHMENT_UNSUPPORTED` | 422 | 当前模型服务不能原生转发该附件类型 | 上下文资源上传、对话请求 |
| `MODEL_NOT_FOUND` | 404 | 模型不存在或未添加 | 上下文资源上传、对话请求、模型配置 |
| `MODEL_NOT_CONFIGURED` | 422 | 未配置模型服务、API key 或未添加可用模型 | 连接测试、添加模型弹窗、上下文资源上传、对话请求 |
| `RATE_LIMITED` | 429 | 请求频率超限 | 预留：限流能力 |
| `INTERNAL_ERROR` | 500 | 服务端内部错误 | 预留：全局异常包装 |

对话流式生成中的远端失败当前通过 `failed` SSE 事件返回；实现会把 provider 异常统一写为 `MODEL_ERROR`，并把认证失败或超时等供应商文本放在事件 `message` 中。连接测试和远端模型列表接口仍按上表映射为 `PROVIDER_AUTH_FAILED` 或 `MODEL_TIMEOUT`。

## 5. 代码已有能力同步

以下能力已在代码中出现，并已同步到模块 PRD、验收清单和模块技术设计：

| 能力 | 文档归属 | 技术契约 |
| --- | --- | --- |
| 密码和 API key 显示/隐藏输入 | 账号注册与登录、账号设置 | 仅影响输入框 `type`，不得改变值；API key 保存到账号私有配置库，不写入前端本地持久化存储 |
| 账号设置页 | 账号设置 | 从左下角账号按钮直接进入 `/setting`，保留左侧主工作栏、登录态和用户摘要；退出登录位于设置页一级导航 |
| 我的收藏页面 URL | 收藏 | 前端路由进入 `/favorites`，保留左侧主工作栏，返回原对话时跳转 `/chat/{source_session_id}` 并高亮来源消息 |
| 消息复制 | 首页对话 | 前端复制当前消息文本，不新增后端接口 |
| 会话删除 | 首页对话 | `DELETE /api/conversations/{session_id}` 删除索引、时间线、资源索引和附件目录 |
| 报告占位列表 | 首页对话 | `GET /api/reports` 当前不校验登录态、不读取账号数据，只返回空列表，不代表报告正式能力已开放 |
| 收藏标签编辑与批量取消收藏 | 收藏 | `PATCH /api/favorites/{favorite_id}`、`POST /api/favorites/batch-delete` |
| 流式输出与取消生成 | 首页对话 | 发送/重新生成创建流式轮次，流式接口输出 SSE 事件，取消接口清除 pending 状态 |
| 真实模型生成与标题生成 | 首页对话 | 流式接口调用 provider `/chat/completions` 生成回答，完成后优先用 `title` 默认模型生成短会话标题，未设置时回退 `chat` 默认模型，失败时回退本地标题规则 |
| 模型能力字段迁移 | 账号设置 | `create_app()` 启动时迁移已有账号 `models` 表的能力字段和列顺序 |
| 草稿上传会话不进历史列表 | 首页对话 | 上传文件可创建空活动路径的草稿会话；`GET /api/conversations` 只返回活动路径非空的会话，发送首条消息后才进入列表 |
| `/chat/{session_id}` 指定会话路由 | 首页对话 | 前端用 URL 恢复指定会话，并在快速切换时忽略过期详情响应 |
| 收藏标签胶囊和显式多选模式 | 收藏 | 前端通过标签胶囊乐观更新并调用 `PATCH /api/favorites/{favorite_id}`；批量选择模式不自动选中收藏 |
| Provider 原生附件转发 | 首页对话 | 上传时按 `model_id`、`chat` 模型、`vision_parse` 模型和 provider 原生能力校验；发送时 `chat` 模型支持的附件编码为 provider 原生 content part 发给 `chat`，不支持但可由 `vision_parse` 处理的附件直接发给 `vision_parse` 生成本轮回答 |
| 侧栏场景与原始文件占位 | 首页对话 | 报告/生活场景入口位于侧栏并停留在 `/`；非首页场景用占位标题和输入框 placeholder 表达未开放，文本输入禁用、附件入口隐藏，提交在前端阻止；原始文件为侧栏辅助占位入口，不录入正式文件 |
| 首页模型弹层当前口径 | 首页对话、账号设置 | 前端刷新全部已添加模型并将 `chat` 默认模型置顶；推理强度随当前选中模型变化，附件按钮合并当前 `chat` 模型与 `vision_parse` 模型能力；上传和真实发送由后端限制为 `chat` 默认请求模型，非默认模型提交返回 `INVALID_REQUEST` |
| 首个添加模型默认用途 | 账号设置 | 当前前端添加模型成功且 `chat` 默认模型为空时，会立即调用 `/api/model-defaults` 把该模型设为 `chat`；后端 `POST /api/models` 本身不隐式修改默认用途 |
| 长上下文与 `compact` 边界 | 首页对话、账号设置 | `context_window_tokens` 仅作为模型能力元数据保存；`compact` 只做设置和数据库预留，当前代码不触发长会话压缩，也不做 token 级历史裁剪 |

## 6. 存储总览

```text
serenita_files/
  all_users/
    auth/
      auth_info.db
      {account}/session.json
  {account}/
    config/config.db
    conversations/
      db_storage/sessions.db
      sessions/{session_id}.jsonl
      attachments/{session_id}/{resource_id}.{ext}
    favorites/db_storage/favorites.db
```

各模块只能读写自己负责的数据边界；跨模块引用通过稳定 ID 完成，例如收藏用 `source_session_id` 和 `source_id` 引用对话消息快照来源。
