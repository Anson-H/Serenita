# Serenita 本地文件存储结构

> 文档状态：技术参考 / 存储结构参考
> 当前用途：定义本地文件系统与账号私有目录组织方式，供 `v0.1.0` 会话/收藏与 `v0.2.0` 报告存储落地时参考
> 版本标注：各目录标注所属版本；未标注的为 v0.1.0 当前实现或稳定参考。实际是否创建取决于代码路径是否触发对应功能。
> 当前执行版本：`v0.1.0`。本文档只做存储结构补充说明，不单独扩展当前版本范围。

## serenita_files 文件存储结构

采用本地文件系统，参照微信 `xwechat_files` 的目录组织方式：公共目录 `all_users/` + 每个账号独立目录。经本机查看，微信目录形态类似 `xwechat_files/all_users/` 与 `xwechat_files/{wxid}/config`、`db_storage`、`resource` 等账号私有目录并存；Serenita 按同样原则区分全局公共配置和账号私有数据。

代码中的数据根目录由 `backend/app/storage/paths.py` 决定：优先使用环境变量 `SERENITA_DATA_ROOT`；未配置时落到仓库根目录下的 `serenita_files/`。本文用 `serenita_files/` 表示逻辑根目录，部署或测试环境可通过环境变量把同一结构映射到其它绝对路径。

---

## 根目录 all_users/

公共目录，存放所有账号共享的全局数据。

---

### config/ — 配置文件夹（预留）

存放 Serenita 应用的全局配置数据。当前代码中的内置模型服务模板直接由 `backend/app/bootstrap.py` 注册，尚未落地到 `all_users/config/`：

- app_config + app_config.crc — 应用配置及其 CRC 校验文件预留位。可包含服务端地址、内置模型服务清单、官网地址模板、API 地址模板、功能开关等全局设置项；不保存任何账号的 API key、已添加模型或默认模型。
- sqlite/lock.ini (0 字节) — 应用层互斥锁文件预留位，用于需要额外串行化配置写入时落盘；不承载业务数据，也不是 SQLite WAL 的一部分。

`app_config` 中模型服务模板至少包含：

- `provider_templates[]` — 内置模型服务模板，包含 `provider_id`、`provider_name`、`default_official_url`、`default_base_url`。

v0.1.0 支持的 `provider_id` 包含 `openrouter`、`deepseek`、`aliyun_bailian`。

---

### auth/ — 注册、登录与退出登录凭证

存放所有账号共用的 auth 凭证库和各账号的会话信息。

- `auth_info.db` — 所有账号共用的 auth 凭证库，包含 `auth_accounts` 和 `auth_sessions`：
  - `auth_accounts` — 账号凭证（account, password_hash, user_name, created_at, updated_at）
  - `auth_sessions` — 登录态索引（session_token_hash, account, user_name, expires_at, revoked_at, created_at, updated_at）
- `auth_info.db-shm / auth_info.db-wal` — SQLite 的 WAL 模式附属文件（共享内存和预写日志），仅在启用 WAL 后可能出现。
- `{account}/` — 以账号标识命名的子文件夹：
  - session.json — 当前登录态摘要，至少包含 `account`、`user_name`、`session_token_hash`、`authenticated`、`expires_at`、`last_login_at`。不得保存明文 `session_token`；当前代码在登录和用户名称变更时写入，退出登录不会依赖或清空该文件，而是以 `auth_sessions.revoked_at` 为权威状态。

注册成功时必须在 `auth_info.db` 中写入凭证记录，并创建对应 `{account}/` 子目录和账号私有目录 `{account}/`；重复注册同一账号不得覆盖已有目录或凭证。密码不得明文保存。`session_token` 有效期约为 183 天，权威索引为 `auth_info.db` 中的 token 哈希记录。

账号设置页可修改 `user_name` 和密码。`user_name` 更新时同步更新 `auth_accounts.updated_at`、未撤销会话的 `auth_sessions.user_name`、当前会话摘要和前端用户摘要；密码更新时必须先校验当前密码，再重写 `password_hash`，并撤销同账号下除当前会话外的其它有效 session。`account` 作为登录主键和账号私有目录名，在账号生命周期内保持固定。

认证存储包含旧结构迁移逻辑：认证初始化时（如登录、注册或 session 校验）若发现旧版 `all_users/login/key_info.db` 且新版 `all_users/auth/auth_info.db` 尚不存在，代码会移动主库及 `-shm`、`-wal` 附属文件到 `auth/`；旧版 `all_users/login/{account}/` 子目录会迁移到 `all_users/auth/{account}/`；旧表名 `login_accounts` 会重命名为 `auth_accounts`。迁移完成后，当前实现以 `auth/` 目录为准。

`auth_info.db` 表结构示例：

```sql
CREATE TABLE IF NOT EXISTS auth_accounts (
    account TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    user_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_token_hash TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    user_name TEXT,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (account) REFERENCES auth_accounts(account)
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_account
ON auth_sessions(account);
```

---

### lab_dict/ — 指标字典（v0.2.0+）

存放指标和分类数据，供离线或快速查询使用：

- lab_dict.db — 指标字典库，包含以下表：
  - lab_item — 指标字典（item_id, item_cn, aliases, description, status）
  - lab_category — 分类字典（category_id, parent_id, level, description, status）
  - lab_item_category — 指标-分类关联（item_id, category_id, relevance）
- lab_dict.db-shm / lab_dict.db-wal — SQLite WAL 模式附属文件，仅在启用 WAL 后可能出现。

`lab_dict.db` 表结构示例：

```sql
CREATE TABLE IF NOT EXISTS lab_item (
    item_id TEXT PRIMARY KEY,
    item_cn TEXT NOT NULL,
    aliases TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'verified'
);

CREATE TABLE IF NOT EXISTS lab_category (
    category_id TEXT PRIMARY KEY,
    parent_id TEXT,
    level INTEGER,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'verified',
    FOREIGN KEY (parent_id) REFERENCES lab_category(category_id)
);

CREATE TABLE IF NOT EXISTS lab_item_category (
    item_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    relevance INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (item_id, category_id),
    FOREIGN KEY (item_id) REFERENCES lab_item(item_id),
    FOREIGN KEY (category_id) REFERENCES lab_category(category_id)
);
```

---

### sqlite/ — 全局 SQLite 锁

- lock.ini (0 字节) — 顶层应用层互斥锁文件预留位。仅在需要跨库、跨目录或跨进程做额外串行化保护时使用；不承载业务数据，也不替代 SQLite 自身的锁与 WAL 机制。若实现未使用额外文件锁，本文件可不存在。

---

## 账号私有目录 {account}/

每个登录账号拥有独立目录，以 `account` 命名，例如 `demo_patient`。

`account` 在注册和登录时会先去除首尾空白并转为小写，再通过 `^[A-Za-z0-9_-]{1,20}$` 校验；因此账号私有目录名实际只应出现小写字母、数字、下划线和短横线。`user_name` 只是展示名，不参与目录命名。

当前 v0.1.0 在注册或登录成功后会确保以下目录存在：`all_users/auth/{account}/`、`{account}/config/`、`{account}/conversations/db_storage/`、`{account}/conversations/sessions/`、`{account}/conversations/attachments/`、`{account}/favorites/db_storage/`。`reports/`、`exports/` 和其它后续版本目录不会在 v0.1.0 主流程中主动创建。

---

### config/ — 账号配置

存放当前账号私有配置。不同账号不能共享模型 API key、已添加模型和默认模型。模型服务配置和对应 API key 放在同一张模型服务表中；已添加模型单独成表。

- `config.db` — 当前账号的模型配置库，包含模型服务配置摘要、已添加模型、默认模型、能力摘要，以及模型服务 API key。API key 必须绑定当前 `account`；不得放入 `all_users/config/`，不得被其它账号读取或复用。
- `config.db-shm / config.db-wal` — SQLite WAL 模式附属文件，仅在启用 WAL 后可能出现。

`config.db` 至少包含：

- `model_providers` — 当前账号的模型服务配置和 API key，包含 `provider_id`、`provider_name`、`base_url`、`official_url`、`api_key`、`configured`、`default_provider`、`created_at`、`updated_at`。
- `models` — 当前账号已添加模型，包含 `model_id`、`provider_id`、`remote_model_id`、`model_name`、`created_at`、`updated_at`、`thinking_modes`、`supports_text`、`file_mime_types`、`supports_tool_calling`、`supports_json_output`、`context_window_tokens`、`max_output_tokens`。附件、视觉、音频和视频能力统一由 `file_mime_types` 表达。
- `model_default_settings` — 当前账号按用途保存的默认模型，`setting_key` 仅允许 `chat`、`title`、`vision_parse`、`compact`。

`model_providers.default_provider` 只表示模型服务列表中的默认服务标记，不等同于聊天、标题、视觉解析或压缩上下文的默认模型；模型用途默认值统一保存在 `model_default_settings`。

官网地址、API 地址和 API key 输入后自动保存到 `model_providers`；API key 为空时仍可保存 `official_url` 和 `base_url`，但 `configured` 为 false。连接测试使用账号设置表单中的临时 `base_url` 和 `api_key` 发起，测试动作本身不额外持久化配置。添加模型弹窗获取远端模型列表时，使用当前账号已保存的 `base_url` 和 `api_key`，由后端请求远端 `GET {base_url}/models`，不在本地维护假模型列表；弹窗按厂商返回顺序展示远端模型。远端模型列表接口先由后端 provider adapter 把厂商元数据归一化为拆分能力字段；前端选择模型后把这些字段随 `POST /api/models` 提交，后端校验 provider 已配置，并把选中模型与能力字段写入 `models` 表。内置模型可用后端内置能力档案兜底。

`model_providers.api_key` 保存当前账号该模型服务的明文 API key。旧版模型服务配置若包含 `key_info_data`，模型配置 API 初始化配置库时会把旧密文解封后写入 `api_key`，并清空 `account_md5`、`key_md5`、`key_info_md5`、`key_info_data` 等旧字段；对话生成读取配置时也兼容旧 `key_info_data`。旧版 `models.capabilities_json` 和 `supports_vision` 会迁移为当前拆分能力列，旧版 `model_default_settings` 若缺少当前外键或字段会被重建。`models.default_model` 不再属于当前 schema，默认模型统一以 `model_default_settings` 为准。`thinking_modes` 和 `file_mime_types` 在 SQLite 中以换行分隔字符串保存，接口响应时再转回数组。

`config.db` 表结构示例：

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

CREATE TABLE IF NOT EXISTS model_default_settings (
    setting_key TEXT PRIMARY KEY,
    model_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (setting_key IN ('chat', 'title', 'vision_parse', 'compact')),
    FOREIGN KEY (model_id) REFERENCES models(model_id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_models_provider_remote
ON models(provider_id, remote_model_id);
```

---

### conversations/ — 对话历史

存放账号与 AI 的所有会话记录。会话数据采用“两层结构”：

- 会话时间线 JSONL 是对话内容可信源，负责保存单个会话内的消息、文件上传、思考过程和少量稳定扩展记录。
- 会话索引库 `conversations/db_storage/sessions.db` 是会话生命周期入口，负责历史列表、会话存在性、当前活动路径和时间线文件定位。

删除某个会话时，必须同时删除：

- `conversation_sessions` 中该会话的索引记录
- `conversation_turns` 和 `conversation_resources` 中该会话的关联记录
- `timeline_path` 对应的会话 JSONL 文件
- `conversations/attachments/{session_id}/` 附件目录

若发现某个时间线 JSONL 对应的 `session_id` 已不存在于会话索引库，应视为待清理的孤儿文件。当前代码没有独立的孤儿文件扫描任务；历史列表以 `sessions.db` 为入口，因此这类 JSONL 不会展示，后续若增加清理流程应删除它们。

所有链路 ID 当前由 `uuid.uuid4()` 生成，包括 `session_id`、`turn_id`、`message_id`、`parent_message_id`、`resource_id`、`favorite_id`。业务时间以显式 ISO 8601 时间字段为准。

会话相关路径如下：

- `db_storage/sessions.db` — 会话索引库。
- `sessions/{session_id}.jsonl` — 会话时间线日志。
- `attachments/{session_id}/{resource_id}.{ext}` — 附件原始文件。
- `attachments/{session_id}/{resource_id}_thumb.{ext}` — 附件缩略图或预览图。

上传接口会先把原始文件写入 `attachments/` 并在 `conversation_resources` 登记资源。当前单文件上限为 20MB；上传成功后的 `usage_status` 初始为 `pending`，`expires_at` 为当前时间后约 24 小时。只有用户真正发送消息并引用该资源时，后端才会把对应 `file_upload` 记录追加进会话 JSONL，并把 `usage_status` 更新为 `attached`；若发送前资源过期，校验时会标记为 `expired` 并拒绝使用。代码也保留 `deleted` 作为不可用资源状态判断，但当前没有单独的资源删除接口。

当前上传资源的 `source` 固定为 `user_upload`，`status` 固定为 `uploaded`；资源可信文件名、MIME、大小、哈希和相对路径均以后端写入的 `conversation_resources` 记录为准。

#### db_storage/ — 会话索引库

`sessions.db` 使用 SQLite 存储会话索引。它是打开历史会话列表的优先读取对象，也记录每个会话时间线文件的位置。

- `sessions.db-shm / sessions.db-wal` — SQLite WAL 模式附属文件（共享内存和预写日志）。仅在启用 WAL 且数据库发生读写后出现；属于运行时附属文件，不承载独立业务语义。

`conversation_sessions` 至少包含：

- `session_id`
- `account`
- `title`
- `timeline_path`
- `created_at`
- `last_active_at`
- `last_message_preview`
- `active_path_message_ids`

`active_path_message_ids` 用于记录当前界面选中的消息路径；它只记录界面选择，不改变消息树本身。当前代码的会话列表只展示该字段非空的会话，因此仅上传文件但尚未发送消息的草稿会话会保留空数组，可通过详情接口读取但不出现在最近会话列表。

`conversation_turns.status` 当前主流程从 `streaming` 进入 `completed`、`failed` 或 `cancelled`；`queued` 只作为待处理轮次判断的兼容/预留状态。当前 `stream_id` 使用 `stream_{turn_id}` 生成，并保存在 `conversation_turns.stream_id` 中供 SSE 订阅定位。

`sessions.db` 表结构示例：

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

#### sessions/ — 会话时间线日志

每个 `session_id` 对应一个会话时间线文件；一个用户提交到助手完成的过程对应一个 `turn_id`。每行 JSONL 都是一条可追加、可审计、可恢复的稳定记录。
时间线文件直接保存在 `sessions/` 下；业务时间以 JSONL 行内 `timestamp` 和数据库时间字段为准。

旧版若存在 `conversations/sessions/{date}/{session_id}.jsonl` 这类带日期子目录的 `timeline_path`，当前 `ConversationRepository.init_db()` 会把它迁移为扁平的 `conversations/sessions/{session_id}.jsonl`，并在可能时清理空日期目录；迁移后以 `conversation_sessions.timeline_path` 中的新路径为准。

单行外层字段至少包含：

- `timestamp` — 记录写入时间，使用 ISO 8601 字符串。
- `type` — 顶层记录类型。
- `payload` — 具体记录内容。

本期需落地或预留的顶层行类型：

- `file_upload` — 随消息实际使用的文件上传记录，记录 `resource_id`、文件名、类型、大小、相对路径、缩略图、哈希和资源处理状态；仅上传但尚未发送的草稿资源不会立即写入 JSONL。
- `user_message` — 用户消息，记录文本（字符串格式）、推理强度、期望模型和本轮使用的上下文资源引用。
- `thinking_process` — 模型显式返回且允许展示的思考过程或思考摘要，记录 `message_id`、`parent_message_id`、`duration_ms`，并按 `turn_id` 关联到本轮。
- `assistant_message` — 助手最终回复，记录最终回答、模型、状态、用量和停止原因；存在思考过程时 `parent_message_id` 指向 `thinking_process.message_id`，否则指向本轮用户消息。
- `turn_cancelled` — 用户取消生成记录，记录 `turn_id`、`stream_id`、`preserve_partial` 以及取消后是否写入助手/思考消息。
- `tool_call` / `tool_result` — 工具调用及结果，本期可预留。
- `hook_result` — Hook 执行结果，本期可预留。
- `compacted` — 长会话压缩摘要，本期可预留，不要求前端暴露。

其中 `assistant_message.status` 表示已落盘助手消息的终态，当前主要为 `completed` 或 `cancelled`；`streaming` 属于本轮生成过程状态，只用于接口响应或流式事件，不写入最终 `assistant_message`。普通取消生成会把已展示的半截回答写成 `status=cancelled`、`stop_reason=cancelled` 的正式 `assistant_message`；生成中点击重新生成时，取消请求使用 `preserve_partial=false`，只写 `turn_cancelled`，不写半截助手消息。模型调用失败当前记录在 `conversation_turns.status=failed`、`error_code`、`error_message` 和 `failed` SSE 事件中，不额外追加失败态 `assistant_message`。`assistant_message.stop_reason` 当前不做强枚举归一化：provider 返回 `finish_reason` 时按原值落盘，例如 OpenAI 兼容接口常见的 `stop`；未返回时使用 `end_turn` 兜底，取消时固定为 `cancelled`。

消息链路字段在 `payload` 中保存：

- `message_id` — 用户消息、思考过程或助手消息的唯一标识。
- `parent_message_id` — 父消息 ID；根用户消息为 `null`。
- `session_id` — 会话 ID，同一会话内所有事件一致。
- `turn_id` — 一轮用户提交到助手完成的过程 ID。

分支规则：

- 编辑历史用户提问时，不覆盖原用户消息，也不删除原助手回答。
- 新提问使用新的 `turn_id` 和新的消息节点。
- 新提问的 `parent_message_id` 指向被编辑消息原本的父消息，使新旧提问成为同一父消息下的并列子消息。
- 重新生成助手回答时，新回答的 `parent_message_id` 指向同一用户消息，原回答保留。
- 普通取消生成保留的 `cancelled` 助手消息参与消息链路；重新生成触发的取消不产生助手分支。
- 当同一个 `parent_message_id` 下存在多个子消息时，该位置自然形成分支；这些子消息优先级相同，展示哪条路径由界面选择决定。
- 当前展示哪条路径由 `conversation_sessions.active_path_message_ids` 决定；该字段通常包含当前路径上的用户消息、思考过程和助手回答。

完整字段含义和消息示例见 `docs/releases/v0.1.0/technical/home-conversation.md` 的会话数据章节。

#### attachments/ — 会话附件与上下文资源

会话中上传、生成或引用的非文本资源按会话组织。时间线 JSONL 中的 `file_upload` 记录保存相对路径和元数据，不直接写入二进制内容：

- `{session_id}/{resource_id}.{ext}` — 原始文件。上传入口基础 allowlist 包含图片、PDF、部分音频/视频和旧版 Office 文档/表格 MIME；实际是否可上传和发送还必须通过 `chat` 模型、`vision_parse` 模型与 provider adapter 原生附件能力校验。前端会根据所选 `chat` 模型与 `vision_parse` 模型的合并 `file_mime_types` 控制附件入口和过滤待发送资源，但可信校验以后端为准。Office MIME 仅保留迁移兼容白名单，当前 v0.1.0 provider adapter 不原生转发 Office 文档，因此不会作为可用附件能力开放。
- `{session_id}/{resource_id}_thumb.{ext}` — 缩略图或预览图（如有）。

`conversation_resources` 记录上传资源的可信元数据；`file_upload` 记录该资源已经被某条消息实际引用。`user_message.context_resources` 记录本轮实际引用了哪些上下文资源。`context_resources[].resource_type` 为 `file` 时，`resource_id` 先对应 `conversation_resources.resource_id`，消息发送后也会对应同一资源的 `file_upload.payload.resource_id`；为 `message_quote` 时，`resource_id` 对应被引用消息的 `message_id`，并通过 `quote_text` 保存选中文字。v0.2.0 新增消息级 `report` 资源，`resource_id` 对应当前账号的 `reports.report_id`。只有对话中实际读取、修改、确认写入或分析的报告才随消息落盘，并出现在聊天末尾索引中；后台分析临时读取的报告不形成会话引用。会话索引表不增加报告专用字段。

### reports/ — 报告文件与分析结果（v0.2.0+）

存放账号上传的报告原始文件及对应的智能分析结果。一个源文件可拆分为多条报告记录，`report_id` 前缀标识类型（`LAB-` / `EXAM-` / `PATH-` / `SURG-` / `OTHER-`）。

当前 v0.1.0 只有无账号数据读取的 `GET /api/reports` 占位接口返回空列表，不创建或读取本节的 `reports.db` 与报告附件目录。

#### db_storage/

- reports.db — 报告主库，包含以下表：
  - reports — 报告元数据（report_id, account, report_type, report_name, report_time, analysis_sections, analysis_outdated, storage_status, content_fingerprint, duplicate_group_key）
  - uploaded_source_files — 上传原始文件（file_id, account, file_path, mime_type, sha256, source_kind）
  - report_source_links — 报告与源文件关联（report_id, file_id, account, is_primary）
  - lab_test_report — 检验报告（report_id, account, collected_at, category_id, item_id, result_text, reference_text, flag_text）
  - examination_report — 检查报告（report_id, account, collected_at, exam_name, clinical_diagnosis, exam_method, exam_findings, exam_diagnosis）
  - pathology_report — 病理报告（report_id, account, submitted_specimen, gross_examination, diagnosis, sampling_location）
  - surgery_report — 手术报告（report_id, account, preoperative_diagnosis, intraoperative_diagnosis, anesthesia_method, started_at, ended_at, blood_transfusion, intraoperative_blood_loss, intraoperative_urine_output, intraoperative_transfusion, intraoperative_infusion, intraoperative_other_drugs, procedure_description, postoperative_vital_signs）
  - other_report — 其它报告原文（report_id, account, report_body）
- reports.db-shm / reports.db-wal — SQLite WAL 模式附属文件（共享内存和预写日志）。仅在启用 WAL 且数据库发生读写后出现。

`reports.db` 表结构示例：

```sql
CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    report_type TEXT NOT NULL CHECK (report_type IN ('检验报告', '检查报告', '病理报告', '手术报告', '其它报告')),
    report_name TEXT NOT NULL,
    report_time TEXT NOT NULL,
    analysis_sections TEXT DEFAULT '{}',
    analysis_outdated INTEGER NOT NULL DEFAULT 0,
    analysis_updated_at TEXT,
    storage_status TEXT NOT NULL DEFAULT 'uploaded',
    content_fingerprint TEXT,
    duplicate_group_key TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS uploaded_source_files (
    file_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'unknown'
        CHECK (source_kind IN ('screenshot', 'scan', 'pdf', 'photo', 'unknown')),
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uk_uploaded_source_file_hash
ON uploaded_source_files(account, sha256);

CREATE TABLE IF NOT EXISTS report_source_links (
    report_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    account TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (report_id, file_id),
    FOREIGN KEY (report_id) REFERENCES reports(report_id),
    FOREIGN KEY (file_id) REFERENCES uploaded_source_files(file_id)
);

CREATE INDEX IF NOT EXISTS idx_report_source_link_file
ON report_source_links(account, file_id);

CREATE INDEX IF NOT EXISTS idx_report_source_link_report
ON report_source_links(account, report_id);

CREATE TABLE IF NOT EXISTS lab_test_report (
    report_id TEXT NOT NULL,
    account TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    category_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    result_text TEXT NOT NULL,
    reference_text TEXT,
    flag_text TEXT CHECK (flag_text IN ('↑', '↓')),
    PRIMARY KEY (report_id, item_id),
    FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE INDEX IF NOT EXISTS idx_ltr_account_item_time
ON lab_test_report(account, item_id, collected_at);

CREATE TABLE IF NOT EXISTS examination_report (
    report_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    exam_name TEXT NOT NULL,
    clinical_diagnosis TEXT,
    exam_method TEXT,
    exam_findings TEXT,
    exam_diagnosis TEXT,
    FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uk_exam_account_time_name
ON examination_report(account, collected_at, exam_name);

CREATE INDEX IF NOT EXISTS idx_exam_account_time
ON examination_report(account, exam_name, collected_at);

CREATE TABLE IF NOT EXISTS pathology_report (
    report_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    submitted_specimen TEXT,
    gross_examination TEXT,
    diagnosis TEXT,
    sampling_location TEXT,
    FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE INDEX IF NOT EXISTS idx_pathology_account
ON pathology_report(account, report_id);

CREATE TABLE IF NOT EXISTS surgery_report (
    report_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    preoperative_diagnosis TEXT,
    intraoperative_diagnosis TEXT,
    anesthesia_method TEXT,
    started_at TEXT,
    ended_at TEXT,
    blood_transfusion TEXT,
    intraoperative_blood_loss TEXT,
    intraoperative_urine_output TEXT,
    intraoperative_transfusion TEXT,
    intraoperative_infusion TEXT,
    intraoperative_other_drugs TEXT,
    procedure_description TEXT,
    postoperative_vital_signs TEXT,
    FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE INDEX IF NOT EXISTS idx_surgery_account_time
ON surgery_report(account, started_at, ended_at);

CREATE TABLE IF NOT EXISTS other_report (
    report_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    report_body TEXT NOT NULL,
    FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE INDEX IF NOT EXISTS idx_other_account
ON other_report(account, report_id);
```

检验报告的 `result_text` 保存结果及单位原文，`reference_text` 保存参考值原文。视觉解析模型在解析阶段结合两段原文和报告上下文生成 `flag_text`：异常或偏高为 `↑`，偏低为 `↓`，无异常或无法判断为空。`flag_text` 只允许这两个箭头或空值。数据库不保存拆分后的数值、单位、参考上下限、结果类型或可比状态。

#### attachments/

- `{file_id}.{pdf|jpg|png|heic}` — 报告原始文件，以源文件 `file_id` 命名，保留原始扩展名；一份报告可关联多个源文件。

---

### favorites/ — 收藏

存放账号收藏的内容快照。

#### db_storage/

- `favorites.db` — 收藏主库。
- `favorites.db-shm / favorites.db-wal` — SQLite WAL 模式附属文件（共享内存和预写日志）。仅在启用 WAL 且数据库发生读写后出现。
- 表名使用 `favorites`，至少包含以下字段：
  - `favorite_id`
  - `account`
  - `source_type`
  - `source_session_id`
  - `source_id`
  - `title`
  - `content_summary`
  - `content_snapshot`
  - `tags`
  - `created_at`
  - `updated_at`

约束要求：

- 同一账号下 `source_type + source_session_id + source_id` 具备去重能力，避免重复收藏同一内容。
- `source_type` 不在数据库层做硬约束（无 CHECK 限制），由应用层控制合法值。
- `v0.1.0` 落地 `message`（AI 回答）。
- `v0.2.0` 新增 `report_analysis`（报告分析结果）和 `report_qa`（报告问答回答）。
- 收藏快照不随原对话或原报告删除自动删除；若返回原内容时发现来源不存在，应仅展示收藏快照。

`favorites.db` 表结构示例：

```sql
CREATE TABLE IF NOT EXISTS favorites (
    favorite_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content_snapshot TEXT NOT NULL,
    content_summary TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account, source_type, source_session_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_account_time
ON favorites(account, created_at);
```

#### attachments/ — 预留

当前收藏只保存文本快照，不单独维护收藏附件目录。若后续支持收藏图片、PDF 片段等富媒体内容，再补充对应附件结构。

---

### exports/ — 用户导出文件（v0.2.0+ 预留）

预留目录，用于存放用户导出的报告摘要、趋势图等文件。

---

## 运行时附属文件说明

以下文件属于运行时附属文件，不应和主业务数据文件混为一类：

- `*.db-wal` / `*.db-shm` — SQLite 在 WAL 模式下生成的附属文件。当前 `backend/app/storage/sqlite.py` 只启用 `PRAGMA foreign_keys = ON`，不主动执行 `PRAGMA journal_mode=WAL`；因此正常代码路径不要求这些文件出现。若测试、部署或后续实现启用 WAL，它们依赖对应主库文件存在，可能在数据库首次读写前不存在，也可能在 checkpoint、关闭连接或清理后消失或被重建。
- `lock.ini` — 应用层额外互斥锁文件预留位，不属于 SQLite 标准组成部分。是否实际创建，取决于实现是否需要在 SQLite 自身锁之外再增加一层跨进程或跨目录串行化控制。

文档中的目录结构优先描述“稳定主数据文件应该放在哪里”；WAL 附属文件和锁文件属于实现运行时可能出现的伴生文件，验收时应与主数据文件区分看待。
