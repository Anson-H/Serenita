# Serenita v0.1.0 首页对话技术设计

> 文档状态：当前执行 / 当前执行版本
>
> 关联产品需求文档：[首页对话 产品需求文档](../prd/home-conversation.md)
>
> 技术设计索引：[README.md](./README.md)

## 1. 接口清单

| 接口 | 说明 |
| --- | --- |
| `POST /api/conversations/context-resources` | 上下文资源上传 |
| `POST /api/conversations/messages` | 发送消息 |
| `POST /api/conversations/{session_id}/messages/{message_id}/regenerate` | 重新生成助手回答 |
| `GET /api/conversations/streams/{stream_id}` | 流式订阅 |
| `GET /api/conversations/{session_id}/turns/{turn_id}` | 查询轮次生成状态 |
| `POST /api/conversations/{session_id}/turns/{turn_id}/cancel` | 取消生成 |
| `GET /api/conversations` | 会话列表 |
| `GET /api/conversations/{session_id}` | 会话详情 |
| `DELETE /api/conversations/{session_id}` | 删除会话 |
| `PATCH /api/conversations/{session_id}/active-path` | 切换分支 |
| `GET /api/reports` | 报告占位列表 |

当前实现说明：

- `ConversationService.send_message` 写入用户消息并创建 `streaming` 轮次，助手消息在流式订阅完成、失败或取消时落盘。
- `GET /api/conversations/streams/{stream_id}` 调用已配置模型并发送 `thinking_delta`、`content_delta`、`completed`、`failed` 或 `cancelled` 事件。
- 模型调用由流式接口触发；发送接口只完成校验、时间线写入和轮次登记，不阻塞等待模型响应。
- Provider 请求使用 OpenAI-compatible `/chat/completions`，`stream=true`；非 `default` 推理强度映射到 `reasoning_effort`。
- Provider 消息包含 Serenita 健康问答 system prompt、当前父路径上的历史 user/assistant 文本、历史消息引用文本，以及可用的附件上下文；`chat` 模型原生支持的附件会直接编码成 provider content part 发给 `chat`，`chat` 模型不支持但 `vision_parse` 模型支持的附件会直接发给 `vision_parse`，由视觉解析模型生成本轮回答。
- 完成回答后会基于用户问题和助手回答生成短标题；优先调用账号设置中的 `title` 默认模型，未设置 `title` 时回退 `chat` 默认模型，模型调用失败时回退到本地标题清洗规则。
- 文件上传当前使用 `UploadFile.content_type` 与当前 `chat` 模型、`vision_parse` 模型和 provider adapter 的原生附件能力判断 MIME，保存原始文件并记录 SHA-256；若 `chat` 和 `vision_parse` 都没有任何可用附件 MIME 能力，前端不展示附件按钮；若两者都不支持该 MIME，后端拒绝上传或发送。
- 报告和生活场景入口位于左侧侧栏；原始文件是侧栏辅助占位入口，当前不录入正式文件或报告结构化数据。
- 会话、轮次、消息、资源和收藏 ID 当前由 `uuid.uuid4()` 生成。
- 报告和生活场景当前只复用工作区外壳、占位标题、输入框 placeholder 和模型选择控件；文本输入禁用、附件入口隐藏，提交动作在前端被阻止，不会调用对话接口或模型服务。
- `context_window_tokens` 当前只作为模型能力元数据保存；对话构造 provider messages 时不做 token 级历史裁剪，也不触发 `compact` 默认模型。

## 2. 上下文资源上传

```http
POST /api/conversations/context-resources
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | string | 否 | 新对话可为空 |
| `model_id` | string | 否 | 用于上传时校验当前请求模型必须为 `chat` 默认模型，并按 `chat` 模型、`vision_parse` 模型和 provider adapter 能力校验附件 MIME；为空时使用 `chat` 默认模型；非 `chat` 默认模型在 v0.1.0 返回 `INVALID_REQUEST` |
| `file` | file | 是 | 上传文件 |

资源处理要求：

- 若 `session_id` 为空，后端创建草稿会话并返回 `session_id`。
- 草稿会话用于承载待发送文件资源；其 `active_path_message_ids` 保持为空，因此可通过会话详情接口读取，但不会出现在 `GET /api/conversations` 历史列表中。
- 上传接口必须校验实际文件大小和文件类型。
- 单文件大小上限为 20MB。
- 当前代码使用上传对象的 `content_type` 判断 MIME，并记录 `size_bytes` 和 `sha256`。
- 后续若进入生产医疗场景，应补充文件头嗅探、扩展名复核和解析结果校验，避免仅信任客户端 MIME。
- 文件超过大小上限时返回 `FILE_TOO_LARGE`。
- 文件类型不在白名单中时返回 `UNSUPPORTED_FILE_TYPE`。
- 当前显式校验阶段的失败（大小、MIME、模型文件能力、provider 原生附件能力）均发生在写入资源索引和时间线之前，并返回对应稳定错误码。
- 文件落盘或数据库写入异常当前尚未做专门的 `UPLOAD_FAILED` 包装和原子性残留清理；这是后续需要补强的稳定错误映射与清理边界。
- 上传成功后，资源写入资源索引：`status` 为 `uploaded`，`usage_status` 为 `pending`。
- 只有在发送消息时被引用的资源才追加 `file_upload` 时间线记录。
- 待使用资源默认 24 小时过期。

当前原生附件能力可能支持的 MIME 类型由已添加模型的 `file_mime_types` 与 provider adapter 共同决定。当前代码白名单和 adapter 覆盖的主要类型如下：

| 类型 | MIME / 扩展名 |
| --- | --- |
| 图片 | `image/bmp`、`image/jpeg`、`image/png`、`image/tiff`、`image/heic`、`image/webp`、`image/gif` |
| PDF | `application/pdf` |
| 音频 | `audio/amr`、`audio/wav`、`audio/x-wav`、`audio/3gpp`、`audio/3gpp2`、`audio/mpeg`、`audio/mp3`、`audio/aiff`、`audio/x-aiff`、`audio/aac`、`audio/ogg`、`audio/flac`、`audio/mp4`、`audio/m4a`、`audio/x-m4a` |
| 视频 | `video/mp4`、`video/mpeg`、`video/x-msvideo`、`video/x-matroska`、`video/mov`、`video/quicktime`、`video/webm`、`video/x-flv`、`video/x-ms-wmv` |

Office 文档 MIME 保留在上传白名单迁移兼容范围内，但当前 provider adapter 不原生转发 Office 文档，因此不会通过 v0.1.0 的模型/provider 能力校验；除非后续 adapter 实现原生文件输入，否则不作为可用附件能力开放。

响应示例：

```json
{
  "session_id": "019db81e-80a0-7000-8a00-019db81e80a1",
  "resource": {
    "resource_id": "019db820-c6a8-7001-8a01-019db820c6aa",
    "name": "体检报告.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 524288,
    "relative_path": "conversations/attachments/019db81e-80a0-7000-8a00-019db81e80a1/019db820-c6a8-7001-8a01-019db820c6aa.pdf",
    "thumb_path": null,
    "sha256": "8f1c...",
    "source": "user_upload",
    "status": "uploaded",
    "usage_status": "pending",
    "expires_at": "2026-04-24T10:17:29+08:00"
  }
}
```

## 3. 发送消息

```http
POST /api/conversations/messages
Content-Type: application/json
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | string/null | 否 | 新对话可为空 |
| `parent_message_id` | string/null | 否 | 根消息为空 |
| `raw_text` | string | 是 | 用户问题；可为空字符串，但必须至少有文本或上下文资源之一 |
| `model_id` | string/null | 否 | 为空时使用 `chat` 默认模型 |
| `thinking_mode` | string | 是 | 必须包含在当前模型 `thinking_modes` 中，例如 `default`、`fast`、`low`、`medium`、`high`、`xhigh` |
| `context_resources` | array | 否 | 文件或历史消息引用 |
| `edited_from_message_id` | string | 否 | 编辑历史提问时的审计线索；当前前端编辑重发主要通过原消息 `parent_message_id` 形成分支，暂不依赖该字段 |

文件类 `context_resources` 只允许提交 `resource_type`、`resource_id` 和可选展示名。`relative_path`、`sha256`、`mime_type`、`size_bytes` 等可信元数据必须以后端资源索引为准。

历史消息引用类 `context_resources` 只允许提交：

```json
{
  "resource_type": "message_quote",
  "resource_id": "message_id",
  "quote_text": "选中的历史消息文本"
}
```

校验要求：

- `raw_text` 去除首尾空白后可为空；但若同时没有 `context_resources`，返回空输入错误且不写入消息。
- 若当前账号没有配置模型服务、没有添加可用模型或没有可用 `chat` 默认模型，返回 `MODEL_NOT_CONFIGURED`。
- 若请求中的 `model_id` 不存在、不属于当前账号或未添加，返回 `MODEL_NOT_FOUND`。
- 若请求中的 `model_id` 属于当前账号但不是 `chat` 默认模型，返回 `INVALID_REQUEST`；v0.1.0 首页真实发送只允许 `chat` 默认模型。
- `thinking_mode` 必须包含在当前模型 `thinking_modes` 中。
- 本轮引用文件资源时，后端必须校验资源属于当前 `account` 和当前 `session_id`。
- 当前 `chat` 模型和 `vision_parse` 模型都不支持文件格式时返回 `MODEL_FILE_UNSUPPORTED`，不得写入 `file_upload` 或 `user_message`。
- 当前候选处理模型元数据声称支持、但对应 provider adapter 不能原生转发该 MIME 时返回 `MODEL_ATTACHMENT_UNSUPPORTED`，不得写入 `file_upload` 或 `user_message`。
- 历史消息引用必须校验被引用消息属于当前账号和当前会话，且 `quote_text` 来自该消息内容。
- 同一 `session_id` 下若已有 `queued` 或 `streaming` 轮次，发送新消息返回 `INVALID_REQUEST`。
- 用户编辑历史提问重新提交时，`parent_message_id` 应填写被编辑消息原本的父消息 ID，追加新消息节点，不覆盖原消息。

请求示例：

```json
{
  "session_id": "019db81e-80a0-7000-8a00-019db81e80a1",
  "parent_message_id": null,
  "raw_text": "报告里肌酐偏高，这严重吗？",
  "model_id": "openrouter:openai/gpt-4.1-mini",
  "thinking_mode": "default",
  "context_resources": [
    {
      "resource_type": "file",
      "resource_id": "019db820-c6a8-7001-8a01-019db820c6aa"
    }
  ]
}
```

响应字段：

| 字段 | 说明 |
| --- | --- |
| `session_id` | 会话 ID |
| `turn_id` | 本轮 ID |
| `user_message_id` | 用户消息 ID |
| `assistant_message_id` | 助手消息 ID，异步时可稍后返回 |
| `assistant_parent_message_id` | 助手消息父节点 |
| `model_id` | 实际使用模型 |
| `message_status` | `queued`、`streaming`、`completed`、`failed`、`cancelled` |
| `stream_id` | 流式订阅标识 |
| `context_resources` | 归一化后的上下文资源 |
| `content` | 发送接口当前返回空字符串；助手正文通过 SSE 增量和会话详情获得 |
| `created_at` | 创建时间 |

## 4. 重新生成

```http
POST /api/conversations/{session_id}/messages/{message_id}/regenerate
Content-Type: application/json
```

要求：

- `message_id` 可为被重新生成的助手消息，也可为生成中回答被取消后对应的用户消息；当前代码允许对已完成或已取消且保留的助手消息发起重新生成。
- 若 `message_id` 不属于用户消息或助手消息，返回 `INVALID_REQUEST`。
- 后端必须校验目标消息属于当前登录 `account` 和当前 `session_id`。
- 后端追溯其对应的用户消息。
- 重新生成前同样校验会话内不存在进行中的 `queued` 或 `streaming` 轮次；若同一用户消息已经有进行中的轮次，后端直接返回该 pending 轮次用于前端继续订阅。
- 可传 `model_id` 和 `thinking_mode`；为空时复用原回答模型和推理强度。
- 重新生成时创建新的 `turn_id` 和新的输出节点。
- 原助手回复及其链路必须保留，并与新输出构成并列分支。
- 若用户在生成中点击 `重新生成`，前端必须先调用取消接口且传 `preserve_partial=false`，后端只取消当前轮次，不把半截助手回答写成正式消息，然后再以同一用户消息创建新的生成轮次。

响应字段与发送消息接口保持一致。

## 5. 取消生成

```http
POST /api/conversations/{session_id}/turns/{turn_id}/cancel
Content-Type: application/json
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `preserve_partial` | boolean | 否 | 默认 `true`；是否把已展示的半截回答保存为正式助手消息 |
| `partial_content` | string | 否 | 前端已收到的助手回答正文增量 |
| `partial_thinking` | string | 否 | 前端已收到的思考过程增量 |

要求：

- 只允许取消当前登录 `account` 名下会话的 `queued` 或 `streaming` 轮次。
- 取消后 `conversation_turns.status` 写为 `cancelled`，并清除该会话的进行中阻塞状态。
- 普通停止生成使用 `preserve_partial=true`：后端追加 `turn_cancelled` 记录，并把 `partial_content` 写成 `assistant_message.status=cancelled`、`stop_reason=cancelled` 的正式助手消息；若存在 `partial_thinking`，同时写入 `thinking_process`。
- 若 `partial_content` 为空，取消助手消息正文写入“生成已取消。”。
- 生成中点击 `重新生成` 使用 `preserve_partial=false`：后端只追加 `turn_cancelled` 记录并取消轮次，不写入半截 `assistant_message`。
- 取消后的同一会话可继续发送消息或重新生成，不再返回“当前会话有正在进行的生成任务”。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `session_id` | 会话 ID |
| `turn_id` | 被取消轮次 ID |
| `status` | 固定为 `cancelled` |
| `preserve_partial` | 本次是否保存半截助手消息 |
| `stream_id` | 原流式订阅 ID |
| `assistant_message_id` | 保存半截消息时返回助手消息 ID，否则为 `null` |
| `thinking_message_id` | 保存半截思考过程时返回思考消息 ID，否则为 `null` |

## 6. 流式输出和轮次状态

流式订阅：

```http
GET /api/conversations/streams/{stream_id}
Accept: text/event-stream
```

事件类型：

| event | 说明 |
| --- | --- |
| `thinking_delta` | 模型显式返回且允许展示的思考过程增量 |
| `content_delta` | 最终回答内容增量 |
| `completed` | 本轮生成完成 |
| `failed` | 本轮生成失败 |
| `cancelled` | 本轮生成被用户取消 |

流式订阅负责消费模型输出，并在终态更新 `conversation_turns.status` 为 `completed`、`failed` 或 `cancelled`。对已经落盘的完成、失败或取消轮次，流式订阅按时间线内容回放对应事件。

当前实现说明：

- 只有 `status=streaming` 且助手消息尚未落盘时，流式接口才发起 provider 调用。
- provider 返回显式思考内容时写入 `thinking_process`，否则只写入 `assistant_message`。
- provider 流式调用失败时更新 `conversation_turns.status=failed` 并发送 `failed` SSE 事件；当前不额外写入失败态 `assistant_message`。
- provider 流式失败事件当前统一使用 `MODEL_ERROR` 作为事件 `code`，具体认证失败或超时文本保留在 `message` 中；连接测试和远端模型列表接口仍映射为 `PROVIDER_AUTH_FAILED` 或 `MODEL_TIMEOUT`。
- 当前 provider messages 由健康问答 system prompt、当前活动路径上的历史 user/assistant 文本、历史消息引用和原生附件 content part 组成；不根据 `context_window_tokens` 自动截断历史，也不调用 `compact` 默认模型生成摘要。

轮次状态查询：

```http
GET /api/conversations/{session_id}/turns/{turn_id}
```

要求：

- 只允许查询当前登录 `account` 名下会话的轮次。
- `status` 契约至少包含 `queued`、`streaming`、`completed`、`failed`、`cancelled`；当前代码创建轮次后直接进入 `streaming`，`queued` 为后续队列化预留状态。
- `stream_id` 在 `queued` 或 `streaming` 时必须返回，用于前端重新订阅。
- `completed` 时必须返回最终 `assistant_message_id`。
- `failed` 或 `cancelled` 时必须返回稳定错误码和可展示错误信息。

## 7. 会话列表与详情

会话列表：

```http
GET /api/conversations
```

返回当前登录 `account` 下最近 50 条会话，按 `last_active_at` 倒序排列。当前代码暂不接收分页参数，响应中固定返回 `has_more: false` 和 `next_cursor: null`。

当前实现只返回 `active_path_message_ids` 非空的会话。仅上传文件但尚未发送用户消息时，上传接口会创建草稿会话并保存资源，但该草稿没有活动消息路径，不进入会话列表；发送第一条消息后，`ConversationService.send_message` 会写入用户消息并更新活动路径，此时会话才进入列表。

会话详情：

```http
GET /api/conversations/{session_id}
```

要求：

- 返回当前活动路径上的已落盘消息。
- 响应同时返回 `all_messages`，用于前端分支计数、分支预览和切换；用户主视图仍以 `active_path_message_ids` 对应的 `messages` 为准。
- 草稿会话详情允许返回空 `messages`，用于前端继续展示待发送资源和后续发送。
- 若存在未完成轮次，额外返回 `pending_turns`。
- `pending_turns` 每项至少包含 `turn_id`、`status`、`stream_id`、`user_message_id`、`created_at`、`updated_at`。
- 前端可用 `pending_turns` 展示生成中状态并重新订阅流式输出。

消息响应字段：

| 字段 | 说明 |
| --- | --- |
| `message_id` | 消息 ID |
| `turn_id` | 本轮 ID |
| `parent_message_id` | 父消息 ID |
| `role` | `user`、`assistant`、`thinking` |
| `model_id` | 模型 ID |
| `thinking_mode` | 用户消息推理强度 |
| `content` | 文本内容 |
| `context_resources` | 用户消息上下文资源 |
| `status` | 助手消息终态 |
| `created_at` | 创建时间 |

## 8. 删除会话

```http
DELETE /api/conversations/{session_id}
```

要求：

- 后端校验会话属于当前 `account`。
- 删除 `conversation_sessions` 中该会话索引。
- 删除 `conversation_turns` 中该会话轮次记录。
- 删除 `conversation_resources` 中该会话资源索引。
- 删除 `timeline_path` 对应的会话 JSONL 文件。
- 删除 `conversations/attachments/{session_id}/` 附件目录。
- 删除会话不删除已经创建的收藏快照。
- 原会话删除后，收藏详情仍可展示快照，但不展示返回原对话入口。

响应示例：

```json
{
  "success": true,
  "session_id": "019db81e-80a0-7000-8a00-019db81e80a1",
  "message": "会话已删除"
}
```

## 9. 切换分支

```http
PATCH /api/conversations/{session_id}/active-path
Content-Type: application/json
```

请求示例：

```json
{
  "active_path_message_ids": [
    "019db820-d2c4-7004-8a04-019db820d2c9",
    "019db821-3fc0-7005-8a05-019db8213fc6"
  ]
}
```

校验要求：

- `active_path_message_ids` 必须全部属于当前登录账号和当前 `session_id`。
- 路径必须能按 `parent_message_id` 从根消息连续连接到目标消息。
- 不允许提交不存在、跨会话、跨账号或断裂的消息 ID。
- `thinking_process` 节点可包含在路径中用于恢复完整链路。
- 前端分支计数不得把 `thinking_process` 单独作为可切换回答分支。

## 10. 报告占位列表

```http
GET /api/reports
```

该接口仅用于 v0.1.0 工作台中的报告占位入口，本版本实现返回空列表。当前代码不校验登录态、不读取账号数据，也不代表报告能力开放。

要求：

- v0.1.0 不通过该接口交付正式报告能力。
- 返回空列表不得触发报告上传入库、结构化解析、OCR 解析或报告详情展示。
- 前端不得把该接口的存在表现为报告能力已经完成。

响应示例：

```json
{
  "reports": []
}
```

## 11. 会话数据存储

会话数据位于账号私有目录：

```text
{account}/conversations/
  db_storage/sessions.db
  sessions/{session_id}.jsonl
  attachments/{session_id}/{resource_id}.{ext}
```

`sessions.db` 至少包含：

### conversation_sessions

| 字段 | 说明 |
| --- | --- |
| `session_id` | 会话 ID |
| `account` | 当前账号 |
| `title` | 会话标题 |
| `timeline_path` | JSONL 时间线相对路径 |
| `created_at` | 创建时间 |
| `last_active_at` | 最近活跃时间 |
| `last_message_preview` | 最近消息摘要 |
| `active_path_message_ids` | 当前展示路径 |

### conversation_turns

| 字段 | 说明 |
| --- | --- |
| `turn_id` | 轮次 ID |
| `session_id` | 会话 ID |
| `account` | 当前账号 |
| `user_message_id` | 用户消息 ID |
| `assistant_message_id` | 助手消息 ID |
| `thinking_message_id` | 思考过程消息 ID |
| `stream_id` | 流式订阅 ID |
| `status` | 轮次状态 |
| `error_code` | 错误码 |
| `error_message` | 错误信息 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

### conversation_resources

| 字段 | 说明 |
| --- | --- |
| `resource_id` | 资源 ID |
| `session_id` | 会话 ID |
| `account` | 当前账号 |
| `name` | 文件名 |
| `mime_type` | 可信 MIME 类型 |
| `size_bytes` | 文件大小 |
| `relative_path` | 资源相对路径 |
| `thumb_path` | 缩略图相对路径 |
| `sha256` | 文件哈希 |
| `source` | `user_upload` 等来源 |
| `status` | 处理状态 |
| `usage_status` | `pending`、`attached`、`expired`、`deleted` |
| `expires_at` | 过期时间 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

表结构示例：

```sql
CREATE TABLE IF NOT EXISTS conversation_sessions (
    session_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    title TEXT NOT NULL,
    timeline_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL,
    last_message_preview TEXT DEFAULT '',
    active_path_message_ids TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    account TEXT NOT NULL,
    user_message_id TEXT,
    assistant_message_id TEXT,
    thinking_message_id TEXT,
    stream_id TEXT,
    status TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS conversation_resources (
    resource_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    account TEXT NOT NULL,
    name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    relative_path TEXT NOT NULL,
    thumb_path TEXT,
    sha256 TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    usage_status TEXT NOT NULL DEFAULT 'pending',
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id)
);
```

## 12. 会话时间线

每个 `session_id` 对应一个 JSONL 时间线文件。每行 JSONL 都是一条可追加、可审计、可恢复的稳定记录。
当前实现直接使用 `sessions/{session_id}.jsonl` 保存时间线。

单行外层字段：

| 字段 | 说明 |
| --- | --- |
| `timestamp` | 记录写入时间 |
| `type` | 顶层记录类型 |
| `payload` | 具体记录内容 |

v0.1.0 需落地或预留的顶层行类型：

| type | 说明 |
| --- | --- |
| `file_upload` | 文件上传记录 |
| `user_message` | 用户消息 |
| `thinking_process` | 模型显式返回且允许展示的思考过程或摘要 |
| `assistant_message` | 助手回答消息；普通停止生成保留的半截回答也可写入该类型 |
| `turn_cancelled` | 用户取消生成记录，标明是否保存半截助手消息 |
| `tool_call` / `tool_result` | 工具调用及结果，本期可预留 |
| `hook_result` | Hook 执行结果，本期可预留 |
| `compacted` | 长会话压缩摘要，本期可预留，不要求前端暴露 |

消息链路字段保存在 `payload` 中：

- `message_id`
- `parent_message_id`
- `session_id`
- `turn_id`

分支规则：

- 编辑历史用户提问时，不覆盖原用户消息，也不删除原助手回答。
- 新提问使用新的 `turn_id` 和新的消息节点。
- 重新生成助手回答时，新回答的 `parent_message_id` 指向同一用户消息，原回答保留。
- 普通取消生成时，保留的半截助手消息也是正式 `assistant_message`，可成为当前活动路径末端；重新生成触发的取消不产生半截助手消息。
- 当前展示路径由 `conversation_sessions.active_path_message_ids` 决定。

当前实现中的助手消息在存在 provider 思考内容时以 `thinking_process.message_id` 为 `parent_message_id`，否则以用户消息为父节点。失败轮次只记录在 `conversation_turns` 和 `failed` SSE 事件中，不追加失败态助手消息。

## 13. 前端无接口操作

以下操作由前端完成，不新增后端接口：

- 复制消息文本到剪贴板。
- 在报告或生活场景发送时阻止真实大模型请求；当前用占位标题和输入框 placeholder 表达未开放，文本输入禁用、附件入口隐藏，不额外调用后端接口。
- 选择分支起点后把下一条消息的 `parent_message_id` 指向该助手回复。
- 点击原始文件辅助入口时切换到 `/` 下的原始文件占位视图，不新增后端接口。
