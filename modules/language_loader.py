# 檔名: modules/language_loader.py

import json
import os
from pathlib import Path

class LanguageLoader:
    """
    多語言載入器
    負責根據模組名稱自動載入對應的語言檔案，並支援自身的多語言顯示。
    """
    _announced_files = set()
    def __init__(self, module_name, language='ZH_TW', debug=True): # 新增 debug 參數
        """
        初始化語言載入器
        
        Args:
            module_name: 模組檔案名稱 (不含.py，例如 'body_jump_main')
            language: 語言代碼 (預設 'ZH_TW')
            debug: 是否顯示日誌訊息 (預設 True)
        """
        self.module_name = module_name
        self.target_language = language
        self.debug = debug # 儲存 debug 狀態
        self.translations = {}
        
        # 載入 LanguageLoader 自身的翻譯 (優先讀檔，失敗則用內建)
        self._loader_msgs = self._load_loader_messages()
        
        # 載入目標模組的翻譯
        self._load_language_file()

    def _load_loader_messages(self):
        """
        載入 LanguageLoader 自身的翻譯訊息
        優先級: 
        1. language/{target}/language_loader.json
        2. language/ZH_TW/language_loader.json (Fallback File)
        3. 內建字典 (Hardcoded Fallback)
        """
        
        # 內建預設值 (最後防線)
        internal_msgs = {
            "module_name": "語言載入器",
            "log_types": {
                "info": "資訊",
                "error": "錯誤",
                "success": "成功",
                "warning": "警告"
            },
            "messages": {
                "load_success": "成功載入語言檔",
                "file_not_found": "找不到語言檔",
                "json_error": "JSON 格式錯誤"
            }
        }
        
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent
        
        # 1. 嘗試載入目標語言 (例如 JP)
        target_file = project_root / 'language' / self.target_language / 'language_loader.json'
        if target_file.exists():
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass # 載入失敗，繼續往下嘗試

        # 2. 嘗試載入預設語言 (ZH_TW)
        fallback_file = project_root / 'language' / 'ZH_TW' / 'language_loader.json'
        if fallback_file.exists():
            try:
                with open(fallback_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
                
        # 3. 使用內建字典
        return internal_msgs

    def _internal_log(self, log_type, message_key, extra_info=""):
        """LanguageLoader 自己的日誌輸出"""
        # 🌟 根據 debug 決定是否要印出
        if not self.debug:
            return

        # 取得自身翻譯
        module = self._loader_msgs.get('module_name', 'LanguageLoader')
        
        # 取得 Log 類型 (Info/Error...)
        log_types = self._loader_msgs.get('log_types', {})
        level = log_types.get(log_type, log_type.upper())
        
        # 取得訊息內容
        msgs = self._loader_msgs.get('messages', {})
        message = msgs.get(message_key, message_key)
        
        print(f"[{module}:{level}] {message} {extra_info}")

    def _load_language_file(self):
        """載入目標模組的語言檔案"""
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent
        
        lang_file = project_root / 'language' / self.target_language / f'{self.module_name}.json'
        
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
            
            # 使用 _internal_log 輸出成功訊息 (會受 self.debug 控制)
            #self._internal_log('info', 'load_success', f"({lang_file.name})")

            # 👇 將原本的 log 替換成這三行：檢查是否已經廣播過
            file_path_str = str(lang_file)
            if file_path_str not in LanguageLoader._announced_files:
                self._internal_log('info', 'load_success', f"({lang_file.name})")
                LanguageLoader._announced_files.add(file_path_str)
            
        except FileNotFoundError:
            # 嚴重錯誤：找不到語言檔
            # 為了安全，這裡強制顯示 "英文 / 中文" 雙語報錯，確保開發者能看懂
            
            err_msg_en = "Language file not found"
            err_msg_zh = "找不到語言檔"
            
            # 嘗試從目前設定取得 (可能是日文)
            err_msg_current = self._loader_msgs.get('messages', {}).get('file_not_found', '')
            
            display_msg = f"{err_msg_en} / {err_msg_zh}"
            if err_msg_current and err_msg_current not in [err_msg_en, err_msg_zh]:
                display_msg += f" / {err_msg_current}"
            
            # 🌟 嚴重報錯也受 debug 控制
            if self.debug:
                print(f"[LanguageLoader:ERROR] {display_msg}: {lang_file}")
            
            # 設定空字典避免崩潰
            self.translations = {
                "module_name": self.module_name,
                "log_types": {"info": "INFO", "error": "ERROR", "success": "SUCCESS", "warning": "WARNING"},
                "messages": {}
            }
            
        except json.JSONDecodeError as e:
            # 此 log 使用 _internal_log，已受 debug 控制
            self._internal_log('error', 'json_error', f"- {e}")
            self.translations = {}

    def get_module_name(self):
        """取得模組名稱的翻譯"""
        return self.translations.get('module_name', self.module_name)
    
    def get_log_type(self, log_type):
        """取得日誌類型的翻譯"""
        return self.translations.get('log_types', {}).get(log_type, log_type.upper())

    def get_message(self, key):
        """取得訊息文字"""
        return self.translations.get('messages', {}).get(key, f"[Missing: {key}]")

    def log(self, log_type, message_key):
        """
        統一的日誌輸出格式
        Returns: "{模組名稱}:{層級} {訊息}"
        """
        module = self.get_module_name()
        log_level = self.get_log_type(log_type)
        message = self.get_message(message_key)
        
        return f"{module}:{log_level} {message}"