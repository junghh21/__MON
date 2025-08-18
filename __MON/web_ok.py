
import requests
from datetime import datetime
import subprocess
from __COMMON.globals import *

url_base = f"https://api.telegram.org/bot{bot_token}/sendmessage"
def send_error_to_telegram(message):
  params = {'chat_id': chat_id, 'text': datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + message}
  response = requests.get(url_base, params=params)

def check_web_jango_ok():
  url = "https://www.okkjc.co.kr:5001"  
  try:
    response = requests.get(url, verify=False)
    if response.status_code == 200:
      print(f"웹사이트 {url}에 정상적으로 접속했습니다.")
      send_error_to_telegram(f"웹사이트 {url}에 정상적으로 접속했습니다.")
    else:
      print(f"웹사이트 {url}에 접속할 수 없습니다. 상태 코드: {response.status_code}")
      send_error_to_telegram(f"웹사이트 {url}에 접속할 수 없습니다. 상태 코드: {response.status_code}")
  except requests.exceptions.RequestException as e:
    print(f"오류 발생: {e}")
    send_error_to_telegram(f"오류 발생: {e}")    
    try:
      result = subprocess.run(["C:\__PY\Run_Server.bat"], capture_output=True, text=True, check=True)
      send_error_to_telegram(result.stdout)
    except subprocess.CalledProcessError as e:
      send_error_to_telegram(f"Error executing shell script in background: {e.output}")

def check_web_temp():
  url = "https://www.okkjc.co.kr:5001/api/temp"
  try:
      response = requests.get(url, timeout=5, verify=False)
      response.raise_for_status()  # HTTP 오류 발생 시 예외
      data = response.json()
      print(data)
      data['CpuInfo']['fTemp'] = [int(a) for a in data['CpuInfo']['fTemp']]
      send_error_to_telegram(	f"\nTemp.: {str(data['CpuInfo']['fTemp'])}\n" \
                              f"Load: {str(data['CpuInfo']['uiLoad'])}\n" \
                              f"Mem Use: {data['MemoryInfo']['MemoryLoad']}")
  except requests.exceptions.HTTPError as errh:
      print("HTTP 오류:", errh)
  except requests.exceptions.ConnectionError as errc:
      print("연결 오류:", errc)
  except requests.exceptions.Timeout as errt:
      print("타임아웃:", errt)
  except requests.exceptions.RequestException as err:
      print("요청 오류:", err)