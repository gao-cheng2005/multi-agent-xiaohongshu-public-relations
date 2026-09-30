"""采集后处理流程（多步骤流水线）。

把"采集之后要做的分析"编排成一个固定流程：
- phase=analyze：①情感 → ②风险 → 落库分析与预警（采集时同步执行）；
- phase=issues：⑥问题标签抽取 → 落库问题标签（采集后异步执行）。

落库等非智能体步骤由调用方注入（store_analysis / store_tags），流程只负责串顺序。
"""

from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..agents import prompts
from ..agents.factory import run_issue_tagger
from ..agents.sentiment_agent import analyze_risk, analyze_sentiment

logger = logging.getLogger("workflow.post_collect")


class PostCollectState(TypedDict, total=False):
    """整个流程共享的"状态包"，各节点读写这里面的字段。"""

    phase: str          # analyze | issues（决定从哪个阶段进入）
    content_id: str     # 笔记业务编号
    product: str        # 产品（采集关键词）
    content: dict       # 笔记内容
    comments: list      # 评论列表
    analysis: dict      # ①② 合并后的分析结果
    issue_items: list   # ⑥ 的问题标签数组


async def _sentiment_node(state: PostCollectState) -> PostCollectState:
    """节点：① 情感判断（标题+正文），把结果合并进分析状态。"""
    logger.info("Agent① 情感判断开始 content_id=%s", state.get("content_id"))
    result = await analyze_sentiment(state.get("content") or {})
    analysis = dict(state.get("analysis") or {})
    analysis.update(result)
    return {"analysis": analysis}


async def _risk_node(state: PostCollectState) -> PostCollectState:
    """节点：② 风险判断（评论+互动），把结果合并进分析状态。"""
    logger.info("Agent② 风险判断开始 content_id=%s", state.get("content_id"))
    result = await analyze_risk(state.get("content") or {}, state.get("comments") or [])
    analysis = dict(state.get("analysis") or {})
    analysis.update(result)
    return {"analysis": analysis}


async def _issues_node(state: PostCollectState) -> PostCollectState:
    """节点：⑥ 问题标签抽取（标题+正文+评论），输出标签数组。"""
    content = state.get("content") or {}
    comments = state.get("comments") or []
    # 把笔记和评论拼成一段文字，交给标签抽取助手
    comment_lines = "\n".join(f"- {c.get('content', '')[:120]}" for c in comments[:40]) or "（无评论）"
    payload = (
        f"产品：{state.get('product', '')}\n"
        f"标题：{content.get('title', '')}\n"
        f"正文：{content.get('body', '')[:2000]}\n"
        f"评论：\n{comment_lines}"
    )
    result = await run_issue_tagger(payload)

    items = []
    for it in result.items:
        # 别名归一化：模型偶尔不照抄标准名，把近义说法换算回标准维度名
        dimension = prompts.normalize_dimension_name(it.dimension)
        # 维度名为空（模型漏输出）直接丢弃，避免落成"其他问题"这类垃圾桶
        if not dimension:
            continue
        items.append(
            {
                "dimension": dimension,
                "dimension_def": it.dimension_def,
                "label": it.label,
                "polarity": it.polarity,
                "source": it.source,
                "author": it.author,
                "excerpt": it.excerpt,
                # 预定义维度 → 正式；新发现维度 → 待确认
                "confirmed": dimension in prompts.DIMENSION_NAMES,
            }
        )
    logger.info("Agent⑥ 问题标签抽取完成 content_id=%s 维度数=%s", state.get("content_id"), len(items))
    return {"issue_items": items}


def _route_start(state: PostCollectState) -> str:
    """起点条件分支：按 phase 决定先进入哪个阶段。"""
    return "issues" if state.get("phase") == "issues" else "sentiment"


def build_post_collect_workflow(store_analysis=None, store_tags=None):
    """构建采集后处理流程。store_analysis / store_tags 由调用方注入落库逻辑。"""

    async def _store_analysis_node(state: PostCollectState) -> PostCollectState:
        """落库节点：把分析结果和预警写进数据库。"""
        if store_analysis is not None:
            logger.info("落库分析+预警 content_id=%s", state.get("content_id"))
            await store_analysis(state)
        return {}

    async def _store_tags_node(state: PostCollectState) -> PostCollectState:
        """落库节点：把问题标签写进数据库。"""
        if store_tags is not None and state.get("issue_items"):
            await store_tags(
                state.get("content_id", ""),
                state.get("product", ""),
                state.get("issue_items", []),
            )
        return {}

    # 定义流程节点和它们之间的连线
    graph = StateGraph(PostCollectState)
    graph.add_node("sentiment", _sentiment_node)
    graph.add_node("risk", _risk_node)
    graph.add_node("issues", _issues_node)
    graph.add_node("store_analysis", _store_analysis_node)
    graph.add_node("store_tags", _store_tags_node)
    graph.add_conditional_edges(START, _route_start, {"sentiment": "sentiment", "issues": "issues"})
    graph.add_edge("sentiment", "risk")
    graph.add_edge("risk", "store_analysis")
    graph.add_edge("store_analysis", END)
    graph.add_edge("issues", "store_tags")
    graph.add_edge("store_tags", END)
    return graph.compile()
