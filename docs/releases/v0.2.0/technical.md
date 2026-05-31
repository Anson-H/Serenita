# Serenita v0.2.0 技术文档

> 文档状态：下一规划 / 下一规划版本
>
> 关联需求文档：[Serenita v0.2.0 需求文档](./prd.md)
>
> 当前用途：承载从原 v0.2.0 需求文档拆出的接口、数据存储和开发拆解内容；原文内容保留，未做精简。
>
> 编号说明：本文沿用原第 8、9、13 章编号，以便和拆分前文档互相追溯。

## 7. 技术架构总览

本节是 v0.2.0 报告场景的实现导航。实现时先确认报告智能体（`ReportAgent`）的统一编排位置，再进入后端模块、数据模型和状态机。第 8、9、10、13 章分别保留详细接口、存储、`ReportAgent` 契约和开发拆解内容。

### 7.1 报告智能体（ReportAgent）核心架构

v0.2.0 采用单一 `ReportAgent`。上传、报告对话和后台分析任务进入报告领域后，由 `ReportAgent` 识别任务、加载匹配的 Skill、组织模型推理，并按需调用报告域工具。第 10 章是 Skills、业务 intents、工具契约、确认机制和模型回退的详细定义来源。

```text
上传事件 / 用户请求 / 后台分析任务
  -> ReportAgent 识别任务并选择 Skill
  -> 当前上下文足够：模型直接生成候选、回答、分析或结构化草稿
  -> 需要外部证据或动作：调用 Tool 并接收 tool result
  -> Report services / action layer 校验并执行确定性业务规则
  -> ReportAgent 基于上下文和执行结果生成最终内容
```

报告大类识别由视觉解析模型生成候选类型、结构化字段和来源位置。`ReportSegmentationService` 校验报告边界、分类和拆分规则，`ReportDuplicateService` 与 `ReportRepository` 负责判重和入库。`ReportAgent` 负责流程编排，持久化结果以后端服务校验为准。

模型直接生成回答、摘要、解释或结构化 JSON 属于模型推理。外部 OCR、视觉解析或文档解析能力只有以可调用接口暴露给 `ReportAgent` 时才属于工具；其余模型调用记录为模型推理节点。

### 7.2 后端模块边界

| 模块 | 主要职责 | 主要数据 |
| --- | --- | --- |
| `ReportUploadService` | 校验批量文件、保存源文件、计算哈希、在运行时任务注册表中维护每个文件的处理状态 | `uploaded_source_files`、临时上传任务状态 |
| `ReportExtractionService` | 调用当前账号的 `vision_parse` 默认模型，抽取页面文本、表格、候选段落和结构化候选 | 源文件、当次结构化候选 |
| `ReportSegmentationService` | 将一个源文件拆分为 `LAB-`、`EXAM-`、`PATH-`、`SURG-`、`OTHER-` 候选；检验报告按功能分类拆分 | 候选报告、源文件关联 |
| `ReportDuplicateService` | 对拆分后报告生成业务指纹，查找当前账号内重复候选，生成待确认动作 | `content_fingerprint`、`duplicate_group_key`、`pending_action` |
| `ReportRepository` | 写入 `reports`、报告子表和源文件关联 | `reports.db` |
| `ReportAnalysisService` | 用户主动分析、后台自动重跑受影响分析、写回 `analysis_sections` | `analysis_sections`、`analysis_outdated` |
| `ReportQueryService` | 列表、详情、按需趋势生成、自然语言查询证据读取 | 报告表、临时趋势结果 |
| `ReportActionService` | 确认重复处理、结构化修正、删除和冲突校验 | `pending_action`、报告表 |

### 7.3 数据模型分层

| 层级 | 表 / 字段 | 含义 |
| --- | --- | --- |
| 上传源文件 | `uploaded_source_files` | 一次上传得到的原始文件，按 `file_id` 管理，可被多个报告引用 |
| 源文件关联 | `report_source_links` | 拆分后的报告与原始文件之间的多对多关联 |
| 报告元数据 | `reports` | 拆分后的 canonical 报告记录，按 `report_id` 管理 |
| 检验指标数据 | `lab_test_report` | 单个 `LAB-` 报告内的指标名称、结果原文、参考值原文和 `↑`、`↓` 异常方向标记 |
| 检查结构化数据 | `examination_report` | 单个 `EXAM-` 报告的检查名称、时间、临床诊断、检查方法、检查表现和检查诊断 |
| 病理结构化数据 | `pathology_report` | 单个 `PATH-` 报告的送检标本、巨检、诊断和取材位置 |
| 手术结构化数据 | `surgery_report` | 单个 `SURG-` 报告的术前信息、术中记录、手术经过和术后生命体征 |
| 其它报告原文 | `other_report` | 单个 `OTHER-` 报告的完整原文；名称和时间保存在 `reports` |

批量上传进度属于运行时任务状态，不属于报告数据模型。后端以 `upload_batch_id` 为键在内存任务注册表中暂存逐文件状态，批次达到终态后按 TTL 清理，不写入 `reports.db`。

### 7.4 入库状态机

```text
source_uploaded
  -> extracting
  -> segmented
  -> duplicate_checking
  -> duplicate_pending
       -> duplicate_resolved_attach
       -> duplicate_resolved_update
       -> duplicate_resolved_new
  -> storing
  -> parsed
       -> parse_failed
```

| 状态 | 说明 |
| --- | --- |
| `source_uploaded` | 原始文件已保存并计算哈希 |
| `extracting` | 多模态解析源文件内容 |
| `segmented` | 已生成拆分后的报告候选 |
| `duplicate_checking` | 正在对拆分后候选做业务指纹判重 |
| `duplicate_pending` | 命中疑似重复，等待用户选择处理方式 |
| `duplicate_resolved_attach` | 作为已有报告的补充来源保存 |
| `duplicate_resolved_update` | 用本次解析结果更新已有结构化数据 |
| `duplicate_resolved_new` | 用户确认仍作为新报告保存 |
| `storing` | 写入 `reports`、子表和源文件关联 |
| `parsed` | 拆分后的报告已结构化入库 |
| `parse_failed` | 解析或入库失败；未形成报告或待确认动作时清理本次源文件，用户从当前上传任务重试 |

### 7.5 分析状态机

```text
parsed
  -> analyzing
  -> analyzed
       -> analysis_outdated
            -> auto_reanalyzing
            -> analyzed
            -> analyze_failed
```

| 状态 | 说明 |
| --- | --- |
| `parsed` | 报告已入库但未生成首次分析 |
| `analyzing` | 用户主动触发当前报告分析 |
| `analyzed` | 分析完成并写回 `analysis_sections` |
| `analysis_outdated` | 同日后续报告可能补充或改变既有分析依据 |
| `auto_reanalyzing` | 后台自动重跑受影响分析 |
| `analyze_failed` | 用户主动分析或后台重跑失败 |

### 7.6 当前实现优先级

| 优先级 | 内容 | 原因 |
| --- | --- | --- |
| P0 | `ReportAgent` 运行骨架和 `report-ingestion` Skill | 建立统一任务编排、Skill 加载和调用轨迹边界 |
| P0 | 批量上传、逐文件状态与部分失败重试 | 支撑用户一次导入多份历史报告 |
| P0 | 源文件保存、报告拆分、结构化入库、列表详情 | 报告场景的基础数据闭环 |
| P0 | 检验报告按功能分类拆分 | 影响 `report_id`、趋势和分析边界 |
| P0 | 重复报告确认和源文件关联 | 避免同一医学事实重复污染趋势 |
| P1 | 用户主动分析和分析结果写回 | 形成报告解读闭环 |
| P1 | 后台自动重跑受影响分析 | 解决同日后到报告影响既有结论 |
| P1 | 自然语言查询和确认修正 | 支撑长期报告对话 |
| P2 | 收藏扩展和体验收尾 | 复用 v0.1.0 收藏闭环 |

## 8. 接口要求

### 8.1 本期新增或扩展接口

前端至少需要以下报告相关接口能力：

- `POST /api/upload-report`
- `GET /api/report-upload-batches/{upload_batch_id}`
- `GET /api/reports`
- `GET /api/reports/{report_id}`
- `PUT /api/reports/{report_id}`
- `DELETE /api/reports/{report_id}`
- `POST /api/reports/{report_id}/analysis`
- `POST /api/conversations/messages`（复用 v0.1.0，扩展消息级报告上下文资源）
- `POST /api/reports/pending-actions/{action_id}/confirm`
- `POST /api/reports/pending-actions/{action_id}/cancel`
- `GET /api/reports/daily-analysis-status`
- `POST /api/favorites`
- `DELETE /api/favorites/{favorite_id}`

报告分析继续使用独立业务接口。单份报告问答、跨报告自然语言查询和自然语言修正统一复用 v0.1.0 会话表与消息接口。对话中实际读取或操作的报告通过消息 `context_resources` 保存，待确认写入继续使用独立确认接口。

v0.2.0 继承 v0.1.0 的错误码体系，并新增以下报告场景错误码：

| code | HTTP 状态码 | 含义 | 适用场景 |
| --- | --- | --- | --- |
| `FILE_TOO_LARGE` | 413 | 文件超过大小上限 | 报告上传 |
| `FILE_FORMAT_UNSUPPORTED` | 415 | 文件格式不支持 | 报告上传 |
| `VISION_PARSE_MODEL_NOT_CONFIGURED` | 422 | 当前账号未配置可处理报告文件的视觉解析模型 | 报告解析 |
| `UPLOAD_FAILED` | 500 | 文件上传失败 | 报告上传（网络中断或服务端异常） |
| `PARSE_FAILED` | 422 | 报告解析失败 | 报告解析 |
| `PARSE_TIMEOUT` | 504 | 报告解析超时 | 报告解析（超过 60 秒） |
| `ANALYSIS_FAILED` | 422 | 报告分析失败 | 智能分析 |
| `ANALYSIS_IN_PROGRESS` | 409 | 该报告正在分析中 | 重复触发分析 |
| `REPORT_DUPLICATE_CANDIDATE` | 409 | 上传内容疑似为已有报告的另一份原始来源 | 报告上传确认 |
| `REPORT_NOT_FOUND` | 404 | 报告不存在 | 报告详情、分析、问答、删除 |
| `REPORT_NOT_PARSED` | 422 | 报告尚未完成解析 | 触发分析时报告未就绪 |
| `REPORT_INDICATOR_NOT_FOUND` | 404 | 报告指标不存在 | 指标查询、指标修正 |
| `REPORT_ACTION_CONFIRMATION_REQUIRED` | 409 | 写入动作需要用户确认 | 自然语言修正、删除 |
| `REPORT_ACTION_EXPIRED` | 410 | 待确认动作已过期 | 确认或取消待确认动作 |
| `REPORT_UPDATE_CONFLICT` | 409 | 确认时原数据已变化 | 指标修正、报告基本信息修正 |

### 8.2 报告上传

```http
POST /api/upload-report
Content-Type: multipart/form-data
```

请求字段至少包含：

- `files`：重复 multipart 字段，1-20 个文件
- `account`
- `session_token` 或等价认证上下文

接口校验每个文件不超过 20MB，并为每个文件创建独立 `file_id`。合法文件进入后台解析队列；单个文件失败不回滚同批其它文件。

响应使用 `202 Accepted`，字段至少包含：

- `upload_batch_id`
- `account`
- `total_files`
- `items`
- `message`

每个 `items[]` 至少包含：

- `file_id`
- `original_filename`
- `status`：`uploaded`、`parsing`、`duplicate_pending`、`parsed` 或 `failed`
- `report_ids`
- `pending_actions`
- `error`（可选）

报告图片和 PDF 固定由当前账号的 `vision_parse` 默认模型解析。后端在接收批次前校验该模型和 provider adapter 能处理对应 MIME；PDF provider 不原生支持时，可先按页渲染为图片再送入 `vision_parse`，但结构化候选仍来自视觉解析链路。

批次状态查询：

```http
GET /api/report-upload-batches/{upload_batch_id}
```

响应返回 `upload_batch_id`、`total_files`、`completed_files`、`failed_files`、`pending_files` 和最新 `items`。该接口只查询当前后端进程中的临时任务状态；任务达到终态后按 TTL 清理，已过期或后端重启后返回 `REPORT_UPLOAD_BATCH_EXPIRED`。成功入库的结果通过报告列表恢复，失败批次不做永久恢复。

若某个文件解析后命中疑似重复报告，该文件进入 `duplicate_pending`，对应 `items[].pending_actions` 包含 `REPORT_DUPLICATE_CANDIDATE` 待确认动作和以下处理选项：

`resolution_options` 至少包含：

- `attach_as_source`：将本次文件作为已有报告的补充原始来源，推荐默认项
- `update_structured_data`：用本次解析结果更新已有结构化数据，确认前必须展示差异
- `save_as_new`：仍作为新报告保存

### 8.3 报告列表

```http
GET /api/reports?account={account}&type={type}&time_range={range}&sort={asc|desc}
```

响应字段至少包含：

- `reports`
- `total`

每条报告至少包含：

- `report_id`
- `report_type`
- `report_time`
- `storage_status`
- `flagged_count`
- `total_count`
- `has_analysis`
- `analysis_outdated`

### 8.4 单份报告详情

```http
GET /api/reports/{report_id}
```

响应字段至少包含：

- `report_id`
- `account`
- `report_type`
- `report_name`
- `report_time`
- `storage_status`
- `analysis_outdated`
- `source_files`
- `lab_test_results`
- `examination_result`
- `pathology_report`
- `surgery_report`
- `other_report`
- `analysis_sections`
- `trend_data`

`trend_data` 只为 `LAB-` 检验报告返回；其它报告类型返回空数组或省略该字段。

### 8.5 触发报告分析

```http
POST /api/reports/{report_id}/analysis
Content-Type: application/json
```

请求字段至少包含：

- `account`
- `session_id`
- `thinking_mode`

响应字段至少包含：

- `message_id`
- `report_id`
- `content`
- `analysis_sections`
- `storage_status`
- `analysis_outdated`
- `created_at`

分析从对话中触发时，分析结果消息必须将目标 `report_id` 写入该消息的 `context_resources`，使报告及其原始文件出现在聊天末尾索引中。后台自动重跑不创建对话引用。

### 8.6 报告聊天复用会话消息接口

报告问答、跨报告查询、报告对比和自然语言修正统一复用 v0.1.0 会话接口：

```http
POST /api/conversations/messages
Content-Type: application/json
```

请求继续使用既有 `session_id`、`raw_text`、`thinking_mode` 和 `context_resources`，会话索引沿用现有 `conversation_sessions` 结构。

`context_resources` 在 v0.2.0 新增消息级报告引用：

```json
{
  "resource_type": "report",
  "resource_id": "LAB-20260423-0001",
  "display_name": "2026-04-23 肝功能"
}
```

前端从报告详情进入聊天时，将当前 `report_id` 作为本轮报告资源提交。后端校验该报告属于当前 `account`，再由 `ReportAgent` 选择匹配的 Skill。对话中实际读取、修改、确认写入或分析的报告都应归一化为对应消息的报告引用并随消息落盘，用于历史恢复和文件索引。后台自动分析临时读取的报告不属于对话引用。

自然语言修改或删除产生的 `pending_action` 仍至少包含 `action_id`、`action_type`、`summary`、目标报告或指标、原值、新值、快照和过期时间。确认写入继续由第 8.8 节的独立业务接口执行。

### 8.7 报告聊天文件索引与面板恢复

报告聊天复用普通会话类型。前端聚合当前活动消息路径中的 `context_resources`，在聊天末尾、输入框上方展示报告与文件索引：

- 报告索引项以 `report_id` 为稳定标识，点击后调用 `GET /api/reports/{report_id}` 并在右侧面板打开。
- 原始文件通过报告详情中的 `source_files` 展开，点击后在右侧面板预览。
- 自然语言修正的目标报告必须出现在索引中。
- 对话中确认写入或触发分析的目标报告必须出现在索引中。
- 右侧报告面板支持折叠和展开；折叠状态只属于当前前端视图状态。
- 历史会话继续显示在现有左侧导航栏。打开历史会话时，前端选择活动路径中最近的报告引用恢复右侧面板；没有报告引用时按普通聊天展示。

### 8.8 待确认报告动作

```http
POST /api/reports/pending-actions/{action_id}/confirm
Content-Type: application/json
```

请求字段至少包含：

- `account`
- `session_id`
- `message_id`

当 `action_type=report_duplicate_resolution` 时，请求还必须包含 `resolution_type`，取值为 `attach_as_source`、`update_structured_data` 或 `save_as_new`。若选择 `update_structured_data`，确认动作必须包含待更新字段差异，确认后直接更新已有报告数据。

响应字段至少包含：

- `success`
- `action_id`
- `action_type`
- `report_id`
- `analysis_outdated`
- `message`

确认动作执行时必须重新读取目标报告或指标，并校验原值与 `pending_action` 中的 `old_value` 或 `old_snapshot` 一致。若确认前数据已被其它流程修改，应返回 `REPORT_UPDATE_CONFLICT`，不得覆盖写入。

确认动作来自对话时，确认结果消息必须保留目标 `report_id`，用于刷新聊天末尾的报告与文件索引。

```http
POST /api/reports/pending-actions/{action_id}/cancel
Content-Type: application/json
```

取消动作关闭待确认状态。

### 8.9 同日分析状态

```http
GET /api/reports/daily-analysis-status?account={account}&date={YYYY-MM-DD}
```

响应字段至少包含：

- `has_analysis`
- `analysis_time`
- `report_count`
- `analyzed_report_ids`
- `has_outdated_analysis`
- `outdated_report_ids`
- `affected_report_ids`
- `message`

该接口用于判断同一自然日内是否已有分析、是否存在受后续报告影响的旧分析，以及后台自动重跑是否仍在进行或失败。

响应示例：

```json
{
  "has_analysis": true,
  "analysis_time": "2026-04-23T10:45:00Z",
  "report_count": 2,
  "analyzed_report_ids": ["LAB-20260423-0001"],
  "has_outdated_analysis": true,
  "outdated_report_ids": ["LAB-20260423-0001"],
  "affected_report_ids": ["LAB-20260423-0001"],
  "message": "同日新上传的检查报告可能补充或验证已有分析，系统会后台更新受影响分析"
}
```

### 8.10 修改报告基本信息

```http
PUT /api/reports/{report_id}
Content-Type: application/json
```

请求字段至少包含：

- `account`
- `report_type`（可选，修改报告类型）
- `report_time`（可选，修改报告时间）

响应字段至少包含：

- `report_id`
- `report_type`
- `report_time`
- `storage_status`
- `has_analysis`
- `message`

修改报告类型或时间后，若该报告已有分析结果，响应中应包含 `analysis_outdated: true` 提示前端询问用户是否重新分析。

### 8.11 删除报告

```http
DELETE /api/reports/{report_id}
```

请求要求：

- 只能删除当前登录 `account` 名下的报告。
- 删除成功后，该报告从报告列表中移除。

响应字段至少包含：

- `success`
- `report_id`
- `message`

响应示例：

```json
{
  "success": true,
  "report_id": "LAB-20260423-0001",
  "message": "报告已删除"
}
```

### 8.12 接口响应示例

报告上传响应示例：

```json
{
  "upload_batch_id": "BATCH-20260423-0001",
  "account": "demo_patient",
  "total_files": 2,
  "items": [
    {
      "file_id": "FILE-20260423-0001",
      "original_filename": "肝功能.pdf",
      "status": "parsing",
      "report_ids": [],
      "pending_actions": []
    },
    {
      "file_id": "FILE-20260423-0002",
      "original_filename": "腹部CT.jpg",
      "status": "parsing",
      "report_ids": [],
      "pending_actions": []
    }
  ],
  "message": "2 个报告文件已进入解析队列"
}
```

疑似重复报告响应示例：

```json
{
  "code": "REPORT_DUPLICATE_CANDIDATE",
  "upload_batch_id": "BATCH-20260423-0001",
  "batch_index": 1,
  "file_id": "FILE-20260423-0002",
  "status": "duplicate_pending",
  "account": "demo_patient",
  "duplicate_candidate": true,
  "existing_report": {
    "report_id": "LAB-20260423-0001",
    "report_type": "检验报告",
    "report_time": "2026-04-23T10:30:00Z",
    "flagged_count": 3,
    "total_count": 12
  },
  "parsed_preview": {
    "report_type": "检验报告",
    "report_time": "2026-04-23T10:30:00Z",
    "source_kind": "scan",
    "match_score": 0.96
  },
  "resolution_options": ["attach_as_source", "update_structured_data", "save_as_new"],
  "pending_action": {
    "action_id": "ACT-20260423-0002",
    "action_type": "report_duplicate_resolution",
    "target_report_id": "LAB-20260423-0001",
    "summary": "本次上传疑似为 LAB-20260423-0001 的纸质扫描件",
    "old_snapshot": {"source_file_count": 1},
    "new_snapshot": {"source_file_count": 2},
    "expires_at": "2026-04-23T11:30:00Z"
  },
  "message": "这份报告看起来已上传过，请选择处理方式"
}
```

报告列表响应示例：

```json
{
  "reports": [
    {
      "report_id": "LAB-20260423-0001",
      "report_type": "检验报告",
      "report_time": "2026-04-23T10:30:00Z",
      "storage_status": "analyzed",
      "flagged_count": 3,
      "total_count": 12,
      "has_analysis": true,
      "analysis_outdated": false
    }
  ],
  "total": 15
}
```

单份报告详情响应示例：

```json
{
  "report_id": "LAB-20260423-0001",
  "account": "demo_patient",
  "report_type": "检验报告",
  "report_name": "糖代谢",
  "report_time": "2026-04-23T10:30:00Z",
  "storage_status": "analyzed",
  "analysis_outdated": true,
  "source_files": [
    {
      "file_id": "FILE-20260423-0001",
      "source_kind": "screenshot",
      "file_path": "demo_patient/reports/uploads/FILE-20260423-0001.png",
      "is_primary": true
    },
    {
      "file_id": "FILE-20260423-0002",
      "source_kind": "scan",
      "file_path": "demo_patient/reports/uploads/FILE-20260423-0002.jpg",
      "is_primary": false
    }
  ],
  "lab_test_results": [
    {
      "report_id": "LAB-20260423-0001",
      "item_id": "HbA1c",
      "name_cn": "糖化血红蛋白",
      "result_text": "7.2%",
      "reference_text": "4.0-6.0%",
      "flag_text": "↑"
    }
  ],
  "analysis_sections": {
    "good_news": [],
    "stable_signals": [],
    "stalemate": [],
    "micro_change": [],
    "warning": [],
    "watch_list": [],
    "prognosis": []
  },
  "trend_data": {
    "HbA1c": {
      "display_mode": "line",
      "points": [
        {"date": "2025-05-15", "result_text": "8.1%", "reference_text": "4.0-6.0%", "flag_text": "↑"},
        {"date": "2025-06-12", "result_text": "7.8%", "reference_text": "4.0-6.0%", "flag_text": "↑"},
        {"date": "2025-07-10", "result_text": "7.2%", "reference_text": "4.0-6.0%", "flag_text": "↑"}
      ]
    }
  }
}
```

## 9. 数据存储要求

v0.2.0 继承 v0.1.0 的登录、对话和收藏存储约定。其中对话历史继续按 v0.1.0 技术设计使用 `{account}/conversations/sessions/{session_id}.jsonl` 追加日志保存。

### 9.1 文件目录

报告文件存放在当前患者私有目录下：

- `{account}/reports/uploads/{file_id}.{pdf|jpg|png|heic}`

同一上传源文件可以拆分并关联到多个 `report_id`。`file_id` 表示一次上传的原始文件，`report_id` 表示拆分后的 canonical 结构化报告。

报告结构化数据库存放在：

- `{account}/reports/db_storage/reports.db`

公共指标字典存放在：

- `all_users/lab_dict/lab_dict.db`

### 9.2 lab_item 指标字典

```sql
CREATE TABLE lab_item (
    item_id     VARCHAR(32)  PRIMARY KEY,
    item_cn     VARCHAR(128) NOT NULL,
    aliases     JSON,
    description TEXT,
    status      VARCHAR(16)  NOT NULL DEFAULT 'verified'
);
```

示例数据：

| item_id | item_cn | aliases | description | status |
| --- | --- | --- | --- | --- |
| GLU | 葡萄糖 | ["血糖","空腹血糖","FBG"] | 血液中的葡萄糖浓度，糖尿病诊断核心指标 | verified |
| HbA1c | 糖化血红蛋白 | ["糖化","GHb"] | 反映近 2-3 个月平均血糖水平 | verified |
| TC | 总胆固醇 | ["胆固醇"] | 血液中所有脂蛋白胆固醇的总和 | verified |
| WBC | 白细胞计数 | ["白细胞"] | 反映体内感染、炎症状态 | verified |
| PIVKA-II | 异常凝血酶原 | ["脱-γ-凝血酶原"] | 肝癌辅助诊断标志物，也可反映维生素 K 缺乏 | verified |
| UNKNOWN_01 | 未知指标A | [] | - | pending |

写入规则：新报告指标先按 `item_id`、`item_cn` 和 `aliases` 匹配。匹配失败时，应用层在同一入库事务中创建新的 `lab_item`，将 `status` 设为 `pending`，并写入解析候选给出的名称、别名和功能分类关联。`pending` 指标可立即用于报告展示、查询和检验趋势，无需等待首批内置字典或人工审核。

### 9.3 lab_category 分类字典

```sql
CREATE TABLE lab_category (
    category_id    VARCHAR(32) PRIMARY KEY,
    parent_id      VARCHAR(32),
    level          TINYINT,
    description    TEXT,
    status         VARCHAR(16) NOT NULL DEFAULT 'verified',
    CONSTRAINT fk_cat_parent FOREIGN KEY (parent_id) REFERENCES lab_category(category_id)
);
```

示例数据：

| category_id | parent_id | level | description | status |
| --- | --- | --- | --- | --- |
| 血液检查 | null | 1 | 所有血液相关检验的顶级分类 | verified |
| 血常规 | 血液检查 | 2 | 白细胞、红细胞、血小板等常规血液指标 | verified |
| 血脂 | 血液检查 | 2 | 胆固醇、甘油三酯等脂质代谢指标 | verified |
| 生化检查 | null | 1 | 生化全套相关检验 | verified |
| 肝功能 | 生化检查 | 2 | ALT、AST、胆红素等肝脏功能指标 | verified |
| 肾功能 | 生化检查 | 2 | 肌酐、尿素氮等肾脏功能指标 | verified |
| 糖代谢 | 生化检查 | 2 | 血糖、糖化血红蛋白等糖代谢指标 | verified |
| 肿瘤标志物 | null | 1 | 肿瘤相关标志物 | verified |
| 肿瘤血清标志物 | 肿瘤标志物 | 2 | AFP、CEA、DCP 等血清肿瘤标志物 | verified |

### 9.4 lab_item_category 指标与分类关联

```sql
CREATE TABLE lab_item_category (
    item_id      VARCHAR(32) NOT NULL,
    category_id  VARCHAR(32) NOT NULL,
    relevance    TINYINT NOT NULL DEFAULT 1,
    PRIMARY KEY (item_id, category_id),
    CONSTRAINT fk_ic_item FOREIGN KEY (item_id) REFERENCES lab_item(item_id),
    CONSTRAINT fk_ic_cat  FOREIGN KEY (category_id) REFERENCES lab_category(category_id)
);
```

示例数据：

| item_id | category_id | relevance |
| --- | --- | --- |
| GLU | 糖代谢 | 1 |
| HbA1c | 糖代谢 | 1 |
| TC | 血脂 | 1 |
| WBC | 血常规 | 1 |
| PIVKA-II | 肝功能 | 1 |
| PIVKA-II | 肿瘤血清标志物 | 2 |

### 9.5 reports 报告元数据表

```sql
CREATE TABLE IF NOT EXISTS reports (
    report_id         TEXT PRIMARY KEY,
    account        TEXT NOT NULL,
    report_type       TEXT NOT NULL CHECK (report_type IN ('检验报告', '检查报告', '病理报告', '手术报告', '其它报告')),
    report_name       TEXT NOT NULL,
    report_time       DATETIME NOT NULL,
    analysis_sections JSON DEFAULT '{}',
    analysis_outdated BOOLEAN NOT NULL DEFAULT 0,
    analysis_updated_at DATETIME,
    storage_status    TEXT NOT NULL DEFAULT 'uploaded',
    content_fingerprint TEXT,
    duplicate_group_key TEXT,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

示例数据：

| report_id | account | report_type | report_name | report_time | storage_status | analysis_outdated |
| --- | --- | --- | --- | --- | --- | --- |
| LAB-20260215-0001 | demo_patient | 检验报告 | 肝功能 | 2026-02-15 08:00 | analyzed | 0 |
| LAB-20260215-0002 | demo_patient | 检验报告 | 肾功能 | 2026-02-15 08:00 | analyzed | 1 |
| LAB-20260215-0003 | demo_patient | 检验报告 | 血脂 | 2026-02-15 08:00 | analyzed | 0 |
| EXAM-20260301-0001 | demo_patient | 检查报告 | 腹部CT平扫 | 2026-03-01 09:30 | uploaded | 0 |
| PATH-20260703-0001 | demo_patient | 病理报告 | 肝、胆囊 | 2026-07-03 10:00 | analyzed | 0 |
| SURG-20260703-0001 | demo_patient | 手术报告 | 肝切除术+胆囊切除术 | 2026-07-03 13:30 | analyzed | 0 |
| OTHER-20260301-0002 | demo_patient | 其它报告 | 出院小结 | 2026-03-01 10:00 | parsed | 0 |

说明：`report_id` 前缀表示报告类型，`LAB-` 为检验报告，`EXAM-` 为检查报告，`PATH-` 为病理报告，`SURG-` 为手术报告，`OTHER-` 为其它报告。检验报告按功能分类拆分，并用 `report_name` 保存拆分后的名称；同一上传源文件中的肝功能、肾功能和血脂会生成多个 `LAB-` 报告。病理报告和手术报告按独立报告单边界保存，联合术式保存在同一 `SURG-` 报告中。解析后的结构化数据按报告类型分流，并通过 `report_id` 与 `reports` 表关联。报告的源文件和主文件均通过 `report_source_links` 查询，文件路径只保存在 `uploaded_source_files`。`content_fingerprint` 用于识别同一拆分后报告记录，`duplicate_group_key` 用于缩小当前账号内的候选范围；两者限定在当前账号范围内使用。

### 9.5.1 uploaded_source_files 上传源文件表

`uploaded_source_files` 保存一次上传的原始文件。一个源文件可被拆分后关联到多个 `report_id`。

```sql
CREATE TABLE uploaded_source_files (
    file_id              TEXT PRIMARY KEY,
    account              VARCHAR(32) NOT NULL,
    file_path            TEXT NOT NULL,
    mime_type            VARCHAR(128) NOT NULL,
    sha256               VARCHAR(64) NOT NULL,
    source_kind          VARCHAR(32) NOT NULL DEFAULT 'unknown'
        CHECK (source_kind IN ('screenshot', 'scan', 'pdf', 'photo', 'unknown')),
    uploaded_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uk_uploaded_source_file_hash
ON uploaded_source_files(account, sha256);
```

### 9.5.2 report_source_links 报告源文件关联表

`report_source_links` 表示某份拆分后的报告关联哪些原始文件。若一张检验报告单包含肝功能、肾功能和血脂，三个 `LAB-` 报告可以关联同一个 `file_id`；同一报告后续上传电子截图或纸质扫描件时，也可以关联多个 `file_id`。

```sql
CREATE TABLE report_source_links (
    report_id            TEXT NOT NULL,
    file_id              TEXT NOT NULL,
    account              VARCHAR(32) NOT NULL,
    is_primary           BOOLEAN NOT NULL DEFAULT 0,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (report_id, file_id),
    CONSTRAINT fk_report_source_link_report FOREIGN KEY (report_id) REFERENCES reports(report_id),
    CONSTRAINT fk_report_source_link_file FOREIGN KEY (file_id) REFERENCES uploaded_source_files(file_id)
);

CREATE INDEX idx_report_source_link_file
ON report_source_links(account, file_id);

CREATE INDEX idx_report_source_link_report
ON report_source_links(account, report_id);
```

写入规则：

- 每次成功接收上传文件时，先写入或复用 `uploaded_source_files`。
- 首次入库某个拆分后的报告时，必须同时写入一条 `report_source_links`，并将其标记为 `is_primary=1`。
- 相同 `account`、相同 `sha256` 的源文件重复上传时，复用已有源文件记录和已有报告关联。
- 文件哈希不同但拆分后的业务指纹高度一致时，生成 `report_duplicate_resolution` 待确认动作。
- 用户选择 `attach_as_source` 后，新增 `uploaded_source_files` 和 `report_source_links` 记录。
- 用户选择 `update_structured_data` 后，新增源文件和关联记录，并按确认后的差异更新结构化数据。
- 用户选择 `save_as_new` 后，创建新的 `report_id`、结构化数据和源文件关联记录。
- 文件解析失败且未形成任何报告或待确认动作时，清理本次新增的源文件记录和原始文件；失败原因只保留在当前运行时上传任务中。

### 9.6 lab_test_report 检验报告表

```sql
CREATE TABLE lab_test_report (
    report_id      TEXT NOT NULL,
    account        VARCHAR(32) NOT NULL,
    collected_at   DATETIME NOT NULL,
    category_id    VARCHAR(32) NOT NULL,
    item_id        VARCHAR(32) NOT NULL,
    result_text    TEXT NOT NULL,
    reference_text TEXT,
    flag_text      TEXT CHECK (flag_text IN ('↑', '↓')),

    PRIMARY KEY (report_id, item_id),
    CONSTRAINT fk_ltr_report FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE INDEX idx_ltr_account_item_time ON lab_test_report(account, item_id, collected_at);
```

说明：`item_id` 和 `category_id` 逻辑引用公共指标字典 `all_users/lab_dict/lab_dict.db` 中的 `lab_item` 与 `lab_category`。字典匹配和完整性校验由应用层在入库前完成。`result_text` 完整保存报告中的结果及单位，`reference_text` 完整保存报告中的参考值。视觉解析模型结合这两段原文和报告上下文判断方向：异常或偏高写 `↑`，偏低写 `↓`，无异常或无法判断写空值。`flag_text` 的 schema 只允许 `↑`、`↓` 或空值。定性结果如“阳性”保留在 `result_text`，相对报告参考值被判断为异常时写 `↑`。后端不拆分参考上下限，也不另建复杂参考范围规则。

示例数据：

| report_id | account | collected_at | category_id | item_id | result_text | reference_text | flag_text |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LAB-20260215-0001 | demo_patient | 2026-02-15 08:00 | 血常规 | WBC | 3.2×10^9/L | 3.5-9.5×10^9/L | ↓ |
| LAB-20260215-0002 | demo_patient | 2026-02-15 08:00 | 肝功能 | ALT | 45 U/L | 9-50 U/L |  |
| LAB-20260215-0003 | demo_patient | 2026-02-15 08:00 | 糖代谢 | HbA1c | 7.2% | 4.0-6.0% | ↑ |
| LAB-20260215-0005 | demo_patient | 2026-02-15 08:00 | 乙肝标志物 | HBsAg | 阳性 | 阴性 | ↑ |

说明：同一源文件可按功能分类拆分为多个 `report_id`。历史查询始终读取上述原文字段；趋势所需的绘图值只在请求时临时生成，不写回 `lab_test_report`。

### 9.7 examination_report 检查报告表

检查报告按原有六类信息结构化保存：检查名称、检查时间、临床诊断、检查方法、检查表现、检查诊断或结论。

```sql
CREATE TABLE examination_report (
    report_id          TEXT PRIMARY KEY,
    account            VARCHAR(32) NOT NULL,
    collected_at       DATETIME NOT NULL,
    exam_name          VARCHAR(255) NOT NULL,
    clinical_diagnosis TEXT,
    exam_method        TEXT,
    exam_findings      TEXT,
    exam_diagnosis     TEXT,

    CONSTRAINT fk_exam_report FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE UNIQUE INDEX uk_exam_account_time_name
ON examination_report(account, collected_at, exam_name);

CREATE INDEX idx_exam_account_time
ON examination_report(account, exam_name, collected_at);
```

示例数据：

| report_id | account | collected_at | exam_name | clinical_diagnosis | exam_method | exam_findings | exam_diagnosis |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EXAM-20260301-0001 | demo_patient | 2026-03-01 09:00 | 腹部CT平扫 | 腹痛待查 | 平扫 | 肝脏大小形态正常，表面光滑... | 脂肪肝（轻度） |
| EXAM-20260315-0001 | demo_patient | 2026-03-15 10:00 | 心脏彩超 | 高血压病 | 经胸超声 | 各房室大小正常，室壁厚度正常... | 左室舒张功能减退 |

### 9.8 pathology_report 病理报告表

病理报告只按送检标本、巨检、诊断、取材位置四个分类保存。源报告中的免疫组化、特殊染色、分级、切缘、侵犯情况和预后指标等内容统一保留在 `diagnosis` 原文内。

```sql
CREATE TABLE pathology_report (
    report_id          TEXT PRIMARY KEY,
    account            VARCHAR(32) NOT NULL,
    submitted_specimen TEXT,
    gross_examination  TEXT,
    diagnosis          TEXT,
    sampling_location  TEXT,

    CONSTRAINT fk_pathology_report FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE INDEX idx_pathology_account ON pathology_report(account, report_id);
```

示例数据：

| report_id | account | submitted_specimen | gross_examination | diagnosis | sampling_location |
| --- | --- | --- | --- | --- | --- |
| PATH-20260703-0001 | demo_patient | 肝，胆囊 | 部分肝及胆囊标本，肝内见肿物... | 肝细胞癌，伴大片坏死；肝切缘未见癌累及... | 001 肿+切；002 肿+切；003 肿+被... |

### 9.9 surgery_report 手术报告表

手术报告只按以下十三个分类保存。源报告未提供的字段保持 `NULL`；麻醉记录中的时间不得代替手术开始时间或结束时间。

```sql
CREATE TABLE surgery_report (
    report_id                    TEXT PRIMARY KEY,
    account                      VARCHAR(32) NOT NULL,
    preoperative_diagnosis       TEXT,
    intraoperative_diagnosis     TEXT,
    anesthesia_method            TEXT,
    started_at                   DATETIME,
    ended_at                     DATETIME,
    blood_transfusion            TEXT,
    intraoperative_blood_loss    TEXT,
    intraoperative_urine_output  TEXT,
    intraoperative_transfusion   TEXT,
    intraoperative_infusion      TEXT,
    intraoperative_other_drugs   TEXT,
    procedure_description        TEXT,
    postoperative_vital_signs    TEXT,

    CONSTRAINT fk_surgery_report FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE INDEX idx_surgery_account_time ON surgery_report(account, started_at, ended_at);
```

字段与界面分类固定映射如下：

| 字段 | 分类 |
| --- | --- |
| `preoperative_diagnosis` | 术前诊断 |
| `intraoperative_diagnosis` | 术中诊断 |
| `anesthesia_method` | 麻醉方法 |
| `started_at` | 开始时间 |
| `ended_at` | 结束时间 |
| `blood_transfusion` | 是否输血 |
| `intraoperative_blood_loss` | 术中失血量 |
| `intraoperative_urine_output` | 术中尿量 |
| `intraoperative_transfusion` | 术中输血量 |
| `intraoperative_infusion` | 术中输液量 |
| `intraoperative_other_drugs` | 术中其他用药 |
| `procedure_description` | 手术经过 |
| `postoperative_vital_signs` | 术后生命体征 |

示例数据：

| report_id | account | preoperative_diagnosis | intraoperative_diagnosis | anesthesia_method | started_at | ended_at | blood_transfusion | intraoperative_blood_loss | intraoperative_urine_output | intraoperative_transfusion | intraoperative_infusion | intraoperative_other_drugs | procedure_description | postoperative_vital_signs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SURG-20260703-0001 | demo_patient | 肝恶性肿瘤 | 肝恶性肿瘤 | 全麻复合硬膜外 | 2026-07-03 13:30 | 2026-07-03 18:30 | 否 | 300mL | 300mL | 0mL | 500mL |  | 完成肝切除术及胆囊切除术... | 平稳 |

### 9.10 other_report 其它报告表

其它报告只保存完整原文；报告名称和时间复用 `reports.report_name` 与 `reports.report_time`。

```sql
CREATE TABLE other_report (
    report_id   TEXT PRIMARY KEY,
    account     VARCHAR(32) NOT NULL,
    report_body TEXT NOT NULL,

    CONSTRAINT fk_other_report FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

CREATE INDEX idx_other_account ON other_report(account, report_id);
```

示例数据：

| report_id | account | report_body |
| --- | --- | --- |
| OTHER-20260301-0002 | demo_patient | 出院小结：患者因“反复上腹痛1月”入院...出院诊断：慢性胃炎... |
| OTHER-20260410-0001 | demo_patient | 多学科会诊记录：肝肿瘤科、介入科和外科共同评估后续治疗方案... |

### 9.11 storage_status 状态流转

```text
uploaded -> parsing -> parsed -> analyzing -> analyzed
                  -> parse_failed
                                      -> analyze_failed
```

| 状态 | 说明 |
| --- | --- |
| uploaded | 文件已上传，尚未解析 |
| parsing | 正在进行多模态解析 |
| parsed | 解析完成，报告数据已写入对应报告表 |
| parse_failed | 解析失败 |
| analyzing | 正在进行智能分析 |
| analyzed | 分析完成，结果已存储 |
| analyze_failed | 分析失败 |

### 9.12 analysis_sections 结构

```json
{
  "good_news": [],
  "stable_signals": [],
  "stalemate": [],
  "micro_change": [],
  "warning": [],
  "watch_list": [],
  "prognosis": []
}
```

说明：`analysis_sections` 存在单份报告的 `reports` 记录中。`analysis_outdated=true` 表示同一自然日后续入库的新报告可能补充、验证或改变该报告的既有分析。后台重跑时可临时读取当日相关报告，完成后只更新目标报告的 `analysis_sections`、`analysis_outdated` 和分析时间，不保存报告之间的分析引用关系，也不定义独立日汇总表。

### 9.13 数据流示例

报告解析后按类型分流入库。检验指标只持久化指标身份、结果原文、参考值原文和 `↑`、`↓` 异常方向标记，不保存拆分后的数值、单位、上下限或可比状态。

入库前必须先执行报告分割和当前账号内的重复候选识别：

1. 计算原始文件 `sha256`，写入或复用 `uploaded_source_files`。
2. 使用当前账号的 `vision_parse` 默认模型进行解析，生成候选报告和结构化字段。
3. 检验报告按功能分类拆分为独立 `LAB-` 报告；肝功能、肾功能、血脂等不同功能分类必须拆成不同 `report_id`。同一功能分类下的多个指标保存在同一 `LAB-` 报告。
4. 检查报告按独立报告单边界拆分为 `EXAM-` 报告，并提取检查名称、检查时间、临床诊断、检查方法、检查表现、检查诊断或结论写入 `examination_report`。
5. 病理报告按独立报告单边界拆分为 `PATH-` 报告，并只提取送检标本、巨检、诊断、取材位置四个分类。
6. 手术报告按独立报告单边界拆分为 `SURG-` 报告；同一份报告中的联合术式保存在同一 `SURG-` 报告中。
7. 其它报告按独立文档边界拆分为 `OTHER-` 报告，完整原文写入 `other_report.report_body`。
8. 每个拆分后的报告写入 `reports` 和对应子表，并通过 `report_source_links` 关联到原始文件。
9. 多模态解析后生成 `content_fingerprint` 和 `duplicate_group_key`。检验报告的 `duplicate_group_key` 必须包含 `report_name`，用于避免把同一源文件中的不同功能分类互相判为重复。
10. 在候选范围内比较指标集合以及结果原文、参考值原文和异常方向箭头。高度一致时生成 `REPORT_DUPLICATE_CANDIDATE` 和 `report_duplicate_resolution` 待确认动作。
11. 用户选择 `attach_as_source` 时，仅写入源文件和 `report_source_links`；列表、趋势和分析继续使用已有 canonical 报告。
12. 用户选择 `update_structured_data` 时，写入源文件和关联记录，再按用户确认的差异更新结构化表。
13. 用户选择 `save_as_new` 时，才生成新的 `report_id` 并进入正常结构化入库。

报告入库后必须执行同日分析影响评估：

1. 以当前 `account` 和报告时间所在患者本地自然日查询当天已分析报告。
2. 排除本次仅作为 `attach_as_source` 保存且未改变结构化数据的重复来源文件。
3. 对同日已分析报告判断新报告是否可能补充、验证或改变既有分析。
4. 将受影响报告标记为 `analysis_outdated=true`。
5. 判断可结合报告类型、检查名称、异常指标、诊断关键词、同类项目和模型生成的结构化关系，但最终写入必须由后端规则和 schema 校验控制。
6. 后端临时读取当前自然日内相关报告重新生成目标分析，只更新 `analysis_sections`、`analysis_updated_at` 和 `analysis_outdated`；临时读取的报告 ID 不落库。

检验报告写入 `lab_test_report`：

| report_id | account | collected_at | category_id | item_id | result_text | reference_text | flag_text |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LAB-20260215-0001 | demo_patient | 2026-02-15 | 血常规 | WBC | 3.2×10^9/L | 3.5-9.5×10^9/L | ↓ |
| LAB-20260215-0003 | demo_patient | 2026-02-15 | 糖代谢 | GLU | 6.1 mmol/L | 3.9-5.6 mmol/L | ↑ |
| LAB-20260115-0001 | demo_patient | 2026-01-15 | 糖代谢 | GLU | 110 mg/dL | 70-100 mg/dL | ↑ |
| LAB-20260215-0005 | demo_patient | 2026-02-15 | 乙肝标志物 | HBsAg | 阳性 | 阴性 | ↑ |

检查报告写入 `examination_report`：

| report_id | account | exam_name | clinical_diagnosis | exam_method | exam_findings | exam_diagnosis | collected_at |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EXAM-20260301-0001 | demo_patient | 腹部CT平扫 | 腹痛待查 | 平扫 | 肝脏大小形态正常... | 脂肪肝（轻度） | 2026-03-01 09:00 |

病理报告写入 `pathology_report`：

| report_id | account | submitted_specimen | gross_examination | diagnosis | sampling_location |
| --- | --- | --- | --- | --- | --- |
| PATH-20260703-0001 | demo_patient | 肝，胆囊 | 部分肝及胆囊标本，肝内见肿物... | 肝细胞癌，伴大片坏死；肝切缘未见癌累及... | 001 肿+切；002 肿+切；003 肿+被... |

手术报告写入 `surgery_report`：

| report_id | account | preoperative_diagnosis | intraoperative_diagnosis | anesthesia_method | started_at | ended_at | blood_transfusion | intraoperative_blood_loss | intraoperative_urine_output | intraoperative_transfusion | intraoperative_infusion | intraoperative_other_drugs | procedure_description | postoperative_vital_signs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SURG-20260703-0001 | demo_patient | 肝恶性肿瘤 | 肝恶性肿瘤 | 全麻复合硬膜外 | 2026-07-03 13:30 | 2026-07-03 18:30 | 否 | 300mL | 300mL | 0mL | 500mL |  | 完成肝切除术及胆囊切除术... | 平稳 |

其它报告写入 `other_report`：

| report_id | account | report_body |
| --- | --- | --- |
| OTHER-20260301-0002 | demo_patient | 出院小结：患者因“反复上腹痛1月”入院...出院诊断：慢性胃炎... |

### 9.14 前端展示策略

本节趋势策略只适用于 `LAB-` 检验报告。`EXAM-`、`PATH-`、`SURG-` 和 `OTHER-` 不生成 `trend_data`，跨报告比较由 `report-query` 基于原文完成。

- 历史节点始终返回 `result_text`、`reference_text` 和 `flag_text`。
- 查询时若同一指标的结果可明确识别为数值且原始单位一致，`ReportQueryService` 可临时生成折线图所需数值。
- 无法可靠解析、单位不同、定性、半定量或文本结果按时间顺序展示原文，不做单位换算。
- 临时解析结果只存在于本次接口响应中，不写回数据库。
- 参考值只展示 `reference_text` 原文，不解析上下限，不据此重新计算异常状态。

### 9.15 收藏扩展

`favorites.source_type` 在 v0.2.0 至少支持：

- `message`
- `report_analysis`
- `report_qa`

收藏记录仍存放在：

- `{account}/favorites/db_storage/favorites.db`

## 10. 报告智能体（ReportAgent）、Skills 与工具调用

### 10.1 架构边界

第一版报告对话能力采用单一 `ReportAgent` 架构，多智能体会诊属于 v0.2.0 范围外。

```text
用户请求或后台分析任务
  -> ReportAgent 判断意图并选择匹配的 Skill
  -> 当前上下文足够：模型直接生成回答、分析或结构化草稿
  -> 需要外部数据或动作：模型发出 tool call
       -> 后端执行工具并返回 tool result
       -> 模型基于上下文和 tool result 直接生成最终内容
  -> ReportService / action layer 做 schema 校验、权限校验、事务和落库
  -> 结果返回业务接口
```

`ReportAgent` 输出业务 `intent`，按任务需要加载 Skill，并在需要访问模型上下文之外的数据或执行受控动作时发起工具调用。模型理解、推理、总结、解释和结构化组织属于模型自身能力。

四层职责固定如下：

| 层级 | 负责 | 示例 |
| --- | --- | --- |
| Model / `ReportAgent` | 意图识别、推理、解释、分析、问答和结构化草稿生成 | 根据 ALT 历史值解释趋势；基于证据生成 `analysis_sections` |
| Skill | 封装可复用流程、判断步骤、参考资料和输出 schema | 报告导入、分析、查询、修正流程 |
| Tool | 读取外部报告证据、调用外部文件解析能力、创建或读取待确认动作 | `query_report_evidence`、`extract_report_file`、`create_pending_action` |
| Report services / action layer | 执行确定性业务规则、权限、状态机、事务和确认写入 | 分割、判重、分析失效判断、入库、修正、删除 |

### 10.2 第一版 Skills

Skill 是 `ReportAgent` 可复用的工作流，不是业务接口。第一版建议提供以下 Skills：

| Skill | 触发场景 | 主要步骤 | 可用工具 | 后端服务边界 |
| --- | --- | --- | --- | --- |
| `report-ingestion` | 新报告上传并进入解析 | 读取文件内容、生成结构化候选、组织分割与重复候选上下文 | `extract_report_file` | `ReportSegmentationService` 强制执行报告边界；`ReportDuplicateService` 判重；`ReportRepository` 入库 |
| `report-analysis` | 用户首次分析；同日证据变化后的后台自动重跑 | 选择证据范围、读取报告证据、按固定 schema 生成分析 | `query_report_evidence` | `ReportAnalysisService` 负责触发、证据范围校验、状态更新和结果写回 |
| `report-query` | 自然语言列表、详情、指标、趋势、对比和报告追问 | 识别查询范围、读取必要证据、直接生成患者可读回答 | `query_report_evidence` | `ReportQueryService` 提供白名单查询和按需趋势结果 |
| `report-correction` | 指标修正、元数据修改和删除请求 | 定位目标、读取旧值、生成结构化 patch、创建待确认动作 | `query_report_evidence`、`create_pending_action` | `ReportActionService` 在确认后重新校验并执行真实写入 |

简单列表、详情、上传状态、同日分析状态、确认和取消动作使用业务接口。同日证据影响评估和后台任务触发由 `ReportAnalysisService` 与任务队列执行；任务触发后可复用 `report-analysis` Skill 的分析流程。

Skills 只能通过受控工具访问当前 `account` 数据。报告分割、重复识别阈值、状态转换和确认校验规则保存在后端代码或配置中。

### 10.3 第一版意图

第一版至少支持以下意图：

| intent | 说明 | 写入确认 |
| --- | --- | --- |
| `report_list_query` | 查询最近报告、指定时间范围报告、某类报告 | 否 |
| `report_detail_query` | 查询单份报告详情 | 否 |
| `report_indicator_query` | 查询某指标当前值、异常项、阳性项 | 否 |
| `report_trend_query` | 查询单指标跨报告趋势 | 否 |
| `report_compare_query` | 比较两份或多份报告差异 | 否 |
| `report_analysis` | 触发或查看报告分析 | 触发分析需用户动作 |
| `report_question_answer` | 围绕报告内容追问 | 否 |
| `report_indicator_update` | 修正指标结果原文、参考值原文或异常方向箭头 | 是 |
| `report_metadata_update` | 修改报告类型或报告时间 | 是 |
| `report_delete` | 删除报告 | 是 |

### 10.4 工具契约

工具是模型向应用程序发出的外部能力请求。模型返回工具名和结构化参数，后端执行对应能力并将结果作为 tool result 返回模型。`report_list_query`、`report_trend_query`、`report_indicator_update` 等属于业务 `intent`，由 Skill 和 `ReportAgent` 决定是否需要工具。

第一版 `ReportAgent` 可见工具建议按以下边界设计，具体名称可在实现时调整：

| 工具 | 输入要点 | 输出要点 | 约束 |
| --- | --- | --- | --- |
| `query_report_evidence` | `account`, `query_scope`, `filters`, `report_ids`, `item_id`, `evidence_fields` | 报告摘要、详情、指标原文、按需趋势结果和分析上下文 | 只读；映射到允许的 repository 方法；所有查询绑定 `account` |
| `extract_report_file` | `account`, `file_id`, `mime_type`, `extraction_schema` | OCR/多模态文本、表格、报告类型候选、结构化字段候选、来源位置和置信度 | 只读源文件；仅在调用外部 OCR、视觉或文档解析能力时作为工具 |
| `create_pending_action` | `account`, `action_type`, `target`, `old_snapshot`, `patch`, `reason_text`, `session_id`, `message_id` | 已持久化的 `pending_action`，包含原值、新值、影响字段和过期时间 | 只写待确认动作；不得修改目标报告 |
| `get_pending_action` | `account`, `action_id` | 待确认动作、当前状态、目标摘要和过期时间 | 只读；只能读取当前账号动作 |

模型直接接收文件作为多模态输入时，文件理解和结构化候选生成属于该次模型推理。`ReportExtractionService` 负责读取源文件、构造模型输入和校验输出；此路径不产生 `extract_report_file` 工具调用。

业务意图到 Skill、工具和模型生成的映射如下：

| 业务能力 | Skill | 工具调用 | 模型直接生成 | 后端执行 |
| --- | --- | --- | --- | --- |
| 列表、详情、指标、趋势、对比查询 | `report-query` | 需要数据库证据时调用 `query_report_evidence` | 基于工具结果组织患者可读回答 | `ReportQueryService` 执行白名单查询 |
| 报告上传解析 | `report-ingestion` | 调用外部解析服务时使用 `extract_report_file` | 已直接接收文件时生成结构化候选 | 分割、判重、校验和入库 |
| 报告问答与分析 | `report-query` / `report-analysis` | 需要补充证据时调用 `query_report_evidence` | 生成回答、解释和 `analysis_sections` | schema 校验、状态更新和分析写回 |
| 指标、元数据修改和删除 | `report-correction` | `query_report_evidence` 读取旧值；`create_pending_action` 保存待确认动作 | 生成结构化 patch 和确认说明 | 确认后执行写入和冲突校验 |

确认后的真实写入由 `POST /api/reports/pending-actions/{action_id}/confirm` 或等价后端 action 执行，并必须经过用户确认、权限校验、旧值校验和事务写入。

### 10.5 确认机制

写入类自然语言请求必须走待确认动作：

```text
用户提出修改
  -> ReportAgent 定位报告和字段
  -> query_report_evidence 读取目标和 old_snapshot
  -> 模型直接生成结构化 patch 和确认说明
  -> create_pending_action 持久化 pending_action
  -> 前端展示确认卡片
  -> 用户确认
  -> confirm action 重新校验 old_snapshot
  -> ReportService 在事务中更新目标报告
```

待确认动作应有过期时间。确认时若报告、指标、原值或权限状态变化，返回 `REPORT_UPDATE_CONFLICT`，不得覆盖写入。

报告上传链路产生的 `report_duplicate_resolution` 也使用同一套确认机制。区别在于该动作的 `resolution_type=attach_as_source` 时新增原始文件来源；`resolution_type=update_structured_data` 时必须展示字段差异并在确认后直接更新已有报告；`resolution_type=save_as_new` 时必须确认用户确实要把同一候选保存为新报告。

### 10.6 模型能力与回退

执行 `ReportAgent` 的模型应支持 tool calling 或结构化输出。若当前模型不支持原生工具调用，后端可要求模型输出结构化 `intent` 和 `tool_requests` JSON，再由后端做 schema 校验、权限校验和工具执行。

当前上下文足以完成任务时，模型直接输出回答、分析或结构化草稿。工具返回外部证据后，模型在下一次推理中生成最终内容。

每个模型调用应在链路追踪中标记为模型推理节点，并记录实际模型、模型服务、输入摘要、输出 schema 和耗时。

所有写入动作以后端 `pending_action` 和用户确认状态为准。模型文本、业务 `intent`、Skill 输出或工具结果仅作为回答、草稿和待确认动作的输入。

## 13. 开发拆解建议

### 阶段 1：上传与入库

1. 后端建立单一 `ReportAgent` 运行骨架，完成任务路由、Skill 加载、模型调用、工具结果回传和调用轨迹记录。
2. 前端实现最多 20 个文件的批量选择、逐文件校验、状态展示和单项重试。
3. 后端实现支持 `files` 数组的 `POST /api/upload-report`、内存上传任务注册表和批次状态查询；终态任务按 TTL 清理。
4. 后端实现报告文件保存到患者目录。
5. 后端接入当前账号 `vision_parse` 默认模型完成报告解析。
6. 后端实现 `report-ingestion` Skill 的导入流程和解析输出 schema，并接入已有 `ReportAgent`。
7. 后端实现文件哈希、业务指纹和重复候选识别。
8. 后端实现 `report_source_links` 和 `report_duplicate_resolution` 待确认动作。
9. 后端实现检验、检查、病理、手术和其它报告结构化入库。
10. 前端实现批量上传、解析、重复报告确认、部分失败和入库完成状态。

### 阶段 2：分析链路

1. 前端实现入库确认卡片。
2. 后端实现 `POST /api/reports/{report_id}/analysis`。
3. 后端实现 `report-analysis` Skill、临时数据选择规则和分析输出 schema，并接入已有 `ReportAgent`。
4. 后端实现同日相关报告触发的自动重跑分析。
5. 后端实现分析结果写回 `analysis_sections` 并清除 `analysis_outdated`。
6. 后端实现新报告入库后的同日分析影响评估和 `analysis_outdated` 标记。
7. 前端实现分析中、分析成功、分析失败和分析可能过期状态。
8. 前端实现“查看该报告”跳转。

### 阶段 3：报告场景

1. 后端实现 `GET /api/reports`。
2. 后端实现 `GET /api/reports/{report_id}`。
3. 前端实现报告列表、筛选和排序。
4. 前端实现报告详情。
5. 前端仅为检验报告实现趋势图和指标切换。

### 阶段 4：报告自然语言查询与修正

1. 后端在已有 `ReportAgent` 中接入 `report-query`、`report-correction` 的意图路由和工具调用循环。
2. 后端实现 `report-query`、`report-correction` Skills 的判断步骤和输出 schema。
3. 后端实现受控 `query_report_evidence`、`create_pending_action` 和 `get_pending_action` 工具。
4. 后端扩展 `POST /api/conversations/messages` 的消息级 `report` 上下文资源，支持报告详情、检验趋势和跨报告对比查询。
5. 后端实现 `pending_action`、确认接口和指标原文字段确认修正。
6. 前端实现左侧聊天、右侧可折叠报告面板、聊天末尾文件索引和写入确认卡片。
7. 前端复用现有会话历史导航，并按消息报告引用恢复右侧面板。

### 阶段 5：报告问答、收藏与收尾

1. 前端实现报告分析收藏入口。
2. 后端扩展收藏来源类型。
3. 前端在 `我的收藏` 支持报告类收藏展示。
4. 补齐报告对话、检验原文趋势降级和指标确认修正验收用例。
