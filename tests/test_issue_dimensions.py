"""问题维度与词频统计的回归测试。"""

import pytest


def test_other_problem_removed_from_predefined():
    """预定义维度里不能再有"其他问题"（否则对不上的都落进去，不会待确认）。"""
    from app_v2.services.agents import prompts

    assert "其他问题" not in prompts.DIMENSION_NAMES
    assert "其他问题" not in prompts.ISSUE_DIMENSIONS


def test_normalize_dimension_name():
    """别名归一化：标准名原样返回；别名换算回标准名；全新维度原样返回；空值返回空。"""
    from app_v2.services.agents import prompts

    # 标准名直接返回
    assert prompts.normalize_dimension_name("发热/散热") == "发热/散热"
    # 常见别名 → 标准名
    assert prompts.normalize_dimension_name("发烫") == "发热/散热"
    assert prompts.normalize_dimension_name("散热差") == "发热/散热"
    assert prompts.normalize_dimension_name("闪屏") == "频闪"
    # 全新维度：原样返回，交给上层标待确认
    assert prompts.normalize_dimension_name("半夜自动亮灯") == "半夜自动亮灯"
    # 空白/空值/全角空格
    assert prompts.normalize_dimension_name("") == ""
    assert prompts.normalize_dimension_name(None) == ""
    assert prompts.normalize_dimension_name("  闪  ") == "频闪"
    assert prompts.normalize_dimension_name("做工/材质　") == "做工/材质"


async def test_issues_node_normalizes_alias_and_skips_empty(monkeypatch):
    """Agent⑥ 节点：别名归一化到正式维度；空维度丢弃；全新维度标待确认。"""
    from app_v2.services.workflows import post_collect_workflow as wf

    class FakeResult:
        items = [
            type("I", (), {"dimension": "发烫", "dimension_def": "", "label": "底座烫", "polarity": "negative", "source": "note", "author": "作者", "excerpt": "底座烫手"})(),
            type("I", (), {"dimension": "", "dimension_def": "", "label": "缺", "polarity": "negative", "source": "comment", "author": "u", "excerpt": "x"})(),
            type("I", (), {"dimension": "自动关灯", "dimension_def": "台灯自己亮起", "label": "半夜自己亮", "polarity": "negative", "source": "comment", "author": "u2", "excerpt": "y"})(),
        ]

    async def fake_tagger(payload):
        return FakeResult()

    monkeypatch.setattr(wf, "run_issue_tagger", fake_tagger)
    state = {"product": "产品A", "content": {"title": "t", "body": "b"}, "comments": []}
    out = await wf._issues_node(state)
    items = out["issue_items"]
    assert len(items) == 2
    assert items[0]["dimension"] == "发热/散热"
    assert items[0]["confirmed"] is True
    assert items[1]["dimension"] == "自动关灯"
    assert items[1]["confirmed"] is False


async def test_replace_for_content_skips_empty_and_defaults_unconfirmed():
    """落库：空维度跳过；缺 confirmed 时默认待确认（False）；别名可写入。"""
    from app_v2.repositories import issue_tag_repository as repo

    class FakeSession:
        def __init__(self):
            self.added = []

        async def execute(self, stmt, *a, **k):
            return None

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

    sess = FakeSession()
    r = repo.IssueTagRepository()
    count = await r.replace_for_content(
        sess,
        "brand-1",
        "产品A",
        "c1",
        [
            {"dimension": "发烫", "confirmed": True, "label": "底座烫"},
            {"dimension": "", "confirmed": False, "label": "空维度"},
            {"dimension": "自动关灯", "label": "缺 confirmed"},
            {"label": "缺 dimension"},
        ],
    )
    assert count == 2
    assert [o.dimension for o in sess.added] == ["发热/散热", "自动关灯"]
    assert sess.added[0].confirmed is True
    assert sess.added[1].confirmed is False


async def test_hotwords_counts_labels():
    """词频统计改为统计问题标签的用户原话（label）。"""
    from app_v2.services import analytics_service as ans

    class FakeIssueRepo:
        async def list_labels(self, session):
            return ["底座烫", "频闪", "底座烫", "亮度不够"]

    service = ans.AnalyticsService.__new__(ans.AnalyticsService)
    service.session = object()
    service.issue_repo = FakeIssueRepo()

    result = await service.hotwords(10)
    assert result == [
        {"word": "底座烫", "count": 2},
        {"word": "频闪", "count": 1},
        {"word": "亮度不够", "count": 1},
    ]
