# 檔名: modules/jsonwriter.py

import os
import json
import sys
from datetime import datetime

# ========== 智能導入處理 ==========
if __name__ == "__main__":
    # 直接執行時，加入根目錄到 sys.path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from modules.language_loader import LanguageLoader
else:
    # 被引用時，使用相對路徑
    from .language_loader import LanguageLoader

class JsonWriter:
    def __init__(self, language='ZH_TW'):
        """
        初始化 JSON 寫入器
        Args:
            language: 語言代碼 (預設 'ZH_TW')
        """
        self.lang = LanguageLoader('jsonwriter', language)

    def log_exercise(self, user_info, exercise_name, count, correct, wrong, base_folder="user_data", extra_data=None):
        """
        記錄使用者運動資料，依照日期分類資料夾，並以時間命名檔案。
        
        Args:
            user_info: 使用者資訊字典
            exercise_name: 運動名稱 (建議傳入已翻譯的名稱，或者 key)
            count: 總次數
            correct: 正確次數
            wrong: 錯誤次數
            base_folder: 基礎資料夾 (預設 "user_data")
            extra_data: 額外的資料字典
            
        Returns:
            str: 檔案路徑 (成功時) 或 None (失敗時)
        """
        
        # 1. 準備時間與路徑
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        time_str = now.strftime("%H-%M-%S")
        timestamp_full = now.strftime("%Y/%m/%d %H:%M:%S")

        # 建立目錄結構: user_data/2026/02/09/
        target_dir = os.path.join(base_folder, year, month, day)
        os.makedirs(target_dir, exist_ok=True)

        # 檔案路徑: user_data/2026/02/09/21-30-05.json
        file_name = f"{time_str}.json"
        file_path = os.path.join(target_dir, file_name)

        # 2. 準備 JSON 資料內容
        exercise_record = {
            "timestamp": timestamp_full,
            "exercise_name": exercise_name,
            "total_count": count,
            "correct_count": correct,
            "wrong_count": wrong,
            "accuracy": round((correct / count * 100), 2) if count > 0 else 0
        }

        # [新增] 如果有額外數據(例如身體錯誤部位)，直接合併進紀錄中
        if extra_data and isinstance(extra_data, dict):
            exercise_record.update(extra_data)

        # 完整的資料結構 (包含使用者資訊)
        # 注意: 這裡依照原始邏輯，每次存檔都是一個全新的 List
        log_data = [{
            "user_info": user_info,
            "exercise_records": [exercise_record]
        }]

        # 3. 寫入檔案
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=4)
            
            # 使用 LanguageLoader 輸出標準化訊息
            # 格式: [紀錄模組:成功] 運動紀錄已儲存至: user_data/...
            print(f"{self.lang.log('success', 'save_success')}: {file_path}")
            
            # 額外資訊顯示 (Time, Item...)
            # 這裡為了排版漂亮，我們手動拼湊字串，但標籤來自語言檔
            lbl_time = self.lang.get_message('time')
            lbl_item = self.lang.get_message('item')
            lbl_total = self.lang.get_message('total')
            lbl_ok = self.lang.get_message('ok')
            
            print(f"  {lbl_time}: {timestamp_full}")
            print(f"  {lbl_item}: {exercise_name} ({lbl_total}: {count}, {lbl_ok}: {correct})")
            
            return file_path

        except Exception as e:
            print(f"{self.lang.log('error', 'save_failed')}: {e}")
            return None

# ====================================================================
# 測試區
# ====================================================================
if __name__ == "__main__":
    # 測試中文
    writer_zh = JsonWriter('ZH_TW')
    sample_user = {"username": "TestUser", "height": 175, "weight": 70}
    writer_zh.log_exercise(sample_user, "測試運動", 10, 8, 2)
    
    print("-" * 30)
    
    # 測試英文
    #writer_en = JsonWriter('US_EN')
    #writer_en.log_exercise(sample_user, "TestExercise", 20, 15, 5)
