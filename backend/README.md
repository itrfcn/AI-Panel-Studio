# AI Panel Studio — Backend

> FastAPI + SQLAlchemy 2.0 + SQLite，对齐 `docs/schema.md` 与 `docs/PRD.md`。

## 1. 目录结构

```
backend/
├── .env.example          # 环境变量模板（复制为 .env 后填写真实 Key）
├── requirements.txt
├── app/
│   ├── main.py           # FastAPI 入口
│   ├── config.py         # 从 .env 读 LLM_API_KEY（绝不硬编码）
│   ├── database.py       # SQLAlchemy engine/session + PRAGMA foreign_keys=ON
│   ├── models/           # ORM（对齐 schema.md 8 张表）
│   ├── schemas/          # Pydantic v2 API 契约
│   └── api/              # RESTful 路由骨架
└── scripts/
    └── init_db.py        # 建表 + 插入 ≥5 条样例数据
```

## 2. 快速开始

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

cp .env.example .env           # 填入 LLM_API_KEY

# 建表 + 样例数据
python scripts/init_db.py

# 启动
uvicorn app.main:app --reload --port 8000
```

打开 http://localhost:8000/docs 查看 Swagger。

## 3. 配置说明（安全约束）

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_API_KEY` | ✅ | 大模型 Key，**仅后端读取**，不通过 API 响应暴露（PRD §7） |
| `LLM_BASE_URL` |   | 兼容 OpenAI 协议的厂商 Base URL |
| `LLM_MODEL` |    | 模型名 |
| `DATABASE_URL` |  | SQLite 路径，默认 `sqlite:///./ai_panel_studio.db` |

校验：`GET /health` 返回 `llm.configured` 字段，**不会泄露 Key**。

## 4. 主要 API（骨架）

| 端点 | 方法 | 说明 | 状态 |
|------|------|------|------|
| `/api/topics` | GET | 首页讨论列表 | ✅ |
| `/api/topics` | POST | 创建讨论（draft） | ✅ |
| `/api/topics/{id}` | GET | 讨论详情（含阵容） | ✅ |
| `/api/topics/{id}` | PATCH | 更新状态/总结 | ✅ |
| `/api/topics/{id}/start` | POST | 触发讨论→ongoing | ✅ |
| `/api/topics/{id}/roster/generate` | POST | LLM 生成阵容 | 🚧 待接 LLM |
| `/api/topics/{id}/roster` | GET | 获取阵容 | ✅ |
| `/api/topics/{id}/roster/confirm` | POST | 确认阵容→setup | ✅ |
| `/api/topics/{id}/stream` | GET (SSE) | Transcript + Insight 实时流 | 🚧 待接 Agent |
| `/api/topics/{id}/stream/replay` | GET | 回放 archived 讨论 | 🚧 |
| `/api/topics/{id}/insights` | GET | 共识/分歧列表 | ✅ |
| `/api/topics/{id}/insights/{iid}` | GET | Insight 详情（含关联） | ✅ |

🚧 标记路由已落地状态校验与数据契约，仅缺 LLM/Agent 调用逻辑（按 PRD §3.3 多 Agent 调度策略接入）。

## 5. 数据库

- 8 张表，对齐 `docs/schema.md`
- 外键开启：`PRAGMA foreign_keys=ON`（`app/database.py`）
- 样例数据：5 个不同风格话题 + 25 嘉宾；archived 话题含 transcript + insight + 推理链

重置数据：

```bash
python scripts/init_db.py   # drop_all + create_all + seed
```

## 6. 已完成能力 / 后续优化

**已完成**：
- 项目骨架、配置、数据库连接、ORM、Pydantic 契约、路由骨架
- 样例数据脚本
- PRD §7 安全约束：API Key 不暴露

**后续优化**：
- 接入 LLM 客户端（阵容生成 / Agent 发言 / Insight 抽取）
- 多 Agent 调度器（PRD §3.3，分阶段分上下文）
- SSE 主循环（主持人开场→专家抢答→收尾）
- 状态机非法转换校验（schema.md §4.1）
- E2E 测试（对齐 PRD §3.1 交付物）
