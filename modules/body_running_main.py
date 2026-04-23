# 檔名: body_running_main.py

import cv2
import numpy as np
import math
import time
import sys
import os
from PIL import Image, ImageDraw, ImageFont  # 新增: 用於繪製中文

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


class RunningDetector(BaseDetector):
    
    def __init__(self, config=None, language='ZH_TW'):
        super().__init__()
        
        self.lang = LanguageLoader('body_running_main', language)
        print(self.lang.log('info', 'system_init'))
        
        self.cfg = {
            'human_height': 170,
            'left_leg_up_knee_angle': 135,
            'left_leg_straight_knee_angle': 155,
            'right_leg_up_knee_angle': 135,
            'right_leg_straight_knee_angle': 155,
            'step_cooldown': 0.35,
            'visibility_threshold': 0.6,
            'auto_pause_seconds': 5.0
        }
        
        if config:
            self.cfg.update(config)
            print(self.lang.log('info', 'config_loaded'))
            
        self.human_height = self.cfg['human_height']
        self.step_cooldown = self.cfg['step_cooldown']
        self.auto_pause_seconds = self.cfg['auto_pause_seconds']
        
        self.actual_leg_length_cm = 0.0
        self.feet_distance_cm = 0.0
        self.max_stride_in_step = 0.0
        self.total_distance_cm = 0.0
        
        self.start_time = None
        self.last_step_time = time.time()  # 初始化為當前時間避免一開始就觸發過久閒置
        self.total_accumulated_time = 0.0
        self.last_activity_time = None
        
        self.last_triggered_side = None
        self.is_running = False
        
        self.draw_color_l = (0, 255, 255)
        self.draw_color_r = (0, 255, 255)
        
        # ★ 一開始必須是暫停狀態！避免把準備時間算進去
        self.is_paused = True

    def reset_state(self):
        self.max_stride_in_step = 0.0
        
    def get_total_time(self):
        current_segment = 0.0
        if self.start_time is not None and not self.is_paused:
            current_segment = time.time() - self.start_time
        return self.total_accumulated_time + current_segment

    # 新增: 繪製中文文字函式
    def draw_text_cn(self, img, text, pos, color=(255, 255, 255), size=30):
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        try:
            # 嘗試使用微軟正黑體 (Windows)
            font = ImageFont.truetype("msjh.ttc", size)
        except:
            try:
                # 嘗試使用常見的黑體
                font = ImageFont.truetype("simhei.ttf", size)
            except:
                # 最後手段：使用預設字體 (可能不支援中文)
                font = ImageFont.load_default()
        
        draw.text(pos, text, font=font, fill=color[::-1]) # BGR to RGB
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    def process_frame(self, img, landmarks):
        h, w, _ = img.shape
        current_time = time.time()
        
        def get_xy(i):
            return utils_math.get_landmark_xy(landmarks, i, w, h)
        
        def get_norm_xy(i):
            try:
                lm = landmarks[i]
                return (lm.x, lm.y)
            except:
                return (0, 0)
        
        def get_vis(i):
            try:
                return landmarks[i].visibility
            except:
                return 0.0
        
        detection_info = {
            'body_visible': True,
            'action_detected': False,
            'step_count': self.count,
            'distance_m': self.total_distance_cm / 100.0,
            'duration_sec': self.get_total_time(),
            'angles': {}
        }
        
        # ========== 2. 新增(容錯版)：檢查半邊身體是否入鏡 ==========
        def check_visible(lm):
            """檢查單一關鍵點是否在畫面內且可見度大於閾值"""
            try:
                return (lm.visibility >= self.cfg['visibility_threshold'] and 
                        0.0 <= lm.x <= 1.0 and 
                        0.0 <= lm.y <= 1.0)
            except:
                return False

        # 頭部 (鼻子:0)
        head_visible = check_visible(landmarks[0])
        # 手部 (左手腕:15 或 右手腕:16 擇一即可)
        hand_visible = check_visible(landmarks[15]) or check_visible(landmarks[16])
        # 腳部 (左腳踝:27 或 右腳踝:28 擇一即可)
        foot_visible = check_visible(landmarks[27]) or check_visible(landmarks[28])
        
        # 只要滿足頭、至少一手、至少一腳有在畫面內，就算有入鏡
        has_full_body = head_visible and hand_visible and foot_visible
        
        if not has_full_body:
            detection_info['body_visible'] = False
            
            cv2.rectangle(img, (0, 0), (w, 80), (0, 0, 0), -1)
            # 修改: 使用 draw_text_cn
            img = self.draw_text_cn(img, self.lang.get_message('warning_show_full_body'), (20, 20), (0, 0, 255), 40)
            
            if self.start_time is not None and not self.is_paused:
                self._pause_timer()
            
            return img, detection_info
            
        time_since_last_step = current_time - self.last_step_time
        if self.start_time is not None and not self.is_paused:
            if time_since_last_step > self.auto_pause_seconds:
                self._pause_timer()
        
        if self.is_paused:
            # 修改: 使用 draw_text_cn
            img = self.draw_text_cn(img, self.lang.get_message('status_paused'), (w//2 - 100, h//2), (0, 0, 255), 60)
            
        # 估算腿長與跨距
        nose = np.array(get_norm_xy(0))
        shoulder_l = np.array(get_norm_xy(11))
        shoulder_r = np.array(get_norm_xy(12))
        shoulder_mid = (shoulder_l + shoulder_r) / 2
        head_len = np.linalg.norm(nose - shoulder_mid) * 2
        
        hip_l = np.array(get_norm_xy(23))
        hip_r = np.array(get_norm_xy(24))
        hip_mid = (hip_l + hip_r) / 2
        body_len = np.linalg.norm(shoulder_mid - hip_mid)
        
        heel_l = np.array(get_norm_xy(27))
        heel_r = np.array(get_norm_xy(28))
        leg_len_norm_l = np.linalg.norm(hip_l - heel_l)
        leg_len_norm_r = np.linalg.norm(hip_r - heel_r)
        leg_len_norm = max(leg_len_norm_l, leg_len_norm_r)
        
        total_len_norm = head_len + body_len + leg_len_norm
        
        if total_len_norm > 0:
            ratio_pixel_to_cm = self.human_height / total_len_norm
            self.actual_leg_length_cm = leg_len_norm * ratio_pixel_to_cm
            
            feet_dist_norm = np.linalg.norm(heel_l - heel_r)
            self.feet_distance_cm = feet_dist_norm * ratio_pixel_to_cm
            
            if self.feet_distance_cm > self.max_stride_in_step:
                self.max_stride_in_step = self.feet_distance_cm
        
        # 計算膝蓋角度
        l_ang = utils_math.calculate_angle(get_xy(23), get_xy(25), get_xy(27))
        r_ang = utils_math.calculate_angle(get_xy(24), get_xy(26), get_xy(28))
        
        detection_info['angles']['left_knee'] = l_ang
        detection_info['angles']['right_knee'] = r_ang
        
        # 角度數字還是可以用 cv2.putText 因為是數字
        cv2.putText(img, f'{int(l_ang)}', (int(get_xy(25)[0]), int(get_xy(25)[1])-20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.draw_color_l, 2)
        cv2.putText(img, f'{int(r_ang)}', (int(get_xy(26)[0]), int(get_xy(26)[1])-20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.draw_color_r, 2)
        
        # 跑步計步邏輯
        if (current_time - self.last_step_time) > self.step_cooldown:
            if l_ang <= self.cfg['left_leg_up_knee_angle'] and r_ang >= 140:
                if self.last_triggered_side != 'Left':
                    self._trigger_step('Left')
                    self.last_step_time = current_time
                    self._resume_timer()
            
            elif r_ang <= self.cfg['right_leg_up_knee_angle'] and l_ang >= 140:
                if self.last_triggered_side != 'Right':
                    self._trigger_step('Right')
                    self.last_step_time = current_time
                    self._resume_timer()
        
        # ========== 5. 顯示資訊 (使用通用 draw_text) ==========
        total_sec = self.get_total_time()
        mins = int(total_sec // 60)
        secs = int(total_sec % 60)
        
        time_str = f"{self.lang.get_message('ui_time')}: {mins:02d}:{secs:02d}"
        dist_str = f"{self.lang.get_message('ui_dist')}: {self.total_distance_cm/100:.2f} m"
        step_str = f"{self.lang.get_message('ui_steps')}: {self.count}"
        
        # 使用繼承自 BaseDetector 的 draw_text 方法
        img = self.draw_text(img, time_str, (20, 40), (255, 255, 255), 32)
        img = self.draw_text(img, dist_str, (20, 80), (0, 255, 255), 32)
        img = self.draw_text(img, step_str, (20, 120), (0, 255, 0), 32)
        
        # 警告視窗也改用 draw_text
        if not has_full_body:
             img = self.draw_text(img, self.lang.get_message('warning_show_full_body'), (20, 50), (0, 0, 255), 40)
        
        if self.is_paused:
             img = self.draw_text(img, self.lang.get_message('status_paused'), (w//2 - 100, h//2), (0, 0, 255), 60)

        return img, detection_info

    def _trigger_step(self, side):
        self.count += 1
        self.last_triggered_side = side
        
        stride = self.max_stride_in_step
        if stride < 10: stride = 20
        if stride > 150: stride = 150
        
        self.total_distance_cm += stride
        self.max_stride_in_step = 0.0
        
        if side == 'Left':
            self.draw_color_l = (0, 0, 255)
            self.draw_color_r = (0, 255, 255)
        else:
            self.draw_color_l = (0, 255, 255)
            self.draw_color_r = (0, 0, 255)
            
        print(self.lang.log('success', 'step_recorded') + f" ({side}) - Stride: {stride:.1f} cm")
        
    def _pause_timer(self):
        if self.start_time is not None and not self.is_paused:
            segment = time.time() - self.start_time
            self.total_accumulated_time += segment
            self.start_time = None
            self.is_paused = True
            print(self.lang.log('warning', 'timer_paused'))
            
    def _resume_timer(self):
        if self.is_paused or self.start_time is None:
            self.start_time = time.time()
            self.is_paused = False
            print(self.lang.log('info', 'timer_resumed'))


# ... (Select camera 和 Main 不變，只需確保 import PIL) ...
def select_camera(lang):
    print(f"\n{lang.log('warning', 'camera_scan_start')}")
    available_cams = []
    for i in range(5):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) if os.name == 'nt' else cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                available_cams.append((i, f"Camera {i} ({w}x{h})\n")) # 修正 print 格式
            cap.release()
    
    if not available_cams:
        print(lang.log('error', 'camera_not_found'))
        return None
    
    if len(available_cams) == 1:
        return available_cams[0][0]
    
    print(f"\n{lang.get_message('camera_multiple_found')}")
    for idx, name in available_cams:
        print(f" [{idx}] {name}")
    
    try:
        sel = input(lang.get_message('camera_select_prompt') + ": ").strip()
        if sel == "": return available_cams[0][0]
        return int(sel)
    except:
        return available_cams[0][0]

if __name__ == "__main__":
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    from mediapipe.framework.formats import landmark_pb2
    
    # 記得把這裡改成 'ZH_TW' 或 'US_EN' 測試
    LANGUAGE = 'ZH_TW' 
    lang = LanguageLoader('body_running_main', LANGUAGE)
    
    MODEL_PATH = 'models/pose_landmarker.task'
    
    print(lang.log('info', 'test_mode_start'))
    
    if not os.path.exists(MODEL_PATH):
        print(lang.log('error', 'model_not_found') + f": {MODEL_PATH}")
        exit()
    
    try:
        cap = cv2.VideoCapture(2)
        if not cap.isOpened():
            idx = select_camera(lang)
            if idx is None: exit()
            cap = cv2.VideoCapture(idx)
            
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO
        )
        detector_engine = vision.PoseLandmarker.create_from_options(options)
        
        # 初始化邏輯
        running_logic = RunningDetector(language=LANGUAGE)
        
        mp_drawing = mp.solutions.drawing_utils
        mp_drawing_styles = mp.solutions.drawing_styles
        mp_pose = mp.solutions.pose
        
        print(lang.log('success', 'camera_opened'))
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            
            frame = cv2.resize(frame, (640, 480))
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            timestamp_ms = int(time.time() * 1000)
            
            results = detector_engine.detect_for_video(mp_image, timestamp_ms)
            
            if results.pose_landmarks:
                frame, info = running_logic.process_frame(frame, results.pose_landmarks[0])
                
                proto_landmarks = landmark_pb2.NormalizedLandmarkList()
                proto_landmarks.landmark.extend([
                    landmark_pb2.NormalizedLandmark(x=lm.x, y=lm.y, z=lm.z)
                    for lm in results.pose_landmarks[0]
                ])
                
                mp_drawing.draw_landmarks(
                    frame, proto_landmarks, mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style()
                )
            
            cv2.imshow('Running Counter (Debug)', frame)
            if cv2.waitKey(5) & 0xFF == ord('q'): break
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        
    finally:
        if 'cap' in locals() and cap.isOpened():
            cap.release()
        cv2.destroyAllWindows()
        
        if 'running_logic' in locals():
            print(f"\n{lang.get_message('final_stats')}")
            print(f"{lang.get_message('total_count')}: {running_logic.count}")
            print(f"{lang.get_message('total_time')}: {running_logic.get_total_time():.1f} {lang.get_message('unit_sec')}")
            print(f"{lang.get_message('total_dist')}: {running_logic.total_distance_cm/100:.2f} {lang.get_message('unit_meter')}")