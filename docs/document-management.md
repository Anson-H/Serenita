# 文档管理规则

> 文档状态：文档规则 / 当前口径约束
> 当前用途：规定当前执行、规划、草案和历史记录文档的组织方式与取信规则。

## 目标

Serenita 的文档管理目标是把“当前交付范围”“下一版本规划”“长期愿景”和“历史工作记录”分清楚，按版本组织文档，打开一个版本目录就能看到该版本的全貌。

## 文档状态

| 状态 | 含义 | 是否可直接开发 |
| --- | --- | --- |
| 当前执行 | 当前执行版本，已经完成范围冻结 | 是 |
| 下一规划 | 下一规划版本，依赖当前版本稳定 | 否，需要二次确认 |
| 长期草案 | 长期方向草案或能力池 | 否 |
| 技术草案 | 技术探索、未来架构或实现参考 | 否 |
| 技术参考 | 可被多个版本引用的技术说明 | 视具体版本产品需求文档而定 |
| 历史记录 | 已完成或阶段性工作记录 | 否 |

## 目录结构

```text
docs/
  roadmap.md                   # 产品路线图
  document-management.md       # 本文件
  shared/                      # 跨版本复用的参考文档
    frontend-backend-responsibilities.md
    frontend-design.md
    local-storage-structure.md
  superpowers/                 # 历史规格、计划和执行记录
  releases/                    # 按版本组织，每个版本一个目录
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

## 命名规则

- 版本目录：`releases/v{x.y.z}/`，草案版本加 `-draft` 后缀
  - `x`：重大架构变化
  - `y`：新增功能
  - `z`：小修小改 / Bug 修复
- 文件名表达文档主题，不重复版本号；多模块版本可用 `prd/` 和 `technical/` 子目录收纳模块文档
- 跨版本复用的文档放 `shared/`，按领域命名

## 更新规则

- 修改产品需求文档前先确认文档状态。
- 当前执行文档只接受与当前版本目标相关的修改。
- 新增功能必须先进入对应产品需求文档，再进入验收清单，最后进入开发任务。
- 下一规划、长期草案、技术草案不得覆盖当前执行版本的范围、接口和存储约定。
- 长期草案中的能力不得直接进入开发，必须拆成明确版本范围。
- `superpowers/` 下的规格和计划是历史工作记录；当它们和当前执行文档或当前代码不一致时，以当前执行文档和代码为准。

## 当前约定

- `v0.1.0` 是当前执行版本。
- `v0.2.0` 是下一规划版本。
- `v1.0.0` 是长期方向草案，不是当前开发版本。
- 当前执行版本由当前执行产品需求文档、验收清单和技术设计定义。
- `shared/`、`v0.2.0` 或 `v1.0.0-draft` 中的术语、接口、目录结构、技术选型出现差异时，先回到当前执行版本文档确认，不直接进入开发。
- 文档同步代码时，需要同时检查 `backend/README.md`、`frontend/README.md`、根目录 `README.md`、当前执行产品需求文档、当前执行技术设计、验收清单和 `shared/` 参考文档。
