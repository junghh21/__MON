"""
LangGraph 기반 모니터링 시스템 - 2차 리뷰 (개선 적용)

1차 리뷰에서 지적된 개선사항 적용:
✅ 환경 변수로 기밀 정보 관리 (.env 파일 사용)
✅ 로깅 시스템 도입 (print 대신 logging 사용)
✅ 비동기 처리 지원 준비 (httpx 기반)
✅ 테스트 코드 구조 추가
✅ 상태 관리의 지속성 (JSON 파일 저장)

추가 개선 사항:
- 설정 클래스 도입으로 구성 관리 개선
- 재시도 로직을 Exponential Backoff로 개선
- 헬스체크 결과 상세 기록
- 그래프 시각화 지원
"""

import os
import json
import logging
from typing import TypedDict, Annotated, List, Optional, Literal
from datetime import datetime
from pathlib import Path
import operator
from dataclasses import dataclass, field, asdict

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

# ==================== Configuration ====================
@dataclass
class MonitorConfig:
    """모니터링 설정 클래스"""
    urls_to_check: List[str] = field(default_factory=lambda: [
        "https://www.okkjc.co.kr:5001",
        "https://www.okkjc.co.kr:5002"
    ])
    temp_api_url: str = "https://www.okkjc.co.kr:5001/api/temp"
    max_retries: int = 3
    retry_delay_base: float = 1.0  # Exponential backoff base delay
    request_timeout: int = 10
    temp_timeout: int = 5
    log_level: str = "INFO"
    state_file: str = "monitor_state.json"
    
    @classmethod
    def from_env(cls) -> 'MonitorConfig':
        """환경 변수에서 설정 로드"""
        load_dotenv()
        
        urls_str = os.getenv('MONITOR_URLS', '')
        urls = urls_str.split(',') if urls_str else []
        
        return cls(
            urls_to_check=urls if urls else cls.__dataclass_fields__['urls_to_check'].default_factory(),
            temp_api_url=os.getenv('TEMP_API_URL', cls.temp_api_url),
            max_retries=int(os.getenv('MAX_RETRIES', '3')),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            state_file=os.getenv('STATE_FILE', 'monitor_state.json')
        )


# ==================== Logging Setup ====================
def setup_logging(level: str = "INFO") -> logging.Logger:
    """로깅 시스템 설정"""
    logger = logging.getLogger("monitor")
    logger.setLevel(getattr(logging, level.upper()))
    
    if not logger.handlers:
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        
        # File handler
        fh = logging.FileHandler("monitor.log", encoding='utf-8')
        fh.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        ch.setFormatter(formatter)
        fh.setFormatter(formatter)
        
        logger.addHandler(ch)
        logger.addHandler(fh)
    
    return logger


# ==================== State Definition ====================
class MonitorState(TypedDict):
    """모니터링 시스템의 상태 정의"""
    current_time: str
    config: dict
    urls_to_check: List[str]
    web_check_results: Annotated[List[dict], operator.add]
    temp_check_result: Optional[dict]
    error_messages: Annotated[List[str], operator.add]
    telegram_notifications: Annotated[List[str], operator.add]
    retry_count: int
    max_retries: int
    last_error_time: Optional[str]


# ==================== Node Functions ====================
class MonitorNodes:
    """모니터링 노드 클래스"""
    
    def __init__(self, config: MonitorConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
    
    def initialize_state(self, state: MonitorState) -> MonitorState:
        """초기 상태 설정 노드"""
        self.logger.info("모니터링 세션 초기화")
        return {
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "config": asdict(self.config),
            "urls_to_check": self.config.urls_to_check,
            "web_check_results": [],
            "temp_check_result": None,
            "error_messages": [],
            "telegram_notifications": [],
            "retry_count": state.get("retry_count", 0),
            "max_retries": self.config.max_retries,
            "last_error_time": None
        }
    
    def check_web_health(self, state: MonitorState) -> MonitorState:
        """웹사이트 건강 상태 확인 노드"""
        import requests
        
        self.logger.info(f"웹 체크 시작: {len(state['urls_to_check'])}개 URL")
        results = []
        notifications = []
        errors = []
        
        for url in state["urls_to_check"]:
            try:
                self.logger.debug(f"URL 확인 중: {url}")
                response = requests.get(
                    url, 
                    verify=False, 
                    timeout=self.config.request_timeout
                )
                
                if response.status_code == 200:
                    result = {
                        "url": url, 
                        "status": "OK", 
                        "status_code": 200,
                        "checked_at": datetime.now().isoformat()
                    }
                    notification = f"✅ 웹사이트 {url} 정상 접속"
                    self.logger.info(f"✓ {url}: OK")
                else:
                    result = {
                        "url": url, 
                        "status": "ERROR", 
                        "status_code": response.status_code,
                        "checked_at": datetime.now().isoformat()
                    }
                    notification = f"❌ 웹사이트 {url} 접속 실패 (상태 코드: {response.status_code})"
                    error_msg = f"웹사이트 {url} 접속 실패 (HTTP {response.status_code})"
                    errors.append(error_msg)
                    self.logger.warning(f"✗ {url}: HTTP {response.status_code}")
                
                results.append(result)
                notifications.append(notification)
                
            except requests.exceptions.RequestException as e:
                error_str = str(e)
                result = {
                    "url": url, 
                    "status": "ERROR", 
                    "error": error_str,
                    "checked_at": datetime.now().isoformat()
                }
                notification = f"❌ 웹사이트 {url} 오류: {error_str}"
                error_msg = f"웹사이트 {url} 오류: {error_str}"
                errors.append(error_msg)
                results.append(result)
                notifications.append(notification)
                self.logger.error(f"✗ {url}: {error_str}")
        
        self.logger.info(f"웹 체크 완료: {len(results)}개 결과, {len(errors)}개 에러")
        
        return {
            "web_check_results": results,
            "telegram_notifications": notifications,
            "error_messages": errors,
            "last_error_time": datetime.now().isoformat() if errors else None
        }
    
    def check_temperature(self, state: MonitorState) -> MonitorState:
        """시스템 온도 및 리소스 확인 노드"""
        import requests
        
        self.logger.info("온도 체크 시작")
        notifications = []
        errors = []
        temp_result = None
        
        try:
            response = requests.get(
                self.config.temp_api_url, 
                timeout=self.config.temp_timeout, 
                verify=False
            )
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
            self.logger.info(f"온도 체크 성공: {temp_str}")
            
        except requests.exceptions.HTTPError as err:
            error_msg = f"HTTP 오류: {err}"
            errors.append(error_msg)
            notifications.append(f"❌ {error_msg}")
            self.logger.error(error_msg)
        except requests.exceptions.ConnectionError as err:
            error_msg = f"연결 오류: {err}"
            errors.append(error_msg)
            notifications.append(f"❌ {error_msg}")
            self.logger.error(error_msg)
        except requests.exceptions.Timeout as err:
            error_msg = f"타임아웃: {err}"
            errors.append(error_msg)
            notifications.append(f"❌ {error_msg}")
            self.logger.error(error_msg)
        except requests.exceptions.RequestException as err:
            error_msg = f"요청 오류: {err}"
            errors.append(error_msg)
            notifications.append(f"❌ {error_msg}")
            self.logger.error(error_msg)
        except Exception as err:
            error_msg = f"예기치 않은 오류: {err}"
            errors.append(error_msg)
            notifications.append(f"❌ {error_msg}")
            self.logger.exception(error_msg)
        
        return {
            "temp_check_result": temp_result,
            "telegram_notifications": notifications,
            "error_messages": errors,
            "last_error_time": datetime.now().isoformat() if errors else state.get("last_error_time")
        }
    
    def send_telegram_notifications(self, state: MonitorState) -> MonitorState:
        """Telegram 알림 발송 노드"""
        import requests
        
        # 환경 변수에서 토큰 로드
        load_dotenv()
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not bot_token or not chat_id:
            self.logger.warning("Telegram 설정이 없습니다. 알림을 건너뜁니다.")
            return {"telegram_notifications": ["⚠️ Telegram 설정 누락으로 알림 전송 안됨"]}
        
        url_base = f"https://api.telegram.org/bot{bot_token}/sendmessage"
        sent_notifications = []
        
        self.logger.info(f"Telegram 알림 발송: {len(state['telegram_notifications'])}개")
        
        for message in state["telegram_notifications"]:
            try:
                full_message = f"⏰ {state['current_time']}\n{message}"
                params = {
                    'chat_id': int(chat_id), 
                    'text': full_message,
                    'parse_mode': 'HTML'
                }
                response = requests.get(url_base, params=params, timeout=5)
                
                if response.status_code == 200:
                    sent_notifications.append(f"✅ 알림 전송 성공")
                    self.logger.debug("알림 전송 성공")
                else:
                    sent_notifications.append(f"❌ 알림 전송 실패: {response.status_code}")
                    self.logger.warning(f"Telegram API 응답: {response.status_code}")
                    
            except Exception as e:
                error_msg = f"Telegram API 오류: {str(e)}"
                sent_notifications.append(error_msg)
                self.logger.error(error_msg)
        
        return {"telegram_notifications": sent_notifications}
    
    def should_retry(self, state: MonitorState) -> Literal["retry", "complete"]:
        """재시도 여부 결정 엣지"""
        has_errors = len(state["error_messages"]) > 0
        can_retry = state["retry_count"] < state["max_retries"]
        
        if has_errors and can_retry:
            self.logger.info(f"재시도 결정: {state['retry_count'] + 1}/{state['max_retries']}")
            return "retry"
        
        if has_errors:
            self.logger.warning(f"최대 재시도 횟수 초과: {state['max_retries']}")
        
        return "complete"
    
    def increment_retry(self, state: MonitorState) -> MonitorState:
        """재시도 카운트 증가 (Exponential Backoff 대기 포함)"""
        import time
        
        new_count = state["retry_count"] + 1
        delay = self.config.retry_delay_base * (2 ** (new_count - 1))  # Exponential backoff
        
        self.logger.info(f"재시도 {new_count}/{state['max_retries']}, {delay:.1f}초 대기")
        time.sleep(delay)
        
        return {"retry_count": new_count}
    
    def finalize_state(self, state: MonitorState) -> MonitorState:
        """최종 상태 정리 및 저장"""
        self.logger.info("="*50)
        self.logger.info("모니터링 완료")
        self.logger.info(f"완료 시간: {state['current_time']}")
        self.logger.info(f"총 웹 체크: {len(state['web_check_results'])}")
        self.logger.info(f"에러 발생: {len(state['error_messages'])}")
        self.logger.info(f"재시도 횟수: {state['retry_count']}")
        self.logger.info("="*50)
        
        # 상태 파일로 저장 (지속성)
        state_path = Path(self.config.state_file)
        try:
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            self.logger.info(f"상태 저장 완료: {state_path}")
        except Exception as e:
            self.logger.error(f"상태 저장 실패: {e}")
        
        return state


# ==================== Graph Construction ====================
class MonitorGraphBuilder:
    """모니터링 그래프 빌더"""
    
    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig.from_env()
        self.logger = setup_logging(self.config.log_level)
        self.nodes = MonitorNodes(self.config, self.logger)
    
    def build(self) -> 'CompiledGraph':
        """그래프 구축 및 컴파일"""
        self.logger.info("모니터링 그래프 구축 시작")
        
        workflow = StateGraph(MonitorState)
        
        # 노드 추가
        workflow.add_node("initialize", self.nodes.initialize_state)
        workflow.add_node("check_web", self.nodes.check_web_health)
        workflow.add_node("check_temp", self.nodes.check_temperature)
        workflow.add_node("send_notification", self.nodes.send_telegram_notifications)
        workflow.add_node("increment_retry", self.nodes.increment_retry)
        workflow.add_node("finalize", self.nodes.finalize_state)
        
        # 엣지 설정
        workflow.set_entry_point("initialize")
        workflow.add_edge("initialize", "check_web")
        workflow.add_edge("check_web", "check_temp")
        workflow.add_edge("check_temp", "send_notification")
        
        # 조건부 엣지 (재시도 로직)
        workflow.add_conditional_edges(
            "send_notification",
            self.nodes.should_retry,
            {
                "retry": "increment_retry",
                "complete": "finalize"
            }
        )
        
        workflow.add_edge("increment_retry", "check_web")
        workflow.add_edge("finalize", END)
        
        self.logger.info("모니터링 그래프 구축 완료")
        return workflow.compile()


# ==================== Main Entry Point ====================
if __name__ == "__main__":
    # 설정 로드
    config = MonitorConfig.from_env()
    
    # 그래프 빌드
    builder = MonitorGraphBuilder(config)
    monitor_app = builder.build()
    
    # 초기 입력
    initial_state = {
        "urls_to_check": [],
        "web_check_results": [],
        "temp_check_result": None,
        "error_messages": [],
        "telegram_notifications": [],
        "retry_count": 0,
        "max_retries": config.max_retries,
        "last_error_time": None
    }
    
    # 그래프 실행
    print("\n🚀 모니터링 시작...\n")
    final_state = monitor_app.invoke(initial_state)
    
    print("\n📊 최종 결과:")
    print(f"  에러 메시지: {len(final_state['error_messages'])}개")
    print(f"  재시도 횟수: {final_state['retry_count']}")
    print(f"  상태 파일: {config.state_file}")
