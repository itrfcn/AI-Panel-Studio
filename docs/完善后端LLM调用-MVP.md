# 完善后端 LLM 调用 — MVP 实现计划与实施记录

> **文档状态**：✅ **已全部实施完成**（阶段 1-5）。本文档保留为实现时的设计依据与决策记录；实际代码见 `backend/app/llm/`、`backend/app/agent/`、`backend/app/stream/`。
>
> 落地后的关键增强（超出原计划范围）见文末 [§ 实施完成记录](#实施完成记录)。

## Context

当前后端骨架已实现（FastAPI + SQLAlchemy + 8 张 ORM 表 + 路由骨架 + 样例数据），但 `roster.generate_roster` 返回 501、`stream.stream_discussion` 返回 503 占位心跳——真正的 AI 圆桌讨论链路未接 LLM。本计划完善 LLM 调用，让"输入话题 → AI 生成阵容 → 主持人开场/收尾"端到端跑通，后续再迭代多专家抢答与共识分歧抽取。

**用户决策**（已确认）：
- LLM 客户端：**httpx 直调**兼容 OpenAI 协议（不引入 openai SDK）
- 实现范围：**先 MVP 跑通**（阶段 1-3），再迭代抢答+抽取
- MAX_TURNS 默认 **8**

## 实现范围（本次 MVP = 阶段 1-3）

### 阶段 1：LLM 客户端 + Prompt 模板 [NEW]
新建 `backend/app/llm/` 包：
- `__init__.py`
- `client.py` — `LLMClient` 单例，封装 `chat()` / `chat_stream()` / `chat_json()`，内部共享一个 `httpx.AsyncClient`，调 `{base_url}/chat/completions`，支持 `stream=True` 拿 SSE chunk。依赖注入 `get_llm_client()`。
- `prompts.py` — 6 个 Prompt 模板函数：`roster_prompt(topic, n)` / `opening_prompt(topic, moderator)` / `followup_prompt(ctx)` / `summary_prompt(ctx)` / `expert_speak_prompt(expert, ctx)` / `extract_prompt(ctx, existing_insights)`。统一中文 system prompt + JSON schema 约束输出。

**验证**：`python -c "import asyncio; from app.llm import get_llm_client; print(asyncio.run(get_llm_client().chat_json([{'role':'user','content':'返回 {ok:true}'}])))"` 返回合法 JSON；`/health` 显示 `configured: true`。

### 阶段 2：roster 接入 [MOD]
改造 `backend/app/api/roster.py` 的 `generate_roster`：
1. 校验 `settings.is_llm_configured()`，否则 503
2. 调 `llm.chat_json(roster_prompt(topic, expert_count), temperature=0.8)`
3. 解析 LLM 返回的 JSON 数组（moderator 1 + experts N），校验字段（name/title/stance/color）
4. 落库 Guest（先清除该 topic 旧候选，再批量插入，sort_order 0=moderator, 1..N=experts）
5. 返回 `RosterOut(is_confirmed=False)`

**验证**：前端准备页输入话题+人数 → 点"生成阵容" → 看到主持人+4 专家档案 → 数据库 guest 表有 5 条记录。

### 阶段 3：状态机校验 + 主持人单轮开场收尾 [NEW + MOD]
- **[NEW] `backend/app/api/_state.py`** — 状态流转校验 helper：`validate_transition(cur, nxt)`，非法转换抛 400。流转图对齐 schema.md §4.1：`draft→setup→ongoing→summarizing→archived`。
- **[NEW] `backend/app/agent/__init__.py` + `base.py`** — Agent 基类：`build_context(db, topic_id, k=8)` 取最近 K 条 Transcript + 对应 guest 拼成 messages。
- **[NEW] `backend/app/agent/moderator.py`** — 主持人 Agent：`opening(topic, moderator)` 调 `opening_prompt` 流式返回开场白；`closing(topic, ctx)` 调 `summary_prompt` 返回收尾总结。
- **[NEW] `backend/app/stream/__init__.py` + `events.py`** — SSE 事件工厂：`make_transcript_event()` / `make_state_event()` / `make_insight_event()` / `make_system_event()` / `make_end_event()`，schema 对齐前端 `frontend/src/api/stream.js` 的 handler。
- **[NEW] `backend/app/stream/orchestrator.py`** — MVP 版主循环 async generator（只跑主持人）：
  ```
  async def run_discussion(topic_id):
      yield system("discussion started")
      yield state(moderator, idle→preparing)
      yield state(moderator, preparing→speaking)
      async for delta in moderator.opening(): yield transcript(streaming, delta)
      yield transcript(done)
      yield state(moderator, speaking→idle)
      yield state(moderator, idle→preparing)
      yield state(moderator, preparing→speaking)
      yield transcript(summary, moderator.closing())  # 收尾
      yield state(moderator, speaking→已退出)
      topic.status = "archived"; summary 落库
      yield end(summary)
  ```
- **[MOD] `backend/app/api/stream.py`** — `stream_discussion` 替换占位 `event_generator` 为 `orchestrator.run_discussion(topic_id)`；每 yield 内部用 `SessionLocal()` 独立 session 写库（避免跨 yield 持有），开场白 + 收尾各落一条 Transcript（speech_type=opening/summary，status=done）。
- **[MOD] `backend/app/api/topics.py`** — `update_topic` 调 `_state.validate_transition`。

**验证**：前端 StudioView 进入 ongoing 话题 → 收到 `state` 切换 + `transcript` 流式开场白 + `transcript` 收尾 + `end`；数据库 transcript 表有 2 条记录（opening + summary），topic.status 变 archived。

## 不在本次 MVP 范围（后续阶段 4-5）

- **阶段 4**：多专家抢答循环（`agent/expert.py` + `agent/arbiter.py` + `orchestrator` 完整循环 + EventPoint 落库 hand_raise/grab_arbitration/grab_result）— ✅ **已完成**
- **阶段 5**：共识/分歧抽取（`agent/extractor.py` 增量 + finalize）+ `replay_discussion` 组装回放 — ✅ **已完成**

这些阶段已迭代落地，骨架预留的事件类型与 schema 均已启用。

## 依赖更新 [MOD]

`backend/requirements.txt` 追加：
```
httpx==0.27.2
```
（不引入 openai SDK）

## 关键设计约束（必须遵守）

1. **安全**：API Key 只在 `config.py` 从 .env 读，`LLMClient` 用 `settings.LLM_API_KEY` 设 Authorization header，绝不通过 API 响应暴露（PRD §7）。
2. **上下文窗口**：`build_context` 只取最近 K=8 条 Transcript（`settings.AGENT_CONTEXT_WINDOW_K`），避免长上下文幻觉（PRD §3.3）。
3. **SSE 事件协议**：严格对齐前端 `frontend/src/api/stream.js` 的 handler（transcript/state/insight/system/heartbeat/end），event 名小写、payload JSON。
4. **不重写历史**：Insight 增量只做 version+1（阶段 5 用，MVP 不涉及）。
5. **Transcript 不显示内部事件**：举手等进 EventPoint，Transcript 只存发言内容（PRD §4.3）。

## 关键文件清单

**新建**：
- `backend/app/llm/__init__.py` / `client.py` / `prompts.py`
- `backend/app/agent/__init__.py` / `base.py` / `moderator.py`
- `backend/app/stream/__init__.py` / `events.py` / `orchestrator.py`
- `backend/app/api/_state.py`

**改造**：
- `backend/app/api/roster.py`（generate_roster 接入 LLM）
- `backend/app/api/stream.py`（stream_discussion 接入 orchestrator）
- `backend/app/api/topics.py`（update_topic 状态校验）
- `backend/app/main.py`（startup 时构造 LLMClient 单例，shutdown 时关闭 httpx）
- `backend/requirements.txt`（+ httpx）

## 快速开始

1. **配置 .env**：`cp backend/.env.example backend/.env`，填入真实 `LLM_API_KEY`（DeepSeek/OpenAI 兼容厂商）
2. **重置库**：`cd backend && python scripts/init_db.py`
3. **启动后端**：`uvicorn app.main:app --reload --port 8000`
4. **健康检查**：`GET /health` → `llm.configured: true`
5. **前端联调**：前端 `.env` 改 `VITE_USE_MOCK=false`，`npm run dev`
6. **端到端**：准备页输入话题 → 生成阵容 → 确认 → 进入演播厅 → 看到 LLM 生成的主持人开场白流式输出 + 专家多轮抢答 + 收尾总结 → 数据库 transcript/insight 表有对应记录

## 风险与缓解

- **LLM 返回非合法 JSON**：`chat_json` 加 try/except，失败时返回 502 + 原始文本片段便于调试；Prompt 里用 `response_format={"type":"json_object"}` 强约束。
- **跨 yield 持有 session**：orchestrator 每 yield 内部新开 `SessionLocal()`，写入后立即 commit + close。
- **SSE 连接断开**：orchestrator 用 try/finally 包裹，断开时把 in-flight transcript 状态置 aborted。

---

## 实施完成记录

> 以下为 MVP 落地后，根据实际运行反馈新增的设计与修复，属原计划之外的增强。

### 性能优化

| 问题 | 处理 | 涉及文件 |
|------|------|----------|
| 每轮多次 LLM 往返，等待感强 | 主持人「追问串联」与「是否继续」判断**合并为一次流式调用**，判定标记随文本尾部输出，服务端解析后剥离、不落库不展示 | `llm/prompts.py`、`agent/moderator.py`、`stream/orchestrator.py` |
| 需等最慢专家才集体举手 | 举手决策改用 `FIRST_COMPLETED` 语义，**谁先返回谁先推送** `state` 事件 | `stream/orchestrator.py` |
| 发言首 token 前的空白期 | 发言开始前先推送**空 delta 占位**，前端立即显示发言人，随后逐字填充 | `stream/orchestrator.py` |
| 决策期前端"死寂" | 前端根据 `system.phase` 显示「专家们正在思考…」「正在提取共识与分歧…」动画 | `frontend/src/views/StudioView.vue`、`components/Transcript.vue` |
| 举手 JSON 输出冗长 | `decide_raise_hand` 的 `max_tokens` 128 → 96 | `agent/expert.py` |

### 容错与稳定性

| 问题 | 处理 | 涉及文件 |
|------|------|----------|
| 上游过载返回 `HTTP 200` + 流体内嵌 `{"error":...}` 伪成功帧 → 发言被静默记空 | 识别错误帧并**指数退避重试**（2/4/8s）；已产出 delta 后失败不重试，避免发言重复 | `llm/client.py` |
| 多 SSE 连接启动多个 orchestrator → 讨论双跑、开场被挤成 aborted | 每场讨论**服务端单实例**运行，多观察者 fan-out 共享事件，晚加入自动补发历史 | `stream/runner.py` |
| SSE 丢事件导致前端缺失发言 | 讨论结束后用 replay 接口补全 / 校正本地发言列表 | `frontend/src/views/StudioView.vue` |
| 持续过载导致整段发言落空 | orchestrator 增加重试与兜底 | `stream/orchestrator.py` |

### 交互与需求对齐

| 问题 | 处理 | 涉及文件 |
|------|------|----------|
| 专家区分度不足、缺乏举手机制、出现同时抢答 | 前端补 `state` 事件处理、小窗显示 ✋ 举手态；发言顺序规范为 `grab→supplement→rebute`；阵容生成强化对立立场 | `stream/orchestrator.py`、`components/GuestPanel.vue`、`views/StudioView.vue` |
| 主持人引导不可见 | 主持人每轮以点名 + 具体问题 + 指定焦点的方式串联；被点名专家优先发言且第一句直接回答 | `llm/prompts.py`、`agent/base.py` |
| 主持人突然收尾 / 无限讨论 | 收尾标准由「达成共识」改为「讨论原地打转」检测（观点重复 / 无新论据），新增 stale 信号辅助；最低 2 轮保障 + `MAX_TURNS` 兜底 | `llm/prompts.py`、`agent/moderator.py`、`stream/orchestrator.py` |
| 思考弹窗仅"抢答"标签有内容 | 举手事件 `turn_index` 为轮首序号而发言序号递增，等值匹配失效 → 改为**贪心对齐**（按序号不早于举手时刻、未被消费的最早一条发言匹配） | `api/topics.py` |
| 收尾总结重复渲染 | 删除 mock 时代残留的底部 summary 区块 | `components/Transcript.vue`、`components/StudioRoom.vue` |

### 新增能力

- **思考过程弹窗**：新增 `GET /api/topics/{id}/guests/{guest_id}/thoughts` 接口 + `ThoughtModal.vue`，可单独查看某位嘉宾逐轮举手思考与实际发言时间线
- **强制中断讨论**：新增终态 `cancelled`、`POST /api/topics/{id}/stream/cancel` 端点、前端自定义确认弹窗；中断后已产生的发言与共识/分歧保留，可回放

### 测试

- `backend/scripts/e2e_test.py` 端到端脚本覆盖 HTTP API、SSE 事件协议、DB 持久化与回放，运行结束打印 `结果: N/N 通过`
