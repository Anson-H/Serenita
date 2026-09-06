# 后端封装改进实施与验收记录

状态：B01–B16 已实施，完整自动化回归与已配置真实服务验收通过。实际服务验收日期：2026-09-06；记录整理日期：2026-09-07（Asia/Shanghai）。

本记录对应[后端边界审查计划](../backend-boundary-review-plan.md)。结论依据下列行为测试、事务故障注入及真实调用结果；测试覆盖范围外的未来变更仍需要重新验证。

## 基线与最终回归

| 检查 | 实施前基线 | 最终结果 |
| --- | --- | --- |
| 后端完整测试 | 1007 项、13 项子测试通过 | 1017 项、13 项子测试通过，67.23 秒 |
| 前端单元测试 | 111 项通过 | 111 项通过 |
| 前端生产构建 | 成功 | 成功，9 个分块，均未超过 500000 字节 |
| 浏览器测试 | 85 项通过 | 85 项通过 |
| 前后端联调 | 2 项通过 | 2 项通过 |

后端命令：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider`。前端在 `frontend` 中分别运行 `npm test`、`npm run build`、`npm run test:browser`、`npm run test:integration`。基线没有失败，最终上述检查没有失败。业务写入使用隔离数据根及生成的测试数据。

## B01–B16 关闭记录

下表中的模块路径相对 `backend/app`，测试路径相对 `tests`。

| 项目 | 状态 | 最终职责与保持条件 | 主要验证入口 |
| --- | --- | --- | --- |
| B01 | 已关闭 | `application/conversation_sse.py`、`conversation_titles.py`、`conversation_jobs.py`、`conversation_queue.py` 分别管理订阅、标题、轮次任务和队列；同数据根共享会话锁、线程、取消信号及事件通知 | `test_conversation_turn_start_concurrency.py`、`test_runtime_cancellation.py`、`test_conversation_list_actions.py`、`test_member_execution.py` |
| B02 | 已关闭 | Harness 公开请求重建；模型网关公开传输请求准备；`conversation_compaction.py`、`model_request_audit.py`、`model_call_recorder.py` 分离压缩、审计和调用记录。实际发送与脱敏审计使用同一次准备的请求 | 四组压缩测试及 `test_event_harness.py` |
| B03 | 已关闭 | `repositories/conversation_index.py`、`turn_index.py`、`conversation_attachments.py` 分离索引与附件生命周期；会话 Repository 保留 JSONL、索引提交和恢复的协调入口 | 事件持久化、分支、附件清理及命名测试 |
| B04 | 已关闭 | `model_history.py`、`conversation_timeline.py`、`application/conversation_presenter.py` 分离模型历史、唯一时间线投影和 HTTP/SSE 呈现；原投影文件已删除，调用者直接更新 | `test_event_harness.py` 中逐个事件前缀的增量与完整投影比较；压缩、分支及注释测试 |
| B05 | 已关闭 | `report_validation.py`、`report_presenter.py`、`report_thumbnail.py`、`report_source_store.py` 承担校验、呈现、缩略图和来源生命周期；ReportService 保留授权及领域用例入口 | 报告 Service、API、来源清理及附件能力测试 |
| B06 | 已关闭 | `repositories/lab_catalog.py` 和 `report_facts.py` 分别拥有目录及报告事实 SQL，共享显式 `ReportTransaction`；联动、过期标记、空报告删除及文件清理任务在原事务内完成 | 目录设置、报告 Service；新增目录联动失败测试核对同一事务、全部原数据及清理任务 |
| B07 | 已关闭 | 报告、会话、模型表定义归入对应 `storage/*_database.py`；`storage/model_codec.py` 负责行编码和解码。唯一表定义及物理结构保持 | Schema 契约、存储路径及模型配置测试 |
| B08 | 已关闭 | 会话与收藏提供成员引用能力；成员协调器传入原连接和附加数据库别名执行解除关联；运行中断仍由成员服务协调 | 成员及成员执行测试；新增已解除引用后故障注入，验证附加数据库全部撤销未提交变更 |
| B09 | 已关闭 | `ApplicationServices` 统一装配；路径向下传递；成员作用域不可变且每次操作实时复核；生命周期锁重入按数据根区分；会话任务及通知按数据根共享 | 双根账号、报告、配置、主密钥、授权与嵌套锁测试；成员运行撤权测试 |
| B10 | 已关闭 | Provider 组合 `transport.py`、`message_codec.py`、`responses.py`、`errors.py` 和 `capability_probe.py`；供应商保留协议差异；探测管理器持有取消信号，防止旧任务影响替代任务 | Provider 传输、能力、溢出及模型 API 测试；三家真实服务调用 |
| B11 | 已关闭 | 模型配置 Repository 使用具名参数，内部完成 SQL 参数排序及存储编码；Service 保留业务更新语义 | 模型 API、密钥及能力归一化测试 |
| B12 | 已关闭 | 报告插件注册负责组装，可信工具观测解析、资源适配与领域调用分离；显式接口替代宽泛属性转发，可信输入由服务端绑定 | 报告工具契约、报告 Service 及成员执行测试 |
| B13 | 已关闭 | 报告、成员、收藏领域异常归入 `core/*_errors.py`；Repository 只分类已知约束冲突，未知数据库错误继续传播 | 收藏冲突精确分类新增用例及报告、目录、成员 API 测试 |
| B14 | 已关闭 | 两种传输共享流行解析器，工具共享逻辑分页构造器；供应商传输、报告分页大小、资源引用效果保持 | Provider 传输、报告工具契约及联网测试 |
| B15 | 已关闭 | `session_activity.py` 提供公共活动状态归约；`conversation_cancellation.py` 与 `storage/session_recovery.py` 分别选择运行取消及日志修复策略 | 运行取消、事件 Harness 及事件持久化测试 |
| B16 | 已关闭 | 删除确认无调用的辅助入口、ReportService 无用途模型依赖及被替代实现；测试调用更新到实际能力入口，原行为断言保留 | 完整后端及前端回归 |

## 新增风险验证与故障处理

[test_backend_boundaries.py](../../tests/test_backend_boundaries.py) 覆盖本次拆分引入的关键风险：

- 只把明确的收藏来源唯一约束识别为领域冲突；其它 SQLite 完整性错误继续传播。
- 同进程两套数据根使用相同账号标识时，报告、配置、授权和主密钥仍隔离；嵌套操作分别取得对应数据根的生命周期锁。
- 探测取消按数据根隔离；旧探测完成不能移除新探测的取消信号。
- 分类目录联动报告事实后注入失败，分别覆盖保留报告及删除最后指标的情况；验证同一事务对象、目录、报告事实、解读结果、来源文件与清理任务均符合事务撤销结果。
- 成员删除在会话、收藏解除关联后注入失败，验证成员、报告及所有附加数据库引用保持原值。

阶段测试曾暴露移动后入口、组件依赖注入和导入问题，已修复调用者并重新运行相关测试及最终完整回归。没有通过删除业务断言或捕获未知异常来掩盖失败。真实验收脚本首次启动时，本地 HTTP 客户端读取系统 SOCKS 代理配置，因缺少 socksio 而在网络请求前失败；脚本改为对本地地址禁用环境代理后完成验收。产品 Provider 的代理、重试和取消行为由原行为测试验证。

## 全产品验收矩阵

| 范围 | 验收证据 | 结果 |
| --- | --- | --- |
| 认证与账号 | `test_auth_api.py`、`test_storage_paths.py`；真实 admin 登录及会话接口 | 通过 |
| 成员与授权 | `test_members.py`、`test_member_defaults.py`、`test_member_execution.py`；双根与跨库故障注入；浏览器成员用例 | 通过 |
| 会话用例 | 并发发送、队列接续与重排、取消、编辑、重新生成、分支、置顶、删除、标题竞争及列表测试 | 通过 |
| Harness | `test_agent_runtime.py`、`test_native_tool_protocol.py`、`test_report_tool_contract.py`；动态技能、授权工具、调用保护及失败工具观测 | 通过 |
| 模型输入与压缩 | `test_compaction_layers.py`、`test_compaction_projection.py`、`test_context_compaction.py`、`test_runtime_compaction.py`、`test_event_harness.py`、`test_provider_context_overflow.py`；输入追溯、脱敏、工具结果预算及已执行结果审计 | 通过 |
| SSE 与事件 | 增量和完整投影比较、重连、终态、部分内容、JSONL 条件追加和恢复测试 | 通过 |
| 附件与注释 | `test_attachment_capabilities.py`、附件命名与清理、分支、资源预览及注释选区测试；浏览器上传重试 | 通过 |
| 五类医疗报告 | `test_report_api.py`、`test_report_service.py`、`test_report_tool_contract.py`、`test_report_source_cleanup.py`；联调结构化字段导出覆盖。含手工 CRUD、导入、查询、来源关联、合并、指标增删、重分类、报告解读和解读结果编辑 | 通过 |
| 检验指标分类目录 | `test_lab_dictionary_settings.py`、报告联动、授权边界及事务中途失败测试 | 通过 |
| 收藏 | `test_report_favorites.py`、成员执行与收藏浏览器测试；真实列表读取 | 通过 |
| 模型设置与传输 | 模型 API、密钥、能力识别、代理、首字节前取消、流中取消、模型删除与探测取消测试；真实已保存模型调用 | 通过 |
| 联网 | `test_web_access.py` 覆盖 Exa、Tavily 模拟适配器、分页、引用、凭证隔离和失败行为；真实 Exa 搜索与正文 | 通过；Tavily 真实调用不适用 |
| 存储与通用能力 | `test_database_schema_contract.py`、`test_storage_paths.py`、`test_provider_secrets.py`、`test_local_time_contract.py`、`test_tabular_json.py` | 通过 |
| 前后端组合 | 前端单元 111 项、浏览器 85 项、真实 HTTP/数据库/Harness 联调 2 项及生产构建 | 通过 |

## 真实服务验收

实际管理方式是 `gui/501/com.serenita.backend` launchd 作业，工作目录为项目根，数据根为 `/Users/anson/Documents/Employment/Serenita/serenita_files`，监听 `127.0.0.1:8000`。每批后端修改及相关测试后均通过原管理方式重启。最终完整回归后再次执行 `launchctl kickstart -k`，随后核对监听与 HTTP 响应；交付复核时父进程 PID 为 75832、工作进程 PID 为 76404，`/api/auth/session` 返回 200。工作进程由现有 uvicorn reload 机制管理。

真实调用结果见 [real-service-acceptance.json](real-service-acceptance.json)，执行入口为 [verify_backend_services.py](verify_backend_services.py)。真实业务数据只读验收，外部模型输入为生成的短文本或项目内置测试图片。

| 验收 | 结果 |
| --- | --- |
| 开发账号登录、会话、成员、收藏、模型服务、模型清单、默认用途、联网配置读取 | 全部通过，8 个读取接口返回 200 |
| 四类默认用途 chat、compact、title、vision_parse | 均使用当前保存的 `aliyun_bailian:qwen3.8-flash`，全部通过；chat 验证流式调用，vision_parse 携带图片 |
| DeepSeek 已保存模型 | `deepseek-v4-flash`、`deepseek-v4-flash-vision-exp`、`deepseek-v4-pro` 全部通过；视觉模型携带图片 |
| OpenRouter 已保存模型 | `tencent/hy4-preview` 调用通过 |
| Exa 搜索 | 返回 10 项搜索结果，通过 |
| Exa 网页正文 | 读取 WHO 官方网页，返回 867 字符并保持搜索引用标识，通过 |
| Tavily | 未配置凭证；真实验收不适用，模拟适配器测试通过 |
| 请求次数 | 8 次模型请求、Exa 搜索和正文各 1 次，共 10 次；每个模型验收任务均只发送 1 次请求 |
| 配置保留 | 真实验收前后账号标识、账号名、密码哈希、完整配置库逻辑内容及两份配套主密钥的内存指纹一致 |

JSON 只记录必要的服务标识、状态、用量和请求计数，不含密钥、Cookie、模型正文或用户业务内容。没有新增数据迁移、旧协议回退、备份或回滚副本。

## 当前文档与交付范围

已同步 `backend/README.md`、`docs/当前执行/架构/技术架构总览.md`、`docs/当前执行/架构/会话事件与投影.md`、`docs/当前执行/领域/医疗报告.md`、`docs/当前执行/运维/本地存储.md`。文档管理规则与未来愿景保留。

现行 HTTP、模型可见工具参数结构与描述、技能授权、数据库物理结构、JSONL 格式和模型自主行动边界继续由现有契约及对应测试验证。工作区原有修改保留，交付未提交 Git。额外执行的 `git diff --check` 提示工作区三个文件存在末尾空行：`agent_runtime/events.py`、`plugins/registry.py` 和前端 `streamingMessages.ts`；本次未为消除此类提示改写这些文件，该提示不影响上述测试和真实服务结果。
