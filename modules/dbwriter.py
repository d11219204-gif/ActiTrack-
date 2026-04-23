# 檔名: modules/dbwriter.py

import os
import sqlite3
import json
import sys
from datetime import datetime

# 依照你的專案結構進行智能導入
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from modules.language_loader import LanguageLoader
else:
    from .language_loader import LanguageLoader

class DbWriter:
    def __init__(self, language='ZH_TW', db_path="user_data/actitrack.db"):
        """
        初始化 SQLite 寫入器，支援多國語言日誌
        """
        self.db_path = db_path
        self.lang = LanguageLoader('dbwriter', language)
        
        # 確保目錄存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """ 初始化資料庫結構 """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 方案 A: 使用 TEXT 欄位 (body_wrong_json) 儲存變動的項目
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS exercise_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    height REAL,
                    weight REAL,
                    age INTEGER,
                    timestamp TEXT,
                    exercise_name TEXT,
                    total_count INTEGER,
                    correct_count INTEGER,
                    wrong_count INTEGER,
                    accuracy REAL,
                    duration_sec REAL,
                    distance_m REAL,
                    body_wrong_json TEXT
                )
            ''')
            conn.commit()
            conn.close()
            # self.lang.log('success', 'db_init_success')
        except Exception as e:
            self.lang.log('error', 'db_init_failed', str(e))

    def log_exercise(self, user_info, exercise_name, count, correct, wrong, extra_data=None):
        """ 寫入運動紀錄 """
        try:
            timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            username = user_info.get("username", "Unknown")
            height = user_info.get("height", 0)
            weight = user_info.get("weight", 0)
            age = user_info.get("age", 0)
            accuracy = round((correct / count * 100), 2) if count > 0 else 0
            
            duration_sec = None
            distance_m = None
            body_wrong_json = None
            
            if extra_data:
                duration_sec = extra_data.get('duration_sec')
                distance_m = extra_data.get('distance_m')
                # 處理變動項目: 將 body_wrong 整個字典轉為 JSON 字串
                if 'body_wrong' in extra_data:
                    body_wrong_json = json.dumps(extra_data['body_wrong'], ensure_ascii=False)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO exercise_records 
                (username, height, weight, age, timestamp, exercise_name, 
                 total_count, correct_count, wrong_count, accuracy, 
                 duration_sec, distance_m, body_wrong_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (username, height, weight, age, timestamp, exercise_name, 
                  count, correct, wrong, accuracy, duration_sec, distance_m, body_wrong_json))
            
            conn.commit()
            conn.close()
            
            # 使用 i18n 輸出成功訊息
            print(f"{self.lang.log('success', 'save_success')}: {self.db_path}")
            return True
            
        except Exception as e:
            self.lang.log('error', 'save_failed', str(e))
            return False