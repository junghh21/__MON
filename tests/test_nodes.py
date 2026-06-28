"""
LangGraph 모니터링 시스템 단위 테스트
"""

import pytest
from datetime import datetime
from src.monitor_graph_v3 import MonitorConfig, MonitorState, AsyncMonitorNodes
import logging


@pytest.fixture
def test_config():
    """테스트용 설정"""
    return MonitorConfig(
        urls_to_check=["https://httpbin.org/status/200"],
        temp_api_url="https://httpbin.org/json",
        max_retries=2,
        request_timeout=5,
        log_level="DEBUG"
    )


@pytest.fixture
def test_logger():
    """테스트용 로거"""
    logger = logging.getLogger("test_monitor")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    return logger


@pytest.fixture
def monitor_nodes(test_config, test_logger):
    """모니터 노드 인스턴스"""
    return AsyncMonitorNodes(test_config, test_logger)


@pytest.fixture
def sample_state():
    """샘플 상태"""
    return {
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {},
        "urls_to_check": ["https://httpbin.org/status/200"],
        "web_check_results": [],
        "temp_check_result": None,
        "error_messages": [],
        "telegram_notifications": [],
        "retry_count": 0,
        "max_retries": 3,
        "last_error_time": None,
        "checkpoint_id": None
    }


class TestMonitorConfig:
    """설정 클래스 테스트"""
    
    def test_default_config(self):
        """기본 설정 테스트"""
        config = MonitorConfig()
        assert len(config.urls_to_check) == 2
        assert config.max_retries == 3
        assert config.request_timeout == 10
    
    def test_custom_config(self):
        """커스텀 설정 테스트"""
        config = MonitorConfig(
            urls_to_check=["https://example.com"],
            max_retries=5
        )
        assert config.urls_to_check == ["https://example.com"]
        assert config.max_retries == 5


class TestInitializeState:
    """초기화 노드 테스트"""
    
    @pytest.mark.asyncio
    async def test_initialize_state(self, monitor_nodes, sample_state):
        """상태 초기화 테스트"""
        result = await monitor_nodes.initialize_state(sample_state)
        
        assert "current_time" in result
        assert result["urls_to_check"] is not None
        assert result["web_check_results"] == []
        assert result["retry_count"] == 0
        assert result["max_retries"] == 2


class TestShouldRetry:
    """재시도 로직 테스트"""
    
    def test_should_retry_with_errors(self, monitor_nodes):
        """에러 발생 시 재시도"""
        state = {
            "error_messages": ["Error 1"],
            "retry_count": 0,
            "max_retries": 3
        }
        result = monitor_nodes.should_retry(state)
        assert result == "retry"
    
    def test_should_not_retry_max_exceeded(self, monitor_nodes):
        """최대 재시도 초과"""
        state = {
            "error_messages": ["Error 1"],
            "retry_count": 3,
            "max_retries": 3
        }
        result = monitor_nodes.should_retry(state)
        assert result == "complete"
    
    def test_should_not_retry_no_errors(self, monitor_nodes):
        """에러 없음"""
        state = {
            "error_messages": [],
            "retry_count": 0,
            "max_retries": 3
        }
        result = monitor_nodes.should_retry(state)
        assert result == "complete"


class TestIncrementRetry:
    """재시도 카운트 테스트"""
    
    @pytest.mark.asyncio
    async def test_increment_retry(self, monitor_nodes, sample_state):
        """재시도 카운트 증가"""
        sample_state["retry_count"] = 1
        result = await monitor_nodes.increment_retry(sample_state)
        
        assert result["retry_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
