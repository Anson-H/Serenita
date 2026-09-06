# 前端职责边界重构实施与验收

日期：2026-09-07。F01—F16 的代码实施与本次验收已完成，现有测试及新增回归用例均通过，未发现尚未解决的新增回归。

基线为审查时的实际工作区，包含用户已有未提交修改，不以 Git HEAD 代替基线。本次保留这些修改，并在其上实施。没有新增依赖、备份、数据迁移或兼容实现。用户随后明确授权修复真实页面验收发现的一项后端成员偏好事务问题，范围和证据见下文。

## 最终职责与调用方

以下文件均相对于 `frontend/src/`。模块只拥有表中所述职责，操作工厂使用原控制器中的状态、请求作用域及队列引用。

| 项目 | 最终所有者及调用变化 | 验收证据 |
| --- | --- | --- |
| F01 工作台归属 | `app/workspace/WorkspacePage`、`WorkspaceRouteContent`、`useWorkspacePageModel` 组合路由、成员、会话、报告、收藏和设置。原会话目录入口已移除，全部引用同步更新 | 全部浏览器测试、工作区深链接及宽窄报告导航、构建 |
| F02 会话状态 | `useConversationDraftState`、`useConversationDataState`、`useConversationEditingState`、`useConversationElements` 在原工作台挂载位置提供状态。`conversationIndex` 统一列表回读和本地更新；队列、侧栏集合操作、流订阅分开。会话视图的状态接口收窄为实际消费字段 | 列表晚响应与重命名、较晚读取胜出、页面/认证失效；生命周期、后台连续执行、断流恢复、停止及正文保留用例 |
| F03 设置 | `SettingsShell` 组合账号、提供方、模型、默认用途、联网、偏好和导航操作模块。原外壳仍持有串行任务、请求序号和草稿引用 | 提供方保存期间继续输入、密钥迟到响应、账号同步和联网配置用例 |
| F04 模型编辑 | `modelSettingsDraft` 负责转换、签名和补丁；`modelEditorActions` 负责原保存队列、等待、删除和识别；`ModelSettingsEditor` 持有原队列生命周期并渲染能力编辑；`RemoteModelPicker` 渲染远程模型选择 | 合并连续输入、失败保留最新草稿、按最后成功值重试、删除等待；模型详情和短视口弹窗页面用例 |
| F05 模型目录 | 工作台持有一份 `ModelCatalog`，设置接收目录及更新入口。保存、识别和删除后的一次模型/默认用途读取直接发布，去掉通知消费者后再次读取的路径 | 页面断言一次 PATCH、一次模型读取、一次默认用途读取；切回聊天显示新模型名称，未增加第二次读取 |
| F06 检验目录 | `LabDictionaryEditor` 保留选择、数据和两类队列；`labItemEditorActions`、`labCategoryEditorActions` 分别保存指标和分类；`LabDictionaryList`、`LabDictionaryDetail`、`LabItemFields`、`LabCategoryFields`、`LabDictionaryDialogs` 分别渲染 | 分类重命名后按新目标继续保存、冲突时使用最新 revision、切换详情不改写另一草稿；目录批量删除及失败处理用例 |
| F07 报告操作 | `useReportWorkspace` 保留查询选择和作用域；修改、集合、原件、解读、收藏由各自操作模块提供。修改共享成功结果应用和失败回读，权限与互斥条件留在每个操作中 | A→B→A 迟到保存隔离、一次详情/列表/资源刷新、原始失败不被回读失败覆盖；真实页面增改删 |
| F08 报告详情 | `ReportInlineField`、`ReportStructuredFields`、`ReportLabResults`、`ReportSources`、`ReportAnalysisEditor` 分别负责字段、结构、指标、原件与解读结果编辑；原件缩略图显式接收所属报告的 `member_id` | 五类报告真实表单和字段编辑；只读成员、跨成员同报告标识、补充原件、原件预览与响应式用例 |
| F09 报告上传 | `useReportUpload` 接收已有上传与标准消息提交能力，保存成功资源、剩余文件及重试信息；路由只组合视图 | 部分失败后只重传剩余文件；成功资源只提交一次；离开再返回后旧批次不发起消息 |
| F10 执行记录 | `useExecutionDisclosure`、`ExecutionDuration`、`ExecutionRecordPrimitives`、`ExecutionRecordDetails` 分别提供折叠、计时及记录视图；总组件继续使用原投影筛选与组合 | 会话内容、上下文压缩分层、流终态、正文不回退及几何用例；本地运行时导入无环 |
| F11 滚动 | `conversationScrollGeometry` 提供原几何与手势计算；`conversationInputListeners` 安装/清理监听器；`useConversationScrollController` 保留唯一状态机、操作令牌、动画及 effect 次序 | Chromium/WebKit：异步增长、暂停阅读、历史插入、来源定位、返回底部、焦点转移、超时重试、千轮会话 |
| F12 资源预览 | `useContextInputPreview` 负责测量和固定状态；`ContextInputPreview` 保留内容渲染、DOM 与事件阶段；`ResourceChips` 组合资源类型 | 键盘、悬停/固定、外部关闭、短视口、缩放、附件与注释交互用例 |
| F13 样式 | `sidebar.css` 集中侧栏；设置/报告响应式规则归入各自样式文件；共享弹窗使用明确的通用语义类；最终状态仍由最后加载的 `interaction-states.css` 管理 | 侧栏关键计算样式前后一致；88 项浏览器测试，包括 300×160 设置弹窗、报告宽窄布局和两种浏览器滚动/覆盖层 |
| F14 类型与展示 | API 类型按账号、会话、偏好、模型、联网、收藏分域；`memberPresentation` 负责成员文案；`accountPreferences` 和 `modelConfiguration` 提供共享设置；Markdown 包装通过类型导入复用渲染器输入 | API 身份/错误/事件用例、成员展示、账号偏好测试；Markdown 与工作区懒加载分块保留 |
| F15 无效接口 | 删除未消费的 `responseError`、`ReportAnalysisResponse`、报告控制器 `setConversations` 参数、`dismissLatestAnalysis`、`cachedBlob`、`switchView`、`changeScenario`、不可达 `activeView` 及其类型/传参。实际健康档案路由与 `activeScenario` 保留 | 重新核对引用、TypeScript 编译、健康档案导航、草稿恢复、原件和解读相关测试 |
| F16 收藏标签 | `FavoriteTagCapsules` 渲染标签；`favoriteTagActions` 管草稿和保存。列表与详情仍消费原收藏控制器中的同一份状态和队列 | 迟到详情隔离、同收藏串行保存且不覆盖新输入、桌面/手机报告快照；真实后端来源删除后快照仍可读 |

所有 HTTP 路径、参数、返回字段、SSE 事件、身份头和错误结构保持现行契约。普通报告修改仍通过普通 API，上传及解读入口仍发送标准会话消息；没有新增页面业务编排或固定工具顺序。

## 验证结果

| 检查 | 改动前基线 | 最终结果 |
| --- | --- | --- |
| `npm test` | 111 通过 | 118 通过 |
| `npm run test:browser` | 85 通过 | 88 通过，包含 Chromium 和针对布局/滚动的 WebKit 用例 |
| `npm run test:integration` | 2 通过 | 4 通过，使用独立临时数据根、真实后端和真实页面 |
| `npm run build` | 通过 | 通过，9 个 JavaScript 分块均不超过 500000 字节；入口约 475.98 kB |
| 后端相关回归 | 新并发用例先复现锁冲突 | `test_member_defaults`、`test_members`、`test_member_execution`、`test_backend_boundaries` 共 46 通过 |
| 静态边界 | 审查基线无本地导入环 | 202 个源模块中未发现运行时本地导入环；差异空白检查通过 |

原有测试断言未放宽、有效用例未删除。会话生命周期测试夹具补入新的统一列表刷新接口；移除不可达视图状态时同步删除夹具中该无效参数。新增页面测试调试期间修正了不符合实际界面的入口名称、目录路径和模型名称断言位置，最终使用实际可访问名称和页面入口验收。

### 功能矩阵对应

| 范围 | 主要可执行证据 |
| --- | --- |
| 账号、身份、成员与授权 | `api-boundaries.test.mjs`、`browser/auth-session-sync.spec.ts`、`browser/members.spec.ts`、`browser/hook-state.spec.ts`、后端成员相关测试 |
| 导航、会话执行、草稿及附件 | `conversation-stream.test.mjs`、`conversation-presentation.test.mjs`、`attachments.test.mjs`、`browser/conversation-upload-retry.spec.ts`、成员连续性用例、生命周期与上传重试 hook 用例 |
| 报告事实、原件和资源状态 | `report-state-refresh.test.mjs`、`refactor-actions.test.mjs`、`browser/members.spec.ts`、`integration/report-pages.spec.ts`；五类报告均从页面创建、编辑与删除，普通操作的会话写入数为 0 |
| 报告解读与执行展示 | 流式事件、上下文压缩层、报告资源刷新、报告输入区与附件页面用例；正常提交仍由实际 Harness 在隔离联调中执行 |
| 收藏与快照 | `browser/favorite-state.spec.ts`、`api-boundaries.test.mjs`、`integration/boundaries.spec.ts` |
| 模型、提供方、联网和检验目录 | `browser/settings-state.spec.ts`、`lab-catalog-actions.test.mjs`、`refactor-actions.test.mjs`、隔离联调和下列独立真实服务检查 |
| 偏好、键盘、触屏、输入法和几何 | `conversation-preferences.test.mjs`、`input-method.test.mjs`、`browser/select-popover.spec.ts`、`browser/conversation-overlay-geometry.spec.ts`、`browser/conversation-scroll-controller.spec.ts`、菜单及短视口弹窗用例 |
| 传输和服务 | `api-boundaries.test.mjs`、`conversation-stream.test.mjs`、模型目录请求计数页面用例、真实后端联调、真实服务结果文件 |

矩阵列出实际执行的自动化证据。不同页面的全部组合、所有外部模型的所有能力档位，以及任意网络时序不可能由这些有限测试穷尽；本记录不据此承诺绝对零缺陷。

## 授权追加的后端事务修复

新增真实页面验收发现：侧栏选择成员调用 `/api/account-settings/member-preferences`，在并发配置写入时返回 500，异常为 `sqlite3.OperationalError: database is locked`。问题定位于本次原先未修改的 `MemberRepository.save_preferences`。用户明确同意增加这一项后端修复。

原实现先在认证库执行 `BEGIN IMMEDIATE`，再附加配置库；配置库的读取随后需要升级写锁，遇到并发配置写入会失败。修复将附加配置库放在事务开始之前，使两库在读取前共同获得写入保留锁。授权验证、偏好保存和访问序号更新仍在同一事务内，未增加重试、迁移或协议回退。

`test_member_preference_waits_for_concurrent_configuration_write` 使用真实 SQLite 连接与并发写入先复现原错误，修复后验证等待并成功保存。侧栏成员选择的页面测试保留并通过，未绕过失败接口。

相关测试后，已通过现有 `uv run` / `uvicorn --reload` 守护方式重启实际开发后端。管理进程为 75832，工作进程由 4403 更换为 5046，继续使用 `127.0.0.1:8000` 和原 `serenita_files` 数据根。重启后开发账号登录、认证、成员、模型及默认用途读取均返回 200。

## 真实服务与配置保留

独立结果见 [真实服务验收记录](frontend-real-service-acceptance.json)。使用当前开发配置执行最小、非破坏性任务，测试文本和图片均为生成的验收输入：

- 阿里云百炼：四项默认用途，包括流式聊天和视觉读取，通过。
- DeepSeek：当前已配置的三项模型最小调用，通过。
- OpenRouter：当前已配置模型最小调用，通过。
- Exa：搜索与网页正文读取，通过。
- Tavily：当前无密钥，真实调用不适用，未虚构配置。
- 账号身份、密码散列、完整配置内容及配套主密钥的前后指纹一致。未创建这些数据的备份或副本。

隔离后端联调中的外部服务仍使用测试适配器；上述真实服务检查独立执行，两类证据分别记录。真实服务通过只证明本次调用和当前配置可用，不替代全部模型能力组合的验收。
