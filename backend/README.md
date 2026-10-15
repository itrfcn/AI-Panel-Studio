# AI Panel Studio — Backend

> FastAPI + SQLAlchemy 2.0 + SQLite + SSE，实现「多 Agent 圆桌讨论」的完整 LLM 链路。
> 对齐 [docs/PRD.md](../docs/PRD.md) 与 [docs/schema.md](../docs/schema.md)。

---

## 1. 目录结构

```
backend/
├── .env.example          # 环境变量模板（复制为 .env 后填写真实 Key）
├── requirements.txt
├── app/
│   ├── main.py           # FastAPI 入口（lifespan 建表 + 预热/关闭 LLMClient）
│   ├── config.py         # 配置：从 .env 读 LLM_API_KEY（绝不硬编码、不下发前端）
│   ├── database.py       # engine / session + PRAGMA foreign_keys=ON
│   ├── models/           # ORM（对齐 schema.md 8 张表）
│   ├── schemas/          # Pydantic v2 API 契约
│   ├── api/              # 路由层
│   │   ├── router.py     # 路由聚合（前缀 /api）
│   │   ├── topics.py     # 讨论列表/创建/详情/状态/思考时间线
│   │   ├── roster.py     # 阵容生成/获取/确认
│   │   ├── stream.py     # SSE 实时流 / 强制中断 / 回放
│   │   ├── insights.py   # 共识与分歧
│   │   └── _state.py     # topic 状态机流转校验
│   ├── llm/              # LLMClient（chat / chat_stream / chat_json）+ Prompt 模板
│   ├── agent/            # base / moderator / expert / arbiter / extractor
│   └── stream/           # events 事件工厂 / runner 会话管理 / orchestrator 主循环
└── scripts/
    ├── init_db.py        # 建表 + 样例数据（5 话题 / 25 嘉宾）
    └── e2e_test.py       # 端到端验证脚本
```

---

## 2. 快速开始

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt

copy .env.example .env          # 填入真实 LLM_API_KEY
python scripts/init_db.py       # 建表 + 样例数据

uvicorn app.main:app --reload --port 8000
```

- 健康检查：<http://localhost:8000/health>（返回 `llm.configured`，**不含 Key**）
- Swagger：<http://localhost:8000/docs>

---

## 3. 配置说明（安全约束）

配置由 `app/config.py` 基于 pydantic-settings 从 `.env` 读取，优先级：`os.environ` > `.env` > 默认值。

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `LLM_API_KEY` | ✅ | — | 大模型 Key，**仅后端读取**，不通过 API 响应暴露（PRD §7） |
| `LLM_BASE_URL` | | `https://api.deepseek.com/v1` | 兼容 OpenAI 协议的 Base URL |
| `LLM_MODEL` | | `deepseek-chat` | 模型名 |
| `LLM_TEMPERATURE` | | `0.7` | 默认温度（各 Agent 覆盖） |
| `APP_ENV` | | `dev` | `dev` / `test` / `prod` |
| `APP_HOST` / `APP_PORT` | | `0.0.0.0` / `8000` | 监听地址与端口 |
| `DATABASE_URL` | | `sqlite:///./ai_panel_studio.db` | SQLite 连接串 |
| `MAX_TURNS` | | `8` | 专家发言最大轮次，达到后强制收尾 |
| `AGENT_CONTEXT_WINDOW_K` | | `8` | 每位 Agent 读取最近 K 条发言 |
| `EXTRACTION_MIN_TRANSCRIPTS` | | `2` | 触发共识/分歧抽取的最少发言条数 |
| `DEFAULT_EXPERT_COUNT` / `MIN_EXPERT_COUNT` / `MAX_EXPERT_COUNT` | | `4` / `2` / `6` | 专家人数默认值与上下限 |

校验：`GET /health` 返回 `llm.configured` 字段，**不会泄露 Key**。

---

## 4. API 一览

统一前缀 `/api`。

### 元信息

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 + LLM 配置状态 |
| GET | `/` | 服务信息与端点索引 |

### 讨论 topics

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/topics` | 讨论列表（分页 + 状态过滤） |
| POST | `/api/topics` | 创建讨论（`draft`） |
| GET | `/api/topics/{topic_id}` | 讨论详情（含嘉宾阵容） |
| PATCH | `/api/topics/{topic_id}` | 更新状态 / 总结（状态机校验） |
| POST | `/api/topics/{topic_id}/start` | 触发讨论 → `ongoing` |
| GET | `/api/topics/{topic_id}/guests/{guest_id}/thoughts` | 嘉宾思考时间线（举手思考 + 对应发言） |

### 阵容 roster

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/topics/{topic_id}/roster/generate` | LLM 生成候选阵容（1 主持人 + N 专家） |
| GET | `/api/topics/{topic_id}/roster` | 获取阵容 |
| POST | `/api/topics/{topic_id}/roster/confirm` | 确认阵容 |

### 实时流 stream

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/topics/{topic_id}/stream` | **SSE** 实时推送（发言 / 状态 / 共识分歧 / 结束） |
| POST | `/api/topics/{topic_id}/stream/cancel` | 强制中断讨论 → `cancelled` |
| GET | `/api/topics/{topic_id}/stream/replay` | 回放（`archived` / `cancelled`） |

### 共识与分歧 insights

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/topics/{topic_id}/insights` | 共识 / 分歧列表 |
| GET | `/api/topics/{topic_id}/insights/{insight_id}` | 单条详情（含关联发言与推理链） |

---

## 5. SSE 事件协议

事件为 `{ event, data }`，`data` 为 JSON 字符串，事件名小写：

| `event` | `data` 主要字段 |
|---------|-----------------|
| `system` | `topic_id`, `message`, `phase`（`opening` / `expert_decide` / `no_speaker` / `extract` / `decide` / `closing` / `summary` / `finalize`） |
| `state` | `guest_id`, `guest_name`, `guest_color`, `state`（`idle` / `hand_raised` / `preparing` / `speaking`）, `thought` |
| `transcript` | `transcript_id`, `guest_id`, `turn_index`, `speech_type`, `status`（`streaming` / `done` / `aborted`）, `delta`, `content` |
| `insight` | `insight_id`, `action`（`create` / `update` / `finalize`）, `type`, `summary`, `strength`, `version`, `is_final` |
| `heartbeat` | — |
| `end` | `topic_id`, `summary` |

---

## 6. 运行机制

### 讨论主循环（`stream/orchestrator.py`）

```
system(opening) → 主持人开场（流式）
  ┌─ 循环（每轮） ────────────────────────────────────────┐
  │ system(expert_decide) → 全体专家并发举手决策            │
  │   （FIRST_COMPLETED：谁先返回谁先推送 state）            │
  │ Arbiter 仲裁排序 → 胜者依次流式发言（最多 3 位）          │
  │ 主持人追问串联 + 判断是否继续（单次流式调用，含标记）      │
  │ system(extract) → 增量抽取共识 / 分歧                   │
  └──────────────────────────────────────────────────────┘
主持人收尾总结（流式）→ finalize 标记最终版 → topic 归档
```

**仲裁优先级**：`grab > supplement > rebute`，同级按举手先后 FIFO。举手与仲裁过程仅写入 `event_point`，不出现在 Transcript。

**收尾判据**：主持人自主判断（结合本轮是否出现新论据）+ 上一轮新增洞见为 0 的 stale 信号 + 最低 2 轮保障 + `MAX_TURNS` 兜底；判定解析失败时保守选择继续。

### 会话管理（`stream/runner.py`）

- 每场讨论**全局单实例**：多个 SSE 连接共享同一编排任务（fan-out），晚加入者自动补发历史事件
- 连接断开仅退订，不影响讨论继续
- `cancel_discussion()` 取消后台 pump task，并注销会话

### 容错（`llm/client.py`）

- 非流式调用：对 408/409/429/5xx 指数退避重试（最多 3 次）
- 流式调用：仅在**尚未产出任何 delta** 时重试；已产出内容后失败不重试，避免发言重复
- 识别上游「HTTP 200 + 流体内嵌 `{"error": ...}`」伪成功帧，避免静默空发言

---

## 7. 数据库

- 8 张表，对齐 [docs/schema.md](../docs/schema.md)：`topic` / `guest` / `transcript` / `event_point` / `insight` / `insight_speech` / `insight_guest` / `reasoning_chain`
- 外键开启：`PRAGMA foreign_keys=ON`（`app/database.py`）
- `topic.status` 状态机：`draft → setup → ongoing → summarizing → archived`，且 `ongoing` / `summarizing` 可被强制中断为 `cancelled`
- 样例数据：**5 个不同风格话题 + 25 位嘉宾**（每话题 1 主持人 + 4 专家）；`archived` 话题额外含发言、共识/分歧与推理链

重置数据（会清空并重建）：

```bash
python scripts/init_db.py
```

---

## 8. 测试

```bash
python scripts/e2e_test.py
```

脚本会自行在独立端口启动 uvicorn 子进程、使用独立测试数据库，覆盖 HTTP API、SSE 事件协议、数据库持久化与回放等主流程，结束打印 `结果: N/N 通过`。

> 注意：会真实调用大模型，耗时取决于所选厂商的推理速度。

---

## 9. 后续可优化方向

- 共识 / 分歧抽取的增量合并策略（当前按轮触发，可进一步按语义去重）
- 支持不同专家绑定不同模型 / 供应商（当前共用单一 `LLMClient`）
- 讨论过程的可观测性（结构化日志与耗时埋点）
- 面向生产的鉴权、限流与 CORS 收紧
