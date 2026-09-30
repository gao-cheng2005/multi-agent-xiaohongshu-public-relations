"""
models/entities 数据库表结构定义。

这个文件把数据库里的每一张表，都对应成一个 Python 类，
每个类里的属性对应表中的一列字段。
这样做的好处是：代码里操作数据库时，就像操作普通对象一样简单，
不用手写一堆 SQL 语句。

表之间的关系（谁和谁有联系）：
- 一个"品牌"(Brand) 可以有多个"笔记"(Content)；
- 一条"笔记"可以有多个"评论"(Comment)、一份"分析"(Analysis)、
  多条"预警"(Alert)、一份"应对方案"(ResponsePlan)；
- "关键词"(Keyword) 和"系统配置"(SystemConfig) 各自独立。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TimestampMixin


def uuid7() -> uuid.UUID:
    """生成一个新的"编号"（UUID），用作每条数据的唯一标识。

    优先使用按时间排序的 UUID7（新生成的编号更大，方便按顺序排列），
    如果环境不支持就退回到普通 UUID。
    """
    try:
        import uuid6

        return uuid6.uuid7()
    except Exception:
        return uuid.uuid4()


class Brand(Base, TimestampMixin):
    """品牌表：记录监控的是哪个品牌。

    目前系统只使用一个默认品牌（is_default=True），
    以后如果要同时监控多个品牌，可以扩展这里。
    """

    __tablename__ = "brands"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 品牌名称（唯一，不能重复）
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # 所属平台，默认小红书
    platform: Mapped[str] = mapped_column(String(50), default="xiaohongshu")
    # 是否默认品牌（系统自动使用它）
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Keyword(Base, TimestampMixin):
    """关键词表：记录我们要监控哪些关键词。

    用户在界面上添加的关键词会存在这里，
    采集时按这些词去搜索并记录上次触发时间。
    """

    __tablename__ = "keywords"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 属于哪个品牌
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    # 关键词内容（唯一）
    keyword: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    # 平台
    platform: Mapped[str] = mapped_column(String(50), default="xiaohongshu")
    # 是否启用
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 上次用这个词触发采集的时间
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SystemConfig(Base, TimestampMixin):
    """系统配置表：保存一些可动态调整的配置。

    和写在 .env 文件里的配置不同，这里的配置可以
    在系统运行中通过接口随时修改。
    """

    __tablename__ = "system_configs"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 属于哪个品牌
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    # 配置项名字（唯一）
    config_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # 配置项的值
    config_value: Mapped[str] = mapped_column(Text, nullable=False)


class Content(Base, TimestampMixin):
    """笔记表：记录采集到的小红书笔记。

    每一条抓回来的笔记就是这里的一行数据，
    包含标题、正文、作者、点赞数等基本信息。
    """

    __tablename__ = "contents"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 属于哪个品牌
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    # 平台（默认小红书）
    platform: Mapped[str] = mapped_column(String(50), default="xiaohongshu")
    # 笔记在平台上的 ID（例如搜索结果链接里的那串编号）
    content_id: Mapped[str] = mapped_column(String(200), index=True)
    # 笔记链接（保留完整链接，含签名参数 xsec_token）
    url: Mapped[str] = mapped_column(Text)
    # 作者名
    author: Mapped[str] = mapped_column(String(200), default="")
    # 标题
    title: Mapped[str] = mapped_column(Text, default="")
    # 正文内容
    body: Mapped[str] = mapped_column(Text, default="")
    # 内容类型（默认是图文笔记 note）
    media_type: Mapped[str] = mapped_column(String(50), default="note")
    # 来源方式：按关键词采集 还是 按笔记链接采集
    source_type: Mapped[str] = mapped_column(String(50), default="keyword")
    # 通过哪个关键词采集到的
    keyword: Mapped[str] = mapped_column(String(200), default="")
    # 点赞数
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    # 收藏数
    collect_count: Mapped[int] = mapped_column(Integer, default=0)
    # 评论总数（平台展示的数字）
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    # 转发数
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    # 浏览量
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    # 发布时间
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 原始抓取数据（JSON，保留所有细节，方便以后追溯）
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    # 去重指纹：内容一样（忽略链接参数差异）的笔记算出的编号一样，防止重复
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # 与评论表的一对多关系：一条笔记有多条评论
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="content", cascade="all, delete-orphan"
    )


class Comment(Base, TimestampMixin):
    """评论表：记录采集到的每一条评论。

    支持楼中楼（回复里的回复）：通过 parent_id 指向上一条父评论，
    没有父评论的就是顶层评论。
    """

    __tablename__ = "comments"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 属于哪个品牌
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    # 属于哪条笔记（外键，指向笔记表的主键；必须填写，不能为空）
    content_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contents.id"), nullable=False)
    # 笔记在平台上的 ID（方便按笔记查找评论）
    note_id: Mapped[str] = mapped_column(String(200), index=True)
    # 评论自己的 ID（由"笔记ID_序号"组成）
    comment_id: Mapped[str] = mapped_column(String(200), index=True)
    # 父评论 ID：有值表示这是回复，空表示顶层评论
    parent_id: Mapped[str | None] = mapped_column(String(200), index=True)
    # 评论作者
    author: Mapped[str] = mapped_column(String(200), default="")
    # 评论内容
    text: Mapped[str] = mapped_column(Text, default="")
    # 点赞数
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    # 发表时间（解析不了的展示文案存空，原文在 raw_json 里）
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 原始抓取数据
    raw_json: Mapped[dict | None] = mapped_column(JSON)

    # 指向所属笔记的对象关系
    content: Mapped[Content] = relationship(back_populates="comments")


class Analysis(Base, TimestampMixin):
    """分析表：保存对每条笔记的情感/风险分析结果。

    分析结果由大模型或规则（词库）生成，
    包含：情感（正面/中性/负面）、置信度、风险等级、关键词等。
    """

    __tablename__ = "analyses"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 属于哪个品牌
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    # 对应笔记在平台上的 ID
    content_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    # 情感倾向：正面/中性/负面
    sentiment: Mapped[str] = mapped_column(String(20), default="中性")
    # 置信度：分析结果有多可信（0~1 之间）
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # 涉及的话题
    topics: Mapped[list] = mapped_column(JSON, default=list)
    # 命中的关键词
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    # 风险等级：低/中/高
    risk_level: Mapped[str] = mapped_column(String(20), default="低")
    # 风险分数（内部排序用）
    score: Mapped[float] = mapped_column(Float, default=0.0)
    # 用哪个模型/方式分析的（记录来源，便于排查）
    model: Mapped[str] = mapped_column(String(100), default="rule")
    # 分析摘要
    summary: Mapped[str] = mapped_column(Text, default="")


class Alert(Base, TimestampMixin):
    """预警表：记录系统发现的值得关注的舆情风险。

    例如发现负面情感、命中敏感词等，就会生成一条预警，
    状态 open 表示还没处理，handled 表示已处理。
    """

    __tablename__ = "alerts"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 属于哪个品牌
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    # 对应的笔记 ID（也可能是评论 ID，看触发来源）
    content_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    # 触发预警的规则/原因类型
    rule: Mapped[str] = mapped_column(String(100), nullable=False)
    # 预警等级：中/高
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    # 预警原因说明
    reason: Mapped[str] = mapped_column(Text, default="")
    # 状态：open 待处理 / handled 已处理
    status: Mapped[str] = mapped_column(String(20), default="open")
    # 处理时间（未处理时为空）
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResponsePlan(Base, TimestampMixin):
    """应对方案表：保存给某条笔记生成的公关应对建议。

    当笔记有中高风险（或用户手动生成）时，系统会生成一份方案，
    包含：应对要点、推荐动作、发给用户/评论区的文案草稿等。
    """

    __tablename__ = "response_plans"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 属于哪个品牌
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    # 对应笔记的 ID（一条笔记只有一份方案，所以唯一）
    content_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    # 触发方式：auto 系统自动生成 / manual 用户手动生成
    trigger: Mapped[str] = mapped_column(String(20), default="auto")
    # 渠道结论：dm 私信 / public 公开评论 / skip 无需处理（Agent③ 输出）
    channel: Mapped[str | None] = mapped_column(String(20), default=None)
    # 应对要点总结
    summary: Mapped[str] = mapped_column(Text, default="")
    # 推荐的行动步骤
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    # 为什么这么建议
    reason: Mapped[str] = mapped_column(Text, default="")
    # 私信回复文案草稿
    dm_copy: Mapped[str] = mapped_column(Text, default="")
    # 评论区回复文案草稿
    comment_copy: Mapped[str] = mapped_column(Text, default="")
    # 状态：pending 待决策 / accepted 已采纳 / closed 已关闭
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # 决策时间
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 决策人
    decided_by: Mapped[str] = mapped_column(String(100), default="")

class IssueTag(Base, TimestampMixin):
    """问题标签表：产品数据分析用。

    每行 = 用户反馈里抽出的一个"问题标签"：
    - dimension 是归并后的大类（如 发热/散热），label 是具体说法（如 易发烫）；
    - polarity 表示该说法是负面问题还是中性描述；
    - source 记录来自正文(note)还是评论(comment)；
    - excerpt 记录原文摘录，报表可回溯；
    - confirmed=False 表示该维度是 Agent 新建、待人工确认。
    """

    __tablename__ = "issue_tags"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 属于哪个品牌
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    # 所属产品（采集关键词）
    product: Mapped[str] = mapped_column(String(200), index=True)
    # 笔记业务编号
    content_id: Mapped[str] = mapped_column(String(200), index=True)
    # 维度大类（预定义 或 Agent 新建）
    dimension: Mapped[str] = mapped_column(String(100), index=True)
    # 维度的一句话定义/近义词（帮助归并，防碎片）
    dimension_def: Mapped[str] = mapped_column(String(500), default="")
    # 用户原话/近义说法
    label: Mapped[str] = mapped_column(String(200), default="")
    # 正负面：negative 抱怨问题 / neutral 中性提及
    polarity: Mapped[str] = mapped_column(String(20), default="negative")
    # 来源：note 正文/标题 / comment 评论
    source: Mapped[str] = mapped_column(String(20), default="comment")
    # 提出者昵称（主体去重计次用）：正文/标题=笔记作者，评论=评论用户
    author: Mapped[str] = mapped_column(String(200), default="")
    # 原文摘录（供回溯）
    excerpt: Mapped[str] = mapped_column(Text, default="")
    # 是否已确认（False = Agent 新建维度，待人工确认）
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductReport(Base, TimestampMixin):
    """产品优化建议缓存表：一个产品一份最新报告（由报表 Agent⑦ 生成）。

    product 唯一；report 存 Agent 输出的结构化报告（summary/top_issues/
    suggestions/new_dimensions），页面读缓存即显示，采集后自动更新。
    """

    __tablename__ = "product_reports"

    # 唯一的编号
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # 属于哪个品牌
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    # 产品名（与产品/关键词一致）
    product: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    # Agent⑦ 生成的结构化报告（JSON）
    report: Mapped[dict] = mapped_column(JSON, default=dict)
