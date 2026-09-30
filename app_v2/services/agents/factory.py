"""大模型智能体工厂。

"智能体"可以理解成一个个有专门分工的大模型助手，比如"情感判断助手"、
"文案撰写助手"等。这个文件负责按用途创建这些助手，并用缓存保证同一个助手只创建一次。

所有助手都通过统一的 create_agent 方式创建，输出格式由结构体约束，保证结果可解析。
"""

from __future__ import annotations

from functools import lru_cache

from langchain.agents import create_agent

from ...core.llm import llm_gateway
from ...models.schemas import (
    ChannelResult,
    DraftResult,
    IssueTagResult,
    MergeResult,
    NoteSentiment,
    ReportResult,
    RiskResult,
    ScoreResult,
)
from . import prompts


def _messages(payload: str) -> list[dict[str, str]]:
    """把要问的内容整理成标准消息格式。"""
    return [{"role": "user", "content": payload}]


def _make_agent(logical_key: str, system_prompt: str, response_format, temperature: float = 0):
    """创建（并缓存）一个助手。

    没配置密钥时返回 None，表示这个助手不可用，调用方应降级处理。
    """
    if not llm_gateway.configured:
        return None
    return create_agent(
        model=llm_gateway.chat_model(logical_key, temperature=temperature),
        system_prompt=system_prompt,
        response_format=response_format,
        name=f"{logical_key}_agent",
    )


# ---- 下面八个助手分别对应项目里的八个角色 ----

@lru_cache(maxsize=1)
def note_sentiment_agent():
    """① 情感判断助手：只判断内容正负面，不判断风险。"""
    return _make_agent("sentiment", prompts.SENTIMENT_PROMPT, NoteSentiment)


@lru_cache(maxsize=1)
def risk_agent():
    """② 风险评估助手：判断风险等级、危害度和传播态势。"""
    return _make_agent("risk", prompts.RISK_PROMPT, RiskResult)


@lru_cache(maxsize=1)
def channel_agent():
    """③ 渠道推荐助手：默认公开评论，特殊情况转私信。"""
    return _make_agent("channel", prompts.CHANNEL_PROMPT, ChannelResult)


@lru_cache(maxsize=1)
def draft_agent():
    """④ 文案撰写助手：写私信或公开评论文案。"""
    return _make_agent("draft", prompts.DRAFT_PROMPT, DraftResult, temperature=0.4)


@lru_cache(maxsize=1)
def score_agent():
    """⑤ 文案质检助手：给写好的文案打分。"""
    return _make_agent("score", prompts.SCORE_PROMPT, ScoreResult)


@lru_cache(maxsize=1)
def issue_tagger_agent():
    """⑥ 问题标签抽取助手：从笔记里抽问题标签。"""
    return _make_agent("issue_tagger", prompts.ISSUE_TAG_PROMPT, IssueTagResult)


@lru_cache(maxsize=1)
def merge_agent():
    """维度归并助手：把新发现的维度归并到正式维度。"""
    return _make_agent("merge", prompts.MERGE_PROMPT, MergeResult)


@lru_cache(maxsize=1)
def report_agent():
    """⑦ 报表助手：把问题数据整理成优化建议报告。"""
    return _make_agent("report", prompts.REPORT_PROMPT, ReportResult)


async def _run(agent_getter, payload: str):
    """统一的调用封装：拿到助手 → 发消息 → 取结构化结果。"""
    agent = agent_getter()
    if agent is None:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")
    result = await agent.ainvoke({"messages": _messages(payload)})
    return result["structured_response"]


# ---- 下面是对外暴露的调用函数，每个对应一个助手 ----

async def run_note_sentiment_agent(payload: str) -> NoteSentiment:
    return await _run(note_sentiment_agent, payload)


async def run_risk_agent(payload: str) -> RiskResult:
    return await _run(risk_agent, payload)


async def run_channel_agent(payload: str) -> ChannelResult:
    return await _run(channel_agent, payload)


async def run_draft_agent(payload: str) -> DraftResult:
    return await _run(draft_agent, payload)


async def run_score_agent(payload: str) -> ScoreResult:
    return await _run(score_agent, payload)


async def run_issue_tagger(payload: str) -> IssueTagResult:
    return await _run(issue_tagger_agent, payload)


async def run_merge_agent(payload: str) -> MergeResult:
    return await _run(merge_agent, payload)


async def run_report_agent(payload: str) -> ReportResult:
    return await _run(report_agent, payload)
