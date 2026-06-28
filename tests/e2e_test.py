"""
E2E (End-to-End) 테스트: 실제 외부 API 와 함께 전체 워크플로우 실행 검증
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# src 디렉토리를 PATH 에 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from monitor_graph_v3 import (
    MonitorConfig, 
    AsyncMonitorGraphBuilder, 
    MonitorState,
    setup_logging
)


async def test_e2e_happy_path():
    """E2E 해피 경로 테스트: 모든 서비스가 정상인 경우"""
    print("\n" + "="*60)
    print("🧪 E2E 테스트 1: 해피 경로 (모든 서비스 정상)")
    print("="*60)
    
    # 테스트용 설정
    config = MonitorConfig(
        urls_to_check=[
            "https://httpbin.org/status/200",
            "https://httpbin.org/delay/1"
        ],
        temp_api_url="https://httpbin.org/json",
        max_retries=1,
        retry_delay_base=0.1,
        request_timeout=10,
        temp_timeout=5,
        log_level="INFO",
        state_file="/tmp/e2e_test_state_happy.json",
        enable_parallel=True
    )
    
    # 그래프 빌드
    builder = AsyncMonitorGraphBuilder(config)
    monitor_app = builder.build(use_checkpointer=False)
    
    # 초기 상태
    initial_state = {
        "urls_to_check": [],
        "web_check_results": [],
        "temp_check_result": None,
        "error_messages": [],
        "telegram_notifications": [],
        "retry_count": 0,
        "max_retries": config.max_retries,
        "last_error_time": None,
        "checkpoint_id": None
    }
    
    # 실행
    start_time = datetime.now()
    final_state = await monitor_app.ainvoke(initial_state)
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # 검증
    print(f"\n⏱️  실행 시간: {elapsed:.2f}초")
    print(f"📊 웹 체크 결과: {len(final_state['web_check_results'])}개")
    print(f"❌ 에러 수: {len(final_state['error_messages'])}개")
    print(f"🔄 재시도 횟수: {final_state['retry_count']}")
    
    # 검증 조건
    assert len(final_state['web_check_results']) == 2, "2 개 URL 모두 체크되어야 함"
    assert final_state['temp_check_result'] is not None, "온도 체크 결과가 있어야 함"
    assert final_state['retry_count'] == 0, "재시도가 없어야 함 (해피 경로)"
    
    # 상태 파일 저장 확인
    state_file = Path(config.state_file)
    assert state_file.exists(), f"상태 파일이 저장되어야 함: {state_file}"
    
    with open(state_file, 'r', encoding='utf-8') as f:
        saved_state = json.load(f)
    
    assert saved_state['web_check_results'][0]['status'] == 'OK', "첫 번째 URL 은 정상"
    
    print("✅ E2E 해피 경로 테스트 통과!")
    return True


async def test_e2e_with_failure_and_retry():
    """E2E 장애 및 재시도 테스트"""
    print("\n" + "="*60)
    print("🧪 E2E 테스트 2: 장애 발생 및 재시도")
    print("="*60)
    
    # 일부러 실패하는 URL 포함
    config = MonitorConfig(
        urls_to_check=[
            "https://httpbin.org/status/500",  # 의도적 에러
            "https://httpbin.org/status/200"   # 정상
        ],
        temp_api_url="https://httpbin.org/status/404",  # 의도적 에러
        max_retries=2,
        retry_delay_base=0.1,
        request_timeout=5,
        temp_timeout=3,
        log_level="INFO",
        state_file="/tmp/e2e_test_state_retry.json",
        enable_parallel=True
    )
    
    builder = AsyncMonitorGraphBuilder(config)
    monitor_app = builder.build(use_checkpointer=False)
    
    initial_state = {
        "urls_to_check": [],
        "web_check_results": [],
        "temp_check_result": None,
        "error_messages": [],
        "telegram_notifications": [],
        "retry_count": 0,
        "max_retries": config.max_retries,
        "last_error_time": None,
        "checkpoint_id": None
    }
    
    # 실행
    start_time = datetime.now()
    final_state = await monitor_app.ainvoke(initial_state)
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print(f"\n⏱️  실행 시간: {elapsed:.2f}초")
    print(f"📊 웹 체크 결과: {len(final_state['web_check_results'])}개")
    print(f"❌ 에러 수: {len(final_state['error_messages'])}개")
    print(f"🔄 재시도 횟수: {final_state['retry_count']}")
    
    # 검증
    assert len(final_state['web_check_results']) == 2, "2 개 URL 모두 체크되어야 함"
    assert final_state['retry_count'] == config.max_retries, f"최대 재시도 횟수 ({config.max_retries}) 까지 재시도해야 함"
    assert len(final_state['error_messages']) > 0, "에러가 기록되어야 함"
    
    print("✅ E2E 장애 및 재시도 테스트 통과!")
    return True


async def test_e2e_parallel_performance():
    """E2E 병렬 처리 성능 테스트"""
    print("\n" + "="*60)
    print("🧪 E2E 테스트 3: 병렬 처리 성능")
    print("="*60)
    
    # 여러 URL 로 부하 테스트
    urls = [f"https://httpbin.org/delay/{i % 2}" for i in range(5)]
    
    config = MonitorConfig(
        urls_to_check=urls,
        temp_api_url="https://httpbin.org/json",
        max_retries=1,
        retry_delay_base=0.1,
        request_timeout=10,
        temp_timeout=5,
        log_level="WARNING",
        state_file="/tmp/e2e_test_state_parallel.json",
        enable_parallel=True,
        parallel_max_concurrent=10
    )
    
    builder = AsyncMonitorGraphBuilder(config)
    monitor_app = builder.build(use_checkpointer=False)
    
    initial_state = {
        "urls_to_check": [],
        "web_check_results": [],
        "temp_check_result": None,
        "error_messages": [],
        "telegram_notifications": [],
        "retry_count": 0,
        "max_retries": config.max_retries,
        "last_error_time": None,
        "checkpoint_id": None
    }
    
    # 병렬 실행 측정
    start_time = datetime.now()
    final_state = await monitor_app.ainvoke(initial_state)
    elapsed_parallel = (datetime.now() - start_time).total_seconds()
    
    print(f"\n⏱️  병렬 실행 시간: {elapsed_parallel:.2f}초")
    print(f"📊 체크한 URL 수: {len(final_state['web_check_results'])}개")
    
    # 순차 실행과의 비교 (예상)
    expected_sequential = sum([1 if i % 2 == 0 else 2 for i in range(5)])  # 대략 7-8 초
    speedup = expected_sequential / elapsed_parallel if elapsed_parallel > 0 else float('inf')
    
    print(f"📈 예상 순차 실행 시간: ~{expected_sequential}초")
    print(f"🚀 성능 향상: {speedup:.1f}x")
    
    assert len(final_state['web_check_results']) == 5, "5 개 URL 모두 체크되어야 함"
    assert elapsed_parallel < 6.0, f"병렬 실행으로 6 초 이내에 완료되어야 함 (실제: {elapsed_parallel:.2f}초)"
    
    print("✅ E2E 병렬 처리 성능 테스트 통과!")
    return True


async def test_e2e_state_persistence():
    """E2E 상태 지속성 테스트"""
    print("\n" + "="*60)
    print("🧪 E2E 테스트 4: 상태 지속성")
    print("="*60)
    
    config = MonitorConfig(
        urls_to_check=["https://httpbin.org/status/200"],
        temp_api_url="https://httpbin.org/json",
        max_retries=0,
        retry_delay_base=0.1,
        request_timeout=5,
        temp_timeout=3,
        log_level="WARNING",
        state_file="/tmp/e2e_test_state_persist.json",
        enable_parallel=False
    )
    
    builder = AsyncMonitorGraphBuilder(config)
    monitor_app = builder.build(use_checkpointer=False)
    
    initial_state = {
        "urls_to_check": [],
        "web_check_results": [],
        "temp_check_result": None,
        "error_messages": [],
        "telegram_notifications": [],
        "retry_count": 0,
        "max_retries": config.max_retries,
        "last_error_time": None,
        "checkpoint_id": None
    }
    
    # 실행
    final_state = await monitor_app.ainvoke(initial_state)
    
    # 파일에서 읽기
    state_file = Path(config.state_file)
    with open(state_file, 'r', encoding='utf-8') as f:
        saved_state = json.load(f)
    
    # 검증
    print(f"\n📄 상태 파일: {state_file}")
    print(f"💾 저장된 데이터 키: {list(saved_state.keys())}")
    
    assert saved_state['current_time'] is not None, "타임스탬프가 저장되어야 함"
    assert len(saved_state['web_check_results']) > 0, "웹 체크 결과가 저장되어야 함"
    assert saved_state['web_check_results'][0]['url'] == "https://httpbin.org/status/200", "URL 이 정확해야 함"
    assert 'CpuInfo' in str(saved_state.get('temp_check_result', '')) or saved_state.get('temp_check_result') is not None, "온도 데이터가 저장되어야 함"
    
    # JSON 직렬화 가능성 확인
    json_str = json.dumps(saved_state, ensure_ascii=False)
    assert len(json_str) > 0, "JSON 으로 직렬화 가능해야 함"
    
    print("✅ E2E 상태 지속성 테스트 통과!")
    return True


async def main():
    """모든 E2E 테스트 실행"""
    print("\n" + "🚀"*30)
    print("🧪 LangGraph 모니터링 시스템 E2E 테스트 스위트")
    print("🚀"*30)
    
    results = []
    
    # 테스트 1: 해피 경로
    try:
        result = await test_e2e_happy_path()
        results.append(("해피 경로", result))
    except Exception as e:
        print(f"❌ 해피 경로 테스트 실패: {e}")
        results.append(("해피 경로", False))
    
    # 테스트 2: 장애 및 재시도
    try:
        result = await test_e2e_with_failure_and_retry()
        results.append(("장애 및 재시도", result))
    except Exception as e:
        print(f"❌ 장애 및 재시도 테스트 실패: {e}")
        results.append(("장애 및 재시도", False))
    
    # 테스트 3: 병렬 성능
    try:
        result = await test_e2e_parallel_performance()
        results.append(("병렬 성능", result))
    except Exception as e:
        print(f"❌ 병렬 성능 테스트 실패: {e}")
        results.append(("병렬 성능", False))
    
    # 테스트 4: 상태 지속성
    try:
        result = await test_e2e_state_persistence()
        results.append(("상태 지속성", result))
    except Exception as e:
        print(f"❌ 상태 지속성 테스트 실패: {e}")
        results.append(("상태 지속성", False))
    
    # 요약
    print("\n" + "="*60)
    print("📊 E2E 테스트 결과 요약")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ 통과" if result else "❌ 실패"
        print(f"  {name}: {status}")
    
    print(f"\n📈 총점: {passed}/{total} ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n🎉 모든 E2E 테스트가 성공했습니다!")
        return 0
    else:
        print(f"\n⚠️  {total - passed}개의 테스트가 실패했습니다.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
