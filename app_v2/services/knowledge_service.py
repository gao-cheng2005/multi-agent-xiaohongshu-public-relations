"""向量库服务（ChromaDB 的通用封装）。

向量库就是用来存"文字→向量"的地方，支持按相似度检索。文案话术库等 RAG 场景
都会复用这里的能力：写入、按向量查询、取全部候选、按条件删除。

设计原则：客户端懒加载；始终显式传入向量，绝不触发内置模型；失败静默。
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..core.settings import settings


class VectorStoreService:
    """ChromaDB 的通用封装。"""

    def __init__(self) -> None:
        self._client: chromadb.ClientAPI | None = None

    @property
    def client(self) -> chromadb.ClientAPI:
        """获取持久化客户端（首次使用时自动创建）。"""
        if self._client is None:
            persist_dir = Path(settings.chroma_persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    def get_or_create_collection(self, name: str):
        """获取集合，没有则自动创建。"""
        return self.client.get_or_create_collection(name=name)

    def upsert(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        """批量写入（有则更新、无则新增），必须显式传入向量。"""
        self.get_or_create_collection(collection_name).upsert(
            ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings
        )

    def query(
        self,
        collection_name: str,
        query_embedding: list[float],
        where: dict | None,
        n_results: int = 5,
    ) -> list[dict]:
        """按向量 + 过滤条件检索，返回 top-k 结果。"""
        collection = self.get_or_create_collection(collection_name)
        count = collection.count()
        if count == 0:
            return []
        result = collection.query(
            query_embeddings=[query_embedding],
            where=where,
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )
        return _normalize_query_result(result)

    def get_all(self, collection_name: str, where: dict | None) -> list[dict]:
        """按过滤条件取出全部候选（供关键词检索建索引等场景）。"""
        collection = self.get_or_create_collection(collection_name)
        result = collection.get(where=where, include=["documents", "metadatas"])
        return _normalize_get_result(result)

    def delete(
        self,
        collection_name: str,
        where: dict | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """按 id 或过滤条件删除。"""
        self.get_or_create_collection(collection_name).delete(ids=ids, where=where)


def _normalize_query_result(result: dict) -> list[dict]:
    """把 query 返回的嵌套结构拍平成统一列表。"""
    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    return [
        {
            "id": _id,
            "document": documents[i] if i < len(documents) else "",
            "metadata": metadatas[i] if i < len(metadatas) else {},
            "distance": distances[i] if i < len(distances) else None,
        }
        for i, _id in enumerate(ids)
    ]


def _normalize_get_result(result: dict) -> list[dict]:
    """把 get 返回的平铺结构整理成统一列表。"""
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    return [
        {
            "id": _id,
            "document": documents[i] if i < len(documents) else "",
            "metadata": metadatas[i] if i < len(metadatas) else {},
        }
        for i, _id in enumerate(ids)
    ]


# 全局唯一实例
vector_store = VectorStoreService()
