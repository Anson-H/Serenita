# Serenita 前端

React + Vite 单页工作台，承载认证、会话、报告、收藏和设置。业务访问统一经过 `src/api/`，不直接读写业务数据库或调用模型服务。

## 开发入口

在本目录执行：

```bash
npm install
npm run dev
```

开发代理和端口以 `vite.config.ts` 为准。产品范围见 [产品契约](../docs/当前执行/产品/产品需求.md)，视觉规范见 [设计语言](../DESIGN.md)，页面交互见 [前端行为文档](../docs/当前执行/前端/行为与交互.md)，接口和执行记录见 [HTTP API](../docs/当前执行/接口/HTTP接口.md) 与 [会话事件](../docs/当前执行/架构/会话事件与投影.md)。

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `src/api/` | HTTP、SSE 与领域类型 |
| `src/app/` | 路由、工作区外壳与响应式导航；`workspace/` 组合全部工作区并连接领域接口 |
| `src/components/` | 列表、控件、菜单、标题栏及焦点机制 |
| `src/features/` | auth、members、conversations、reports、favorites、settings 的领域视图与行为；accountPreferences、modelConfiguration 提供共享配置 |
| `src/styles/` | Token、基础继承、共享设计样式、内容样式、页面布局 |
| `src/utils/` | 可独立验证的通用计算与事件边界 |
| `tests/` | 可观察行为测试；`fixtures/` 只承载需要真实 DOM 几何的会话测试页面 |

共享数值仅在 `tokens.css` 定义；`base.css` 管元素重置、继承、滚动条与全局可访问性；`design-language.css` 和其导入的 `controls.css` 管容器、条目与控件；最后加载的 `interaction-states.css` 集中管理状态优先级；`components.css` 管 Markdown 等内容。页面样式不重新规定共享外观。

侧栏规则集中在 `sidebar.css`；设置和报告的响应式规则分别由 `settings-responsive.css`、`reports-responsive.css` 管理，公共断点留在 `responsive.css`。共享弹窗通过 `dialog-viewport-backdrop`、`dialog-viewport-surface` 和 `dialog-title-ellipsis` 接入视口及标题约束；内容类继续负责各页面布局。

## 状态与操作的所有者

- `app/workspace` 保持原工作台挂载位置，组合草稿、会话数据、编辑、模型目录和布局。`conversationIndex` 是会话列表刷新与本地更新的唯一入口；请求序号阻止旧列表响应覆盖新标题或更晚的读取。详情完整读取、权限更新、报告资源刷新和流式正文分别处理。
- `SettingsShell` 保留提供方队列、请求序号、密钥草稿和各域状态的生命周期，组合账号、提供方、模型、默认用途、联网及导航操作。领域操作工厂接收明确依赖，不创建另一份状态。模型目录由工作台持有；设置保存后把一次读取的模型与默认用途完整发布给工作台，聊天与设置消费同一目录。
- `ModelSettingsEditor` 持有模型队列及草稿引用，`modelEditorActions` 负责提交、合并、等待、删除与识别，`modelSettingsDraft` 负责转换和补丁。`RemoteModelPicker` 只渲染选择界面。`LabDictionaryEditor` 持有选择和两类独立保存队列；列表、指标字段、分类字段、详情布局与对话框各自渲染，切换详情不重建队列。
- `useReportWorkspace` 负责报告查询、选择与作用域；修改、集合、原件、收藏和解读操作分别封装。`reportMutationActions` 共享成功结果应用与失败回读，具体操作保留各自的权限和互斥条件。详情按内联字段、结构化内容、指标表、原件和解读结果编辑组合，原件身份来自所属报告。
- `useReportUpload` 接收附件上传与标准消息提交能力，保存成功资源及剩余批次；路由只组合上传状态和重试入口。普通报告操作仍使用普通 API。
- 收藏标签视图和保存操作分别由 `FavoriteTagCapsules`、`favoriteTagActions` 提供，列表与详情消费 `useFavoriteWorkspace` 中同一份草稿和保存结果。
- 执行记录的折叠、计时和记录视图各自封装。资源预览的测量和固定状态在 `useContextInputPreview`。`conversationScrollStateMachine` 定义唯一滚动状态转换，`useConversationScrollController` 持有状态并协调操作令牌、锚点、动画与 effect；`conversationScrollGeometry` 提供几何与手势计算，`conversationInputListeners` 负责监听器安装及清理。

主要代码入口：[工作台组合](src/app/workspace/useWorkspacePageModel.ts)、[会话列表](src/features/conversations/conversationIndex.ts)、[共享模型目录](src/features/modelConfiguration/modelCatalog.ts)、[设置外壳](src/features/settings/SettingsShell.tsx)、[报告控制器](src/features/reports/useReportWorkspace.ts)、[报告上传](src/features/reports/useReportUpload.ts)。跨前后端约束见[职责边界](../docs/当前执行/接口/前后端职责边界.md)。

`GroupedList` 每次使用都必须显式填写 `density="standard"`（40px）或 `density="compact"`（30px），不提供默认值，可与 `layout="plain"`、`"fields"`、`"navigation"` 独立组合。尺寸在列表内部生效，文字、图标、字段与内嵌按钮一起调整，嵌套列表按自己的格式重设尺寸，多行内容自然增高。

## 验证

```bash
npm test
npx playwright install chromium webkit
npm run test:browser
npm run test:integration
npm run build
```

`npm test` 直接执行纯函数、状态机、并发竞态和真实组件输出，不通过匹配源码字符串或 CSS 选择器证明行为。`test:browser` 先检查测试与配置的 TypeScript 类型，再自动启动独立的 4175 端口服务；Chromium 验证真实应用流程和复杂会话布局，WebKit 只复核浏览器差异明显的会话布局与滚动控制。浏览器测试拦截或阻止业务 API 请求，不操作真实账号、密码或报告。浏览器二进制只需首次安装，失败截图与追踪保存于忽略提交的 `test-results/`。

macOS 下的 WebKit 验收进程通过启动参数启用完整键盘导航，以保证 Tab 测试不依赖个人系统偏好；不会修改用户的系统或浏览器设置。相关平台行为见 [Playwright 的 macOS WebKit 说明](https://github.com/microsoft/playwright/issues/41808)。

共享界面修改优先验证受影响的真实流程；只有行为确实在断点或浏览器间分支时才增加对应矩阵，避免同一断言在无差异宽度上重复运行。只修改 Markdown 时遵守项目规则，不运行测试或校验命令。

## 成员与健康档案授权

认证会话向前端提供稳定的 `account_id`、当前用户标识 `account` 和便于人识别的账号名称 `account_name`。注册、登录、认证恢复和账号资料更新共享 `AuthenticatedSession`；资料保存后当前页面直接采用完整响应，并通知其它标签页刷新。输入框与回答显示偏好通过账号设置接口保存到 `settings.db`，因此用户标识更新或更换浏览器后继续使用同一组偏好。一个账号可以从零位可访问成员开始，并可创建成员或获授其健康档案访问权；医疗资料与原件以不可变 `member_id` 关联所属成员，成员名称使用 `member_name`，聊天、附件、收藏和配置属于操作者。聊天创建时固定关联一位成员，也可以保持不关联成员，报告能力随该成员的健康档案权限提供。授权失效后历史会话继续显示为只读记录，工作区进入替代默认成员或不关联成员的新聊天。报告请求统一携带 `member_id`。当前完整契约见 [成员与健康档案授权](../docs/当前执行/领域/成员与健康档案授权.md)。

## 前后端边界联调

`npm run test:integration` 启动 4176 端口的前端和 8186 端口的真实后端，使用独立临时数据根；结束时删除该测试数据。只有外部模型与联网响应采用测试适配器，认证、成员、报告、收藏、配置、附件、会话 Harness、HTTP 与 SSE 均使用实际实现。普通浏览器测试继续使用拦截的业务 API。附件能力来自后端接口，模型切换时只应用当前有效响应；查询失败保留草稿并提供重试。

`integration/report-pages.spec.ts` 通过真实页面录入五类报告、编辑字段和删除，并断言普通报告操作没有会话写入；检验目录仅作为测试前置数据创建。`refactor-actions.test.mjs` 验证列表晚响应、报告切换、模型队列与目录 revision 交错；`settings-state` 验证保存后请求次数、聊天目录同步和短视口弹窗。真实提供方的最小调用证据单独保存，不能用测试适配器结果替代。
