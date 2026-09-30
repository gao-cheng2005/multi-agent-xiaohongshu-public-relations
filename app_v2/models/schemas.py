"""
models/schemas 接口输入输出格式定义。

接口之间传递数据需要一个"格式说明"，这里是两处用途：
1. 接收前端传来的数据（如采集请求、新增关键词请求），
   提前定义好哪些字段必须有、范围是多少，不符合就报错；
2. 定义大模型返回结果的格式，用来校验大模型回答是否规范。

（Pydantic 是一个做数据校验的库，保证收到的数据长成我们预期的样子。）
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class KeywordCreate(BaseModel):
    """新增关键词时前端需要传的数据。"""

    keyword: str                    # 关键词内容（必填）
    platform: str = "xiaohongshu"   # 平台，默认小红书


class CollectRequest(BaseModel):
    """触发采集时前端传的参数。

    两种采集方式二选一：
    - 按关键词采集（keyword）；
    - 按笔记链接采集（note_url）。
    另外还可以控制：抓多少条笔记、要不要抓评论、最多抓几条评论。
    """

    keyword: str | None = None             # 采集关键词（与 note_url 二选一）
    note_url: str | None = None            # 采集的笔记链接（与 keyword 二选一）
    limit: int = Field(default=10, ge=1, le=50)          # 最多抓取的笔记数（1~50）
    fetch_comments: bool = True            # 是否抓取评论
    comment_depth: int = Field(default=3, ge=1, le=20)   # 每条笔记最多抓的顶层评论数


class ConfigUpdate(BaseModel):
    """更新系统配置时前端传的数据。"""

    key: str    # 配置项名
    value: str  # 配置项值


class SentimentResult(BaseModel):
    """大模型做情感分析时，要求它严格按这个格式回答。"""

    sentiment: str      # 情感：正面/中性/负面
    confidence: float   # 置信度
    topics: list[str]   # 涉及的话题列表
    keywords: list[str] # 命中的关键词列表
    risk_level: str     # 风险等级：低/中/高
    score: float        # 风险分数
    summary: str        # 分析摘要


class ResponsePlanResult(BaseModel):
    """大模型生成应对方案时，要求它严格按这个格式回答。"""

    summary: str             # 应对要点总结
    recommended_action: str  # 推荐行动步骤
    reason: str              # 为什么这么建议
    dm_copy: str             # 私信回复文案草稿
    comment_copy: str        # 评论区回复文案草稿

class NoteSentiment(BaseModel):
    """Agent① 情感判断输出：只看作者情绪，不评估风险。"""

    sentiment: str        # 正面 / 中性 / 负面
    confidence: float     # 置信度 0~1


class RiskResult(BaseModel):
    """Agent② 风险输出：内容危害度 × 传播态势。"""

    risk_level: str       # 低 / 中 / 高
    reason: str           # 一句话原因（给人看，也喂给 Agent③）
    harm_score: float     # 内容危害度 0~10
    spread_score: float   # 传播态势 0~10
    urgent: bool          # 是否建议尽快干预


class ChannelResult(BaseModel):
    """Agent③ 渠道输出。"""

    action: Literal["dm", "public", "skip"]  # skip 由规则短路处理
    reason: str           # 给使用者的一句话原因


class DraftResult(BaseModel):
    """Agent④ 文本输出。"""

    text: str             # 最终文案


class ScoreResult(BaseModel):
    """Agent⑤ 打分输出。"""

    score: float            # 总分 0~10
    passed: bool            # 是否达标
    feedback: str           # 修改建议（给 Agent④）
    dimension_scores: dict = Field(default_factory=dict)  # 各维度分，如 {"tone": 8, ...}


class IssueTagItem(BaseModel):
    """问题标签抽取 Agent⑥ 输出的单个标签项。"""

    dimension: str        # 问题类型（预定义 或 新建）
    dimension_def: str    # 该类型的一句话定义/近义词（帮助归并，防碎片）
    label: str            # 用户原话/近义表达
    polarity: str         # negative（抱怨/问题）或 neutral（中性提及）
    source: str           # note（正文/标题=作者）或 comment（评论）
    author: str           # 提出者昵称：正文/标题填笔记作者；评论填评论用户
    excerpt: str          # 原文摘录（简短）


class IssueTagResult(BaseModel):
    """Agent⑥ 输出：一篇笔记的所有问题标签。"""

    items: list[IssueTagItem]


class ReportIssueItem(BaseModel):
    """报表中单个问题的统计与建议。"""

    dimension: str
    count: int
    ratio: float
    negative_ratio: float
    suggestion: str
    evidence: str


class ReportResult(BaseModel):
    """报表 Agent⑦ 输出。"""

    summary: str                       # 一句话结论
    top_issues: list[ReportIssueItem]  # 问题排行
    suggestions: list[str]             # 优化建议列表
    new_dimensions: list[str]          # 新发现的待确认维度


class DimensionMergeItem(BaseModel):
    """维度归并 Agent 输出：单个归并项。"""

    from_dim: str   # 待确认的新维度名
    into_dim: str   # 归并到的正式维度名；空字符串表示保留为新维度


class MergeResult(BaseModel):
    """维度归并 Agent 输出。"""

    merges: list[DimensionMergeItem]
