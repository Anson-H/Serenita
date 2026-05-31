# Serenita 技术架构草案 v1.0.0

> 文档状态：技术草案 / 长期技术架构草案
> 当前用途：记录未来多层架构、Agent 编排和基础设施方向，不等同于当前 `v0.1.0` 必须实现的架构
> 当前执行版本：`v0.1.0`，以登录、对话、会话、收藏为主
> ⚠️ 注意：本文档中的技术选型（PostgreSQL、Docker Compose、Redis、多 Agent 微服务）与当前执行版本 v0.1.0 不同，仅供长期架构讨论。
> ⚠️ 术语说明：本文档使用 `patient_id` 作为用户标识，当前执行文档使用 `account`。若引入独立患者身份体系，需要明确 `account` 与 `patient_id` 的映射规则。
> ⚠️ 侧边栏说明：本文档侧边栏使用"我的资料"和"我的报告"，当前执行版本侧边栏为"报告"、"生活"、"原始文件"、"我的收藏"和左下角账号入口；账号设置位于 `/setting` 页面。两者属于不同范围下的信息架构表达。

## 医疗智能体 MVP — 技术架构规范

**版本：** 1.0.0-MVP | **最后更新：** 2025-07

---

## 0. 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        客户端 (React Web App)                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTPS
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  L1  感知与接入层                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐              │
│  │  OCR 服务  │  │ ASR (未来) │  │ IoT 网关   │              │
│  │  (Vision LM)  │  │              │  │ (未来)      │              │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘              │
│         └─────────┬────────┘                  │                      │
│                   ▼                           ▼                      │
│         结构化意图 JSON         原始时序数据 → L5           │
└───────────────────┬──────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  L2  预计算与 Token 防护 (零 LLM，纯代码)         │
│  ┌──────────────────────────────────────────────────────────┐        │
│  │              数据压缩器 (Python + SQL)                │        │
│  │  50,000 rows  ──→  1 份压缩 JSON  (~200 tokens)      │        │
│  └──────────────────────────┬───────────────────────────────┘        │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  L3  编排层 (FastAPI + Python 异步)                   │
│  ┌──────────────────────────────────────────────────────────┐        │
│  │              全局编排器                      │        │
│  │  • 意图路由 (单次响应 / 多专家会诊)             │        │
│  │  • 上下文窗口预算控制器                      │        │
│  │  • 分发/汇总 Agent 协调器                    │        │
│  └────┬──────────────────┬──────────────────┬───────────────┘        │
│       │  并行分发│                  │                        │
└───────┼──────────────────┼──────────────────┼────────────────────────┘
        ▼                  ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  L4  专家 Agent 微服务 (LLM 推理)                      │
│  ┌────────────────┐ ┌────────────────┐ ┌─────────────────┐          │
│  │ 🩺 临床报告   │ │ 💊 用药安全   │ │ 🥗 生活方式   │          │
│  │   Agent │ │   Agent │ │   教练 Agent   │          │
│  └────────┬───────┘ └────────┬───────┘ └────────┬────────┘          │
│           │                  │                   │                   │
│           └──────────┬───────┘───────────────────┘                   │
│                      ▼                                               │
│              聚合专家结论                            │
└──────────────────────────────────────────────────────────────────────┘
        ▲ 查询                ▲ 查询               ▲ 查询
        │                      │                      │
┌───────┴──────────────────────┴──────────────────────┴────────────────┐
│  L5  基础设施层                                            │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────────┐       │
│  │  PostgreSQL   │  │ TimescaleDB   │  │ Neo4j + Milvus      │       │
│  │  (OLTP 核心)  │  │  (未来)     │  │  (未来)           │       │
│  └──────────────┘  └───────────────┘  └─────────────────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 目标能力状态 (v1.0.0 草案)

| 层级 | 组件 | 状态 | 说明 |
|:---|:---|:---:|:---|
| L1 | 意图分类 | 目标 | 规则分类器 |
| L1 | OCR | 占位 | 返回样例数据 |
| L1 | ASR | 规划 | 规划中 |
| L1 | IoT 网关 | 规划 | 规划中 |
| L2 | 数据压缩器 | 目标 | Python/SQL 实现 |
| L3 | 编排器 | 目标 | FastAPI + 异步 IO |
| L3 | Token 预算 | 目标 | 字符数估算 |
| L4 | 临床 Agent | 目标 | DeepSeek + mock 回退 |
| L4 | 用药 Agent | 目标 | DeepSeek + mock 回退 |
| L4 | 生活方式 Agent | 目标 | DeepSeek + mock 回退 |
| L5 | PostgreSQL | 目标 | 核心 OLTP |
| L5 | TimescaleDB | 规划 | 规划中 |
| L5 | Neo4j/Milvus | 规划 | 规划中 |

**图例:** 目标 | 占位 | 规划

---

## 1. 设计约束

| 编号 | 约束 | 强制级别 | 说明 |
|:---|:---|:---|:---|
| **C-1** | 计算 / 推理分离 | `MUST` | 统计聚合由 Python/SQL 完成；病因归因由 LLM 完成 |
| **C-2** | Token 熔断 | `MUST` | 单次 LLM 调用 `input_tokens` 上限 **4096** |
| **C-3** | 原始时序禁入 LLM | `MUST` | 时序数据经 L2 Condenser 聚合后才能进入 LLM |
| **C-4** | 专家幂等性 | `SHOULD` | L4 Agent 相同输入产出相同结构化 JSON （temperature=0） |
| **C-5** | 故障隔离 | `MUST` | 任一 L4 Agent 超时/异常不阻塞其他 Agent |

---

## 2. 各层详细规范

### 2.1 L1：感知与接入层

**目标能力:**
- 多模态意图解析器 （规则驱动）
- 结构化意图 JSON 输出

**输出结构 (`IntentPayload`):**

```json
{
  "request_id": "uuid-v4",
  "timestamp": "2025-07-11T08:30:00+08:00",
  "patient_id": "P-10042",
  "intent": "upload_report",
  "confidence": 0.95,
  "extracted_data": {
    "source_type": "lab_report_image",
    "parsed_fields": {
      "ALT": { "value": 65, "unit": "U/L", "ref_range": "0-40" }
    }
  },
  "raw_text": "医生，我这个转氨酶怎么又高了..."
}
```

---

### 2.2 L2：预计算与 Token 防护

**目标能力:** 数据压缩器 服务

**触发方式:**
```jsonc
{
  "patient_id": "P-10042",
  "command": "condense",
  "time_window": "30d",
  "metric_types": ["bp_systolic", "cgm_glucose", "heart_rate"]
}
```

**输出结构 (`CondensedSummary`):**

```jsonc
{
  "patient_id": "P-10042",
  "period": "2025-06-11 ~ 2025-07-11",
  "window_days": 30,
  "metrics": {
    "bp": { "avg": "135/85", "morning_surge_count": 5 },
    "cgm_glucose": { "TIR_3.9_10.0": "82%", "hypo_events": 3 },
    "heart_rate": { "resting_avg": 68 }
  }
}
```

---

### 2.3 L3：编排层

**技术选型：** FastAPI + Python 异步 IO

**路由模式:**

**模式 A：单次响应**
```
User Intent ──→ 编排器 ──→ 1~2 Expert Agents ──→ 口语化回复
```
- 适用: upload_report, ask_symptom, daily_checkin
- 延迟: < 8s 端到端

### 2.4 L4：专家 Agent 微服务

#### 2.4.1 临床报告 Agent

**输出结构:**
```jsonc
{
  "agent": "clinical",
  "sections": {
    "good_news": ["HbA1c 从 7.2% 降至 6.8%"],
    "warning": ["ALT 65 U/L, 超上限 1.6 倍"],
    "watch_list": ["建议 2 周后复查肝功"]
  },
  "severity": "YELLOW",
  "tokens_used": 820
}
```

#### 2.4.2 用药安全 Agent

**输出结构:**
```jsonc
{
  "agent": "medication",
  "danger": false,
  "danger_level": "SAFE",
  "analysis": [
    {
      "drug": "阿托伐他汀 20mg",
      "concern": "ALT 65 U/L 偏高",
      "verdict": "CAUTION",
      "reasoning": "他汀类药物已知肝损风险..."
    }
  ]
}
```

#### 2.4.3 生活方式教练 Agent

**输出结构:**
```jsonc
{
  "agent": "lifestyle",
  "insights": [
    {
      "observation": "5次清晨血压飙升与晚睡记录重合",
      "causal_factor": "睡眠不足 → 交感神经兴奋",
      "confidence": "HIGH"
    }
  ],
  "micro_action": {
    "action": "明天下午 3 点喝半杯牛奶",
    "target_metric": "cgm_glucose",
    "expected_impact": "减少低血糖发作"
  }
}
```

---

### 2.5 L5：基础设施层

**当前实现：** PostgreSQL 核心表

```sql
-- 患者档案
CREATE TABLE patient_profile (
    patient_id TEXT PRIMARY KEY,
    age INT,
    gender TEXT,
    diagnoses JSONB
);

-- 用药史
CREATE TABLE medication_history (
    id SERIAL PRIMARY KEY,
    patient_id TEXT,
    drug_name TEXT,
    dosage TEXT,
    status TEXT DEFAULT 'active'
);

-- 化验报告
CREATE TABLE lab_reports (
    id SERIAL PRIMARY KEY,
    patient_id TEXT,
    report_date DATE,
    indicators JSONB,
    source TEXT
);

-- 会话日志
CREATE TABLE session_log (
    session_id TEXT PRIMARY KEY,
    patient_id TEXT,
    mode TEXT,
    state_dump JSONB,
    total_tokens INT,
    latency_ms INT
);

-- 报告表 (v1.0.0 新增)
CREATE TABLE reports (
    report_id TEXT PRIMARY KEY,
    patient_id TEXT,
    report_type TEXT,
    report_category TEXT,
    report_time TIMESTAMPTZ,
    parsed_fields JSONB,
    analysis_sections JSONB,
    storage_status TEXT,
    filename TEXT
);

-- 健康日志 (v1.0.0 新增)
CREATE TABLE health_journal (
    id SERIAL PRIMARY KEY,
    patient_id TEXT,
    entry_time TIMESTAMPTZ,
    summary TEXT,
    source_scene TEXT,
    tags JSONB
);
```

---

## 3. 新增 API 端点 (v1.0.0)

| 端点 | 描述 |
|:---|:---|
| `POST /api/upload-report` | 上传报告文件，解析后入库 |
| `GET /api/reports` | 获取报告列表（支持分类/排序） |
| `GET /api/reports/{id}` | 获取单份报告详情 |
| `GET /api/healthkit/cards` | 获取健康数据卡片 |
| `GET /api/health-journal` | 获取健康日志摘要 |

---

## 4. 前端架构

**技术栈：** React 19 + Vite 8 + 原生 CSS

**页面结构:**
```
┌──────────────────────────────────────────────────────┐
│  侧边栏    │  主内容                          │
│  ─────────  │  ────────────────────────────────────  │
│  品牌      │  标签页: [首页] [报告] [生活]            │
│  新对话     │                                        │
│  历史记录   │  Tab 内容:                             │
│  ─────────  │    - 首页: 对话 + 健康卡片 + 日志      │
│  我的资料   │    - 报告: 列表 + 详情 + 分析          │
│  我的报告   │    - 生活: 每日建议                    │
│  账号设置   │                                        │
│             │  底部栏:                           │
│             │    [+] [模式▼] [发送]                  │
└──────────────────────────────────────────────────────┘
```

---

## 5. 部署架构 (MVP)

```
┌───────────────────────────────────────────────────┐
│                Docker Compose                     │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ FastAPI   │  │ L2       │  │ L4 Agents    │   │
│  │ Gateway   │  │ Condenser│  │ (×3 workers) │   │
│  │ + L3 Orch │  │          │  │              │   │
│  └─────┬─────┘  └────┬─────┘  └──────┬───────┘   │
│        │              │               │           │
│  ┌─────┴──────────────┴───────────────┴────┐      │
│  │              PostgreSQL :5432           │      │
│  └─────────────────────────────────────────┘      │
│                                                   │
│  ┌────────────┐  ┌──────────┐                    │
│  │ 前端   │  │ Redis    │                    │
│  │ React :5173│  │ :6379    │                    │
│  └────────────┘  └──────────┘                    │
└───────────────────────────────────────────────────┘
         │
         │ HTTPS
         ▼
   ┌───────────┐
   │  LLM API  │   DeepSeek / OpenAI
   └───────────┘
```

---

## 6. 关键非功能指标

| 指标 | 目标 | 当前状态 |
|:---|:---|:---:|
| 单次响应延迟 | < 8s (P95) | ✅ ~5-7s |
| 多专家会诊延迟 | < 30s (P95) | ✅ ~15-20s |
| 单次请求 Token | < 10,000 | ✅ ~5,000-8,000 |
| L2 数据压缩器延迟 | < 3s | ✅ ~0.5s |
| API 可用性 | 99.5% | ✅ |

---

**文档结束**
