"""分析流程（情感 + 风险）。

把"分析"这件事串成一个固定流程：①情感 → ②风险。
每次分析的产出会随状态返回，由调用方负责落库分析与预警。

这个流程主要供测试和独立分析场景使用；生产采集路径走 post_collect_workflow。
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..agents.sentiment_agent import analyze_risk, analyze_sentiment


class AnalysisState(TypedDict, total=False):
    """分析流程的共享状态包。"""

    content_id: str
    title: str
    body: str
    like_count: int
    collect_count: int
    share_count: int
    comment_count: int
    published_at: str
    comments: list
    sentiment: str       # ① 结果
    confidence: float    # ① 置信度
    analysis: dict       # ①② 合并后的完整分析字典


async def _sentiment_node(state: AnalysisState) -> AnalysisState:
    """节点：① 情感判断，把结果写进状态并合并进分析字典。"""
    result = await analyze_sentiment(dict(state))
    return {
        "sentiment": result["sentiment"],
        "confidence": result.get("confidence", 0.5),
        "analysis": {**(state.get("analysis") or {}), **result},
    }


async def _risk_node(state: AnalysisState) -> AnalysisState:
    """节点：② 风险判断，把结果合并进分析字典。"""
    result = await analyze_risk(dict(state), state.get("comments") or [])
    return {"analysis": {**(state.get("analysis") or {}), **result}}


def build_analysis_workflow():
    """构建分析流程：开始 → 情感 → 风险 → 结束。"""
    graph = StateGraph(AnalysisState)
    graph.add_node("sentiment", _sentiment_node)
    graph.add_node("risk", _risk_node)
    graph.add_edge(START, "sentiment")
    graph.add_edge("sentiment", "risk")
    graph.add_edge("risk", END)
    return graph.compile()
