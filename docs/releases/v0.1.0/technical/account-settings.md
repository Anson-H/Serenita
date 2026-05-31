# Serenita v0.1.0 账号设置技术设计

> 文档状态：当前执行 / 当前执行版本
>
> 关联产品需求文档：[账号设置 产品需求文档](../prd/account-settings.md)
>
> 技术设计索引：[README.md](./README.md)

## 1. 接口清单

| 接口 | 说明 |
| --- | --- |
| `PATCH /api/auth/account` | 修改当前账号资料 |
| `PATCH /api/auth/password` | 修改当前账号密码 |
| `GET /api/model-providers` | 获取模型服务配置 |
| `POST /api/model-providers` | 自动保存/新增或更新模型服务配置 |
| `PATCH /api/model-providers/{provider_id}` | 更新模型服务配置 |
| `POST /api/model-providers/{provider_id}/test` | 测试模型服务连接 |
| `GET /api/model-providers/{provider_id}/models` | 获取模型服务的模型列表 |
| `POST /api/models` | 添加可用模型 |
| `GET /api/models` | 获取已添加模型 |
| `DELETE /api/models/{model_id}` | 删除已添加模型 |
| `GET /api/model-defaults` | 获取默认模型用途设置 |
| `PATCH /api/model-defaults` | 批量更新默认模型用途设置 |

## 2. 修改账号资料

```http
PATCH /api/auth/account
Content-Type: application/json
```

该接口用于修改当前登录账号的可变资料。v0.1.0 只允许修改 `user_name`，不允许修改 `account`。

请求示例：

```json
{
  "user_name": "陈女士"
}
```

要求：

- 接口必须根据当前登录态定位 `account`，不得接受前端传入的 `account` 作为修改目标。
- `user_name` 去除首尾空白后不能为空。
- `user_name` 不能包含任何空白字符。
- 保存成功后更新 `auth_accounts.user_name` 和 `updated_at`。
- 若当前会话摘要或 `auth_sessions.user_name` 保存了用户名称，也应同步更新。

响应示例：

```json
{
  "account": "demo_patient",
  "user_name": "陈女士",
  "updated_at": "2026-04-23T10:15:00+08:00"
}
```

## 3. 修改密码

```http
PATCH /api/auth/password
Content-Type: application/json
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `current_password` | string | 是 | 当前密码 |
| `new_password` | string | 是 | 新密码 |
| `confirm_password` | string | 是 | 确认新密码 |

请求示例：

```json
{
  "current_password": "old-password",
  "new_password": "new-password",
  "confirm_password": "new-password"
}
```

要求：

- 接口必须根据当前登录态定位 `account`。
- 三个密码字段均不能为空。
- `confirm_password` 必须与 `new_password` 完全一致。
- `current_password` 必须能通过当前账号的 `password_hash` 校验。
- 校验失败时返回 `SIGN_IN_FAILED`，不得修改密码。
- 密码不得明文保存。
- 修改成功后重写 `auth_accounts.password_hash` 和 `updated_at`。
- 修改成功后撤销同一账号下除当前会话以外的其它有效 session。
- 当前会话可继续保持。

响应示例：

```json
{
  "success": true,
  "message": "密码已更新"
}
```

## 4. 模型提供方与模型服务

v0.1.0 设置页 UI 名称为 `模型提供方`，接口和存储仍沿用 `model_providers` / 模型服务命名。当前支持以下模型服务：

| provider_id | 显示名 | API 地址 | 官网地址 |
| --- | --- | --- | --- |
| `openrouter` | `OpenRouter` | `https://openrouter.ai/api/v1` | `https://openrouter.ai/settings/credits` |
| `deepseek` | `深度求索` | `https://api.deepseek.com` | `https://platform.deepseek.com/top_up` |
| `aliyun_bailian` | `阿里云百炼` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `https://bailian.console.aliyun.com/?tab=model#/api-key` |

模型服务配置要求：

- 用户选择模型服务后，系统自动填入官网地址和 API 地址。
- 用户可修改官网地址和 API 地址。
- API key 由用户自行输入，并绑定当前 `account`。
- 官网地址、API 地址和 API key 输入后自动保存到当前账号私有配置。
- 不同 `account` 不能共享已保存官网地址、API key、已添加模型或默认模型设置。
- API key 明文保存在当前账号私有 `config.db` 中，不写入前端本地持久化存储。
- 应用启动时会扫描已有账号的 `config.db`，迁移旧版 `models` 表中的能力字段和列顺序；旧版 `model_providers.key_info_data` 存在时会迁移为 `api_key` 并清理旧密钥列。
- 当前前端模型提供方列表展示服务名称、连接测试图标状态和进入详情箭头，不展示 API 地址，也不单独展示 `default_provider` 标记；详情区展示官网地址、API 地址、API key 和已添加模型列表。

## 5. 获取模型服务配置

```http
GET /api/model-providers
```

要求：

- 返回 v0.1.0 支持的模型服务清单。
- 合并当前登录 `account` 下的配置状态。
- 未配置的模型服务也应返回。
- 返回默认官网地址、当前账号已保存官网地址和当前账号已保存明文 API key，用于设置表单回填编辑。

响应示例：

```json
{
  "providers": [
    {
      "provider_id": "openrouter",
      "provider_name": "OpenRouter",
      "default_base_url": "https://openrouter.ai/api/v1",
      "default_official_url": "https://openrouter.ai/settings/credits",
      "base_url": "https://openrouter.ai/api/v1",
      "official_url": "https://openrouter.ai/settings/credits",
      "api_key": "sk-or-********",
      "configured": true,
      "default": true
    }
  ]
}
```

## 6. 自动保存模型服务配置

保存：

```http
POST /api/model-providers
Content-Type: application/json
```

局部更新：

```http
PATCH /api/model-providers/{provider_id}
Content-Type: application/json
```

保存请求示例：

```json
{
  "provider_id": "openrouter",
  "base_url": "https://openrouter.ai/api/v1",
  "official_url": "https://openrouter.ai/settings/credits",
  "api_key": "sk-or-********",
  "default": true
}
```

要求：

- `provider_id` 必须是 v0.1.0 支持的模型服务，否则返回 `NOT_FOUND`。
- `POST /api/model-providers` 用于自动保存，可重复提交同一个 `provider_id`；已存在时按更新处理。
- 更新时若该模型服务尚未配置，返回 `NOT_FOUND`。
- `official_url` 可为空；为空时前端仍保留用户输入状态。
- `base_url` 为空时使用模型服务默认 API 地址。
- API key 允许为空；为空时保存官网地址和 API 地址，但 `configured` 为 false。
- API key 非空时保存后直接覆盖当前账号该模型服务的已保存密钥，并将 `configured` 置为 true。
- 响应返回当前账号已保存的官网地址和明文 API key，用于设置表单回填编辑。
- 若设置 `default: true`，同一账号下其它模型服务的默认标记应置为 false。

响应示例：

```json
{
  "provider_id": "openrouter",
  "provider_name": "OpenRouter",
  "default_base_url": "https://openrouter.ai/api/v1",
  "default_official_url": "https://openrouter.ai/settings/credits",
  "base_url": "https://openrouter.ai/api/v1",
  "official_url": "https://openrouter.ai/settings/credits",
  "api_key": "sk-or-********",
  "configured": true,
  "default": true
}
```

## 7. 测试连接

```http
POST /api/model-providers/{provider_id}/test
Content-Type: application/json
```

请求示例：

```json
{
  "base_url": "https://openrouter.ai/api/v1",
  "api_key": "sk-or-********"
}
```

要求：

- 测试使用请求体中的临时 `base_url` 和 `api_key` 发起。
- 测试不持久化请求体中的临时 API key，也不改变已保存配置。
- 若请求体缺少 `api_key`，但当前账号保存过该模型服务 API key，后端可使用已保存密钥测试。
- 若两者都不存在，返回 `MODEL_NOT_CONFIGURED`。
- 认证失败返回 `PROVIDER_AUTH_FAILED`。
- 连接超时返回 `MODEL_TIMEOUT`。
- 其它模型服务调用失败返回 `MODEL_ERROR`。
- 错误响应不包含 API key。

成功响应示例：

```json
{
  "provider_id": "openrouter",
  "reachable": true,
  "message": "连接测试成功"
}
```

## 8. 远端模型列表接口

```http
GET /api/model-providers/{provider_id}/models
```

要求：

- 后端必须使用当前账号保存的 API 地址和 API key 调用远端模型列表接口。
- 远端请求格式为 `GET {base_url}/models`，其中 `base_url` 来自当前账号保存的 `model_providers.base_url`。
- 远端请求必须带上 `Authorization: Bearer <api_key>` 和 `Accept: application/json`。
- 只能使用当前登录 `account` 自己保存的 API key。
- 未配置 API 地址或 API key 时返回 `MODEL_NOT_CONFIGURED`。
- 远端返回 `401` 或 `403` 时映射为 `PROVIDER_AUTH_FAILED`；连接超时映射为 `MODEL_TIMEOUT`；其它远端错误映射为 `MODEL_ERROR`。
- 返回模型列表时应标记模型能力，包括是否支持文本、图片/文件理解、支持的文件 MIME 类型、思考过程或推理强度、工具调用、JSON 输出和上下文/输出长度上限。
- 返回模型列表必须保持模型服务远端返回顺序，后端和前端都不得重新排序。
- 如果远端不提供完整能力元数据，系统必须通过模型服务适配器补充：OpenRouter 读取 `architecture` 和 `supported_parameters`，深度求索按官方模型 ID 与参数文档判断，阿里云百炼按模型 ID、深度推理模式和模型目录规则判断；阿里云百炼的 `qwen3.5`、`qwen3.6`、`qwen3-vl` 系列按图片+视频输入处理，`qwen3.5-omni` 与 `qwen3-omni` 系列按图片+音频+视频输入处理。仍未命中时使用保守默认能力，并允许后续修正。
- 不允许在远端模型列表请求失败时返回假模型列表。

响应示例：

```json
{
  "account": "demo_patient",
  "provider_id": "openrouter",
  "models": [
    {
      "remote_model_id": "openai/gpt-4.1-mini",
      "model_name": "GPT-4.1 Mini",
      "supports_text": true,
      "file_mime_types": ["image/jpeg", "image/png", "application/pdf"],
      "thinking_modes": ["default", "low", "medium", "high"],
      "supports_tool_calling": true,
      "supports_json_output": true,
      "context_window_tokens": 1048576,
      "max_output_tokens": 32768
    }
  ]
}
```

## 9. 添加和读取模型

添加模型：

```http
POST /api/models
Content-Type: application/json
```

请求示例：

```json
{
  "provider_id": "openrouter",
  "remote_model_id": "openai/gpt-4.1-mini",
  "model_name": "GPT-4.1 Mini",
  "supports_text": true,
  "file_mime_types": ["image/jpeg", "image/png", "application/pdf"],
  "thinking_modes": ["default", "low", "medium", "high"],
  "supports_tool_calling": true,
  "supports_json_output": true,
  "context_window_tokens": 1048576,
  "max_output_tokens": 32768
}
```

获取已添加模型：

```http
GET /api/models
```

删除已添加模型：

```http
DELETE /api/models/{model_id}
```

要求：

- `provider_id` 必须已由当前账号配置。
- `remote_model_id` 来自该模型服务的远端模型列表；保存时使用前端提交的远端模型 ID 和模型名称。
- 保存模型时必须同时保存当时识别到的拆分能力字段，包括 `supports_text`、`file_mime_types`、`thinking_modes`、`supports_tool_calling`、`supports_json_output`、`context_window_tokens`、`max_output_tokens`。附件、视觉、音频和视频能力统一由 `file_mime_types` 判断。
- 若前端未提交拆分能力字段，后端先查找内置模型能力；仍未命中时使用模型服务适配器或保守默认能力并允许后续更新。接口只接受拆分能力字段。
- 内置模型能力目前覆盖 OpenRouter 的 `openai/gpt-4.1-mini`、`anthropic/claude-sonnet-4.5`，DeepSeek 的 `deepseek-chat`、`deepseek-reasoner`，以及阿里云百炼的 `qwen-plus`、`qwen-max`。
- `POST /api/models` 只负责新增或更新已添加模型，不隐式修改默认用途；当前前端在添加模型成功且 `chat` 默认模型为空时，会随后调用 `PATCH /api/model-defaults` 把该模型设置为 `chat` 默认模型。
- 删除模型时只能删除当前登录账号已添加模型；`model_id` 可包含 `/`，前端发起删除请求时必须进行 URL 编码。
- 删除模型后，若该模型被 `model_default_settings` 的任一用途引用，系统应清空对应用途或要求用户重新选择；不得保留指向已删除模型的默认用途记录。

模型响应示例：

```json
{
  "model_id": "openrouter:openai/gpt-4.1-mini",
  "provider_id": "openrouter",
  "remote_model_id": "openai/gpt-4.1-mini",
  "model_name": "GPT-4.1 Mini",
  "supports_text": true,
  "file_mime_types": ["image/jpeg", "image/png", "application/pdf"],
  "thinking_modes": ["default", "low", "medium", "high"],
  "supports_tool_calling": true,
  "supports_json_output": true,
  "context_window_tokens": 1048576,
  "max_output_tokens": 32768
}
```

## 10. 默认模型用途设置

默认模型用途是账号级设置，不写在单个模型行上。模型目录仍由 `models` 表维护；用途映射由 `model_default_settings` 维护。

获取默认模型设置：

```http
GET /api/model-defaults
```

响应示例：

```json
{
  "defaults": {
    "chat": {
      "model_id": "openrouter:openai/gpt-4.1-mini",
      "model_name": "GPT-4.1 Mini"
    },
    "title": {
      "model_id": "openrouter:openai/gpt-4.1-mini",
      "model_name": "GPT-4.1 Mini"
    },
    "vision_parse": null,
    "compact": null
  }
}
```

批量更新默认模型设置：

```http
PATCH /api/model-defaults
Content-Type: application/json
```

请求示例：

```json
{
  "chat": "openrouter:openai/gpt-4.1-mini",
  "title": "deepseek:deepseek-chat",
  "vision_parse": null,
  "compact": null
}
```

要求：

- 请求字段只允许 `chat`、`title`、`vision_parse`、`compact`。
- 字段值为 `model_id` 或 `null`；`null` 表示清空该用途。
- 非空 `model_id` 必须属于当前登录账号已添加模型，否则返回 `MODEL_NOT_FOUND`。
- `chat` 是首页对话默认模型；后端上传和真实发送以该模型为请求模型最终校验准入。当前前端首页模型弹层会刷新全部已添加模型并将 `chat` 默认模型置顶，前端推理强度随当前选中模型变化，附件按钮同时参考当前 `chat` 模型和 `vision_parse` 模型的文件能力；后端上传和发送接口仍只允许 `chat` 默认模型作为请求模型，提交其它已添加模型会返回 `INVALID_REQUEST`。
- `title` 是会话标题生成模型；未设置时回退 `chat` 模型，若 `chat` 也不可用则回退本地标题清洗规则。
- `vision_parse` 用于 `chat` 模型不能原生处理附件时的视觉解析回退：后端直接调用该模型并把附件作为原生输入发送，由 `vision_parse` 生成本轮回答。
- `compact` 在 v0.1.0 只做设置入口和数据库预留，不触发长会话压缩。
- 后端应允许 `title`、`vision_parse`、`compact` 为空；不得因它们为空阻断首页问答。
- 前端 `vision_parse` 候选列表只展示 `file_mime_types` 中包含图片 MIME 的视觉模型；当 `chat` 模型不能原生处理附件但 `vision_parse` 模型可以处理时，v0.1.0 会调用视觉解析模型直接回答。
- 默认模型只能通过 `/api/model-defaults` 按用途设置。

## 11. 配置数据存储

模型配置位于账号私有目录：

```text
{account}/config/config.db
```

`config.db` 至少包含：

### model_providers

| 字段 | 说明 |
| --- | --- |
| `provider_id` | 模型服务 ID，主键 |
| `provider_name` | 模型服务显示名 |
| `base_url` | API 地址 |
| `official_url` | 充值、控制台或 API key 管理官网地址 |
| `api_key` | 明文 API key |
| `configured` | 是否已配置 |
| `default_provider` | 是否默认 provider；当前前端列表不单独展示 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

表结构示例：

```sql
CREATE TABLE IF NOT EXISTS model_providers (
    provider_id TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    official_url TEXT,
    api_key TEXT,
    configured INTEGER NOT NULL DEFAULT 0,
    default_provider INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### models

| 字段 | 说明 |
| --- | --- |
| `model_id` | 模型 ID，建议为 `{provider_id}:{remote_model_id}` |
| `provider_id` | 所属模型服务 |
| `remote_model_id` | 远端模型 ID |
| `model_name` | 模型显示名 |
| `supports_text` | 是否支持文本对话 |
| `file_mime_types` | 支持的附件 MIME 类型，按行存储；图片、音频、视频能力由该字段判断 |
| `thinking_modes` | 支持的推理强度档位，按行存储 |
| `supports_tool_calling` | 是否支持工具调用 |
| `supports_json_output` | 是否支持 JSON 输出约束 |
| `context_window_tokens` | 上下文窗口 token 上限，可为空 |
| `max_output_tokens` | 最大输出 token 上限，可为空 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

表结构示例：

```sql
CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    remote_model_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    thinking_modes TEXT NOT NULL DEFAULT 'default',
    supports_text INTEGER NOT NULL DEFAULT 1,
    file_mime_types TEXT NOT NULL DEFAULT '',
    supports_tool_calling INTEGER NOT NULL DEFAULT 0,
    supports_json_output INTEGER NOT NULL DEFAULT 0,
    context_window_tokens INTEGER,
    max_output_tokens INTEGER,
    FOREIGN KEY (provider_id) REFERENCES model_providers(provider_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_models_provider_remote
ON models(provider_id, remote_model_id);
```

### model_default_settings

| 字段 | 说明 |
| --- | --- |
| `setting_key` | 默认模型用途，固定为 `chat`、`title`、`vision_parse`、`compact` |
| `model_id` | 已添加模型 ID，可为空 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

表结构示例：

```sql
CREATE TABLE IF NOT EXISTS model_default_settings (
    setting_key TEXT PRIMARY KEY,
    model_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (setting_key IN ('chat', 'title', 'vision_parse', 'compact')),
    FOREIGN KEY (model_id) REFERENCES models(model_id) ON DELETE SET NULL
);
```

数据库设计原则：

- `models` 表只维护当前账号已添加模型及模型能力。
- `model_default_settings` 表维护用途到模型的映射，避免以后新增用途时继续给 `models` 表扩布尔列。
- 默认模型用途必须显式写入 `model_default_settings`；没有 `chat` 记录时，首页对话视为未配置默认聊天模型。

## 12. 前端安全要求

- 密码和 API key 输入框可使用显示/隐藏切换，但只改变输入控件可见性。
- 已保存 API key 可在当前账号的设置表单中明文回显并编辑。
- 测试连接不应把临时 API key 写入前端本地持久化存储或账号配置库。
- 账号设置页 `/setting` 使用患者主工作台外壳，不清除有效登录态和用户摘要。

## 13. 当前前端状态口径

- 设置页不提供独立的全页加载中占位；模型提供方配置加载失败时在服务列表展示错误消息。
- 当前前端密码修改没有单独的提交中禁用防重复状态；提交成功后清空当前密码、新密码和确认新密码三个输入框，并展示后端返回消息。
- 连接测试按钮在 `testing` 状态禁用重复点击；成功或失败反馈通过连接测试图标按钮的状态和提示展示，并在短时间后复位。
- 设置页一级导航包含 `账号资料`、`密码安全`、`模型提供方`、`默认模型` 和 `退出登录`。
- 设置页提供 `默认模型` 一级入口，可分别维护 `chat`、`title`、`vision_parse` 和 `compact`；`vision_parse` 和 `compact` 在 v0.1.0 只做设置入口、接口和数据库预留。
- 添加模型成功后，如果当前账号没有 `chat` 默认模型，前端会自动把新增模型写入 `chat` 用途；已有 `chat` 默认模型时，新增模型不自动切换默认用途。
