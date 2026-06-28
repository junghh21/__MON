"""
E2E Final Test Suite - LangGraph 모니터링 시스템 최종 검증
실제 브라우저 환경 (httpbin.org) 에서 전체 워크플로우 실행
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from monitor_graph_v3 import MonitorConfig, AsyncMonitorGraphBuilder


async def test_1_happy_path():
    """테스트 1: 해피 경로 - 모든 서비스 정상"""
    print("\n" + "="*70)
    print("🧪 TEST 1: 해피 경로 (모든 서비스 정상)")
    print("="*70)
    
    config = MonitorConfig(
        urls_to_check=["https://httpbin.org/status/200"],
        temp_api_url="https://httpbin.org/json",
        max_retries=0,
        retry_delay_base=0.1,
        request_timeout=10,
        log_level="WARNING",
        state_file="/tmp/e2e_final_happy.json",
        enable_parallel=True
    )
    
    builder = AsyncMonitorGraphBuilder(config)
    app = builder.build(use_checkpointer=False)
    
    start = datetime.now()
    final_state = await app.ainvoke({
        "urls_to_check": [], "web_check_results": [], "temp_check_result": None,
        "error_messages": [], "telegram_notifications": [], "retry_count": 0,
        "max_retries": 0, "last_error_time": None, "checkpoint_id": None
    })
    elapsed = (datetime.now() - start).total_seconds()
    
    # 검증
    assert len(final_state['web_check_results']) >= 1, "웹 체크 결과가 있어야 함"
    assert final_state['temp_check_result'] is not None, "온도 데이터가 있어야 함"
    assert final_state['retry_count'] == 0, "재시도가 없어야 함"
    
    print(f"⏱️  실행 시간: {elapsed:.2f}초")
    print(f"✅ 웹 체크: {len(final_state['web_check_results'])}개 URL")
    print(f"✅ 온도 체크: 성공")
    print(f"✅ 재시도: {final_state['retry_count']}회")
    print("✅ TEST 1 PASSED")
    return True


async def test_2_retry_logic():
    """테스트 2: 장애 발생 및 재시도 로직"""
    print("\n" + "="*70)
    print("🧪 TEST 2: 장애 발생 및 재시도")
    print("="*70)
    
    config = MonitorConfig(
        urls_to_check=["https://httpbin.org/status/500"],
        temp_api_url="https://httpbin.org/status/404",
        max_retries=2,
        retry_delay_base=0.1,
        request_timeout=5,
        log_level="WARNING",
        state_file="/tmp/e2e_final_retry.json",
        enable_parallel=True
    )
    
    builder = AsyncMonitorGraphBuilder(config)
    app = builder.build(use_checkpointer=False)
    
    start = datetime.now()
    final_state = await app.ainvoke({
        "urls_to_check": [], "web_check_results": [], "temp_check_result": None,
        "error_messages": [], "telegram_notifications": [], "retry_count": 0,
        "max_retries": 2, "last_error_time": None, "checkpoint_id": None
    })
    elapsed = (datetime.now() - start).total_seconds()
    
    # 검증
    assert final_state['retry_count'] == 2, f"재시도 2 회 해야 함 (실제: {final_state['retry_count']})"
    assert len(final_state['error_messages']) > 0, "에러가 기록되어야 함"
    
    print(f"⏱️  실행 시간: {elapsed:.2f}초")
    print(f"✅ 재시도: {final_state['retry_count']}회 (예상: 2)")
    print(f"✅ 에러 기록: {len(final_state['error_messages'])}개")
    print("✅ TEST 2 PASSED")
    return True


async def test_3_parallel_performance():
    """테스트 3: 병렬 처리 성능"""
    print("\n" + "="*70)
    print("🧪 TEST 3: 병렬 처리 성능")
    print("="*70)
    
    urls = ["https://httpbin.org/delay/0.3" for _ in range(3)]
    
    config = MonitorConfig(
        urls_to_check=urls,
        temp_api_url="https://httpbin.org/json",
        max_retries=0,
        retry_delay_base=0.1,
        request_timeout=10,
        log_level="WARNING",
        state_file="/tmp/e2e_final_parallel.json",
        enable_parallel=True,
        parallel_max_concurrent=10
    )
    
    builder = AsyncMonitorGraphBuilder(config)
    app = builder.build(use_checkpointer=False)
    
    start = datetime.now()
    final_state = await app.ainvoke({
        "urls_to_check": [], "web_check_results": [], "temp_check_result": None,
        "error_messages": [], "telegram_notifications": [], "retry_count": 0,
        "max_retries": 0, "last_error_time": None, "checkpoint_id": None
    })
    elapsed = (datetime.now() - start).total_seconds()
    
    # 병렬 실행이면 3 초 이내 (네트워크 지연 고려)
    assert len(final_state['web_check_results']) >= 3, f"3 개 URL 이상 체크 필요 (실제: {len(final_state['web_check_results'])})"
    assert elapsed < 3.5, f"병렬 실행으로 3.5 초 이내 완료 (실제: {elapsed:.2f}초)"
    
    print(f"⏱️  실행 시간: {elapsed:.2f}초")
    print(f"✅ 처리 URL: {len(final_state['web_check_results'])}개")
    print(f"✅ 병렬 효율: {'좋음' if elapsed < 1.0 else '보통'}")
    print("✅ TEST 3 PASSED")
    return True


async def test_4_state_persistence():
    """테스트 4: 상태 지속성"""
    print("\n" + "="*70)
    print("🧪 TEST 4: 상태 지속성 (JSON 저장)")
    print("="*70)
    
    config = MonitorConfig(
        urls_to_check=["https://httpbin.org/status/200"],
        temp_api_url="https://httpbin.org/json",
        max_retries=0,
        log_level="WARNING",
        state_file="/tmp/e2e_final_persist.json"
    )
    
    builder = AsyncMonitorGraphBuilder(config)
    app = builder.build(use_checkpointer=False)
    
    final_state = await app.ainvoke({
        "urls_to_check": [], "web_check_results": [], "temp_check_result": None,
        "error_messages": [], "telegram_notifications": [], "retry_count": 0,
        "max_retries": 0, "last_error_time": None, "checkpoint_id": None
    })
    
    # 파일 확인
    state_file = Path(config.state_file)
    assert state_file.exists(), f"상태 파일 생성 필요: {state_file}"
    
    with open(state_file, 'r', encoding='utf-8') as f:
        saved = json.load(f)
    
    assert saved['current_time'] is not None, "타임스탬프 저장"
    assert len(saved['web_check_results']) > 0, "웹 결과 저장"
    assert saved['temp_check_result'] is not None, "온도 데이터 저장"
    
    print(f"📄 상태 파일: {state_file}")
    print(f"💾 저장된 키: {list(saved.keys())}")
    print("✅ TEST 4 PASSED")
    return True


async def test_5_graceful_degradation():
    """테스트 5: Graceful Degradation - 네트워크 에러 처리"""
    print("\n" + "="*70)
    print("🧪 TEST 5: Graceful Degradation (네트워크 에러 처리)")
    print("="*70)
    
    config = MonitorConfig(
        urls_to_check=["https://invalid-domain-that-does-not-exist.example"],
        temp_api_url="https://invalid-domain-that-does-not-exist.example/api",
        max_retries=1,
        retry_delay_base=0.1,
        request_timeout=2,
        log_level="WARNING",
        state_file="/tmp/e2e_final_graceful.json"
    )
    
    builder = AsyncMonitorGraphBuilder(config)
    app = builder.build(use_checkpointer=False)
    
    start = datetime.now()
    final_state = await app.ainvoke({
        "urls_to_check": [], "web_check_results": [], "temp_check_result": None,
        "error_messages": [], "telegram_notifications": [], "retry_count": 0,
        "max_retries": 1, "last_error_time": None, "checkpoint_id": None
    })
    elapsed = (datetime.now() - start).total_seconds()
    
    # 시스템이 crash 하지 않고 정상 종료되어야 함
    assert final_state['retry_count'] <= 1, "최대 재시도 초과 금지"
    assert len(final_state['error_messages']) > 0, "에러 기록 있어야 함"
    
    print(f"⏱️  실행 시간: {elapsed:.2f}초")
    print(f"✅ 시스템 안정성: 유지됨")
    print(f"✅ 에러 처리: {len(final_state['error_messages'])}개 기록")
    print("✅ TEST 5 PASSED")
    return True


async def main():
    """전체 E2E 테스트 실행"""
    print("\n" + "🚀"*35)
    print("🧪 LangGraph 모니터링 시스템 E2E FINAL TEST")
    print("🚀"*35)
    
    tests = [
        ("해피 경로", test_1_happy_path),
        ("장애 및 재시도", test_2_retry_logic),
        ("병렬 성능", test_3_parallel_performance),
        ("상태 지속성", test_4_state_persistence),
        ("Graceful Degradation", test_5_graceful_degradation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, True))
        except Exception as e:
            print(f"\n❌ {name} FAILED: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 요약
    print("\n" + "="*70)
    print("📊 E2E FINAL TEST RESULTS")
    print("="*70)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {name}")
    
    print(f"\n📈 SUMMARY: {passed}/{total} ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n🎉 ALL E2E TESTS PASSED!")
        print("✅ 프로덕션 배포 준비 완료")
        return 0
    else:
        print(f"\n⚠️  {total - passed} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
