// ActiTrack_Settings_Body.js
// 【功能】控制身體資料輸入表單，負責防呆驗證，並同步資料至系統設定與歷史紀錄

async function saveBodySettings() {
    // 1. 取得所有輸入框的數值
    const heightVal = document.getElementById('input-height').value;
    const weightVal = document.getElementById('input-weight').value;
    const ageVal    = document.getElementById('input-age').value;
    const bfVal     = document.getElementById('input-bf').value;
    const muscleVal = document.getElementById('input-muscle').value;
    const bmrVal    = document.getElementById('input-bmr').value;

    // 確保有抓到 dob 的 DOM，如果沒有填寫就給一個預設值，例如 "未提供" 或 "2000-01-01"
    const dobInput  = document.getElementById('input-dob');
    const dobVal    = (dobInput.value);
    // 2. 必填欄位檢查
    if (!heightVal || !weightVal) {
        alert("⚠️ 身高與體重為必填欄位！");
        return;
    }

    // 將字串轉換為數字
    const h = parseFloat(heightVal);
    const w = parseFloat(weightVal);
    const age = parseInt(ageVal) || 25; // 若未填寫年齡，預設為 25 歲

    // 3. 最大與最小值防呆檢查
    if (h < 50 || h > 300) { alert("❌ 身高數值異常 (限制 50~300 cm)"); return; }
    if (w < 10 || w > 500) { alert("❌ 體重數值異常 (限制 10~500 kg)"); return; }
    if (ageVal && (age < 1 || age > 150)) { alert("❌ 年齡數值異常 (限制 1~150 歲)"); return; }

    // 4. 準備發送給歷史紀錄 API 的完整資料 (包含所有選填生理數據)
    const fullBodyData = {
        height: h,
        weight: w,
        age: age,
        dob: dobVal ? dobVal : null,
        body_fat: parseFloat(bfVal) || 0,
        muscle: parseFloat(muscleVal) || 0,
        bmr: parseInt(bmrVal) || 0,
        update_time: new Date().toLocaleString()
    };
    console.log("準備送給後端的資料:", fullBodyData);

    
    // 5. 準備發送給系統設定 API 的核心資料 (AI 偵測器只需要這三個)
    const systemConfigData = {
        height: h,
        weight: w,
        age: age
    };

    // 如果這個 HTML 頁面裡也存在暱稱輸入框，就一併抓取更新 (相容舊邏輯)
    const nameInput = document.getElementById('user-name-input');
    if (nameInput && nameInput.value) {
        systemConfigData.username = nameInput.value;
    }

    // 6. 雙向同步發送資料到後端
    try {
        // [動作 A]：更新系統當前設定 (寫入 user_config.json 並更新 server 記憶體)
        const configUpdate = fetch('/api/save_user_config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(systemConfigData)
        });

        // [動作 B]：存入歷史紀錄 (建立 User_data_profile/YYYY/MM/DD 資料夾)
        const profileUpdate = fetch('/api/save_profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(fullBodyData)
        });

        // 同時等待兩個 API 請求完成
        const [resConfig, resProfile] = await Promise.all([configUpdate, profileUpdate]);

        if (resConfig.ok && resProfile.ok) {
            // --- 成功後的 UI 無聲提示 (按鈕變綠色) ---
            const saveBtn = document.querySelector('.btn-save');
            if (saveBtn) {
                const originalText = saveBtn.innerText;
                saveBtn.innerText = "已儲存 ✔";
                saveBtn.style.backgroundColor = "#219150"; // 成功綠色
                
                // 2 秒後恢復按鈕原始狀態
                setTimeout(() => {
                    saveBtn.innerText = originalText;
                    saveBtn.style.backgroundColor = "";
                }, 2000);
            }

            // --- 同步更新瀏覽器的 LocalStorage ---
            // 這樣使用者切換頁面時，不需要等後端回應，網頁就會立刻顯示最新身高體重
            const localConfig = JSON.parse(localStorage.getItem('actitrack_user_config') || '{}');
            localConfig.height = h;
            localConfig.weight = w;
            localConfig.age = age;
            if (systemConfigData.username) {
                localConfig.username = systemConfigData.username;
            }
            localStorage.setItem('actitrack_user_config', JSON.stringify(localConfig));

            console.log("✅ 生理數據已成功同步至系統與歷史紀錄");
            
            // 如果全域有掛載同步頭像與名稱的函式，順便觸發更新
            if (window.syncUsernameAndAvatar) {
                window.syncUsernameAndAvatar();
            }
        } else {
            console.warn("⚠️ 部分資料儲存可能失敗，請檢查後端日誌");
        }
    } catch (error) {
        console.error("❌ 儲存失敗:", error);
        alert("儲存發生錯誤，請檢查伺服器連線是否正常。");
    }
}