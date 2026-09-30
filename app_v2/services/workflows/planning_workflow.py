"""方案生成流程。

负责"生成应对方案"的完整流程：③渠道推荐 → ④文案撰写 → ⑤打分（不达标最多回环 2 轮）→ 落库。

流程入口状态由调用方提供（情感/风险/笔记信息）；store_plan 由调用方注入，负责最终写库。
打分回环用条件分支实现：不达标且轮数不足 → 回到文案节点重写。
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..agents.decision import score_passed
from ..agents.factory import run_channel_agent, run_draft_agent, run_score_agent

MAX_ROUNDS = 2  # 文案最多写到 2 版（初稿 + 一次修改）


class PlanState(TypedDict, total=False):
    """方案流程的共享状态包。"""

    content_id: str
    title: str
    body: str
    comments: list
    sentiment: str       # ① 结果
    risk_level: str      # ② 结果
    risk_reason: str
    urgent: bool
    published_at: str
    human_feedback: str  # 操作者的人工修改要求
    analysis: dict
    dimensions: list     # 问题维度（供检索历史文案用）
    channel: str         # ③ 结论：dm / public
    reason: str          # ③ 给使用者的话
    draft_text: str      # ④ 生成的文案
    score: float         # ⑤ 总分
    feedback: str        # ⑤ 修改建议
    passed: bool         # 是否达标
    rounds: int          # 已生成第几版
    status: str          # done / skipped


async def _channel_node(state: PlanState) -> PlanState:
    """节点：③ 渠道推荐（公开评论 / 私信）。"""
    payload = (
        f"笔记：{state.get('title', '')}\n"
        f"情感：{state.get('sentiment', '中性')}  风险：{state.get('risk_level', '低')}"
        f"  风险原因：{state.get('risk_reason', '')}\n"
        f"发布时间：{state.get('published_at', '') or '未知'}\n"
        f"是否建议尽快干预：{state.get('urgent', False)}"
    )
    channel = await run_channel_agent(payload)
    return {"channel": channel.action, "reason": channel.reason}


async def _draft_node(state: PlanState) -> PlanState:
    """节点：④ 文案撰写（带历史参考、上一轮修改建议与人工要求）。"""
    # 人工修改要求优先级最高，放在提示词里强调遵循
    human = (state.get('human_feedback') or '').strip()
    human_line = f"\n⚠️ 操作者的修改要求（必须满足）：{human}\n" if human else ""

    # 检索历史"完成处理时采用"的相似文案作为参考；失败/无结果静默跳过
    rag_line = ""
    try:
        from ..plan_copy_index import format_references, search_references

        references = await search_references({
            "title": state.get("title", ""),
            "body": state.get("body", ""),
            "sentiment": state.get("sentiment", ""),
            "risk_level": state.get("risk_level", ""),
            "channel": state.get("channel", ""),
            "dimensions": state.get("dimensions") or [],
        })
        rag_line = format_references(references, state.get("channel", ""))
    except Exception:
        rag_line = ""

    payload = (
        f"渠道：{'私信作者' if state.get('channel') == 'dm' else '公开评论'}\n"
        f"情感：{state.get('sentiment', '中性')}  风险等级：{state.get('risk_level', '低')}\n"
        f"风险原因：{state.get('risk_reason', '')}\n"
        f"上轮修改建议：{state.get('feedback', '')}"
        f"{human_line}"
    )
    if rag_line:
        payload += rag_line
    draft = await run_draft_agent(payload)
    return {"draft_text": draft.text}


async def _score_node(state: PlanState) -> PlanState:
    """节点：⑤ 打分（用统一及格线判定是否达标）。"""
    payload = f"渠道：{state.get('channel')}\n文案：\n{state.get('draft_text', '')}"
    scored = await run_score_agent(payload)
    return {
        "score": scored.score,
        "feedback": scored.feedback,
        "passed": score_passed(scored.score, scored.dimension_scores),
        "rounds": (state.get("rounds") or 0) + 1,
    }


def _route_after_score(state: PlanState) -> str:
    """条件分支：不达标且轮数不足 → 回 draft 重写；否则进入收尾。"""
    if not state.get("passed") and (state.get("rounds") or 0) < MAX_ROUNDS:
        return "draft"
    return "finalize"


def build_planning_workflow(store_plan=None):
    """构建方案流程。store_plan 是收尾时写库的回调函数。"""

    async def _finalize_node(state: PlanState) -> PlanState:
        """收尾节点：把最终方案交给调用方落库，并标记状态。"""
        status = "done" if state.get("channel") else "skipped"
        if store_plan is not None:
            await store_plan(state)
        return {"status": status}

    # 定义节点和连线
    graph = StateGraph(PlanState)
    graph.add_node("channel", _channel_node)
    graph.add_node("draft", _draft_node)
    graph.add_node("score", _score_node)
    graph.add_node("finalize", _finalize_node)
    graph.add_edge(START, "channel")
    graph.add_edge("channel", "draft")
    graph.add_edge("draft", "score")
    graph.add_conditional_edges("score", _route_after_score, {"draft": "draft", "finalize": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile()
