async def test_delete_contents_excludes_closed_plans():
    """舆情内容的删除必须排除已处理（closed）的笔记，保护处理记录存档。"""
    from sqlalchemy.dialects import mysql
    from app_v2.services import content_service as cs

    class FakeRows:
        def scalars(self):
            return self

        def all(self):
            return []          # 没有查到内容 → 直接返回（不会再发删除 SQL）

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, *a, **k):
            self.statements.append(statement)
            return FakeRows()

    service = cs.ContentService.__new__(cs.ContentService)
    service.session = FakeSession()

    count = await service.delete_contents(q="任一条件")   # 任意筛选
    assert count == 0

    # 检查发给数据库的查询里包含"只保留未处理"的过滤（把参数转成字面量便于断言）
    sql = str(service.session.statements[0].compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "closed" in sql                       # 包含对 closed 的排除
    assert "response_plans" in sql.lower()       # 关联了方案表
    assert "IS NULL" in sql                      # 允许"没有方案"的笔记被删


async def test_delete_contents_handled_only_adds_closed_filter():
    """处理记录页删筛选/清空时：handled_only=True 应只删已处理（closed）笔记。"""
    from sqlalchemy.dialects import mysql
    from app_v2.services import content_service as cs

    class FakeRows:
        def scalars(self):
            return self

        def all(self):
            return []

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, *a, **k):
            self.statements.append(statement)
            return FakeRows()

    service = cs.ContentService.__new__(cs.ContentService)
    service.session = FakeSession()

    await service.delete_contents(allow_handled=True, handled_only=True)
    sql = str(
        service.session.statements[0].compile(
            dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "closed" in sql          # 明确限定只删已处理
    assert "IS NULL" not in sql      # 不再排除"无方案"（处理记录一定都有方案）


async def test_delete_contents_channel_filter():
    """处理记录页按处理渠道删除时，应把 channel 条件下推到 SQL。"""
    from sqlalchemy.dialects import mysql
    from app_v2.services import content_service as cs

    class FakeRows:
        def scalars(self):
            return self

        def all(self):
            return []

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, *a, **k):
            self.statements.append(statement)
            return FakeRows()

    service = cs.ContentService.__new__(cs.ContentService)
    service.session = FakeSession()

    await service.delete_contents(channel="skip", allow_handled=True, handled_only=True)
    sql = str(
        service.session.statements[0].compile(
            dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "skip" in sql


async def test_delete_contents_allow_handled_removes_closed_filter():
    """allow_handled=True 时，删除 SQL 不应再排除已处理（closed）的笔记。"""
    from sqlalchemy.dialects import mysql
    from app_v2.services import content_service as cs

    class FakeRows:
        def scalars(self):
            return self

        def all(self):
            return []

    class FakeSession:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, *a, **k):
            self.statements.append(statement)
            return FakeRows()

    service = cs.ContentService.__new__(cs.ContentService)
    service.session = FakeSession()

    await service.delete_contents(keyword="x", allow_handled=True)
    sql = str(
        service.session.statements[0].compile(
            dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    # 语义：status=closed 的笔记可以被删除 → sql 不应包含对 closed 的排除条件
    assert "closed" not in sql
