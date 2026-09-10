# Serenita 前端

React + Vite 单页工作台。业务访问统一经过 `src/api/`。本页负责开发入口、模块定位和验证；产品、页面行为及视觉规则分别见[产品需求](../docs/当前执行/产品/产品需求.md)、[前端行为](../docs/当前执行/前端/行为与交互.md)和 [DESIGN](../DESIGN.md)。

## 启动

在本目录执行：

```bash
npm install
npm run dev
```

开发代理和端口以 `vite.config.ts` 为准。HTTP 与 SSE 契约见 [HTTP 接口](../docs/当前执行/接口/HTTP接口.md)，执行记录见[会话事件](../docs/当前执行/架构/会话事件与投影.md)。

## 模块入口

| 目录或模块 | 开发职责 |
| --- | --- |
| `src/api/` | HTTP、SSE、API 基址与领域类型 |
| `src/app/workspace/` | 工作区组合、当前领域加载与共享模型目录 |
| `src/components/` | 控件、列表、覆盖层、预览及焦点机制 |
| `src/features/conversations/conversationIndex.ts` | 会话分页、刷新及迟到响应处理 |
| `src/features/conversations/useConversationController.tsx` | 持有会话内部状态与操作；应用组合层使用快照、动作和视图入口 |
| `src/features/conversations/conversationDraftStore.ts` | 按草稿身份管理内容、上传任务与会话归属 |
| `src/features/modelConfiguration/useModelCatalog.ts` | 共享账号模型目录、默认用途及刷新顺序 |
| `src/features/reports/useReportWorkspace.ts` | 订阅医疗报告状态、组合查询筛选与领域操作 |
| `src/features/reports/model/` | 医疗报告状态与操作的内部实现，职责及调用入口见下表 |
| `src/features/settings/SettingsShell.tsx` | 组合账号、供应商、模型、联网控制器与通知组件 |
| `src/features/members/` | 成员授权、资料、既往史与健康档案导航 |
| `src/features/medicalLogs/` | 健康日记列表和编辑 |
| `src/features/medications/` | 药箱、计划、原件与批次 |
| `src/features/medications/medicationDraft.ts` | 药品与用药计划的明确草稿类型、可编辑字段投影及更新内容 |
| `src/features/bodyMetrics/` | 身体指标、图表、编辑与导入 |
| `src/features/bodyMetrics/useBodyMetricData.ts`、`useBodyMetricFilters.ts`、`useBodyRecordNavigation.ts` | 分别管理数据请求、筛选条件和详情导航 |
| `src/features/favorites/` | 收藏列表、快照与标签草稿 |
| `src/features/favorites/favoriteEntities.ts` | 收藏详情与标签变更共用实体，防止旧读取覆盖新保存 |
| `src/utils/resourceDraft.ts` | 单资源草稿、串行提交和响应确认 |
| `src/utils/useResourceAutosave.ts` | 分组自动保存、组合输入和导航等待 |
| `src/utils/useAutosaveResource.ts` | 药品、批次和健康日记共享草稿保存、删除等待及失败恢复 |
| `src/components/ScrollRegion.tsx` | 公共滚动容器与显式滚动引用 |
| `src/features/conversations/useAttachmentTask.ts` | 识别附件上传、会话提交与失败恢复 |
| `src/styles/` | Token、共享设计样式、内容样式和页面布局 |

具体状态所有者与依赖见[前后端职责边界](../docs/当前执行/接口/前后端职责边界.md)。共享数值只在 `tokens.css` 定义；页面样式只处理所属布局。控件更新先从共享组件与其样式入口排查。

## 医疗报告工作区

审查页面从 `src/features/reports/ReportWorkspacePanel.tsx` 进入，它组合列表、详情和手工创建组件。审查状态与操作从 `src/features/reports/useReportWorkspace.ts` 进入，它由 `useConversationController.tsx` 创建，订阅 `model/` 中的只读快照，并将操作交给页面。`model/` 存放前端状态与操作实现。

| `src/features/reports/model/` 文件 | 职责与主要调用 |
| --- | --- |
| `detail.ts` | `ReportDetailState` 持有医疗报告详情、选择及显示状态；`open`、`refresh` 读取详情，`apply` 检查医疗报告身份与读取顺序，`clear` 使关联操作失效 |
| `mutations.ts` | `ReportMutationActions` 管理字段、检验指标、解读结果和来源编辑；字段保存经过串行队列，更新结果通过 `detail.apply` 发布 |
| `sources.ts` | `ReportSourceActions` 读取来源预览并定义预览数据类型；`openSourceFile` 管理读取请求，`clearSourcePreview` 释放对象 URL，并响应详情选择失效 |
| `analysis.ts` | `reportAnalysisPrompt` 构建解读任务文本；`ReportAnalysisActions` 提交开始解读与重新解读的会话任务，管理提交状态、重试目标和会话导航 |
| `collection.ts` | `ReportCollectionActions` 执行手工创建、单条及批量删除，并通过详情公开操作更新选择 |
| `favorites.ts` | `createReportFavoriteActions` 执行收藏与取消收藏，更新账号收藏列表及操作反馈 |
| `conversationRefresh.ts` | `ReportStateRefresher` 合并医疗报告资源的刷新范围，只更新对应会话中的资源状态，保留会话其它内容 |
| `store.ts` | `ReportStore` 提供只读快照与订阅接口，状态由所属控制器发布 |

调用顺序按用户操作进入：页面通过 `useReportWorkspace` 提供的操作调用 `model/`，控制器经 `src/api/` 发起请求，结果回到所属状态，再由订阅更新界面。医疗报告上传从 `useReportUpload.ts` 进入并复用会话附件提交能力；开始解读与重新解读由 `model/analysis.ts` 提交给会话 Harness。手工创建、字段保存和删除直接调用 HTTP API。

`reportContext.ts` 与 `reportPresentation.ts` 是会话界面也会使用的共享函数，保留在医疗报告根目录；`reportUploadValidation.ts` 供上传入口、表单和来源编辑共用。页面组件和其它功能通过工作区入口或这些共享函数访问医疗报告能力。

## 验证

```bash
npm test
npx playwright install chromium webkit
npm run test:browser
npm run test:integration
npm run build
```

单元测试验证纯函数、状态变化、并发和组件输出。浏览器测试先检查 TypeScript 类型，再启动 4175 端口服务，通过拦截业务 API 验证真实交互；失败截图与追踪保存在忽略提交的 `test-results/`。Chromium 覆盖应用流程，WebKit 复核浏览器差异明显的布局与滚动行为。macOS WebKit 测试通过进程参数启用完整键盘导航。

集成测试启动 4176 端口前端、8186 端口真实后端和独立临时数据根，结束时删除测试数据；认证、领域数据、附件、Harness、HTTP 与 SSE 使用实际实现，外部模型和联网响应使用测试适配器。普通页面 CRUD 应保持直接操作路径。真实供应商调用证据须单独记录，不能以测试适配器结果代替。

共享界面更新验证受影响流程；只有行为在断点或浏览器间存在分支时才扩大矩阵。只更新 Markdown 时不运行测试或校验命令。
