# Serenita v1.0.0 应用实现草案

> 文档状态：技术草案 / 未来实现参考
> 当前用途：记录未来应用实现方案的能力清单、接口形态和运行方式设想，供后续拆分版本范围时参考
> 当前执行版本：`v0.1.0`
> ⚠️ 注意：本文档中的接口设计（如 `POST /api/submit-intent`）、数据库方案（PostgreSQL）和部署方式（Docker）均不是当前开发依据，仅供后续拆分版本范围时参考。

## 医疗 Agent 应用骨架 - v1.0.0

基于技术架构规范整理的应用实现草案，用于描述后端、前端、数据表和本地运行方式的目标形态。

---

## 目标能力

### 后端 (FastAPI)

| 端点 | 方法 | 描述 |
|------|------|------|
| `GET /api/health` | GET | 健康检查 |
| `GET /api/demo-payloads` | GET | 获取演示意图载荷 |
| `POST /api/submit-intent` | POST | 提交意图（对话/报告/生活建议） |
| `POST /api/upload-report` | POST | 上传报告并解析入库 |
| `GET /api/reports` | GET | 获取报告列表（支持分类/排序） |
| `GET /api/reports/{report_id}` | GET | 获取单份报告详情 |
| `GET /api/healthkit/cards` | GET | 获取健康数据卡片（心率/血压/血糖） |
| `GET /api/health-journal` | GET | 获取重要记录/健康日志 |
| `POST /api/upload-report-demo` | POST | 演示报告解读 |

### 前端 (React + Vite)

| 功能 | 规划状态 | 说明 |
|------|------|------|
| **首页** | 目标形态 | 对话入口，显示健康卡片，承接所有 LLM 结果 |
| **报告** | 目标形态 | 报告列表 + 详情 + 分析按钮，支持排序筛选 |
| **生活** | 目标形态 | 每日建议入口，获取个性化生活建议 |
| **健康卡片** | 目标形态 | 显示心率、血压、血糖等 HealthKit 数据 |
| **重要记录** | 目标形态 | 首页底部显示健康日志摘要 |

---

## 数据库表

```sql
-- 患者档案
CREATE TABLE patient_profile (
    patient_id TEXT PRIMARY KEY,
    age INT,
    gender TEXT,
    diagnoses JSONB
);

-- 用药历史
CREATE TABLE medication_history (
    id SERIAL PRIMARY KEY,
    patient_id TEXT NOT NULL,
    drug_name TEXT NOT NULL,
    dosage TEXT,
    start_date DATE,
    end_date DATE,
    status TEXT NOT NULL DEFAULT 'active'
);

-- 化验报告
CREATE TABLE lab_reports (
    id SERIAL PRIMARY KEY,
    patient_id TEXT NOT NULL,
    report_date DATE,
    indicators JSONB,
    source TEXT
);

-- 会话日志
CREATE TABLE session_log (
    session_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    mode TEXT,
    state_dump JSONB,
    total_tokens INT,
    latency_ms INT
);

-- 报告表（新增）
CREATE TABLE reports (
    report_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    report_type TEXT NOT NULL,
    report_category TEXT,
    report_time TIMESTAMPTZ,
    parsed_fields JSONB,
    analysis_sections JSONB,
    storage_status TEXT,
    filename TEXT
);

-- 健康日志（新增）
CREATE TABLE health_journal (
    id SERIAL PRIMARY KEY,
    patient_id TEXT NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL,
    summary TEXT NOT NULL,
    source_scene TEXT,
    tags JSONB
);
```

---

## 目标本地运行方式

后续实现可采用以下本地运行方式。

### 方式一：Conda 环境

```powershell
conda env create -f environment.yml
conda activate serenita
uvicorn app.main:app --reload
```

打开:
- `http://127.0.0.1:8000/docs` - API 文档
- `http://127.0.0.1:8000/api/health` - 健康检查

### 方式二：Docker Compose

```powershell
docker compose up --build
```

### 前端启动

```powershell
cd frontend
npm install
npm run dev
```

默认本地访问: `http://127.0.0.1:5173`

---

## 环境变量

可使用以下变量作为 `.env` 内容：

```bash
APP_NAME=Serenita
APP_ENV=development
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/serenita
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT_SECONDS=60
```

---

## API 详情草案

### 上传报告

```bash
curl -X POST "http://127.0.0.1:8000/api/upload-report" \
  -F "file=@lab_report.pdf" \
  -F "patient_id=P-10042"
```

响应:
```json
{
  "report_id": "RPT-P-10042-XXXX",
  "storage_status": "stored",
  "report_type": "化验报告",
  "parsed_fields": {...},
  "message": "报告已完成解析和结构化入库，是否需要进行分析？"
}
```

### 获取报告列表

```bash
curl "http://127.0.0.1:8000/api/reports?patient_id=P-10042&sort=desc"
```

### 获取健康卡片

```bash
curl "http://127.0.0.1:8000/api/healthkit/cards?patient_id=P-10042"
```

---

## 前端 Tab 结构

按 PRD 需求实现三标签页:

1. **首页** - 通用结果承接页，所有 LLM 交互结果在此展示
2. **报告** - 报告列表 + 详情 + 分析功能
3. **生活** - 每日健康建议入口

底部输入栏:
- 左侧: 文件上传按钮
- 右侧: 思考模式选择器 + 发送按钮

---

## 目标冒烟测试

```powershell
conda activate serenita
python smoke_test.py
```

---

## 说明

- 方案设想使用 PostgreSQL 作为持久化存储
- 专家分析服务默认支持 `DeepSeek`，未配置或失败时自动回退到 mock 输出
- 前端目标接入所有新增 API，用于形成交互 demo
- 报告上传后目标自动入库，可在报告页查看和分析
