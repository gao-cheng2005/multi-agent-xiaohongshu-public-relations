"""关键词检索（BM25 字面匹配）。

向量检索靠"意思相近"来召回，但有时候用户就是按关键词搜，字面匹配更直接。
这个文件用分词 + BM25 算法做关键词打分，作为向量检索的兜底：
向量接口不可用时，仍能按关键词召回内容；两者混合使用时还能互相补充。

原则：分词或建索引失败一律返回空，绝不抛异常影响主流程。
"""

from __future__ import annotations

import jieba
from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    """把一段中文文本切成词（去掉空白词）。"""
    if not text:
        return []
    return [w for w in jieba.lcut(str(text)) if w.strip()]


class BM25Index:
    """对一批文档建立 BM25 索引，支持按查询词召回 top-k。"""

    def __init__(self, documents: list[str]) -> None:
        self._documents = list(documents)
        try:
            # 先把每篇文档分词，再交给算法建索引
            self._index = BM25Okapi([tokenize(d) for d in self._documents])
        except Exception:
            self._index = None

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        """返回 [(文档下标, 分数)]，按分数从高到低排序；无结果返回空。"""
        if self._index is None or not self._documents or not query:
            return []
        try:
            scores = self._index.get_scores(tokenize(query))
        except Exception:
            return []
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
