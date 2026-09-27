"""测试: agents/tools.py — 工具函数"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestAmapMCP:

    def test_no_key_returns_error(self):
        """高德 Key 未配置 → 返回 error JSON"""
        from agents.tools import _amap_mcp
        result = _amap_mcp("maps_weather", city="北京")
        data = json.loads(result)
        assert "error" in data

    def test_integration_session(self):
        """配置 Key 后尝试完整 MCP 流程"""
        import config
        config.settings.amap_key = "test_key"

        from agents.tools import _amap_mcp
        with patch("httpx.post") as mock_post:
            # 模拟初始化响应
            mock_init_resp = MagicMock()
            mock_init_resp.headers = {"mcp-session-id": "sess_123"}
            mock_init_resp.json.return_value = {}

            # 模拟工具调用响应
            mock_tool_resp = MagicMock()
            mock_tool_resp.json.return_value = {
                "result": {
                    "content": [
                        {"type": "text", "text": '{"city":"北京","weather":"晴"}'}
                    ]
                }
            }

            mock_post.side_effect = [mock_init_resp, mock_init_resp, mock_tool_resp]

            result = _amap_mcp("maps_weather", city="北京")
            data = json.loads(result)
            assert "weather" in data


class TestGetWeather:

    def test_no_amap_key_returns_seasonal_fallback(self):
        """高德未配置 → 用往年平均数据补全预报"""
        from agents.tools import get_weather
        result = get_weather("北京")
        assert result["city"] == "北京"
        # live 总是有格式化后的键
        assert "weather" in result["live"]
        # 预报天数不足时用往年数据补全
        assert len(result["forecast"]) == 3

    def test_with_amap_key(self):
        """配置 Key 后解析正常"""
        import config
        config.settings.amap_key = "test_key"

        from agents.tools import get_weather
        with patch("agents.tools._amap_mcp") as mock_mcp:
            mock_mcp.return_value = json.dumps({
                "lives": [{"city": "北京", "weather": "晴", "temperature": "25",
                           "winddirection": "南风", "windpower": "4", "humidity": "45"}],
                "forecasts": [{
                    "casts": [
                        {"date": "2025-06-01", "dayweather": "晴", "nightweather": "晴",
                         "daytemp": "32", "nighttemp": "18", "daywind": "南风", "daypower": "3"},
                        {"date": "2025-06-02", "dayweather": "多云", "nightweather": "阴",
                         "daytemp": "30", "nighttemp": "20", "daywind": "南风", "daypower": "3"},
                        {"date": "2025-06-03", "dayweather": "小雨", "nightweather": "中雨",
                         "daytemp": "28", "nighttemp": "22", "daywind": "东风", "daypower": "2"},
                    ]
                }]
            }, ensure_ascii=False)

            result = get_weather("北京", days=3)
            assert result["live"]["weather"] == "晴"
            assert len(result["forecast"]) == 3

    def test_weather_various_forecast_formats(self):
        """兼容 forecasts 为 dict 的格式"""
        from agents.tools import get_weather
        from config import settings

        with patch.object(settings, "amap_key", "test_key"):
            with patch("agents.tools._amap_mcp") as mock_mcp:
                mock_mcp.return_value = json.dumps({
                    "lives": [{"city": "北京", "weather": "多云"}],
                    "forecasts": {
                        "casts": [
                            {"date": "2025-06-01", "dayweather": "多云", "nightweather": "晴",
                             "daytemp": "28", "nighttemp": "20"}
                        ]
                    }
                }, ensure_ascii=False)

                result = get_weather("北京")
                assert len(result["forecast"]) >= 1


class TestSeasonalAvg:

    def test_summer(self):
        """夏季 → 返回夏季气候数据"""
        from agents.tools import _seasonal_avg
        result = _seasonal_avg("北京", 4, 6, "2025-06-01")
        assert len(result) == 3  # day4~day6
        for r in result:
            assert r["isHistorical"] is True
            assert "北京6月" in r["note"]

    def test_winter(self):
        """冬季 → 返回冬季气候数据"""
        from agents.tools import _seasonal_avg
        result = _seasonal_avg("北京", 4, 5, "2025-01-01")
        assert len(result) == 2
        assert "北京1月" in result[0]["note"]

    def test_unknown_city_falls_back_to_default(self):
        """未收录的城市 → 使用默认数据"""
        from agents.tools import _seasonal_avg
        result = _seasonal_avg("未知城市", 4, 4, "2025-06-01")
        assert len(result) == 1
        assert result[0]["dayTemp"]  # 应有温度值


class TestGetMonth:

    def test_iso_format(self):
        """"2025-06-01" → 6"""
        from agents.tools import _get_month
        assert _get_month("2025-06-01") == 6

    def test_dot_format(self):
        """"2025.06.01" → 6"""
        from agents.tools import _get_month
        assert _get_month("2025.06.01") == 6

    def test_empty_returns_current(self):
        """空字符串 → 当前月份"""
        from agents.tools import _get_month
        from datetime import datetime
        assert _get_month("") == datetime.now().month

    def test_december(self):
        """"2025-12-25" → 12"""
        from agents.tools import _get_month
        assert _get_month("2025-12-25") == 12


class TestGeocode:

    def test_success(self):
        """地理编码成功 → 返回经纬度"""
        from agents.tools import geocode
        from config import settings

        with patch.object(settings, "amap_key", "test_key"):
            with patch("agents.tools._amap_mcp") as mock_mcp:
                mock_mcp.return_value = json.dumps({
                    "results": [{"location": "120.15,30.25"}]
                })
                result = geocode("杭州西湖")
                assert result["longitude"] == 120.15
                assert result["latitude"] == 30.25

    def test_geocodes_format(self):
        """兼容 geocodes 格式"""
        from agents.tools import geocode
        from config import settings

        with patch.object(settings, "amap_key", "test_key"):
            with patch("agents.tools._amap_mcp") as mock_mcp:
                mock_mcp.return_value = json.dumps({
                    "geocodes": [{"location": "116.40,39.90"}]
                })
                result = geocode("北京天安门")
                assert result["longitude"] == 116.40
                assert result["latitude"] == 39.90

    def test_location_format(self):
        """兼容直接 location 格式"""
        from agents.tools import geocode
        from config import settings

        with patch.object(settings, "amap_key", "test_key"):
            with patch("agents.tools._amap_mcp") as mock_mcp:
                mock_mcp.return_value = json.dumps({
                    "location": "121.47,31.23"
                })
                result = geocode("上海外滩")
                assert result["longitude"] == 121.47
                assert result["latitude"] == 31.23

    def test_failure_returns_empty(self):
        """失败时返回空字典"""
        from agents.tools import geocode
        from config import settings

        with patch.object(settings, "amap_key", "test_key"):
            with patch("agents.tools._amap_mcp") as mock_mcp:
                mock_mcp.return_value = "invalid json"
                result = geocode("不存在的地址")
                assert result == {}

