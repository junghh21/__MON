import os, sys, shutil
sys.path.append("../")
sys.path.append("./")

import threading
import schedule
import time
from datetime import datetime

#from __MON.temp_mon import capture_win_jango_ok
from __MON.web_ok import check_web_jango_ok

def job_1hour():  
  try:    
    print("job_1hour")
    check_web_jango_ok ()
    #capture_win_jango_ok("CORETEMP", None, 0, 280, 336, 76)    # HH32
    capture_win_jango_ok("CORETEMP", None, 0, 115, 344, 140)    # KJC333
  except Exception as e:
    print(f"job_1hour error: {e}")

if __name__ == "__main__":
  job_1hour()
  exit()
  #schedule.every().day.at("02:00").do(job_0200)
  #schedule.every().day.at("12:10").do(job_1210)
  schedule.every().hour.at(":01").do(job_1hour)
  while True:
    try:      
      current_time = datetime.now().time()
      print("Current Time:", current_time)
      schedule.run_pending()
      time.sleep(30)
    except KeyboardInterrupt:
      break
