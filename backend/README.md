# Serenita 后端

后端是 FastAPI 分层单体，负责认证、账号隔离、模型网关、智能体轮次、事件持久化和业务数据安全边界。认证入口遵循 API → `AuthService` → `AuthRepository`，并向各业务域提供由规范 UUID 表示的可信 `account_id`。

## 模块

```text
backend/app/
  api/              HTTP 协议与依赖注入
  application/      应用装配、会话用例及任务、审计、压缩与领域能力
  agent_runtime/    可选任务计划、Skill 发现、行动循环、Tool 注册
  plugins/          能力插件及其 Skills、Tools
  providers/        供应商策略、传输、编码、解析与能力探测
  repositories/     索引、附件、报告事实、分类目录与事务协调
  storage/          当前 Schema、路径、JSONL、密钥
```

插件通过 `PluginRuntimeContext` 获得可信 `account_id`、模型网关、事件记录器和按插件隔离的 Service。`ConversationService` 不识别报告工具名称或报告业务分支，只消费通用 effect envelope 中的资源引用。

`create_app(paths=...)` 通过 `ApplicationServices` 显式绑定数据根；HTTP 依赖和插件使用同一装配入口。命令行工厂省略参数时使用 `DATA_ROOT` 或项目默认目录。架构组件及所有权见[技术架构总览](../docs/当前执行/架构/技术架构总览.md#进程内能力装配)。

## 智能体轮次

消息提交返回 started/queued 联合响应；不同会话独立执行，同会话由持久化约束限制一个执行中轮次，其余输入由队列事件投影。终态自动提升队首，取消以服务端持久化正文保留上下文；调整方向属于取消而非失败。队列接口与恢复语义见 [Agent Harness 与轮次运行](../docs/当前执行/架构/智能体运行时.md#轮次-worker-与等候队列)。

任何用户消息都直接进入统一 Harness，不存在前置规划调用。任务计划只是当前任务的可选参考；行动模型仅在确有需要时调用普通工具 `update_plan`，普通回答和单一明确操作不会产生计划。计划不约束技能、工具、行动顺序或成功判定，也不是用户审批或操作授权。`update_plan` 只产生标准的模型工具调用请求和工具结果；Harness 不维护或恢复独立计划状态，也不产生计划专用事件、上下文或阶段。Harness 的新轮次会恢复当前会话线性视图中已经成功读取、且指令仍在上下文里的技能，其余技能可按需动态加载；模型通过原生 `tools/tool_calls` 调用只读 `load_skill({"name": ...})`、`update_plan`、所有 `model_exposure="direct"` 工具和已读取技能授权的 `model_exposure="skill"` 工具，自然语言内容就是终态回答或向用户的提问。`load_skill` 的真实工具输出仅为读到的完整指令文本，并作为会话历史直接进入下一次模型请求；允许工具等宿主约束不冒充技能输出，技能也没有激活或完成状态。完整技能目录与 `load_skill` 参数枚举在当前轮次的每一步都保持不变；Harness 不会因技能已经读取而缩减目录或拒绝再次读取，是否重读由模型根据真实历史自主判断。

消息接口完成校验和事件落盘后立即启动独立轮次任务；SSE 端点不执行模型调用，而是持续追尾并重放已经持久化的记录。后台 Worker 通过一次条件更新领取任务，并使用心跳和过期中断语义。每次请求先生成一个 `PreparedProviderRequest`：Provider transport request 和最终 payload 只装配、序列化一次，同一 payload 随后用于安全持久化与真实网络发送，不再生成日志快照。安全持久化副本只排除 API Key、登录凭证、Cookie 和附件二进制，写入 `request/header.header.provider_payload`；header 不再保存重复的 system、messages、tools、tool choice 或 normalized request。

事件按 `step/start → request/context* → request/header → assistant/chunk* → model/result → step/end` 持久化。每条 `request/context` 都带 `provider_source.path` 及可选的字符区间，内容必须能从同一个持久化 `provider_payload` 精确解析，并共同覆盖全部 Provider 输入。API 与 SSE 返回完整模型输入和模型结束记录用于溯源、状态与 Token 汇总，但页面时间线过滤这两个通道，只把可追溯上下文切片、reasoning、正文、每个模型工具调用请求、工具调用和工具观测平级展示。原生模型工具调用请求直接显示持久化 `model/result.tool_calls[index].function`，不拼接、解析、格式化或补充字段；文本模型工具调用请求直接显示持久化 `raw_content`，作为实际计费的原始 JSON 唯一展示，不重复显示服务端解析结果。工具结果优先从下一次真实 `provider_payload` 的工具观测消息取模型可读 `content`：原生协议隐藏模型无法作为正文读取的 role、name 和 `tool_call_id` 外层字段，文本协议保留位于 `content` 内且模型确实可读的 `TOOL_OBSERVATION` 封装。工具业务 output 在结果事件边界递归压缩：两个及以上键集合相同的对象使用保留首行字段顺序的 `$keys`/`$rows` 列式结构，`effects` 不参与编码；持久化时间线和后续模型请求共享这一形态，需要结构访问的后端消费者先用 `decode_tabular_json` 还原。`load_skill` 是真实只读工具，技能本身没有输入输出或完成状态；当其工具观测实际进入后续 Provider message 时，该消息作为普通历史工具调用结果投影，不设技能专用输入追溯分类，也不会二次注入。原生模式的 `/tools` 与文本模式的工具协议都先于技能目录。终态模型正文保留。

## 模型能力与附件

账号模型按 `non_thinking`、`thinking` 两个 profile 保存文本、工具调用和附件 MIME 能力，同时返回只读汇总能力；思考档位、上下文窗口和最大输出 Token 独立保存。`POST /api/models/capability-probe/{model_id}` 先尝试刷新上游元数据，再探测两种状态，结果写回当前模型；删除模型会取消该模型正在执行的能力识别、关闭相关上游连接并阻止结果回写。`chat`、`title`、`vision_parse`、`compact` 四类默认用途在一条单例设置中分别持久化；删除模型会清空引用它的用途。

Provider 的原生附件 MIME 是不可突破的上限。会话发送时由一个能读取当前轮次全部文件的会话模型或 `vision_parse` 模型处理整轮；PDF 不支持原生输入时可完整渲染为最多 30 页图片。所选思考状态缺少当前轮次文本、原生工具调用或附件能力、而另一状态完整可用时，Runtime 只临时调整当前轮次并追加 `turn/thinking_mode_changed`；SSE 返回请求模式、有效模式和原因，用户偏好不被覆盖。两种状态都不支持原生工具调用时仍可使用统一文本工具协议，不把该能力字段等同于“完全不能使用工具”。

`record_annotation` 只接受当前线性投影中用户输入、过程 `model/content` 或助手最终回答的真实选区。后端验证来源记录和选区归属，再把注释作为 `ATTACHED ANNOTATION` 文本 part 放入当前用户消息；执行元数据、reasoning、工具、工具观测、错误、相关报告和 Token 用量都不能成为来源。

## 报告能力

报告插件提供独立工具：`read_report_catalog`、`read_report_information`、`read_report_analysis`、`validate_parsed_reports`、`read_lab_dictionary`、`create_report`、`link_duplicate_sources`、`merge_report`、`write_report_analysis`、`update_report_fields`、`add_lab_report_items`、`delete_lab_report_items`、`reclassify_report` 和 `delete_report`。四个技能的工具授权彼此独立：`report-query` 提供全部只读工具，`report-import` 提供导入校验与三种写入，`report-analysis` 只提供解读结果写入，`report-update` 提供校验与更新/删除；导入、解读或更新需要读取证据时必须再读取 `report-query`，后端不会隐式加载。当前用户消息文本、图片、完整 PDF 和多个附件由主 Agent 统一理解；`validate_parsed_reports` 只校验最终结构与逐报告多来源绑定，不调用模型、不拆分、不查询字典、不写业务数据。三个导入写入工具使用 `parse_call_id + report_index` 引用当前会话线性视图中的完整解析校验结果。`read_report_information` 设置 `fields` 包含 `sources` 时返回已保存原件元数据，用于重分类来源确认；不再把原件二进制注入后续模型请求。

报告详情页除上传和开始/重新解读外使用普通 CRUD：

- `POST /api/members/{member_id}/reports`
- `GET /api/members/{member_id}/reports`
- `GET /api/members/{member_id}/reports/{report_id}`
- `GET /api/members/{member_id}/reports/{report_id}/conversation-input-preview`
- `PATCH /api/members/{member_id}/reports/{report_id}/fields`
- `POST /api/members/{member_id}/reports/{report_id}/lab-items`
- `DELETE /api/members/{member_id}/reports/{report_id}/lab-items/{item_id}`
- `DELETE /api/members/{member_id}/reports/{report_id}`
- `POST /api/account-settings/lab-dictionary/items/{source_item_id}/merge`
- `POST /api/members/{member_id}/reports/{report_id}/source-files`
- `GET /api/members/{member_id}/reports/{report_id}/source-files/{resource_id}`
- `GET /api/members/{member_id}/reports/{report_id}/source-files/{resource_id}/thumbnail`

页面手工录入通过 `POST /api/members/{member_id}/reports` 一次创建已经由用户明确填写的五类结构化报告，可以没有原件；上传文件导入仍走 Harness。报告详情通过 `POST /api/members/{member_id}/reports/{report_id}/source-files` 为既有医疗报告直接补充原件，只保存并关联用户选择的文件，不解析或修改报告事实。字段更新请求包含 `field`、`value` 和可选 `item_id`。检验报告详情可从健康档案所有者账号的检验指标分类目录中，为当前分类新增尚未存在的指标记录，也可删除非最后一条指标记录；两者都是单次页面命令。页面 API 直接调用 Service → Repository，不经过工具或 Harness；普通并发修改以后提交的有效写入为准，目标已被删除、合并或移走时返回明确错误。

上传统一使用 `POST /api/conversations/context-resources`，发送统一使用 `POST /api/conversations/messages`。每轮最多 20 个文件，单文件 20MB，总计 100MB。

首次发送即使没有文本、只有附件，也会立即使用附件名设置临时会话标题，并由标题模型结合附件内容生成最终标题。标题生成属于会话索引元数据；会话详情只接收最终标题更新，不展示标题提示词或标题模型输出。会话索引保存置顶、手工标题及运行摘要所需元数据；列表按置顶优先、最近活跃时间倒序，queued/streaming 摘要从轮次索引派生。标题任务按 `(account_id, session_id)` 登记取消信号；手工重命名先取消该任务及阻塞中的 Provider 请求，再保存标题，自动标题以手工标题标记仍为 false 为 CAS 条件。

## 联网研究能力

`plugins/web` 不注册技能，只注册直接可用的 `web_search` 与 `web_read`。系统提示词要求模型对依赖当前指南或权威依据的重要医疗问题主动搜索，并按监管或卫生机构、正式指南与专业学会、系统综述、原始研究的非排他层级选择来源；关键医学结论必须读取至少一项直接支持它的权威网页正文，并且只引用成功读取页面中的 `citation_id`。成功读取的来源中至少一项必须本身来自上述权威层级，转载或文档镜像不能单独满足要求；已有足以回答用户问题的权威网页正文时及时作答，不为非必要细节反复读取同一搜索结果或追求资料穷尽。最终回答逐项检查并就近引用每项保留的关键结论，没有已读取权威网页正文引用的结论应省略或明确说明无法核验，带单位的医学阈值、时间区间和明确处置建议不能作为常见安全提示而免除核验与引用。稳定概念和低风险常识不强制联网，纯概念问题不得主动扩展到正常范围、诊断阈值或治疗建议来触发搜索。`web_search` 统一 Tavily Search 和 Exa Search，每次只请求供应商一次并取得最多 10 条搜索结果，保留供应商实际返回的完整搜索结果摘要，在内部按每条搜索结果一个逻辑页装配，为去重结果生成只属于该次工具观测的 `citation_id`；`web_read` 只接受当前会话线性视图中真实 `web_search` 工具消息的 `tool_call_id`（观测外层同值 `call_id`）作为 `search_call_id` 与一个结果索引，由供应商 Extract/Contents 一次取得网页正文，再在内部按每 10000 字符一个逻辑页装配，不能接收任意 URL，也不对网页正文做有损截断。模型只看到一次工具调用和一个包含全部逻辑页的工具结果；工具结果整体超出上下文硬预算时只返回 `TOOL_RESULT_TOO_LARGE`，不持久化部分成功结果。两者原样保留搜索结果的 `citation_id`，不返回 `resource_refs`，真实 URL、搜索结果摘要、网页正文、失败与 usage 沿用普通工具结果/工具观测、列式编码和事件审计。模型正文只逐字回显 `[cite:真实ID]`，例如 `[cite:abc123-1]`，前端从当前轮次工具结果建立来源注册表并渲染行内编号链接；原始 assistant 事件不被改写。

每个账号的聊天显示偏好、联网开关、当前服务、两家各自的 API 地址和密文凭证与模型配置共同保存在 `settings.db`；联网 master key 与模型 Provider master key 仍然分离。适配器在保存的 API 地址后追加对应服务路径；20/45 秒超时、8 MiB 响应上限、安全搜索/内容审核及错误归一化都位于适配器和 Service 边界。当前服务失败不重试、不切换另一家。

## 存储与安全

`DATA_ROOT` 指定数据根。当前数据根、数据库文件、密钥、权限和 Schema 生命周期见[本地存储](../docs/当前执行/运维/本地存储.md)；SQLite 表、列、主外键、索引和约束见[数据库结构](../docs/当前执行/运维/数据库结构.md)；JSONL header、事件行、写入和恢复见[会话 JSONL 格式](../docs/当前执行/运维/会话JSONL格式.md)。账号私有目录固定使用不可变 `account_id`，模型与联网凭证分别以 `account_id + provider_id` 组成 AAD；SQLite、JSONL、附件与密钥文件使用私有文件权限。浏览器认证使用 HttpOnly Cookie，Provider 密钥使用当前密封格式。

空数据根会创建当前最终 Schema。已有非空数据库会按[本地存储约定](../docs/当前执行/运维/本地存储.md)先只读验证；不满足当前校验边界时返回 `UNSUPPORTED_SCHEMA`，不会修改文件。

## 开发

```bash
uv sync
uv run pytest -q
uv run uvicorn backend.app.main:create_app --factory --reload
```

## 成员与健康档案授权

`account_id` 统一承担账号主键、操作者身份和账号私有目录作用域；`account` 是可修改的用户标识，服务于登录、界面标识和授权接收方查找；`account_name` 是便于人识别的账号名称。认证由 API、`AuthService` 和 `AuthRepository` 三层协作，业务路由从公共依赖取得唯一的 `CurrentUser` 身份。一个账号可以从零位可访问成员开始，并可创建成员或获授其健康档案访问权。医疗资料与原件保存在健康档案所有者账号目录，并以 `member_id` 关联所属成员；成员名称使用 `member_name`，聊天、附件、收藏和配置归操作者。聊天创建时固定关联一位成员，也可以保持不关联成员，运行时根据固定成员及实时健康档案权限提供报告能力。授权失效后历史会话保留为只读记录，当前工作区进入替代默认成员或不关联成员的新聊天。报告接口统一以 `member_id` 确定成员作用域。当前完整契约见 [成员与健康档案授权](../docs/当前执行/领域/成员与健康档案授权.md)。

## 收藏与模型配置

收藏由 `FavoriteService`、`FavoriteRepository` 提供业务操作和事务；模型配置由 `ModelSettingsService`、`ModelProviderRepository` 提供。模型运行共用配置 Repository 和模型响应投影。对应 API 负责认证依赖、请求及响应，不直接执行 SQL。会话附件能力查询、上传和发送共用后端能力检查；前端消费查询结果。
