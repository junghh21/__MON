"""
LangGraph 기반 모니터링 시스템 - 3차 리뷰 (최종 개선)

2 차에서 적용된 개선사항:
✅ 환경 변수로 기밀 정보 관리
✅ 로깅 시스템 도입
✅ 설정 클래스 도입
✅ Exponential Backoff 재시도 로직
✅ 상태 지속성 (JSON 파일 저장)

3 차 리뷰에서 추가된 개선사항:
✅ 비동기 처리 완전 지원 (httpx + asyncio)
✅ 단위 테스트 및 통합 테스트 코드
✅ Dockerfile 및 docker-compose.yml 업데이트
✅ GitHub Actions 워크플로우 개선
✅ .env.example 템플릿 제공
✅ 타입 힌트 및 문서화 강화
✅ 에러 복구 메커니즘 추가
✅ 체크포인트 기능 (LangGraph Checkpointer)
✅ 병렬 실행 지원 (웹 체크 병렬화)
"""

import os
import json
import logging
import asyncio
from typing import TypedDict, Annotated, List, Optional, Literal, Sequence
from datetime import datetime
from pathlib import Path
import operator
from dataclasses import dataclass, field, asdict
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

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
    retry_delay_base: float = 1.0
    request_timeout: int = 10
    temp_timeout: int = 5
    log_level: str = "INFO"
    state_file: str = "monitor_state.json"
    enable_parallel: bool = True
    parallel_max_concurrent: int = 5
    
    @classmethod
    def from_env(cls) -> 'MonitorConfig':
        """환경 변수에서 설정 로드"""
        load_dotenv()
        
        urls_str = os.getenv('MONITOR_URLS', '')
        urls = [u.strip() for u in urls_str.split(',') if u.strip()] if urls_str else []
        
        return cls(
            urls_to_check=urls if urls else cls.__dataclass_fields__['urls_to_check'].default_factory(),
            temp_api_url=os.getenv('TEMP_API_URL', cls.temp_api_url),
            max_retries=int(os.getenv('MAX_RETRIES', '3')),
            retry_delay_base=float(os.getenv('RETRY_DELAY_BASE', '1.0')),
            request_timeout=int(os.getenv('REQUEST_TIMEOUT', '10')),
            temp_timeout=int(os.getenv('TEMP_TIMEOUT', '5')),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            state_file=os.getenv('STATE_FILE', 'monitor_state.json'),
            enable_parallel=os.getenv('ENABLE_PARALLEL', 'true').lower() == 'true',
            parallel_max_concurrent=int(os.getenv('PARALLEL_MAX_CONCURRENT', '5'))
        )


# ==================== Logging Setup ====================
def setup_logging(level: str = "INFO") -> logging.Logger:
    """로깅 시스템 설정"""
    logger = logging.getLogger("monitor")
    logger.setLevel(getattr(logging, level.upper()))
    
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        
        fh = logging.FileHandler("monitor.log", encoding='utf-8')
        fh.setLevel(logging.INFO)
        
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


# ==================== Async Node Functions ====================
class AsyncMonitorNodes:
    """비동기 모니터링 노드 클래스"""
    
    def __init__(self, config: MonitorConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self._http_client: Optional[httpx.AsyncClient] = None
    
    @asynccontextmanager
    async def get_http_client(self):
        """HTTP 클라이언트 컨텍스트 매니저"""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.request_timeout),
            verify=False  # SSL 검증 비활성화 (프로덕션에서는 활성화 권장)
        ) as client:
            yield client
    
    async def initialize_state(self, state: MonitorState) -> MonitorState:
        """초기 상태 설정 노드"""
        self.logger.info("모니터링 세션 초기화 (비동기)")
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
            "last_error_time": None,
            "checkpoint_id": None
        }
    
    async def check_single_url(self, client: httpx.AsyncClient, url: str) -> dict:
        """단일 URL 체크 (병렬용)"""
        try:
            self.logger.debug(f"URL 확인 중: {url}")
            response = await client.get(url)
            
            if response.status_code == 200:
                result = {
                    "url": url, 
                    "status": "OK", 
                    "status_code": 200,
                    "checked_at": datetime.now().isoformat(),
                    "response_time_ms": response.elapsed.total_seconds() * 1000
                }
                notification = f"✅ 웹사이트 {url} 정상 접속 ({result['response_time_ms']:.0f}ms)"
                self.logger.info(f"✓ {url}: OK ({result['response_time_ms']:.0f}ms)")
            else:
                result = {
                    "url": url, 
                    "status": "ERROR", 
                    "status_code": response.status_code,
                    "checked_at": datetime.now().isoformat()
                }
                notification = f"❌ 웹사이트 {url} 접속 실패 (상태 코드: {response.status_code})"
                self.logger.warning(f"✗ {url}: HTTP {response.status_code}")
            
            return {
                "result": result,
                "notification": notification,
                "error": None if response.status_code == 200 else f"웹사이트 {url} 접속 실패 (HTTP {response.status_code})"
            }
            
        except httpx.RequestError as e:
            error_str = str(e)
            result = {
                "url": url, 
                "status": "ERROR", 
                "error": error_str,
                "checked_at": datetime.now().isoformat()
            }
            notification = f"❌ 웹사이트 {url} 오류: {error_str}"
            self.logger.error(f"✗ {url}: {error_str}")
            
            return {
                "result": result,
                "notification": notification,
                "error": f"웹사이트 {url} 오류: {error_str}"
            }
    
    async def check_web_health(self, state: MonitorState) -> MonitorState:
        """웹사이트 건강 상태 확인 노드 (병렬 지원)"""
        self.logger.info(f"웹 체크 시작: {len(state['urls_to_check'])}개 URL")
        
        results = []
        notifications = []
        errors = []
        
        async with self.get_http_client() as client:
            if self.config.enable_parallel:
                # 병렬 실행
                tasks = [self.check_single_url(client, url) for url in state["urls_to_check"]]
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                
                for response in responses:
                    if isinstance(response, Exception):
                        error_msg = f"병렬 실행 오류: {str(response)}"
                        errors.append(error_msg)
                        self.logger.error(error_msg)
                    else:
                        results.append(response["result"])
                        notifications.append(response["notification"])
                        if response["error"]:
                            errors.append(response["error"])
            else:
                # 순차 실행
                for url in state["urls_to_check"]:
                    response = await self.check_single_url(client, url)
                    results.append(response["result"])
                    notifications.append(response["notification"])
                    if response["error"]:
                        errors.append(response["error"])
        
        self.logger.info(f"웹 체크 완료: {len(results)}개 결과, {len(errors)}개 에러")
        
        return {
            "web_check_results": results,
            "telegram_notifications": notifications,
            "error_messages": errors,
            "last_error_time": datetime.now().isoformat() if errors else None
        }
    
    async def check_temperature(self, state: MonitorState) -> MonitorState:
        """시스템 온도 및 리소스 확인 노드"""
        self.logger.info("온도 체크 시작")
        notifications = []
        errors = []
        temp_result = None
        
        async with self.get_http_client() as client:
            try:
                response = await client.get(self.config.temp_api_url)
                response.raise_for_status()
                data = response.json()
                
                # 데이터 정제 (CpuInfo 키가 있는 경우만)
                if 'CpuInfo' in data and 'fTemp' in data.get('CpuInfo', {}):
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
                    self.logger.info(f"온도 체크 성공: {temp_str}")
                else:
                    # CpuInfo 가 없는 경우 (테스트용 API 등)
                    temp_result = {"raw_data": data, "note": "표준 형식 아님"}
                    notification = f"📊 시스템 데이터 수신 (형식: {list(data.keys())})"
                    self.logger.info(f"온도 데이터 수신 (비표준 형식): {list(data.keys())}")
                
                notifications.append(notification)
                
            except httpx.HTTPStatusError as err:
                error_msg = f"HTTP 오류: {err}"
                errors.append(error_msg)
                notifications.append(f"❌ {error_msg}")
                self.logger.error(error_msg)
            except httpx.ConnectError as err:
                error_msg = f"연결 오류: {err}"
                errors.append(error_msg)
                notifications.append(f"❌ {error_msg}")
                self.logger.error(error_msg)
            except httpx.TimeoutException as err:
                error_msg = f"타임아웃: {err}"
                errors.append(error_msg)
                notifications.append(f"❌ {error_msg}")
                self.logger.error(error_msg)
            except httpx.RequestError as err:
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
    
    async def send_telegram_notifications(self, state: MonitorState) -> MonitorState:
        """Telegram 알림 발송 노드"""
        load_dotenv()
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not bot_token or not chat_id:
            self.logger.warning("Telegram 설정이 없습니다. 알림을 건너뜁니다.")
            return {"telegram_notifications": ["⚠️ Telegram 설정 누락으로 알림 전송 안됨"]}
        
        url_base = f"https://api.telegram.org/bot{bot_token}/sendmessage"
        sent_notifications = []
        
        self.logger.info(f"Telegram 알림 발송: {len(state['telegram_notifications'])}개")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for message in state["telegram_notifications"]:
                try:
                    full_message = f"⏰ {state['current_time']}\n{message}"
                    params = {
                        'chat_id': int(chat_id),
                        'text': full_message,
                        'parse_mode': 'HTML'
                    }
                    response = await client.get(url_base, params=params)
                    
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
    
    async def increment_retry(self, state: MonitorState) -> MonitorState:
        """재시도 카운트 증가 (Exponential Backoff 대기 포함)"""
        new_count = state["retry_count"] + 1
        delay = self.config.retry_delay_base * (2 ** (new_count - 1))
        
        self.logger.info(f"재시도 {new_count}/{state['max_retries']}, {delay:.1f}초 대기")
        await asyncio.sleep(delay)
        
        return {"retry_count": new_count}
    
    async def finalize_state(self, state: MonitorState) -> MonitorState:
        """최종 상태 정리 및 저장"""
        self.logger.info("="*50)
        self.logger.info("모니터링 완료 (비동기)")
        self.logger.info(f"완료 시간: {state['current_time']}")
        self.logger.info(f"총 웹 체크: {len(state['web_check_results'])}")
        self.logger.info(f"에러 발생: {len(state['error_messages'])}")
        self.logger.info(f"재시도 횟수: {state['retry_count']}")
        self.logger.info("="*50)
        
        # 상태 파일로 저장
        state_path = Path(self.config.state_file)
        try:
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            self.logger.info(f"상태 저장 완료: {state_path}")
        except Exception as e:
            self.logger.error(f"상태 저장 실패: {e}")
        
        return state


# ==================== Graph Construction ====================
class AsyncMonitorGraphBuilder:
    """비동기 모니터링 그래프 빌더"""
    
    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig.from_env()
        self.logger = setup_logging(self.config.log_level)
        self.nodes = AsyncMonitorNodes(self.config, self.logger)
    
    def build(self, use_checkpointer: bool = False):
        """그래프 구축 및 컴파일
        
        Args:
            use_checkpointer: 체크포인터 사용 여부 (테스트 시 False 권장)
        
        Returns:
            컴파일된 그래프
        """
        self.logger.info("비동기 모니터링 그래프 구축 시작")
        
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
        
        # 체크포인터 설정 (상태 복원 지원)
        if use_checkpointer:
            memory = MemorySaver()
            self.logger.info("체크포인터 활성화됨")
            compiled_graph = workflow.compile(checkpointer=memory)
        else:
            self.logger.info("체크포인터 비활성화됨 (테스트 모드)")
            compiled_graph = workflow.compile()
        
        self.logger.info("비동기 모니터링 그래프 구축 완료")
        return compiled_graph


# ==================== Main Entry Point ====================
async def run_monitor():
    """비동기 모니터링 실행"""
    # 설정 로드
    config = MonitorConfig.from_env()
    
    # 그래프 빌드
    builder = AsyncMonitorGraphBuilder(config)
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
        "last_error_time": None,
        "checkpoint_id": None
    }
    
    # 그래프 실행
    print("\n🚀 비동기 모니터링 시작...\n")
    final_state = await monitor_app.ainvoke(initial_state)
    
    print("\n📊 최종 결과:")
    print(f"  에러 메시지: {len(final_state['error_messages'])}개")
    print(f"  재시도 횟수: {final_state['retry_count']}")
    print(f"  상태 파일: {config.state_file}")
    
    return final_state


if __name__ == "__main__":
    asyncio.run(run_monitor())
