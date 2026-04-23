# 檔名: body_squat_main.py

import cv2
import numpy as np
import math
import sys
import os
import time  # <--- 確保引入計時模組

# ========== 智能導入處理 ==========
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import utils_math
    from base_detector import BaseDetector
    from language_loader import LanguageLoader
else:
    from . import utils_math
    from .base_detector import BaseDetector
    from .language_loader import LanguageLoader


class SquatDetector(BaseDetector):
    
    def __init__(self, config=None, language='ZH_TW'):
        """
        初始化深蹲偵測器
        
        Args:
            config: (Optional) 包含角度設定的字典
            language: 語言設定 (預設 'ZH_TW')
        """
        super().__init__()
        
        # ========== 載入多語言支援 ==========
        self.lang = LanguageLoader('body_squat_main', language)
        print(self.lang.log('info', 'system_init'))
        
        # 1. 定義預設參數 (Default Configuration) - 包含全域預設的自動暫停秒數
        self.cfg = {
            'waist_up_angle': 120,       # 腰部伸直角度閾值 (站立狀態)
            'waist_down_angle': 90,      # 腰部蹲下角度閾值 (蹲下狀態)
            'knee_straight_angle': 120,  # 膝蓋伸直角度閾值 (判斷是否站直)
            'knee_down_angle': 90,       # 膝蓋蹲下角度閾值
            'auto_pause_seconds': 5.0    # 預設的暫停秒數
        }
        
        # 2. 外部 Config 覆蓋
        if config:
            self.cfg.update(config)
            print(self.lang.log('info', 'config_loaded'))
        
        # 3. 綁定屬性
        self.waist_up_angle = self.cfg['waist_up_angle']
        self.waist_down_angle = self.cfg['waist_down_angle']
        self.knee_straight_angle = self.cfg['knee_straight_angle']
        self.knee_down_angle = self.cfg['knee_down_angle']
        self.auto_pause_seconds = self.cfg['auto_pause_seconds']
        
        # ========== 狀態變數 ==========
        self.A = False  # 站立狀態 (Start)
        self.B = False  # 蹲下狀態 (Down)
        self.knee_wrong = False # 膝蓋錯誤
        self.hip_wrong = False  # 腰部錯誤

        # ========== [新增] 累計計數器 (供 JSON 分析用) ==========
        self.total_errors = {
            "fail_knee_angle": 0,
            "fail_hip_angle": 0
        }

        # ========== 計時機制變數 ==========
        self.start_time = time.time()
        self.last_action_time = time.time()
        self.total_accumulated_time = 0.0
        # ★ 一開始必須是暫停狀態！避免把準備時間算進去
        self.is_paused = True

    def get_detailed_errors(self):
        """回傳原始的變數名稱，作為 JSON 分析用"""
        return {k: v for k, v in self.total_errors.items() if v > 0}
    
    def _pause_timer(self):
        """暫停計時"""
        if not self.is_paused:
            self.total_accumulated_time += (time.time() - self.start_time)
            self.is_paused = True
            # ===== 輸出終端機警告 =====
            print(self.lang.log('warning', 'auto_pause'))

    def _resume_timer(self):
        """恢復計時並更新最後動作時間"""
        if self.is_paused:
            self.start_time = time.time()
            self.is_paused = False
        self.last_action_time = time.time()

    def get_total_time(self):
        """取得總運動時間 (主程式寫入 JSON 時會自動呼叫此函式)"""
        if self.is_paused:
            return self.total_accumulated_time
        return self.total_accumulated_time + (time.time() - self.start_time)

    def reset_state(self):
        """重置動作狀態標記"""
        self.A = False
        self.B = False
        self.knee_wrong = False
        self.hip_wrong = False
    
    def process_frame(self, img, landmarks):
        """
        處理單一影像幀
        
        Args:
            img: 輸入影像
            landmarks: MediaPipe 偵測到的骨架關鍵點
        
        Returns:
            處理後的影像, 偵測資訊字典
        """
        h, w, _ = img.shape
        
        # ========== 1. 檢查是否閒置過久 ==========
        if time.time() - self.last_action_time > self.auto_pause_seconds:
            self._pause_timer()

        def get_xy(i):
            return utils_math.get_landmark_xy(landmarks, i, w, h)
        
        detection_info = {
            'body_visible': True,
            'angles': {},
            'action_detected': False,
            'form_correct': None
        }

        # ========== 2. 新增(容錯版)：檢查半邊身體是否入鏡 ==========
        def check_visible(lm):
            """檢查單一關鍵點是否在畫面內且可見度大於 0.6"""
            return (lm.visibility >= 0.6 and 
                    0.0 <= lm.x <= 1.0 and 
                    0.0 <= lm.y <= 1.0)

        # 頭部 (鼻子:0)
        head_visible = check_visible(landmarks[0])
        # 手部 (左手腕:15 或 右手腕:16 擇一即可)
        hand_visible = check_visible(landmarks[15]) or check_visible(landmarks[16])
        # 腳部 (左腳踝:27 或 右腳踝:28 擇一即可)
        foot_visible = check_visible(landmarks[27]) or check_visible(landmarks[28])
        
        # 只要滿足頭、至少一手、至少一腳有在畫面內，就算有入鏡
        body_fully_visible = head_visible and hand_visible and foot_visible
                
        detection_info['body_visible'] = body_fully_visible
        
        if not body_fully_visible:
            # 如果連半邊身體都沒入鏡，直接暫停計時，不進入動作判斷邏輯
            self._pause_timer()
        else:
            # ========== 計算各關節角度 (僅在有效入鏡時執行) ==========
            # 右手肘 (11-13-15)
            a, b, c = get_xy(11), get_xy(13), get_xy(15)
            angle_13 = utils_math.calculate_angle(a, b, c)
            detection_info['angles']['right_elbow'] = angle_13
            # 角度數字部分繼續使用 cv2.putText
            cv2.putText(img, f'{int(angle_13)}', (int(b[0]), int(b[1]-20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # 左手肘 (12-14-16)
            a2, b2, c2 = get_xy(12), get_xy(14), get_xy(16)
            angle_14 = utils_math.calculate_angle(a2, b2, c2)
            detection_info['angles']['left_elbow'] = angle_14
            cv2.putText(img, f'{int(angle_14)}', (int(b2[0]), int(b2[1]-20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # 右膝 (24-26-28)
            a5, b5, c5 = get_xy(24), get_xy(26), get_xy(28)
            angle_26 = utils_math.calculate_angle(a5, b5, c5)
            detection_info['angles']['right_knee'] = angle_26
            cv2.putText(img, f'{int(angle_26)}', (int(b5[0]), int(b5[1]-20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # 左膝 (23-25-27)
            a6, b6, c6 = get_xy(23), get_xy(25), get_xy(27)
            angle_25 = utils_math.calculate_angle(a6, b6, c6)
            detection_info['angles']['left_knee'] = angle_25
            cv2.putText(img, f'{int(angle_25)}', (int(b6[0]), int(b6[1]-20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # 左腰 (11-23-25)
            a7, b7, c7 = get_xy(11), get_xy(23), get_xy(25)
            angle_23 = utils_math.calculate_angle(a7, b7, c7)
            detection_info['angles']['left_waist'] = angle_23
            cv2.putText(img, f'{int(angle_23)}', (int(b7[0]), int(b7[1]-20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # 右腰 (12-24-26)
            a8, b8, c8 = get_xy(12), get_xy(24), get_xy(26)
            angle_24 = utils_math.calculate_angle(a8, b8, c8)
            detection_info['angles']['right_waist'] = angle_24
            cv2.putText(img, f'{int(angle_24)}', (int(b8[0]), int(b8[1]-20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # ========== 深蹲邏輯判斷 ==========
            # 判斷 A: 站立 (腰部角度大於 waist_up_angle)
            if angle_23 >= self.waist_up_angle and angle_24 >= self.waist_up_angle:
                if not self.A:
                    self.A = True
                    self.B = False
                    self._resume_timer()  # 動作觸發，開始計時或重置閒置時間
            
            # 判斷 B: 蹲下 (腰部角度小於 waist_down_angle)
            if angle_23 <= self.waist_down_angle and angle_24 <= self.waist_down_angle:
                if self.A and not self.B:
                    self.B = True
                    self._resume_timer()  # 動作觸發，開始計時或重置閒置時間
            
            # ========== 錯誤判斷 ==========
            # 膝蓋錯誤: 膝蓋角度比腰大 30 度以上 (膝蓋前衝過多)
            if (angle_26 > angle_24 and (angle_26 - angle_24) >= 30) or \
               (angle_25 > angle_23 and (angle_25 - angle_23) >= 30):
                self.knee_wrong = True
            
            # 腰部錯誤: 腰角度比膝蓋大 30 度以上 (彎腰過多)
            elif (angle_24 > angle_26 and (angle_24 - angle_26) >= 30) or \
                 (angle_23 > angle_25 and (angle_23 - angle_25) >= 30):
                self.hip_wrong = True
            
            # ========== 完整動作判斷 ==========
            if (self.A and self.B) and \
               angle_23 >= self.waist_up_angle and angle_24 >= self.waist_up_angle and \
               angle_26 >= self.knee_straight_angle and angle_25 >= self.knee_straight_angle:
                
                self.count += 1
                detection_info['action_detected'] = True
                self._resume_timer()  # 完整做完一次，確保計時啟動
                
                # 正確/錯誤判定
                if self.hip_wrong or self.knee_wrong:
                    self.wrong += 1
                    detection_info['form_correct'] = False
                    
                    if self.hip_wrong:
                        print(self.lang.log('error', 'fail_hip_angle'))
                        self.total_errors["fail_hip_angle"] += 1   # [新增] 累計錯誤
                        cv2.circle(img, (int(b7[0]), int(b7[1])), 10, (0, 0, 255), -1)
                        cv2.circle(img, (int(b8[0]), int(b8[1])), 10, (0, 0, 255), -1)
                    
                    if self.knee_wrong:
                        print(self.lang.log('error', 'fail_knee_angle'))
                        self.total_errors["fail_knee_angle"] += 1  # [新增] 累計錯誤
                        cv2.circle(img, (int(b5[0]), int(b5[1])), 10, (0, 0, 255), -1)
                        cv2.circle(img, (int(b6[0]), int(b6[1])), 10, (0, 0, 255), -1)
                else:
                    self.correct += 1
                    detection_info['form_correct'] = True
                    print(self.lang.log('success', 'action_correct'))
                
                self.reset_state()
        
        # ========== 顯示統計資訊與時間 UI ==========
        # 使用 self.draw_text 支援多語言
        try:
            count_str = f"{self.lang.get_message('ui_count')}: {self.count}"
            correct_str = f"{self.lang.get_message('ui_correct')}: {self.correct}"
            wrong_str = f"{self.lang.get_message('ui_wrong')}: {self.wrong}"
            
            # ★ 抓取多語言的時間標籤並顯示即時時間
            try:
                time_lbl = self.lang.get_message('total_time')
                if "Missing" in time_lbl: time_lbl = "Time"
            except:
                time_lbl = "Time"
                
            time_str = f"{time_lbl}: {self.get_total_time():.1f} s"
            
            img = self.draw_text(img, count_str, (20, 60), (255, 255, 255), 32)
            img = self.draw_text(img, correct_str, (20, 100), (0, 255, 0), 32)
            img = self.draw_text(img, wrong_str, (20, 140), (0, 0, 255), 32)
            img = self.draw_text(img, time_str, (20, 180), (255, 255, 0), 32) # 黃色顯示時間
            
            # ★ 若處於暫停狀態，在畫面中央上方顯示大大的暫停提示
            if self.is_paused:
                try:
                    pause_lbl = self.lang.get_message('ui_paused')
                    if "Missing" in pause_lbl: pause_lbl = "PAUSED"
                except:
                    pause_lbl = "PAUSED"
                
                img = self.draw_text(img, f"[{pause_lbl}]", (w // 2 - 100, 80), (0, 0, 255), 48)
                
        except AttributeError:
             pass
        
        # ========== 3. 新增：未達容錯標準的畫面警告提示 ==========
        if not body_fully_visible:
            try:
                # 嘗試抓取多語言字典內的警告，若無則顯示英文預設值
                warning_msg = self.lang.get_message('warning_full_body')
                if "Missing" in warning_msg: warning_msg = "Please Show Full Body"
            except:
                warning_msg = "Please Show Full Body"
                
            # 在畫面中央提示使用者調整距離或角度
            img = self.draw_text(img, f"[{warning_msg}]", (w // 2 - 180, h // 2), (0, 0, 255), 40)
            
        return img, detection_info


# ====================================================================
# 測試模式專用函式
# ====================================================================

def select_camera(lang):
    """
    自動掃描並讓使用者選擇攝影機
    """
    print(f"\n{lang.log('warning', 'camera_scan_start')}")
    
    available_cams = []
    
    for i in range(5):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) if os.name == 'nt' else cv2.VideoCapture(i)
        
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                available_cams.append((i, f"Camera {i} ({w}x{h})"))
            cap.release()
    
    if not available_cams:
        print(lang.log('error', 'camera_not_found'))
        print(f"  {lang.get_message('camera_check_connection')}")
        return None
    
    if len(available_cams) == 1:
        idx = available_cams[0][0]
        print(lang.log('info', 'camera_auto_select') + f": {available_cams[0][1]}")
        return idx
    
    print(f"\n{lang.get_message('camera_multiple_found')}")
    for idx, name in available_cams:
        print(f"  [{idx}] {name}")
    
    while True:
        try:
            sel = input(lang.get_message('camera_select_prompt') + ": ").strip()
            if sel == "":
                return available_cams[0][0]
            
            sel_idx = int(sel)
            if any(c[0] == sel_idx for c in available_cams):
                return sel_idx
            else:
                print(lang.get_message('camera_invalid_index'))
        except ValueError:
            print(lang.get_message('camera_input_number'))


if __name__ == "__main__":
    import time
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    from mediapipe.framework.formats import landmark_pb2
    
    # ========== 初始化語言支援 ==========
    LANGUAGE = 'ZH_TW'  # 改成 'US_EN' 測試英文
    lang = LanguageLoader('body_squat_main', LANGUAGE)
    
    MODEL_PATH = 'models/pose_landmarker.task'
    
    print(lang.log('info', 'test_mode_start'))
    
    if not os.path.exists(MODEL_PATH):
        print(lang.log('error', 'model_not_found') + f": {MODEL_PATH}")
        print(f"  {lang.get_message('model_download_hint')}")
        input(lang.get_message('press_enter_to_exit'))
        exit()
    
    try:
        print(lang.log('info', 'camera_default_try'))
        cap = cv2.VideoCapture(2)
        
        camera_ok = False
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                camera_ok = True
            else:
                cap.release()
        
        if not camera_ok:
            print(lang.log('warning', 'camera_default_failed'))
            cam_index = select_camera(lang)
            if cam_index is None:
                input(lang.get_message('press_enter_to_exit'))
                exit()
            
            cap = cv2.VideoCapture(cam_index)
            if not cap.isOpened():
                print(lang.log('error', 'camera_selected_failed'))
                input(lang.get_message('press_enter_to_exit'))
                exit()
        
        print(lang.log('success', 'camera_opened'))
        
        print(lang.log('info', 'model_loading'))
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO
        )
        detector_engine = vision.PoseLandmarker.create_from_options(options)
        print(lang.log('success', 'model_loaded'))
        
        # 初始化邏輯
        squat_logic = SquatDetector(language=LANGUAGE)
        
        mp_drawing = mp.solutions.drawing_utils
        mp_drawing_styles = mp.solutions.drawing_styles
        mp_pose = mp.solutions.pose
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print(lang.log('warning', 'frame_read_failed'))
                break
            
            frame = cv2.resize(frame, (640, 480))
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            timestamp_ms = int(time.time() * 1000)
            
            results = detector_engine.detect_for_video(mp_image, timestamp_ms)
            
            if results.pose_landmarks:
                frame, info = squat_logic.process_frame(frame, results.pose_landmarks[0])
                
                proto_landmarks = landmark_pb2.NormalizedLandmarkList()
                proto_landmarks.landmark.extend([
                    landmark_pb2.NormalizedLandmark(x=lm.x, y=lm.y, z=lm.z)
                    for lm in results.pose_landmarks[0]
                ])
                
                mp_drawing.draw_landmarks(
                    frame,
                    proto_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
                )
            
            cv2.imshow('Squats Counter (Debug)', frame)
            
            if cv2.waitKey(5) & 0xFF == ord('q'):
                print(lang.log('info', 'user_exit'))
                break
    
    except KeyboardInterrupt:
        print(f"\n{lang.log('warning', 'user_interrupt')}")
    
    except Exception as e:
        import traceback
        print(f"\n{lang.log('error', 'critical_error')}")
        traceback.print_exc()
        input(lang.get_message('press_enter_to_exit'))
    
    finally:
        if 'cap' in locals() and cap.isOpened():
            cap.release()
        cv2.destroyAllWindows()
        
        if 'squat_logic' in locals():
            print(f"\n{lang.get_message('final_stats')}")
            print(f"{lang.get_message('total_count')}: {squat_logic.count}")
            print(f"{lang.get_message('correct_count')}: {squat_logic.correct}")
            print(f"{lang.get_message('wrong_count')}: {squat_logic.wrong}")
            
            # [新增] 測試模式印出詳細錯誤分析
            err_details = squat_logic.get_detailed_errors()
            if err_details:
                print(f"--- {lang.get_message('error_analysis')} ---")
                if err_details.get('fail_knee_angle', 0) > 0:
                    print(f"  {lang.get_message('err_knee_total')}: {err_details['fail_knee_angle']}")
                if err_details.get('fail_hip_angle', 0) > 0:
                    print(f"  {lang.get_message('err_hip_total')}: {err_details['fail_hip_angle']}")

            try:
                time_lbl = lang.get_message('total_time')
                if "Missing" in time_lbl: time_lbl = "Total Time"
            except:
                time_lbl = "Total Time"
            print(f"{time_lbl}: {squat_logic.get_total_time():.1f} s")