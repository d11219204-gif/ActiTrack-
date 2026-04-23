# 檔名: modules/base_detector.py

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont # 需要先 pip install pillow
import platform
import os

class BaseDetector:
    def __init__(self):
        self.count = 0
        self.correct = 0
        self.wrong = 0
        
        # 快取字體物件，避免重複載入
        self._font_cache = {}
        
    def reset_state(self):
        """
        重置動作狀態 (由子類別實作)
        """
        pass

    def draw_text(self, img, text, pos, color=(255, 255, 255), size=32):
        """
        [通用] 繪製多語言文字 (支援中文)
        
        Args:
            img: OpenCV 影像 (BGR)
            text: 文字內容
            pos: (x, y) 座標
            color: (B, G, R) 顏色 tuple
            size: 字體大小
            
        Returns:
            繪製後的 img (OpenCV 格式)
        """
        # 1. 將 OpenCV (BGR) 轉為 PIL (RGB)
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        
        # 2. 取得或載入字體
        font = self._get_font(size)
        
        # 3. 繪製文字 (PIL 使用 RGB 顏色，所以要將 BGR 轉 RGB)
        # OpenCV 的 color 是 (B, G, R)，PIL 需要 (R, G, B)
        rgb_color = color[::-1]
        draw.text(pos, text, font=font, fill=rgb_color)
        
        # 4. 將 PIL (RGB) 轉回 OpenCV (BGR)
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    def _get_font(self, size):
        """
        [內部] 智能取得系統字體
        """
        if size in self._font_cache:
            return self._font_cache[size]
        
        system = platform.system()
        font = None
        
        try:
            if system == "Windows":
                # Windows 優先嘗試微軟正黑體
                try:
                    font = ImageFont.truetype("msjh.ttc", size)
                except:
                    font = ImageFont.truetype("arial.ttf", size)
                    
            elif system == "Linux":
                # Linux 嘗試 Noto Sans CJK 或常見中文字體
                # Termux 或常見 Linux 發行版路徑
                font_paths = [
                    "/system/fonts/NotoSansCJK-Regular.ttc", # Android/Termux
                    "/usr/share/fonts/noto/NotoSansCJK-Regular.ttc",
                    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                    "NotoSansCJK-Regular.ttc",
                    "DroidSansFallback.ttf"
                ]
                for path in font_paths:
                    try:
                        if os.path.exists(path):
                            font = ImageFont.truetype(path, size)
                            break
                        # 嘗試直接用名稱載入
                        font = ImageFont.truetype(path.split('/')[-1], size)
                        break
                    except:
                        continue
                        
            elif system == "Darwin": # macOS
                try:
                    font = ImageFont.truetype("PingFang.ttc", size)
                except:
                    font = ImageFont.truetype("Arial Unicode.ttf", size)
            
            # 如果上面都失敗，使用 PIL 預設 (不支援中文，但不會崩潰)
            if font is None:
                font = ImageFont.load_default()
                
        except Exception as e:
            print(f"[Warning] Font loading failed: {e}, using default.")
            font = ImageFont.load_default()
            
        self._font_cache[size] = font
        return font
