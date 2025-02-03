import os, sys, shutil
sys.path.append("../")
sys.path.append("./")

import win32gui
import win32ui
import win32con
from PIL import Image
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
import io
import requests
from __COMMON.globals import *

def capture_win_jango_ok(cls_name, title, clip_left, clip_top, clip_width, clip_height):
  hwnd = win32gui.FindWindow(cls_name, title)
  if hwnd == 0:
    exception = Exception(f"{cls_name} {title} not found.")
    raise exception
  
  window_dc = win32gui.GetWindowDC(hwnd)
  dc_obj = win32ui.CreateDCFromHandle(window_dc)
  mem_dc = dc_obj.CreateCompatibleDC()
  left, top, right, bot = win32gui.GetWindowRect(hwnd)
  width = right - left
  height = bot - top
  bitmap = win32ui.CreateBitmap()
  bitmap.CreateCompatibleBitmap(dc_obj, width, height)
  mem_dc.SelectObject(bitmap)
  mem_dc.BitBlt((0, 0), (width, height), dc_obj, (0, 0), win32con.SRCCOPY)
  
  raw = bitmap.GetBitmapBits(True)
  image = Image.frombuffer('RGB', (width, height), raw, 'raw', 'BGRX', 0, 1)
  clipped_image = image.crop((clip_left, clip_top, clip_left + clip_width, clip_top + clip_height))
  clipped_image.save('clipped_screenshot_dc.png', format='PNG')

  mem_dc.DeleteDC()
  dc_obj.DeleteDC()
  win32gui.ReleaseDC(hwnd, window_dc)
  win32gui.DeleteObject(bitmap.GetHandle())
  '''
  text = pytesseract.image_to_string(clipped_image)
  print(text)
  '''
  
  io_buf = io.BytesIO()
  clipped_image.save(io_buf, format='PNG')
  url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
  response = requests.post(url, data={'chat_id': chat_id}, files={'photo': io_buf.getvalue()})
  print(response.json())