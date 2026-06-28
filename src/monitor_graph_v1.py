"""
LangGraph 기반 모니터링 시스템 구조 변경 - 1차 리뷰

변경 사항:
1. 기존 schedule 기반을 LangGraph 상태 머신으로 전환
2. 각 모니터링 작업을 독립적인 노드로 분리
3. 에러 처리와 재시도 로직을 그래프 흐름에 통합
4. Telegram 알림을 전용 노드로 분리

개선 필요 사항 (1차 리뷰):
- [ ] 환경 변수로 기밀 정보 관리 필요 (bot_token, chat_id)
- [ ] 로깅 시스템 도입 필요 (print 대신 logging 사용)
- [ ] 비동기 처리 미지원 (httpx 사용 고려)
- [ ] 테스트 코드 부재
- [ ] 상태 관리의 지속성 없음 (DB 연동 필요)
"""

from typing import TypedDict, Annotated, List, Optional
from datetime import datetime
import operator


# ==================== State Definition ====================
class MonitorState(TypedDict):
    """모니터링 시스템의 상태 정의"""
    current_time: str
    urls_to_check: List[str]
    web_check_results: List[dict]
    temp_check_result: Optional[dict]
    error_messages: Annotated[List[str], operator.add]
    telegram_notifications: Annotated[List[str], operator.add]
    retry_count: int
    max_retries: int


# ==================== Node Functions ====================
def initialize_state(state: MonitorState) -> MonitorState:
    """초기 상태 설정 노드"""
    return {
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "urls_to_check": [
            "https://www.okkjc.co.kr:5001",
            "https://www.okkjc.co.kr:5002"
        ],
        "web_check_results": [],
        "temp_check_result": None,
        "error_messages": [],
        "telegram_notifications": [],
        "retry_count": 0,
        "max_retries": 3
    }


def check_web_health(state: MonitorState) -> MonitorState:
    """웹사이트 건강 상태 확인 노드"""
    import requests
    
    results = []
    notifications = []
    errors = []
    
    for url in state["urls_to_check"]:
        try:
            response = requests.get(url, verify=False, timeout=10)
            if response.status_code == 200:
                result = {"url": url, "status": "OK", "status_code": 200}
                notification = f"✅ 웹사이트 {url} 정상 접속"
            else:
                result = {"url": url, "status": "ERROR", "status_code": response.status_code}
                notification = f"❌ 웹사이트 {url} 접속 실패 (상태 코드: {response.status_code})"
                errors.append(f"웹사이트 {url} 접속 실패")
            
            results.append(result)
            notifications.append(notification)
            
        except requests.exceptions.RequestException as e:
            result = {"url": url, "status": "ERROR", "error": str(e)}
            notification = f"❌ 웹사이트 {url} 오류: {str(e)}"
            errors.append(f"웹사이트 {url} 오류: {str(e)}")
            results.append(result)
            notifications.append(notification)
    
    return {
        "web_check_results": results,
        "telegram_notifications": notifications,
        "error_messages": errors
    }


def check_temperature(state: MonitorState) -> MonitorState:
    """시스템 온도 및 리소스 확인 노드"""
    import requests
    
    url = "https://www.okkjc.co.kr:5001/api/temp"
    notifications = []
    errors = []
    temp_result = None
    
    try:
        response = requests.get(url, timeout=5, verify=False)
        response.raise_for_status()
        data = response.json()
        
        # 데이터 정제
        data['CpuInfo']['fTemp'] = [int(a) for a in data['CpuInfo']['fTemp']]
        temp_result = data
        
        # 포맷팅된 알림 생성
        temp_str = str(data['CpuInfo']['fTemp'])
        load_str = str(data['CpuInfo']['uiLoad'])
        mem_str = data['MemoryInfo']['MemoryLoad']
        
        notification = (
            f"🌡️ 시스템 상태\n"
            f"온도: {temp_str}\n"
            f"CPU 사용량: {load_str}\n"
            f"메모리 사용량: {mem_str}"
        )
        notifications.append(notification)
        
    except requests.exceptions.HTTPError as err:
        error_msg = f"HTTP 오류: {err}"
        errors.append(error_msg)
        notifications.append(f"❌ {error_msg}")
    except requests.exceptions.ConnectionError as err:
        error_msg = f"연결 오류: {err}"
        errors.append(error_msg)
        notifications.append(f"❌ {error_msg}")
    except requests.exceptions.Timeout as err:
        error_msg = f"타임아웃: {err}"
        errors.append(error_msg)
        notifications.append(f"❌ {error_msg}")
    except requests.exceptions.RequestException as err:
        error_msg = f"요청 오류: {err}"
        errors.append(error_msg)
        notifications.append(f"❌ {error_msg}")
    except Exception as err:
        error_msg = f"예기치 않은 오류: {err}"
        errors.append(error_msg)
        notifications.append(f"❌ {error_msg}")
    
    return {
        "temp_check_result": temp_result,
        "telegram_notifications": notifications,
        "error_messages": errors
    }


def send_telegram_notifications(state: MonitorState) -> MonitorState:
    """Telegram 알림 발송 노드"""
    from __COMMON.globals import bot_token, chat_id
    import requests
    
    url_base = f"https://api.telegram.org/bot{bot_token}/sendmessage"
    sent_notifications = []
    
    for message in state["telegram_notifications"]:
        try:
            full_message = f"{state['current_time']} {message}"
            params = {'chat_id': chat_id, 'text': full_message}
            response = requests.get(url_base, params=params, timeout=5)
            
            if response.status_code == 200:
                sent_notifications.append(f"알림 전송 성공: {message[:50]}...")
            else:
                sent_notifications.append(f"알림 전송 실패: {response.status_code}")
                
        except Exception as e:
            sent_notifications.append(f"Telegram API 오류: {str(e)}")
    
    return {"telegram_notifications": sent_notifications}


def should_retry(state: MonitorState) -> str:
    """재시도 여부 결정 엣지"""
    has_errors = len(state["error_messages"]) > 0
    can_retry = state["retry_count"] < state["max_retries"]
    
    if has_errors and can_retry:
        return "retry"
    return "complete"


def increment_retry(state: MonitorState) -> MonitorState:
    """재시도 카운트 증가"""
    return {"retry_count": state["retry_count"] + 1}


def finalize_state(state: MonitorState) -> MonitorState:
    """최종 상태 정리"""
    print(f"\n{'='*50}")
    print(f"모니터링 완료 시간: {state['current_time']}")
    print(f"총 웹 체크: {len(state['web_check_results'])}")
    print(f"에러 발생: {len(state['error_messages'])}")
    print(f"재시도 횟수: {state['retry_count']}")
    print(f"{'='*50}\n")
    return state


# ==================== Graph Construction ====================
from langgraph.graph import StateGraph, END


def build_monitor_graph():
    """모니터링 그래프 구축"""
    
    # 그래프 생성
    workflow = StateGraph(MonitorState)
    
    # 노드 추가
    workflow.add_node("initialize", initialize_state)
    workflow.add_node("check_web", check_web_health)
    workflow.add_node("check_temp", check_temperature)
    workflow.add_node("send_notification", send_telegram_notifications)
    workflow.add_node("increment_retry", increment_retry)
    workflow.add_node("finalize", finalize_state)
    
    # 엣지 설정
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "check_web")
    workflow.add_edge("check_web", "check_temp")
    workflow.add_edge("check_temp", "send_notification")
    
    # 조건부 엣지 (재시도 로직)
    workflow.add_conditional_edges(
        "send_notification",
        should_retry,
        {
            "retry": "increment_retry",
            "complete": "finalize"
        }
    )
    
    workflow.add_edge("increment_retry", "check_web")
    workflow.add_edge("finalize", END)
    
    return workflow.compile()


# ==================== Main Entry Point ====================
if __name__ == "__main__":
    # 그래프 컴파일
    monitor_app = build_monitor_graph()
    
    # 초기 입력
    initial_state = {
        "urls_to_check": [],
        "web_check_results": [],
        "temp_check_result": None,
        "error_messages": [],
        "telegram_notifications": [],
        "retry_count": 0,
        "max_retries": 3
    }
    
    # 그래프 실행
    final_state = monitor_app.invoke(initial_state)
    
    print("\n최종 상태:")
    print(f"에러 메시지: {final_state['error_messages']}")
    print(f"재시도 횟수: {final_state['retry_count']}")
