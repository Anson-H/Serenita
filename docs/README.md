# Serenita 文档中心

> 文档状态：文档索引 / 当前口径入口
>
> 当前用途：说明各版本文档、共享参考文档和历史工作记录之间的关系。当前执行范围以 `docs/releases/v0.1.0/` 为准。

本目录用于集中管理 Serenita 的产品、技术、验收和工程参考文档。当前文档口径已按仓库代码同步：`v0.1.0` 是执行版本，`v0.2.0` 和 `v1.0.0-draft` 只作为规划或历史草案。

## 当前版本定位

| 层级 | 版本 | 状态 | 说明 |
| --- | --- | --- | --- |
| 当前执行 | `v0.1.0` | 当前执行 | 注册与登录、账号设置页、模型配置、首页对话、文件上下文登记、会话历史/分支、收藏闭环 |
| 下一规划 | `v0.2.0` | 下一规划 | 在 `v0.1.0` 稳定后新增报告场景，不作为当前开发依据 |
| 长期方向 | `v1.0.0` | 长期草案 | 未来能力池和产品蓝图，尚未冻结范围 |

## 当前执行文档

当前执行版本文档集中在 `docs/releases/v0.1.0/`：

- [v0.1.0 需求文档索引](releases/v0.1.0/prd/README.md)
  - [账号注册与登录 产品需求文档](releases/v0.1.0/prd/auth.md)
  - [账号设置 产品需求文档](releases/v0.1.0/prd/account-settings.md)
  - [首页对话 产品需求文档](releases/v0.1.0/prd/home-conversation.md)
  - [收藏 产品需求文档](releases/v0.1.0/prd/favorites.md)
- [v0.1.0 验收清单](releases/v0.1.0/acceptance.md)
- [v0.1.0 技术设计索引](releases/v0.1.0/technical/README.md)
  - [账号注册与登录技术设计](releases/v0.1.0/technical/auth.md)
  - [账号设置技术设计](releases/v0.1.0/technical/account-settings.md)
  - [首页对话技术设计](releases/v0.1.0/technical/home-conversation.md)
  - [收藏技术设计](releases/v0.1.0/technical/favorites.md)

其它文档保留为规划、参考或历史工作记录，不承担当前执行范围定义。

## 当前代码实现摘要

- 后端是 `backend.app.main:create_app` 创建的 FastAPI 应用，启动时会执行模型能力字段迁移。
- 前端是 React + Vite 工作台，当前受保护路由为 `/`、`/chat/{session_id}`、`/favorites` 和 `/setting`，认证路由为 `/sign_in` 和 `/sign_up`。
- 账号设置从左下角账号按钮直接进入 `/setting` 页面，并保留左侧主工作栏；退出登录位于设置页一级导航。
- API 基地址默认是同源 `/api`，本地由 Vite 代理到 `http://127.0.0.1:8000`。
- 本地数据根目录优先读取 `SERENITA_DATA_ROOT`，未配置时落到仓库根目录的 `serenita_files/`。
- 当前对话服务会校验模型、推理强度和上下文资源，并持久化会话时间线；发送接口创建 `streaming` 轮次，流式接口消费后才调用已配置模型服务生成回答。
- 首页文件上传已完成保存、过期和模型 MIME 能力校验。上传和真实发送均以账号的 `chat` 默认模型为后端请求模型；发送时，若 `chat` 模型原生支持附件 MIME，后端直接转发给 `chat` 模型；若 `chat` 模型不支持但 `vision_parse` 默认模型支持，后端直接调用视觉解析模型并把附件作为原生输入发送，由 `vision_parse` 生成本轮回答；两者都不支持时拒绝上传或发送。
- 仅上传文件但尚未发送消息时，对话服务会保留草稿会话和待发送资源，但该草稿不进入最近会话列表；发送首条用户消息后才进入列表。
- 前端进入登录后工作台时会拉取会话、收藏、已添加模型和默认模型；如果当前路径不是 `/chat/{session_id}` 且存在历史会话，会自动打开最近一条会话。
- `GET /api/reports` 仅返回空列表，报告、生活和原始文件入口在 `v0.1.0` 仍为占位边界。

## 前后端职责速览

- 前端负责界面、路由、交互状态、流式展示和调用后端接口。
- 后端负责登录态、权限隔离、业务校验、模型服务调用、本地文件和数据库持久化。
- 前端不直接读写 SQLite/JSONL，也不直接调用大模型；后端不负责页面布局和浏览器交互。

详细说明见 [前端与后端职责边界](shared/frontend-backend-responsibilities.md)。

## 推荐阅读顺序

1. [v0.1.0 需求文档索引](releases/v0.1.0/prd/README.md)
2. [v0.1.0 验收清单](releases/v0.1.0/acceptance.md)
3. [v0.1.0 技术设计索引](releases/v0.1.0/technical/README.md)
4. [产品路线图](roadmap.md)
5. [文档管理规则](document-management.md)
6. [前端与后端职责边界](shared/frontend-backend-responsibilities.md)
7. [v0.2.0 产品需求文档](releases/v0.2.0/prd.md)
8. [v0.2.0 技术文档](releases/v0.2.0/technical.md)
9. [v1.0.0 长期方向草案](releases/v1.0.0-draft/vision.md)
10. [本地文件存储结构](shared/local-storage-structure.md)
11. [前端设计说明](shared/frontend-design.md)

## 目录说明

```text
docs/
  roadmap.md               # 产品路线图
  document-management.md   # 文档状态、命名和更新规则
  shared/                  # 跨版本复用的参考文档
    frontend-backend-responsibilities.md
    frontend-design.md
    local-storage-structure.md
  superpowers/             # 历史规格、计划和工作记录，不作为当前范围来源
  releases/                # 按版本组织，每个版本一个目录
    v0.1.0/
      acceptance.md
      prd/
        README.md
        auth.md
        account-settings.md
        home-conversation.md
        favorites.md
      technical/
        README.md
        auth.md
        account-settings.md
        home-conversation.md
        favorites.md
    v0.2.0/
      prd.md
      technical.md
    v1.0.0-draft/
      vision.md
      architecture.md
      frontend.md
      app-implementation.md
```

## 管理原则

- 当前执行版本由当前执行状态的产品需求文档、验收清单和技术设计定义。
- `shared/` 文档只作为补充参考，不单独扩展当前范围。
- 下一规划文档需要二次确认后才可进入开发范围。
- 长期草案只代表方向，不自动进入开发范围。
- 版本文档集中放在 `docs/releases/{version}/`，代码版本由 Git 分支或 tag 管理。
