import sys
if __name__ == "__main__":
    sys.modules["server"] = sys.modules[__name__]

import cv2
import mediapipe as mp
import importlib
import json
import os
import time
import threading
import numpy as np
import logging
import re

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from modules.language_loader import LanguageLoader
from modules.model_loader import ModelLoader
from modules.jsonwriter import JsonWriter

class GlobalState:
    def __init__(self):
        self.frame_bytes = None
        # ★ 新增：用於同步前後端影像幀的條件變數
        self.frame_condition = threading.Condition() 
        self.is_running = False
        self.camera_active = False  
        self.show_skeleton = True
        self.detectors = []
        self.locked_idx = -1
        self.user_info = {"username": "WebUser", "height": 170, "weight": 70, "age": 25}
        self.last_api_access = time.time()
        self.language = 'ZH_TW'  
        self.lock = threading.Lock() 
        self.mediapipe_model = "2"  # 預設中階 (Full)

state = GlobalState()

JSON_DIR = os.path.join('HTML', 'JS', 'json')
USER_CONFIG_PATH = os.path.join(JSON_DIR, 'user_config.json')

# === 新增：啟動時讀取前端的使用者設定，覆蓋預設的 WebUser ===
def initialize_user_state():
    """ 伺服器啟動時，從 user_config.json 同步資料到記憶體 """
    user_config_path = os.path.join('HTML', 'JS', 'json', 'user_config.json')
    if os.path.exists(user_config_path):
        try:
            with open(user_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 同步到記憶體 state 中
                if 'username' in config:
                    state.user_info['username'] = config['username']
                if 'height' in config:
                    state.user_info['height'] = config['height']
                if 'weight' in config:
                    state.user_info['weight'] = config['weight']
                if 'age' in config:
                    state.user_info['age'] = config['age']
                print(f"[Init] 已載入使用者設定: {state.user_info}")
        except Exception as e:
            print(f"[Init] 載入使用者設定失敗: {e}")

# 執行初始化
initialize_user_state()
# ========================================================

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_current_username():
    config_path = os.path.join("HTML", "JS", "json", "user_config.json")
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("username", "User")
    except:
        pass
    return "User"

def load_config():
    """ 
    進階版載入設定：自動合併預設檔與使用者自訂的角度設定。
    """
    config_path = 'detector_config.json'
    # 確保路徑與 server_api.py 儲存時一致
    user_config_path = os.path.join('HTML', 'JS', 'json', 'user_detector_config.json')
    
    # 1. 載入基礎預設設定
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    else:
        config = {"detectors": []}

    # 2. 檢查並合併使用者自訂設定
    if os.path.exists(user_config_path):
        try:
            with open(user_config_path, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
            
            # === 新增：合併解析度 (system_settings) ===
            if 'system_settings' in user_data:
                if 'system_settings' not in config:
                    config['system_settings'] = {}
                config['system_settings'].update(user_data['system_settings'])
            # =======================================

            # 支援您目前的 user_detector_config.json 格式 (直接以 ClassName 為 Key)
            # 遍歷預設配置清單
            if 'detectors' in config:
                for d_cfg in config['detectors']:
                    cls_name = d_cfg.get('class')
                    
                    # 檢查使用者檔案中是否有這個類別的設定
                    if cls_name in user_data:
                        custom_params = user_data[cls_name]
                        
                        # 核心動作：合併字典
                        if 'config' in d_cfg:
                            d_cfg['config'].update(custom_params)
                            #print(f"  [Config] 套用成功: {cls_name} 已覆蓋自訂參數。")
                        else:
                            d_cfg['config'] = custom_params
                            
        except Exception as e:
            print(f"  [Config] 合併使用者設定時出錯: {e}")

    return config

def load_posture_map():
    """ 讀取運動姿勢分類 JSON 檔案 """
    try:
        with open('posture_map.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] 姿勢設定檔 (posture_map.json) 讀取失敗，將使用預設空集合: {e}")
        return {"standing": [], "lying": []}

def get_video_capture(cam_id):
    """ 改用 DSHOW 後台以提升對 Windows 筆電鏡頭的相容性 """
    if os.name == 'nt':
        return cv2.VideoCapture(cam_id, cv2.CAP_DSHOW)
    return cv2.VideoCapture(cam_id)

# ==========================================
# ★ 新增：多執行緒相機讀取類別 (解決卡頓與閃退核心)
# ==========================================
class ThreadedCamera:
    def __init__(self, cap):
        self.stream = cap
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False

    def start(self):
        # 啟動背景執行緒來專心讀取畫面
        t = threading.Thread(target=self.update, args=())
        t.daemon = True
        t.start()
        return self

    def update(self):
        # 背景執行緒：死命抓取最新畫面，不被主程式的 AI 與畫圖拖慢
        while not self.stopped:
            if not self.stream.isOpened():
                break
            self.stream.grab()
            self.grabbed, self.frame = self.stream.retrieve()

    def read(self):
        # 主程式呼叫這個方法，直接拿最新這張，瞬間返回
        return self.grabbed, self.frame

    def isOpened(self):
        return self.stream.isOpened()

    def release(self):
        # ★ 安全釋放機制，避免 C++ 底層記憶體區段錯誤 (閃退)
        self.stopped = True
        time.sleep(0.1) # 等待讀取迴圈結束
        self.stream.release()
        time.sleep(0.5) # 給作業系統 500ms 釋放硬體資源
# ==========================================

def save_current_record():
    if state.locked_idx != -1 and state.locked_idx < len(state.detectors):
        target_d = state.detectors[state.locked_idx]
    else:
        target_d = None
        best_count = 0
        for d in state.detectors:
            c = max(d['instance'].count, getattr(d['instance'], 'correct', 0))
            if c > best_count:
                best_count = c
                target_d = d
        if target_d is None:
            print("[Server] 無有效運動紀錄，略過存檔")
            return

    # [修正 Bug] 改用 target_d，避免 locked_idx 為 -1 時發生錯誤
    inst = target_d['instance'] 
    is_running_sport = target_d.get('is_running', False)
    count = inst.count
    correct = getattr(inst, 'correct', 0)
    wrong = getattr(inst, 'wrong', 0)

    raw_name = inst.__class__.__name__ 
    
    if count == 0 and correct == 0:
        print("[Server] 次數為 0，略過存檔")
        return

    if hasattr(inst, 'lang') and inst.lang is not None:
        exercise_name = inst.lang.get_module_name()
    else:
        exercise_name = raw_name

    extra_data = {}
    
    if is_running_sport and hasattr(inst, 'total_distance_cm'):
        distance = round(getattr(inst, 'total_distance_cm', 0) / 100, 2)
        extra_data['distance_m'] = distance

    if callable(getattr(inst, 'get_total_time', None)):
        extra_data['duration_sec'] = round(inst.get_total_time(), 1)

    # ========== [新增] 自動抓取詳細錯誤紀錄 ==========
    if hasattr(inst, 'get_detailed_errors'):
        detailed_errs = inst.get_detailed_errors()
        if detailed_errs:
            extra_data['body_wrong'] = detailed_errs
    # ===============================================

    if not extra_data:
        extra_data = None

    # 原本的 JSON 寫入
    writer = JsonWriter(language=state.language)
    writer.log_exercise(
        user_info=state.user_info,
        exercise_name=exercise_name,
        count=count,
        correct=correct,
        wrong=wrong,
        base_folder='user_data',
        extra_data=extra_data
    )
    # ========== [新增] 併行寫入 SQLite ==========
    try:
        from modules.dbwriter import DbWriter
        db_writer = DbWriter(language=state.language)
        db_writer.log_exercise(
            user_info=state.user_info,
            exercise_name=exercise_name,
            count=count,
            correct=correct,
            wrong=wrong,
            extra_data=extra_data
        )
    except Exception as e:
        print(f"[Server] ⚠️ SQLite 併行儲存失敗: {e}")
    # ==========================================

    print(f"\n[Server] 💾 已成功寫入運動紀錄: {exercise_name} (正確:{correct} 錯誤:{wrong})\n")

# ==========================================
# 姿勢判斷邏輯
# ==========================================
def get_body_posture(landmarks):
    """ 根據肩膀與髖部的相對位置，判斷人體是站立還是躺下 """
    # 11: 左肩, 12: 右肩, 23: 左髖, 24: 右髖
    mid_shoulder_x = (landmarks[11].x + landmarks[12].x) / 2
    mid_shoulder_y = (landmarks[11].y + landmarks[12].y) / 2
    
    mid_hip_x = (landmarks[23].x + landmarks[24].x) / 2
    mid_hip_y = (landmarks[23].y + landmarks[24].y) / 2

    # 計算 X 軸與 Y 軸的距離差
    dx = abs(mid_shoulder_x - mid_hip_x)
    dy = abs(mid_shoulder_y - mid_hip_y)

    # 加上 1.2 倍的緩衝，避免稍微傾斜就被誤判
    if dy > dx * 1.2:
        return "standing"
    elif dx > dy * 1.2:
        return "lying"
    else:
        return "transition"


def web_camera_loop(target_mode="auto", target_camera_id=-1):
    print(f"[Server] 啟動核心偵測引擎 (模式: {target_mode}, 指定鏡頭: {target_camera_id})...")
    state.last_api_access = time.time()

    config_data = load_config()
    posture_map = load_posture_map()  
    
    sys_cfg = config_data.get('system_settings', {})
    global_language = sys_cfg.get('language', 'ZH_TW')
    state.language = global_language

    model_loader = ModelLoader(language=global_language)
    model_path = model_loader.get_model_path_silent()
    if not model_path: model_path = model_loader.download_model_silent(2)

    detectors = []
    for d_cfg in config_data.get('detectors', []):
        if not d_cfg.get('enabled', False): continue
        if target_mode != "auto" and d_cfg['class'] != target_mode:
            continue
        try:
            module = importlib.import_module(d_cfg['module'])
            cls = getattr(module, d_cfg['class'])
            final_cfg = d_cfg.get('config', {}).copy()
            final_cfg['language'] = global_language
            final_cfg['human_height'] = state.user_info['height']
            instance = cls(config=final_cfg, language=global_language) if d_cfg.get('use_custom_config') else cls(language=global_language)
            
            display_label = d_cfg['class'].replace("Detector", "")
            if hasattr(instance, 'lang') and instance.lang:
                display_label = instance.lang.get_module_name()

            detectors.append({
                "label": display_label,
                "class_name": d_cfg['class'],
                "instance": instance,
                "active": True,
                "locked": False,
                "target_count": d_cfg.get('target_count', 10),
                "max_wrong": d_cfg.get('max_wrong', 5),
                "is_running": hasattr(instance, 'total_distance_cm'),
            })
            print(f" + {d_cfg['class']} 載入成功")
        except Exception as e:
            print(f" [Error] {d_cfg['class']} 載入失敗: {e}")

    state.detectors = detectors

    if target_mode != "auto" and len(state.detectors) == 1:
        state.locked_idx = 0
        state.detectors[0]['locked'] = True
        print(f"[Info] 單一模式啟動，直接鎖定: {state.detectors[0]['label']}")

    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        min_pose_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    detector_engine = mp.tasks.vision.PoseLandmarker.create_from_options(options)

    # 決定初始要測試的鏡頭 ID
    cam_id = sys_cfg.get('camera_id', 0)
    if target_camera_id != -1:
        cam_id = target_camera_id
        
    print(f"[Server] 準備開啟鏡頭 ID: {cam_id} ...")
    cap = get_video_capture(cam_id)

    is_valid = False
    if cap.isOpened():
        for _ in range(5):
            ret, _ = cap.read()
            if ret:
                is_valid = True
                break
            time.sleep(0.1)

    if not is_valid:
        if cap.isOpened():
            cap.release()
        print(f"[Server] ❌ 無法初始化攝影機: {cam_id}")
        print("[Server] >> 正在掃描可用攝影機...")
        
        found_id = None
        for i in range(5):
            if i == cam_id: continue
            temp_cap = cv2.VideoCapture(i)
            if temp_cap.isOpened():
                ret, _ = temp_cap.read()
                if ret:
                    found_id = i
                    temp_cap.release()
                    break
                temp_cap.release()
                
        if found_id is not None:
            cam_id = found_id
            print(f"[Server] >> 自動選擇可用攝影機: Camera {cam_id}")
            cap = get_video_capture(cam_id)
        else:
            print("[Server] ❌ 掃描結束：找不到任何可用的攝影機！")
            cap = get_video_capture(cam_id) # 給下面的 Retry 最後一次機會

    retry_count = 0
    while not cap.isOpened() and retry_count < 3:
        print(f"[Server] ⚠️ 鏡頭無法立即開啟 (等待硬體釋放)，等待 1 秒後重試... ({retry_count+1}/3)")
        time.sleep(1.0)
        cap = get_video_capture(cam_id)
        retry_count += 1

    if not cap.isOpened():
        print(f"[Server] ❌ 嚴重錯誤：無法開啟鏡頭 {cam_id}，請檢查是否被其他程式佔用！")
    else:
        print(f"[Server] ✅ 攝影機已啟動 (ID: {cam_id})")

    # === 新增：從 config 讀取解析度設定，若無則預設為 640x480 ===
    target_w = sys_cfg.get('video_width', 640)
    target_h = sys_cfg.get('video_height', 480)

    print(f"[Server] 🎥 嘗試向硬體請求設定解析度 {target_w}x{target_h}...")
    
    # 1. 大膽嘗試設定目標解析度 (加入 try-except 防護)
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
    except cv2.error as e:
        print(f"[Server] ⚠️ 快速切換導致鏡頭解析度設定失敗 (可忽略): {e}")
    except Exception as e:
        print(f"[Server] ⚠️ 設定解析度時發生未知錯誤 (可忽略): {e}")
    
    # 2. 試拍一張，驗證硬體有沒有因為切換解析度而「崩潰」或「給出破圖」
    ret, test_frame = cap.read()
    
    # 3. 如果硬體罷工 (沒反應或給空圖)，果斷退回最安全的 640x480
    if not ret or test_frame is None or test_frame.size == 0:
        print("[Server] ⚠️ 鏡頭無法支援該解析度或發生異常，退回安全預設值 640x480")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.read() # 試拍一張把剛才的壞圖從硬體緩衝區清掉
    else:
        print("[Server] ✅ 鏡頭解析度測試通過！")
        
    # 4. 取得相機硬體最終妥協的真實解析度 (無論成功或退回，以這個為準)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[Server] 🎥 鏡頭實際輸出: {actual_w}x{actual_h}")
    # =========================================================
    
    # ★ 新增：限制硬體緩衝區為 1，避免舊畫面堆積造成延遲 (Delay)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    # ★ 新增：將原本的 cap 包裝進多執行緒類別中並啟動
    print("[Server] 🚀 啟動多執行緒相機讀取模式...")
    cap = ThreadedCamera(cap).start()
    try:
        # 重置計時器
        state.last_api_access = time.time()
        
        if not state.is_running:
            print("[Server] ⚠️ 進入影像迴圈前，state.is_running 已被其他執行緒設為 False！(可能是前端重複發送了啟動請求)")
            
        while state.is_running and cap.isOpened():
            if time.time() - state.last_api_access > 5.0:
                print("[Server] ⚠️ 偵測到前端斷線或跳轉頁面，準備自動存檔並關閉鏡頭...")
                break

            ret, frame = cap.read()
            # 加上 frame is None 與 size == 0 的防禦，攔截壞掉的畫面
            if not ret or frame is None or frame.size == 0:
                time.sleep(0.1)
                continue

            # === 軟體層「嘗試」等比例縮放 (依據設定檔) ===
            h, w = frame.shape[:2]
            target_w = sys_cfg.get('video_width', 640)
            
            if w != target_w and w > 0:
                scale = target_w / w
                new_w = target_w
                new_h = int(h * scale) # 保持等比例縮放，避免人體變形
                
                # 若縮小使用 INTER_AREA 畫質較好；若放大則用 INTER_LINEAR
                inter_mode = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                frame = cv2.resize(frame, (new_w, new_h), interpolation=inter_mode)
            # ====================================

            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            timestamp_ms = int(time.time() * 1000)
            results = detector_engine.detect_for_video(mp_img, timestamp_ms)

            display_frame = frame.copy()

            if results.pose_landmarks:
                landmarks = results.pose_landmarks[0]
                if state.show_skeleton:
                    h, w, _ = display_frame.shape
                    for conn in mp.solutions.pose.POSE_CONNECTIONS:
                        if conn[0] > 10 and conn[1] > 10:
                            cv2.line(display_frame, (int(landmarks[conn[0]].x * w), int(landmarks[conn[0]].y * h)), (int(landmarks[conn[1]].x * w), int(landmarks[conn[1]].y * h)), (0, 255, 0), 2)
                            cv2.circle(display_frame, (int(landmarks[conn[0]].x * w), int(landmarks[conn[0]].y * h)), 4, (0, 0, 255), -1)

                current_posture = get_body_posture(landmarks)

                for idx, d in enumerate(state.detectors):
                    if not d['active']: continue
                    
                    if target_mode == "auto" and state.locked_idx == -1:
                        expected_posture = None
                        for p_type, classes in posture_map.items():
                            if d['class_name'] in classes:
                                expected_posture = p_type
                                break
                        
                        if expected_posture and current_posture != "transition":
                            if current_posture != expected_posture:
                                continue 

                    dummy = np.zeros_like(frame)
                    _, info = d['instance'].process_frame(dummy, landmarks)

                    if target_mode == "auto" and not d['is_running']:
                        wrong = getattr(d['instance'], 'wrong', 0)
                        if wrong > d['max_wrong'] and state.locked_idx == -1:
                            d['active'] = False
                            continue

                    metric = d['instance'].count if d['is_running'] else getattr(d['instance'], 'correct', 0)

                    if target_mode == "auto" and metric >= d['target_count'] and state.locked_idx == -1:
                        state.locked_idx = idx
                        d['locked'] = True
                        for i, other in enumerate(state.detectors):
                            if i != idx: other['active'] = False

            # 原本是：ret, buffer = cv2.imencode('.jpg', display_frame)
            # 改成以下這樣，將畫質設定為 70 (肉眼看不出差異，但可大幅減少傳輸延遲與 CPU 負載)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
            ret, buffer = cv2.imencode('.jpg', display_frame, encode_param)

            if ret: 
                # ★ 關鍵修改：以條件鎖保護寫入，並「主動喚醒」正在等待畫面的 API
                with state.frame_condition:
                    state.frame_bytes = buffer.tobytes()
                    state.frame_condition.notify_all()
                    
            # ★ 關鍵修改：移除 time.sleep(0.03)，因為 cap.read() 本身已是阻塞讀取
            # 不需要強加延遲去拖慢相機硬體的原始效能
            
    except Exception as e:
        print(f"[Server] 核心迴圈發生例外: {e}")

    finally:
        save_current_record()
        if 'cap' in locals() and cap is not None:
            try:
                cap.release()
            except:
                pass 
        try:
            if 'detector_engine' in locals() and detector_engine is not None:
                detector_engine.close()
        except:
            pass
        
        state.camera_active = False 
        state.frame_bytes = None
        print("[Server] 🛑 鏡頭已釋放，引擎完全停止")


def load_user_config():
    if os.path.exists(USER_CONFIG_PATH):
        with open(USER_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"username": "User"}

def save_movement_record(exercise_name, count, correct, wrong):
    current_config = load_user_config()
    state.user_info["username"] = current_config.get("username", "User")
    
    real_name = get_localized_exercise_name(exercise_name, state.language)

    writer = JsonWriter(language=state.language)
    writer.log_exercise(
        user_info=state.user_info, 
        exercise_name=real_name,
        count=count,
        correct=correct,
        wrong=wrong,
        extra_data=None 
    )

def get_localized_exercise_name(raw_name, language):
    if not raw_name: return "Unknown"
    
    clean_name = re.sub(r'[^a-zA-Z0-9]', '', raw_name).lower()
    clean_name = clean_name.replace("detector", "")
    
    config_data = load_config()
    target_module = None
    
    for d_cfg in config_data.get('detectors', []):
        cfg_class = d_cfg.get('class', '')
        cfg_clean = re.sub(r'[^a-zA-Z0-9]', '', cfg_class).lower()
        cfg_clean = cfg_clean.replace("detector", "")
        
        if clean_name == cfg_clean:
            target_module = d_cfg.get('module', '').split('.')[-1]
            break
            
    if target_module:
        try:
            loader = LanguageLoader(target_module, language)
            name = loader.get_module_name()
            if "[Missing" not in name: 
                return name
        except Exception as e:
            print(f"語言載入失敗 ({target_module}): {e}")
            
    return raw_name.replace("Detector", "").replace("detector", "")


from server_api import router
app.include_router(router)

app.mount("/", StaticFiles(directory="HTML", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    class EndpointFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if record.args and len(record.args) >= 3:
                if "/api/status" in record.args[2] or "/video_feed" in record.args[2]: return False
            return True

    logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

    print("\n========================================")
    print(" 🚀 ActiTrack Server 啟動成功！")
    print(" 👉 請開啟瀏覽器: http://localhost:8000")
    print("========================================\n")

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")