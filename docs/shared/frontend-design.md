# Serenita 前端设计说明

> 文档状态：技术参考 / 前端设计参考
> 适用范围：React + Vite 患者端工作台
> 当前用途：记录患者端工作台的前端体验、页面结构与交互规则，供各版本实现时参考
> 当前执行版本：`v0.1.0`。本文档只做前端体验参考，不单独扩展当前版本范围。

## 1. 设计定位

前端采用患者主工作台形态，核心目标是让用户在一个稳定的工作区内完成健康提问、报告查看和生活建议查看。

核心体验是患者主工作台外壳，采用"左侧导航 + 右侧主面板 + 底部统一输入区"。`/` 承载首页对话、报告占位、生活占位和原始文件占位；报告和生活场景入口位于左侧栏。我的收藏页 `/favorites` 和账号设置页 `/setting` 都是受登录保护的独立 URL 页面，并保留同一套左侧主工作栏。当前 `v0.1.0` 只有首页可发送真实对话接口请求，报告和生活保留占位入口。

## 2. 视觉系统（全版本统一）

视觉风格偏轻医疗、低压、柔和陪伴。

核心特征：

- 主色为柔和紫蓝色系。
- 背景使用浅色渐变和低透明度径向光感。
- 界面整体采用少线条层级：默认控件和列表项不依赖描边表达边界，主要通过背景色、文字权重和留白区分层级。
- 面板和卡片优先使用白色半透明背景；边框只用于结构分区、弹窗、输入聚焦和必要的可访问状态，阴影只用于真正悬浮的元素。
- 主文本使用低饱和深紫灰，辅助文本使用低饱和灰紫。
- 操作按钮使用 8px 左右的克制圆角；图标按钮保持固定尺寸，不强制做圆形。

字体：

- 当前正文字体变量为系统 UI 字体栈：`-apple-system`、`BlinkMacSystemFont`、`Segoe UI`、`PingFang SC`、`Microsoft YaHei`、`sans-serif`。
- 当前不再单独加载展示字体；品牌和标题使用同一套 UI 字体，通过字重、字号和留白建立层级。

主要 CSS 变量：

```css
--page-bg: oklch(97.6% 0.014 286);
--ink: oklch(31% 0.031 272);
--ink-strong: oklch(20% 0.042 274);
--muted: oklch(52% 0.029 274);
--accent-strong: oklch(43% 0.106 276);
--radius-control: 8px;
--font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
```

样式入口 `frontend/src/styles.css` 只保留一行 `@import "./styles/index.css";`。真实 CSS 按 cascade 拆到 `tokens.css`、`base.css`、`components.css`、`shell.css`、`auth.css`、`conversations.css`、`composer.css`、`favorites.css`、`settings.css` 和 `responsive.css`；`base.css` 只保留 reset、body、原生表单和全局 focus，跨页面复用的 Markdown、SecretInput、状态文本和共享按钮放在 `components.css`。

异常指标配色：

| 标记 | 颜色 | 说明 |
| --- | --- | --- |
| 正常 | 默认文字色 | 报告未标记异常 |
| `↑` | `#E67E22` | 异常或偏高只显示上箭头 |
| `↓` | `#3498DB` | 偏低只显示下箭头 |

## 3. 响应式规则（全版本统一）

前端定义三个主要响应式区间：

| 断点 | 行为 |
| --- | --- |
| `max-width: 1000px` | 左侧主工作栏切换为抽屉；右侧工作区保持单列，顶部显示侧边栏开关 |
| `651px-1000px` | 收藏页和设置页保留工作区列结构，但收紧列表栏、详情栏和对话列宽度 |
| `max-width: 650px` | 首页场景、收藏页和设置页收敛为单列，输入区操作按钮分行，收藏详情以覆盖式详情抽屉展示 |

当前支持的最小视口宽度为 300px，不再维护 300px 以下的专门断点。检验报告趋势图仍属于后续报告场景规划；进入正式实现后，移动端应调整为单列轴线和单列统计卡，避免图表和标签挤压。

## 4. 页面骨架（全版本统一）

页面根布局为 `.patient-shell`，使用两栏 Grid：

- 左侧 `.patient-sidebar`：固定导航区，桌面端支持完全折叠，窄屏切换为抽屉。
- 右侧 `.patient-main`：患者主工作区。

左侧导航与右侧主页之间只使用一条竖向分隔线，不使用左右两块卡片式外框。会话条目标题必须限制在左栏宽度内，超长文本使用省略号截断，不允许越过分隔线。

左侧导航、会话列表、收藏列表和设置列表默认不画独立外框；当前页面、当前条目和当前设置项使用浅紫灰背景块表示选中状态，hover 使用更轻的背景反馈。除侧边栏与主区、设置页列与列、收藏详情与列表之间的结构分隔线外，不应在普通行项目上叠加描边和投影。

桌面端侧边栏折叠后不保留图标窄栏，主区占满宽度；折叠后的展开入口显示在右侧工作区顶部。`max-width: 1000px` 以下使用同一枚侧边栏图标打开抽屉，抽屉打开时显示遮罩，按 Escape 或点击遮罩可关闭。

左侧导航包含：

- 品牌区只展示 `Serenita`，不展示产品定位语。
- 场景入口：`报告`、`生活`，点击后停留在 `/` 并切换占位场景。
- 按钮：`开启新对话`。
- 对话记录区：不显示 `最近会话` 或 `最近对话` 标题；每行会话条目使用悬浮垃圾桶图标删除。
- 底部辅助入口：`原始文件` 排在 `我的收藏` 上方，整体位于账号按钮上方；`原始文件` 是占位入口，`我的收藏` 进入 `/favorites`。
- 当前登录用户摘要：左下角账号按钮展示当前 `user_name` 和设置图标；点击后直接进入 `/setting`，退出登录位于设置页一级导航。

当前代码入口 `frontend/src/App.tsx` 只负责路由和认证门禁；共享外壳在 `frontend/src/app/`，其中 `WorkspaceRouteShell.tsx` 负责登录后外壳接线和主区侧栏 toggle 控制，`PatientShell.tsx` 与 `Sidebar.tsx` 负责结构与导航 UI。登录后工作台页入口由 `features/conversations/WorkspacePage.tsx` 承担，右侧工作区和会话状态编排由 `features/conversations/useWorkspacePageModel.ts` 承担，登录后 route 分支和 `WorkspaceRouteShell` 包装由 `features/conversations/WorkspaceRouteContent.tsx` 承担。首页对话页本地状态和 DOM refs 初始化由 `features/conversations/useConversationPageState.ts` 承担，首页对话工作区的分组状态到 surface prop 映射由 `features/conversations/ConversationWorkspacePanel.tsx` 承担，首页对话的消息列表、输入区和模型控件拼装由 `features/conversations/ConversationWorkspaceSurface.tsx` 承担，首页标题、消息索引、分支预览截断和附件能力等派生值由 `features/conversations/useConversationViewState.ts` 承担。会话打开、URL 恢复、删除、退出和工作台重置由 `features/conversations/useConversationLifecycle.ts` 承担；会话发送、重新生成、提交草稿和发送后列表刷新由 `features/conversations/useConversationWorkspace.ts` 承担，流式响应、停止生成和 active stream 清理由 `features/conversations/useConversationStreamController.ts` 承担，复制、引用选区和编辑消息动作由 `features/conversations/useConversationMessageActions.ts` 承担，分支切换和分支预览由 `features/conversations/useConversationBranching.ts` 承担，附件上传、附件能力过滤和附件移除由 `features/conversations/useConversationAttachments.ts` 承担，对话滚动、高亮定位和输入区测量由 `features/conversations/useConversationLayout.ts` 承担，模型选择和推理模式弹层由 `features/conversations/useConversationModelControl.ts` 承担，收藏页工作区外壳由 `FavoritesWorkspacePanel` 承担，收藏页状态与动作由 `features/favorites/useFavoriteWorkspace.ts` 承担，对话消息收藏/取消收藏由 `features/favorites/useFavoriteMessageActions.ts` 承担，收藏列表滚动条补偿由 `features/favorites/useFavoriteListAlignment.ts` 承担。账号设置工作区外壳由 `SettingsWorkspacePanel` 承担，`SettingsShell` 负责数据编排，`SettingsView` 负责界面结构。

未登录时展示认证页。登录页路径为 `/sign_in`，注册页路径为 `/sign_up`；两者仍在同一个认证界面中通过顶部 `auth-switch` 登录/注册 tab 互相跳转并同步 URL。登录表单只包含账号、密码、提交按钮和错误提示；注册表单包含注册说明、账号、用户名称、密码、确认密码、提交按钮和错误提示。注册、登录过程中均展示加载状态并禁止重复提交。未登录访问受保护页面 `/`、`/chat/{session_id}`、`/favorites` 或 `/setting` 时回到 `/sign_in`，已登录访问 `/sign_in` 或 `/sign_up` 时进入 `/`。

登录后进入工作台会执行 `loadWorkspaceData()`，并行拉取会话、收藏、已添加模型和默认模型；如果当前路径是 `/chat/{session_id}`，按路径打开指定会话；如果当前路径是 `/` 且已有历史会话，默认打开最近一条。无历史会话、点击“开启新对话”或恢复空白首页草稿时，才进入没有打开会话的首页状态。

### 4.1 账号设置页

点击左下角账号按钮后直接进入 `/setting` 页面；页面仍使用患者主工作台外壳。账号设置内容内部按当前模块调整栏位：账号资料、密码安全和默认模型在非窄屏下使用设置入口加详情区两列，模型提供方在非窄屏下使用设置入口、服务列表和详情区三列，窄屏下收敛为逐级推进的单层视图。这个内部导航仅作用于账号设置页内部，不替代产品左侧主工作栏。

账号设置页保留列与列之间的结构分隔线，但设置入口、模型提供方行和已添加模型行默认不画卡片边框；选中和悬停状态通过背景块表达，避免三列布局中出现密集框线。

账号设置内部导航直接包含以下入口：

- `账号资料`：展示当前账号标识和用户名称。账号标识用于数据目录和登录凭证索引，v0.1.0 不支持修改；用户名称可编辑。
- `密码安全`：通过独立表单修改当前账号密码。
- `模型提供方`：管理各模型服务的官网地址、API 地址、API key 配置状态、连接测试、远端模型添加和已添加模型。
- `默认模型`：按 `chat`、`title`、`vision_parse`、`compact` 四个用途维护默认模型；`vision_parse` 用于 `chat` 模型不能原生处理附件时直接完成带附件回答，`compact` 在 v0.1.0 只做设置入口和数据库预留。
- `退出登录`：清除当前登录态并返回 `/sign_in`。

非窄屏下，账号资料、密码安全和默认模型使用第一栏加详情区两列，不渲染空的第二栏；模型提供方保留第一栏、服务列表和详情区三列。`max-width: 650px` 时采用手机设置式逐级推进：根层展示账号资料、密码安全、模型提供方、默认模型和退出登录，点击模型提供方后先进入服务列表，再进入具体服务详情；点击账号资料、密码安全或默认模型直接进入对应详情。

账号资料与密码安全交互要求：

- 用户名称表单默认填入当前 `user_name`，保存成功后刷新侧边栏用户摘要和当前登录态中的用户名称。
- 修改密码表单包含当前密码、新密码和确认新密码；新密码不做复杂度要求，但不能为空，且两次输入必须一致。
- 修改密码成功后给出明确反馈；当前会话可继续保持，其它已登录会话应失效。
- 前端不得展示密码哈希、session token 或其它登录凭证。

模型提供方交互要求：

- 模型提供方列表至少包含 `OpenRouter`、`深度求索`、`阿里云百炼`，并展示服务名称、连接测试图标状态和进入详情箭头；当前前端列表不展示 API 地址，也不单独展示 `default_provider` 标记。
- 模型提供方中间列表只展示服务名称、连接测试图标和进入详情箭头，避免列表区域信息过载。
- 选中模型提供方后，右侧详情从上到下依次展示官网地址、API 地址、API key 输入框和已添加模型列表；连接测试从服务列表行内图标触发。
- 官网地址当前作为可编辑配置项保存和回填，不在设置页内提供单独跳转按钮；用户可直接编辑，并随草稿自动保存。
- API key 输入框回填已保存密钥，用户可直接编辑，短暂停顿后自动保存。
- API 地址会预填为服务建议地址，用户可直接修改，短暂停顿后自动保存。
- 测试连接使用当前表单中的 API 地址和 API key，成功或失败都展示明确状态。
- 已添加模型列表只展示当前账号已经添加的模型；已添加模型可删除，默认用途在 `默认模型` 一级设置中维护。
- `添加模型` 按钮打开弹窗；弹窗使用当前账号已保存的 API 地址和 API key 真实请求远端模型服务，按厂商返回顺序展示远端模型，并在每个模型右侧提供添加按钮；未保存 API key 时提示先补全配置，不展示假模型列表。

默认模型交互要求：

- 默认模型候选项来自当前账号已添加模型。
- `vision_parse` 候选项只展示 `file_mime_types` 中包含图片 MIME 的视觉模型。
- `chat` 是首页真实发送的后端最终校验；当前首页模型弹层会刷新全部已添加模型并将 `chat` 默认模型置顶，前端推理强度随当前选中模型变化，附件按钮同时参考当前 `chat` 模型和 `vision_parse` 模型的文件能力，后端上传和发送仍只接受 `chat` 默认模型作为请求模型。
- `title` 用于会话标题生成；未设置时回退 `chat`。
- `vision_parse` 在 `chat` 模型不能原生处理附件时触发带附件回答回退；`compact` 在 v0.1.0 不触发长会话压缩流程。

### 4.2 我的收藏页

`我的收藏` 是 v0.1.0 的正式能力，点击左侧导航中的 `我的收藏` 后进入收藏页 `/favorites`；页面仍保留产品左侧主工作栏。

收藏页展示当前登录账号的收藏列表、批量选择工具栏、收藏详情和标签编辑。收藏详情中的“返回原对话”会回到 `/` 并打开来源会话；来源会话不存在时，收藏页仍展示收藏快照，不展示返回入口。

收藏页列表默认使用无框行/无框卡片形态，选中收藏和批量选中收藏使用背景色区分；收藏详情与列表之间可保留结构分隔线，普通标签、按钮和批量工具栏不使用重描边。

收藏页当前交互定稿：

- 顶部工具栏默认标题为 `收藏`，进入批量选择模式后居中显示 `已选择 n 条`。
- 多选按钮只进入批量选择模式，不自动选中任何收藏；批量区提供全选/取消全选、设置标签和删除选中收藏。
- 收藏卡片顺序为标题、Markdown 摘要、来源类型和创建时间、标签胶囊。
- 标签胶囊在列表和详情中复用，支持新增、删除和完成编辑；点击控件外部、关闭详情或退出批量模式时自动保存。
- 收藏详情标题下方展示来源类型、创建时间和标签；详情正文使用收藏快照。
- `max-width: 650px` 时，收藏列表保持单列，选中详情以后覆盖在列表上方，并提供 `返回收藏列表`。

## 5. 底部统一输入区（全版本统一）

底部输入区 `.assistant-composer` 是首页、报告和生活场景共享的视觉区域。当前只有首页场景允许输入和发送；报告、生活场景复用占位 placeholder，但 textarea 禁用且提交不会发起请求。空首页时，提示文案和输入区组成居中引导；进入真实对话后，输入区再回到底部悬浮层。代码不为报告/生活维护独立草稿；离开空白首页草稿到收藏、设置、原始文件或占位场景时，会临时保存首页草稿并在“开启新对话”回到首页时恢复。

输入区包含：

- 多行文本输入框。
- 文件上传按钮（当前显示为回形针图标，背后使用隐藏 file input，保留 `附加文件` 可访问名称）。
- 待发送附件和历史引用提示。
- 模型与推理强度组合选择器。
- 发送按钮。

输入区不展示快捷问题或示例提问按钮，例如不主动给出“是否需要马上去医院”这类建议问题。用户输入 Markdown 源文本；输入输出内容使用 Markdown 渲染，包含用户消息、助手回答、思考过程和收藏快照。

对话布局要求：

- 思考过程以可折叠区域显示，用户可展开或收起。
- 空首页的提示文案和输入框必须作为一个整体在首页内容区居中；提示字号和提示到输入框的间距必须使用固定值，不随视口宽度、高度或断点变化。有消息后，只有对话历史区域可以滚动，底部输入区固定在工作区底部并作为覆盖式悬浮层浮在对话历史上方。
- 对话历史内容不得出现在输入框下方；历史滚动容器应保留输入区遮挡安全距离，让滚动条属于整块对话历史区域并尽量贴近工作区最右侧。
- 最新生成过程、助手回答和对话历史尾部在自动滚动到最新时必须显示在输入框上方，不得被悬浮输入框遮挡或落到输入框背后。
- 输入框默认保持较矮高度；输入框随输入行数逐步增高，到达阈值后改为输入框内部滚动。
- 输入框行数增多时，只允许输入框自身增高或内部滚动；对话历史滚动容器的高度、滚动范围和滚动条位置只随对话历史内容变化，不随输入内容行数变化。
- 对话历史列和悬浮输入框必须使用同一条居中列宽和响应式左右留白，左右边缘也必须对齐；不得使用固定像素 inset 或 JS offset 硬凑；滚动条预留空间不得造成历史列与输入框左右错位。
- 对话历史正文、思考块和输入框可输入文字的起点必须保持一致，不能只让外框对齐却让文字起点错位；历史内容与输入内容的左右内边距要按同一基准设计。
- `conversation-surface`、`message-list` 和 `conversation-composer` 的关系必须保持稳定：`conversation-surface` 是唯一历史滚动容器，`message-list` 只承载消息和尾部安全留白，`conversation-composer` 是覆盖在历史上方的悬浮输入层。
- 更新输入框高度只允许更新 `--composer-overlay-height` 以调整尾部安全留白，不允许主动修改 `conversation-surface.scrollTop`，也不允许通过改变历史容器高度来容纳输入框。
- 多行输入框所有行的输入光标高度必须一致，并与当前文字字号和行高一致，不得出现明显高于文字的 caret。
- 输入区视觉只保留一个柔和悬浮容器；textarea、模型选择和附件等内部控件默认弱化或取消描边，聚焦时再给出清晰边框或 focus ring，不用发光阴影制造层级。
- 对话过程中主标题显示当前会话标题；没有打开会话时才使用首页引导标题。
- 打开历史会话时先清空旧滚动位置，再按最新消息定位；自动滚动锚定最新消息本身，不锚定底部输入框留白。
- 快速切换 `/chat/{session_id}`、点击历史会话或开启新对话时，前端必须忽略过期的会话详情响应，避免旧请求覆盖当前页面。

发送按钮行为：

- 当前视觉为向上箭头图标，保留 `发送` 可访问名称；提交中使用 `发送中...` 可访问名称。
- 没有文本且没有上下文资源时，当前实现直接忽略提交并清空输入区错误，不发起后端请求；已有附件或历史引用等上下文资源时可发送无文本消息。
- 提交中禁用重复发送。

推理强度选择器：

| UI 文案 | payload 值 | 用途 |
| --- | --- | --- |
| 默认强度推理 | `default` | 平衡速度与完整性 |
| 关闭推理 | `fast` | 关闭额外推理，直接输出回答 |
| 低强度推理 | `low` | 轻量推理 |
| 中强度推理 | `medium` | 中等分析深度 |
| 高强度推理 | `high` | 更深入展开依据与建议 |
| 超高强度推理 | `xhigh` | 仅在模型能力声明支持时展示 |

触发按钮里的推理强度 chip 使用短文案，例如 `默认`、`关闭`、`低`、`中`、`高`、`超高`；浮层菜单仍展示完整推理强度文案。选择器使用固定定位 sheet，主弹层内推理强度选项和当前模型入口等宽，内部按“推理强度区域 + 分隔线 + 模型列表区域”组织，模型列表嵌在同一个 sheet 内并独立滚动，不使用桌面二级浮层。选择器支持当前项标记，并在外部点击、切换场景、选择推理强度或模型后关闭。模型列表展示当前账号已添加模型，并将 `chat` 默认模型置顶；选择后更新当前模型并按模型能力刷新可用推理强度和附件按钮可见性。上传和真实发送阶段仍以后端 `chat` 默认模型校验为准。

模型配置：

- 支持 `openrouter`、`deepseek`、`aliyun_bailian` 三类模型服务，其中 `deepseek` 的显示名为 `深度求索`。
- 用户可在账号设置的 `模型提供方` 页选择模型服务；前端自动填充官网地址和 API 地址，用户可修改并输入 API key。
- 官网地址、API 地址和 API key 输入后自动保存到当前账号模型服务配置；测试连接只负责验证当前表单值。
- `添加模型` 弹窗调用模型列表接口获取远端模型，后端必须使用已保存的 API 地址和 API key 请求模型服务的 `/models` 接口，用户从真实远端返回列表中添加可用模型；前端不得对远端列表重新排序。
- 远端模型能力必须由后端按模型服务归一化为独立字段：`supports_text`、`file_mime_types`、`thinking_modes`、`supports_tool_calling`、`supports_json_output`、`context_window_tokens`、`max_output_tokens`。前端添加模型时逐项提交这些字段，不提交统一的 `capabilities` JSON，不提交 `supports_vision`。
- 附件能力只由 `file_mime_types` 判断；图片、音频、视频等视觉或多模态能力不再用单独布尔字段表达。
- 能力归一化按模型服务适配：OpenRouter 读取 `architecture` 和 `supported_parameters`；深度求索按官方模型 ID 和参数文档判断；阿里云百炼按模型 ID、深度推理模式和模型目录规则判断，其中 `qwen3.5`、`qwen3.6`、`qwen3-vl` 系列按图片+视频输入处理，`qwen3.5-omni` 与 `qwen3-omni` 系列按图片+音频+视频输入处理，普通 `qwen3.7-max`/`qwen3-max` 不因版本号自动开放附件。无法识别时使用保守默认能力。
- API key 由模型服务接口明文返回并回填到设置表单，不写入前端本地持久化存储。
- 模型服务配置、API key、已添加模型和默认模型用途均按当前登录账号隔离；切换账号后需加载该账号自己的模型配置。

---

## 6. v0.1.0 前端设计

本节描述 v0.1.0 正式交付的前端能力。

### 6.1 场景结构

| 场景 | 状态 | 主要用途 |
| --- | --- | --- |
| 首页 | 正式交付 | 基础对话、AI 结果承接 |
| 报告 | 视觉占位 | 不交付正式报告能力 |
| 生活 | 视觉占位 | 不交付正式生活管理能力 |

`报告`、`生活` 入口位于左侧侧栏，点击后停留在 `/` 并切换当前占位场景。`首页` 在开启新对话、打开会话或回到主对话工作区时使用。当前输入草稿、附件状态和错误状态由底部统一输入区维护，不为占位场景提供单独的快捷提问建议。

### 6.2 首页设计

首页有两种视觉状态：

- pristine：没有打开会话时，展示首页引导标题和底部输入区。
- conversation：已有会话时，主标题显示当前会话标题，展示用户消息气泡、思考过程、AI 结果气泡和收藏入口。

登录后首次进入 `/` 时，如果账号存在历史会话，当前代码会自动打开最近一条会话；pristine 状态主要出现在新账号、点击“开启新对话”或恢复空白首页草稿时。

AI 结果由统一转换层处理为前端展示模型，避免直接把后端 JSON 原样铺到页面。

### 6.2.1 当前工作台交互定稿

本节记录当前界面已经定稿并落地的规则：

- 品牌区只展示 `Serenita`。
- 左侧导航支持折叠。
- 窄屏下左侧导航改为抽屉，抽屉断点与收藏页侧栏开关共用 `max-width: 1000px`。
- 左侧导航和右侧主页之间只使用一条竖向分隔线。
- 左侧导航、会话列表、设置列表和收藏列表的默认条目不画独立边框，当前项通过浅紫灰背景块和文字权重突出；hover 只使用轻背景，不额外叠加投影。
- 会话标题限制在左侧导航栏内部，超长文本使用省略号截断。
- `原始文件` 排在 `我的收藏` 上方，并固定在账号按钮上方的底部辅助区。
- 会话列表不显示 `最近会话` 或 `最近对话` 标题。
- 会话删除按钮使用悬浮垃圾桶图标。
- 左下角账号按钮点击后直接进入 `/setting`，退出登录位于设置页一级导航。
- `报告`、`生活` 场景入口位于左侧栏；首页工作区顶部不再放置居中场景入口。
- 对话过程中主标题显示当前会话标题。
- 输入区不展示快捷问题或示例提问按钮。
- 第一轮对话后应从首条用户问题生成简短标题，不直接把整句问题当会话标题。
- 输入输出内容使用 Markdown 渲染。
- 思考过程以可折叠区域显示：生成中显示 `正在思考`，完成后显示 `思考完成（用时 x秒）`。
- 思考仍在生成且助手正文尚未开始时，不展示空的正式回复显示区；正文开始流式输出后再展示助手消息气泡。
- 流式生成期间，输入区右侧发送按钮替换为同位置、同尺寸的圆形停止按钮，图标使用方形停止符号；停止入口不额外出现在消息动作区。
- 空首页的提示文案和输入框必须作为一个整体在首页内容区居中，且提示字号和提示到输入框的间距不随响应式布局变化；进入对话后，对话历史滚动条属于整块会话区域，输入框浮在会话历史上方且与最新回答保持紧凑留白。输入框高度应保持紧凑，内部按钮尺寸贴合文字和图标，不做夸张大按钮。
- 对话历史末尾保留真实尾部留白，确保最新生成过程、最新回答和最新历史记录自动显示在输入框上方，不会被悬浮输入框遮挡，也不会落到输入框下方。
- 自动滚动到最新内容时，应根据最新消息元素和悬浮输入区高度计算目标滚动位置，至少保留一段最新消息可见区域；不得简单滚到 `scrollHeight` 末尾导致最新消息被输入区尾部留白误导。
- 输入框默认保持较矮高度，随输入行数逐步增高，到达阈值后改为输入框内部滚动；输入框行数变化不得改变对话历史滚动容器的高度、滚动范围或滚动条位置，历史滚动条只跟随历史内容变化。
- 对话历史列和悬浮输入框必须使用同一条居中列宽和响应式左右留白，左右边缘也必须对齐；不得使用固定像素 inset 或 JS offset 硬凑；滚动条预留空间不得造成历史列与输入框左右错位。
- 对话历史正文、思考块和输入框可输入文字的起点必须保持一致，不能只让外框对齐却让文字起点错位；历史内容与输入内容的左右内边距要按同一基准设计。
- `conversation-surface`、`message-list` 和 `conversation-composer` 的关系固定为滚动层、消息内容层和悬浮输入层；更新输入框高度只允许更新 `--composer-overlay-height`，用于同步消息列表尾部安全留白。
- 多行输入时，所有行的输入光标高度必须一致，并与文字字号和行高一致。
- 悬浮输入框不使用发光阴影；聚焦时只改变边框状态，不制造光晕。
- AI 回答操作区使用图标按钮：复制、重新生成、分支和星标收藏。
- 用户在流式生成中向上浏览历史时，自动滚动不得强行把历史拉回底部；只有用户仍停在历史尾部附近时才自动跟随最新输出。
- 重新生成和切换分支不得给历史消息气泡或思考过程画绿色边框、绿色文本框或其它输入框式高亮；滚动定位状态只用于定位，不作为气泡视觉状态。
- 点击 AI 回答的分支按钮后，该按钮显示与复制成功一致的对勾反馈；分支起点之后的历史消息临时隐藏，并在下方展示带左右横线的 `恢复分支前对话` 按钮，用户可用它取消临时分支预览。
- 会话列表删除按钮和选中文本的“添加到对话”浮层必须固定在原定位，不受全局按钮 hover 位移影响。

### 6.3 报告与生活占位

v0.1.0 中，`报告` 和 `生活` 场景只保留视觉占位和轻量引导，不允许从这两个场景发起真实大模型请求。

首页聊天仍支持通过共享输入区上传上下文资源；当前代码完成资源保存、能力校验和本轮引用写入。发送时，若 `chat` 模型原生支持附件 MIME，后端直接转发给 `chat` 模型；若 `chat` 模型不支持但 `vision_parse` 模型支持，后端直接调用视觉解析模型并把附件作为原生输入发送，由 `vision_parse` 生成本轮回答；两者都不支持时拒绝上传或发送。该能力只用于会话时间线和本轮 AI 上下文，不触发报告结构化字段抽取、指标入库或报告列表刷新。

分屏对话模式不属于 v0.1.0 交付范围，放入 v0.2.0 或后续版本设计。

### 6.4 状态管理

当前使用 React 本地状态管理，不引入全局状态库。

主要状态包括：

- `route`：当前前端路由，支持 `/sign_in`、`/sign_up`、`/`、`/favorites`、`/setting`。
- `/chat/{session_id}`：指定会话路由，仍复用患者主工作台外壳。
- `session`：当前认证状态。
- `useWorkspaceRouteShell()`、`useResponsiveSidebar()`：桌面折叠、窄屏抽屉、当前侧栏模式和主区侧栏 toggle。
- `useWorkspacePageModel()`：登录后工作台 hook 编排、会话/收藏/附件/模型状态组合和 route content 入参聚合。
- `WorkspaceRouteContent`：登录后 route 分支、`WorkspaceRouteShell` 包装、首页/收藏/设置工作区入口分发。
- `activeView`：主工作台右侧视图，当前支持 `home` 和原始文件占位；代码内部仍使用 `health` 作为原始文件占位视图 key。
- `activeScenario`：首页工作区内的 `home`、`reports`、`lifestyle` 场景。
- `useConversationPageState()`：首页对话页本地状态和 DOM refs 初始化。
- `ConversationWorkspacePanel`：首页对话工作区状态/动作分组到 surface props 的接线层。
- `ConversationWorkspaceSurface`：首页对话的消息列表、输入区、模型控件和分支控件拼装。
- `useConversationViewState()`：首页标题、消息索引、分支预览截断、可见消息和附件能力派生状态。
- `composerText`、`composerError`、`sending`：输入区文本、错误和提交状态。
- `activeStreamRef`、`activeStreamTurnId`、`cancellingTurnId`：当前流式生成请求、对应轮次和取消中的轮次。普通停止生成会保存半截回答；重新生成触发的停止会丢弃半截回答。
- `currentSessionId`、`conversationDetail`、`conversations`、`conversationRequestSeqRef`：当前会话、会话详情、最近会话列表和会话详情请求序号。
- `useConversationLifecycle()`：初始数据加载、指定会话路由恢复、打开/删除会话、开启新对话、退出登录和工作台重置。
- `useConversationLayout`、`messageRefs`、`messageListRef`、`conversationSurfaceRef`、`composerRef`：消息列表、历史滚动容器、会话切换滚动重置、高亮来源消息定位、自动跟随状态、输入区高度测量和滚动条补偿。
- `uploadedResources`、`quotedContext`、`parentForNextMessage`：文件上下文、历史引用和分支起点。
- `useConversationWorkspace()`：会话发送、重新生成、提交对话消息动作和会话列表刷新。
- `useConversationStreamController()`：流式响应、停止生成、思考状态和 active stream 清理。
- `useConversationMessageActions()`：复制消息、历史选区引用、编辑历史提问和提交编辑草稿动作。
- `useConversationBranching()`：兄弟分支计算、分支切换、分支起点预览和恢复。
- `useConversationAttachments()`：附件上传、上传进度同步、会话详情同步、按模型能力过滤待发送附件和待发送附件移除。
- `useConversationModelControl()`：当前 `chat` 默认模型、推理强度和组合弹层状态。
- `FavoritesWorkspacePanel`：收藏页右侧工作区外壳、收藏状态传递、侧栏开关和来源会话跳转接线。
- `useFavoriteWorkspace()`：收藏列表、详情、是否处于批量选择模式、已选收藏、列表/详情标签编辑、新增标签输入和待保存标签。
- `useFavoriteMessageActions()`：对话消息收藏/取消收藏、收藏列表刷新和收藏错误提示。
- `useFavoriteListAlignment()`：收藏列表滚动条 gutter 测量、`--favorite-list-end-compensation` 设置和列表/工具栏末端对齐。
- `SettingsWorkspacePanel`：账号设置页右侧工作区外壳、顶部标题栏、侧栏开关传递和模型列表刷新回写。
- `SettingsShell` 内部维护 `activeSection`、`accountPanel`、`providers`、`drafts`、`remoteModels`、`addedModels` 和连接测试状态。

### 6.5 接口对接

v0.1.0 前端对接以下接口（技术入口见 `docs/releases/v0.1.0/technical/README.md`，需求入口见 `docs/releases/v0.1.0/prd/README.md`）：

| 函数 | HTTP 接口 | 用途 |
| --- | --- | --- |
| `signUp` | `POST /api/auth/sign_up` | 注册账号 |
| `signIn` | `POST /api/auth/sign_in` | 登录 |
| `signOut` | `POST /api/auth/sign_out` | 退出登录 |
| `checkSession` | `GET /api/auth/session` | 会话恢复 |
| `updateAccount` | `PATCH /api/auth/account` | 修改当前账号资料 |
| `changePassword` | `PATCH /api/auth/password` | 修改当前账号密码 |
| `fetchModelProviders` | `GET /api/model-providers` | 获取模型服务配置 |
| `saveModelProvider` | `POST /api/model-providers` | 自动保存模型服务配置、官网地址、API 地址和 API key |
| `updateModelProvider` | `PATCH /api/model-providers/{provider_id}` | 更新模型服务配置 |
| `testModelProvider` | `POST /api/model-providers/{provider_id}/test` | 测试模型服务连接 |
| `fetchProviderModels` | `GET /api/model-providers/{provider_id}/models` | 获取模型服务的模型列表 |
| `addModel` | `POST /api/models` | 添加可用模型并提交拆分后的模型能力字段 |
| `fetchModels` | `GET /api/models` | 获取已添加模型 |
| `deleteModel` | `DELETE /api/models/{model_id:path}` | 删除已添加模型；`model_id` 可能包含 `/`，请求路径必须 URL 编码 |
| `fetchModelDefaults` | `GET /api/model-defaults` | 获取 `chat`、`title`、`vision_parse`、`compact` 默认模型用途设置 |
| `updateModelDefaults` | `PATCH /api/model-defaults` | 批量更新默认模型用途设置 |
| `uploadContextResource` | `POST /api/conversations/context-resources` | 上传上下文资源 |
| `sendMessage` | `POST /api/conversations/messages` | 发送对话消息 |
| `fetchConversations` | `GET /api/conversations` | 获取会话列表 |
| `getConversation` | `GET /api/conversations/{session_id}` | 获取会话详情 |
| `regenerateMessage` | `POST /api/conversations/{session_id}/messages/{message_id}/regenerate` | 重新生成助手回答 |
| `cancelTurn` | `POST /api/conversations/{session_id}/turns/{turn_id}/cancel` | 取消生成；普通停止保存半截回答，重新生成前取消丢弃半截回答 |
| `deleteConversation` | `DELETE /api/conversations/{session_id}` | 删除会话 |
| `setActivePath` | `PATCH /api/conversations/{session_id}/active-path` | 切换分支/更新活动路径 |
| `fetchFavorites` | `GET /api/favorites` | 获取收藏列表 |
| `getFavorite` | `GET /api/favorites/{favorite_id}` | 获取收藏详情 |
| `createFavorite` | `POST /api/favorites` | 创建收藏 |
| `updateFavorite` | `PATCH /api/favorites/{favorite_id}` | 编辑收藏标签 |
| `deleteFavorite` | `DELETE /api/favorites/{favorite_id}` | 取消收藏 |
| `batchDeleteFavorites` | `POST /api/favorites/batch-delete` | 批量取消收藏 |

接口基地址优先读取 `VITE_API_BASE_URL`。本地开发默认使用同源 `/api`，由 Vite 代理转发到 `http://127.0.0.1:8000`，避免浏览器在 `localhost` 与 `127.0.0.1` 之间产生跨源网络失败。

---

## 7. v0.2.0 前端设计

本节描述 v0.2.0 在 v0.1.0 基础上新增的前端能力。

### 7.0 前端与后端契约对齐

v0.2.0 前端展示后端已经拆分和入库的报告记录。报告上传后的复杂业务判断由后端完成，前端负责展示状态、确认动作和刷新列表详情。

| 规则 | 前端行为 |
| --- | --- |
| 批量上传逐文件处理 | 单批最多选择 20 个文件，并分别展示上传、解析、重复待确认、成功或失败状态 |
| 报告统一视觉解析 | 图片和 PDF 使用当前账号的 `vision_parse` 默认模型，缺少配置时引导用户进入设置 |
| 检验报告按功能分类拆分 | 报告列表直接展示后端返回的多个 `LAB-` 报告，例如肝功能、肾功能、血脂 |
| 检查报告按原分类展示 | 详情展示检查名称、检查时间、临床诊断、检查方法、检查表现、检查诊断或结论 |
| 其它报告保留原文 | 详情展示报告名称、时间和完整原文 |
| 病理与手术报告按固定分类展示 | 病理报告展示四个分类，手术报告展示十三个分类；缺失字段显示为空 |
| 源文件可关联多份报告 | 报告详情展示关联的原始文件来源 |
| 疑似重复报告需要确认 | 首页展示重复报告确认卡片，用户选择后调用确认接口 |
| 同日新证据影响既有分析 | 后端后台自动重跑受影响分析；前端刷新列表和详情状态 |
| 检验趋势按需生成 | 只为 `LAB-` 报告渲染临时返回的 `trend_data`，不持久化绘图值 |
| 写入类自然语言动作 | 前端展示待确认卡片，确认成功后刷新报告数据 |
| 报告聊天复用现有会话 | 左侧展示聊天，右侧展示可折叠报告，聊天末尾展示实际读取或操作过的报告和文件索引 |

### 7.1 场景结构变更

| 场景入口 | 状态 | 变更 |
| --- | --- | --- |
| 首页 | 正式交付 | 新增报告上传进度、确认卡片、分析结果承接 |
| 报告 | 正式交付 | 从占位升级为正式报告场景 |
| 生活 | 视觉占位 | 不变 |

### 7.2 报告场景设计

报告场景默认使用双栏布局 `.report-tab-layout`：

- 左侧：筛选区 + 报告列表（数量、排序按钮、报告条目）。
- 右侧：选中报告详情。

类型筛选固定包含：全部、检验报告、检查报告、病理报告、手术报告、其它报告。

报告列表项展示：

- 报告类型。
- 报告名称或功能分类，例如肝功能、肾功能、血脂。
- 报告时间。
- 解析或分析状态。
- 异常指标数量。

报告详情展示：

- 报告基本信息（类型、时间、状态）。
- 检验报告展示对应功能分类下的指标列表；结果和参考值按数据库中的原始文本展示，使用解析阶段返回的方向，异常或偏高只显示 `↑`、偏低只显示 `↓`、无异常或无法判断不显示标记，前端不自行计算方向。
- 检查报告展示检查名称、检查时间、临床诊断、检查方法、检查表现、检查诊断或结论。
- 病理报告只展示送检标本、巨检、诊断、取材位置四个分类。
- 手术报告只展示术前诊断、术中诊断、麻醉方法、开始时间、结束时间、是否输血、术中失血量、术中尿量、术中输血量、术中输液量、术中其他用药、手术经过、术后生命体征十三个分类。
- 其它报告展示报告名称和正文。
- 分析结果或"分析此报告"按钮。
- 检验报告展示趋势图和指标切换；其它报告类型不展示趋势图。
- 修改和删除入口。
- “聊天”入口。

点击"分析此报告"后界面切回首页展示分析进度和结果。

点击“聊天”后，主工作区切换为 `.report-chat-layout`：

- 左侧为现有会话消息、流式输出和输入区。
- 右侧为当前报告详情或原始文件预览，并提供折叠按钮。
- 报告与文件索引位于聊天末尾、输入区上方，聚合当前活动消息路径中实际读取、修改、确认写入或分析报告的 `context_resources`。
- 点击报告索引在右侧打开该报告；点击文件索引在右侧预览原始文件。
- 折叠右侧面板后，聊天区域填充剩余宽度。
- 报告聊天保存到现有会话历史，显示在全局左侧导航栏；恢复历史会话时按最近的报告引用恢复右侧面板。
- 会话状态沿用现有会话结构，报告上下文由消息级 `context_resources` 承载。

### 7.3 首页新增卡片

v0.2.0 首页新增以下卡片类型：

- 上传进度卡片：按文件展示"上传中"、"解析中"、"处理成功"或"处理失败"状态。
- 重复报告确认卡片：当电子截图、纸质扫描件等文件疑似对应已有报告时展示，提供"作为补充文件保存"、"用本次解析结果更新"和"仍作为新报告保存"。
- 入库确认卡片：展示报告类型、时间、指标数量、异常数量、"开始分析"和"暂不分析"按钮。
- 分析结果卡片：按结构化板块展示分析结果，底部提供"查看该报告"跳转。

### 7.4 文件上传行为

- 通过底部输入区 `+` 按钮触发隐藏 input。
- 支持 PDF、JPG、PNG、HEIC，文件选择控件启用 `multiple`。
- 第一版单批最多 20 个文件。
- 单文件上限 20MB。
- 批量上传按文件显示独立状态，单个文件失败不阻断其它文件，并提供单项重试。
- 上传开始后界面切回首页展示处理进度。
- 上传解析后若命中疑似重复报告，首页展示重复报告确认卡片。
- 用户选择"作为补充文件保存"后，报告详情刷新原始文件来源。
- 用户选择"用本次解析结果更新"后，前端先展示差异确认；确认成功后刷新报告详情，并提示已有分析可能需要重新生成。
- 用户选择"仍作为新报告保存"后，才刷新报告列表并选中新报告。
- 上传成功或重复处理导致结构化数据变化后，若后端返回受影响分析状态，前端刷新报告列表和详情状态。
- 上传成功且未命中重复时刷新报告列表。
- 上传失败展示错误提示和重试入口。

### 7.5 接口新增

v0.2.0 前端新增对接以下规划接口（详见 v0.2.0 PRD 第 8 节）。这些接口不是 v0.1.0 当前代码能力；当前代码只实现报告占位接口 `GET /api/reports`。

| 函数 | HTTP 接口 | 用途 |
| --- | --- | --- |
| `uploadReports` | `POST /api/upload-report` | 批量上传报告文件 |
| `fetchReportUploadBatch` | `GET /api/report-upload-batches/{upload_batch_id}` | 轮询当前后端运行期间的临时批次状态 |
| `fetchReports` | `GET /api/reports` | 获取报告列表 |
| `fetchReport` | `GET /api/reports/{report_id}` | 获取报告详情 |
| `updateReport` | `PUT /api/reports/{report_id}` | 修改报告基本信息 |
| `deleteReport` | `DELETE /api/reports/{report_id}` | 删除报告 |
| `analyzeReport` | `POST /api/reports/{report_id}/analysis` | 触发报告分析 |
| `sendMessage` | `POST /api/conversations/messages` | 复用现有会话发送报告问答、对比和修正请求 |
| `fetchDailyAnalysisStatus` | `GET /api/reports/daily-analysis-status` | 同日分析状态 |
| `confirmReportAction` | `POST /api/reports/pending-actions/{action_id}/confirm` | 确认重复报告处理、结构化修正或删除等待确认动作 |
| `cancelReportAction` | `POST /api/reports/pending-actions/{action_id}/cancel` | 取消待确认动作 |

### 7.6 状态管理扩展

v0.2.0 新增以下状态：

- `reports`：报告列表数据。
- `selectedReport`：当前选中报告。
- `reportFilters`：筛选条件（类型、时间范围、排序方向）。
- `uploadBatches`：仅在前端内存中按 `upload_batch_id` 保存当前运行期间的逐文件状态；不写入本地数据库，刷新或重启后以正式报告列表为准。
- `reportPanelCollapsed`：当前报告聊天视图的右侧面板折叠状态，不写入会话记录。
- `reportContextIndex`：从当前活动消息路径的 `context_resources` 派生的报告与文件索引。
- `duplicateReportAction`：疑似重复报告的待确认动作、已有报告摘要、解析预览和处理选项。
- `analysisStatus`：分析进度状态，包含单报告分析和后台自动重跑状态。

---

## 8. 设计边界

以下能力不属于 v0.1.0 或 v0.2.0 交付范围，需后续版本产品化：

- 语音输入闭环。
- HealthKit 授权与真实数据接入。
- 健康卡片（心率、血压、血糖等 HealthKit 数据展示）。
- 生活场景正式能力。
- 完整患者档案。
