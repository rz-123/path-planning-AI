"""测试: api/v1/destinations.py — 目的地推荐 API"""


class TestGetHot:

    def test_returns_20_destinations(self):
        """热门目的地应返回 20 个"""
        from api.v1.destinations import get_hot
        import asyncio
        result = asyncio.run(get_hot())
        items = result["items"]
        assert len(items) == 20
        assert items[0]["name"] == "北京"
        assert items[0]["id"] == "beijing"

    def test_each_destination_has_required_fields(self):
        """每个目的地应有完整字段"""
        from api.v1.destinations import get_hot
        import asyncio
        result = asyncio.run(get_hot())
        for item in result["items"]:
            assert all(k in item for k in ("id", "name", "tags", "image", "description", "basePrice"))

    def test_base_price_is_number(self):
        """basePrice 应为数字"""
        from api.v1.destinations import get_hot
        import asyncio
        result = asyncio.run(get_hot())
        for item in result["items"]:
            assert isinstance(item["basePrice"], (int, float))


class TestGetRandom:

    def test_returns_single_destination(self):
        """随机推荐应返回单个目的地的详细信息"""
        from api.v1.destinations import get_random
        import asyncio
        result = asyncio.run(get_random())
        assert "name" in result
        assert "id" in result
        assert "tags" in result
        assert "description" in result

    def test_random_in_hot_list(self):
        """随机推荐的目的地应在 HOT_DESTINATIONS 中"""
        from api.v1.destinations import get_random, HOT_DESTINATIONS
        import asyncio
        result = asyncio.run(get_random())
        ids = [d.id for d in HOT_DESTINATIONS]
        assert result["id"] in ids
