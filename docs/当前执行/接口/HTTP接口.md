# HTTP API 契约

> 文档层级：当前执行 / 接口契约
>
> 负责：浏览器与后端之间的当前 HTTP 路由、方法和高层请求语义。
>
> 不负责：领域内部工具参数结构、数据库表、页面布局、事件信封或供应商 wire 协议。
>
> 上位文档：[技术架构总览](../架构/技术架构总览.md)；领域语义见[成员](../领域/成员与健康档案授权.md)、[医疗报告](../领域/医疗报告.md)和[公网研究](../领域/公网研究.md)。

接口均使用同源 HttpOnly Cookie 认证。报告接口统一将 `member_id` 写入路径以确定成员作用域。表格是当前路由总表，具体授权、事务和展示行为由相应领域与前端契约定义。

## 请求身份与错误

所有已认证的写请求携带 `X-Serenita-Account-ID`，值为发起请求时的 `account_id`。后端以 Cookie 认证身份为准，再比较该标识；缺少标识返回 `422 REQUEST_VALIDATION_FAILED`，不一致返回 `409 ACCOUNT_CONTEXT_CHANGED`，均在业务执行前拒绝。退出也检查预期账号；已经失效的会话可以幂等退出。

错误响应统一为 `detail: { code, message, details? }`。请求字段错误使用 `REQUEST_VALIDATION_FAILED`，`details` 只包含字段位置、错误类型和消息，不回传密码、密钥或其它输入原值。领域错误使用与 HTTP 无关的类别；HTTP 适配层映射状态码，工具适配层将失败交回行动循环。

## 会话与附件



| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/conversations/attachment-capabilities` | 读取当前账号所选模型可接收的会话附件类型 |
| `POST` | `/api/conversations/context-resources` | 上传 pending 会话附件 |
| `GET` | `/api/conversations/{session_id}/context-resources/{resource_id}` | 在当前账号与会话权限内预览附件 |
| `POST` | `/api/conversations/messages` | 提交新消息；空闲会话启动轮次，活动会话写入等候队列 |
| `PATCH` | `/api/conversations/{session_id}/queued-inputs/order` | 提交当前完整等候输入顺序 |
| `DELETE` | `/api/conversations/{session_id}/queued-inputs/{input_id}` | 删除一条尚未提升的等候输入 |
| `POST` | `/api/conversations/{session_id}/queued-inputs/{input_id}/restore-to-draft` | 原样取回一条等候输入并移出队列 |
| `POST` | `/api/conversations/{session_id}/queued-inputs/{input_id}/run-now` | 调整方向并立即提升目标输入 |
| `POST` | `/api/conversations/{session_id}/fork` | 从稳定轮次边界创建独立子会话 |
| `POST` | `/api/conversations/{session_id}/messages/{message_id}/edit` | 编辑最新已结束轮次的用户问题并追加替代轮次 |
| `POST` | `/api/conversations/{session_id}/messages/{message_id}/regenerate` | 重新生成最新已结束轮次并追加替代轮次 |
| `GET` | `/api/conversations/{session_id}/streams/{stream_id}` | 在会话作用域内重放并跟随持久化执行记录 |
| `POST` | `/api/conversations/{session_id}/turns/{turn_id}/cancel` | 取消当前账号的开放轮次，可选择保留已生成的部分正文 |
| `GET` | `/api/conversations/{session_id}/turns/{turn_id}` | 读取单个轮次的持久化状态与记录 |
| `GET` | `/api/conversations` | 读取当前账号会话列表 |
| `PATCH` | `/api/conversations/{session_id}` | 原子更新手工标题和/或置顶状态并返回会话摘要 |
| `POST` | `/api/conversations/batch-pin` | 在一个事务内统一设置非空去重会话集合的置顶状态 |
| `POST` | `/api/conversations/batch-delete` | 复用单条删除语义并返回已删除 ID 与逐项真实失败 |
| `GET` | `/api/conversations/{session_id}` | 读取当前线性投影、pending 轮次与资源状态 |
| `DELETE` | `/api/conversations/{session_id}` | 删除当前会话；不级联删除独立子会话 |

报告上传、开始解读和重新解读复用这些接口。会话详情的账号作用域由认证 Cookie、账号私有数据库路径与事件 header 共同确定，响应主体聚焦会话投影和业务资源。

附件能力接口接受可选 `model_id`，省略时使用当前聊天默认模型，返回 `{model_id, file_mime_types}`；未配置默认模型时返回 `model_id=null` 和空列表，指定模型不存在时返回 `MODEL_NOT_FOUND`。列表同时考虑模型能力、Provider 原生附件支持和视觉解析能力，与上传及发送共享后端检查。查询结果不代替后续请求的实时校验。

附件上传不接收上传标识，也不提供上传任务或状态查询接口。成功响应保留 `resource_id`、`original_filename`、`mime_type`、`size_bytes`、`relative_path`、`sha256`、`storage_status=ready`、`lifecycle_status=pending` 和 `expires_at`。`original_filename` 是安全规范化后的原始显示文件名；`resource_id` 是会话目录中的实际存储文件名，同名上传以 `-002`、`-003` 递增，前端放入预览 URL 时必须对其整体执行百分号编码。响应与 `resource/attached` 事件均不含 `source`；事件也不保存 `storage_status`、`lifecycle_status` 或 `expires_at`。

上传进度只存在于当前浏览器内存。网络错误、HTTP 错误或无效成功响应都结束并移除该进度项，用户通过重新选择文件再次上传。客户端不区分服务端未处理与服务端已经成功但响应丢失；后一种资源保持不可见的 `ready + pending`，按 24 小时过期规则清理。

`context_resources` 请求只提交资源类型、资源 ID 及必要的成员 ID 或注释定位字段，不接受展示名、报告名或文件名快照。轮次开始时，后端通过报告插件按 `report_id` 重新读取当前医疗报告，并在同一条 Provider 用户消息中附加 `ATTACHED EXISTING CONTENT` 文本块。该文本块进入实际发送且持久化的 `provider_payload`：`report` 保存完整报告事实，不含 `analysis_content`；若存在既有解读结果，则另以 `existing_ai_analysis` 保存正文、更新时间和过期状态。

## 报告读取与页面命令

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/api/members/{member_id}/reports` | 页面手工创建一份五类结构化报告 |
| `GET` | `/api/members/{member_id}/reports` | 报告列表读取；可用 `report_type` 筛选，按日期降序分组 |
| `GET` | `/api/members/{member_id}/reports/{report_id}` | 报告详情、结构化字段、来源和解读结果 |
| `GET` | `/api/members/{member_id}/reports/{report_id}/conversation-input-preview` | 返回账号安全的 `ATTACHED EXISTING CONTENT` 描述；原始 `report` 与可选 `existing_ai_analysis` 分字段保存 |
| `PATCH` | `/api/members/{member_id}/reports/{report_id}/fields` | 页面字段或解读结果正文编辑 |
| `POST` | `/api/members/{member_id}/reports/{report_id}/lab-items` | 页面新增一条检验指标记录 |
| `DELETE` | `/api/members/{member_id}/reports/{report_id}/lab-items/{item_id}` | 页面删除一条非最后的检验指标记录 |
| `DELETE` | `/api/members/{member_id}/reports/{report_id}` | 页面删除 |
| `POST` | `/api/members/{member_id}/reports/{report_id}/source-files` | 为既有医疗报告补充一份或多份原件 |
| `GET` | `/api/members/{member_id}/reports/{report_id}/source-files/{resource_id}` | 下载有权限的来源文件 |
| `GET` | `/api/members/{member_id}/reports/{report_id}/source-files/{resource_id}/thumbnail` | 获取来源缩略图 |

补充原件使用 `multipart/form-data`，同名 `files` 字段可提交 1 至 20 份 PDF、JPG、PNG 或 HEIC 文件；单文件不超过 20MB，单次总大小不超过 100MB。该页面命令直接关联当前医疗报告，不解析或修改报告事实，不创建会话。目标没有既有来源时，第一份新增原件成为主来源；已有主来源时保持不变。相同内容已经关联到目标报告，或同次选择包含相同内容时，返回 `REPORT_SOURCE_DUPLICATE`，不产生部分写入。

字段更新请求：

```json
{
  "field": "report_name",
  "value": "腹部超声报告"
}
```

`field` 必须属于当前允许字段；检验指标字段需要 `item_id`。

## 模型 Provider、能力与默认用途

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/model-providers` | 读取内置 Provider、账号配置状态与 Provider 原生附件上限 |
| `POST` | `/api/model-providers` | 保存 Provider 地址、官网和密封凭证 |
| `PATCH` | `/api/model-providers/{provider_id}` | 更新已配置 Provider |
| `POST` | `/api/model-providers/{provider_id}/credential/reveal` | 主动读取当前账号已保存密钥；响应禁止缓存 |
| `POST` | `/api/model-providers/{provider_id}/test` | 使用本次输入或已保存密钥测试连接 |
| `GET` | `/api/model-providers/{provider_id}/models` | 从已配置上游读取远端模型元数据 |
| `POST` | `/api/models` | 添加或更新一个账号模型行 |
| `GET` | `/api/models` | 读取当前账号已添加模型 |
| `PATCH` | `/api/models/{model_id}` | 编辑名称、思考档位、分状态能力 profile 与 Token 上限 |
| `POST` | `/api/models/capability-probe/{model_id}` | 刷新远端元数据并探测两种思考状态的真实能力 |
| `GET/PATCH` | `/api/model-access-settings` | 读取或更新模型接入设置中的 `chat/title/vision_parse/compact` 默认模型 |
| `DELETE` | `/api/models/{model_id}` | 删除模型并清空引用它的默认用途 |

普通 Provider 响应和保存、测试结果提供 `has_api_key`，显式 reveal 接口才向认证用户返回密钥。模型列表沿用认证 `account_id` 作用域，响应主体由模型及能力字段组成。能力字段、默认值和附件选择语义只在[模型运行契约](../架构/模型附件与推理模式.md#模型配置语义)维护。

模型 Provider 与联网 Provider 的服务地址在数据库、HTTP API、Service 和前端类型中统一使用 `api_url`；内置默认值使用 `default_api_url`。

## 聊天设置

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/account-settings/conversation-preferences` | 读取当前账号的输入框与回答显示偏好 |
| `PUT` | `/api/account-settings/conversation-preferences` | 完整保存当前账号的输入框与回答显示偏好 |

偏好保存在操作者的 `settings.db`，包括发送快捷键、上下文使用情况、相关内容、词元用量、系统与能力显示频率、工具记录和输入追溯显示项。HTTP 直接暴露的三个布尔字段是 `is_context_window_usage_visible`、`is_related_content_visible` 和 `is_token_usage_visible`；列表字段 `visible_context_types` 与 `tool_display_types` 保持列表表达。`PUT` 接收并返回完整偏好，普通并发修改采用最后有效写入优先；这些字段只控制前端交互与展示，不修改会话事件、模型输入或记录生成。

## 检验指标分类目录

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/account-settings/lab-dictionary` | 读取当前账号分类、指标与 `dictionary_revision` |
| `POST` | `/api/account-settings/lab-dictionary/items` | 创建指标 |
| `PATCH/DELETE` | `/api/account-settings/lab-dictionary/items/{item_id}` | 更新或删除指标 |
| `POST` | `/api/account-settings/lab-dictionary/items/{source_item_id}/merge` | 把来源指标在同一事务中合并到明确目标指标 |
| `POST` | `/api/account-settings/lab-dictionary/categories` | 创建分类 |
| `PATCH/DELETE` | `/api/account-settings/lab-dictionary/categories/{category_name}` | 更新或删除分类 |

所有字典写入携带 `expected_dictionary_revision`。指标字段使用 `item_name_zh`、`primary_category_name` 和 `related_category_names`；分类使用可修改的自然主键 `category_name`。写入影响与合并冲突语义见[报告领域的检验指标分类目录](../领域/医疗报告.md#检验指标分类目录)。

## 联网账号设置

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/account-settings/web-access` | 读取开关、当前服务与两家 `has_api_key` |
| `PATCH` | `/api/account-settings/web-access` | 更新 `is_enabled`、`active_provider_id`；启用时要求当前服务已配置 |
| `PUT` | `/api/account-settings/web-access/providers/{provider_id}/credential` | AES-GCM 密封并保存密钥 |
| `POST` | `/api/account-settings/web-access/providers/{provider_id}/credential/reveal` | 主动读取当前账号已保存密钥，响应禁止缓存 |
| `DELETE` | `/api/account-settings/web-access/providers/{provider_id}/credential` | 删除非当前启用凭证 |
| `PATCH` | `/api/account-settings/web-access/providers/{provider_id}` | 保存当前账号中该联网服务的 API 地址 |
| `POST` | `/api/account-settings/web-access/providers/{provider_id}/test` | 用本次输入或已保存密钥测试该服务已保存的 API 地址 |

普通设置、保存、删除和测试响应只返回 `has_api_key`，不回传密钥；reveal 响应设置 `Cache-Control: no-store`。启用、去标识化和供应商行为见[公网研究领域契约](../领域/公网研究.md)。

## 认证与收藏

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/auth/session` | 读取 HttpOnly Cookie 登录态 |
| `POST` | `/api/auth/sign_up`、`/api/auth/sign_in`、`/api/auth/sign_out` | 注册、登录和退出 |
| `PATCH` | `/api/auth/account`、`/api/auth/password` | 自动保存当前用户标识与账号名称，或更新密码；用户标识由数据库唯一约束保护 |

`account_id` 是服务端生成的规范 UUID，作为不可变账号身份；`member_id` 是不可变成员身份。`account` 是可修改、大小写不敏感且全局唯一的用户标识，用于登录、界面标识和授权接收方查找。目录、凭证 AAD、会话及授权关系都以 `account_id` 为账号作用域。物理边界见[本地存储](../运维/本地存储.md)。

用户标识会去除首尾空白并规范化为小写，长度为 1–20 个字符，可使用英文字母、数字、下划线和短横线；`all_users` 保留给共享系统目录。

认证 JSON 采用封闭字段集合，便于人识别的账号名称统一使用 `account_name`。`POST /api/auth/sign_up` 的注册请求为：

```json
{
  "account": "admin",
  "account_name": "Serenita 用户",
  "password": "...",
  "confirm_password": "..."
}
```

账号名称会去除首尾空白，允许 Unicode 与内部空格，长度为 1–50 个 Unicode 码点。`GET /api/auth/session` 的已认证响应为：

```json
{
  "authenticated": true,
  "account_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "account": "admin",
  "account_name": "Serenita 用户",
  "expires_at": "2026-09-12T12:00:00+08:00"
}
```

`PATCH /api/auth/account` 的账号资料更新请求为：

```json
{
  "account": "new_login",
  "account_name": "新的账号名称"
}
```

保存成功返回完整认证会话，与注册、登录和认证恢复使用同一结构：

```json
{
  "authenticated": true,
  "account_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "account": "new_login",
  "account_name": "新的账号名称",
  "expires_at": "2026-09-12T12:00:00+08:00"
}
```

登录先规范化用户输入的 `account`，再按该用户标识查询账号。新登录会话保存 `account_id`；恢复登录态时连接 `accounts`，因此会直接取得当前 `account` 和 `account_name`。账号资料更新按 `account_id` 原子保存当前账号行，并保持登录会话、目录、凭证、业务数据和 `access_revision` 连续稳定。其它账号在下一次成员或授权请求中读取当前名称。密码更新按 `account_id` 撤销其它登录会话。授权列表使用 `grantee_account` 与 `owner_account` 表示双方当前用户标识，使用 `grantee_account_name` 表示接收方当前账号名称。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET/POST` | `/api/favorites` | 列出或创建收藏 |
| `GET/PATCH/DELETE` | `/api/favorites/{favorite_id}` | 读取、更新或删除单条收藏 |
| `POST` | `/api/favorites/batch-delete` | 批量删除当前账号收藏 |

收藏响应聚焦收藏内容与来源信息，账号作用域由认证 `account_id` 确定。`source_type` 只支持 `message` 和 `report`；所有聊天回答都使用 `message`，无论该回答是否关联医疗报告。报告收藏使用 `source_type=report`、`member_id` 和报告 ID。服务端从当前有权限的医疗报告生成完整 Markdown 快照，覆盖报告事实以及当时已有的 `analysis_content`；没有解读结果的医疗报告同样可以收藏，解读结果不作为独立收藏来源。回答收藏可以来自不关联成员的聊天，此时成员字段为空；回答唯一性由账号、来源类型、来源会话和来源消息共同约束，不依赖空成员字段。

## 成员、逐成员健康档案授权与启动偏好

聊天列表与详情返回 `access_state`：`available` 表示未关联成员或仍获授权，可执行；`history_only` 表示撤权后的历史聊天，可读但不可发送、重新生成或分叉。`member_name` 为根据操作者已保存关联读取的当前名称，允许撤权后的历史名称展示；未关联时为 `null`。成员删除后聊天、收藏的 `member_id` 均为 `null`。报告引用状态 `availability` 为 `available`、`deleted` 或 `forbidden`，依据引用自身的成员与报告身份解析，不依赖聊天当前关联。

身份、默认、固定聊天绑定、授权复核与删除事务语义只在[成员与健康档案领域契约](../领域/成员与健康档案授权.md)维护。成员接口统一以认证账号解析操作者、健康档案所有者账号和有效健康档案权限；客户端不能指定健康档案所有者账号目录。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET/POST` | `/api/members` | 读取可访问成员及偏好，或创建自有成员 |
| `GET/PATCH/DELETE` | `/api/members/{member_id}` | 读取或保存成员基础资料与默认选择，或删除自有成员及其健康档案 |
| `GET` | `/api/members/{member_id}/lab-dictionary` | 读取目标成员健康档案所有者账号的检验指标分类目录，报告使用统计限于当前成员 |
| `GET/PUT` | `/api/account-settings/member-grants` | 读取或批量授予、调整逐份权限 |
| `DELETE` | `/api/account-settings/member-grants/{member_id}/{account_id}` | 撤销单份授权 |
| `PATCH` | `/api/account-settings/member-preferences` | 保存启动模式、默认成员与最近选择 |
| `GET` | `/api/members/access-events` | 读取账号级授权修订通知，不传医疗内容 |

成员集合的 `default_member_id`、`last_member_id` 和 `initial_member_id` 都可以为 `null`。删除响应返回 `member_id`、`deleted`、`pending_file_cleanup` 与更新后的 `collection`；`pending_file_cleanup` 只表示尚未完成的物理原件清理，不改变已经提交的领域删除结果。

成员基础资料采用封闭字段集合：必填成员名称 `member_name`，以及可空的 `sex`、`birth_date` 和 `blood_type`。不另设完整姓名或成员与操作者关系字段；请求包含其它成员资料字段时返回参数校验错误。
