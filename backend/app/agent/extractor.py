"""
Extractor Agent — 共识/分歧增量抽取与 finalize。

PRD §6.2/§6.3 触发时机：
  - T0 (开场完成) 不抽取
  - T1+ (每个专家发言完成) 增量抽取
  - Tf (收尾完成) 最终一致性校验，标记 is_final

PRD §6.5 增量策略：
  - 强化已有共识 → version+1
  - 修正已有分歧 → version+1
  - 新增立场 → 创建 version=1
  - 无影响 → 跳过

PRD §6.6 关键约束（已在 schema.md 落地）：
  - 不重写历史：旧 version 行保留，新 version 单独 INSERT
  - is_final 只在 Tf 标记最新版本
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.agent.base import AgentContext
from app.database import SessionLocal
from app.llm import LLMJsonError, get_llm_client
from app.llm.prompts import extract_prompt
from app.models import Guest, Insight, InsightGuest, InsightSpeech, Transcript


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_existing_insights(topic_id: int) -> list[dict[str, Any]]:
    """加载当前所有 insight（按版本倒序，便于 LLM 比对）。"""
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(Insight)
                .where(Insight.topic_id == topic_id)
                .order_by(Insight.type, Insight.version.desc())
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "type": r.type,
                "summary": r.summary,
                "strength": r.strength,
                "version": r.version,
                "is_final": bool(r.is_final),
            }
            for r in rows
        ]


def _latest_version(topic_id: int, insight_id: int) -> int:
    """查找某条 insight 链路上的最新版本号（按同 summary 匹配近似）。"""
    with SessionLocal() as db:
        base = db.get(Insight, insight_id)
        if base is None:
            return 0
        # 简化：直接返回当前行 version（调用方在 update 时 +1）
        return base.version


def _persist_new_insight(
    topic_id: int,
    *,
    type: str,
    summary: str,
    strength: str,
    version: int,
    guest_ids: list[int],
    transcript_ids: list[int],
    relation: str = "support",
) -> dict[str, Any]:
    """新建一条 Insight + 关联，返回 SSE payload 字段。"""
    now = _now_iso()
    with SessionLocal() as db:
        ins = Insight(
            topic_id=topic_id,
            type=type,
            summary=summary[:64],
            strength=strength,
            version=version,
            is_final=0,
            created_at=now,
            updated_at=now,
        )
        db.add(ins)
        db.flush()  # 拿 id
        for gid in guest_ids:
            db.add(
                InsightGuest(
                    insight_id=ins.id,
                    guest_id=gid,
                )
            )
        for tid in transcript_ids:
            db.add(
                InsightSpeech(
                    insight_id=ins.id,
                    transcript_id=tid,
                    relation=relation,
                )
            )
        db.commit()
        db.refresh(ins)
        return {
            "insight_id": ins.id,
            "type": ins.type,
            "summary": ins.summary,
            "strength": ins.strength,
            "version": ins.version,
            "is_final": bool(ins.is_final),
        }


def _persist_bump_insight(
    existing_insight_id: int,
    *,
    summary: str,
    strength: str,
    guest_ids: list[int],
    transcript_ids: list[int],
    relation: str = "support",
) -> dict[str, Any]:
    """基于已有 insight 创建 version+1 新行（不删旧行，不重写历史）。

    旧行保持不变；新行 is_final=0；finalize 阶段统一标最终版。
    """
    now = _now_iso()
    with SessionLocal() as db:
        base = db.get(Insight, existing_insight_id)
        if base is None:
            # fallback：当作新建（无法判断 topic_id，跳过）
            return {
                "insight_id": 0,
                "type": "consensus",
                "summary": summary[:64],
                "strength": strength,
                "version": 1,
                "is_final": False,
            }
        new_row = Insight(
            topic_id=base.topic_id,
            type=base.type,
            summary=summary[:64],
            strength=strength,
            version=base.version + 1,
            is_final=0,
            created_at=now,
            updated_at=now,
        )
        db.add(new_row)
        db.flush()
        for gid in guest_ids:
            db.add(InsightGuest(insight_id=new_row.id, guest_id=gid))
        for tid in transcript_ids:
            db.add(
                InsightSpeech(
                    insight_id=new_row.id,
                    transcript_id=tid,
                    relation=relation,
                )
            )
        # 把旧行标记为非 final（保险，避免遗留 is_final=1）
        base.is_final = 0
        db.commit()
        db.refresh(new_row)
        return {
            "insight_id": new_row.id,
            "type": new_row.type,
            "summary": new_row.summary,
            "strength": new_row.strength,
            "version": new_row.version,
            "is_final": bool(new_row.is_final),
        }


def _mark_final(topic_id: int) -> list[dict[str, Any]]:
    """Tf 阶段：把每个逻辑 insight 链的最新版本标记为 is_final=1。

    简化策略：取 (topic_id, type, summary 前缀) 分组后的最大 version 行，
    事实上更稳的做法是按 guest_links 集合相似度分组——MVP 用 summary 简化。
    """
    out: list[dict[str, Any]] = []
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(Insight).where(Insight.topic_id == topic_id).order_by(Insight.type)
            )
            .scalars()
            .all()
        )
        # 按 (type, summary) 聚合，每组取最高 version
        groups: dict[tuple[str, str], Insight] = {}
        for r in rows:
            key = (r.type, r.summary)
            if key not in groups or r.version > groups[key].version:
                groups[key] = r
        for latest in groups.values():
            latest.is_final = 1
            latest.updated_at = _now_iso()
            out.append(
                {
                    "insight_id": latest.id,
                    "type": latest.type,
                    "summary": latest.summary,
                    "strength": latest.strength,
                    "version": latest.version,
                    "is_final": True,
                }
            )
        db.commit()
    return out


def _resolve_guest_ids_by_names(topic_id: int, names: list[str]) -> list[int]:
    """LLM 返回的姓名转 guest_id（容错：模糊匹配失败返回空）。"""
    if not names:
        return []
    with SessionLocal() as db:
        guests = (
            db.execute(select(Guest).where(Guest.topic_id == topic_id))
            .scalars()
            .all()
        )
        ids: list[int] = []
        for name in names:
            for g in guests:
                if name and (name in g.name or g.name in name):
                    ids.append(g.id)
                    break
        return list({x for x in ids})  # 去重


def _recent_transcript_ids(topic_id: int, k: int = 8) -> list[int]:
    """取最近 K 条 transcript id（用于关联）。"""
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(Transcript.id)
                .where(Transcript.topic_id == topic_id)
                .order_by(Transcript.turn_index.desc())
                .limit(k)
            )
            .scalars()
            .all()
        )
        return list(rows)


class ExtractorAgent:
    """共识/分歧抽取 Agent。

    用法：
      agent = ExtractorAgent(topic_id)
      events = await agent.extract_incremental(ctx)  # 返回 SSE insight 事件列表
      events = await agent.finalize(ctx)             # 返回 finalize 事件列表
    """

    def __init__(self, topic_id: int) -> None:
        self.topic_id = topic_id

    async def extract_incremental(self, ctx: AgentContext) -> list[dict[str, str]]:
        """增量抽取一轮，返回 SSE insight 事件列表（已落库）。"""
        client = get_llm_client()
        existing = _load_existing_insights(self.topic_id)
        messages = extract_prompt(ctx.topic_title, ctx.as_text(), existing)
        try:
            raw = await client.chat_json(messages, temperature=0.3, max_tokens=512)
        except LLMJsonError:
            return []
        if not isinstance(raw, dict):
            return []
        items = raw.get("insights") or []
        if not isinstance(items, list):
            return []

        recent_tids = _recent_transcript_ids(self.topic_id, k=8)
        sse_events: list[dict[str, str]] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            summary = item.get("summary")
            strength = item.get("strength", "weak")
            if itype not in ("consensus", "divergence") or not summary:
                continue
            if strength not in ("weak", "medium", "strong"):
                strength = "weak"

            related_id = item.get("related_existing_id")
            guest_names = item.get("guest_names") or []
            transcript_ids = item.get("transcript_ids") or []
            # 若 LLM 未给 transcript_ids，关联最近 K 条
            if not transcript_ids:
                transcript_ids = recent_tids
            guest_ids = _resolve_guest_ids_by_names(self.topic_id, guest_names)

            if related_id and isinstance(related_id, int):
                # bump 既有
                payload = _persist_bump_insight(
                    related_id,
                    summary=summary,
                    strength=strength,
                    guest_ids=guest_ids,
                    transcript_ids=transcript_ids,
                    relation="support",
                )
                action = "update"
            else:
                payload = _persist_new_insight(
                    self.topic_id,
                    type=itype,
                    summary=summary,
                    strength=strength,
                    version=1,
                    guest_ids=guest_ids,
                    transcript_ids=transcript_ids,
                    relation="support",
                )
                action = "create"

            from app.stream.events import make_insight_event

            sse_events.append(
                make_insight_event(
                    topic_id=self.topic_id,
                    insight_id=payload["insight_id"],
                    action=action,
                    type=payload["type"],
                    summary=payload["summary"],
                    strength=payload["strength"],
                    version=payload["version"],
                    is_final=payload["is_final"],
                )
            )

        # 记录抽取触发事件
        from app.agent.arbiter import record_event

        record_event(
            self.topic_id,
            "consensus_extract_trigger",
            guest_id=None,
            turn_index=None,
            payload={"extracted": len(sse_events)},
        )
        return sse_events

    async def finalize(self, ctx: AgentContext) -> list[dict[str, str]]:
        """Tf：再做一次抽取 + 把最新版本标记 is_final=1。"""
        # 先做最后一次增量（保证覆盖收尾前所有发言）
        events = await self.extract_incremental(ctx)
        # 标记 final
        finalized = _mark_final(self.topic_id)
        from app.stream.events import make_insight_event

        for item in finalized:
            events.append(
                make_insight_event(
                    topic_id=self.topic_id,
                    insight_id=item["insight_id"],
                    action="finalize",
                    type=item["type"],
                    summary=item["summary"],
                    strength=item["strength"],
                    version=item["version"],
                    is_final=True,
                )
            )
        return events
