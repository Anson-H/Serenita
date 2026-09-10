# Serenita 后端

FastAPI 分层单体。产品范围、业务规则与传输协议从[当前执行文档](../docs/当前执行/README.md)进入，本页负责开发入口和验证方法。

## 启动

在项目根目录执行：

```bash
uv sync
uv run uvicorn backend.app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

`create_app(paths=...)` 可显式指定数据根；命令行工厂使用 `DATA_ROOT` 或项目默认目录。数据目录、账号配置、密钥与 Schema 生命周期见[本地存储](../docs/当前执行/运维/本地存储.md)。

PDF 检查、页面渲染和缩略图依赖 Poppler 的 `pdfinfo`、`pdftoppm`。真实后端守护进程的 PATH 也必须包含它们。

## 更新生效

先检查正在监听的端口、服务管理进程及其 `DATA_ROOT`。本地默认端口为 8000，实际配置变化时以正在使用的服务为准。后端更新和相关验证完成后，通过现有守护方式退出旧后端，并在同一数据根和真实端口重新提供服务，再从前端验收。

Skill 目录、Skill Markdown、运行配置及引用文件采用进程内缓存；更新后需要重启真实后端。Python 的开发自动重载不能替代这一步。重启后验证认证会话和受影响页面；账号身份、配置库及配套加密主密钥必须继续可用。

## 模块入口

`app/` 根目录只放 `main.py` 应用入口和包声明。`main.create_app()` 创建应用，由 `application/services.py` 的 `ApplicationServices` 按同一数据根装配 Service、Repository 和后台任务。

| 目录 | 开发职责 |
| --- | --- |
| `app/api/` | HTTP 路由、认证依赖、请求与响应以及线程池边界 |
| `app/application/` | Service 装配、实时授权、领域操作和后台执行；会话协作者集中在 `conversations/` |
| `app/domain/` | 共享领域契约与纯计算，包括会话事件投影、模型能力、时间、统计和提醒规则 |
| `app/schemas/` | 领域字段与请求结构校验；药品请求标识校验集中在 `medication.py` |
| `app/core/` | 错误、时间、取消、分页等基础能力，以及按数据根隔离的进程内任务状态 |
| `app/agent_runtime/` | 通用行动循环、Skill 发现、工具参数校验和持有执行状态的请求重建 |
| `app/plugins/` | 领域 Skill、工具注册、工具参数 Schema 和资源解析入口 |
| `app/providers/` | 供应商传输、消息编码、响应解析与能力探测 |
| `app/repositories/` | 查询、事务、幂等和持久化；消费底层契约及纯投影 |
| `app/storage/` | 唯一数据库结构定义、结构检查、路径、JSONL、密钥和文件清理基础能力 |

### 会话应用模块

HTTP API 和其它应用能力通过 `app/application/conversations/service.py` 的 `ConversationService` 使用会话操作。它负责装配与公开入口，具体操作由下列模块承担；表中路径均相对于 `app/application/conversations/`。

| 文件 | 职责与主要入口 |
| --- | --- |
| `service.py` | `ConversationService`：发送、读取、取消与会话管理的公开入口，以及协作者装配 |
| `submissions.py` | `ConversationSubmissions`：提交、编辑、重新生成；`start_message_turn()` 创建可执行轮次 |
| `jobs.py` | `ConversationTurnJobs.start()`：领取轮次、启动线程与心跳，并在结束后推进队列 |
| `lifecycle.py` | `ConversationTurnLifecycle`：`execute_turn()` 执行轮次；处理取消、结束、失败、过期与恢复 |
| `execution.py` | `ConversationExecution.run()`：准备会话上下文、装配插件并进入 `AgentHarnessRuntime.execute()` |
| `access.py` | `ConversationExecutionGuard`：读取会话成员绑定，复核授权、取消与轮次状态 |
| `cancellation.py` | 统一取消文案；`interrupted_activity_specifications()` 根据持久化事件构造中断收尾记录 |
| `queue.py` | `ConversationQueue`：保存、排序、删除和提升等待输入；`ConversationQueueActions` 声明所需协作入口 |
| `queries.py` | `ConversationQueries`：读取列表、详情、轮次、资源状态与收藏来源 |
| `sessions.py` | `ConversationSessionCommands`：手工标题、置顶、分叉、批量操作与删除 |
| `events.py` | `ConversationEvents.view()` / `reader()`：共享按需事件快照；`SessionView` 定位消息与 Observation |
| `presenter.py` | `record_response()` / `message_response()`：详情与 SSE 共用的响应字段呈现 |
| `sse.py` | `ConversationSSESubscriber.stream_events()`：重放和跟随持久化事件，生成增量投影 |
| `streaming.py` | `sse_event()` 编码具名 SSE 消息；`stream_text_chunks()` 为轮次执行和 SSE 共享文本分片规则 |
| `inputs.py` | `ConversationInputs`：上传与资源授权、附件内容读取、模型能力和请求输入准备 |
| `attachment_rendering.py` | `model_file_parts()`：按模型能力把原件内容转换为输入内容片段 |
| `model_resources.py` | `ConversationModelResources.prepare()`：解析工具返回的原件引用并准备模型输入 |
| `model_calls.py` | `ModelCallRecorder`：执行模型请求，记录上下文、增量、结果与用量 |
| `request_audit.py` | `ModelRequestAudit`：从实际供应商请求生成安全审计记录与字段溯源 |
| `compaction.py` | `ConversationCompaction`：协调历史选择、摘要请求、预算和检查点提交 |
| `tool_results.py` | `ConversationToolResults.persist()`：追加工具结果，处理幂等、取消和结果保存 |
| `titles.py` | `ConversationTitleTasks`：构造标题请求并管理独立标题任务 |
| `notifications.py` | `completion_event()` / `build_types()`：生成已完成回答的通知内容及有效性投影 |

### 共享会话契约与模型能力

`app/domain/conversations/` 只处理事件与纯投影：`events.py` 定义并校验事件；`queries.py` 查询消息、等待输入、有效轮次与未结束活动；`model_history.py` 派生模型消息和已读取 Skill；`timeline.py` 派生界面时间线与增量；`titles.py` 保存标题长度、清理词表和默认值。应用、Repository 与恢复逻辑共享这些模块。

`app/domain/model_capabilities.py` 集中生成与嵌入模型的能力契约、规范化和默认用途资格判断。数据库编码归 `storage/model_codec.py`，供应商探测归 `providers/`。`core/conversation_tasks.py` 保存会话线程、锁、取消信号与持久化事件提交后的读者唤醒机制；面向用户的通知由应用层生成与投递。

### 主要调用链

- 发送消息：`api.conversations.send_message()` → `ConversationService.send_message()` → `ConversationSubmissions.send_message()` → `start_message_turn()` → `ConversationRepository.append_session_events()`。已有活动轮次时保存等待输入。
- 执行轮次：API 收到 `started` 后调用 `ConversationService.start_turn_job()` → `ConversationTurnJobs.start()` → `ConversationTurnLifecycle.execute_turn()` → `ConversationExecution.run()` → `AgentHarnessRuntime.execute()`。队列通过 `ConversationQueue.promote_next()` 提升下一项，再使用同一提交与任务入口。
- 模型与工具：Harness 调用会话提供的模型入口，经 `ModelCallRecorder.complete_chat_with_events()` 调用模型服务；工具经领域 Service → Repository 执行，结果由 `ConversationToolResults.persist()` 保存并返回行动循环。
- 详情与流：`ConversationService.get_conversation()` → `ConversationQueries.get_conversation()` → `ConversationEvents.view()`；`ConversationService.stream_events()` → `ConversationSSESubscriber.stream_events()`。两条读取路径共用领域投影和 `presenter.py`。

公开协作方法表达具体动作，组件间调用不访问彼此的私有方法。已构造组件直接绑定方法；需要延后连接的执行、失败收尾和队列入口使用具名回调，并在 Service 中集中装配。

模块依赖与运行契约见[技术架构总览](../docs/当前执行/架构/技术架构总览.md)、[职责边界](../docs/当前执行/接口/前后端职责边界.md)和[会话事件](../docs/当前执行/架构/会话事件与投影.md)。工具描述与参数更新按根目录 [AGENTS.md](../AGENTS.md) 执行。

## 验证与演示

```bash
uv run pytest -q
```

先运行更新所涉及的测试，再运行必要的跨模块回归。前后端真实边界联调由[前端验证入口](../frontend/README.md#验证)运行。只更新 Markdown 时不运行测试或校验命令。

显式演示命令：

```bash
uv run python -m backend.app.application.body_metric_demo
```

该命令通过 Service 创建“身体指标演示”成员，生成截至执行日最近 90 天的虚构测量、饮食、运动和睡眠数据，默认输出 `artifacts/body-metrics-demo.json`。相同来源身份重复执行不追加，已编辑内容保留；演示来源和备注明确标注虚构。命令不在应用启动时执行。
