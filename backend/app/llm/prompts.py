"""
Prompt 模板 — 中文 system prompt + JSON schema 约束。

对齐 PRD §3.3 多 Agent 调度与 §6 共识/分歧时机。

设计原则：
- 每个 Prompt 函数返回 list[dict] messages，可直接喂给 LLMClient
- system prompt 全中文，明确角色 + 输出格式约束
- roster/extract 用 json_object 模式（chat_json）
- opening/summary/expert_speak 用流式文本（chat_stream/chat）

阶段 4-5（抢答+抽取）的 Prompt 函数预留位置：
  - expert_speak_prompt 已在 MVP 中实现（用于阶段 4 专家发言）
  - extract_prompt 已在 MVP 中实现（用于阶段 5 抽取）
骨架预留、当前阶段不一定调用。
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# 阶段 2：阵容生成
# ---------------------------------------------------------------------------


def roster_prompt(topic_title: str, expert_count: int) -> list[dict[str, str]]:
    """生成主持人与 N 专家阵容。返回 JSON 数组（外层包 {roster:[...]}）。"""
    system = (
        "你是一名资深圆桌讨论策划人。根据用户给出的话题，"
        f"组建一个由 1 位主持人 + {expert_count} 位专家组成的讨论阵容。\n\n"
        "专家席位要求（核心：每位专家必须是独立思考的个体，立场鲜明对立）：\n"
        f"- {expert_count} 位专家必须覆盖话题的不同乃至对立立场（支持/反对/中立/技术派/伦理派等），\n"
        "  确保讨论中会产生真实的观点碰撞与反驳\n"
        "- 每位专家有独特的专业背景（title），且该背景直接决定其 stance\n"
        "- stance 必须具体、有倾向性（≤30 字），避免模糊的「视情况而定」类表述\n"
        "- 每位专家的 profile 应描述其思维倾向与论证风格（如「数据驱动」「人文关怀」「技术乐观」）\n"
        "- 颜色需区分明显，使用 #RRGGBB 格式\n\n"
        "严格输出 JSON 对象，格式如下（不要 markdown、不要解释）：\n"
        "{\n"
        '  "roster": [\n'
        '    {"role":"moderator","name":"主持人姓名","title":"主持人职业","stance":null,"color":"#RRGGBB","profile":"资深主持人，擅长..."},\n'
        '    {"role":"expert","name":"专家姓名","title":"专家职业","stance":"该专家明确立场摘要","color":"#RRGGBB","profile":"背景与观点倾向..."}\n'
        "  ]\n"
        "}\n"
        "roster 数组长度必须 = 1 + expert_count，第 0 位固定为 moderator。"
    )
    user = f"话题：{topic_title}\n专家人数：{expert_count}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 阶段 3：主持人开场 / 收尾
# ---------------------------------------------------------------------------


def opening_prompt(topic_title: str, moderator_name: str, expert_count: int) -> list[dict[str, str]]:
    """主持人开场白。流式输出，自然语言文本。"""
    system = (
        f"你是圆桌讨论的主持人 {moderator_name}。请用中文输出一段开场白（约 150-250 字）。"
        f"讨论话题：{topic_title}。\n\n"
        "开场白要求：\n"
        "- 介绍话题背景与讨论价值\n"
        "- 简要介绍现场有 {n} 位专家将参与讨论\n"
        "- 抛出 1-2 个引导性问题，激发后续讨论\n"
        "- 语气自然、专业，不带 markdown 或 emoji\n"
    ).format(n=expert_count)
    user = f"请为话题「{topic_title}」开场。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def summary_prompt(topic_title: str, transcript_text: str) -> list[dict[str, str]]:
    """主持人收尾总结。基于已有发言给出结论。"""
    system = (
        "你是圆桌讨论的主持人，负责收尾。基于已有发言，用中文输出一段总结（约 200-350 字）。"
        "总结要求：\n"
        "- 概括各方核心观点与分歧\n"
        "- 给出本场讨论的阶段性结论（不强行统一立场）\n"
        "- 不带 markdown 或 emoji，自然语气\n\n"
        f"讨论话题：{topic_title}"
    )
    user = f"已有发言摘要：\n{transcript_text}\n\n请输出收尾总结。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 阶段 4：专家抢答决策
# ---------------------------------------------------------------------------


def raise_hand_prompt(
    expert_name: str,
    expert_stance: str,
    expert_title: str,
    topic_title: str,
    context_text: str,
    turn_number: int,
    max_turns: int,
) -> list[dict[str, str]]:
    """专家决策是否举手 + 举手优先级（PRD §5.2/§5.3）。

    返回 JSON：{will_raise: bool, priority: "grab"|"supplement"|"rebute",
              thought: "≤30 字思考摘要"}
    priority 含义（仲裁发言顺序，数值越大越先发言）：
      - grab     抢答新角度（最先发言，提出新观点）
      - supplement 补充信息或例子（中间发言，补充前面）
      - rebute   反驳他人观点（最后发言，反驳前面）
    """
    system = (
        f"你是圆桌讨论专家 {expert_name}（{expert_title}），你的独立立场：{expert_stance}。"
        f"讨论话题：{topic_title}。\n"
        f"当前第 {turn_number}/{max_turns} 轮。\n\n"
        "你是一个独立思考的个体，有自己的判断和坚持。根据已有发言，决策本轮是否举手发言：\n\n"
        "【主持人引导】如果上下文中有【主持人追问】的内容，你必须优先回应主持人的问题。"
        "如果主持人点了你的名，你必须举手回答（will_raise=true），且 priority=grab 以优先发言。\n"
        "【观点交锋】若有人观点与你立场冲突，即使对方是多数派，你也应坚持己见举手反驳 → priority=rebute\n"
        "【补充】若你有独特的例子/数据/视角尚未被提及 → priority=supplement\n"
        "【新角度】若你想从全新角度切入讨论 → priority=grab\n"
        "只有当你完全无话可说且与所有发言都一致时，才 will_raise=false\n"
        "记住：独立思考意味着不人云亦云，敢于表达不同意见。\n"
        "严格输出 JSON（不带 markdown）：\n"
        '{"will_raise": true|false, "priority": "grab|supplement|rebute", "thought": "≤30字思考"}\n'
        "will_raise=false 时 priority 可填 grab。"
    )
    user = f"已有发言：\n{context_text}\n\n请输出决策 JSON。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 阶段 4：专家发言
# ---------------------------------------------------------------------------


def expert_speak_prompt(
    expert_name: str,
    expert_stance: str,
    expert_title: str,
    topic_title: str,
    context_text: str,
    priority: str = "grab",
) -> list[dict[str, str]]:
    """专家单轮发言。阶段 4 用。

    context_text 是 build_context 拼出的最近 K 条发言。
    priority 决定发言基调：rebute=反驳 / supplement=补充 / grab=抢答新角度。
    """
    priority_hint = {
        "rebute": "本轮请着重反驳他人观点，给出具体反例或逻辑漏洞",
        "supplement": "本轮请补充例子、数据或被遗漏的视角",
        "grab": "本轮请引入新的角度或论点，开拓讨论面",
    }.get(priority, "自然发言")
    system = (
        f"你是圆桌讨论的专家 {expert_name}（{expert_title}），你的独立立场：{expert_stance}。"
        f"讨论话题：{topic_title}。\n"
        f"{priority_hint}。\n"
        "请基于上下文发表 1-2 句话（不超过 80 字），要求：\n"
        "- 若上下文中有【主持人追问】且点了你的名，必须第一句就直接回答主持人的问题，然后再反驳或补充\n"
        "- 坚守你的独立立场，不被他人观点带偏\n"
        "- 若有人观点与你冲突，直接点名反驳，给出你的论据\n"
        "- 提供具体论点或例子，不空话\n"
        "- 不带 markdown、emoji，自然口语化\n"
        "- 每次发言控制在 1-2 句话，简短有力\n"
        "- 你是独立的思考者，不是附和者\n"
    )
    user = f"已有发言：\n{context_text}\n\n请发言。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def followup_prompt(topic_title: str, context_text: str) -> list[dict[str, str]]:
    """主持人串联/追问。每轮专家发言后调用，强力引导下一轮讨论方向。"""
    system = (
        "你是圆桌讨论的主持人，你的职责是控制讨论节奏、引导深入、激发交锋。"
        f"讨论话题：{topic_title}。\n\n"
        "根据本轮专家发言，输出一段引导性追问（2-3 句话，不超过 100 字）。要求：\n"
        "1. 必须点名 1-2 位专家，向他们提出具体问题（如「陈启川，你能否举例说明…？」）\n"
        "2. 明确指出本轮讨论的焦点或分歧，引导下一轮围绕此展开\n"
        "3. 你的追问必须让专家有话可说，激发他们反驳或补充\n"
        "4. 不要泛泛而谈，要具体、有针对性\n"
        "不带 markdown/emoji，自然口语化。"
    )
    user = f"已有发言：\n{context_text}\n\n请输出引导性追问。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def should_continue_prompt(
    topic_title: str,
    context_text: str,
    turn_number: int,
    max_turns: int,
    stale_round: bool,
) -> list[dict[str, str]]:
    """主持人判断讨论是否应继续。每轮追问后调用。stale_round=上一轮没有产生任何新洞见。"""
    system = (
        f"你是圆桌讨论的主持人。讨论话题：{topic_title}。\n"
        f"当前已进行第 {turn_number}/{max_turns} 轮。\n"
        + (
            "【重要信号】上一轮的所有发言都没有产生任何新论据或新角度——"
            "专家在重复之前的观点，讨论已原地打转。\n\n"
            if stale_round
            else "\n"
        )
        + "判断标准（按专家立场强对立的圆桌设计，不要期待达成共识）：\n"
        "应收尾的条件：\n"
        "- 最近一轮发言与之前的观点高度重复，只是换措辞重说\n"
        "- 各方立场和论据已经完整表达，没有新角度可挖\n"
        f"- 已接近最大轮次（{max_turns} 轮）\n"
        "应继续的条件：\n"
        "- 最近一轮出现了新论据、新例证或新角度，值得深挖\n"
        "- 某位专家的论点尚未被其他专家正面回应\n"
        "- 有一方明显回避了关键质疑，需要追问\n"
        "严格输出 JSON（不带 markdown）：\n"
        '{"continue": true|false, "reason": "≤30字说明"}\n'
        + (
            "上一轮已无新内容，除非你发现仍有重大未被回应的分歧，否则应收尾（continue=false）。"
            if stale_round
            else "若上一轮有实质新内容，倾向继续。"
        )
    )
    user = f"已有发言：\n{context_text}\n\n请判断是否继续。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 阶段 5（预留）：共识/分歧抽取
# ---------------------------------------------------------------------------


def extract_prompt(
    topic_title: str, transcript_text: str, existing_insights: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """抽取共识/分歧。阶段 5 用。"""
    system = (
        "你是圆桌讨论的洞察分析 Agent。基于发言抽取共识与分歧。"
        f"讨论话题：{topic_title}。\n"
        "- 共识：多人达成一致的观点；分歧：明显对立的观点\n"
        "- 每条 summary ≤30 字\n"
        "- strength：weak/medium/strong\n"
        "- 若是对已有 insight 的强化或修正，提供 related_existing_id（来自下方列表的 id）\n"
        "严格输出 JSON：\n"
        '{"insights":[{"type":"consensus|divergence","summary":"...","strength":"weak|medium|strong","related_existing_id":null,"guest_names":["发言人姓名"],"transcript_ids":[]}]}\n'
        "若无可抽取，返回 {\"insights\":[]}。transcript_ids 留空数组即可（后端会补全）。"
    )
    user = (
        f"已有发言：\n{transcript_text}\n\n"
        f"已有 insight（id 用于 related_existing_id，避免重复）：\n{existing_insights}\n\n请抽取增量。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
