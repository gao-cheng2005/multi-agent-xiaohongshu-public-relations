def test_import_schemas():
    from app_v2.models import schemas
    assert schemas.CollectRequest is not None
