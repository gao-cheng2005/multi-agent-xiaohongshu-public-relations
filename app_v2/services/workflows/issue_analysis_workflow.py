"""产品数据分析的低频流程。

包含两个独立的小流程：
- 维度归并：把待确认的新维度归并到正式维度；
- 报表建议：把产品问题聚合数据整理成优化建议报告。

这两个流程调用频率低，所以单独放在这里，不和采集后处理流程混在一起。
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..agents.factory import run_merge_agent, run_report_agent


class MergeState(TypedDict, total=False):
    """维度归并流程的状态。"""

    payload: str   # 现有维度 + 待确认维度清单（文本）
    merges: list   # 归并结果：[{from_dim, into_dim}]


class ReportGraphState(TypedDict, total=False):
    """报表建议流程的状态。"""

    payload: str   # 产品问题聚合数据（文本）
    report: dict   # 报表助手输出的结构化报告


async def _merge_node(state: MergeState) -> MergeState:
    """节点：维度归并助手。"""
    result = await run_merge_agent(state.get("payload") or "")
    return {"merges": [m.model_dump() for m in result.merges]}


async def _report_node(state: ReportGraphState) -> ReportGraphState:
    """节点：报表建议助手。"""
    result = await run_report_agent(state.get("payload") or "")
    return {"report": result.model_dump()}


def build_merge_workflow():
    """构建维度归并流程：归并助手 → 结束。"""
    graph = StateGraph(MergeState)
    graph.add_node("merge", _merge_node)
    graph.add_edge(START, "merge")
    graph.add_edge("merge", END)
    return graph.compile()


def build_report_workflow():
    """构建报表建议流程：报表助手 → 结束。"""
    graph = StateGraph(ReportGraphState)
    graph.add_node("report", _report_node)
    graph.add_edge(START, "report")
    graph.add_edge("report", END)
    return graph.compile()
