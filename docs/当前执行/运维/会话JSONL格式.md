# 会话 JSONL 格式

> 文档层级：当前执行 / 运维与存储格式
>
> 负责：会话 JSONL 的逐行编码、首行 header、事件信封、23 种事件的最低 `data` 结构、写入与恢复边界，以及安全盘点方法。
>
> 不负责：事件的业务顺序与页面投影、轮次 Worker 策略、SQLite 表结构、附件文件格式或动态实例快照。
>
> 上位文档：[技术架构总览](../架构/技术架构总览.md)；事件语义与投影见[会话事件与投影](../架构/会话事件与投影.md)，路径与权限见[本地存储](本地存储.md)，SQLite 索引表见[数据库结构](数据库结构.md#conversationsdb)。

JSONL 是唯一的会话事件持久化格式。它不是数据库，也不是一个外层 JSON 数组，而是“每行一个完整 JSON 对象”的只追加事件文件。一个会话对应一个 JSONL：第一行描述会话，第二行开始按顺序保存事件。

需要先区分三类持久化内容：

| 内容 | 位置 | 作用 |
| --- | --- | --- |
| 会话索引与运行状态 | `conversations.db` | 列表、标题、置顶、轮次状态、附件索引和 JSONL 定位 |
| 会话完整执行记录 | 会话 JSONL | 用户消息、模型请求与输出、工具调用与结果、错误、耗时和投影依据 |
| 附件二进制 | `conversations/attachments/` | 实际上传文件；JSONL 只保存引用和进入模型请求后的安全表示 |

JSONL 是会话事件的唯一可信源，`conversations.db` 不保存同一批事件。准确物理位置以[本地存储](本地存储.md)为准。

进程内可以复用已校验的会话快照，最多保留 64 份，按原始文件大小合计不超过 8 MiB。每次读取都在文件锁内核对文件身份、大小、更新时间和状态变更时间；其它进程写入、替换或截断文件后重新读取并校验。追加内容在持久化完成后更新快照，包含替换来源引用的事件仍校验此前的来源。返回值与缓存中的可变内容隔离，缓存不替代 JSONL、文件锁、追加校验或持久化刷新。

## 文件级格式

每条记录使用 UTF-8 紧凑 JSON：

- 中文按原字符保存，不转成 `\uXXXX`。
- 字段之间不增加格式化空格或缩进。
- 每条记录都必须以 LF（`\n`）结束，包括最后一条；空行不合法。
- 不允许 NaN、Infinity 或不能编码成 JSON 的值。
- 文件没有 BOM、压缩、文件级加密、校验和、大小上限或自动轮转。
- 文件内容是明文健康与执行数据；安全依赖账号目录和文件权限，以及写入前的凭证与附件二进制清理。

真实文件是一行一个对象。下面这个最小示例包含一个根会话 header 和两条事件：

```jsonl
{"type":"session","version":2,"id":"session-id","accountId":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","createdAt":1786665600000}
{"type":"turn/start","seq":0,"time":1786665600100,"data":{"turn_id":"turn-id","user_message_id":"user-message-id","stream_id":"stream-id"}}
{"type":"user/message","seq":1,"time":1786665600200,"data":{"turn_id":"turn-id","message_id":"message-id","parent_message_id":null,"content":"你好"},"surfaceOp":"append"}
```

物理行号与事件序号的关系固定为：第一条事件位于第 2 行且 `seq=0`，因此事件行号始终等于 `seq + 2`。

## 第一行：会话 header

根会话第一行只允许以下字段：

```json
{
  "type": "session",
  "version": 2,
  "id": "session-id",
  "accountId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "createdAt": 1786665600000
}
```

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `type` | 字符串 | 固定为 `session` |
| `version` | 整数 | 当前固定为 `2`；其它版本拒绝读取 |
| `id` | 非空字符串 | 会话 ID，必须与调用路径中的会话 ID 一致 |
| `accountId` | 规范 UUID 字符串 | 操作账号不可变 `account_id`，必须与调用身份、索引行和账号目录一致 |
| `createdAt` | 非负整数 | 正常写入为 Unix epoch 毫秒 |

持久化层的 `SessionHeader.account_id` 序列化为 JSON 字段 `accountId`；两种命名表达同一不可变账号身份。

独立子会话额外且必须成对包含：

```json
{
  "type": "session",
  "version": 2,
  "id": "child-session-id",
  "accountId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "createdAt": 1786665600000,
  "parentSession": "parent-session-id",
  "seedEventCount": 42
}
```

`parentSession` 必须是非空字符串，`seedEventCount` 必须是正整数，并等于创建子会话时复制的 seed 事件数量。根会话必须省略这两个字段，不能写成 `seedEventCount: 0`。Header 是封闭结构，以上 7 个字段之外的字段都会被拒绝。Header 不包含 `member_id` 或成员名称；成员删除只清空私有数据库中的关联，既有 JSONL 事件中出现过的成员身份、名称及医疗报告引用保持原样，不用于恢复当前关联或授权。

版本 2 是当前 header 的完整读取与写入契约；其它版本返回格式错误并保持文件原样。

## 第二行以后：事件信封

每条事件的外层结构固定为：

```json
{
  "type": "assistant/message",
  "seq": 8,
  "time": 1786665600000,
  "data": {
    "turn_id": "turn-id",
    "message_id": "assistant-message-id",
    "parent_message_id": "user-message-id",
    "content": "回答正文"
  },
  "sourceEventSeqs": [5, 6],
  "surfaceOp": "append"
}
```

| 字段 | 必填 | 类型与规则 |
| --- | --- | --- |
| `type` | 是 | 23 种当前事件类型之一 |
| `seq` | 是 | 非负整数；文件中必须从 `0` 无断号连续递增 |
| `time` | 是 | 非负整数；正常写入为 epoch 毫秒，不要求跨事件单调递增 |
| `data` | 是 | JSON 对象；不能包含重复会话作用域的 `session_id` |
| `sourceEventSeqs` | 否 | 无重复的非负整数数组；每项必须严格小于当前 `seq`，不要求排序 |
| `surfaceOp` | 否 | 当前事件对线性模型表面的追加或替换规则 |

事件信封也是封闭结构，不能增加其它顶层字段。与信封不同，`data` 是开放对象：必须包含对应事件的最低字段，但除 `session_id` 外通常可以带额外 JSON 字段。所以下一节描述的是“最低可读格式”，不是所有事件都只能有这些字段。

`surfaceOp` 只允许出现在 `user/message`、`assistant/message`、`tool/result` 和 `compaction/checkpoint`：

- `"append"`：把该记录追加到当前线性模型表面。
- `{"op":"replace","start":N,"end":M}`：替换左闭右开的事件表面区间，要求 `0 <= N < M`。

`compaction/checkpoint` 必须使用 `replace`，并携带非空 `sourceEventSeqs` 精确列举被替换的来源事件；其 `end` 不得超过当前事件 `seq`。区间只定位覆盖范围，实际替换只使用来源集合，包括被纳入新摘要的旧 checkpoint；`replaced_turn_ids` 仅表达涉及轮次，不用于整轮删除。这里的 replace 是投影含义：原始事件行仍保留，不会因此从 JSONL 中删除或改写。`compaction/status` 不携带 `surfaceOp`，不进入模型消息表面。

`tool/result` 使用 `replace` 时，`sourceEventSeqs` 必须恰好为一个先前结果的序号 `[N]`，`surfaceOp` 必须精确为 `{"op":"replace","start":N,"end":N+1}`。新结果的 `status` 只能是 `completed` 或 `failed`；被替换事件必须是 `status="interrupted"`、`result=null`、`error.code="TOOL_OUTCOME_UNKNOWN"` 的 `tool/result`，且新旧事件的 `turn_id, call_id, tool_call_id, name` 全部相同。不能借此覆盖已知成功或失败结果，也不能替换其它调用或一段事件。单事件读取校验来源数量、精确区间和新状态；可读取完整来源前缀时继续校验目标类型、未知结果条件及调用身份。投影位置、来源更新与摘要失效规则见[投影与展示](../架构/会话事件与投影.md#投影与展示)。

## 23 种事件的最低 `data` 格式

下表以当前读取器实际接受的结构为准。“常见扩展”是当前写入路径便于理解的代表，不是字段白名单。

### 等候输入

| `type` | 最低必填字段 | 额外结构规则与常见扩展 |
| --- | --- | --- |
| `input/queued` | `input_id, content, model_id, thinking_mode, context_resources, created_at` | 除 `context_resources` 外均须为字符串，只有 `input_id` 强制非空；`context_resources` 须为数组 |
| `input/queue-reordered` | `input_ids` | 无重复的非空字符串数组 |
| `input/queue-removed` | `input_id, reason` | 两者均为非空字符串；当前常见 reason 为 `deleted`、`restored_to_draft` |

这些事件只用于恢复同一会话的等候输入队列，不进入会话正文或模型上下文。

### 轮次与行动步骤

| `type` | 最低必填字段 | 额外结构规则与常见扩展 |
| --- | --- | --- |
| `turn/start` | `turn_id, user_message_id, stream_id` | 三个标识均为非空白文本；常见扩展：`final_assistant_message_id, model_id`；编辑或重新生成还可记录被替代轮次和消息 ID |
| `turn/thinking_mode_changed` | `turn_id, requested_mode, effective_mode, reasons` | 当前写入路径把 `reasons` 写成字符串数组，并带 `created_at` |
| `turn/end` | `turn_id, reason` | `reason` 支持字符串或带 `kind` 的对象；标准写入使用对象，并可携带错误码、消息和部分正文保留信息 |
| `step/start` | `turn_id, step, purpose` | `step` 必须是正整数 |
| `step/end` | `turn_id, step` | `step` 必须是正整数；常见扩展：`status, error` |

### 用户与助手消息

| `type` | 最低必填字段 | 额外结构规则与常见扩展 |
| --- | --- | --- |
| `user/message` | `turn_id, message_id, parent_message_id, content` | `parent_message_id` 可为 `null`；常见扩展：模型、思考模式、资源引用、排队输入 ID、标题标记和创建时间 |
| `user/message-update` | `message_id, patch` | 投影只会应用对象型 `patch`；当前用于更新正文、模型、思考模式或上下文资源 |
| `assistant/chunk` | `turn_id, step, call_id, chunk` | 常见扩展：消息与父消息 ID、模型、purpose、耗时和创建时间；`chunk` 子类型见下文 |
| `assistant/message` | `turn_id, message_id, parent_message_id, content` | `content` 只能为 `null`、字符串或内容数组；可选 `tool_calls` 必须是数组，每项必须有非空 `id` 和 `function.name`；可选 `branch_addressable` 必须为布尔值 |
| `assistant/message-update` | `message_id, patch` | 投影只会应用对象型 `patch`；当前主写入链没有常规使用点 |

### 模型请求、结果与 Observation

| `type` | 最低必填字段 | 额外结构规则与常见扩展 |
| --- | --- | --- |
| `request/header` | `turn_id, step, call_id, purpose, header` | `step` 为正整数；`header` 必须是对象且含对象型 `provider_payload`；不能在 header 顶层复制 `system/messages/tools/tool_choice/normalized_request` |
| `request/context` | `turn_id, step, call_id, context` | `step` 为正整数；`context.provider_source.path` 必须是 JSON Pointer 字符串；可选字符区间 `start/end` 必须成对且满足 `0 <= start <= end` |
| `model/result` | `turn_id, step, call_id, result` | `step` 为正整数；常见扩展：`status, duration_ms, channel_durations_ms, created_at, error` |
| `harness/observation` | `turn_id, step, observation, status` | `step` 为正整数；`observation` 必须是对象；`status` 只能为 `completed` 或 `failed`；常见扩展：`call_id, created_at` |

### 工具、资源与工作流

| `type` | 最低必填字段 | 额外结构规则与常见扩展 |
| --- | --- | --- |
| `tool/call` | `turn_id, call_id, tool_call_id, name, arguments` | `tool_call_id` 必须非空；当前上游把 `arguments` 约束为对象；常见扩展：`step, created_at` |
| `tool/result` | `turn_id, call_id, tool_call_id, name, result, status` | `status` 只能为 `completed/failed/interrupted`；后两者必须带对象型 `error`；使用 replace 时还必须有仅含一个来源的信封 `sourceEventSeqs`，并仅以 completed/failed 结果精确替换同一调用的 `TOOL_OUTCOME_UNKNOWN` 中断结果，详见上方 `surfaceOp` 规则；常见扩展：`step, created_at` |
| `resource/attached` | `resource_id, original_filename, mime_type, size_bytes, relative_path, sha256` | 保存附件身份、原始文件名和完整性信息；不含内部存储/生命周期状态、过期时间、`source`、缩略图路径或文件二进制 |
| `workflow/trace` | `turn_id, payload` | `payload` 保存工作流状态或安全失败信息，事件层不限定其内部结构 |

### 上下文压缩

每次摘要调用的 `request/header.header.model_config.summary_kind` 为 `history` 或 `turn_prefix`，摘要输入也标明同名类型。该字段用于审计与模型记录展示，不作为 Provider 生成参数发送。对应模型记录投影保留类型，状态仍按同一个压缩操作聚合。checkpoint 的 `summary` 由程序以 `# 历史摘要`、`# 轮次前半段摘要` 拼接非空层；连续压缩将上次完整 `summary` 输入历史摘要更新，不解析 `content` 或章节恢复分层状态。

| `type` | 最低必填字段 | 额外结构规则与常见扩展 |
| --- | --- | --- |
| `compaction/checkpoint` | `turn_id, message_id, compaction_id, summary, content, replaced_turn_ids, estimated_tokens_before, estimated_tokens_after, target_tokens` | `summary` 为供下次摘要读取的独立非空摘要；`content` 为完整包裹摘要及精确保留内容的非空模型消息；`compaction_id` 关联同次 `compaction/status.message_id`；`replaced_turn_ids` 必须是至少一个非空轮次 ID；三个估算词元字段均为必填非负整数；信封必须带 replace `surfaceOp` 和非空 `sourceEventSeqs` |
| `compaction/status` | `turn_id, message_id, status, reason, estimated_tokens_before, target_tokens` | `turn_id` 非空，`message_id` 为同一次操作稳定的 `compaction_<id>`；`status` 为 `running/completed/failed`，`reason` 为 `threshold/overflow/tool_result`；仅 completed 必须带 `estimated_tokens_after`；仅 failed 必须带 `error`，含非空 `code/message` |

checkpoint 的三个估算词元字段全部必填；status 的压缩前估算值和目标值必填，压缩后估算值仅 completed 必填且只允许在该状态出现。所有估算词元字段必须是非负整数，不接受布尔值。`compaction/status` 各状态变化都追加新事件，详情和 SSE 按同一 `message_id` 投影更新同一 `record_id`，保留首次位置和时间；`completed` 表示有效 checkpoint 已提交。状态记录始终投影为 `context_type="compaction_status"`、`purpose="context_compaction"`、`label="上下文压缩"`，携带相同状态、估算字段和安全错误；checkpoint 投影为 `compacted_summary` 并提供三个估算字段。开始状态先于该次分块模型请求，结束状态更新同一记录；未提交的摘要不得写成 checkpoint。checkpoint 必须独立保存 `summary`，不能通过解析 `content` 恢复该字段；`compaction_id` 必须准确指向同一次状态操作。completed 状态行缺失或损坏时，有效 checkpoint 仍是完成依据，恢复后的状态投影规则见[投影与展示](../架构/会话事件与投影.md#投影与展示)；文件读取继续遵守既定损坏恢复边界。预算、取消与快照 CAS 规则见[上下文压缩](../架构/会话事件与投影.md#上下文压缩)。

`_pending_execution` 是模型表面投影内部标记，不是 JSONL 最低字段，也不发送给 Provider。中断且结果未知的工具组按该标记继续受到压缩保护，精确语义见[预算与选择范围](../架构/会话事件与投影.md#预算与选择范围)。

读取器主要保证 header、封闭信封、JSON 可编码、已知事件类型、连续 `seq` 和上述少数单事件结构。它不会普遍验证轮次、消息、模型调用和工具调用之间的全部业务因果关系；这些关系由 Service、Repository、投影和运行恢复共同维护。

## 常见嵌套结构

### Provider 请求与上下文来源

`request/header.header.provider_payload` 是实际发送 Provider payload 经安全处理后的持久化副本，也是同一次请求全部 `request/context` 的唯一内容来源。Header 还常见：

```json
{
  "model": {
    "model_id": "model-id",
    "provider_id": "provider-id",
    "remote_model_id": "remote-model-id",
    "model_name": "display-name",
    "context_window_tokens": 128000
  },
  "thinking_mode": "default",
  "transport_mode": "native",
  "model_config": {},
  "parent_tool_call_id": null,
  "provider_payload": {}
}
```

`request/context.context.provider_source` 使用 RFC 6901 JSON Pointer 定位同一个 payload；文本片段可再带 Unicode 左闭右开字符区间：

```json
{
  "path": "/messages/3/content",
  "start": 0,
  "end": 120
}
```

`request/context` 不是第二份重新拼接的模型输入。完整覆盖与逐值相等在请求写入前校验；从磁盘单独读取一条事件时只校验 pointer 和可选区间的基本结构。

### 模型流式 chunk

当前 `assistant/chunk.data.chunk` 会出现：

| `chunk.type` | 代表性字段 | 含义 |
| --- | --- | --- |
| `reasoning-delta` | `delta` | reasoning 文本增量 |
| `text-delta` | `delta` | 正文文本增量 |
| `raw-text-delta` | `delta` | 文本工具协议原始输出增量 |
| `tool-call-delta` | `index, id, name_delta, arguments_delta` | 原生工具调用增量 |
| `usage` | `usage` | Provider 返回的 Token 用量 |
| `stop` | `reason` | Provider 停止原因 |
| `channel-end` | `channel` | 一个模型输出通道结束及耗时边界 |

`assistant/chunk` 是执行时间线的原始增量，不等于最终助手消息。完整聚合结果进入 `model/result`，用户可见的正式回答进入 `assistant/message`。

### 模型结果与工具调用

当前成功的 `model/result.data.result` 形状为：

```json
{
  "content": "...",
  "raw_content": "...",
  "reasoning": "...",
  "tool_calls": [],
  "usage": {},
  "stop_reason": "end_turn"
}
```

模型工具调用使用 OpenAI-compatible 结构：

```json
{
  "id": "tool-call-id",
  "type": "function",
  "function": {
    "name": "tool-name",
    "arguments": "{\"key\":\"value\"}"
  }
}
```

模型请求的工具调用、实际 `tool/call` 和 `tool/result` 通过 `tool_call_id` 对应；持久化层只检查 ID 非空，跨事件对应关系由运行时保证。自动续读生成的 `assistant/message` 和 `tool/call` 额外保存 `origin="harness_pagination"`、`pagination={"root_call_id": 原查询调用标识, "page": 页次}`，每页使用独立调用标识；该来源表示 Harness 机械续读，不对应添加行动模型请求。每页 `tool/result.result.output.pagination` 保存 `page` 与 `complete`，后者表示整个查询是否已读完。

工具已经执行、但完整工具结果超预算或结果准备期间取消时，`tool/result` 的 `status="failed"`，`result` 保存完整实际工具结果用于审计，`error.details` 中的 `execution_completed=true` 和 `effects` 记录已完成操作。失败结果的模型投影只包含 `error`，不包含审计用的完整 `result`。

取消可能先追加 `interrupted / TOOL_OUTCOME_UNKNOWN` 占位结果。实际结果晚到时，Service 在账号、会话及资源权限校验后，核对既有调用的 `turn_id, call_id, tool_call_id, name`，在会话操作锁内幂等保存。修正事件仍使用 `tool/result`，`sourceEventSeqs` 只引用该占位事件，`surfaceOp` 为其单条位置的 `replace`。原事件保留用于审计，模型在原位置仅保留修正后的一个工具回复；依赖未知结果的摘要及其后继摘要失效。结果保存后继续传播取消，停止后续行动。已经确定的结果不能由不同结果覆盖。

工具业务结果中两个及以上键集合相同的对象数组，会递归编码为：

```json
{
  "$keys": ["field_a", "field_b"],
  "$rows": [
    ["value-a1", "value-b1"],
    ["value-a2", "value-b2"]
  ]
}
```

这是无损列式表示，不是摘要或截断；需要按对象访问的消费者先还原。`effects` 等控制元数据不参与该编码。

## 会保存什么，不保存什么

JSONL 会保存执行和审计所需的真实内容，包括：

- 用户消息、等候输入和助手正式回答。
- 模型 reasoning、正文增量、文本协议原始输出、最终结果、usage、停止原因、错误与耗时。
- 去除凭证和附件二进制后的最终 `provider_payload`，其中可能包含系统提示词、消息历史、工具参数 Schema 和当前健康资料。
- 模型请求工具调用、工具参数、完整工具业务结果、Observation 和安全错误。
- 附件元数据与资源引用；当模型实际读取文本内容时，相应安全 payload 仍可能包含该文本。

以下内容不得进入事件：

- API Key、登录凭证和 Cookie。
- 附件二进制；常见 base64 附件字段在持久化前替换为 `<attachment-binary-redacted>`。
- 会话标题生成的提示词、thinking/reasoning 和原始输出；标题只作为会话索引元数据更新。

通用事件读取器没有“敏感字段名黑名单”，凭证隔离依赖 Provider、工具和 Service 在写事件之前完成安全处理。因此排查 JSONL 时应把整个文件视为敏感健康数据，不能提交 Git、粘贴到公开工单或直接输出完整 `data`。

## 写入、锁与耐久性

### 创建

创建会话时先校验 header、连续 seed 和 `seedEventCount`。随后在锁内一次编码 header 与全部 seed，写入私有隐藏临时文件并 `fsync`，再以 hard link 原子发布最终文件，最后 `fsync` 会话目录。若最终文件已存在，只有 durable 内容完全相同时才按幂等成功处理。

因此正常创建不会让读取方看到半个 header 或半个 seed 文件。

### 追加

追加前在同名 `.jsonl.lock` 上持有独占锁，读取并校验现有文件，再检查新批次从当前事件数继续编号。可选 `expected_seq` 提供 CAS；竞争写入不满足时重试或返回冲突。

新事件以 `O_APPEND` 写入，正常返回前执行 `flush + fsync`。一个调用可以追加多条事件，但整批不是数据库事务；进程异常时可能留下若干完整行和最后一个无换行片段。恢复保留完整前缀并按下一节处理最后片段。

`.jsonl.lock` 是零字节 advisory lock 载体，正常情况下会长期保留；看到锁文件存在不表示当前有进程持锁。POSIX 系统同时使用进程内可重入锁和 `flock`，没有 `fcntl` 的平台只剩进程内锁。锁文件与 JSONL 都使用私有文件权限，具体模式见[本地存储](本地存储.md)。

### 加载与恢复

完整加载会检查 header、每条完整事件行和连续 `seq`。自动恢复只处理两件事：

1. 最后一条物理记录没有 LF 时，把文件截断到该行开始位置并 `fsync`。
2. 如果剩余事件中仍有开放轮次，按顺序追加未知结果的 `tool/result(status="interrupted")`、`step/end(status="interrupted")` 和 `turn/end(reason.kind="interrupted")`。

完整但非法的 JSON、未知事件类型、断号、坏 header 或路径/header 不一致不会自动修复。即使最后一行是完整 JSON，只要没有 LF，也按未提交尾片段整体丢弃。

增量读取 `read_from(from_seq)` 读取 header 后跳过更早事件，只解析请求的后缀；它不是完整文件健康检查。需要确认整个日志时必须做完整读取或使用下文只读盘点方法。

### 分叉、替换与删除

- 分叉会把父会话一个稳定轮次边界之前的完整事件前缀物理复制到子 JSONL；原 `seq/time/turn_id/message_id/resource_id` 保持不变，子 header 使用新会话 ID、直接父 ID 和实际 seed 数量。
- 当前产品事件写入路径只追加。持久化接口另有带 revision CAS 的全量 replace 能力，写临时文件后使用 `os.replace`；它不是 `surfaceOp=replace`，当前常规会话执行不调用它。
- 删除会话会删除 JSONL 和对应锁文件；`conversations.db` 的索引删除与文件删除属于跨 SQLite/文件系统操作，不是一个 SQLite 事务。
- Header 与事件区域通过不可变 `accountId` 维持稳定归属；当前用户标识和显示名称由认证账号实时投影。

JSONL 内部 revision 不是内容哈希，而是 `device:inode:size:mtime_ns`；lineage 是 `device:inode`。普通追加通常只改变 revision，全量替换会改变 inode 和 lineage。这两个值用于并发追尾和替换校验，不写进 JSONL。

## 与 `conversations.db` 的对应关系

当前存储关系如下：

```text
conversations.db.conversations
  session_id / relative_path
  parent_session_id / seed_event_count / title / member_id / ...
                      │
                      └── 定位一个 JSONL
                            第 1 行：header
                            第 2 行起：完整事件序列

conversations.db.conversation_turns      轮次运行状态索引
conversations.db.conversation_resources  附件索引
```

三处身份必须一致：调用身份、`accounts/{account_id}` 目录和 header `accountId`。文件名和 header `id` 对应 `conversations.session_id`，header `parentSession/seedEventCount` 对应索引中的分叉字段。这些是 Repository 维护的文件/数据库逻辑关系，不是 SQLite 外键；账号私有表不逐行重复 `account_id`。

## 安全只读盘点

JSONL 的会话数、行数、大小和事件类型会持续变化，不写进版本化契约。实例盘点应记录检查时间、时区、实际 `DATA_ROOT` 和账号作用域，并只输出 header 元数据、计数和结构，不输出消息正文、Provider payload、工具参数/结果或附件内容。

设定一个明确文件后，可使用：

```bash
jsonl_path='serenita_files/accounts/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/conversations/sessions/session-id.jsonl'

wc -l "$jsonl_path"
stat "$jsonl_path"
head -n 1 "$jsonl_path" | jq '{type,version,id,accountId,createdAt,parentSession,seedEventCount}'
tail -n +2 "$jsonl_path" | jq -r '.type' | sort | uniq -c
tail -n +2 "$jsonl_path" | jq -c '{type,seq,time,dataKeys:(.data|keys),sourceEventSeqs,surfaceOp}'
tail -c 1 "$jsonl_path" | od -An -t u1
```

最后一条命令应输出十进制 `10`，表示文件以 LF 结束。只验证 JSON 与连续序号而不显示 payload：

```bash
jq -s '
  .[1:] as $events
  | {
      event_count: ($events | length),
      seq_contiguous: (
        [range(0; ($events | length))] == [$events[].seq]
      )
    }
' "$jsonl_path"
```

只读盘点还应把 JSONL 与 `conversations.db.conversations`、`conversation_turns` 对照，检查缺失文件、孤儿文件、`relative_path`、分叉字段和轮次 ID。数据库检查方式见[数据库结构](数据库结构.md#读取当前本地实例状态)。动态盘点结果是带时间的运行观测，不替代本格式契约。
