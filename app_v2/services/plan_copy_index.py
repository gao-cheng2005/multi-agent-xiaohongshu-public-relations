"""文案话术库索引。

负责"完成处理时采用的公关文案"的入库、删除与检索：
- 写入：方案完成处理且渠道/文案有效时，异步灌入向量库；
- 删除：内容删除时同步移除索引；
- 检索：文案生成前，按情感/风险/渠道 + 笔记文本召回历史参考。

原则：检索失败或无结果返回空；索引失败静默，绝不阻断主流程。
"""

from __future__ import annotations

import asyncio
import logging

from ..core.embedding import embeddings
from ..core.settings import settings
from ..repositories.analysis_repository import AnalysisRepository
from ..repositories.content_repository import ContentRepository
from ..repositories.issue_tag_repository import IssueTagRepository
from ..repositories.plan_repository import ResponsePlanRepository
from .knowledge_service import vector_store
from .retrieval import hybrid_search

COLLECTION = "plan_copy_library"  # 向量库里的集合名
_TEXT_LIMIT = 200   # 标题/正文各自最大长度
_COPY_LIMIT = 800   # 存储文案的最大长度

_logger = logging.getLogger("rag.plan_copy_index")


def build_document(title: str, body: str, dimensions: list[str]) -> str:
    """构造用于检索的文档文本：标题 + 正文摘要 + 问题标签。"""
    parts: list[str] = []
    if title:
        parts.append((title or "").strip()[:_TEXT_LIMIT])
    if body:
        parts.append((body or "").strip()[:_TEXT_LIMIT])
    if dimensions:
        parts.append("问题标签：" + "、".join(dimensions))
    return "\n".join(parts) or "（无标题）"


async def build_plan_copy_record(session, content_id: str) -> dict | None:
    """读取数据库，组装一条待入库的文案记录。

    准入条件：方案已关闭、渠道是私信或公开评论、对应文案非空。
    不符合返回 None，表示不写入。
    """
    plan = await ResponsePlanRepository().get_by_content_id(session, content_id)
    if plan is None or plan.status != "closed":
        return None
    # 按渠道取对应的文案
    if plan.channel == "dm":
        copy_text = (plan.dm_copy or "").strip()
    elif plan.channel == "public":
        copy_text = (plan.comment_copy or "").strip()
    else:
        return None
    if not copy_text:
        return None

    content = await ContentRepository().get_by_external_id(session, content_id)
    if content is None:
        return None

    analysis = await AnalysisRepository().latest_for_content(session, content_id)
    sentiment = (analysis.sentiment if analysis else "") or "中性"
    risk_level = (analysis.risk_level if analysis else "") or "低"
    dimensions = await _load_dimensions(session, content_id)

    # 组装元数据（用于结构化过滤和展示）
    metadata: dict = {
        "sentiment": sentiment,
        "risk_level": risk_level,
        "channel": plan.channel,
        "copy_text": copy_text[:_COPY_LIMIT],
        "content_id": content_id,
        "title": (content.title or "").strip()[:100] or "（无标题）",
    }
    if dimensions:
        metadata["dimensions"] = dimensions

    return {
        "id": f"{content_id}:{plan.channel}",
        "document": build_document(content.title, content.body, dimensions),
        "metadata": metadata,
    }


async def _load_dimensions(session, content_id: str) -> list[str]:
    """读取某篇笔记的问题维度（去重、排序），供检索用。"""
    try:
        return await IssueTagRepository().list_dimensions_by_content(session, content_id)
    except Exception:
        return []


async def index_plan_copy_async(record: dict) -> None:
    """后台任务：把一条文案转成向量并写入向量库（失败静默但留日志）。"""
    _id = record.get("id", "")
    try:
        vec = await embeddings.embed_query(record["document"])
        if vec is None:
            _logger.warning("文案库写入跳过（embedding 不可用）：%s", _id)
            return
        vector_store.upsert(
            COLLECTION,
            ids=[record["id"]],
            documents=[record["document"]],
            metadatas=[record["metadata"]],
            embeddings=[vec],
        )
        meta = record.get("metadata") or {}
        _logger.info(
            "文案库已写入：id=%s，渠道=%s，文案前30字=%s",
            _id, meta.get("channel", ""), (meta.get("copy_text") or "")[:30],
        )
    except Exception as exc:
        _logger.warning("文案库写入失败（跳过）：%s，原因=%s", _id, exc)


def schedule_index(record: dict) -> None:
    """调度后台写入任务，不阻塞当前请求。"""
    try:
        asyncio.get_running_loop().create_task(index_plan_copy_async(record))
    except Exception:
        pass


async def remove_plan_copies(content_ids: list[str]) -> None:
    """按笔记 ID 批量移除索引（内容删除时调用）。"""
    if not content_ids:
        return
    try:
        await asyncio.to_thread(_remove_sync, content_ids)
    except Exception:
        return


def _remove_sync(content_ids: list[str]) -> None:
    """同步删除（放在线程里跑，避免阻塞事件循环）。"""
    removed = 0
    for cid in content_ids:
        try:
            vector_store.delete(COLLECTION, where={"content_id": cid})
            removed += 1
        except Exception:
            continue
    if removed:
        _logger.info("文案库已移除 %s 篇笔记的索引", removed)


def schedule_remove(content_ids: list[str]) -> None:
    """调度后台删除任务。"""
    if not content_ids:
        return
    try:
        asyncio.get_running_loop().create_task(remove_plan_copies(content_ids))
    except Exception:
        pass


async def search_references(query: dict) -> list[dict]:
    """在线检索历史文案参考；失败或无结果返回空列表。

    query 可包含 title/body/sentiment/risk_level/channel/dimensions。
    """
    if not settings.rag_enabled:
        return []
    title = (query.get("title") or "").strip()
    body = (query.get("body") or "").strip()
    dims = query.get("dimensions") or []
    # 没有笔记文本也没有问题维度时，不检索
    if not title and not body and not dims:
        return []
    query_text = build_document(title, body, dims)
    where = _build_where(query)
    try:
        return await hybrid_search(COLLECTION, query_text, where, settings.rag_top_k)
    except Exception:
        return []


def _build_where(query: dict) -> dict | None:
    """构造结构化过滤条件：情感/风险/渠道精确匹配，维度做包含匹配。"""
    conditions: list[dict] = []
    for key in ("sentiment", "risk_level", "channel"):
        val = (query.get(key) or "").strip()
        if val:
            conditions.append({key: val})
    dims = query.get("dimensions") or []
    if dims:
        conditions.append({"dimensions": {"$contains": dims[0]}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def format_references(references: list[dict], channel: str) -> str:
    """把命中的历史文案拼成 few-shot 参考文本；无有效内容返回空串。"""
    channel_label = "私信" if channel == "dm" else "公开评论"
    lines = ["\n【历史完成处理时采用的文案参考（参考其风格与口径，但需针对当前笔记重新撰写，不要照抄）】"]
    for i, ref in enumerate(references, start=1):
        md = ref.get("metadata") or {}
        copy_text = (md.get("copy_text") or "").strip()
        title = (md.get("title") or "").strip()
        if not copy_text:
            continue
        lines.append(f"示例{i}：背景={title or '（无标题）'}，渠道={channel_label}，采用的文案={copy_text}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)
