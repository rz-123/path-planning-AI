"""测试: config.py — Settings + LLM 工厂"""

import pytest
from unittest.mock import patch


class TestSettings:

    def test_default_name(self):
        """默认 app_name 应为 'AI旅行规划 API'"""
        from config import settings
        assert settings.app_name == "AI旅行规划 API"

    def test_default_debug(self):
        from config import settings
        assert settings.debug is True

    def test_database_url_contains_sqlite(self):
        from config import settings
        assert "sqlite" in settings.database_url


class TestGetLLM:

    def test_get_llm_deepseek(self):
        """deepseek provider → 返回 ChatOpenAI 实例 + 参数正确"""
        from config import get_llm
        llm = get_llm()
        from langchain_openai import ChatOpenAI
        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "deepseek-v3-0324"

    def test_get_llm_openai(self):
        """openai provider → 返回 ChatOpenAI 实例"""
        from config import settings, get_llm
        with patch.object(settings, "llm_provider", "openai"):
            llm = get_llm()
            from langchain_openai import ChatOpenAI
            assert isinstance(llm, ChatOpenAI)

    def test_get_llm_hunyuan(self):
        """hunyuan provider → 返回 ChatOpenAI"""
        from config import settings, get_llm
        with patch.object(settings, "llm_provider", "hunyuan"):
            llm = get_llm()
            from langchain_openai import ChatOpenAI
            assert isinstance(llm, ChatOpenAI)

    def test_get_llm_zhipu(self):
        """zhipu provider → 返回 ChatOpenAI"""
        from config import settings, get_llm
        with patch.object(settings, "llm_provider", "zhipu"):
            llm = get_llm()
            from langchain_openai import ChatOpenAI
            assert isinstance(llm, ChatOpenAI)

    def test_get_llm_unsupported_provider(self):
        """不支持的 provider → ValueError"""
        from config import settings, get_llm
        with patch.object(settings, "llm_provider", "unknown"):
            with pytest.raises(ValueError, match="不支持的 LLM provider"):
                get_llm()


class TestGetLLMStructured:

    def test_temperature_is_lower(self):
        """get_llm_structured 的 temperature 应为 0.3"""
        from config import get_llm_structured
        llm = get_llm_structured()
        assert llm.temperature == 0.3
