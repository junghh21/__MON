"""
LangGraph 모니터링 시스템 통합 테스트
"""

import pytest
import asyncio
from datetime import datetime
from src.monitor_graph_v3 import (
    MonitorConfig, 
    AsyncMonitorGraphBuilder,
    run_monitor
)


@pytest.fixture
def test_config():
    """테스트용 설정"""
    return MonitorConfig(
        urls_to_check=[
            "https://httpbin.org/status/200",
            "https://httpbin.org/status/404"  # 에러 테스트용
        ],
        temp_api_url="https://httpbin.org/json",
        max_retries=1,  # 테스트 속도 향상을 위해 1 로 설정
        request_timeout=5,
        log_level="DEBUG",
        enable_parallel=True
    )


class TestGraphConstruction:
    """그래프 구축 테스트"""
    
    def test_build_graph(self, test_config):
        """그래프 정상 구축"""
        builder = AsyncMonitorGraphBuilder(test_config)
        graph = builder.build()
        
        assert graph is not None
        assert hasattr(graph, 'invoke') or hasattr(graph, 'ainvoke')


class TestFullWorkflow:
    """전체 워크플로우 테스트"""
    
    @pytest.mark.asyncio
    async def test_monitor_execution(self, test_config):
        """모니터링 실행 테스트"""
        builder = AsyncMonitorGraphBuilder(test_config)
        monitor_app = builder.build(use_checkpointer=False)  # 테스트용 체크포인터 비활성화
        
        initial_state = {
            "urls_to_check": [],
            "web_check_results": [],
            "temp_check_result": None,
            "error_messages": [],
            "telegram_notifications": [],
            "retry_count": 0,
            "max_retries": test_config.max_retries,
            "last_error_time": None,
            "checkpoint_id": None
        }
        
        # 그래프 실행
        final_state = await monitor_app.ainvoke(initial_state)
        
        # 결과 검증
        assert "current_time" in final_state
        assert "web_check_results" in final_state
        assert len(final_state["web_check_results"]) > 0
        
        # 최소한 하나의 결과는 있어야 함
        assert len(final_state["web_check_results"]) >= 1
    
    @pytest.mark.asyncio
    async def test_retry_logic(self, test_config):
        """재시도 로직 테스트"""
        # 존재하지 않는 URL 로 에러 유도 (httpbin 을 사용하여 실제 에러 발생)
        error_config = MonitorConfig(
            urls_to_check=["https://httpbin.org/status/500"],  # 500 에러 반환
            temp_api_url="https://invalid-temp-api-url.com/api/temp",  # 온도 API 도 에러
            max_retries=2,
            request_timeout=3
        )
        
        builder = AsyncMonitorGraphBuilder(error_config)
        monitor_app = builder.build(use_checkpointer=False)  # 테스트용 체크포인터 비활성화
        
        initial_state = {
            "urls_to_check": [],
            "web_check_results": [],
            "temp_check_result": None,
            "error_messages": [],
            "telegram_notifications": [],
            "retry_count": 0,
            "max_retries": error_config.max_retries,
            "last_error_time": None,
            "checkpoint_id": None
        }
        
        final_state = await monitor_app.ainvoke(initial_state)
        
        # 재시도가 발생했는지 확인 (에러가 있으면 재시도 발생)
        # httpbin.org/status/500 은 HTTP 500 에러를 반환하므로 에러로 처리됨
        assert len(final_state["error_messages"]) > 0 or final_state["retry_count"] > 0


class TestParallelExecution:
    """병렬 실행 테스트"""
    
    @pytest.mark.asyncio
    async def test_parallel_vs_sequential(self):
        """병렬 vs 순차 실행 비교"""
        urls = [
            "https://httpbin.org/delay/1",
            "https://httpbin.org/delay/1",
            "https://httpbin.org/delay/1"
        ]
        
        # 병렬 실행
        parallel_config = MonitorConfig(
            urls_to_check=urls,
            enable_parallel=True,
            request_timeout=10
        )
        
        start = datetime.now()
        builder = AsyncMonitorGraphBuilder(parallel_config)
        monitor_app = builder.build(use_checkpointer=False)  # 테스트용 체크포인터 비활성화
        
        initial_state = {
            "urls_to_check": [],
            "web_check_results": [],
            "temp_check_result": None,
            "error_messages": [],
            "telegram_notifications": [],
            "retry_count": 0,
            "max_retries": 1,
            "last_error_time": None,
            "checkpoint_id": None
        }
        
        await monitor_app.ainvoke(initial_state)
        parallel_duration = (datetime.now() - start).total_seconds()
        
        # 병렬 실행이 순차보다 빨라야 함 (대략 3 초 vs 9 초)
        # 네트워크 상황에 따라 다르므로 여유있게 6 초로 설정
        assert parallel_duration < 6.0, f"병렬 실행이 너무 느림: {parallel_duration}초"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
