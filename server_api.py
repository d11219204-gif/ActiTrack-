import os
import json
import glob
import shutil
import time
import threading
import io
import sys
from datetime import datetime
import cv2
import numpy as np
import sqlite3

from modules.model_loader import ModelLoader
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse
# ==========================================
# 從主程式 server.py 引入共用狀態與核心方法
# ==========================================
from server import state, web_camera_loop, load_config, get_localized_exercise_name

# 由於 API 路由中有直接用到 LanguageLoader，因此也需要將它引入
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))
from modules.language_loader import LanguageLoader
from modules.db_sync import DbSyncManager

# --- server_api.py 開頭 ---
JSON_DIR = os.path.join('HTML', 'JS', 'json')
USER_CONFIG_PATH = os.path.join(JSON_DIR, 'user_config.json')
USER_DETECTOR_CONFIG_PATH = os.path.join(JSON_DIR, 'user_detector_config.json')
USER_DATA_PROFILE_DIR = os.path.join(JSON_DIR, 'User_data_profile')

# 確保目錄存在
for directory in [JSON_DIR, USER_DATA_PROFILE_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# 確保目錄存在
if not os.path.exists(JSON_DIR):
    os.makedirs(JSON_DIR)

# 建立 FastAPI Router
router = APIRouter()

@router.get("/")
def redirect_to_home():
    return RedirectResponse(url="/ActiTrack_Interface.html")


@router.get("/api/sports_menu")
def get_sports_menu():
    """ 供前端動態生成左側 HTML 選單 """
    config_data = load_config()
    
    # 【修正 1】跟隨當前伺服器狀態的語言，而不是死板的 config 預設值
    global_language = state.language 
    
    menu = []
    for d_cfg in config_data.get('detectors', []):
        if d_cfg.get('enabled', False):
            module_name = d_cfg['module'].split('.')[-1]
            display_name = get_localized_exercise_name(d_cfg['class'], state.language)            
            
            # 【修正 2】直接重複利用已經寫好的 LanguageLoader 工具
            try:
                # 實例化語言載入器 (它會自動處理正確的絕對路徑)
                lang_loader = LanguageLoader(module_name, global_language)
                # 取得該模組在 json 裡面的 "module_name"
                display_name = lang_loader.get_module_name()
            except Exception as e:
                # 如果找不到語言檔或發生錯誤，則保持預設的 display_name (容錯處理)
                print(f"選單語言載入失敗 ({module_name}): {e}")
                    
            menu.append({
                "class_name": d_cfg['class'],
                "display_name": display_name
            })
            
    # 【修正 3】明確指定 content 參數
    return JSONResponse(content=menu)


@router.get("/api/get_cameras")
def get_cameras():
    """ 掃描可用的攝影機清單 """
    available_cameras = []
    # 掃描 0~4 號鏡頭 (範圍到 10 個)
    for i in range(10):
        cap = None
        try:
            # 嘗試開啟鏡頭
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) if os.name == 'nt' else cv2.VideoCapture(i)
            
            if cap.isOpened():
                # 【關鍵防呆】試著讀取一張畫面，確認這不是壞掉的頻道或是被佔用的鏡頭
                ret, _ = cap.read()
                if ret:
                    available_cameras.append({"id": i, "name": f"攝像頭 {i}"})
        except Exception as e:
            print(f"[Server] 掃描鏡頭 {i} 時發生例外，已略過: {e}")
        finally:
            # 確保不管有沒有出錯，都會安全釋放資源
            if cap is not None:
                try:
                    cap.release()
                except:
                    pass

    return JSONResponse(content=available_cameras)


@router.post("/api/start")
def start_detection(mode: str = "auto", camera_id: int = -1):
    camera_needs_restart = False
    
    # 第一步：先取得鎖，只負責「通知」舊迴圈停止，然後立刻放開鎖
    with state.lock: 
        if state.camera_active:
            state.is_running = False  
            camera_needs_restart = True
            
    # 第二步：在「鎖的範圍外」等待舊迴圈結束
    if camera_needs_restart:
        wait_time = 0
        while state.camera_active and wait_time < 3.0:
            time.sleep(0.1)
            wait_time += 0.1
        if state.camera_active:
            print("[Server] ⚠️ 警告: 舊鏡頭未能在3秒內釋放，強制重啟可能會報錯")
            
    # 第三步：重新取得鎖，準備啟動新迴圈
    with state.lock:
        # ★★★ 新增防護機制：如果這段期間已經有別的重整請求搶先啟動了，就直接忽略！ ★★★
        if state.camera_active and state.is_running:
            print("[Server] 🛡️ 攔截到重複的啟動請求 (連續重整)，已安全忽略")
            return {"status": "ignored", "reason": "already_starting", "mode": mode}

        state.is_running = True
        state.camera_active = True
        state.locked_idx = -1
        state.detectors = []
        state.frame_bytes = None 
        
        t = threading.Thread(target=web_camera_loop, args=(mode, camera_id), daemon=True)
        t.start()
        return {"status": "started", "mode": mode, "camera_id": camera_id}
    

@router.post("/api/stop")
def stop_detection():
    state.is_running = False
    # 後端迴圈會自己優雅關閉，無需 time.sleep 卡死 API 回應
    return {"status": "stopped_and_saved"}


@router.post("/api/set_user")
def set_user(username: str = "WebUser", height: int = 170, weight: int = 70):
    state.user_info = {"username": username, "height": height, "weight": weight}
    return {"status": "ok", "user_info": state.user_info}


# ==========================================
# ★ 解決「卡成 PPT」的關鍵修改：影像串流路由
# ==========================================
@router.get("/video_feed")
def video_feed():
    def iter_frames():
        while state.is_running:
            # ★ 關鍵修改：使用 condition.wait 等待最新畫面，而非無腦 time.sleep(0.04)
            with state.frame_condition:
                # 設定 timeout 以免後端卡死時串流無法正常退出
                if not state.frame_condition.wait(timeout=0.1):
                    continue
                frame_data = state.frame_bytes
            
            # 將最新鮮的 frame 送給前端
            if frame_data:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
                
        # 迴圈結束後傳送黑幕
        black_frame = cv2.imencode('.jpg', np.zeros((480, 640, 3), dtype=np.uint8))[1].tobytes()
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + black_frame + b'\r\n')

    return StreamingResponse(iter_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/api/status")
def get_status():
    state.last_api_access = time.time() 
    if not state.is_running:
        return JSONResponse({"locked_mode": "尚未啟動", "main_count": 0, "main_wrong": 0, "details": []})

    all_stats = []
    locked_name = "偵測中..."
    main_count = 0
    main_wrong = 0

    for idx, d in enumerate(state.detectors):
        is_running = d['is_running']
        correct = getattr(d['instance'], 'correct', 0)
        wrong = getattr(d['instance'], 'wrong', 0)
        val = round(d['instance'].total_distance_cm / 100, 1) if is_running else d['instance'].count
        is_locked = (idx == state.locked_idx)

        if is_locked:
            locked_name = d['label']
            main_count = val if is_running else correct
            main_wrong = 0 if is_running else wrong

        all_stats.append({
            "class_name": d['class_name'],  # ★ 加上這行，讓前端知道這是哪個運動
            "label": d['label'],
            "value": val,
            "correct": 0 if is_running else correct,
            "wrong": 0 if is_running else wrong,
            "is_running": is_running,
            "active": d['active'],
            "locked": is_locked,
        })

    return JSONResponse({"locked_mode": locked_name, "main_count": main_count, "main_wrong": main_wrong, "details": all_stats})


@router.post("/api/save_profile")
async def save_profile(request: Request):
    """
    【生理歷史紀錄 API】
    用途：儲存詳細的生理數據（體脂、肌肉、BMR 等）到歷史日期路徑下。
    """
    try:
        data = await request.json()
        
        # === 🔧 修正 Bug：將傳來的新版單層 JSON 格式，轉換回舊版巢狀陣列格式 ===
        formatted_data = [
            {
                "basic_info": {
                    "height_cm": data.get("height"),
                    "weight_kg": data.get("weight")
                },
                "optional_info": {
                    "age": data.get("age"),
                    "dob": data.get("dob"),
                    "body_fat_percent": data.get("body_fat"),
                    "skeletal_muscle_kg": data.get("muscle"),
                    "bmr_kcal": data.get("bmr")
                },
                # 若前端有傳時間就用前端的，沒有則在此處自動生成
                "last_updated": data.get("update_time") or datetime.now().strftime("%Y/%m/%d %p%I:%M:%S").replace("AM", "上午").replace("PM", "下午")
            }
        ]
        
        # 取得當前時間並動態建立路徑 (統一使用 USER_DATA_PROFILE_DIR)
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        time_str = now.strftime("%H-%M-%S")
        save_dir = os.path.join(USER_DATA_PROFILE_DIR, year, month, day)
        os.makedirs(save_dir, exist_ok=True)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        file_path = os.path.join(save_dir, f"{time_str}.json")
        
        # ⚠️ 注意這裡改為寫入 formatted_data
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(formatted_data, f, ensure_ascii=False, indent=4)
            
        return {"status": "success", "file_path": file_path}
    except Exception as e:
        print(f"儲存歷史生理紀錄發生錯誤: {e}")
        return {"status": "error", "message": str(e)}
    
@router.get("/api/get_records")
def get_records(source: str = "hybrid"):
    """
    獲取運動紀錄 API
    :param source: 'json' (僅讀取 JSON), 'sql' (僅讀取 DB), 'hybrid' (兩者合併，JSON 優先)
    """
    # ----------------------------------------
    # 輔助函式 1：讀取既有 JSON 檔案
    # ----------------------------------------
    def get_json_data():
        records = []
        search_path = os.path.join("user_data", "**","**","**", "*.json")
        for filepath in glob.glob(search_path):            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        records.extend(data)
                    else:
                        records.append(data)
            except Exception as e:
                print(f"[API] 讀取 JSON 失敗 {filepath}: {e}")
        return records

    # ----------------------------------------
    # 輔助函式 2：讀取 SQLite 資料庫
    # ----------------------------------------
    def get_sql_data():
        db_path = "user_data/actitrack.db"
        if not os.path.exists(db_path):
            return []
        
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row  # 讓結果可以用 dict 方式存取
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM exercise_records")
            rows = cursor.fetchall()
            conn.close()
            
            sql_records = []
            for row in rows:
                # 解析變動的 body_wrong_json
                body_wrong = {}
                if row["body_wrong_json"]:
                    try:
                        body_wrong = json.loads(row["body_wrong_json"])
                    except json.JSONDecodeError:
                        pass
                
                # 組裝成前端習慣的格式
                record_item = {
                    "timestamp": row["timestamp"],
                    "exercise_name": row["exercise_name"],
                    "total_count": row["total_count"],
                    "correct_count": row["correct_count"],
                    "wrong_count": row["wrong_count"],
                    "accuracy": row["accuracy"],
                    "duration_sec": row["duration_sec"],
                    "distance_m": row["distance_m"],
                    "body_wrong": body_wrong
                }
                
                # 包裝進 exercise_records 陣列中
                sql_records.append({
                    "user_info": {"username": row["username"]}, # 簡化 user_info
                    "exercise_records": [record_item]
                })
            return sql_records
        except Exception as e:
            print(f"[API] 讀取 SQL 失敗: {e}")
            return []

    # ----------------------------------------
    # 核心邏輯：依照 source 決定回傳內容
    # ----------------------------------------
    if source == "json":
        return JSONResponse(content=get_json_data())
    
    elif source == "sql":
        return JSONResponse(content=get_sql_data())
    
    else:  # 'hybrid' 模式 (預設)
        json_data = get_json_data()
        sql_data = get_sql_data()
        
        # 使用 timestamp 作為錨點進行合併 (Deduplication)
        merged_dict = {}
        
        # 1. 先放入 SQL 資料
        for file_obj in sql_data:
            for rec in file_obj.get("exercise_records", []):
                ts = rec.get("timestamp")
                if ts:
                    merged_dict[ts] = rec
                    
        # 2. 再放入 JSON 資料 (若時間相同，會覆寫 SQL 的資料)
        for file_obj in json_data:
            for rec in file_obj.get("exercise_records", []):
                ts = rec.get("timestamp")
                if ts:
                    merged_dict[ts] = rec

        # 將合併後的單筆紀錄，重新包裝回前端期待的外層結構
        final_payload = [{
            "exercise_records": list(merged_dict.values())
        }]

        return JSONResponse(content=final_payload)

@router.post("/api/toggle_skeleton")
def toggle_skeleton(enable: bool):
    state.show_skeleton = enable
    return {"status": "ok", "enabled": enable}


@router.get("/api/get_user_config")
def get_user_config():
    config_path = os.path.join("HTML", "JS", "json", "user_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"username": "User"}


@router.post("/api/save_user_config")
async def save_user_config(request: Request):
    """
    【系統級設定 API】
    用途：儲存當前系統使用的參數（暱稱、字體、頭像形狀、當前身高體重）。
    影響：直接更新 USER_CONFIG_PATH (HTML/JS/json/user_config.json) 與 state.user_info。
    """
    try:
        data = await request.json()
        
        # 1. 讀取現有設定
        current_config = {}
        if os.path.exists(USER_CONFIG_PATH):
            with open(USER_CONFIG_PATH, 'r', encoding='utf-8') as f:
                current_config = json.load(f)

        # 2. 更新欄位 (在 list 中新增 'mediapipe_model')
        for key in ['username', 'avatar_shape', 'font_scale', 'height', 'weight', 'age', 'mediapipe_model']:
            if key in data:
                current_config[key] = data[key]
                # 同步更新全域變數，確保 AI 偵測時拿到最新身高
                if key in state.user_info:
                    state.user_info[key] = data[key]
                elif key == 'age': # 確保 age 也有被寫入 state
                    state.user_info['age'] = data[key]
        
        current_config['last_update'] = time.time()

        # 3. 寫回檔案 (統一使用 USER_CONFIG_PATH)
        with open(USER_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=4, ensure_ascii=False)

        return JSONResponse({"status": "success", "message": "User config saved"})
    except Exception as e:
        print(f"儲存 user_config 發生錯誤: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    
@router.post("/api/upload_avatar")
async def upload_avatar(file: UploadFile = File(...)):
    base_dir = os.path.join("HTML", "Photo")
    save_dir = os.path.join(base_dir, "save")
    current_avatar_path = os.path.join(base_dir, "user_avatar.jpg")

    os.makedirs(save_dir, exist_ok=True)

    if os.path.exists(current_avatar_path):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archived_path = os.path.join(save_dir, f"{timestamp}.jpg")
        try:
            shutil.move(current_avatar_path, archived_path)
            print(f"[Server] 📦 舊頭像已歸檔至: {archived_path}")
        except Exception as e:
            print(f"[Server] ⚠️ 歸檔舊頭像失敗: {e}")

    try:
        with open(current_avatar_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # ✅ 加上這段：頭貼上傳成功後，也去更新 config 的時間
        try:
            config_dir = os.path.join("HTML", "JS", "json")
            config_path = os.path.join(config_dir, "user_config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                config_data["last_update"] = time.time()
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception as json_e:
            print(f"更新時間標記失敗: {json_e}")
            
        return {"status": "success", "image_url": f"/Photo/user_avatar.jpg?t={datetime.now().timestamp()}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        file.file.close()


@router.get("/api/get_body_records")
async def get_body_records():
    try:
        # 根據你的專案結構，對應到存放 BMI JSON 的路徑
        base_dir = os.path.join("HTML", "JS", "json", "User_data_profile")
        records = []
        
        if not os.path.exists(base_dir):
            return JSONResponse(content=[])
            
        # 遞迴搜尋該目錄下所有的 .json 檔案
        search_pattern = os.path.join(base_dir, "**", "*.json")
        for file_path in glob.glob(search_pattern, recursive=True):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records.append(data)
            except Exception as file_e:
                print(f"讀取檔案失敗 {file_path}: {file_e}")
                
        return JSONResponse(content=records)
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@router.get("/api/get_history_records")
async def get_history_records():
    try:
        base_dir = "user_data"
        records = []
        if not os.path.exists(base_dir):
            return JSONResponse(content=[])
            
        # 🌟 1. 建立「全方位靜音翻譯字典」(只跑一次，不吵不鬧)
        translation_map = {}
        try:
            with open("detector_config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # 暫時把系統的 print 導向黑洞，避免語言載入器瘋狂洗版
            old_stdout = sys.stdout
            sys.stdout = io.StringIO() 
            
            for det in config.get("detectors", []):
                mod_name = det["module"].split(".")[-1]
                class_name = det["class"]
                
                try:
                    # 抓取三種語言的名稱 (目標語言、繁中、英文)
                    target_name = LanguageLoader(mod_name, state.language).get_module_name()
                    zh_name = LanguageLoader(mod_name, 'ZH_TW').get_module_name()
                    en_name = LanguageLoader(mod_name, 'EN').get_module_name()
                    
                    # 把所有可能的舊名字，全部指向「當前目標語言的名字」
                    translation_map[class_name] = target_name
                    translation_map[zh_name] = target_name
                    translation_map[en_name] = target_name
                except:
                    pass
                    
            # 建立完畢，恢復 print 功能
            sys.stdout = old_stdout 
        except Exception as e:
            sys.stdout = old_stdout # 確保出錯也能恢復聲音
            print(f"建立字典失敗: {e}")

        # 🌟 2. 讀取並清洗歷史紀錄
        search_pattern = os.path.join(base_dir, "**", "*.json")
        for file_path in glob.glob(search_pattern, recursive=True):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    for user_data in data:
                        if "exercise_records" in user_data:
                            for ex_record in user_data["exercise_records"]:
                                raw_name = ex_record.get("exercise_name", "")
                                
                                # 多向翻譯：不管紀錄裡是「開合跳」、「Jumping Jack」還是「JumpingJackDetector」，統統洗成當前語言
                                if raw_name in translation_map:
                                    ex_record["exercise_name"] = translation_map[raw_name]
                                else:
                                    # 防呆模糊比對 (把空白和 Detector 拿掉再比對一次)
                                    clean_raw = raw_name.lower().replace("detector", "").replace(" ", "")
                                    for k, v in translation_map.items():
                                        if clean_raw == k.lower().replace("detector", "").replace(" ", ""):
                                            ex_record["exercise_name"] = v
                                            break

                    records.append(data)
            except Exception as file_e:
                print(f"讀取運動紀錄檔案失敗 {file_path}: {file_e}")
                
        return JSONResponse(content=records)
        
    except Exception as e:
        print(f"取得運動紀錄 API 發生錯誤: {e}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)
    
# ==========================================
# 運動參數設定 API (不污染預設檔的設計)
# ==========================================
# 設定存放自訂設定檔的路徑
USER_CONFIG_DIR = os.path.join("HTML", "JS", "json")
USER_DETECTOR_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, "user_detector_config.json")

@router.get("/api/get_detector_config")
def get_detector_config():
    """ 取得合併後的設定檔 (預設 + 使用者自訂) """
    # 1. 讀取預設設定檔
    default_config = load_config()
    
    # 2. 讀取使用者自訂設定檔
    user_config = {}
    if os.path.exists(USER_DETECTOR_CONFIG_PATH):
        try:
            with open(USER_DETECTOR_CONFIG_PATH, "r", encoding="utf-8") as f:
                user_config = json.load(f)
        except Exception as e:
            print(f"[API] 讀取使用者自訂設定檔失敗: {e}")
            
    # 3. 合併邏輯: 將 user_config 裡的設定覆蓋到 default_config
    for d_cfg in default_config.get('detectors', []):
        class_name = d_cfg.get('class')
        if class_name in user_config:
            if 'config' not in d_cfg:
                d_cfg['config'] = {}
            # 覆蓋設定 (只覆蓋使用者有修改過的角度/參數)
            for k, v in user_config[class_name].items():
                d_cfg['config'][k] = v
                
    return JSONResponse(content=default_config)

@router.post("/api/save_detector_config")
async def save_detector_config(request: Request):
    """ 儲存使用者自訂的運動參數到獨立檔案 """
    try:
        data = await request.json()
        class_name = data.get("class_name")
        new_config = data.get("config")
        
        if not class_name or not new_config:
            return JSONResponse({"status": "error", "message": "缺少必要參數"})
            
        # 確保資料夾存在
        os.makedirs(USER_CONFIG_DIR, exist_ok=True)
        
        # 讀取現有的使用者設定
        user_config = {}
        if os.path.exists(USER_DETECTOR_CONFIG_PATH):
            try:
                with open(USER_DETECTOR_CONFIG_PATH, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
            except:
                pass # 檔案損毀則從空字典開始
                
        # 更新該運動的設定
        user_config[class_name] = new_config
        
        # 寫入獨立的使用者設定檔
        with open(USER_DETECTOR_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(user_config, f, ensure_ascii=False, indent=4)
            
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

@router.get("/api/current_exercise")
def get_current_exercise():
    """ 取得當前正在偵測的運動項目 (修正版) """
    try:
        # 1. 優先檢查是否已經鎖定特定運動 (locked_idx)
        if state.locked_idx != -1 and state.locked_idx < len(state.detectors):
            current_d = state.detectors[state.locked_idx]
            # 嘗試從物件屬性獲取類別名稱，若物件沒有屬性則嘗試字典取值，最後防呆
            class_name = getattr(current_d, '__class__', {}).__name__ if not isinstance(current_d, dict) else current_d.get('class')
            
            # 如果還是拿不到，我們從 detector_config 裡對照索引拿
            if not class_name:
                config = load_config()
                detectors_cfg = config.get('detectors', [])
                if state.locked_idx < len(detectors_cfg):
                    class_name = detectors_cfg[state.locked_idx].get('class')
            
            return JSONResponse({"class_name": class_name})

        # 2. 如果沒鎖定，找尋第一個正在運行的偵測器
        config = load_config()
        detectors_cfg = config.get('detectors', [])
        
        # 遍歷目前載入的實例
        for i, d in enumerate(state.detectors):
            # 檢查實例是否有 is_running 屬性
            is_running = getattr(d, 'is_running', False)
            if is_running:
                if i < len(detectors_cfg):
                    return JSONResponse({"class_name": detectors_cfg[i].get('class')})

        # 3. 若都沒運行，回傳設定檔中第一個啟用的運動作為預設選中
        for d_cfg in detectors_cfg:
            if d_cfg.get('enabled', True):
                return JSONResponse({"class_name": d_cfg.get('class')})

        return JSONResponse({"class_name": None})
    except Exception as e:
        print(f"[API] get_current_exercise 發生錯誤: {e}")
        # 發生任何錯誤時，回傳 None 讓前端處理，不要噴 500
        return JSONResponse({"class_name": None})
    
@router.post("/api/reset_detector_config")
async def reset_detector_config(request: Request):
    """ 刪除指定運動的自訂設定，使其恢復預設值 """
    try:
        data = await request.json()
        class_name = data.get("class_name")
        
        # 【修正】對齊上方定義的 USER_DETECTOR_CONFIG_PATH，而不是去根目錄找
        user_config_path = USER_DETECTOR_CONFIG_PATH 
        
        if os.path.exists(user_config_path):
            with open(user_config_path, 'r', encoding='utf-8') as f:
                user_configs = json.load(f)
            
            # 如果存在該運動的自訂值，則刪除它
            if class_name in user_configs:
                del user_configs[class_name]
                
                with open(user_config_path, 'w', encoding='utf-8') as f:
                    json.dump(user_configs, f, indent=4, ensure_ascii=False)
                return JSONResponse({"status": "success", "message": f"{class_name} 已恢復預設值"})
        
        return JSONResponse({"status": "no_change", "message": "尚無自訂設定，無需重製"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    
@router.get("/api/get_detector_system_config")
def get_detector_system_config():
    """ 取得當前系統的攝影機解析度 (自動合併第一與第二層設定) """
    config_data = load_config()
    sys_cfg = config_data.get("system_settings", {})
    return {
        "video_width": sys_cfg.get("video_width", 640),
        "video_height": sys_cfg.get("video_height", 480)
    }

@router.post("/api/save_detector_system_config")
async def save_detector_system_config(request: Request):
    """ 將使用者自訂的解析度等系統設定存入 user_detector_config.json """
    try:
        data = await request.json()
        
        user_data = {}
        # 統一使用 USER_DETECTOR_CONFIG_PATH
        if os.path.exists(USER_DETECTOR_CONFIG_PATH):
            with open(USER_DETECTOR_CONFIG_PATH, "r", encoding="utf-8") as f:
                try:
                    user_data = json.load(f)
                except Exception:
                    pass
                    
        # 確保有 system_settings 結構
        if "system_settings" not in user_data:
            user_data["system_settings"] = {}
            
        # 寫入傳過來的寬與高
        if "video_width" in data:
            user_data["system_settings"]["video_width"] = int(data["video_width"])
        if "video_height" in data:
            user_data["system_settings"]["video_height"] = int(data["video_height"])

        with open(USER_DETECTOR_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=4)
            
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    
@router.get("/api/get_model_info")
def get_model_info():
    """ 取得當前模型資訊供前端顯示 """
    try:
        loader = ModelLoader(state.language)
        info = loader._load_info()
        # 從 JSON 中取得當前模型名稱，若無則顯示預設
        model_name = info.get("name", "Unknown") if info else "Unknown"
        return JSONResponse({"current_model": model_name, "model_id": state.mediapipe_model})
    except Exception as e:
        return JSONResponse({"current_model": "Error", "error": str(e)})

@router.post("/api/switch_model")
async def switch_model(request: Request):
    """ 動態切換 MediaPipe 模型 (覆蓋實體檔案並重啟記憶體) """
    try:
        data = await request.json()
        model_id = str(data.get("model_id", "2")) 
        
        # 1. 呼叫 ModelLoader 進行實體檔案替換
        loader = ModelLoader(state.language)
        loader.switch_model(model_id)
        
        # 2. 更新全域狀態與使用者的設定檔 (讓下次開機記住)
        state.mediapipe_model = model_id
        if os.path.exists(USER_CONFIG_PATH):
            with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                
            config_data["mediapipe_model"] = model_id
            with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
                
        # 3. ★ 關鍵修復：如果相機正在運行中，必須強制重啟迴圈來套用新模型！
        with state.lock:  # 使用線程鎖避免衝突
            if state.camera_active:
                print(f"[Server] 準備套用新模型 {model_id}，正在重啟影像迴圈...")
                state.is_running = False  # 通知舊迴圈停止
                
                # 等待舊相機資源與舊模型完全釋放 (最多等3秒)
                wait_time = 0
                while state.camera_active and wait_time < 3.0:
                    time.sleep(0.1)
                    wait_time += 0.1
                
                # 重新啟動相機迴圈 (預設以 auto 模式重啟)
                state.is_running = True
                state.camera_active = True
                state.locked_idx = -1
                state.detectors = []
                state.frame_bytes = None 
                
                # 啟動新的執行緒，此時程式會重新實例化 MediaPipe，讀取到新的 task 檔
                t = threading.Thread(target=web_camera_loop, args=("auto", -1), daemon=True)
                t.start()
                print("[Server] 新模型載入完畢，影像迴圈已重啟！")
        
        return JSONResponse({"status": "success", "message": "模型切換成功並已套用"})
        
    except Exception as e:
        print(f"[Error] 模型切換失敗: {e}")
        return JSONResponse({"status": "error", "message": str(e)})
    
    
# ==========================================
# 新增：手動同步 JSON 至 SQLite 的 API
# ==========================================
@router.post("/api/sync_records")
def sync_data_endpoint():
    try:
        print("\n[API] 收到前端請求，啟動資料庫雙向同步...")
        
        # 實例化同步工具
        sync_manager = DbSyncManager(language=state.language)
        
        # 執行任務 1：JSON 同步到 SQLite (補齊資料庫)
        sync_manager.sync_json_to_sqlite()
        
        # 執行任務 2：SQLite 同步到 JSON (還原缺少的檔案)
        sync_manager.export_sqlite_to_json()
        
        # 關閉連線釋放資源
        sync_manager.close()
        
        return JSONResponse({
            "status": "success", 
            "message": "資料雙向同步完成！\n(詳細同步數量請查看伺服器後台日誌)"
        })
        
    except Exception as e:
        print(f"[Sync API] 雙向同步失敗: {e}")
        return JSONResponse(
            status_code=500, 
            content={"status": "error", "message": str(e)}
        )

