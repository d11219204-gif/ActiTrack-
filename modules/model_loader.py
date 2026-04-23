import os
import urllib.request
import sys
import json
import shutil
import hashlib

# ========== 智能導入處理 ==========
if __name__ == "__main__":
    # 情況 1: 直接執行此檔案 (例如 python modules/model_loader.py)
    # 我們需要把專案根目錄加入 sys.path，這樣才能正確引用 modules
    
    # 取得當前檔案的絕對路徑
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 取得專案根目錄 (往上一層)
    project_root = os.path.dirname(current_dir)
    
    # 將根目錄加入 sys.path
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        
    # 現在可以從根目錄引用了
    from modules.language_loader import LanguageLoader
    
else:
    # 情況 2: 被其他模組引用 (例如 from modules.model_loader import ModelLoader)
    # 此時使用相對導入最安全
    from .language_loader import LanguageLoader


class ModelLoader:
    def __init__(self, language='ZH_TW'):
        """
        初始化模型管理器
        """
        self.lang = LanguageLoader('model_loader', language)
        self.model_dir = "models"
        self.save_dir = os.path.join(self.model_dir, "save")
        self.target_name = "pose_landmarker.task"
        self.info_file = os.path.join(self.model_dir, "model_info.json")
        
        # 定義模型清單
        self.models = {
            "1": {
                "id": "lite",
                "name": "Lite",
                "filename": "pose_landmarker_lite.task",
                "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
                "desc_key": "desc_lite"
            },
            "2": {
                "id": "full",
                "name": "Full",
                "filename": "pose_landmarker_full.task",
                "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
                "desc_key": "desc_full"
            },
            "3": {
                "id": "heavy",
                "name": "Heavy",
                "filename": "pose_landmarker_heavy.task",
                "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task",
                "desc_key": "desc_heavy"
            }
        }

    def _save_info(self, data):
        """儲存模型資訊 JSON"""
        with open(self.info_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _load_info(self):
        """讀取模型資訊 JSON"""
        if os.path.exists(self.info_file):
            try:
                with open(self.info_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return None
        return None

    def _report_progress(self, block_num, block_size, total_size):
        """下載進度條回呼函數"""
        downloaded = block_num * block_size
        if total_size > 0:
            percent = 100 * downloaded / total_size
            if percent > 100: percent = 100
            bar_length = 30
            filled = int(bar_length * percent // 100)
            bar = '█' * filled + '-' * (bar_length - filled)
            sys.stdout.write(f'\rProgress: |{bar}| {percent:.1f}%')
            sys.stdout.flush()

    def _backup_current(self):
        """備份當前使用的模型"""
        current_path = os.path.join(self.model_dir, self.target_name)
        if not os.path.exists(current_path):
            return

        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

        info = self._load_info()
        if info and 'filename' in info:
            backup_name = info['filename']
        else:
            backup_name = f"unknown_{int(os.path.getmtime(current_path))}.task"
        
        backup_path = os.path.join(self.save_dir, backup_name)
        print(f"{self.lang.log('info', 'backup_start')}: {backup_name}")
        
        # 移動檔案
        if os.path.exists(backup_path):
            os.remove(backup_path) # 如果備份已存在，先刪除舊的
        shutil.move(current_path, backup_path)

    def _restore_backup(self, filename):
        """嘗試從 save 資料夾還原"""
        backup_path = os.path.join(self.save_dir, filename)
        target_path = os.path.join(self.model_dir, self.target_name)
        
        if os.path.exists(backup_path):
            print(f"{self.lang.log('info', 'restore_start')}: {filename}")
            if os.path.exists(target_path):
                os.remove(target_path)
            shutil.copy2(backup_path, target_path) # 使用 copy 保留備份
            return True
        return False

    def check_and_download_model(self):
        """
        主邏輯：檢查模型狀態，並處理下載或切換
        Returns:
            str: 模型檔案的絕對路徑
        """
        # 1. 初始化目錄
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)
            print(self.lang.log('info', 'directory_created'))
            
        target_path = os.path.join(self.model_dir, self.target_name)
        current_info = self._load_info()
        
        # 2. 顯示介面
        print("\n" + "="*50)
        print(f" {self.lang.get_message('title')}")
        print("="*50)
        
        # 顯示當前模型
        curr_msg = self.lang.get_message('current_model')
        if os.path.exists(target_path):
            model_name = current_info['name'] if current_info else "Unknown"
            print(f"{curr_msg}: \033[92m{model_name}\033[0m")
        else:
            print(f"{curr_msg}: \033[91m{self.lang.get_message('model_none')}\033[0m")
            
        print("-" * 50)
        print(f"{self.lang.get_message('model_list')}:")
        
        for k, v in self.models.items():
            prefix = " "
            if current_info and current_info.get('id') == v['id']:
                prefix = "*" # 標記當前
            
            # 取得多語言描述
            desc = self.lang.get_message(v['desc_key'])
            print(f"{prefix}[{k}] {v['name']}")
            print(f"     {desc}")
            
        print("="*50)
        
        # 3. 使用者互動
        if os.path.exists(target_path):
            prompt = f"{self.lang.get_message('select_prompt_switch')}: "
        else:
            prompt = f"{self.lang.get_message('select_prompt_download')}: "
            
        choice = input(prompt).strip()
        
        # 處理空輸入 (跳過或使用預設)
        if not choice:
            if os.path.exists(target_path):
                print(self.lang.log('info', 'keep_current'))
                return target_path
            else:
                choice = "2" # 預設下載 Full
        
        # 檢查輸入有效性
        if choice not in self.models:
            if os.path.exists(target_path):
                print(self.lang.log('warning', 'cancel_switch'))
                return target_path
            choice = "2"
            
        selected = self.models[choice]
        
        # 檢查是否重複選擇
        if current_info and current_info.get('id') == selected['id'] and os.path.exists(target_path):
            print(self.lang.log('info', 'already_using'))
            return target_path
            
        # 4. 執行切換/下載
        # Step A: 備份舊的
        if os.path.exists(target_path):
            self._backup_current()
            
        # Step B: 嘗試還原
        if not self._restore_backup(selected['filename']):
            # Step C: 下載
            print(f"\n{self.lang.get_message('download_start')}: {selected['name']} ...")
            try:
                temp_path, _ = urllib.request.urlretrieve(
                    selected['url'],
                    filename=None,
                    reporthook=self._report_progress
                )
                print(f"\n{self.lang.get_message('download_complete')}")
                shutil.move(temp_path, target_path)
            except Exception as e:
                print(f"\n{self.lang.log('error', 'download_failed')}: {e}")
                # 簡單錯誤處理：程式終止，讓使用者檢查網路
                sys.exit(1)
                
        # Step D: 更新資訊
        new_info = {
            "id": selected['id'],
            "name": selected['name'],
            "filename": selected['filename'],
            "url": selected['url'],
            "last_updated": os.path.getmtime(target_path)
        }
        self._save_info(new_info)
        
        print(f"{self.lang.log('success', 'switch_success')}: {selected['name']}")
        return target_path

    def get_model_path_silent(self):
        """
        安靜檢查模型是否存在
        Returns:
            str: 模型路徑 (如果存在)
            None: 如果不存在
        """
        target_path = os.path.join(self.model_dir, self.target_name)
        if os.path.exists(target_path):
            # 這裡可以加一個簡單的 Log，但不要阻斷流程
            current_info = self._load_info()
            model_name = current_info['name'] if current_info else "Unknown"
            # 只有在非 UI 模式下才 print，避免干擾主畫面
            # print(f"Model found: {model_name}") 
            return target_path
        return None

    def switch_model(self, choice):
        """
        供網頁 API 呼叫的非互動式模型切換邏輯
        """
        if choice not in self.models:
            raise ValueError(f"無效的模型選項: {choice}")
            
        selected = self.models[choice]
        target_path = os.path.join(self.model_dir, self.target_name)
        current_info = self._load_info()
        
        # 1. 檢查是否已經是目標模型，是的話直接返回
        if current_info and current_info.get('id') == selected['id'] and os.path.exists(target_path):
            return target_path
            
        # 2. 備份舊模型 (直接呼叫原本寫好的功能)
        if os.path.exists(target_path):
            self._backup_current()
            
        # 3. 嘗試從備份還原
        if not self._restore_backup(selected['filename']):
            # 4. 如果沒有備份，則執行下載
            print(f"API 觸發下載模型: {selected['name']} ...")
            # 這裡不使用進度條，避免 API 執行緒卡住
            temp_path, _ = urllib.request.urlretrieve(selected['url'], filename=None)
            shutil.move(temp_path, target_path)
                
        # 5. 更新模型資訊 JSON
        new_info = {
            "id": selected['id'],
            "name": selected['name'],
            "filename": selected['filename'],
            "url": selected['url'],
            "last_updated": os.path.getmtime(target_path)
        }
        self._save_info(new_info)
        
        return target_path
        
# 方便直接執行的接口
if __name__ == "__main__":
    # 預設使用繁體中文測試
    loader = ModelLoader(language='ZH_TW')
    loader.check_and_download_model()
