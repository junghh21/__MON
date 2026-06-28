"""
LangGraph Monitoring System - Full Verification Suite
기능 블록별 (F-01~06) 및 워크플로우별 (W-01~04) 100% 검증 스크립트
"""
import asyncio, json, time, os
from unittest.mock import patch, AsyncMock, MagicMock
import sys
sys.path.insert(0, 'src')
from monitor_graph_v3 import MonitorConfig, AsyncMonitorNodes, AsyncMonitorGraphBuilder, setup_logging

results = {"functional": {}, "workflow": {}, "non_functional": {}}

def log_test(test_id, name, status, msg=""):
    icon = "✅" if status == "PASS" else "❌"
    print(f"{icon} [{test_id}] {name}: {status}")
    if msg: print(f"   ↳ {msg}")
    return status == "PASS"

async def verify_functional_blocks():
    print("\n" + "="*60 + "\n🧪 1. 기능 블록별 검증 (Functional Blocks)\n" + "="*60)
    config, logger = MonitorConfig(), setup_logging("WARNING")
    nodes = AsyncMonitorNodes(config, logger)
    passed, total = 0, 6

    # F-01
    try:
        result = await nodes.initialize_state({"retry_count": 0})
        success = "current_time" in result
        results["functional"]["F-01"] = "PASS" if success else "FAIL"
        if log_test("F-01", "Initialize Node", "PASS" if success else "FAIL", f"time set: {'current_time' in result}"): passed += 1
    except Exception as e: results["functional"]["F-01"] = "FAIL"; log_test("F-01", "Initialize", "FAIL", str(e))

    # F-02
    try:
        with patch('httpx.AsyncClient') as mc:
            mr = AsyncMock(); mr.status_code = 200; mr.text = "OK"; mr.raise_for_status = MagicMock(); mr.elapsed.total_seconds = MagicMock(return_value=0.1)
            mc.return_value.__aenter__.return_value.get = AsyncMock(return_value=mr)
            result = await nodes.check_web_health({"urls_to_check": ["https://x.com"], "web_check_results": [], "error_messages": []})
            success = len(result["web_check_results"]) > 0
            results["functional"]["F-02"] = "PASS" if success else "FAIL"
            if log_test("F-02", "Check Web Node", "PASS" if success else "FAIL", f"Results: {len(result['web_check_results'])}"): passed += 1
    except Exception as e: results["functional"]["F-02"] = "FAIL"; log_test("F-02", "Check Web", "FAIL", str(e))

    # F-03
    try:
        with patch('httpx.AsyncClient') as mc:
            mr = AsyncMock(); mr.status_code = 200; mr.json = AsyncMock(return_value={"CpuInfo": {"fTemp": [45.0], "uiLoad": [1.2]}, "MemoryInfo": {"MemoryLoad": "50%"}})
            mc.return_value.__aenter__.return_value.get = AsyncMock(return_value=mr)
            result = await nodes.check_temperature({"telegram_notifications": [], "error_messages": [], "last_error_time": None})
            success = result["temp_check_result"] is not None
            results["functional"]["F-03"] = "PASS" if success else "FAIL"
            if log_test("F-03", "Check Temp Node", "PASS" if success else "FAIL", f"Temp: {success}"): passed += 1
    except Exception as e: results["functional"]["F-03"] = "FAIL"; log_test("F-03", "Check Temp", "FAIL", str(e))

    # F-04
    try:
        with patch('httpx.AsyncClient.get') as mg:
            mg.return_value = AsyncMock(status_code=200)
            os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'] = 't', '1'
            result = await nodes.send_telegram_notifications({"current_time": "2024", "telegram_notifications": ["T"]})
            success = mg.called
            results["functional"]["F-04"] = "PASS" if success else "FAIL"
            if log_test("F-04", "Send Notification", "PASS" if success else "FAIL", f"Called: {success}"): passed += 1
            del os.environ['TELEGRAM_BOT_TOKEN']; del os.environ['TELEGRAM_CHAT_ID']
    except Exception as e: results["functional"]["F-04"] = "FAIL"; log_test("F-04", "Notify", "FAIL", str(e))

    # F-05
    try:
        tf = "/tmp/f5.json"
        if os.path.exists(tf): os.remove(tf)
        state = {"current_time": "2024", "retry_count": 0, "web_check_results": [], "error_messages": [], "telegram_notifications": [], "urls_to_check": [], "temp_check_result": None, "last_error_time": None, "checkpoint_id": None}
        await nodes.finalize_state(state)
        success = os.path.exists(tf)
        results["functional"]["F-05"] = "PASS" if success else "FAIL"
        if log_test("F-05", "Finalize Node", "PASS" if success else "FAIL", f"File: {success}"): passed += 1
        if os.path.exists(tf): os.remove(tf)
    except Exception as e: results["functional"]["F-05"] = "FAIL"; log_test("F-05", "Finalize", "FAIL", str(e))

    # F-06
    try:
        r1 = nodes.should_retry({"error_messages": ["E"], "retry_count": 1, "max_retries": 3})
        r2 = nodes.should_retry({"error_messages": ["E"], "retry_count": 3, "max_retries": 3})
        success = r1 == "retry" and r2 == "complete"
        results["functional"]["F-06"] = "PASS" if success else "FAIL"
        if log_test("F-06", "Retry Logic", "PASS" if success else "FAIL", f"{r1}, {r2}"): passed += 1
    except Exception as e: results["functional"]["F-06"] = "FAIL"; log_test("F-06", "Retry", "FAIL", str(e))

    print(f"\n📊 기능 블록: {passed}/{total}\n")
    return passed == total

async def verify_workflows():
    print("="*60 + "\n🔄 2. 워크플로우별 검증 (Workflows)\n" + "="*60)
    passed, total = 0, 4
    
    # W-01
    try:
        cfg = MonitorConfig()
        bld = AsyncMonitorGraphBuilder(cfg)
        with patch('httpx.AsyncClient') as mc:
            mr = AsyncMock(); mr.status_code = 200; mr.json = AsyncMock(return_value={"CpuInfo": {"fTemp": [40], "uiLoad": [1]}, "MemoryInfo": {"MemoryLoad": "50%"}}); mr.text = "OK"; mr.raise_for_status = MagicMock(); mr.elapsed.total_seconds = MagicMock(return_value=0.1)
            mc.return_value.__aenter__.return_value.get = AsyncMock(return_value=mr)
            with patch('httpx.AsyncClient.get'):
                app = bld.build(use_checkpointer=False)
                res = await asyncio.wait_for(app.ainvoke({"retry_count": 0, "urls_to_check": ["https://x.com"]}), timeout=10)
                success = res.get("temp_check_result") is not None and len(res.get("error_messages", [])) == 0
                results["workflow"]["W-01"] = "PASS" if success else "FAIL"
                if log_test("W-01", "Happy Path", "PASS" if success else "FAIL", f"Errors: {len(res.get('error_messages',[]))}"): passed += 1
    except Exception as e: results["workflow"]["W-01"] = "FAIL"; log_test("W-01", "Happy", "FAIL", str(e))

    # W-02
    try:
        async def mf(*a, **k):
            r = AsyncMock(); r.status_code = 500; r.raise_for_status = MagicMock(side_effect=Exception("E")); return r
        cfg = MonitorConfig(max_retries=1)
        bld = AsyncMonitorGraphBuilder(cfg)
        with patch('httpx.AsyncClient') as mc:
            mc.return_value.__aenter__.return_value.get = mf
            app = bld.build(use_checkpointer=False)
            res = await asyncio.wait_for(app.ainvoke({"retry_count": 0, "urls_to_check": ["https://x.com"]}), timeout=15)
            success = res.get("retry_count", 0) >= 1 or len(res.get("error_messages", [])) > 0
            results["workflow"]["W-02"] = "PASS" if success else "FAIL"
            if log_test("W-02", "Web Failure & Retry", "PASS" if success else "FAIL", f"Retry: {res.get('retry_count')}"): passed += 1
    except Exception as e: results["workflow"]["W-02"] = "FAIL"; log_test("W-02", "Retry", "FAIL", str(e))

    # W-03
    try:
        cfg = MonitorConfig()
        bld = AsyncMonitorGraphBuilder(cfg)
        with patch('httpx.AsyncClient') as mc:
            wr = AsyncMock(); wr.status_code = 200; wr.text = "OK"; wr.raise_for_status = MagicMock(); wr.elapsed.total_seconds = MagicMock(return_value=0.1)
            tr = AsyncMock(); tr.status_code = 200; tr.json = AsyncMock(return_value={"CpuInfo": {"fTemp": [85], "uiLoad": [1]}, "MemoryInfo": {"MemoryLoad": "50%"}})
            mc.return_value.__aenter__.return_value.get = AsyncMock(side_effect=[wr, tr])
            with patch('httpx.AsyncClient.get'):
                app = bld.build(use_checkpointer=False)
                res = await asyncio.wait_for(app.ainvoke({"retry_count": 0, "urls_to_check": ["https://x.com"]}), timeout=10)
                success = res.get("temp_check_result") is not None
                results["workflow"]["W-03"] = "PASS" if success else "FAIL"
                if log_test("W-03", "Temp Check", "PASS" if success else "FAIL", f"Present: {success}"): passed += 1
    except Exception as e: results["workflow"]["W-03"] = "FAIL"; log_test("W-03", "Temp", "FAIL", str(e))

    # W-04
    try:
        cfg = MonitorConfig()
        bld = AsyncMonitorGraphBuilder(cfg)
        with patch('httpx.AsyncClient') as mc:
            mr = AsyncMock(); mr.status_code = 200; mr.json = AsyncMock(return_value={"CpuInfo": {"fTemp": [40], "uiLoad": [1]}, "MemoryInfo": {"MemoryLoad": "50%"}}); mr.text = "OK"; mr.raise_for_status = MagicMock(); mr.elapsed.total_seconds = MagicMock(return_value=0.1)
            mc.return_value.__aenter__.return_value.get = AsyncMock(return_value=mr)
            with patch('httpx.AsyncClient.get'):
                app = bld.build(use_checkpointer=False)
                await asyncio.wait_for(app.ainvoke({"retry_count": 0, "urls_to_check": ["https://x.com"]}), timeout=10)
                success = True
                results["workflow"]["W-04"] = "PASS" if success else "FAIL"
                if log_test("W-04", "Stability", "PASS" if success else "FAIL", "OK"): passed += 1
    except Exception as e: results["workflow"]["W-04"] = "FAIL"; log_test("W-04", "Stability", "FAIL", str(e))

    print(f"\n📊 워크플로우: {passed}/{total}\n")
    return passed == total

async def verify_non_functional():
    print("="*60 + "\n⚡ 3. 비기능적 요구사항 검증\n" + "="*60)
    passed, total = 0, 3

    # NF-01
    try:
        async def sg(*a, **k):
            await asyncio.sleep(0.25)
            r = AsyncMock(); r.status_code = 200; r.text = "OK"; r.raise_for_status = MagicMock(); r.elapsed.total_seconds = MagicMock(return_value=0.25); return r
        cfg = MonitorConfig()
        bld = AsyncMonitorGraphBuilder(cfg)
        with patch('httpx.AsyncClient') as mc:
            mc.return_value.__aenter__.return_value.get = sg
            with patch('httpx.AsyncClient.get'):
                app = bld.build(use_checkpointer=False)
                st = time.time()
                await app.ainvoke({"retry_count": 0, "urls_to_check": ["https://a.com", "https://b.com"]})
                dur = time.time() - st
                success = dur < 0.6
                results["non_functional"]["NF-01"] = "PASS" if success else "FAIL"
                if log_test("NF-01", "Performance", "PASS" if success else "FAIL", f"{dur:.2f}s"): passed += 1
    except Exception as e: results["non_functional"]["NF-01"] = "FAIL"; log_test("NF-01", "Perf", "FAIL", str(e))

    # NF-02
    try:
        async def re(*a, **k): raise ConnectionError("N")
        cfg = MonitorConfig(max_retries=1)
        bld = AsyncMonitorGraphBuilder(cfg)
        with patch('httpx.AsyncClient') as mc:
            mc.return_value.__aenter__.return_value.get = re
            app = bld.build(use_checkpointer=False)
            try:
                res = await asyncio.wait_for(app.ainvoke({"retry_count": 0, "urls_to_check": ["https://x.com"]}), timeout=10)
                success = "error_messages" in res
            except: success = False
            results["non_functional"]["NF-02"] = "PASS" if success else "FAIL"
            if log_test("NF-02", "Stability", "PASS" if success else "FAIL", f"Graceful: {success}"): passed += 1
    except Exception as e: results["non_functional"]["NF-02"] = "FAIL"; log_test("NF-02", "Stab", "FAIL", str(e))

    # NF-03
    try:
        tf = "/tmp/nf3.json"
        if os.path.exists(tf): os.remove(tf)
        cfg = MonitorConfig(state_file=tf)
        bld = AsyncMonitorGraphBuilder(cfg)
        with patch('httpx.AsyncClient') as mc:
            mr = AsyncMock(); mr.status_code = 200; mr.json = AsyncMock(return_value={"CpuInfo": {"fTemp": [40], "uiLoad": [1]}, "MemoryInfo": {"MemoryLoad": "50%"}}); mr.text = "OK"; mr.raise_for_status = MagicMock(); mr.elapsed.total_seconds = MagicMock(return_value=0.1)
            mc.return_value.__aenter__.return_value.get = AsyncMock(return_value=mr)
            with patch('httpx.AsyncClient.get'):
                app = bld.build(use_checkpointer=False)
                await app.ainvoke({"retry_count": 0, "urls_to_check": ["https://x.com"]})
        success = os.path.exists(tf)
        if success:
            with open(tf) as f: data = json.load(f); success = "current_time" in data
        results["non_functional"]["NF-03"] = "PASS" if success else "FAIL"
        if log_test("NF-03", "Persistence", "PASS" if success else "FAIL", f"File: {success}"): passed += 1
        if os.path.exists(tf): os.remove(tf)
    except Exception as e: results["non_functional"]["NF-03"] = "FAIL"; log_test("NF-03", "Persist", "FAIL", str(e))

    print(f"\n📊 비기능적: {passed}/{total}\n")
    return passed == total

async def main():
    print("🚀 LangGraph 모니터링 시스템 전체 검증 시작\n" + "="*60)
    f = await verify_functional_blocks()
    w = await verify_workflows()
    n = await verify_non_functional()
    print("="*60 + "\n🏁 최종 검증 결과 요약\n" + "="*60)
    ok = f and w and n
    print(f"1. 기능 블록: {'✅ PASS' if f else '❌ FAIL'}")
    print(f"2. 워크플로우: {'✅ PASS' if w else '❌ FAIL'}")
    print(f"3. 비기능적:   {'✅ PASS' if n else '❌ FAIL'}")
    print("-"*60 + f"\n최종: {'✅ 전체 시스템 검증 완료 (100%)' if ok else '❌ 일부 실패'}\n")
    if ok: print("🎉 프로덕션 배포 준비 완료!")
    else: print("⚠️ 수정 필요")
    return ok

if __name__ == "__main__":
    asyncio.run(main())
