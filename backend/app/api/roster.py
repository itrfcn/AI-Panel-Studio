"""
Roster 路由 — 阵容生成与确认。

对齐 PRD §4.2 准备页与 schema.md §3.2。
阵容生成调用 LLM 输出 JSON，落库 Guest（候选态，待用户 /confirm）。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.llm import LLMJsonError, get_llm_client
from app.llm.prompts import roster_prompt
from app.models import Guest, Topic
from app.schemas.guest import GuestCreate, GuestOut, RosterGenerateRequest, RosterOut

router = APIRouter(prefix="/topics/{topic_id}/roster", tags=["roster"])


def _get_topic_or_404(db: Session, topic_id: int) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Topic {topic_id} not found"
        )
    return topic


# 允许的颜色范围（前端可识别的 hex）；后端只做格式校验，不限制色板
_HEX_PATTERN = "^[#][0-9A-Fa-f]{6}$"


def _validate_roster_payload(payload: dict) -> list[dict]:
    """校验 LLM 返回的 roster 字段。"""
    if not isinstance(payload, dict) or "roster" not in payload:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM JSON missing 'roster' key. raw={str(payload)[:200]}",
        )
    roster = payload["roster"]
    if not isinstance(roster, list) or not roster:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM 'roster' must be a non-empty array",
        )

    moderators = [r for r in roster if r.get("role") == "moderator"]
    experts = [r for r in roster if r.get("role") == "expert"]
    if len(moderators) != 1:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Roster must contain exactly 1 moderator, got {len(moderators)}",
        )

    import re

    compiled = re.compile(_HEX_PATTERN)
    out: list[dict] = []
    for idx, item in enumerate(roster):
        for field in ("role", "name", "title", "color"):
            if not item.get(field):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Roster[{idx}] missing required field: {field}",
                )
        if item["role"] not in ("moderator", "expert"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Roster[{idx}] invalid role: {item['role']}",
            )
        if not compiled.match(item["color"]):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Roster[{idx}] invalid color hex: {item['color']}",
            )
        out.append(item)
    return out


@router.post("/generate", response_model=RosterOut)
async def generate_roster(
    topic_id: int,
    payload: RosterGenerateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RosterOut:
    """生成候选阵容（主持人 + N 专家）。

    PRD §4.2 + schema.md §3.2：
      1. 校验 settings.is_llm_configured()
      2. 调用 LLM 输出 JSON 阵容（temperature=0.8 鼓励多样性）
      3. 校验字段后落库（先清除该 topic 旧候选，再批量插入）
      4. 返回 RosterOut（is_confirmed=False）
    """
    if not settings.is_llm_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM API Key not configured. Set LLM_API_KEY in .env.",
        )

    topic = _get_topic_or_404(db, topic_id)
    # 仅允许在 draft/setup 状态重新生成阵容（ongoing 之后不能改）
    if topic.status not in ("draft", "setup"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot regenerate roster when topic status='{topic.status}'",
        )

    expert_count = payload.expert_count or topic.expert_count
    if not (settings.MIN_EXPERT_COUNT <= expert_count <= settings.MAX_EXPERT_COUNT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"expert_count must be in [{settings.MIN_EXPERT_COUNT},{settings.MAX_EXPERT_COUNT}]",
        )

    try:
        client = get_llm_client()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    try:
        raw = await client.chat_json(
            roster_prompt(topic.title, expert_count),
            temperature=0.8,
            max_tokens=1024,
        )
    except LLMJsonError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM returned invalid JSON: {exc}. raw={exc.raw[:200]}",
        ) from exc
    except Exception as exc:  # noqa: BLE001 — httpx 网络错误等
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM call failed: {exc}",
        ) from exc

    items = _validate_roster_payload(raw)
    if len([i for i in items if i["role"] == "expert"]) != expert_count:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM returned wrong expert count: expected {expert_count}, got {len(items) - 1}",
        )

    # 落库：先删旧候选，再批量插入（moderator sort_order=0，experts 1..N）
    db.execute(Guest.__table__.delete().where(Guest.topic_id == topic_id))
    now = datetime.now(timezone.utc).isoformat()
    created: list[Guest] = []
    expert_idx = 0
    for item in items:
        if item["role"] == "moderator":
            sort_order = 0
        else:
            expert_idx += 1
            sort_order = expert_idx
        guest = Guest(
            topic_id=topic_id,
            role=item["role"],
            name=item["name"],
            title=item["title"],
            stance=item.get("stance"),
            color=item["color"],
            profile=item.get("profile"),
            sort_order=sort_order,
            created_at=now,
        )
        db.add(guest)
        created.append(guest)
    db.commit()
    for g in created:
        db.refresh(g)

    # 更新 topic.expert_count（用户可能改）+ 状态保持 draft
    topic.expert_count = expert_count
    topic.updated_at = now
    db.commit()
    db.refresh(topic)

    return RosterOut(
        topic_id=topic_id,
        guests=[GuestOut.model_validate(g) for g in created],
        is_confirmed=False,
    )


@router.get("", response_model=RosterOut)
def get_roster(topic_id: int, db: Session = Depends(get_db)) -> RosterOut:
    """获取当前已生成的阵容（候选或已确认）。"""
    _get_topic_or_404(db, topic_id)
    guests = (
        db.execute(
            select(Guest).where(Guest.topic_id == topic_id).order_by(Guest.sort_order)
        )
        .scalars()
        .all()
    )
    topic = db.get(Topic, topic_id)
    return RosterOut(
        topic_id=topic_id,
        guests=[GuestOut.model_validate(g) for g in guests],
        is_confirmed=(topic.status not in ("draft", "setup")) and bool(guests),
    )


@router.post("/confirm", response_model=RosterOut)
def confirm_roster(
    topic_id: int,
    db: Session = Depends(get_db),
) -> RosterOut:
    """用户确认阵容 → 进入可启动演播厅的 setup 状态。

    PRD §3：用户确认阵容后进入演播厅。
    本端点：
      - 校验已存在 1 moderator + N expert
      - 将 topic.status 切到 setup（待 /start 端点切 ongoing）
    """
    from datetime import datetime, timezone

    topic = _get_topic_or_404(db, topic_id)
    guests = (
        db.execute(
            select(Guest).where(Guest.topic_id == topic_id).order_by(Guest.sort_order)
        )
        .scalars()
        .all()
    )
    moderators = [g for g in guests if g.role == "moderator"]
    experts = [g for g in guests if g.role == "expert"]

    if len(moderators) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exactly 1 moderator required, got {len(moderators)}",
        )
    if len(experts) != topic.expert_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected {topic.expert_count} experts, got {len(experts)}",
        )

    topic.status = "setup"
    topic.updated_at = datetime.now(timezone.utc).isoformat()
    db.commit()
    db.refresh(topic)

    return RosterOut(
        topic_id=topic_id,
        guests=[GuestOut.model_validate(g) for g in guests],
        is_confirmed=True,
    )
