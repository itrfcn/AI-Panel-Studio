"""
init_db.py — 建表 + 插入样例数据。

对齐 schema.md §7 与 PRD §3.1 交付物要求（≥5 条高质量样例数据）。

运行方式（在 backend 目录下）：
    python scripts/init_db.py

特性：
  1. DROP + CREATE 所有表（清空旧数据，便于复跑）
  2. 插入 5 个不同风格的讨论话题
  3. 每个话题配 1 主持人 + 4 专家（共 25 嘉宾）
  4. archived 话题额外插入 transcript 与 insight 样例
     （覆盖 PRD §6 数据结构：consensus + divergence + 关联 + 推理链）

设计约定：
  - 时间戳统一用 ISO8601 字符串
  - 颜色用 hex #RRGGBB
  - profile 用 JSON 字符串
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- 让脚本能从 backend/ 目录直接运行 ---
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy.orm import Session  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    EventPoint,
    Guest,
    Insight,
    InsightGuest,
    InsightSpeech,
    ReasoningChain,
    Topic,
    Transcript,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# 样例数据：5 个不同风格的讨论话题 + 4 人专家阵容
# ============================================================

SAMPLE_DATA: list[dict] = [
    # ---------- 话题 1：科技/AI — ongoing ----------
    {
        "title": "AGI 是否会在 10 年内取代大部分知识工作者？",
        "expert_count": 4,
        "status": "ongoing",
        "moderator": {
            "name": "林清远",
            "title": "资深科技评论员",
            "stance": "中立主持人，负责追问与串联",
            "color": "#2A6F97",
            "profile": {"background": "20 年科技媒体从业", "style": "客观追问", "catchphrase": "让我们听听反方意见"},
        },
        "experts": [
            {
                "name": "陈思齐",
                "title": "AI 实验室首席研究员",
                "stance": "乐观派：AGI 将释放人类创造力",
                "color": "#E63946",
                "profile": {"background": "斯坦福博士，Transformer 方向", "style": "数据驱动", "catchphrase": "技术曲线不会撒谎"},
            },
            {
                "name": "王敏行",
                "title": "劳动经济学教授",
                "stance": "谨慎派：技术性失业被低估",
                "color": "#F4A261",
                "profile": {"background": "北大经院，研究过 4 次工业革命", "style": "历史对照", "catchphrase": "上次也这么说过"},
            },
            {
                "name": "Daniel Carter",
                "title": "硅谷连续创业者",
                "stance": "激进派：拥抱颠覆才有未来",
                "color": "#264653",
                "profile": {"background": "3 家独角兽创始人", "style": "实战派", "catchphrase": "市场比论文更诚实"},
            },
            {
                "name": "周雅琴",
                "title": "认知科学教授",
                "stance": "悲观派：AI 缺乏真正的理解力",
                "color": "#6A4C93",
                "profile": {"background": "MIT Brain Sciences", "style": "反 reductionism", "catchphrase": "智能不是预测下一个 token"},
            },
        ],
    },
    # ---------- 话题 2：组织/管理 — archived ----------
    {
        "title": "远程办公 vs 回归办公室：后疫情时代的工作范式之争",
        "expert_count": 4,
        "status": "archived",
        "summary": (
            "本场讨论未能形成单一答案。远程派以 productivity 数据与人才池扩张为据，"
            "回归派强调文化沉淀与创新偶然性。最终共识：混合模式为当前最优解，"
            "但需以「会议密度」与「异步文档质量」为 KPI 进行校验。分歧在于"
            "管理者是否能在缺乏物理在场时维持信任传递。"
        ),
        "moderator": {
            "name": "苏明",
            "title": "组织行为学顾问",
            "stance": "中立主持人，串联议题",
            "color": "#457B9D",
            "profile": {"background": "麦肯锡 8 年", "style": "案例追问", "catchphrase": "数据背后是什么"},
        },
        "experts": [
            {
                "name": "张力行",
                "title": "HR SaaS 创始人",
                "stance": "远程派：async-first 是未来",
                "color": "#E76F51",
                "profile": {"background": "远程公司 5 年", "style": "工具论", "catchphrase": "通勤是 20 世纪的遗产"},
            },
            {
                "name": "Lisa Chen",
                "title": "金融科技公司 COO",
                "stance": "混合派：3+2 是平衡点",
                "color": "#2A9D8F",
                "profile": {"background": "200 人团队管理者", "style": "运营视角", "catchphrase": "我们不赌极端"},
            },
            {
                "name": "黄志远",
                "title": "传统制造业 CEO",
                "stance": "回归派：现场感不可替代",
                "color": "#E9C46A",
                "profile": {"background": "3000 人工厂", "style": "工业派", "catchphrase": "我知道现场的力量"},
            },
            {
                "name": "Marcus Wright",
                "title": "远程协作工具 PM",
                "stance": "远程派：工具已足够",
                "color": "#6D597A",
                "profile": {"background": "10 年 SaaS PM", "style": "产品视角", "catchphrase": "工具决定组织"},
            },
        ],
        # 样例发言（用于回放与共识/分歧关联）
        "transcripts": [
            {"turn_index": 1, "guest_name": "苏明", "speech_type": "opening", "content": "欢迎来到这场关于工作范式的圆桌。我们要回答一个问题：后疫情时代，远程、混合还是回归，哪种才是真正的答案？"},
            {"turn_index": 2, "guest_name": "张力行", "speech_type": "grab", "content": "我先抛观点：async-first 是未来。我们的员工 productivity 在远程后提升了 23%，人才池也扩张到全国。"},
            {"turn_index": 3, "guest_name": "黄志远", "speech_type": "rebute", "content": "你的 23% 来自哪？我猜是知识工作者。但文化沉淀、新人融入、创新偶然性，这些不能用季度 KPI 衡量。"},
            {"turn_index": 4, "guest_name": "Lisa Chen", "speech_type": "supplement", "content": "我同意双方各对一半。我们实践 3+2 混合：周二周四周现场，其余远程。关键不是地点，而是会议密度与异步文档质量。"},
            {"turn_index": 5, "guest_name": "Marcus Wright", "speech_type": "grab", "content": "工具已经足够支撑 async。问题不在工具，而在管理者的信任传递能力——这是黄总真正担心的。"},
            {"turn_index": 6, "guest_name": "苏明", "speech_type": "summary", "content": "我们形成了共识：混合模式是当前最优解。但分歧仍在——管理者能否在缺乏物理在场时维持信任。这是下一场讨论的议题。"},
        ],
        "insights": [
            {
                "type": "consensus",
                "summary": "混合办公是当前最优解，3+2 是常见配置",
                "strength": "strong",
                "guest_names": ["张力行", "Lisa Chen", "Marcus Wright"],
                "transcript_turns": [2, 4, 5],
            },
            {
                "type": "divergence",
                "summary": "管理者在场与信任传递是否可解耦",
                "strength": "medium",
                "guest_names": ["黄志远", "Marcus Wright"],
                "transcript_turns": [3, 5],
            },
        ],
    },
    # ---------- 话题 3：产业/商业 — setup（候选阵容待确认）----------
    {
        "title": "电动车的\"全面替代燃油车\"是否被高估？",
        "expert_count": 4,
        "status": "setup",
        "moderator": {
            "name": "高瑞",
            "title": "汽车产业分析师",
            "stance": "中立主持人",
            "color": "#355C7D",
            "profile": {"background": "10 年汽车产业研究", "style": "数据追问", "catchphrase": "看渗透率曲线"},
        },
        "experts": [
            {
                "name": "林晓峰",
                "title": "新势力车企产品总监",
                "stance": "电动派：渗透率只会加速",
                "color": "#F94144",
                "profile": {"background": "新势力 5 年", "style": "市场派", "catchphrase": "趋势不可逆"},
            },
            {
                "name": "Karl Berg",
                "title": "电池材料科学家",
                "stance": "理性派：技术瓶颈被忽视",
                "color": "#F8961E",
                "profile": {"background": "固态电池研究 15 年", "style": "技术现实派", "catchphrase": "实验室≠量产"},
            },
            {
                "name": "田岛由纪",
                "title": "能源政策研究员",
                "stance": "政策派：电网与基建是关键",
                "color": "#43AA8B",
                "profile": {"background": "IEA 顾问", "style": "系统视角", "catchphrase": "车不是孤岛"},
            },
            {
                "name": "何塞·加西亚",
                "title": "传统车企动力总成工程师",
                "stance": "保守派：内燃机还有 20 年",
                "color": "#577590",
                "profile": {"background": "内燃机 25 年", "style": "工程派", "catchphrase": "热效率还能涨"},
            },
        ],
    },
    # ---------- 话题 4：教育 — ongoing ----------
    {
        "title": "大学教育在 AI 时代是否还值得？",
        "expert_count": 4,
        "status": "ongoing",
        "moderator": {
            "name": "宋怀瑾",
            "title": "教育社会学教授",
            "stance": "中立主持人",
            "color": "#1D3557",
            "profile": {"background": "教育社会学 20 年", "style": "结构追问", "catchphrase": "教育为谁服务"},
        },
        "experts": [
            {
                "name": "顾长青",
                "title": "计算机系主任",
                "stance": "改革派：大学必须重构",
                "color": "#E63946",
                "profile": {"background": "CS 院长", "style": "改革派", "catchphrase": "课程体系已过时"},
            },
            {
                "name": "苏菲·拉弗勒",
                "title": "终身学习平台创始人",
                "stance": "替代派：学位不再是入场券",
                "color": "#F4A261",
                "profile": {"background": "EdTech 创业 8 年", "style": "市场派", "catchphrase": "技能 > 学位"},
            },
            {
                "name": "罗伯特·海恩",
                "title": "文学院教授",
                "stance": "传统派：博雅教育不可替代",
                "color": "#6A4C93",
                "profile": {"background": "文学 30 年", "style": "人文派", "catchphrase": "教育不是培训"},
            },
            {
                "name": "林芷若",
                "title": "职业教育研究学者",
                "stance": "融合派：大学应嵌入实践",
                "color": "#2A9D8F",
                "profile": {"background": "职教研究 12 年", "style": "实践派", "catchphrase": "学用要合一"},
            },
        ],
    },
    # ---------- 话题 5：科技/投资 — archived ----------
    {
        "title": "元宇宙是否只是一场资本泡沫？",
        "expert_count": 4,
        "status": "archived",
        "summary": (
            "讨论揭示了「元宇宙」概念的多义性。共识：XR 硬件与图形渲染是有价值的技术底座。"
            "分歧：消费级 use case 是否存在，以及当前估值是否透支了 10 年预期。"
            "最终判断：资本炒作阶段已过，但技术基建仍在生长——这是一场"
            "「泡沫化的真实趋势」。"
        ),
        "moderator": {
            "name": "伊藤健",
            "title": "科技投资评论员",
            "stance": "中立主持人",
            "color": "#4A4E69",
            "profile": {"background": "VC 评论 12 年", "style": "估值追问", "catchphrase": "看现金流"},
        },
        "experts": [
            {
                "name": "张若虚",
                "title": "XR 设备创业公司 CEO",
                "stance": "长期派：硬件成熟临界点",
                "color": "#9A8C98",
                "profile": {"background": "XR 8 年", "style": "产品派", "catchphrase": "重量低于 100g 是拐点"},
            },
            {
                "name": "安娜·诺维科娃",
                "title": "风险投资合伙人",
                "stance": "泡沫派：估值已透支",
                "color": "#C9ADA7",
                "profile": {"background": "消费 VC 10 年", "style": "财务派", "catchphrase": "现金流向哪"},
            },
            {
                "name": "程慕白",
                "title": "图形渲染技术专家",
                "stance": "技术派：底层突破值得期待",
                "color": "#22223B",
                "profile": {"background": "图形学博士，NVIDIA 6 年", "style": "技术派", "catchphrase": "算力曲线不会停"},
            },
            {
                "name": "大卫·克拉克",
                "title": "消费电子资深记者",
                "stance": "怀疑派：缺杀手级应用",
                "color": "#F2E9E4",
                "profile": {"background": "CES 报道 15 年", "style": "消费者视角", "catchphrase": "用户买什么"},
            },
        ],
        "transcripts": [
            {"turn_index": 1, "guest_name": "伊藤健", "speech_type": "opening", "content": "元宇宙这个词在过去 3 年从天堂到地狱。今天我们要拆解：哪些是真趋势，哪些是泡沫。"},
            {"turn_index": 2, "guest_name": "张若虚", "speech_type": "grab", "content": "硬件正在逼近拐点。当头显低于 100g、续航 8 小时，消费市场会启动。"},
            {"turn_index": 3, "guest_name": "安娜·诺维科娃", "speech_type": "rebute", "content": "硬件拐点不等于商业拐点。问题是没有 killer app——估值却已经透支了 10 年。"},
            {"turn_index": 4, "guest_name": "程慕白", "speech_type": "supplement", "content": "我同意安娜的财务判断，但从技术底层看，实时渲染与神经渲染的突破是真实的，不应被资本炒作掩盖。"},
            {"turn_index": 5, "guest_name": "大卫·克拉克", "speech_type": "grab", "content": "我跑 CES 15 年，看到的永远是 demo。用户最终买的是「解决问题」，不是「沉浸感」本身。"},
            {"turn_index": 6, "guest_name": "伊藤健", "speech_type": "summary", "content": "我们的结论：泡沫阶段已过，但技术基建仍在生长。这是一场「泡沫化的真实趋势」。"},
        ],
        "insights": [
            {
                "type": "consensus",
                "summary": "XR 与图形渲染是有价值的技术底座",
                "strength": "medium",
                "guest_names": ["张若虚", "程慕白"],
                "transcript_turns": [2, 4],
            },
            {
                "type": "divergence",
                "summary": "消费级 killer app 是否存在",
                "strength": "strong",
                "guest_names": ["安娜·诺维科娃", "大卫·克拉克", "张若虚"],
                "transcript_turns": [2, 3, 5],
            },
        ],
    },
]


# ============================================================
# 建表与插入逻辑
# ============================================================


def create_all_tables() -> None:
    """DROP + CREATE 所有表。"""
    # 注意：DROP 在 dev/seed 场景下清空旧数据，生产慎用
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("[init_db] tables recreated")


def _insert_guest(db: Session, topic_id: int, role: str, data: dict, sort_order: int) -> Guest:
    return Guest(
        topic_id=topic_id,
        role=role,
        name=data["name"],
        title=data["title"],
        stance=data.get("stance"),
        color=data["color"],
        profile=json.dumps(data.get("profile"), ensure_ascii=False) if data.get("profile") else None,
        sort_order=sort_order,
        created_at=now_iso(),
    )


def _insert_topic(db: Session, item: dict) -> Topic:
    created = now_iso()
    started = created if item["status"] in ("ongoing", "summarizing", "archived") else None
    ended = created if item["status"] == "archived" else None
    return Topic(
        title=item["title"],
        expert_count=item["expert_count"],
        status=item["status"],
        created_at=created,
        updated_at=created,
        started_at=started,
        ended_at=ended,
        summary=item.get("summary"),
    )


def seed_all(db: Session) -> None:
    for idx, item in enumerate(SAMPLE_DATA, start=1):
        topic = _insert_topic(db, item)
        db.add(topic)
        db.flush()  # 拿到 topic.id

        # 主持人（sort_order=0）
        db.add(_insert_guest(db, topic.id, "moderator", item["moderator"], sort_order=0))
        # 专家（sort_order=1..N）
        for i, exp in enumerate(item["experts"], start=1):
            db.add(_insert_guest(db, topic.id, "expert", exp, sort_order=i))

        db.flush()
        print(f"[init_db] topic#{idx} '{topic.title}' -> {topic.status}, guests seeded")

        # archived 话题：插入 transcript + insight 样例
        if item["status"] == "archived" and "transcripts" in item:
            _seed_transcripts_and_insights(db, topic, item)

    db.commit()


def _seed_transcripts_and_insights(db: Session, topic: Topic, item: dict) -> None:
    """为 archived 话题插入发言、共识/分歧及关联，覆盖 PRD §6 数据结构。"""
    # name -> guest 映射
    name_to_guest: dict[str, Guest] = {
        g.name: g for g in db.query(Guest).filter(Guest.topic_id == topic.id).all()
    }
    turn_to_transcript: dict[int, Transcript] = {}

    # 发言
    for t in item["transcripts"]:
        guest = name_to_guest.get(t["guest_name"])
        if guest is None:
            print(f"  [warn] guest '{t['guest_name']}' not found, skip transcript turn {t['turn_index']}")
            continue
        tr = Transcript(
            topic_id=topic.id,
            guest_id=guest.id,
            turn_index=t["turn_index"],
            content=t["content"],
            speech_type=t["speech_type"],
            status="done",
            started_at=topic.started_at,
            completed_at=topic.ended_at,
        )
        db.add(tr)
        db.flush()
        turn_to_transcript[t["turn_index"]] = tr

    # 共识/分歧 + 关联 + 推理链
    for ins_data in item["insights"]:
        insight = Insight(
            topic_id=topic.id,
            type=ins_data["type"],
            summary=ins_data["summary"],
            strength=ins_data["strength"],
            version=1,
            is_final=1,
            created_at=topic.ended_at or now_iso(),
            updated_at=topic.ended_at or now_iso(),
        )
        db.add(insight)
        db.flush()

        # 关联发言人
        for name in ins_data.get("guest_names", []):
            g = name_to_guest.get(name)
            if g:
                db.add(InsightGuest(insight_id=insight.id, guest_id=g.id))

        # 关联发言片段
        for turn in ins_data.get("transcript_turns", []):
            tr = turn_to_transcript.get(turn)
            if tr:
                relation = "refute" if ins_data["type"] == "divergence" else "support"
                db.add(InsightSpeech(insight_id=insight.id, transcript_id=tr.id, relation=relation))

        # 推理链：每条 insight 至少有一条 reasoning，引用一个抽取触发事件点
        ep = EventPoint(
            topic_id=topic.id,
            guest_id=None,
            event_type="consensus_extract_trigger",
            turn_index=max(ins_data.get("transcript_turns", [1])),
            payload=json.dumps({"insight_type": ins_data["type"]}, ensure_ascii=False),
            created_at=topic.ended_at or now_iso(),
        )
        db.add(ep)
        db.flush()
        db.add(
            ReasoningChain(
                insight_id=insight.id,
                event_point_id=ep.id,
                step_index=1,
                note=f"由 turn {ins_data.get('transcript_turns', [])} 的发言抽取",
                created_at=topic.ended_at or now_iso(),
            )
        )
        print(f"  [seed] insight#{insight.id} {insight.type} '{insight.summary}' with links + reasoning")


def main() -> None:
    print(f"[init_db] using DATABASE_URL={os.getenv('DATABASE_URL', 'sqlite:///./ai_panel_studio.db')}")
    create_all_tables()

    db = SessionLocal()
    try:
        seed_all(db)
        # 简单统计
        topic_count = db.query(Topic).count()
        guest_count = db.query(Guest).count()
        transcript_count = db.query(Transcript).count()
        insight_count = db.query(Insight).count()
        print(
            f"[init_db] done: topics={topic_count}, guests={guest_count}, "
            f"transcripts={transcript_count}, insights={insight_count}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
