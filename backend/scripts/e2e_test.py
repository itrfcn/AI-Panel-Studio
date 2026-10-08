"""
端到端验证脚本 — 跑通"输入话题 → 阵容 → 抢答讨论 → 共识分歧 → 归档"全链路。

自启独立 uvicorn 子进程（端口 8001，MAX_TURNS=2），不影响已在 8000 运行的服务；
跑的是当前工作区代码，结束自动清理子进程。

用法：
    cd backend
    python scripts/e2e_test.py
    # 自定义参数
    E2E_MAX_TURNS=3 E2E_EXPERTS=4 python scripts/e2e_test.py

依赖：httpx（项目 requirements 已含）。API Key 仅从 .env 读取，脚本不硬编码。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

# --- 让脚本能 import 后端 app ---
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)  # 保证读取到 .env 与 SQLite 文件

# --- 配置（可被环境变量覆盖，不写死 Key） ---
PORT = int(os.environ.get("E2E_PORT", "8001"))
HOST = "127.0.0.1"
BASE_URL = f"http://{HOST}:{PORT}"
MAX_TURNS = os.environ.get("E2E_MAX_TURNS", "2")
EXPERT_COUNT = int(os.environ.get("E2E_EXPERTS", "3"))
TOPIC_TITLE = "远程办公是否会成为主流"
SSE_TIMEOUT = float(os.environ.get("E2E_SSE_TIMEOUT", "300"))
STARTUP_TIMEOUT = 40.0
# 独立 DB 文件：脚本进程与 uvicorn 子进程都必须在 import app.* 前指向它
E2E_DB_NAME = "ai_panel_studio_e2e.db"
os.environ["DATABASE_URL"] = f"sqlite:///./{E2E_DB_NAME}"

# Windows 下不输出 ANSI 颜色转义
_IS_WIN = sys.platform.startswith("win")


class C:
    GREEN = "" if _IS_WIN else "\033[92m"
    RED = "" if _IS_WIN else "\033[91m"
    YELLOW = "" if _IS_WIN else "\033[93m"
    CYAN = "" if _IS_WIN else "\033[96m"
    RESET = "" if _IS_WIN else "\033[0m"
    BOLD = "" if _IS_WIN else "\033[1m"


results: list[tuple[bool, str, str]] = []  # (ok, name, detail)


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((ok, name, detail))
    mark = f"{C.GREEN}PASS{C.RESET}" if ok else f"{C.RED}FAIL{C.RESET}"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def info(msg: str) -> None:
    print(f"{C.CYAN}›{C.RESET} {msg}")


# ---------------------------------------------------------------------------
# 子进程管理
# ---------------------------------------------------------------------------


def port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def start_server() -> subprocess.Popen:
    """启动独立 uvicorn 子进程，MAX_TURNS 通过环境变量注入（缩短验证时长）。"""
    # 独立 DB 文件：避免与 8000 端口 dev 后端（可能被浏览器访问）共用 SQLite
    e2e_db = BACKEND_DIR / E2E_DB_NAME
    if e2e_db.exists():
        e2e_db.unlink()
    env = os.environ.copy()
    env["MAX_TURNS"] = MAX_TURNS
    env["APP_PORT"] = str(PORT)
    env["DATABASE_URL"] = f"sqlite:///./{E2E_DB_NAME}"
    info(f"启动 uvicorn 子进程: {HOST}:{PORT} (MAX_TURNS={MAX_TURNS})")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if _IS_WIN else 0
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
    )
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"uvicorn 启动即退出 (code={proc.returncode})\n{out[-2000:]}")
        if port_open(HOST, PORT):
            # 等应用就绪
            try:
                r = httpx.get(f"{BASE_URL}/health", timeout=2)
                if r.status_code == 200:
                    return proc
            except httpx.TransportError:
                pass
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"等待 {HOST}:{PORT} 就绪超时（{STARTUP_TIMEOUT}s）")


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        info("停止 uvicorn 子进程")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# SSE 解析
# ---------------------------------------------------------------------------


async def consume_sse(client: httpx.AsyncClient, topic_id: int) -> dict:
    """消费 SSE 流，返回事件统计与原始事件列表。"""
    counts: Counter = Counter()
    transcripts_done: list[dict] = []
    transcript_deltas: dict[int, str] = {}
    insights: list[dict] = []
    states: list[dict] = []
    systems: list[dict] = []
    end_seen = False

    # 简易 SSE 解析：按行读，event:/data: 成对
    current_event = None
    async with client.stream(
        "GET", f"{BASE_URL}/api/topics/{topic_id}/stream", timeout=SSE_TIMEOUT
    ) as resp:
        if resp.status_code != 200:
            body = (await resp.aread()).decode("utf-8", "replace")
            raise RuntimeError(f"SSE 返回 {resp.status_code}: {body[:500]}")
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                current_event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_str = line[len("data:"):].strip()
                try:
                    payload = json.loads(data_str) if data_str and data_str != "{}" else {}
                except json.JSONDecodeError:
                    payload = {"_raw": data_str}
                counts[current_event] += 1
                if current_event == "transcript":
                    tid = payload.get("transcript_id")
                    status = payload.get("status")
                    if status == "streaming":
                        transcript_deltas[tid] = transcript_deltas.get(tid, "") + (
                            payload.get("delta") or ""
                        )
                    elif status == "done":
                        transcripts_done.append(payload)
                elif current_event == "insight":
                    insights.append(payload)
                elif current_event == "state":
                    states.append(payload)
                elif current_event == "system":
                    systems.append(payload)
                elif current_event == "end":
                    end_seen = True
                current_event = None

    return {
        "counts": counts,
        "transcripts_done": transcripts_done,
        "transcript_deltas": transcript_deltas,
        "insights": insights,
        "states": states,
        "systems": systems,
        "end_seen": end_seen,
    }


async def shadow_subscribe(client: httpx.AsyncClient, topic_id: int) -> dict:
    """回归测试：第二个观察者晚加入订阅同一场讨论，随后主动断开。

    预期（单实例编排 + fan-out）：
    - 能收到事件（history 补发 / 实时广播）
    - 断开不影响主讨论（由最终 DB 无 aborted 断言兜底）
    """
    await asyncio.sleep(3)  # 等主订阅把 pump 拉起来
    stats: Counter = Counter()
    try:
        async with client.stream(
            "GET", f"{BASE_URL}/api/topics/{topic_id}/stream", timeout=SSE_TIMEOUT
        ) as resp:
            if resp.status_code != 200:
                return {"ok": False, "reason": f"status={resp.status_code}", "stats": stats}
            deadline = asyncio.get_event_loop().time() + 20
            current_event = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    stats[current_event] += 1
                    current_event = None
                if asyncio.get_event_loop().time() >= deadline:
                    break  # 主动离开，模拟观察者关页面
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc), "stats": stats}
    return {"ok": stats.total() > 0, "reason": "", "stats": stats}


# ---------------------------------------------------------------------------
# DB 校验
# ---------------------------------------------------------------------------


def verify_db(topic_id: int) -> dict:
    """直接读 SQLite 校验最终持久化状态。"""
    from sqlalchemy import func, select

    from app.database import SessionLocal
    from app.models import EventPoint, Guest, Insight, Topic, Transcript

    db = SessionLocal()
    try:
        topic = db.get(Topic, topic_id)
        guests = (
            db.execute(
                select(Guest).where(Guest.topic_id == topic_id).order_by(Guest.sort_order)
            )
            .scalars()
            .all()
        )
        transcripts = (
            db.execute(
                select(Transcript)
                .where(Transcript.topic_id == topic_id)
                .order_by(Transcript.turn_index)
            )
            .scalars()
            .all()
        )
        events = (
            db.execute(
                select(EventPoint).where(EventPoint.topic_id == topic_id)
            )
            .scalars()
            .all()
        )
        insights = (
            db.execute(
                select(Insight).where(Insight.topic_id == topic_id)
            )
            .scalars()
            .all()
        )
        return {
            "topic": topic,
            "guests": guests,
            "transcripts": transcripts,
            "event_types": Counter(e.event_type for e in events),
            "insights": insights,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


async def run_flow() -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(200.0, connect=10.0)) as client:
        # 1. health
        info("1/6 健康检查 GET /health")
        r = await client.get(f"{BASE_URL}/health")
        health = r.json()
        check("health 返回 200", r.status_code == 200)
        check("LLM 已配置 (configured=true)", health.get("llm", {}).get("configured") is True,
              f"model={health.get('llm', {}).get('model')}")

        # 2. 创建话题
        info(f"2/6 创建话题 POST /api/topics 「{TOPIC_TITLE}」")
        r = await client.post(
            f"{BASE_URL}/api/topics",
            json={"title": TOPIC_TITLE, "expert_count": EXPERT_COUNT},
        )
        check("创建话题 201", r.status_code == 201, f"status={r.status_code}")
        topic = r.json()
        topic_id = topic["id"]
        check("初始状态 draft", topic["status"] == "draft", f"topic_id={topic_id}")

        # 3. 生成阵容
        info("3/6 生成阵容 POST /roster/generate（调用 LLM，约 10-30s）")
        t0 = time.time()
        r = await client.post(
            f"{BASE_URL}/api/topics/{topic_id}/roster/generate",
            json={"topic_id": topic_id, "expert_count": EXPERT_COUNT},
            timeout=200,
        )
        elapsed = time.time() - t0
        check("阵容生成 200", r.status_code == 200,
              f"status={r.status_code} detail={r.text[:200]}")
        roster = r.json()
        guests = roster["guests"]
        mods = [g for g in guests if g["role"] == "moderator"]
        exps = [g for g in guests if g["role"] == "expert"]
        check("1 位主持人", len(mods) == 1,
              mods[0]["name"] if mods else "无主持人")
        check(f"{EXPERT_COUNT} 位专家", len(exps) == EXPERT_COUNT,
              "、".join(e["name"] for e in exps))
        hex_ok = all(re.match(r"^#[0-9A-Fa-f]{6}$", g["color"]) for g in guests)
        check("颜色均为 #RRGGBB", hex_ok)
        diverse_stances = len({(e.get("stance") or "")[:8] for e in exps}) >= 2
        check("专家立场多样化", diverse_stances)
        print(f"      阵容生成耗时 {elapsed:.1f}s")

        # 4. 确认 + 启动
        info("4/6 确认阵容 /roster/confirm 并 /start")
        r = await client.post(f"{BASE_URL}/api/topics/{topic_id}/roster/confirm")
        check("阵容确认 200", r.status_code == 200 and r.json()["is_confirmed"] is True)
        r = await client.post(f"{BASE_URL}/api/topics/{topic_id}/start")
        check("启动讨论 200", r.status_code == 200)
        check("状态切到 ongoing", r.json()["status"] == "ongoing")

        # 5. SSE（同时启动一个"晚加入观察者"做并发订阅回归）
        info(f"5/6 订阅 SSE（最多 {SSE_TIMEOUT:.0f}s，MAX_TURNS={MAX_TURNS}）")
        t0 = time.time()
        shadow_task = asyncio.create_task(shadow_subscribe(client, topic_id))
        stream = await consume_sse(client, topic_id)
        sse_elapsed = time.time() - t0
        shadow = shadow_task.done() and shadow_task.result() or None
        if not shadow_task.done():
            shadow_task.cancel()
            shadow = {"ok": False, "reason": "shadow task timeout", "stats": Counter()}
        c = stream["counts"]
        print(f"      事件统计: {dict(c)}；流耗时 {sse_elapsed:.1f}s")
        check("收到 end 事件", stream["end_seen"])
        check(
            "并发观察者晚加入可收到事件（单实例 fan-out）",
            bool(shadow and shadow.get("ok")),
            f"{dict(shadow['stats']) if shadow else None} {shadow.get('reason') if shadow else ''}",
        )
        check("有 system 事件", c.get("system", 0) >= 1)
        check("有 state 事件", c.get("state", 0) >= 1)
        check("transcript 流式增量存在", len(stream["transcript_deltas"]) >= 1,
              f"{len(stream['transcript_deltas'])} 条发言有流式 delta")
        check("transcript done 存在", len(stream["transcripts_done"]) >= 2,
              f"{len(stream['transcripts_done'])} 条完整发言")

        # 发言类型序列：opening → [grab|supplement|rebute]… → summary
        speech_types = [t["speech_type"] for t in stream["transcripts_done"]]
        check("首条为 opening", speech_types and speech_types[0] == "opening",
              str(speech_types))
        check("末条为 summary", speech_types and speech_types[-1] == "summary")
        expert_speeches = [s for s in speech_types[1:-1] if s in ("grab", "supplement", "rebute")]
        check("中间有专家发言", len(expert_speeches) >= 1, str(expert_speeches))
        expert_types_ok = all(s in ("grab", "supplement", "rebute") for s in expert_speeches)
        check("专家发言类型合法", expert_types_ok, str(expert_speeches))
        followup_count = speech_types[1:-1].count("followup")
        check("主持人串联存在", followup_count >= 1, f"followup×{followup_count}")

        # done 的 content 应非空且与 delta 累积一致
        for t in stream["transcripts_done"]:
            tid = t["transcript_id"]
            if not t.get("content"):
                check(f"transcript#{tid} content 非空", False)
                break
        else:
            check("所有 done 发言 content 非空", True)

        # state 事件覆盖主持人与专家
        state_guest_ids = {s.get("guest_id") for s in stream["states"]}
        expected_ids = {g["id"] for g in guests}
        check("state 覆盖全部嘉宾", expected_ids.issubset(state_guest_ids),
              f"{len(state_guest_ids & expected_ids)}/{len(expected_ids)}")
        speaking_seen = any(s.get("state") == "speaking" for s in stream["states"])
        check("存在 speaking 状态", speaking_seen)

        # insight 事件（LLM 抽取结果非强确定性，只在有返回时校验格式）
        if stream["insights"]:
            actions = Counter(i.get("action") for i in stream["insights"])
            check("insight 含 create", actions.get("create", 0) >= 1, str(dict(actions)))
            check("insight 含 finalize", actions.get("finalize", 0) >= 1, str(dict(actions)))
            valid = all(
                i.get("type") in ("consensus", "divergence")
                and i.get("strength") in ("weak", "medium", "strong")
                and isinstance(i.get("version"), int)
                for i in stream["insights"]
            )
            check("insight 字段合法", valid)
        else:
            check("insight 事件（LLM 本次未抽到，允许）", True, "0 条，跳过强校验")

        # 6. DB 校验
        info("6/6 数据库最终状态校验")
        db_data = verify_db(topic_id)
        t = db_data["topic"]
        check("topic.status=archived", t is not None and t.status == "archived",
              t.status if t else "topic 不存在")
        check("topic.summary 已落库", bool(t and t.summary),
              f"{len(t.summary or '')} 字")
        check("topic.ended_at 已写入", bool(t and t.ended_at))

        dbt = db_data["transcripts"]
        check(f"DB transcript 共 {len(speech_types)} 条",
              len(dbt) == len(stream["transcripts_done"]),
              f"DB={len(dbt)} SSE={len(stream['transcripts_done'])}")
        all_done = all(x.status == "done" for x in dbt)
        check("DB transcript 全部 done", all_done)
        turns = [x.turn_index for x in dbt]
        check("turn_index 唯一且连续", turns == list(range(len(turns))), str(turns))

        et = db_data["event_types"]
        check("EventPoint 含 hand_raise", et.get("hand_raise", 0) >= 1, f"×{et.get('hand_raise', 0)}")
        check("EventPoint 含 grab_arbitration", et.get("grab_arbitration", 0) >= 1)
        check("EventPoint 含 grab_result", et.get("grab_result", 0) >= 1)
        check("EventPoint 含 closing_trigger", et.get("closing_trigger", 0) >= 1)
        check("EventPoint 含 consensus_extract_trigger",
              et.get("consensus_extract_trigger", 0) >= 1,
              f"×{et.get('consensus_extract_trigger', 0)}")

        db_ins = db_data["insights"]
        final_ins = [i for i in db_ins if i.is_final]
        if db_ins:
            check("Insight 已持久化", len(db_ins) >= 1, f"{len(db_ins)} 条")
            check("存在 is_final=1", len(final_ins) >= 1, f"{len(final_ins)} 条最终版")
        else:
            check("Insight（LLM 本次未抽到，允许）", True, "0 条")

        # 回放接口
        r = await client.get(f"{BASE_URL}/api/topics/{topic_id}/stream/replay")
        check("replay 接口 200", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            replay = r.json()
            check("replay transcript 数一致",
                  len(replay.get("transcripts", [])) == len(dbt))


async def main() -> int:
    print(f"{C.BOLD}═══ AI Panel Studio 端到端验证 ═══{C.RESET}")
    print(f"  服务: {BASE_URL}  MAX_TURNS={MAX_TURNS}  专家数={EXPERT_COUNT}")
    proc = None
    try:
        proc = start_server()
        await run_flow()
    except Exception as exc:  # noqa: BLE001
        print(f"\n{C.RED}{C.BOLD}验证脚本异常: {exc}{C.RESET}")
        import traceback

        traceback.print_exc()
        if proc is not None and proc.stdout is not None:
            tail = proc.stdout.read()[-2000:]
            if tail:
                print(f"\n{C.YELLOW}── uvicorn 日志尾部 ──{C.RESET}\n{tail}")
        return 2
    finally:
        if proc is not None:
            stop_server(proc)

    total = len(results)
    passed = sum(1 for ok, _, _ in results if ok)
    failed = total - passed
    print(f"\n{C.BOLD}═══ 结果: {passed}/{total} 通过"
          + (f"，{C.RED}{failed} 失败{C.RESET}" if failed else f" 全部通过 {C.GREEN}✓{C.RESET}")
          + " ═══")
    if failed:
        print(f"{C.RED}失败项:{C.RESET}")
        for ok, name, detail in results:
            if not ok:
                print(f"  - {name} — {detail}")
        return 1
    print(f"{C.GREEN}端到端链路验证通过：话题创建 → LLM 阵容 → 抢答循环 → 共识抽取 → 收尾归档{C.RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
