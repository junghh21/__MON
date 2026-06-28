"""
LangGraph 기반 모니터링 시스템 v4.0
- 시각적 UX 개선 (ASCII Dashboard, Table Report, Color Coding)
- 병렬 처리 및 재시도 로직 유지
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from dataclasses import dataclass, asdict

# LangGraph & LangChain
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# HTTP & Env
import httpx
from dotenv import load_dotenv

# --- 설정 로드 ---
load_dotenv()

# --- 로깅 설정 (기본 설정만, 시각화는 별도 클래스에서 처리) ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("monitor.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("MonitorUX")

# --- 상수 정의 ---
WEB_URLS = [
    "https://www.okkjc.co.kr:5001",
    "https://www.okkjc.co.kr:5002"
]
TEMP_API_URL = "https://httpbin.org/json"  # Mock API
MAX_RETRIES = 3
TIMEOUT_SECONDS = 5

# --- 시각적 유틸리티 클래스 ---
class VisualFormatter:
    """터미널 출력을 위한 시각적 포맷팅 클래스"""
    
    COLORS = {
        "RESET": "\033[0m",
        "BOLD": "\033[1m",
        "GREEN": "\033[92m",
        "YELLOW": "\033[93m",
        "RED": "\033[91m",
        "BLUE": "\033[94m",
        "CYAN": "\033[96m"
    }
    
    ICONS = {
        "SUCCESS": "✅",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "INFO": "ℹ️",
        "RUNNING": "🔄"
    }

    @classmethod
    def colorize(cls, text: str, color: str) -> str:
        return f"{cls.COLORS.get(color, '')}{text}{cls.COLORS['RESET']}"

    @classmethod
    def get_icon(cls, status: str) -> str:
        return cls.ICONS.get(status, "•")

    @classmethod
    def print_header(cls):
        """대시보드 헤더 출력"""
        border = "╔" + "═" * 40 + "╗"
        title = cls.colorize("🛡️  LangGraph Monitor System  ", "CYAN")
        status = cls.colorize("Status: OPERATIONAL", "GREEN")
        
        print("\n" + border)
        print(f"║{title.center(40)}║")
        print(f"║{status.center(40)}║")
        print("╚" + "═" * 40 + "╝\n")

    @classmethod
    def print_step(cls, step_name: str, message: str = ""):
        """단계별 진행 메시지"""
        icon = cls.get_icon("RUNNING")
        step = cls.colorize(f"[{step_name}]", "BLUE")
        print(f"{icon} {step} {message}")

    @classmethod
    def print_result_row(cls, name: str, status: str, value: str, latency: str):
        """표 형식 출력을 위한 행 데이터 생성"""
        icon = cls.get_icon(status)
        color = "GREEN" if status == "OK" else ("YELLOW" if status == "WARN" else "RED")
        return {
            "name": name,
            "icon": icon,
            "status": cls.colorize(status, color),
            "value": value,
            "latency": latency
        }

    @classmethod
    def print_table(cls, rows: List[Dict]):
        """결과 표 출력"""
        if not rows:
            return
            
        # rows 가 generator 일 경우 list 로 변환
        if hasattr(rows, '__iter__') and not isinstance(rows, list):
            rows = list(rows)
            
        if not rows:
            return

        # 컬럼 너비 계산 (ANSI 코드 제거한 실제 길이)
        import re
        def clean_len(s):
            return len(re.sub(r'\x1b\[[0-9;]*m', '', str(s)))
            
        col_widths = {
            "name": max(clean_len(r["name"]) for r in rows),
            "status": max(clean_len(r["status"]) for r in rows),
            "value": max(clean_len(r["value"]) for r in rows),
            "latency": max(clean_len(r["latency"]) for r in rows)
        }
        # 최소 너비 보장
        col_widths["name"] = max(col_widths["name"], 20)
        col_widths["status"] = max(col_widths["status"], 10)
        col_widths["value"] = max(col_widths["value"], 10)
        col_widths["latency"] = max(col_widths["latency"], 10)

        # 테두리 문자
        tl, tr, bl, br = "┌", "┐", "└", "┘"
        vh, vp = "─", "│"
        vl, vr = "├", "┤"

        # 헤더
        header = ["Component", "Status", "Value", "Latency"]
        
        # 테이블 그리기
        width = sum(col_widths.values()) + (len(col_widths) * 3) + 1
        
        print("")
        print(tl + vh * (width-2) + tr)
        
        # 헤더 행
        header_row = f"{vp} {header[0]:<{col_widths['name']}} {vp} {header[1]:^{col_widths['status']}} {vp} {header[2]:^{col_widths['value']}} {vp} {header[3]:^{col_widths['latency']}} {vp}"
        print(header_row)
        print(vl + vh * (width-2) + vr)
        
        # 데이터 행
        for r in rows:
            row_str = f"{vp} {r['icon']} {r['name']:<{col_widths['name']-2}} {vp} {r['status']:^{col_widths['status']}} {vp} {r['value']:>{col_widths['value']}} {vp} {r['latency']:>{col_widths['latency']}} {vp}"
            print(row_str)
            
        print(bl + vh * (width-2) + br)
        print("")

# --- 상태 정의 ---
class MonitorState(TypedDict):
    messages: Annotated[List[str], lambda x, y: x + y]
    web_results: List[Dict[str, Any]]
    temp_result: Optional[Dict[str, Any]]
    retry_count: int
    start_time: str
    errors: List[str]

# --- 노드 함수들 ---

async def initialize(state: MonitorState) -> MonitorState:
    VisualFormatter.print_header()
    VisualFormatter.print_step("INIT", "시스템 초기화 중...")
    
    now = datetime.now().isoformat()
    return {
        "messages": [f"Started at {now}"],
        "web_results": [],
        "temp_result": None,
        "retry_count": 0,
        "start_time": now,
        "errors": []
    }

async def check_single_web(url: str, session: httpx.AsyncClient) -> Dict[str, Any]:
    """단일 웹 URL 체크 (내부 헬퍼)"""
    start = datetime.now()
    status = "OK"
    code = "-"
    msg = ""
    
    try:
        resp = await session.get(url, timeout=TIMEOUT_SECONDS)
        code = resp.status_code
        if 200 <= code < 300:
            msg = "Success"
        else:
            status = "WARN"
            msg = f"HTTP {code}"
    except httpx.TimeoutException:
        status = "ERROR"
        msg = "Timeout"
        code = "0"
    except Exception as e:
        status = "ERROR"
        msg = str(e)[:20]
        code = "0"
        
    latency = (datetime.now() - start).total_seconds() * 1000
    return {
        "url": url,
        "status": status,
        "code": str(code),
        "msg": msg,
        "latency_ms": f"{latency:.0f}ms"
    }

async def check_web(state: MonitorState) -> MonitorState:
    VisualFormatter.print_step("WEB CHECK", f"모니터링 대상: {len(WEB_URLS)}개")
    
    results = []
    async with httpx.AsyncClient() as client:
        tasks = [check_single_web(url, client) for url in WEB_URLS]
        results = await asyncio.gather(*tasks)
    
    # 시각적 피드백 (중간 결과)
    for res in results:
        icon = VisualFormatter.get_icon(res['status'])
        color = "GREEN" if res['status'] == "OK" else "RED"
        print(f"  {icon} {res['url']}: {VisualFormatter.colorize(res['status'], color)} ({res['latency_ms']})")

    has_error = any(r['status'] == 'ERROR' for r in results)
    
    updates = {"web_results": results}
    if has_error:
        updates["errors"] = [f"Web check failed for {r['url']}" for r in results if r['status'] == 'ERROR']
        updates["retry_count"] = state["retry_count"] + 1
    
    return updates

async def check_temp(state: MonitorState) -> MonitorState:
    VisualFormatter.print_step("TEMP CHECK", "CPU 온도 조회 중...")
    
    result = {"status": "ERROR", "value": "-", "latency_ms": "0ms"}
    start = datetime.now()
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(TEMP_API_URL, timeout=TIMEOUT_SECONDS)
            if resp.status_code == 200:
                # Mock 데이터 파싱 시도
                data = resp.json()
                # 실제 API 가 아닐 경우를 대비해 기본값 사용
                temp_val = data.get("slideshow", {}).get("title", "N/A") 
                result = {
                    "status": "OK",
                    "value": temp_val, # 실제로는 온도 숫자가 와야 함
                    "latency_ms": f"{(datetime.now() - start).total_seconds() * 1000:.0f}ms"
                }
            else:
                result["status"] = "WARN"
                result["value"] = f"HTTP {resp.status_code}"
    except Exception as e:
        result["value"] = str(e)[:15]
        
    # 시각적 피드백
    icon = VisualFormatter.get_icon(result['status'])
    color = "GREEN" if result['status'] == "OK" else "YELLOW"
    print(f"  {icon} Temperature API: {VisualFormatter.colorize(result['status'], color)} ({result['value']})")

    return {"temp_result": result}

def should_retry(state: MonitorState) -> str:
    if state["retry_count"] < MAX_RETRIES and len(state["errors"]) > 0:
        logger.warning(f"Retrying... Attempt {state['retry_count']}/{MAX_RETRIES}")
        print(f"\n{VisualFormatter.get_icon('WARNING')} 재시도합니다... ({state['retry_count']}/{MAX_RETRIES})\n")
        return "retry"
    return "finish"

async def send_notification(state: MonitorState) -> MonitorState:
    # Telegram 연동 로직은 생략 (로그로 대체)
    error_count = len(state["errors"])
    if error_count > 0:
        logger.error(f"Alert: {error_count} errors detected. Sending notification...")
        print(f"\n{VisualFormatter.get_icon('ERROR')} 알림 전송 완료: {error_count}개의 오류 발견")
    else:
        logger.info("All checks passed. No notification needed.")
        print(f"\n{VisualFormatter.get_icon('SUCCESS')} 모든 점검이 정상입니다.")
    return {}

async def finalize(state: MonitorState) -> MonitorState:
    VisualFormatter.print_step("REPORT", "최종 보고서 생성")
    
    rows = []
    # 웹 결과 추가
    for res in state["web_results"]:
        rows.append(VisualFormatter.print_result_row(
            res['url'].split('/')[-1], # 짧은 이름
            "OK" if res['status'] == 'OK' else ("WARN" if res['status'] == 'WARN' else "FAIL"),
            res['code'],
            res['latency_ms']
        ))
    
    # 온도 결과 추가
    if state["temp_result"]:
        tr = state["temp_result"]
        rows.append(VisualFormatter.print_result_row(
            "CPU Temperature",
            tr['status'],
            tr['value'],
            tr['latency_ms']
        ))
    
    VisualFormatter.print_table(rows)
    
    # 상태 저장
    with open("monitor_state.json", "w", encoding='utf-8') as f:
        # datetime 객체 직렬화 방지
        save_data = {k: v for k, v in state.items()}
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 상태가 저장되었습니다: monitor_state.json")
    return {}

# --- 그래프 구축 ---
def build_graph():
    workflow = StateGraph(MonitorState)
    
    workflow.add_node("initialize", initialize)
    workflow.add_node("check_web", check_web)
    workflow.add_node("check_temp", check_temp)
    workflow.add_node("send_notification", send_notification)
    workflow.add_node("finalize", finalize)
    
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "check_web")
    workflow.add_edge("initialize", "check_temp") # 병렬 시작을 위해 initialize 에서 둘 다 연결? 
    # LangGraph 는 기본적으로 순차적이지만, 노드 내부에서 asyncio.gather 를 쓰거나, 
    # 여기서는 간단히 Web -> Temp 순서로 하되, Web 노드 내부에서 병렬 처리함.
    # 더 고급 병렬을 원하면 Fan-out 패턴 사용 필요하지만, 현재는 Web 노드 하나에서 처리.
    
    workflow.add_edge("check_web", "check_temp")
    workflow.add_conditional_edges(
        "check_temp",
        should_retry,
        {
            "retry": "check_web",
            "finish": "send_notification"
        }
    )
    workflow.add_edge("send_notification", "finalize")
    workflow.add_edge("finalize", END)
    
    return workflow.compile()

# --- 메인 실행 ---
async def main():
    app = build_graph()
    
    initial_state = {
        "messages": [],
        "web_results": [],
        "temp_result": None,
        "retry_count": 0,
        "start_time": "",
        "errors": []
    }
    
    try:
        await app.ainvoke(initial_state)
    except Exception as e:
        logger.critical(f"System Crash: {e}")
        print(f"\n{VisualFormatter.get_icon('ERROR')} 시스템 오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main())
