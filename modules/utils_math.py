# 檔名: utils_math.py
import math
import numpy as np

def calculate_angle(a, b, c):
    """
    計算三點之間的夾角 (與原本邏輯完全一致)
    """
    v1 = np.array(a) - np.array(b)
    v2 = np.array(c) - np.array(b)

    # 防止浮點誤差導致 math domain error
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0

    cosine = np.dot(v1, v2) / (norm_v1 * norm_v2)
    cosine = np.clip(cosine, -1.0, 1.0) 
    angle = math.degrees(math.acos(cosine))
    return angle

def get_landmark_xy(landmarks, index, width, height):
    """相容性函數：處理新版 MediaPipe 的物件屬性存取"""
    try:
        # 新版 Tasks API 回傳的是物件，用 .x .y 存取
        lm = landmarks[index]
        return (lm.x * width, lm.y * height)
    except:
        return (0, 0)
