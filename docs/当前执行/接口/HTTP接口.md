# HTTP API 契约

> 文档层级：当前执行 / 接口契约
>
> 负责：浏览器与后端之间的当前 HTTP 路由、方法和高层请求语义。
>
> 不负责：领域内部工具参数 Schema、数据库表、页面布局、事件信封或供应商 wire 协议。
>
> 上位文档：[技术架构总览](../架构/技术架构总览.md)；领域语义见[成员](../领域/成员与健康档案授权.md)、[医疗报告](../领域/医疗报告.md)和[公网研究](../领域/公网研究.md)。

接口均使用同源 HttpOnly Cookie 认证。医疗报告接口统一将 `member_id` 写入路径以确定成员作用域。表格是当前路由总表，具体授权、事务和展示行为由相应领域与前端契约定义。

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
| `GET` | `/api/conversations` | 使用 cursor、limit 读取当前账号会话列表，默认 24、上限 100，返回 conversations、next_cursor、has_more |
| `PATCH` | `/api/conversations/{session_id}` | 原子更新手工标题和/或置顶状态并返回会话摘要 |
| `POST` | `/api/conversations/batch-pin` | 在一个事务内统一设置非空去重会话集合的置顶状态 |
| `POST` | `/api/conversations/batch-delete` | 复用单条删除语义并返回已删除 ID 与逐项真实失败 |
| `GET` | `/api/conversations/{session_id}` | 读取当前线性投影、pending 轮次与资源状态 |
| `DELETE` | `/api/conversations/{session_id}` | 删除当前会话；不级联删除独立子会话 |

医疗报告上传、开始解读和重新解读复用这些接口。会话详情的账号作用域由认证 Cookie、账号私有数据库路径与事件 header 共同确定，响应主体聚焦会话投影和业务资源。

附件能力接口接受可选 `model_id`，省略时使用当前聊天默认模型，返回 `{model_id, file_mime_types}`；未配置默认模型时返回 `model_id=null` 和空列表，指定模型不存在时返回 `MODEL_NOT_FOUND`。列表同时考虑模型能力、Provider 原生附件支持和视觉解析能力，与上传及发送共享后端检查。查询结果不代替后续请求的实时校验。

附件上传不接收上传标识，也不提供上传任务或状态查询接口。成功响应保留 `resource_id`、`original_filename`、`mime_type`、`size_bytes`、`relative_path`、`sha256`、`storage_status=ready`、`lifecycle_status=pending` 和 `expires_at`。`original_filename` 是安全规范化后的原始显示文件名；`resource_id` 是会话目录中的实际存储文件名，同名上传以 `-002`、`-003` 递增，前端放入预览 URL 时必须对其整体执行百分号编码。响应与 `resource/attached` 事件均不含 `source`；事件也不保存 `storage_status`、`lifecycle_status` 或 `expires_at`。

上传进度只存在于当前浏览器内存。网络错误、HTTP 错误或无效成功响应都结束并移除该进度项，用户通过重新选择文件再次上传。客户端不区分服务端未处理与服务端已经成功但响应丢失；后一种资源保持不可见的 `ready + pending`，按 24 小时过期规则清理。

`context_resources` 请求只提交资源类型、资源 ID 及必要的成员 ID 或注释定位字段，不接受展示名、医疗报告名或文件名快照。轮次开始时，后端通过医疗报告插件按 `report_id` 重新读取当前医疗报告，并在同一条 Provider 用户消息中附加 `ATTACHED EXISTING CONTENT` 文本块。该文本块进入实际发送且持久化的 `provider_payload`：`report` 保存完整医疗报告事实，不含 `analysis_content`；若存在既有解读结果，则另以 `existing_ai_analysis` 保存正文、更新时间和过期状态。

## 医疗报告读取与页面命令

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `POST` | `/api/members/{member_id}/reports` | 页面手工创建一份七类结构化医疗报告 |
| `GET` | `/api/members/{member_id}/reports` | 医疗报告列表读取；可用 `report_type` 筛选，按日期降序分组 |
| `GET` | `/api/members/{member_id}/reports/{report_id}` | 医疗报告详情、结构化字段、来源和解读结果 |
| `GET` | `/api/members/{member_id}/reports/{report_id}/conversation-input-preview` | 返回账号安全的 `ATTACHED EXISTING CONTENT` 描述；原始 `report` 与可选 `existing_ai_analysis` 分字段保存 |
| `PATCH` | `/api/members/{member_id}/reports/{report_id}/fields` | 页面字段或解读结果正文编辑 |
| `POST` | `/api/members/{member_id}/reports/{report_id}/lab-items` | 页面添加一条检验指标记录 |
| `DELETE` | `/api/members/{member_id}/reports/{report_id}/lab-items/{item_id}` | 页面删除一条非最后的检验指标记录 |
| `DELETE` | `/api/members/{member_id}/reports/{report_id}` | 页面删除 |
| `POST` | `/api/members/{member_id}/reports/{report_id}/source-files` | 为既有医疗报告补充一份或多份原件 |
| `GET` | `/api/members/{member_id}/reports/{report_id}/source-files/{resource_id}` | 下载有权限的来源文件 |
| `GET` | `/api/members/{member_id}/reports/{report_id}/source-files/{resource_id}/thumbnail` | 获取来源缩略图 |

补充原件使用 `multipart/form-data`，同名 `files` 字段可提交 1 至 20 份 PDF、JPG、PNG 或 HEIC 文件；单文件不超过 20MB，单次总大小不超过 100MB。该页面命令直接关联当前医疗报告，不解析或更新医疗报告事实，不创建会话。目标没有既有来源时，第一份补充的原件成为主来源；已有主来源时保持不变。相同内容已经关联到目标医疗报告，或同次选择包含相同内容时，返回 `REPORT_SOURCE_DUPLICATE`，不产生部分写入。

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
| `POST` | `/api/models` | 以 unknown 添加账号模型行，重复添加保留既有配置 |
| `GET` | `/api/models` | 读取当前账号已添加模型 |
| `PATCH` | `/api/models/{model_id}` | 编辑名称、类型、对应能力结构与可空参数 |
| `POST` | `/api/models/capability-probe/{model_id}` | 先实测模型类型，再读取元数据并检测对应能力 |
| `POST` | `/api/models/capability-probe-cancel/{model_id}` | 取消当前账号目标模型的检测 |
| `GET/PATCH` | `/api/model-access-settings` | 读取或更新 chat/title/vision_parse/compact/text_embedding/multimodal_embedding 默认模型 |
| `DELETE` | `/api/models/{model_id}` | 删除模型并清空引用它的默认用途 |

批量输入上限只使用可编辑的 `max_batch_size`：1 表示每次一条，null 表示未知。检测明确不支持批量时写入 1，确认支持时清除原有的 1，其余手工值保留；未验证时保留原值。`embedding_capabilities` 不保存独立的批量支持状态，调用按当前上限校验，多项融合内容算作一条输入。

向量输出维度统一使用可编辑的 `embedding_dimensions`；成功检测以未指定维度请求的实际返回维度覆盖，检测失败保留原值。

模型配置中的 `embedding_capabilities` 使用 `supports_text` 布尔值和 `file_mime_types` 字符串列表保存输入能力；读取、添加、编辑及检测返回均使用相同结构。输入未确认时文本为 false、文件列表为空。`capability_detection.checks` 保留检测状态与错误详情。

添加请求使用 provider_id、remote_model_id，页面自动启动后续检测。模型响应统一包含 model_type 与两类参数，不适用字段为 null。PATCH 字段省略表示不更新，可空参数显式 null 表示清空，输入限制与维度必须为正整数。

检测和取消请求可携带 `{probe_id}`。检测返回 `{model, metadata, checks, errors, cleared_defaults}`，检查分组增加 type 与 embedding。模型响应的 capability_detection 保存最近完成的 metadata、checks、errors；取消或配置变化导致失效的检测不提交。编辑也返回 cleared_defaults，告知被清空的默认用途。取消返回 `{model_id, cancelled}`，被取消的检测请求返回 MODEL_CAPABILITY_PROBE_CANCELLED；不符合用途的默认选择返回 INVALID_DEFAULT_MODEL。

普通 Provider 响应和保存、测试结果提供 `has_api_key`，显式 reveal 接口才向认证用户返回密钥。模型列表沿用认证 `account_id` 作用域，响应主体由模型及能力字段组成。完整能力结构、默认值和附件选择语义在[模型运行契约](../架构/模型附件与推理模式.md#模型配置语义)维护。

模型 Provider 与联网 Provider 的服务地址在数据库、HTTP API、Service 和前端类型中统一使用 `api_url`；内置默认值使用 `default_api_url`。

## 聊天设置

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/account-settings/conversation-preferences` | 读取当前账号的输入框与回答显示偏好 |
| `PUT` | `/api/account-settings/conversation-preferences` | 完整保存当前账号的输入框与回答显示偏好 |

偏好保存在操作者的 `settings.db`，包括发送快捷键、上下文使用情况、相关内容、词元用量、模型标识、系统与能力显示频率、工具记录和输入追溯显示项。HTTP 直接暴露的四个布尔字段是 `is_context_window_usage_visible`、`is_related_content_visible`、`is_token_usage_visible` 和 `is_model_identity_visible`（默认关闭）；列表字段 `visible_context_types` 与 `tool_display_types` 保持列表表达。`PUT` 接收并返回完整偏好，普通并发更新采用最后有效写入优先；这些字段只控制前端交互与展示，不更新会话事件、模型输入或记录生成。

## 检验指标分类目录

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/account-settings/lab-dictionary` | 读取当前账号分类、指标与 `dictionary_revision` |
| `POST` | `/api/account-settings/lab-dictionary/items` | 创建指标 |
| `PATCH/DELETE` | `/api/account-settings/lab-dictionary/items/{item_id}` | 更新或删除指标 |
| `POST` | `/api/account-settings/lab-dictionary/items/{source_item_id}/merge` | 把来源指标在同一事务中合并到明确目标指标 |
| `POST` | `/api/account-settings/lab-dictionary/categories` | 创建分类 |
| `PATCH/DELETE` | `/api/account-settings/lab-dictionary/categories/{category_name}` | 更新或删除分类 |

所有字典写入携带 `expected_dictionary_revision`。指标字段使用 `item_name_zh`、`primary_category_name` 和 `related_category_names`；分类使用可更新的自然主键 `category_name`。写入影响与合并冲突语义见[医疗报告领域的检验指标分类目录](../领域/医疗报告.md#检验指标分类目录)。

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

`account_id` 是服务端生成的规范 UUID，作为不可变账号身份；`member_id` 是不可变成员身份。`account` 是可更新、大小写不敏感且全局唯一的用户标识，用于登录、界面标识和授权接收方查询。目录、凭证 AAD、会话及授权关系都以 `account_id` 为账号作用域。物理边界见[本地存储](../运维/本地存储.md)。

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

登录先规范化用户输入的 `account`，再按该用户标识查询账号。新登录会话保存 `account_id`；恢复登录态时连接 `accounts`，因此会直接读取当前 `account` 和 `account_name`。账号资料更新按 `account_id` 原子保存当前账号行，并保持登录会话、目录、凭证、业务数据和 `access_revision` 连续稳定。其它账号在下一次成员或授权请求中读取当前名称。密码更新按 `account_id` 撤销其它登录会话。授权列表使用 `grantee_account` 与 `owner_account` 表示双方当前用户标识，使用 `grantee_account_name` 表示接收方当前账号名称。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET/POST` | `/api/favorites` | 列出或创建收藏 |
| `GET/PATCH/DELETE` | `/api/favorites/{favorite_id}` | 读取、更新或删除单条收藏 |
| `POST` | `/api/favorites/batch-delete` | 批量删除当前账号收藏 |

收藏响应聚焦收藏内容与来源信息，账号作用域由认证 `account_id` 确定。`source_type` 只支持 `message` 和 `report`；所有聊天回答都使用 `message`，无论该回答是否关联医疗报告。医疗报告收藏使用 `source_type=report`、`member_id` 和医疗报告 ID。服务端从当前有权限的医疗报告生成完整 Markdown 快照，覆盖医疗报告事实以及当时已有的 `analysis_content`；没有解读结果的医疗报告同样可以收藏，解读结果不作为独立收藏来源。回答收藏可以来自不关联成员的聊天，此时成员字段为空；回答唯一性由账号、来源类型、来源会话和来源消息共同约束，不依赖空成员字段。

## 成员、逐成员健康档案授权与启动偏好

聊天列表与详情返回 `access_state`：`available` 表示未关联成员或仍获授权，可执行；`history_only` 表示撤权后的历史聊天，可读但不可发送、重新生成或分叉。`member_name` 为根据操作者已保存关联读取的当前名称，允许撤权后的历史名称展示；未关联时为 `null`。成员删除后聊天、收藏的 `member_id` 均为 `null`。医疗报告引用状态 `availability` 为 `available`、`deleted` 或 `forbidden`，依据引用自身的成员与医疗报告身份解析，不依赖聊天当前关联。

身份、默认、固定聊天绑定、授权复核与删除事务语义只在[成员与健康档案领域契约](../领域/成员与健康档案授权.md)维护。成员接口统一以认证账号解析操作者、健康档案所有者账号和有效健康档案权限；客户端不能指定健康档案所有者账号目录。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET/POST` | `/api/members` | 读取可访问成员及偏好，或创建自有成员 |
| `GET/PATCH/DELETE` | `/api/members/{member_id}` | 读取或保存成员基础资料与默认选择，或删除自有成员及其健康档案 |
| `GET` | `/api/members/{member_id}/lab-dictionary` | 读取目标成员健康档案所有者账号的检验指标分类目录，医疗报告使用统计限于当前成员 |
| `GET/PUT` | `/api/account-settings/member-grants` | 读取或批量授予、调整逐份权限 |
| `DELETE` | `/api/account-settings/member-grants/{member_id}/{account_id}` | 撤销单份授权 |
| `PATCH` | `/api/account-settings/member-preferences` | 保存启动模式、默认成员与最近选择 |
| `GET` | `/api/members/access-events` | 读取账号级授权修订通知，不传医疗内容 |

成员集合的 `default_member_id`、`last_member_id` 和 `initial_member_id` 都可以为 `null`。删除响应返回 `member_id`、`deleted`、`pending_file_cleanup` 与更新后的 `collection`；`pending_file_cleanup` 只表示尚未完成的物理原件清理，不改变已经提交的领域删除结果。

成员基础资料采用封闭字段集合：必填成员名称 `member_name`，以及可空的 `sex`、`birth_date` 和 `blood_type`。不另设完整姓名或成员与操作者关系字段；请求包含其它成员资料字段时返回参数校验错误。

## 成员既往史接口

- `GET /api/members/{member_id}/medical-history`：读取既往史；重复查询参数 `fields` 选择一项或多项，省略读取全部。
- `PATCH /api/members/{member_id}/medical-history`：JSON 对象仅提交需更新的项目；至少一项，未提交保持原值，文本替换，`null` 或空白清空。整次事务保存。

项目、响应及更新时间语义见[成员既往史](../领域/成员既往史.md)。两者返回 `member_id` 和 `history`，读取返回所选项目，更新返回全部项目。沿用实时成员权限和失效目标错误。

## 健康日记

健康日记使用 GET/POST `/api/members/{member_id}/medical-logs` 查询目录与创建；GET/PATCH/DELETE `/api/members/{member_id}/medical-logs/{medical_log_id}` 读取、局部更新与删除。创建返回 201，其余成功返回 200。目录接受 after_date、before_date、query、cursor、limit，默认每页 24 条、上限 100 条；返回 member_id、medical_logs、total、next_cursor。详情包含 medical_log_id、member_id、recorded_on、title、完整正文 content、created_at 和 updated_at，创建与更新返回 medical_log，删除返回 medical_log_id 与 deleted。字段业务含义和更新语义见[健康日记](../领域/健康日记.md)，权限和错误沿用现有契约。

## 用药资料与站内提醒

所有成员路由以 `/api/members/{member_id}` 为前缀。详情与目录读取需要成员读权限，资料写入需要编辑权限。统一通知设置、到期事项和通知操作使用当前登录操作者作用域。

### 药品管理

| 方法 | 路径 | 返回与行为 |
| --- | --- | --- |
| GET | `/medications` | 当前成员可引用的所有者账号药品目录 `{items,total,next_cursor}`；`inventory_only=true` 时只返回当前成员有批次的药品 |
| GET | `/medications/{medication_id}` | 只读目录药品资料、原件元数据及当前成员批次 |
| GET / POST | `/medications/{medication_id}/batches` | 批次集合 / 创建批次 |
| PATCH / DELETE | `/medications/{medication_id}/batches/{batch_id}` | 更新 / 删除批次，检查父药品归属 |
| GET | `/medications/{medication_id}/source-files/{resource_id}` | 读取仅归属当前药品的私有原件内容，响应 no-store、nosniff |

设置中的药品信息接口使用 `/api/medication-catalog`：GET 分页查询，POST 创建；`/{medication_id}` 支持 GET、PATCH、DELETE。`/{medication_id}/source-files` 使用 POST 批量补充原件，`/{medication_id}/source-files/{resource_id}` 使用 GET 读取。全部按登录账号隔离，创建与原件补充使用 `Idempotency-Key`。药品仍被库存或计划引用时删除返回 409。成员用药接口没有药品信息写入或原件补充路由。


药品使用 `generic_name` 与 `brand_name` 保存名称。`generic_name` 创建必填，不接受 null、空字符串或纯空白；`brand_name` 未知为 null，填写时必须非空。PATCH 省略名称时保持原值，不能清空通用名；两个名称可在一次请求中替换。应用层与数据库同时校验必填内容。药品资料及计划、通知中的药品身份均只返回这两个名称字段，显示名称由使用方组合。

单文件非空且最多 20 MB，允许 JPEG、PNG、HEIC、PDF 和 UTF-8 纯文本；用途 package、label、leaflet，默认 package。文件响应重新校验权限、路径和 SHA-256。

药品允许没有批次；仍被任一库存或计划引用时，设置中的删除操作返回 409。删除成员库存批次或计划不删除目录药品。

### 用药计划

| 方法 | 路径 | 返回与行为 |
| --- | --- | --- |
| GET / POST | `/medication-plans` | 目录 `{items,total,next_cursor}` / 创建计划（201） |
| GET / PATCH / DELETE | `/medication-plans/{medication_plan_id}` | 计划详情 / 更新计划 / 删除计划 |

计划创建必填非空 `medication_id`，必须指向当前成员健康档案所有者账号目录中的已有药品；PATCH 可提交该字段切换药品，不能提交 null 或空白。`medication_identity` 仅在读取结果中返回，由服务端每次按 `medication_id` 从目录读取，POST 和 PATCH 均不接受该字段，计划和通知表均不保存药品身份。缺失或无效标识返回 400，不存在、已删除或其它账号目录药品返回 404。计划的补充说明统一使用 `notes`。起止时间、精度、时区、每次剂量、给药途径、频率和使用状态均直接作为计划字段读写。PATCH 仅提交更新的字段，合并当前计划后整次校验并在同一事务中保存。相同 medication_id 可对应多个独立计划，各自按稳定标识更新和删除。保存计划时 starts_at 和 start_precision 必须有值，缺少开始日期返回 400，整个请求不写入；结束边界 ends_at 接受带偏移 ISO 时间、long_term（明确长期）或 null（未知，省略默认）；long_term 和 null 均要求 end_precision 为 null。每次剂量仅保存于 `dose_text`，允许为空；`schedule.times` 每项只接受 `time`，提交条目级剂量返回 400。


### 统一站内通知

| 方法 | 路径 | 返回与行为 |
| --- | --- | --- |
| GET / PUT | `/api/account-settings/notifications` | PUT 接受 notifications_enabled、medication_due_enabled、medication_expired_enabled、answer_completed_enabled 四个布尔开关，至少提供一个；总通知与子通知参数互斥，拒绝 null 和未知字段。设置总通知时全部子通知跟随；仅设置子通知时省略的子通知保持原值，总通知等于子通知是否存在开启项。返回四个开关、各自的 *_enabled_since 和 notifications_updated_at |
| GET | `/api/notifications` | status=pending/read，默认 pending；limit 默认 50、范围 1–100；cursor 绑定账号与状态；返回 items、next_cursor、errors |
| GET | `/api/notifications/summary` | 返回 pending_count、errors；验证最多 2,000 条候选，确认达到 100 返回 100；无法确认返回 null 和错误 |
| GET | `/api/notifications/events` | Cookie 认证的 SSE；notifications_changed 事件仅包含 revision，格式为连接代次:变更序号；10 秒心跳，定期发送 stream_renewal 后结束流，客户端正常重连；认证失效发送 authentication_expired 并结束 |
| POST | `/api/notifications/{notification_id}/actions` | action=read；返回 notification_id、status、available_at |

列表按 occurred_at 和 notification_id 倒序，每次最多验证 500 条候选，达到扫描边界时提供继续游标。items 包含公共通知字段及经过权限核验的 details、target、actions。target 的 member_id、resource_type、resource_id 定位具体对象。药品过期提醒的 resource_type 为 medication_batch，target 另含经授权读取的 medication_id，用于打开该药品的对应批次。错误只返回安全的类别和说明，不暴露未授权对象。

通知查看、接收设置和标为已读仅通过上述 HTTP API 提供给页面；会话智能体不提供通知工具。接收关闭保留已有记录和操作能力，详见[站内通知](../领域/站内通知.md)。

### 共同请求规则

创建资料、计划、批次或补充文件时必须提交 `Idempotency-Key`，非空且最多 200 字符；持久化按操作者及标识去重，相同请求重试返回对应对象，相同标识不同内容为 409，原对象已删除为 404。普通更新采用最后有效写入优先。PATCH 省略保持原值，可空字段 null 清空，集合空数组清空；空更新、未知字段及不合法的完整对象均拒绝。

目录返回的 total 为当前作用域及筛选条件下的完整总数，不受游标与每页数量影响。设置药品目录支持 `query`、`cursor`、`limit`；成员药品查询另支持 `inventory_only`，只列出当前成员有批次的药品。计划目录支持 `query`、`status`、`after_date`、`before_date`、`undated`、`cursor`、`limit`。页长默认 24、最大 100，游标绑定成员、对象类别和筛选条件。日期为 YYYY-MM-DD，界限含当天；计划按区间相交筛选，未明确日期的计划通过 undated 筛选。游标对应位置失效返回 400，调用方重新加载目录。设置药品详情返回基本信息及原件；成员药品详情另返回当前成员的完整批次集合。

完整字段及枚举以 `schemas/medication.py` 和[领域契约](../领域/用药记录.md)为准，Schema 在合并 PATCH 后校验，业务错误为 400、不可访问为 403、不存在为 404、请求或提醒状态冲突为 409。

## 身体指标接口

以下路径统一前缀 `/api/members/{member_id}/body-metrics`，均实时校验成员授权。业务参数与返回字段见[身体指标](../领域/身体指标.md)，记录结构后端由 `schemas/body_metric.py` 校验，前端使用 `api/bodyMetricApi.ts`。

| 方法及相对路径 | 请求与结果 |
| --- | --- |
| GET /catalog | 返回 metrics、meal_types、stages |
| GET /records | after/before 日期、category、source、timezone、offset、limit；返回 items、total、next_offset |
| POST /records | 完整 BodyRecord，可选 Idempotency-Key；返回创建详情 |
| GET /records/{record_id} | 详情与 files 元数据 |
| PATCH /records/{record_id} | metric、starts_at、ends_at、timezone、precision、notes、data；省略字段保持，data 合并，foods/stages 整组替换 |
| DELETE /records/{record_id} | 删除记录、图片和导入关联，返回 deleted |
| GET /statistics | 同记录查询的日期、分类、来源与时区过滤；返回 series、sources、total_records、coverage_from/to |
| GET /statistics/series/{series_id} | 同一筛选下读取序列日期桶或原始点，使用游标分页 |
| POST /records/{record_id}/files | multipart file，PNG/JPEG/WebP，上限 10 MiB；返回详情 |
| GET /records/{record_id}/files/{file_id} | 原图字节，no-store、nosniff |
| DELETE /records/{record_id}/files/{file_id} | 解除图片关联，返回详情 |
| POST /imports/preview | multipart file，必填 Idempotency-Key；timezone 决定预览日期边界；返回范围、问题、计数与任务身份 |
| GET /imports | cursor/limit 分页读取导入摘要，默认每页 24 条，返回 items、next_cursor、has_more |
| GET /imports/{import_id} | 返回任务状态与结果 |
| POST /imports/{import_id}/commit | 可选 after/before、categories，后台提交，可重试；返回当前任务 |
| DELETE /imports/{import_id} | 按导入归属删除批次，返回 records_deleted 与 records_retained |
| GET /template?format=json\|csv | 下载含虚构数据的标准文件 |

统计序列摘要含 series_id、metric、label、source、device、method、unit、score_max、aggregation、count、days、latest、minimum、maximum、mean、secondary_mean、total、daily_mean、omitted_overlaps、allocated_intervals，以及最多 12 个日期值的 preview。汇总不含全量 points 或 buckets；total_records 为完整匹配数量，coverage_from、coverage_to 为匹配时刻范围，coverage_dates 含 first、last、recorded_days，missing_values 为营养及睡眠字段的缺失记录数量。excluded_stale_scores 返回排除的过期评分数量；omitted_overlaps 和 allocated_intervals 均按去重记录数计。

序列读取使用 `view=buckets|points`、cursor、limit 和返回的 next_cursor；默认 100 项，上限 1,000 项。桶返回日期、值、极值和数量；点返回 record_id 与起止时间。游标绑定序列和范围，数据变化使其失效时返回 400。统计覆盖范围不受分页限制。

预览的 `Idempotency-Key` 为 1 至 200 字符，同一上传失败重试复用原标识。相同标识不同文件或时区拒绝；同文件新请求建立新预览。记录、统计接口的 timezone 决定 after、before 日期边界，省略为 Asia/Shanghai，页面显式提交浏览器时区。

页面普通操作走 API → Service → Repository。图片识别复用会话附件与消息接口，由通用 Harness 自主调用身体指标工具。


登录签发会话时，Repository 在同一写事务内确认账号密码仍与 Service 刚才验证的哈希一致。并发更新密码会使旧凭证的待签发请求返回 SIGN_IN_FAILED；密码变更也要求已验证哈希仍有效。
