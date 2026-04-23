import sqlite3
import json
import glob
import os
import sys
from datetime import datetime

# ========== 智能導入 LanguageLoader ==========
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from modules.language_loader import LanguageLoader
else:
    from modules.language_loader import LanguageLoader

# ==========================================
# 設定區
# ==========================================
JSON_DIR = "user_data"
DB_PATH = os.path.join(JSON_DIR, "actitrack.db")

class DbSyncManager:
    def __init__(self, language='ZH_TW'):
        # 載入語言包
        self.lang = LanguageLoader('db_sync', language)
        
        # 確保 user_data 資料夾存在
        os.makedirs(JSON_DIR, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self._init_db()

    def _init_db(self):
        """初始化資料表"""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exercise_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                height REAL,
                weight REAL,
                age INTEGER,
                timestamp TEXT UNIQUE,
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
        self.conn.commit()

    def sync_json_to_sqlite(self):
        """【任務 1】將 JSON 資料匯入 SQLite"""
        # 🌟 修正：加上 print 並拔除多餘參數
        print(self.lang.log('info', 'task1_start'))
        
        json_files = glob.glob(os.path.join(JSON_DIR, "**/*.json"), recursive=True)
        # 過濾掉非資料的 JSON (例如 user_config.json)
        json_files = [f for f in json_files if "user_config" not in f and "user_detector_config" not in f]
        
        # 🌟 修正：用 f-string 將變數接在 log() 回傳的字串後面
        print(f"{self.lang.log('info', 'json_scanned')}: {len(json_files)}")

        cursor = self.conn.cursor()
        synced_count = 0
        skipped_count = 0

        for j_path in json_files:
            try:
                with open(j_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for session in data:
                    user_info = session.get("user_info", {})
                    username = user_info.get("username", "Unknown")
                    height = user_info.get("height", 0)
                    weight = user_info.get("weight", 0)
                    age = user_info.get("age", 0)
                    
                    for rec in session.get("exercise_records", []):
                        timestamp = rec.get("timestamp")
                        ex_name = rec.get("exercise_name")
                        
                        # 檢查是否已存在
                        cursor.execute('SELECT 1 FROM exercise_records WHERE timestamp = ? AND exercise_name = ?', (timestamp, ex_name))
                        if cursor.fetchone():
                            skipped_count += 1
                            continue
                            
                        body_wrong = rec.get("body_wrong")
                        bw_json = json.dumps(body_wrong, ensure_ascii=False) if body_wrong else None
                        
                        cursor.execute('''
                            INSERT INTO exercise_records 
                            (username, height, weight, age, timestamp, exercise_name, 
                             total_count, correct_count, wrong_count, accuracy, 
                             duration_sec, distance_m, body_wrong_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            username, height, weight, age, timestamp, ex_name,
                            rec.get("total_count", 0), rec.get("correct_count", 0), rec.get("wrong_count", 0),
                            rec.get("accuracy", 0.0), rec.get("duration_sec"), rec.get("distance_m"), bw_json
                        ))
                        synced_count += 1
            except Exception as e:
                # 🌟 修正：改用 f-string 組合
                print(f"{self.lang.log('error', 'read_failed')}: {j_path} ({e})")
                
        self.conn.commit()
        # 🌟 修正：加上 print()
        print(self.lang.log('success', 'task1_complete'))
        print(f"  ➜ {self.lang.get_message('db_inserted')}: {synced_count} | {self.lang.get_message('db_skipped')}: {skipped_count}")

    def export_sqlite_to_json(self):
        """【任務 2】將 SQLite 資料匯出成 JSON"""
        # 🌟 修正：加上 print()
        print(self.lang.log('info', 'task2_start'))
        
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM exercise_records')
        
        columns = [desc[0] for desc in cursor.description]
        records = [dict(zip(columns, row)) for row in cursor.fetchall()]

        new_json_count = 0
        
        for record_dict in records:
            ts_str = record_dict["timestamp"]
            try:
                dt_obj = datetime.strptime(ts_str, "%Y/%m/%d %H:%M:%S")
            except ValueError:
                continue
                
            folder_path = dt_obj.strftime("%Y/%m/%d")
            file_name = dt_obj.strftime("%H-%M-%S.json")
            
            target_dir = os.path.join(JSON_DIR, folder_path)
            target_filepath = os.path.join(target_dir, file_name)
            
            if os.path.exists(target_filepath):
                continue
                
            body_wrong_obj = {}
            if record_dict["body_wrong_json"]:
                try:
                    body_wrong_obj = json.loads(record_dict["body_wrong_json"])
                except:
                    pass
                    
            session_data = [{
                "user_info": {
                    "username": record_dict["username"],
                    "height": record_dict["height"],
                    "weight": record_dict["weight"],
                    "age": record_dict["age"]
                },
                "exercise_records": [
                    {
                        "timestamp": record_dict["timestamp"],
                        "exercise_name": record_dict["exercise_name"],
                        "total_count": record_dict["total_count"],
                        "correct_count": record_dict["correct_count"],
                        "wrong_count": record_dict["wrong_count"],
                        "accuracy": record_dict["accuracy"],
                        "duration_sec": record_dict["duration_sec"],
                        "distance_m": record_dict.get("distance_m"),
                        "body_wrong": body_wrong_obj
                    }
                ]
            }]
            
            os.makedirs(target_dir, exist_ok=True)
            try:
                with open(target_filepath, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, ensure_ascii=False, indent=4)
                new_json_count += 1
            except Exception as e:
                # 🌟 修正：改用 f-string 組合
                print(f"{self.lang.log('error', 'write_failed')}: {target_filepath} ({e})")

        # 🌟 修正：加上 print()
        print(self.lang.log('success', 'task2_complete'))
        print(f"  ➜ {self.lang.get_message('json_created')}: {new_json_count}")

    def close(self):
        self.conn.close()

# ==========================================
# 測試執行區
# ==========================================
if __name__ == "__main__":
    sync_manager = DbSyncManager() 
    # 🌟 修正：加上 print()
    print(sync_manager.lang.log('info', 'sync_start'))
    sync_manager.sync_json_to_sqlite()
    print("-" * 40)
    sync_manager.export_sqlite_to_json()
    sync_manager.close()