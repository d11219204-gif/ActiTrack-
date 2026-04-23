# Detector Config 參數說明書

本檔案對應 `detector_config.json` 中的各項設定參數。

## 1. System Settings (系統設定)

| 參數 | 說明 | 建議值 |
| :--- | :--- | :--- |
| `camera_id` | 攝影機編號 (0 為預設, 1 為外接) | 0 |
| `video_width` | 畫面寬度 | 640 |
| `video_height` | 畫面高度 | 480 |
| `target_correct_count` | 每個運動的目標次數 (達標後顯示 GOAL) | 10 |
| `max_wrong_tolerance` | **自動卸載閾值**：當某個運動錯誤次數超過此值，且尚未鎖定任何運動時，系統會自動停止偵測該項目，節省資源。 | 5 |
| `lock_threshold` | **自動鎖定閾值**：當某個運動正確次數達到此值，系統會判定使用者正在做此運動，並強制關閉其他所有偵測器。 | 3 |

## 2. Detectors (運動模組設定)

### JumpingJackDetector (開合跳)
*   `arm_down_angle`: 手臂放下時的角度 (越小越嚴格) -> 45
*   `arm_up_angle`: 手臂舉起時的角度 (越大越嚴格) -> 155
*   `knee_strict_angle`: 膝蓋打直的判定角度 -> 165

### PushUpDetector (伏地挺身)
*   `elbow_up_angle`: 手肘撐起時的角度 (接近 180 代表直) -> 150
*   `elbow_down_angle`: 手肘下壓時的角度 (越小越低) -> 120
*   `hip_straight_angle`: 腰部是否打直 (防止塌腰/翹臀) -> 135

### SquatDetector (深蹲)
*   `waist_down_angle`: 下蹲時大腿與身體夾角 (90度代表標準坐姿) -> 90
*   `waist_up_angle`: 站立時角度 -> 120
*   `knee_down_angle`: 下蹲時膝蓋角度 -> 90

### SitUpDetector (仰臥起坐)
*   `waist_down_angle`: 躺下時腰部角度 -> 95
*   `waist_up_angle`: 坐起時腰部角度 -> 55
*   `arm_ratio_threshold`: **手部抱頭判定閾值**。數值越小代表手離耳朵越近。 -> 0.45
*   `knee_wrong_angle`: 膝蓋伸直錯誤判定 (180為全直，170代表微彎) -> 170

### RunningDetector (原地跑)
*   `human_height`: 預設身高 (會被使用者輸入覆蓋) -> 170
*   `step_cooldown`: 兩步之間的最小間隔秒數 (防抖動) -> 0.35
*   `auto_pause_seconds`: 幾秒沒動自動暫停計時 -> 5.0

每個 Detector 可以設定：
- `target_correct_count`: 該運動的目標次數 (達標後顯示 GOAL)
- `max_wrong_tolerance`: 該運動的錯誤容忍次數 (超過此值自動卸載)

### 範例：
```json
{
    "module": "body_situp_main",
    "class": "SitUpDetector",
    "target_correct_count": 10,
    "max_wrong_tolerance": 8,
    ...
}
