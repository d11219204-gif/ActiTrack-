/**
 * ActiTrack_Params_Editor.js
 * 簡化版：側邊欄由 actitrack-settings-ui.js 統一接管
 * 這裡專注於處理運動參數的讀取、產生編輯器與儲存/重製功能
 */

let globalDetectorsConfig = []; // 存放所有的運動設定陣列
let currentSelectedClass = null; // 目前選擇編輯的運動類別 (class)

// 當畫面載入完成時執行
document.addEventListener("DOMContentLoaded", async () => {
    // 側邊欄已經寫死在 HTML，並由 actitrack-settings-ui.js 接管了！
    // 我們只需要專心把參數載入就好
    await loadConfigAndMenu(); 
});

/**
 * 從後端抓取整合好的 Config (預設 + 使用者自訂)，並產生內部左側清單
 */
async function loadConfigAndMenu() {
    try {
        const configRes = await fetch('/api/get_detector_config');
        const configData = await configRes.json();
        globalDetectorsConfig = configData.detectors || [];

        // 若是從其他頁面過來，可能有正在運行的運動
        const currentRes = await fetch('/api/current_exercise');
        const currentData = await currentRes.json();
        const activeClass = currentData.class_name;

        renderExerciseList(globalDetectorsConfig, activeClass);
    } catch (error) {
        console.error("載入資料失敗:", error);
        document.getElementById('exercise-list-container').innerHTML = `<div style="color:red; text-align:center;">載入失敗，請確認後端運行中</div>`;
    }
}

/**
 * 渲染內部左側運動選擇清單
 */
function renderExerciseList(detectors, activeClass) {
    const container = document.getElementById('exercise-list-container');
    container.innerHTML = ''; 

    let firstAvailableClass = null;
    let targetClassToSelect = null;

    detectors.forEach(d => {
        // 只顯示有啟用的運動項目
        if (!d.enabled) return; 

        if (!firstAvailableClass) firstAvailableClass = d.class;
        
        // 簡單去掉 Detector 字眼當作顯示名稱
        let displayName = d.class.replace("Detector", "");

        const item = document.createElement('div');
        item.className = 'exercise-item';
        item.innerHTML = `<span>${displayName}</span>`;
        
        // 點擊事件：切換選中狀態並載入右側編輯器
        item.onclick = () => {
            document.querySelectorAll('.exercise-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            loadEditor(d.class);
        };

        container.appendChild(item);

        // 如果目前這個運動是後端正在運行的，自動記下來準備預設選中
        if (d.class === activeClass) {
            targetClassToSelect = d.class;
            item.classList.add('active'); 
        }
    });

    // 優先選中當前運動，若無則選中清單第一個
    const finalSelection = targetClassToSelect || firstAvailableClass;
    if (finalSelection) {
        loadEditor(finalSelection);
    } else {
        container.innerHTML = '<div style="text-align:center; color:#888;">目前沒有任何啟用的運動</div>';
    }
}

/**
 * 根據選擇的運動，動態產生右側的參數輸入框
 */
function loadEditor(className) {
    currentSelectedClass = className;
    const targetDetector = globalDetectorsConfig.find(d => d.class === className);
    
    if (!targetDetector) return;

    document.getElementById('current-edit-title').textContent = `${className.replace('Detector', '')} 參數設定`;
    document.getElementById('current-class-name').textContent = `Class: ${className}`;

    const container = document.getElementById('dynamic-fields-container');
    container.innerHTML = ''; 

    // 防呆處理：如果該運動點開後發現裡面沒有參數可調整
    if (!targetDetector.config || Object.keys(targetDetector.config).length === 0) {
        container.innerHTML = '<div style="text-align:center; margin-top:50px; color:#888; font-size:18px;">此運動目前無可調整的參數。</div>';
        return;
    }

    const section = document.createElement('div');
    section.className = 'section-block';
    
    const sectionTitle = document.createElement('div');
    sectionTitle.className = 'section-title';
    sectionTitle.textContent = '角度與時間設定 (Angle & Time)';
    section.appendChild(sectionTitle);

    // 遍歷 config 物件生成輸入框
    for (const [key, value] of Object.entries(targetDetector.config)) {
        const row = document.createElement('div');
        row.className = 'field-row';

        const label = document.createElement('div');
        label.className = 'field-label';
        label.textContent = formatConfigKey(key);

        const input = document.createElement('input');
        input.className = 'field-input';
        input.type = 'number';
        // 若名稱包含 seconds 或是 ratio，允許小數點輸入，否則視為整數(如角度)
        input.step = key.includes('seconds') || key.includes('ratio') ? '0.1' : '1'; 
        input.value = value;
        input.dataset.key = key; // 利用 dataset 綁定原本的 key

        row.appendChild(label);
        row.appendChild(input);
        section.appendChild(row);
    }

    container.appendChild(section);
}

/**
 * 格式化參數鍵值 (例如: waist_up_angle -> Waist Up Angle)
 */
function formatConfigKey(key) {
    return key.split('_')
              .map(word => word.charAt(0).toUpperCase() + word.slice(1))
              .join(' ');
}

/**
 * 儲存修改的設定到後端
 */
async function saveConfig() {
    if (!currentSelectedClass) return;

    const inputs = document.querySelectorAll('.field-input');
    if(inputs.length === 0) return;

    const newConfig = {};
    inputs.forEach(input => {
        newConfig[input.dataset.key] = parseFloat(input.value);
    });

    const payload = {
        class_name: currentSelectedClass,
        config: newConfig
    };

    try {
        const response = await fetch('/api/save_detector_config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();

        if (result.status === 'success') {
            showToast("參數已儲存並套用！(不影響系統預設檔)");
            // 更新本地快取
            const target = globalDetectorsConfig.find(d => d.class === currentSelectedClass);
            if (target) target.config = newConfig;
        } else {
            alert("儲存失敗：" + result.message);
        }
    } catch (error) {
        console.error("儲存發生錯誤:", error);
        alert("儲存發生錯誤，請檢查網路或後端狀態。");
    }
}

/**
 * 還原預設值
 */
async function resetToDefault() {
    const currentClassName = currentSelectedClass; 
    if (!currentClassName) return;

    const targetDetector = globalDetectorsConfig.find(d => d.class === currentClassName);
    if (!targetDetector || !targetDetector.config || Object.keys(targetDetector.config).length === 0) return;

    if (!confirm(`確定要將 ${currentClassName} 恢復為預設參數嗎？`)) return;

    try {
        const response = await fetch('/api/reset_detector_config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ class_name: currentClassName })
        });
        const result = await response.json();
        
        if (result.status === "success") {
            alert("已恢復預設！頁面即將重新整理。");
            location.reload(); 
        } else if (result.status === "no_change") {
            alert(result.message);
        } else {
            alert("重製失敗：" + result.message);
        }
    } catch (e) {
        console.error("重製失敗:", e);
        alert("重製發生錯誤");
    }
}

/**
 * 顯示浮動提示訊息
 */
function showToast(msg) {
    const toast = document.getElementById('toast-msg');
    toast.textContent = msg;
    toast.style.opacity = '1';
    setTimeout(() => { toast.style.opacity = '0'; }, 3000);
}