
import requests
from datetime import datetime
import subprocess
from __COMMON.globals import *

url_base = f"https://api.telegram.org/bot{bot_token}/sendmessage"
def send_error_to_telegram(message):
  params = {'chat_id': chat_id, 'text': datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + message}
  response = requests.get(url_base, params=params)

url = "https://localhost:5001"  
def check_web_jango_ok():
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