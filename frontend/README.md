# Serenita 前端

> 文档状态：当前代码说明 / 前端模块参考
>
> 当前用途：说明当前 React + Vite 前端的路由、模块边界、页面结构和运行方式。产品范围仍以 `docs/releases/v0.1.0/` 的当前执行文档为准。

## 前端概览

Serenita 前端是 React + Vite 实现的患者端 AI 健康工作台。它是一个单页应用，用同一个应用外壳承载登录、注册、主工作台、指定会话、账号设置页和我的收藏。

前端服务的是“患者在敏感健康场景中低压力地提问、保存回答、配置模型”的产品目标。界面设计偏克制、工具化、稳定：左侧负责导航和账号入口，右侧负责当前任务，浮层只用于添加模型、模型与推理强度选择、文本选区引用这类临时任务。

核心文件：

```text
frontend/
  index.html
  package.json
  vite.config.ts
  src/
    main.tsx                         React 入口，挂载 App 并引入全局样式
    App.tsx                          薄路由壳：认证门禁、认证页和工作台页分发
    styles.css                       样式入口 shim，实际样式拆在 src/styles/
    api/
      client.ts                      聚合并重新导出所有 API 域
      request.ts                     fetch 包装器，注入 token 并统一错误文案
      sessionToken.ts                localStorage token 读写与旧 key 迁移
      types.ts                       前端使用的后端响应类型
      authApi.ts                     登录、注册、会话检查、退出
      accountSettingsApi.ts          账号资料与密码
      modelProviderApi.ts            模型服务、模型列表、默认模型
      conversationApi.ts             会话、消息、流式响应、上传资源、分支路径
      favoriteApi.ts                 收藏、标签、批量取消收藏
    components/
      MarkdownContent.tsx            Markdown 渲染包装
      SecretInput.tsx                密码/API key 输入框，包含显示/隐藏按钮
      icons.tsx                      应用内图标组件
    app/
      routes.ts                      前端路径常量、chat path 解析和当前 route 识别
      useBrowserRoute.ts             History API 路由状态 hook
      useResponsiveSidebar.ts        桌面折叠、窄屏抽屉和 1000px 断点状态
      WorkspaceRouteShell.tsx        登录后共享外壳接线和侧栏 toggle 控制器
      PatientShell.tsx               登录后共享外壳结构
      Sidebar.tsx                    全局导航、场景入口、历史会话和账号设置入口
    features/
      auth/
        AuthPage.tsx                 登录/注册页
        useAuthSession.ts            登录态恢复、认证提交和退出
        validation.ts                认证表单前端校验
      conversations/
        WorkspacePage.tsx            工作台页入口，把顶层 props 接到 route content
        useWorkspacePageModel.ts     登录后工作台 hook 编排和跨模块状态组合
        WorkspaceRouteContent.tsx    登录后 route 分支和 WorkspaceRouteShell 包装
        ConversationWorkspacePanel.tsx 首页对话工作区接线和 surface prop 映射
        ConversationWorkspaceSurface.tsx 首页对话界面拼装：场景、消息、输入区和模型控件
        HomeWorkspace.tsx            首页工作区骨架
        ConversationComposer.tsx     输入区
        ConversationMessageBubble.tsx 消息气泡、编辑框和消息动作
        BranchControls.tsx           分支切换控件
        ComposerModelControl.tsx     模型与推理强度选择器
        ResourceChips.tsx            附件和引用 chip
        attachmentSupport.ts         模型附件能力判断
        branching.ts                 分支路径纯逻辑
        contextResources.ts          附件/引用展示转换
        conversationDraft.ts         发送草稿、编辑草稿和默认父节点纯逻辑
        conversationModels.ts        模型列表与默认聊天模型合并逻辑
        streamingMessages.ts         流式消息临时状态纯逻辑
        thinking.ts                  思考过程文案、时长和取消判断
        useConversationPageState.ts  工作台对话页本地状态和 DOM refs 初始化
        useConversationWorkspace.ts  会话发送、重新生成、提交草稿和会话列表刷新动作
        useConversationStreamController.ts 流式响应、停止生成和 active stream 清理
        useConversationMessageActions.ts 复制、引用选区和编辑消息动作
        useConversationBranching.ts  分支切换、分支预览和兄弟分支计算
        useConversationAttachments.ts 附件上传、进度同步、能力过滤和附件移除
        useConversationModelControl.ts 模型选择、推理模式和模型弹层状态
        useConversationLifecycle.ts 会话打开、路由恢复、删除、退出和工作台重置
        useConversationLayout.ts     对话滚动、高亮定位、输入框高度和 overlay 测量 hook
        useConversationViewState.ts  首页标题、消息索引、分支预览和附件能力派生状态
        workspaceTypes.ts            工作台局部类型与场景文案
      favorites/
        FavoritesWorkspacePanel.tsx  收藏页工作区外壳和 FavoritesWorkspace 接线
        FavoritesWorkspace.tsx       收藏页视图
        useFavoriteWorkspace.ts      收藏列表、详情、选择和标签动作 hook
        useFavoriteListAlignment.ts  收藏列表滚动条补偿和工具栏对齐 hook
        useFavoriteMessageActions.ts 对话消息收藏/取消收藏动作 hook
        favoriteState.ts             收藏详情、选择和标签本地状态纯逻辑
        favoriteTags.ts              标签颜色与展示规则
      settings/
        SettingsWorkspacePanel.tsx   设置页工作区外壳、标题栏和模型刷新接线
        SettingsShell.tsx            设置页数据编排
        SettingsView.tsx             设置页响应式界面
        settingsTypes.ts             设置页局部类型
    styles/
      index.css                      样式聚合入口
      tokens.css                     设计变量
      base.css                       reset、body、原生表单和全局 focus
      components.css                 Markdown、SecretInput、状态文本和共享按钮
      shell.css                      登录后应用外壳和侧边栏
      auth.css                       登录/注册页
      conversations.css              首页对话、消息、分支和引用
      composer.css                   底部输入区和模型选择器
      favorites.css                  收藏页
      settings.css                   设置页
      responsive.css                 1000px / 650px 响应式规则
```

`App.tsx` 现在只保留应用入口职责：读取浏览器路径、恢复登录态、选择认证页或工作台页。登录后共享外壳接线和侧栏 toggle 控制由 `src/app/WorkspaceRouteShell.tsx` 承担；`PatientShell.tsx` 和 `Sidebar.tsx` 负责外壳结构、场景入口、历史会话、辅助导航和账号设置入口。登录后工作台页入口 `features/conversations/WorkspacePage.tsx` 只接收顶层 props 并渲染 route content，跨模块状态组合集中在 `features/conversations/useWorkspacePageModel.ts`，route 分支和 `WorkspaceRouteShell` 包装集中在 `features/conversations/WorkspaceRouteContent.tsx`。首页对话页本地状态和 DOM refs 初始化拆到 `features/conversations/useConversationPageState.ts`，首页对话工作区的分组状态到 surface prop 映射由 `features/conversations/ConversationWorkspacePanel.tsx` 承担，首页对话的消息、输入区和模型控件拼装由 `features/conversations/ConversationWorkspaceSurface.tsx` 承担。首页标题、消息索引、分支预览截断和附件能力等派生值拆到 `features/conversations/useConversationViewState.ts`。会话打开、URL 恢复、删除、退出和工作台重置拆到 `features/conversations/useConversationLifecycle.ts`，会话发送、重新生成、提交草稿和发送后会话列表刷新拆到 `features/conversations/useConversationWorkspace.ts`，流式响应、停止生成和 active stream 清理拆到 `features/conversations/useConversationStreamController.ts`，复制、引用选区和编辑消息动作拆到 `features/conversations/useConversationMessageActions.ts`，分支切换和分支预览拆到 `features/conversations/useConversationBranching.ts`，附件上传、附件能力过滤和附件移除拆到 `features/conversations/useConversationAttachments.ts`，对话滚动、高亮定位和输入区测量拆到 `features/conversations/useConversationLayout.ts`，模型选择和推理模式弹层拆到 `features/conversations/useConversationModelControl.ts`，收藏页工作区外壳拆到 `features/favorites/FavoritesWorkspacePanel.tsx`，收藏面板的状态与动作拆到 `features/favorites/useFavoriteWorkspace.ts`，对话消息的收藏/取消收藏动作拆到 `features/favorites/useFavoriteMessageActions.ts`，收藏列表滚动条补偿和工具栏对齐拆到 `features/favorites/useFavoriteListAlignment.ts`，设置页工作区外壳和模型刷新接线拆到 `features/settings/SettingsWorkspacePanel.tsx`，纯数据转换按职责拆进 `branching.ts`、`conversationDraft.ts`、`conversationModels.ts`、`streamingMessages.ts`、`favoriteState.ts` 等小文件。

前端不负责鉴权可信判断、不直接读写 SQLite/JSONL、不直接调用大模型，也不保存 API key 到本地持久化存储。

## 本地开发

在 `frontend/` 目录安装依赖：

```bash
npm install
```

启动开发服务器：

```bash
npm run dev
```

构建前端：

```bash
npm run build
```

运行前端静态契约测试：

```bash
npm test
```

默认情况下，API 请求使用同源 `/api`。本地开发时，`vite.config.ts` 会把 `/api` 代理到 `http://127.0.0.1:8000`。也可以用 `VITE_API_BASE_URL` 覆盖 API 基地址。

## 页面与路由总览

前端没有引入 React Router，而是用浏览器 History API 和本地状态维护路由。

| 路由 | 页面 | 外壳 | 说明 |
| --- | --- | --- | --- |
| `/sign_in` | 登录页 | 独立认证面板 | 未登录入口 |
| `/sign_up` | 注册页 | 独立认证面板 | 未登录注册入口 |
| `/` | 主工作台 | 患者工作台外壳 | 首页对话、报告占位、生活占位、原始文件视图 |
| `/chat/{session_id}` | 指定会话 | 患者工作台外壳 | 打开某个历史会话，复用主工作台布局 |
| `/favorites` | 我的收藏 | 患者工作台外壳 | 收藏列表与详情 |
| `/setting` | 账号设置 | 患者工作台外壳 | 账号资料、密码、模型提供方和默认模型用途配置 |

路由相关函数：

- `currentRoute()` 从 `window.location.pathname` 识别当前路径。
- `navigateTo(path, replace?)` 调用 `pushState` 或 `replaceState`，然后同步 `route` 状态。
- `popstate` 监听浏览器前进/后退。
- 未登录访问非认证页时会跳到 `/sign_in`。
- 已登录访问 `/sign_in` 或 `/sign_up` 时会跳回 `/`。

账号设置从侧边栏底部账号按钮进入 `/setting`，并复用患者工作台外壳。退出登录位于设置页一级导航中。

## 登录与注册模块

### 登录页 `/sign_in`

登录页是独立页面，不使用患者工作台外壳。它的目标是让用户完成认证，不展示任何会话或工作台内容。

```text
main.login-page
└─ section.auth-panel
   ├─ div.brand-block
   │  └─ div.brand-name
   ├─ div.auth-switch
   │  ├─ button.workspace-tab 登录
   │  └─ button.workspace-tab 注册
   └─ form.login-form
      ├─ label 账号
      ├─ div.secret-field
      │  ├─ label 密码
      │  └─ SecretInput
      ├─ button.command-button
      └─ p.status-message.error（按需出现）
```

容器关系：

- `login-page` 占满视口，用 grid 居中 `auth-panel`。
- `auth-panel` 是认证卡片，内部从上到下排列品牌、模式切换和表单。
- `auth-switch` 是两个 tab 按钮，点击后通过 `navigateTo()` 在 `/sign_in` 和 `/sign_up` 间切换。
- `login-form` 只包含账号、密码、提交按钮和错误提示。
- 密码字段使用 `SecretInput`，`SecretInput` 内部再包含原生 `input` 和显示/隐藏按钮。

### 注册页 `/sign_up`

注册页复用登录页的顶层容器，只是表单切换为注册模式。

```text
main.login-page
└─ section.auth-panel
   ├─ div.brand-block
   ├─ div.auth-switch
   └─ form.register-form
      ├─ div.registration-guidance
      ├─ label 账号
      ├─ label 用户名称
      ├─ div.secret-field 密码 + SecretInput
      ├─ div.secret-field 确认密码 + SecretInput
      ├─ button.command-button
      └─ p.status-message.error（按需出现）
```

容器关系：

- `register-form` 是 `auth-panel` 的直接子区域，不新开页面外壳。
- `registration-guidance` 是注册说明区域，位于所有输入字段之前。
- 用户名称和确认密码只在注册模式出现。
- 注册前端会校验用户名称不能为空且不能包含空格；账号格式、密码一致性等最终以后端接口为准。

### 登录态恢复页

这是启动过程中的临时状态页面，不对应独立 URL。

```text
main.login-page
└─ section.auth-panel
   ├─ div.brand-name
   └─ p.status-message.testing 正在恢复登录态...
```

它复用认证页的居中布局，让用户在 `checkSession()` 完成前不会看到工作台的半加载状态。

### 认证流程

页面首次加载时：

```text
App 初始化
└─ checkSession()
   ├─ 成功：setSession(authenticated)，进入 WorkspacePage
   │  └─ useConversationLifecycle.loadWorkspaceData()
   │     ├─ fetchConversations()
   │     ├─ fetchFavorites()
   │     ├─ fetchModels()
   │     ├─ fetchModelDefaults()
   │     ├─ route 是 /chat/{session_id}：openConversation(session_id)
   │     └─ route 是 / 且有历史会话：openConversation(最近一条)
   └─ 失败：clearSessionToken()，进入未登录页面
```

登录或注册成功后：

```text
submitAuth()
└─ signIn() / signUp()
   ├─ saveSessionToken()
   ├─ setSession(authenticated)
   └─ navigateTo("/")
```

退出登录会调用后端退出接口，清空 token，重置工作台状态，并跳回 `/sign_in`。

登录 token 在本地开发时存储为 `serenita_auth_session_token`，请求时通过 `Authorization: Bearer ...` 发给后端。旧 key `serenita_session_token` 会在读取时迁移。

## 共享应用外壳

登录后大多数页面都通过 `WorkspaceRouteShell` 包住右侧工作区内容：

```text
main.patient-shell.main-page
├─ button.mobile-sidebar-backdrop（窄屏抽屉打开时）
├─ aside.patient-sidebar
│  ├─ section.sidebar-header
│  │  └─ div.brand-row
│  │     ├─ div.brand-name
│  │     ├─ button.sidebar-collapse-button
│  │     └─ button.mobile-sidebar-close-button
│  ├─ div.sidebar-content
│  │  ├─ nav.global-nav
│  │  │  ├─ div.sidebar-scenario-nav
│  │  │  │  ├─ button.sidebar-scenario-tab 报告
│  │  │  │  └─ button.sidebar-scenario-tab 生活
│  │  │  └─ button.primary-action 开启新对话
│  │  ├─ section.conversation-list
│  │  │  └─ conversation-item-row / message-meta
│  │  └─ div.sidebar-bottom
│  │     ├─ nav.secondary-nav
│  │     │  ├─ 原始文件
│  │     │  └─ 我的收藏
│  │     └─ section.user-summary
│  │        └─ button.account-button 账号设置
├─ section.patient-main
│  └─ 当前页面 mainContent
```

外壳关系：

- `patient-shell` 是顶层 grid 容器。当前后置样式中，实际桌面侧栏宽度为 `--sidebar-width: 264px`；桌面端折叠侧边栏后 grid 变为 `0 + 1fr`，不保留图标窄栏。
- `max-width: 1000px` 以下侧边栏改为左侧抽屉，`mobile-sidebar-backdrop` 负责点击遮罩关闭，`mobileSidebarOpen` 控制展开状态。
- `patient-sidebar` 承载场景入口、全局动作、会话列表、辅助导航和账号设置入口。
- `patient-main` 只承载当前任务页面，因此主工作区不会混入账号入口或会话导航逻辑。
- `sidebar-header` 是品牌区，只包含品牌标识、桌面折叠按钮和窄屏关闭按钮。
- `global-nav` 是高优先级动作区，先展示报告/生活场景入口，再展示“开启新对话”。
- `conversation-list` 是历史会话区域，每条会话由 `conversation-item-frame` 包住标题按钮和删除图标按钮。仅上传文件但尚未发送消息的草稿会话不会出现在这里。
- `sidebar-bottom` 把低频导航和账号区固定在侧边栏底部。
- `account-button` 直接进入 `/setting`；退出登录在设置页一级导航中提供。

## 主工作台模块

### 主工作台 `/`

`/` 是登录后的核心工作区。它包在 `patient-shell` 内，右侧 `patient-main` 渲染 `renderMainWorkspace()`。

```text
section.workspace-panel.home-workspace
├─ div.home-workspace-header
│  └─ header.workspace-titlebar
│     ├─ div.workspace-titlebar-side（侧栏展开按钮按需出现）
│     ├─ h1 当前场景标题
│     └─ span.workspace-titlebar-side
├─ div.home-workspace-content
│  ├─ div.conversation-surface
│  │  ├─ div.message-list（有消息时出现）
│  │  │  ├─ article.message-entry
│  │  │  │  ├─ div.message-bubble
│  │  │  │  └─ div.message-actions
│  │  │  ├─ details.thinking-process
│  │  │  └─ button.branch-restore-divider（按需出现）
│  │  └─ div.home-empty-center（无消息时出现）
│  │     ├─ div.empty-state
│  │     └─ form.assistant-composer.conversation-composer
│  └─ form.assistant-composer.conversation-composer（有消息时覆盖在历史底部）
│     ├─ div.resource-list.quote-context-list（引用消息后出现）
│     ├─ div.resource-list.file-context-list（上传文件后出现）
│     ├─ div.composer-input-frame
│     │  └─ textarea
│     ├─ div.composer-footer
│     │  ├─ label.file-button
│     │  ├─ composer-model-control
│     │  └─ button.send-button / button.stop-button
│     └─ p.status-message.error（按需出现）
└─ button.selection-quote-popover（选中文本后出现）
```

主工作台边界规则：

- `patient-main:has(.home-workspace)` 会把首页右侧主区 padding 归零，避免 `patient-main` 在对话历史左右额外包一层留白。
- `home-workspace` 是纵向 flex 容器：标题栏和对话舞台；报告/生活场景入口已经移到侧边栏。
- `home-workspace` 在首页对话场景中使用 `gap: 0`，避免标题栏和对话舞台之间产生隐式间距。
- `home-workspace-content` 是会话舞台和悬浮输入区定位容器。它开启 container query，并用 `--chat-scrollbar-gutter`、`--chat-column-side-gap` 计算 `--chat-column-width`，让消息列和输入框宽度保持一致。`home-workspace-content` 自身必须保持 `margin: 0`、`padding: 0`、`background: transparent` 和无额外阴影。
- `conversation-surface` 是唯一历史滚动容器，只负责展示消息或空状态，不承担额外的左右 inset。它使用 `overflow-y: auto`、`scrollbar-gutter: stable` 和固定的 `--chat-scrollbar-gutter` 右侧滚动条宽度，让滚动条只在内容溢出时显示；不能使用 `stable both-edges`，否则可见留白会把左侧虚拟 gutter 也算进去。
- `conversation-surface` 定义克制但可见的 scrollbar thumb，轨道保持透明，避免 Chromium/WebKit 在只设置滚动条宽度时把 thumb 计算成透明。
- `message-list`、空首页的 `home-empty-center` 和 `conversation-composer` 共享 `--chat-column-width`；有消息时，`conversation-composer` 仍以 `left: 50%` 对齐 `home-workspace-content` 的中心轴，历史列用 `--chat-scrollbar-axis-offset` 抵消右侧滚动条占位，避免滚动条把历史列中心拉偏。
- 空首页时，提示文案和输入区组成同一个居中组，`conversation-composer` 回到普通文档流，和提示文案一起在首页内容区水平、垂直居中；提示字号和提示到输入区的间距使用固定值，不随视口宽度、高度或断点变化。
- `home-workspace-content` 和 `conversation-surface` 都必须是直角容器，即使全局面板变量有圆角，也要在后置工作台规则里覆盖为 `border-radius: 0`。
- `conversation-surface`、`message-entry`、普通消息内部的 `message-bubble`、思考过程和 `conversation-composer` 使用轻量层级；普通消息容器不再依赖黑色 1px 边框，`message-list` 只负责列宽和尾部留白，不再额外画黑框。

消息组件关系：

- 用户消息和助手消息都由 `renderMessageBubble()` 渲染为 `message-entry`。
- 普通消息包含 `message-bubble` 和 `message-actions`。
- 思考过程不使用普通气泡，而是 `details.thinking-process`，可以显示思考耗时和思考内容。
- 思考仍在生成且助手正文尚未开始时，不展示空的正式回复区域；正文流式增量到达后再展示助手消息气泡。
- `message-actions` 中包含复制、编辑、分支、重新生成和收藏等动作，具体按钮由消息角色和消息状态决定。
- 有消息时，`assistant-composer` 绝对定位在 `home-workspace-content` 底部，消息列表用 `message-list::after` 留出底部空间，避免最后一条消息被输入框遮住；空首页时它位于 `home-empty-center` 内，和提示文案共同居中。
- 自动滚动到最新内容时，`scrollLatestMessageIntoView()` 以最新消息元素和当前输入区覆盖高度计算目标滚动位置，不直接滚到 `scrollHeight` 末尾。切换会话时会先清空旧滚动位置，再按新会话最新消息定位。
- `openConversation()` 使用 `conversationRequestSeqRef` 标记请求序号；用户快速切换会话、开启新对话或退出工作台后，过期的详情响应会被忽略。
- `composer-model-control` 是输入框底部的模型控制器，内部包含触发按钮、推理强度列表和嵌入式模型列表。
- `selection-quote-popover` 是 fixed 浮层，不属于消息列表 DOM 层级；它根据文本选区坐标定位。

输入区设计：

- `form.assistant-composer.conversation-composer` 是主工作台底部的统一输入区，不随 `首页`、`报告`、`生活` 场景切换而重建；输入草稿、上传资源、引用上下文和错误提示都由同一组状态维护。
- `composer-input-frame` 只负责承载多行 `textarea`，让输入框内部可以独立控制高度、滚动和焦点样式。当前 `textarea` 默认保持较矮高度，输入行数增加时先增高，达到上限后改为输入框内部滚动。
- `quote-context-list` 显示从历史消息文本选区加入的引用上下文，来源是 `quotedContext`，并提供“清除引用”按钮；`file-context-list` 显示待发送的上传资源和上传进度，来源是 `uploadingResources` 与 `uploadedResources`。
- 上传文件如果没有当前会话，会先创建草稿 `session_id` 并读取空消息详情；草稿会话只用于承载待发送资源，不会出现在左侧最近会话列表，直到用户发送第一条消息。
- `composer-footer` 是输入区底部工具栏，按顺序放置附件按钮、模型控制器和发送按钮。附件按钮保留 `附加文件` 可访问名称，发送按钮视觉上是向上箭头，但保留 `发送` / `发送中...` 可访问名称。
- `composer-model-control` 是模型与推理强度的组合选择器，属于输入区工具栏的一部分，不属于消息列表；触发按钮里的推理强度 chip 使用短文案，例如 `低`、`中`、`高`、`关闭`。当前弹层是固定定位 sheet，主弹层把推理强度选项和当前模型值作为连续菜单项展示，主弹层内推理强度选项和当前模型入口等宽，内部用两个区域展示推理强度和模型列表，中间以一条分隔线隔开；模型列表嵌入同一个 sheet 内独立滚动，不再使用桌面二级浮层。
- 流式生成期间发送按钮替换为同位置、同尺寸的圆形 `stop-button`，图标为方形停止符号；点击后取消当前生成并保留已生成片段，普通状态下不占位显示。
- `status-message.error` 只在 `composerError` 有值时出现，用于显示附件上传、发送失败、模型刷新失败等输入区级错误。当前空输入或非首页场景提交会直接忽略，不发起后端请求。
- 输入区覆盖在对话历史上方，不能通过改变 `conversation-surface` 高度来给输入区腾位置；输入区高度变化只同步更新 `--composer-overlay-height`，再由 `message-list::after` 提供历史尾部安全留白。

### 首页、报告、生活

首页、报告和生活使用 `activeScenario` 控制。报告和生活入口在侧边栏的 `sidebar-scenario-nav` 中；首页会在开启新对话、打开会话或回到主对话工作区时使用。

首页场景是真实对话场景：

- 标题来自当前会话标题；没有会话时显示默认文案。
- 登录后首次进入 `/` 时，如果当前账号已有历史会话，`loadWorkspaceData()` 会打开最近一条；只有没有历史会话、点击“开启新对话”或恢复空白首页草稿时才显示无会话的首页状态。
- 输入框可以发送消息。
- 文件上传会调用 `uploadContextResource()`，并随请求提交当前选择的模型 ID；上传结果显示在输入框上方的 `resource-list`。后端只接受当前 `chat` 默认模型作为上传和真实发送请求模型，非默认聊天模型会被拒绝；若 `chat` 模型不支持附件但 `vision_parse` 默认模型支持，后端会直接调用 `vision_parse` 并把附件作为原生输入发送，由视觉解析模型生成本轮回答。
- 选中历史消息文本后可加入引用上下文，引用也显示在 `resource-list`。
- 发送消息会创建或继续当前会话，并进入流式响应。

报告场景是占位入口：

- 从侧边栏切换后会导航到 `/`，并把 `activeScenario` 设置为 `reports`。
- 标题显示“报告能力正在准备中”。
- 输入框 placeholder 显示报告相关占位文案，textarea 处于禁用状态。
- `sendMessage()` 会在 `activeScenario !== "home"` 时直接返回，因此不会发起真实模型请求。

生活场景也是占位入口：

- 标题显示“生活建议先作为占位入口”。
- 输入框 placeholder 显示生活建议相关占位文案，textarea 处于禁用状态。
- 和报告场景一样，不发起真实模型请求。

这三个场景共享同一个 `home-workspace` 容器。差异由 `scenarioCopy` 中的标题、eyebrow 和 placeholder 驱动。

### 指定会话 `/chat/{session_id}`

`/chat/{session_id}` 与 `/` 使用同一个主工作台页面结构，区别是路由中带有会话 ID。

```text
/chat/{session_id}
└─ renderAppPage()
   └─ renderWorkspaceShell(renderMainWorkspace())
      └─ home-workspace
         └─ conversationDetail.messages
```

打开逻辑：

- `sessionIdFromChatPath(route)` 从路径解码会话 ID。
- 如果当前路径会话与 `currentSessionId` 不同，则调用 `openConversation(sessionId)`。
- `openConversation()` 会拉取会话详情，重置上传资源、引用、分支预览、编辑状态和错误状态。
- 如果从收藏详情点击“返回原对话”，会传入 `sourceMessageId`，打开后高亮对应消息。

消息关系：

- `conversationDetail.messages` 是当前激活路径上的消息。
- `conversationDetail.all_messages` 保存完整分支消息，用于计算兄弟分支和路径。
- `childrenByParent` 根据 `parent_message_id` 构建分支关系。
- `setActivePath()` 会把用户切换到另一个分支路径。
- `parentForNextMessage` 不为 `undefined` 时，界面进入“从某条消息之后创建分支”的预览状态，`visibleMessages` 会截断到该消息，并显示 `branch-restore-divider`。

### 对话发送与流式响应

发送消息时的状态流：

```text
sendMessage()
└─ submitConversationMessage()
   ├─ apiClient.sendMessage()
   ├─ navigateTo("/chat/{session_id}")
   ├─ showPendingConversationSummary()
   ├─ showStreamingTurn()
   └─ useConversationStreamController.startResponseStream()
      ├─ thinking_delta -> 更新 thinking 消息内容
      ├─ content_delta  -> 更新 assistant 消息内容
      ├─ completed      -> 标记完成
      ├─ cancelled      -> 标记取消
      └─ failed         -> 显示错误
```

容器与状态的关系：

- 流式消息先被乐观插入 `conversationDetail.messages`，所以用户能立刻看到自己的问题和思考框；思考仍在生成且助手正文为空时，空的助手回答不会渲染出来。
- `activeStreamRef` 保存当前流的 `AbortController`、`streamId`、`turnId` 和消息 ID。
- `activeStreamTurnId` 控制输入区发送按钮替换为停止按钮。
- `activelyThinkingTurnId` 控制思考过程的“正在思考”状态。
- 取消生成可以选择保留部分内容，保留时会把助手消息标记为 `cancelled`。

### 原始文件视图

原始文件不是独立 URL。点击侧边栏“原始文件”时会导航到 `/`，并把 `activeView` 设置为 `health`。

```text
section.workspace-panel
├─ header.workspace-header
│  ├─ span 原始文件
│  └─ h1 原始文件暂作为占位入口
└─ div.empty-state
   ├─ strong
   └─ p
```

容器关系：

- 它仍然位于 `patient-main` 里，并继续使用 `patient-sidebar`。
- 这个视图不包含场景入口、`home-workspace-content` 或输入框。
- 当前仅说明 v0.1.0 不录入正式文件，避免用户误以为报告、用药和生活指标已经完成。

## 账号设置模块

账号设置从侧边栏底部账号按钮进入 `/setting`，保留同一套患者工作台外壳。

```text
section.workspace-panel.settings-workspace
├─ div.settings-workspace-header
│  └─ div.settings-toolbar
└─ div.settings-workspace-content
   └─ SettingsShell
```

外层关系：

- `settings-workspace` 位于 `patient-main` 内，和收藏页一样占满右侧工作区。
- `settings-toolbar` 提供居中的页面标题，并在侧栏折叠或窄屏抽屉模式下显示侧栏开关。
- `settings-workspace-content` 是设置页内部布局容器，承载 `SettingsShell`。
- `SettingsWorkspacePanel` 负责右侧工作区外壳、顶部标题栏、侧栏开关传递和模型列表刷新回写。
- `SettingsShell` 是设置页内部真正的设置界面。

`SettingsShell` 使用按模块切换的响应式布局：账号资料、密码安全和默认模型在非窄屏下为第一栏加详情区两列，模型提供方为第一栏、服务列表和详情区三列。`max-width: 650px` 时切换为手机设置式逐级推进，一次只显示当前层级。

```text
section.settings-shell.settings-three-column
├─ aside.settings-nav.settings-primary-nav
│  ├─ 账号资料
│  ├─ 密码安全
│  ├─ 模型提供方
│  ├─ 默认模型
│  └─ 退出登录
├─ aside.settings-list-column（仅模型提供方模块渲染）
│  └─ provider-row
└─ main.settings-detail-column
   └─ 当前详情表单、模型提供方面板或默认模型面板
```

栏位职责：

- 第一栏 `settings-primary-nav` 是设置入口，直接放置“账号资料”“密码安全”“模型提供方”“默认模型”和“退出登录”。
- 第二栏 `settings-list-column` 只在模型提供方模块渲染，用于展示 OpenRouter、深度求索、阿里云百炼等服务列表，并在每行提供连接测试图标按钮。
- 第三栏 `settings-detail-column` 是详情工作区，展示表单、状态和操作按钮。
- 窄屏下由 `data-mobile-layer` 控制当前可见层级：根层展示设置入口，模型提供方先进入服务列表，再进入服务详情；账号资料、密码安全和默认模型直接进入对应详情。

### 账号资料

```text
section.settings-section
├─ h1 账号资料
├─ div.form-grid
│  ├─ label 账号标识 + readonly input
│  └─ label 用户名称 + input
└─ p.status-message.account-feedback（按需出现）
```

用户名称修改后会在 650ms 后自动保存；保存成功后，`SettingsShell` 调用 `onUserNameChange()`，由 `App` 更新侧边栏账号显示。

### 密码安全

```text
form.settings-section.password-section
├─ h1 修改密码
├─ div.form-grid
│  ├─ secret-field 当前密码 + SecretInput
│  ├─ secret-field 新密码 + SecretInput
│  └─ secret-field 确认新密码 + SecretInput
├─ button.command-button 更新密码
└─ p.status-message.account-feedback（按需出现）
```

这里的三个敏感字段全部使用 `SecretInput`，避免把密码直接裸露在界面中。

### 模型提供方

```text
section.settings-section.provider-panel
├─ div.provider-workspace
│  ├─ form.provider-form
│  │  ├─ div.form-grid.provider-fields
│  │  │  ├─ 官网地址
│  │  │  ├─ API 地址
│  │  │  └─ API key + SecretInput
│  ├─ p.status-message.provider-feedback（按需出现）
│  └─ section.provider-model-section
│     ├─ div.model-section-header
│     │  └─ div.model-section-title
│     │     ├─ h2 已添加模型
│     │     ├─ span.status
│     │     └─ button.settings-icon-button 添加模型
│     └─ div.model-list / p.status-message
```

模型提供方的状态关系：

- `providers` 是服务列表。
- `selectedProviderId` 决定第二栏选中项和第三栏详情。
- `drafts` 保存每个服务当前输入的官网、API 地址和 API key。
- `savedDraftsRef` 保存上次已保存草稿，用于判断是否需要自动保存。
- 用户修改服务配置后，`useEffect` 会在 650ms 后自动保存。
- 服务列表每行的连接测试图标会调用后端测试接口，并用图标状态和 tooltip 展示结果。
- 已添加模型显示在 `model-list`，每个 `model-row` 包含模型名和删除动作；默认模型在独立的“默认模型”面板里设置。

### 默认模型

```text
section.settings-section.default-model-section
├─ h1 默认模型
└─ div.default-model-list / p.status-message
   └─ div.default-model-row
      ├─ div.default-model-copy
      └─ div.default-model-picker
         ├─ button.default-model-trigger
         └─ div.default-model-popover（按需出现）
```

默认模型用途包括聊天模型、标题生成模型、视觉解析模型和压缩上下文模型。候选模型来自已添加模型列表；其中视觉解析模型只展示 `file_mime_types` 中包含图片 MIME 的模型。选择聊天默认模型后，会刷新工作台输入区的模型候选顺序。`chat` 默认模型是 v0.1.0 首页真实对话和附件上传的后端有效请求模型；输入区模型列表可以展示其它已添加模型的能力，但发送或上传时请求模型必须与 `chat` 默认模型一致；附件按钮和可选 MIME 会合并当前 `chat` 模型与 `vision_parse` 模型能力。

### 添加模型子浮窗

在模型提供方页点击“添加模型”后会打开另一个浮层：

```text
div.model-picker-backdrop
└─ section.model-picker-modal[role="dialog"]
   ├─ div.model-picker-header
   │  ├─ 标题区
   │  └─ button.secondary-button 关闭
   ├─ p.status-message.testing（加载中）
   ├─ div.model-picker-error-actions（加载失败时，含错误和重试）
   ├─ div.model-list
   │  └─ div.model-row
   │     ├─ span 模型名
   │     └─ button.text-button 添加 / 已添加
   └─ p.status-message（无可添加模型）
```

它的外层 `model-picker-backdrop` 独立于 `settings-three-column`，但仍由 `SettingsShell` 渲染。打开时会先自动保存当前 provider draft，再请求远端模型列表。

## 我的收藏模块

收藏页复用患者工作台外壳，右侧主区域由 `FavoritesWorkspacePanel` 接入收藏状态、侧栏开关和来源会话跳转。

```text
section.workspace-panel.favorites-workspace
├─ div.favorites-workspace-header
│  └─ div.favorite-toolbar
│     ├─ button.favorites-sidebar-toggle（按需出现）
│     ├─ strong.favorite-toolbar-title 收藏 / 已选择 n 条
│     └─ button.favorite-multi-select-button / button.favorite-selection-cancel-button
├─ div.favorites-workspace-content
│  ├─ div.favorite-layout（有收藏时）
│  │  ├─ section.favorite-list-panel
│  │  │  ├─ div.favorite-list
│  │  │  │  ├─ div.favorite-selection-row
│  │  │  │  │  ├─ label.favorite-card-check-frame（批量模式时）
│  │  │  │  │  └─ article.favorite-card
│  │  │  │  │     ├─ div.favorite-card-top 标题
│  │  │  │  │     ├─ div.favorite-summary markdown summary
│  │  │  │  │     ├─ div.favorite-card-meta-row 来源类型 / 创建时间
│  │  │  │  │     └─ div.favorite-card-tag-row + FavoriteTagCapsules
│  │  │  │  └─ p.favorite-list-count 共 n 条
│  │  │  └─ div.favorite-bulk-actions（批量模式时）
│  │  └─ aside.favorite-detail / favorite-detail-empty
│  │     ├─ div.favorite-detail-header
│  │     │  ├─ button.favorite-detail-back-button
│  │     │  ├─ h2
│  │     │  ├─ div.favorite-detail-meta-row 来源类型 / 创建时间
│  │     │  └─ div.favorite-detail-tag-row + FavoriteTagCapsules
│  │     ├─ div.favorite-detail-body markdown snapshot / summary
│  │     ├─ p.favorite-source-note（原会话不可用时）
│  │     └─ div.favorite-detail-actions 返回原对话（按需出现）
└─ div.favorite-empty-shell > div.empty-state（无收藏时）
```

容器关系：

- `favorites-workspace` 是收藏页根容器。
- `favorites-workspace-header` 承载页面工具栏；`favorite-layout` 只出现在 `favorites-workspace-content` 中，是两列 grid，左列列表、右列详情。
- `favorite-list-panel` 包含收藏列表、列表底部总数和批量动作区。
- `favorite-card` 是重复项容器，内容顺序固定为标题、Markdown 摘要、元信息和标签胶囊。
- `favorite-selection-row` 只在批量模式下显示左侧选择框；非批量模式点击卡片打开详情。
- `favorite-detail` 是详情侧栏；没有选中收藏时使用 `favorite-detail-empty` 占位。
- `max-width: 650px` 时收藏页变成单列，详情以覆盖式抽屉出现，并通过“返回收藏列表”关闭。
- 无收藏时不渲染两列布局，直接显示 `empty-state`。

交互关系：

- “多选收藏”只开启 `favoriteSelectionMode`，不会自动选中所有收藏。
- 批量模式下，勾选卡片会维护 `selectedFavoriteIds`；工具栏可全选/取消全选、批量设置标签或删除选中收藏。
- “删除”调用 `batchDeleteFavorites()`。
- 点击收藏卡片调用 `getFavorite()` 并把结果放入 `favoriteDetail`。
- 标签由 `FavoriteTagCapsules` 渲染；列表和详情都可新增或删除标签，前端会去空、去重并通过 `updateFavorite()` 自动保存。
- “返回原对话”会打开来源会话并定位到来源消息。

## 共享实现细节

### API client

页面不直接写 fetch，而是通过 `apiClient` 访问后端：

```text
App / SettingsShell
└─ apiClient
   ├─ authApi
   ├─ accountSettingsApi
   ├─ modelProviderApi
   ├─ conversationApi
   └─ favoriteApi
      └─ request.ts / streamConversation()
         └─ 后端 /api
```

`request.ts` 会读取 `sessionToken.ts` 中保存的 token，并在请求头中注入 `Authorization: Bearer ...`。普通 JSON 请求走 `request<T>()`；会话流式响应在 `conversationApi.ts` 中用 `fetch` 直接读取 SSE 文本流。

### SecretInput

```text
span.secret-input
├─ input[type=password/text]
└─ button.secret-toggle
```

`SecretInput` 接收所有普通 input 属性，并额外要求 `labelForAction`。它自己维护 `revealed` 状态，按钮通过 `aria-controls` 和 `aria-pressed` 表达当前可见性。它被认证表单、密码修改表单和 API key 输入框复用。`SecretInput` 不在主工作台对话区使用，敏感输入集中在 `/setting` 的设置页。

### Markdown 内容

`renderMarkdownContent(content)` 把文本统一包在：

```text
div.markdown-content
└─ ReactMarkdown
```

它用于助手回答、思考过程、收藏摘要和收藏详情。样式统一处理段落、列表、代码块和引用。

### 图标按钮

`components/icons.tsx` 定义一组应用内 SVG 图标组件：

- `PaperclipIcon`：文件上传。
- `ArrowUpIcon`：发送。
- `StopIcon`：停止生成。
- `TrashIcon`：删除会话。
- `SidebarBackIcon`、`SidebarCloseIcon`：侧边栏展开/返回和关闭。
- `PlusIcon`：开启新对话；收藏标签和设置页添加模型处也有局部加号按钮。
- `ReportScenarioIcon`、`LifestyleScenarioIcon`、`HealthRecordIcon`、`FavoriteNavIcon`、`SettingsNavIcon`：侧边栏导航图标。
- `CopyIcon`、`EditIcon`、`RegenerateIcon`、`BranchIcon`、`StarIcon`：消息操作。
- `QuoteIcon`：选中文本加入对话。
- `EyeIcon`、`EyeOffIcon`：敏感输入显示/隐藏。
- `LightningIcon`、`CheckIcon`、`ChevronLeftIcon`、`ChevronRightIcon`、`XIcon`：设置页状态、导航、关闭和模型管理操作。

这些图标只服务当前应用壳、消息交互、收藏和设置入口；调用方通过组件名表达语义，不在页面文件里手写重复 SVG。

### 状态分组

当前状态可以按职责理解；入口层、外壳层、工作台层分开承载：

| 状态组 | 代表状态 | 负责内容 |
| --- | --- | --- |
| 路由与认证 | `useBrowserRoute()`、`useAuthSession()` | 当前页面、登录态、启动检查、登录/注册/退出 |
| 应用壳 | `useWorkspaceRouteShell()`、`useResponsiveSidebar()` | 桌面折叠、窄屏抽屉、当前侧栏模式和主区 toggle |
| 对话页状态 | `useConversationPageState()` | 工作台视图、会话、输入区、附件、引用、编辑、流式标记和 DOM refs 初始化 |
| 工作区 | `activeView`、`activeScenario` | 主工作台、原始文件、首页/报告/生活 |
| 首页派生状态 | `useConversationViewState()` | 首页标题、消息索引、分支预览截断、可见消息和附件能力 |
| 首页渲染 | `ConversationWorkspacePanel`、`ConversationWorkspaceSurface`、`HomeWorkspace`、`ConversationComposer`、`ConversationMessageBubble` | 首页对话的 prop 映射、标题栏、消息列表、输入区、模型控件和分支控件拼装 |
| 会话 | `currentSessionId`、`conversationDetail`、`conversations`、`conversationRequestSeqRef` | 当前会话、历史会话、消息列表和过期详情响应防护 |
| 会话生命周期 | `useConversationLifecycle()` | 初始数据加载、`/chat/{session_id}` 恢复、打开/删除会话、新对话、退出登录和工作台重置 |
| 滚动与输入区布局 | `useConversationLayout()`、`messageRefs`、`messageListRef`、`conversationSurfaceRef`、`composerRef` | 会话切换时重置滚动、锚定最新消息、高亮来源消息定位、控制流式跟随、测量输入区高度和滚动条补偿 |
| 发送与重新生成 | `useConversationWorkspace()`、`sending` | 发送中、重新生成、提交对话草稿和发送后会话列表刷新 |
| 流式控制 | `useConversationStreamController()`、`activeStreamTurnId`、`activelyThinkingTurnId`、`cancellingTurnId` | 流式响应、思考中、取消生成和 active stream 清理 |
| 消息动作 | `useConversationMessageActions()`、`copiedMessageId`、`editingMessageId`、`quoteSelection` | 复制消息、引用历史文本、选区浮层、编辑历史提问 |
| 分支 | `useConversationBranching()`、`parentForNextMessage`、`highlightedMessageId` | 切换分支、创建分支、分支预览恢复、定位消息 |
| 附件 | `useConversationAttachments()`、`uploadingResources`、`uploadedResources` | 上传文件、同步上传进度、按模型能力过滤待发送附件、移除待发送附件 |
| 上下文 | `quotedContext` | 提交引用上下文 |
| 模型 | `useConversationModelControl()`、`models`、`selectedModelId`、`thinkingMode`、`modelPickerOpen` | 模型选择、推理强度、输入区模型弹层 |
| 收藏 | `useFavoriteWorkspace()` 管理的 `favorites`、`favoriteSelectionMode`、`selectedFavoriteIds`、`favoriteDetail` | 收藏列表、批量选择模式、已选收藏和详情 |
| 消息收藏 | `useFavoriteMessageActions()` | 对话消息收藏/取消收藏、刷新收藏列表和错误提示 |
| 收藏布局 | `useFavoriteListAlignment()`、`favoriteListPanelRef`、`favoriteListRef` | 测量收藏列表滚动条 gutter，设置列表行和工具栏共享的末端补偿 |
| 收藏标签 | `useFavoriteWorkspace()` 管理的 `editingFavoriteTagIds`、`editingFavoriteDetailTagId`、`addingFavoriteTagId`、`favoriteTagInput`、`pendingFavoriteTagsRef` | 列表/详情标签胶囊编辑、新增标签和待保存标签 |
| 设置 | `SettingsWorkspacePanel`、`SettingsShell`、`SettingsView`、`settingsTypes.ts` | 设置页外壳、账号资料、密码、模型提供方、默认模型和响应式层级 |

## 视觉与布局系统

`styles.css` 只作为兼容入口引入 `src/styles/index.css`；真实样式按 surface 拆分到 `tokens.css`、`base.css`、`components.css`、`shell.css`、`auth.css`、`conversations.css`、`composer.css`、`favorites.css`、`settings.css` 和 `responsive.css`。`base.css` 只保留 reset、body、原生表单和全局 focus；跨页面复用的 Markdown、SecretInput、状态文本和共享按钮放在 `components.css`。

核心视觉变量：

- `--page-bg`、`--page-wash`：页面背景。
- `--ink`、`--ink-strong`、`--muted`：文字层级。
- `--surface-strong`、`--surface`、`--surface-muted`、`--surface-accent`：容器表面。
- `--accent-strong`、`--accent`、`--accent-soft`、`--accent-ink`：主要动作、选中态和强调态。
- `--danger`、`--danger-soft`：删除和错误。
- `--radius-panel`、`--radius-control`、`--radius-small`：面板、控件和小按钮圆角。
- `--focus-ring`：键盘焦点。

布局原则：

- 顶层工作台是左右分栏，侧边栏负责导航，主区负责任务。
- 首页主工作台不依赖 `patient-main` 的通用内边距；对话舞台需要贴齐右侧主区边界时，应先检查 `patient-main:has(.home-workspace)`、`home-workspace`、`home-workspace-content`、`conversation-surface` 的 padding、margin 和 gap。
- 主对话区域使用 `home-workspace-content` 做定位和宽度约束，消息列和输入框共享同一个 `--chat-column-width`。输入框中心固定在 `home-workspace-content` 的 `50%`，消息列通过 `--chat-scrollbar-axis-offset` 抵消右侧滚动条占位，二者共享同一条中心轴。
- `home-workspace-content` 和 `conversation-surface` 是调试边界容器，保持直角；不要让全局面板圆角重新作用到这两层。
- 输入框覆盖在对话舞台底部，消息列表用伪元素预留空间。
- 设置页按模块使用两栏或三栏结构：一级导航、对象列表（仅模型提供方）、详情。
- 收藏页使用两列结构：列表和详情。
- 表单控件和按钮使用统一圆角、边框、焦点态和状态色。

响应式规则：

- `max-width: 1000px`：`patient-shell` 变成单列，侧边栏改为左侧抽屉；首页和收藏页顶部显示侧边栏开关。
- `651px-1000px`：收藏页和设置页保留双栏/三栏工作区，但收紧列表栏、详情栏和对话列宽度。
- `max-width: 650px`：整体 padding 和圆角收紧；消息气泡最大宽度放宽到 100%；输入区底部控件重新排布；模型选择弹层从绝对定位变为表单内静态布局；收藏页详情改为覆盖式抽屉。
- `min-width: 300px`：当前最小支持宽度；代码不维护 300px 以下的额外断点。
- `prefers-reduced-motion: reduce`：把过渡时间压到 1ms，避免动态效果干扰。

## 当前边界与后续拆分方向

- `src/App.tsx` 已经是薄入口；不要再把业务状态、页面渲染或 API 编排塞回入口层。
- `src/app/` 负责路由、共享外壳和响应式侧边栏；`WorkspaceRouteShell.tsx` 集中处理登录后外壳接线和主区侧栏 toggle，`Sidebar.tsx` 集中处理场景入口、历史会话、辅助导航和账号设置入口，1000px 抽屉断点只应在 `useResponsiveSidebar` 和 `responsive.css` 中保持一致。
- `features/conversations/WorkspacePage.tsx` 当前是工作台页入口；`useWorkspacePageModel.ts` 负责登录后工作台 hook 编排和跨模块状态组合；`WorkspaceRouteContent.tsx` 负责登录后 route 分支和 `WorkspaceRouteShell` 包装；`useConversationPageState.ts` 集中初始化工作台对话页本地状态和 DOM refs；`ConversationWorkspacePanel.tsx` 集中把分组后的状态和动作映射给 `ConversationWorkspaceSurface`；`ConversationWorkspaceSurface.tsx` 已接管首页对话的渲染拼装，包括 `HomeWorkspace`、`ConversationComposer`、`ConversationMessageBubble`、`BranchControls` 和 `ComposerModelControl` 的组合；`useConversationViewState.ts` 集中派生首页标题、消息索引、分支预览截断、可见消息和附件能力。
- `conversationDraft.ts`、`streamingMessages.ts`、`branching.ts`、`favoriteState.ts` 是纯逻辑边界，适合单元化测试和契约测试引用；`useConversationLifecycle.ts` 是会话生命周期边界，集中管理初始加载、指定会话路由恢复、打开/删除会话、新对话、退出和工作台重置；`useConversationLayout.ts` 是 DOM layout hook 边界，集中管理对话滚动、高亮来源消息定位和输入区测量；`useConversationWorkspace.ts` 是会话动作边界，集中处理发送、重新生成、提交草稿和会话列表刷新；`useConversationStreamController.ts` 是流式控制边界，集中处理 SSE 增量、停止生成、思考状态和 active stream 清理；`useConversationMessageActions.ts` 是消息动作边界；`useConversationBranching.ts` 是分支动作边界；`useConversationAttachments.ts` 是附件动作边界，集中处理上传、进度、模型能力过滤和移除；`useConversationModelControl.ts` 是模型控制边界；`FavoritesWorkspacePanel.tsx` 是收藏页外壳边界，集中处理收藏页右侧工作区接线；`useFavoriteWorkspace.ts` 是收藏页状态与动作边界，集中处理详情、标签、批量选择和删除；`useFavoriteMessageActions.ts` 是对话消息收藏动作边界，集中处理收藏/取消收藏和收藏列表刷新；`useFavoriteListAlignment.ts` 是收藏页 DOM layout 边界，集中处理列表滚动条补偿。
- 账号设置 UI 已经拆为 `SettingsWorkspacePanel.tsx`、`SettingsShell.tsx`、`SettingsView.tsx` 和 `settingsTypes.ts`。
- 未来报告正式 UI 应放在 `src/features/reports/`。
- Agent、工具、记忆和技能内部逻辑只属于后端。前端应调用“分析报告”“发送消息”这类业务接口，而不是直接调用 Agent。
