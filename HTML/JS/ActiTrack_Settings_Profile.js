// ActiTrack_Settings_Profile.js
// 【功能】控制個人資料設定頁，包含大頭貼裁切上傳、暱稱修改、字體大小設定、AI 模型切換

document.addEventListener('DOMContentLoaded', () => {

    const avatarTrigger    = document.getElementById('avatar-trigger');
    const avatarBtnTrigger = document.getElementById('avatar-btn-trigger');
    const fileInput        = document.getElementById('file-input');
    const cropModal        = document.getElementById('crop-modal');
    const imageToCrop      = document.getElementById('image-to-crop');
    const cropCancel       = document.getElementById('crop-cancel');
    const cropConfirm      = document.getElementById('crop-confirm');
    let cropper = null;

    // =========================================================
    // --- 1. Toast 通知 ---
    // =========================================================
    // [BUG FIX #1] 原始 if (!toast){ 區塊從未關閉，導致 Section 2~7 全被包在裡面：
    //   - 頁面載入時 window.updateUsername 未掛載 → 按鈕 onclick 直接報錯
    //   - loadCameraConfig / loadAiModel 不會在頁面載入時執行
    //   - 每次顯示通知都會重新綁定一次事件監聽器
    function showNotification(msg, type = 'success') {
        let toast = document.getElementById('actitrack-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'actitrack-toast';
            document.body.appendChild(toast);
            toast.style.cssText = `
                position:fixed; bottom:30px; right:30px;
                padding:15px 25px; border-radius:10px;
                color:#fff; font-size:16px; font-weight:bold;
                z-index:9999; box-shadow:0 4px 12px rgba(0,0,0,0.3);
                transition:opacity 0.3s, transform 0.3s;
            `;
        } // ← [BUG FIX #1] 正確關閉 if (!toast)

        // [BUG FIX #2] 加入 'info' 類型（藍色），避免模型切換提示顯示成紅色
        const colorMap = { success: '#2ecc71', error: '#e74c3c', info: '#3498db' };
        toast.style.backgroundColor = colorMap[type] || colorMap.error;
        toast.style.transform = 'translateY(0)';
        toast.style.opacity   = '1';
        toast.style.display   = 'block';
        toast.innerText       = msg;

        setTimeout(() => {
            toast.style.opacity   = '0';
            toast.style.transform = 'translateY(20px)';
            setTimeout(() => { toast.style.display = 'none'; }, 300);
        }, 2500);
    }

    // =========================================================
    // --- 2. 大頭貼裁切與上傳 ---
    // =========================================================
    function triggerFileInput() { if (fileInput) fileInput.click(); }
    if (avatarTrigger)    avatarTrigger.addEventListener('click', triggerFileInput);
    if (avatarBtnTrigger) avatarBtnTrigger.addEventListener('click', triggerFileInput);

    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (event) => {
                    if (imageToCrop) imageToCrop.src = event.target.result;
                    if (cropModal)   cropModal.style.display = 'flex';
                    if (cropper)     cropper.destroy();
                    cropper = new Cropper(imageToCrop, {
                        aspectRatio: 1, viewMode: 1, dragMode: 'move',
                        autoCropArea: 0.8, restore: false, guides: false,
                        center: false, highlight: false,
                        cropBoxMovable: false, cropBoxResizable: false,
                        toggleDragModeOnDblclick: false,
                    });
                };
                reader.readAsDataURL(file);
            }
            fileInput.value = '';
        });
    }

    function closeCropModal() {
        if (cropModal) cropModal.style.display = 'none';
        if (cropper)   { cropper.destroy(); cropper = null; }
    }

    if (cropCancel) cropCancel.addEventListener('click', closeCropModal);

    if (cropConfirm) {
        cropConfirm.addEventListener('click', () => {
            if (!cropper) return;
            const canvas = cropper.getCroppedCanvas({ width: 300, height: 300,
                imageSmoothingEnabled: true, imageSmoothingQuality: 'high' });
            canvas.toBlob(async (blob) => {
                const formData = new FormData();
                formData.append('file', blob, 'user_avatar.jpg');
                const originalBtnText = cropConfirm.innerText;
                cropConfirm.innerText = '上傳中...';
                cropConfirm.disabled  = true;
                try {
                    const response = await fetch('/api/upload_avatar', { method: 'POST', body: formData });
                    if (response.ok) {
                        const result = await response.json();
                        if (result.status === 'success') {
                            closeCropModal();
                            showNotification('✅ 頭貼更新成功！', 'success');
                            localStorage.setItem('actitrack_avatar_time', new Date().getTime());
                            if (typeof window.syncUsernameAndAvatar === 'function')
                                window.syncUsernameAndAvatar();
                        } else {
                            showNotification('❌ 圖片上傳失敗，請稍後再試。', 'error');
                        }
                    } else {
                        throw new Error('網路請求失敗');
                    }
                } catch (error) {
                    showNotification('❌ 發生錯誤，無法連接到伺服器。', 'error');
                } finally {
                    cropConfirm.innerText = originalBtnText;
                    cropConfirm.disabled  = false;
                }
            }, 'image/jpeg', 0.8);
        });
    }

    // =========================================================
    // --- 3. 暱稱、模型與頭像形狀儲存 ---
    // =========================================================
    async function updateUsername() {
        const camWidth  = document.getElementById('cam-width');
        const camHeight = document.getElementById('cam-height');

        const usernameInput = document.getElementById('user-name-input');
        if (!usernameInput) {
            console.error("嚴重錯誤：HTML 找不到 id='user-name-input' 的輸入框！");
            showNotification('❌ 系統錯誤：找不到輸入框。', 'error');
            return;
        }

        // 注意：updateUsername 儲存目前選單上的模型值（可能是 "" 空白的預設提示選項）
        // 只有在有選擇非空值時才帶入，否則維持原本設定
        const modelSelect = document.getElementById('model-select');
        const modelVal    = (modelSelect && modelSelect.value) ? modelSelect.value : null;

        const newName = usernameInput.value.trim();
        if (newName.length === 0 || newName.length > 20) {
            showNotification('❌ 名稱長度須介於 1~20 字元', 'error');
            return;
        }

        const shapeSelect  = document.getElementById('avatar-shape-select');
        const newShape     = shapeSelect ? shapeSelect.value : 'circle';
        const currentScale = localStorage.getItem('actitrack_font_scale') || 1;

        // 儲存攝影機解析度
        if (camWidth && camHeight && camWidth.value && camHeight.value) {
            fetch('/api/save_detector_system_config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_width:  parseInt(camWidth.value),
                    video_height: parseInt(camHeight.value)
                })
            }).then(res => res.json())
              .then(data => console.log('攝影機解析度儲存結果:', data))
              .catch(err  => console.error('攝影機解析度儲存失敗:', err));
        }

        // 組合送出的資料（若模型選單為空白提示選項則不覆蓋模型設定）
        const payload = {
            username:     newName,
            avatar_shape: newShape,
            font_scale:   parseFloat(currentScale)
        };
        if (modelVal) payload.mediapipe_model = modelVal;

        try {
            const response = await fetch('/api/save_user_config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (response.ok) {
                showNotification('✅ 設定與字體更新成功！', 'success');
                localStorage.setItem('actitrack_avatar_time', new Date().getTime());
                const cachedData        = JSON.parse(localStorage.getItem('actitrack_user_config') || '{}');
                cachedData.username     = newName;
                cachedData.avatar_shape = newShape;
                cachedData.font_scale   = parseFloat(currentScale);
                localStorage.setItem('actitrack_user_config', JSON.stringify(cachedData));
                if (typeof window.syncUsernameAndAvatar === 'function')
                    window.syncUsernameAndAvatar();
            } else {
                showNotification('❌ 伺服器拒絕請求，儲存失敗。', 'error');
            }
        } catch (error) {
            showNotification('❌ 網路請求失敗。', 'error');
        }
    }

    // =========================================================
    // --- 4. 字體大小初始化 ---
    // =========================================================
    async function loadFontScale() {
        try {
            const response   = await fetch('/api/get_user_config');
            const config     = await response.json();
            const savedScale = config.font_scale || localStorage.getItem('actitrack_font_scale') || 1;

            document.documentElement.style.setProperty('--font-scale', savedScale);
            localStorage.setItem('actitrack_font_scale', savedScale);

            const select        = document.getElementById('font-scale-select');
            const customWrapper = document.getElementById('custom-scale-wrapper');
            const customInput   = document.getElementById('font-scale-custom');
            if (select && customWrapper && customInput) {
                const presetValues = ["0.8", "1", "1.2", "1.5"];
                if (presetValues.includes(savedScale.toString())) {
                    select.value              = savedScale.toString();
                    customWrapper.style.display = 'none';
                } else {
                    select.value              = 'custom';
                    customWrapper.style.display = 'flex';
                    customInput.value         = Math.round(savedScale * 100);
                }
            }
        } catch (e) {
            console.error("讀取字體設定失敗:", e);
        }
    }

    // =========================================================
    // --- 5. 字體選單切換邏輯 ---
    // =========================================================
    window.handleFontScaleChange = function () {
        const select        = document.getElementById('font-scale-select');
        const customWrapper = document.getElementById('custom-scale-wrapper');
        const customInput   = document.getElementById('font-scale-custom');
        if (!select) return;
        if (select.value === 'custom') {
            customWrapper.style.display = 'flex';
            if (!customInput.value) customInput.value = 100;
            window.applyCustomFontScale();
        } else {
            customWrapper.style.display = 'none';
            setFontScaleAndSave(parseFloat(select.value));
        }
    };

    window.applyCustomFontScale = function () {
        const customInput = document.getElementById('font-scale-custom');
        if (!customInput) return;
        let percentage = parseInt(customInput.value);
        if (isNaN(percentage)) percentage = 100;
        if (percentage < 50)  percentage = 50;
        if (percentage > 300) percentage = 300;
        customInput.value = percentage;
        setFontScaleAndSave(percentage / 100);
    };

    async function setFontScaleAndSave(scaleValue) {
        document.documentElement.style.setProperty('--font-scale', scaleValue);
        localStorage.setItem('actitrack_font_scale', scaleValue);
        try {
            const response = await fetch('/api/save_user_config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ font_scale: scaleValue })
            });
            if (response.ok) {
                console.log(`✅ 字體大小 ${scaleValue} 已存入`);
                const cachedData      = JSON.parse(localStorage.getItem('actitrack_user_config') || '{}');
                cachedData.font_scale = scaleValue;
                localStorage.setItem('actitrack_user_config', JSON.stringify(cachedData));
            }
        } catch (error) {
            console.error("❌ 網路請求失敗:", error);
        }
    }

    // =========================================================
    // --- 6. AI 模型切換 ---
    // =========================================================

    // 更新「目前模型」小字顯示
    function updateModelDisplay(modelName, isError = false) {
        const displayDiv = document.getElementById('current-model-display');
        if (!displayDiv) return;
        displayDiv.innerText = isError
            ? '🔴 無法取得目前模型資訊'
            : `目前使用：${modelName}`;
        displayDiv.style.color = isError ? '#e74c3c' : '#27ae60';
    }

    // [BUG FIX #3] 原本呼叫 /api/get_current_model（不存在的端點），
    //              正確端點為 /api/get_model_info，回傳 { current_model, model_id }
    async function loadAiModel() {
        try {
            const res  = await fetch('/api/get_model_info');
            const data = await res.json();
            // 更新「目前模型」小字
            updateModelDisplay(data.current_model || 'Unknown');
        } catch (e) {
            console.error("無法載入 AI 模型資訊", e);
            updateModelDisplay('', true);
        }
    }

    // [BUG FIX #4] model_id 偏移（-1 效應）根本原因：
    //   model_loader.py 的 self.models 字典鍵為 "1"/"2"/"3"（1-indexed）
    //   但 HTML <option value="0/1/2"> 送出的是 0-indexed → 全部少 1
    //   解法：HTML 的 option value 改為 "1"/"2"/"3"（見 HTML 修改說明）
    //   changeAiModel 本身不需轉換，直接把選單值送給後端即可
    async function changeAiModel(modelId) {
        if (!modelId) return; // 選到「請選擇...」預設選項時不動作

        showNotification('🔄 模型切換中，請稍候...', 'info');

        try {
            const res  = await fetch('/api/switch_model', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ model_id: modelId })
            });
            const data = await res.json();

            if (data.status === 'success') {
                showNotification('✅ 模型切換成功！下次偵測生效', 'success');
                // 切換成功後重新抓取並更新小字顯示
                loadAiModel();
            } else {
                showNotification('❌ 模型切換失敗：' + (data.message || ''), 'error');
            }
        } catch (e) {
            showNotification('❌ 網路發生錯誤，無法切換模型。', 'error');
        }

        // 切換後讓選單回到「請選擇...」預設提示選項
        const modelSelect = document.getElementById('model-select');
        if (modelSelect) modelSelect.value = '';
    }

    // =========================================================
    // --- 7. 攝影機解析度載入 ---
    // =========================================================
    async function loadCameraConfig() {
        try {
            const response = await fetch('/api/get_detector_system_config');
            if (response.ok) {
                const data = await response.json();
                const wEl  = document.getElementById('cam-width');
                const hEl  = document.getElementById('cam-height');
                if (wEl) wEl.value = data.video_width;
                if (hEl) hEl.value = data.video_height;
            }
        } catch (error) {
            console.error('讀取攝影機解析度失敗:', error);
        }
    }

    // =========================================================
    // --- 初始化（頁面載入時執行）---
    // [BUG FIX #1 後續] 這些呼叫原本全被包在 showNotification 的 if 區塊內，
    //                   只有在第一次通知顯示後才會執行
    // =========================================================
    loadCameraConfig();
    loadFontScale();
    loadAiModel(); // [BUG FIX #3] 原本沒有在初始化時呼叫 loadAiModel

    window.changeAiModel  = changeAiModel;
    window.updateUsername = updateUsername;

}); // DOMContentLoaded 結束
