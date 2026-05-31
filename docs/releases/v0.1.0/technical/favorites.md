# Serenita v0.1.0 收藏技术设计

> 文档状态：当前执行 / 当前执行版本
>
> 关联产品需求文档：[收藏 产品需求文档](../prd/favorites.md)
>
> 技术设计索引：[README.md](./README.md)

## 1. 接口清单

| 接口 | 说明 |
| --- | --- |
| `GET /api/favorites` | 收藏列表 |
| `GET /api/favorites/{favorite_id}` | 收藏详情 |
| `POST /api/favorites` | 创建收藏 |
| `PATCH /api/favorites/{favorite_id}` | 编辑收藏 |
| `DELETE /api/favorites/{favorite_id}` | 取消收藏 |
| `POST /api/favorites/batch-delete` | 批量取消收藏 |

## 2. 收藏列表

```http
GET /api/favorites
```

要求：

- 返回当前登录 `account` 下的收藏。
- 按 `created_at` 倒序排列。
- 当前代码固定返回最近 50 条收藏，暂不接收分页参数；响应中固定返回 `has_more: false` 和 `next_cursor: null`。
- 列表响应不必返回完整 `content_snapshot`，避免列表过重。

响应示例：

```json
{
  "favorites": [
    {
      "favorite_id": "019db823-1480-700a-8a0a-019db823148b",
      "source_type": "message",
      "source_session_id": "019db81e-80a0-7000-8a00-019db81e80a1",
      "source_id": "019db821-3fc0-7005-8a05-019db8213fc6",
      "title": "肾功能和头晕咨询",
      "content_summary": "肌酐偏高需要结合参考范围、eGFR、年龄、既往结果判断...",
      "tags": ["肾功能", "复查建议"],
      "created_at": "2026-04-23T10:33:00+08:00"
    }
  ],
  "has_more": false,
  "next_cursor": null
}
```

## 3. 收藏详情

```http
GET /api/favorites/{favorite_id}
```

要求：

- 只允许读取当前登录 `account` 名下收藏。
- 详情返回收藏时保存的 `content_snapshot`。
- 若原会话和来源消息仍存在，`source_available` 为 `true`。
- 若原会话已删除，`source_available` 为 `false`，但仍返回快照。
- 当前前端从收藏详情点击“返回原对话”时，会打开 `source_session_id` 对应会话、跳转到 `/chat/{source_session_id}`，并用 `source_id` 高亮来源消息。

响应示例：

```json
{
  "favorite_id": "019db823-1480-700a-8a0a-019db823148b",
  "account": "demo_patient",
  "source_type": "message",
  "source_session_id": "019db81e-80a0-7000-8a00-019db81e80a1",
  "source_id": "019db821-3fc0-7005-8a05-019db8213fc6",
  "source_available": true,
  "title": "肾功能和头晕咨询",
  "content_snapshot": "肌酐偏高需要结合参考范围、eGFR、年龄、既往结果判断...",
  "content_summary": "肌酐偏高需要结合参考范围、eGFR、年龄、既往结果判断...",
  "tags": ["肾功能", "复查建议"],
  "created_at": "2026-04-23T10:33:00+08:00",
  "updated_at": "2026-04-23T10:33:00+08:00"
}
```

## 4. 创建收藏

```http
POST /api/favorites
Content-Type: application/json
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source_type` | string | 是 | v0.1.0 仅支持 `message` |
| `source_session_id` | string | 是 | 来源会话 ID |
| `source_id` | string | 是 | 来源消息 ID |
| `tags` | string[] | 否 | 标签，不传默认为空数组 |

请求示例：

```json
{
  "source_type": "message",
  "source_session_id": "019db81e-80a0-7000-8a00-019db81e80a1",
  "source_id": "019db821-3fc0-7005-8a05-019db8213fc6",
  "tags": ["肾功能", "复查建议"]
}
```

要求：

- `source_type` 仅支持 `message`。
- 后端必须校验 `source_session_id` 属于当前账号。
- 后端必须校验 `source_id` 是该会话内的助手消息。
- 不允许收藏用户消息、思考过程或不存在的消息。
- `title`、`content_snapshot` 和 `content_summary` 均由后端自动填充，前端无需传入，也不得作为可信来源。
- 标题取值为来源会话当前标题；若会话标题仍为“新对话”，后端使用内容前 20 个字符作为标题。
- 同一 `account`、同一来源类型、同一来源会话和同一来源消息不得重复收藏。
- 重复收藏返回 `CONFLICT`。

响应返回收藏详情结构。

## 5. 编辑收藏

```http
PATCH /api/favorites/{favorite_id}
Content-Type: application/json
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 否 | 收藏标题 |
| `tags` | string[] | 否 | 标签 |

请求示例：

```json
{
  "tags": ["肾功能", "复查建议", "下次门诊"]
}
```

要求：

- 只允许编辑当前登录 `account` 名下收藏。
- `title` 传入时，去除首尾空白后不能为空。
- `tags` 传入时覆盖原标签数组；前端在提交前去除首尾空白、过滤空标签并去重，后端仍以收到的数组作为本次覆盖值。
- 更新 `updated_at`。
- 响应返回更新后的收藏详情。

前端当前标签交互：

- 收藏列表和收藏详情共用标签胶囊控件。
- 列表项和详情页均可新增或删除标签；本地先乐观更新 `favorites` 和 `favoriteDetail`，再调用 `PATCH /api/favorites/{favorite_id}`。
- 点击标签控件外部、关闭详情或退出批量选择模式时，会刷新所有待保存标签。
- 批量选择模式中的“设置标签”只负责把已选收藏切换为可编辑状态；具体标签仍通过每条收藏的胶囊控件提交。

## 6. 取消收藏

```http
DELETE /api/favorites/{favorite_id}
```

要求：

- 只允许删除当前登录 `account` 名下收藏。
- 删除收藏不删除原始对话。
- 删除成功后原回答收藏状态应刷新。

前端当前取消收藏入口：

- 当前前端的单条取消收藏入口在原回答收藏按钮上，再次点击已收藏回答会调用 `DELETE /api/favorites/{favorite_id}`。
- 收藏页不提供单条取消收藏按钮；收藏页通过批量选择模式调用 `POST /api/favorites/batch-delete` 删除选中收藏。

响应示例：

```json
{
  "success": true,
  "favorite_id": "019db823-1480-700a-8a0a-019db823148b",
  "message": "已取消收藏"
}
```

## 7. 批量取消收藏

```http
POST /api/favorites/batch-delete
Content-Type: application/json
```

请求示例：

```json
{
  "favorite_ids": [
    "019db823-1480-700a-8a0a-019db823148b",
    "019db824-bb80-700b-8a0b-019db824bb8c"
  ]
}
```

要求：

- 逐条校验收藏是否属于当前账号。
- 已成功删除和失败项应可区分。
- 找不到的收藏项写入 `failed`，不影响其它项删除。
- 批量取消收藏不删除原始对话。

响应示例：

```json
{
  "success": true,
  "deleted_ids": [
    "019db823-1480-700a-8a0a-019db823148b"
  ],
  "failed": [
    {
      "favorite_id": "019db824-bb80-700b-8a0b-019db824bb8c",
      "code": "NOT_FOUND"
    }
  ]
}
```

## 8. 收藏数据存储

收藏数据位于账号私有目录：

```text
{account}/favorites/db_storage/favorites.db
```

`favorites` 表字段：

| 字段 | 说明 |
| --- | --- |
| `favorite_id` | 收藏 ID，主键 |
| `account` | 当前账号 |
| `source_type` | 来源类型，v0.1.0 为 `message` |
| `source_session_id` | 来源会话 ID |
| `source_id` | 来源消息 ID |
| `title` | 收藏标题 |
| `content_snapshot` | 收藏时的完整内容快照 |
| `content_summary` | 列表摘要；保留该字段的意图是数据量很大时，列表查询只读摘要列，不读完整快照 |
| `tags` | 标签 JSON 数组 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

表结构示例：

```sql
CREATE TABLE IF NOT EXISTS favorites (
    favorite_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content_snapshot TEXT NOT NULL,
    content_summary TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account, source_type, source_session_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_account_time
ON favorites(account, created_at);
```

约束：

- `UNIQUE(account, source_type, source_session_id, source_id)` 防止重复收藏。
- `content_snapshot` 是收藏详情的可信内容源。
- `content_summary` 面向收藏列表查询保留，数据量很大时列表可以只读摘要列，不读取完整 `content_snapshot`。
- 原会话删除时不删除收藏记录。

## 9. 与对话模块的关系

- 创建收藏时，收藏模块通过 `source_session_id` 和 `source_id` 读取对话模块中的助手消息。
- 收藏详情的“返回原对话”只在来源会话和来源消息仍存在时可用；当前路由目标为 `/chat/{source_session_id}`。
- 原会话删除后，收藏模块仍以 `content_snapshot` 展示详情。
