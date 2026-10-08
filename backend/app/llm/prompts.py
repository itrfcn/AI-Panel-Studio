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
        "专家席位要求：\n"
        "- 立场应多样化，覆盖话题不同侧面（支持/反对/中立/技术/伦理等）\n"
        "- 颜色需区分明显，使用 #RRGGBB 格式\n"
        "- 每位专家有独立 title 与简短 stance（≤30 字）\n\n"
        "严格输出 JSON 对象，格式如下（不要 markdown、不要解释）：\n"
        "{\n"
        '  "roster": [\n'
        '    {"role":"moderator","name":"主持人姓名","title":"主持人职业","stance":null,"color":"#RRGGBB","profile":"资深主持人，擅长..."},\n'
        '    {"role":"expert","name":"专家姓名","title":"专家职业","stance":"该专家立场摘要","color":"#RRGGBB","profile":"背景与观点倾向..."}\n'
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
# 阶段 4（预留）：专家发言
# ---------------------------------------------------------------------------


def expert_speak_prompt(
    expert_name: str,
    expert_stance: str,
    expert_title: str,
    topic_title: str,
    context_text: str,
) -> list[dict[str, str]]:
    """专家单轮发言。MVP 不调用，阶段 4 用。

    context_text 是 build_context 拼出的最近 K 条发言。
    """
    system = (
        f"你是圆桌讨论的专家 {expert_name}（{expert_title}），立场倾向：{expert_stance}。"
        f"讨论话题：{topic_title}。\n"
        "请基于上下文发表 1 段发言（约 100-180 字），要求：\n"
        "- 紧扣话题、保持立场一致性，可适度反驳他人\n"
        "- 提供具体论点或例子，不空话\n"
        "- 不带 markdown、emoji，自然口语化\n"
    )
    user = f"已有发言：\n{context_text}\n\n请发言。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def followup_prompt(topic_title: str, context_text: str) -> list[dict[str, str]]:
    """主持人追问。MVP 不调用，阶段 4 用。"""
    system = (
        "你是圆桌讨论的主持人，根据当前发言决定是否追问或切换话题。"
        f"讨论话题：{topic_title}。\n"
        "输出一段简短追问或过渡语（50-100 字），不带 markdown/emoji。"
    )
    user = f"已有发言：\n{context_text}\n\n请输出追问或过渡。"
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
    """抽取共识/分歧。MVP 不调用，阶段 5 用。"""
    system = (
        "你是圆桌讨论的洞察分析 Agent。基于发言抽取共识与分歧。"
        f"讨论话题：{topic_title}。\n"
        "- 共识：多人达成一致的观点；分歧：明显对立的观点\n"
        "- 每条 summary ≤30 字\n"
        "- strength：weak/medium/strong\n"
        "严格输出 JSON：\n"
        '{"insights":[{"type":"consensus|divergence","summary":"...","strength":"weak|medium|strong","guest_ids":[],"transcript_ids":[]}]}\n'
        "若无可抽取，返回 {\"insights\":[]}。"
    )
    user = (
        f"已有发言：\n{transcript_text}\n\n"
        f"已有 insight（避免重复）：\n{existing_insights}\n\n请抽取增量。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
