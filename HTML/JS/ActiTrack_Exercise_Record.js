// =============================================
// ActiTrack_Exercise_Record.js
// 功能：從 API 取得運動記錄，整理後以卡片形式渲染至畫面，支援多資料來源切換
// =============================================

/* 【全域變數】
   globalExerciseData     → 整理完成的記錄資料（排序時重複使用，避免重新呼叫 API）
   globalDynamicExNameMap → 從 API 動態取得的「class_name → 顯示名稱」翻譯字典
   globalDefaultExNameMap → 預設翻譯字典
   QUERY_MODE             → 目前的查詢模式 ('hybrid', 'json', 'sql') */
let globalExerciseData = null;
let globalDynamicExNameMap = {};
let globalDefaultExNameMap = {};
let QUERY_MODE = 'hybrid'; // 預設使用混合模式

/* 【字串正規化函式】
   將運動名稱轉為統一格式以利比對，例如："PushUpDetector" → "pushup" */
function cleanStringForMatch(str) {
    if (!str) return "";
    return str.toLowerCase().replace(/detector/g, "").replace(/[^a-z0-9]/g, "");
}

/* 【DOMContentLoaded】HTML 載入完成後自動執行 */
document.addEventListener('DOMContentLoaded', () => {
    // 如果有 ActiTrackUI 模組，先執行初始化
    if (typeof ActiTrackUI !== 'undefined') {
        ActiTrackUI.init();
    }
    
    setupSortListener();
    setupModeListener(); // 註冊模式切換監聽器
    fetchAndRenderRecords();
    
    // ==========================================
    // ★ 新增：綁定同步按鈕的點擊事件
    // ==========================================
    const syncBtn = document.getElementById('btn-sync-db');
    if (syncBtn) {
        syncBtn.addEventListener('click', async () => {
            // 防止重複點擊，並顯示處理中狀態
            const originalText = syncBtn.innerText;
            syncBtn.innerText = "⏳ 同步中...";
            syncBtn.disabled = true;
            syncBtn.style.backgroundColor = "#95a5a6";

            try {
                const response = await fetch('/api/sync_records', { method: 'POST' });
                const result = await response.json();

                if (result.status === 'success') {
                    // 顯示後端回傳的成功訊息
                    alert(`✅ 同步成功！\n${result.message}`);
                    
                    // 同步完畢後，自動重新載入畫面卡片
                    fetchAndRenderRecords(); 
                } else {
                    alert(`❌ 同步失敗: ${result.message}`);
                }
            } catch (error) {
                console.error("同步 API 發生錯誤:", error);
                alert('❌ 無法連線至伺服器');
            } finally {
                // 恢復按鈕狀態
                syncBtn.innerText = originalText;
                syncBtn.disabled = false;
                syncBtn.style.backgroundColor = "#3498db";
            }
        });
    }

});

/* 【排序事件監聽】
   選單值改變時，直接用已有資料重新渲染（不重新呼叫 API） */
function setupSortListener() {
    const sortSelect = document.getElementById('sort-order');
    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
            if (globalExerciseData) {
                renderRecords(globalExerciseData, e.target.value);
            }
        });
    }
}

/* 【資料來源模式切換監聽】
   選單值改變時，更新 QUERY_MODE 並重新向後端請求資料 */
function setupModeListener() {
    const modeSelect = document.getElementById('query-mode');
    if (modeSelect) {
        // 確保初始狀態與變數一致
        modeSelect.value = QUERY_MODE; 
        
        modeSelect.addEventListener('change', (e) => {
            QUERY_MODE = e.target.value;
            console.log(`[UI] 切換查詢模式至: ${QUERY_MODE}`);
            fetchAndRenderRecords(); // 重新呼叫 API
        });
    }
}

/* 【時間字串解析函式】
   將 "YYYY/MM/DD HH:mm:ss" 轉為時間戳，供排序使用 */
function parseTaiwanTime(dateStr) {
    if (!dateStr) return 0;
    return new Date(dateStr).getTime() || 0;
}

/* 【顯示載入中狀態】 */
function showLoadingState() {
    const container = document.getElementById('records-container');
    if (container) {
        container.innerHTML = '<div class="loading" style="text-align:center; padding: 20px; color: #7f8c8d;">資料載入中...</div>';
    }
}

/* 【主要 API 請求】從後端取得記錄資料 */
async function fetchAndRenderRecords() {
    try {
        showLoadingState();
        
        // 🌟 使用動態 QUERY_MODE 參數
        const apiUrl = `/api/get_records?source=${QUERY_MODE}`;
        const response = await fetch(apiUrl);
        
        if (!response.ok) throw new Error(`API 請求失敗，狀態碼: ${response.status}`);
        const data = await response.json();

        let allRecords = [];

        // 防呆機制：確保 data 是一個陣列 (避免後端回傳單一物件導致 forEach 報錯)
        const dataArray = Array.isArray(data) ? data : (data.data ? data.data : [data]);

        // 扁平化資料結構 (萬用相容版)
        dataArray.forEach(item => {
            // 🌟 關鍵相容處理：
            // 如果有 exercise_records，代表是 JSON 巢狀格式；
            // 如果沒有，代表這層本身就是 SQL 的平鋪紀錄，就把 item 直接包成陣列。
            const records = item.exercise_records ? item.exercise_records : [item];
            
            records.forEach(rec => {
                // 如果沒有時間資料，代表不是有效的紀錄，直接跳過
                const recTime = rec.timestamp || rec.time;
                if (!recTime) return;

                // 處理 body_wrong：如果是從 SQL 來的，有時候會是字串 (Stringified JSON)
                let parsedBodyWrong = {};
                try {
                    if (typeof rec.body_wrong === 'string') {
                        parsedBodyWrong = JSON.parse(rec.body_wrong);
                    } else {
                        parsedBodyWrong = rec.body_wrong || rec.bodyWrong || {};
                    }
                } catch (e) {
                    console.warn("body_wrong 解析失敗", rec.body_wrong);
                }

                allRecords.push({
                    time: recTime,
                    timestampMs: parseTaiwanTime(recTime), // 確保你有 parseTaiwanTime 這個函式
                    exerciseName: rec.exercise_name || rec.exerciseName || "未知運動",
                    // 兼容 snake_case 與 camelCase
                    totalCount: rec.total_count !== undefined ? rec.total_count : (rec.totalCount !== undefined ? rec.totalCount : null),
                    correctCount: rec.correct_count !== undefined ? rec.correct_count : (rec.correctCount !== undefined ? rec.correctCount : null),
                    wrongCount: rec.wrong_count !== undefined ? rec.wrong_count : (rec.wrongCount !== undefined ? rec.wrongCount : null),
                    accuracy: rec.accuracy !== undefined ? rec.accuracy : null,
                    durationSec: rec.duration_sec !== undefined ? rec.duration_sec : (rec.durationSec !== undefined ? rec.durationSec : null),
                    distanceM: rec.distance_m !== undefined ? rec.distance_m : (rec.distanceM !== undefined ? rec.distanceM : null),
                    bodyWrong: parsedBodyWrong
                });
            });
        });

        // 存入全域變數供排序使用
        globalExerciseData = allRecords;
        
        // 取得目前選取的排序方式
        const sortSelect = document.getElementById('sort-order');
        const sortOrder = sortSelect ? sortSelect.value : 'desc';
        
        // 執行渲染
        renderRecords(globalExerciseData, sortOrder);

    } catch (error) {
        console.error('取得記錄失敗:', error);
        const container = document.getElementById('records-container'); // 確定這裡是有 s 的
        if (container) {
            container.innerHTML = `<div class="no-data" style="text-align:center; padding: 20px; color: #e74c3c;">無法載入記錄: ${error.message}</div>`;
        }
    }
}

/* 【渲染畫面】將資料轉換為 HTML 卡片 */
function renderRecords(records, sortOrder = 'desc') {
    const container = document.getElementById('records-container');
    if (!container) return;

    if (!records || records.length === 0) {
        container.innerHTML = '<div class="no-data" style="text-align:center; padding: 20px; color: #7f8c8d;">目前尚無任何運動記錄。</div>';
        return;
    }

    // 1. 執行排序
    records.sort((a, b) => {
        return sortOrder === 'desc' ? b.timestampMs - a.timestampMs : a.timestampMs - b.timestampMs;
    });

    // 2. 依照日期 (YYYY/MM/DD) 進行群組化
    const grouped = {};
    records.forEach(rec => {
        const datePart = rec.time.split(' ')[0] || "未知日期";
        if (!grouped[datePart]) {
            grouped[datePart] = [];
        }
        grouped[datePart].push(rec);
    });

    // 3. 生成 HTML
    let html = '';
    Object.keys(grouped).forEach(date => {
        html += `
            <div class="date-group">
                <div class="date-title">📅 ${date}</div>
                <div class="record-grid">
        `;
        
        grouped[date].forEach(record => {
            const exName = record.exerciseName || "未知運動";
            let statsHtml = '';

            // 總次數
            if (record.totalCount !== null) {
                statsHtml += `<div class="stat-item"><span class="stat-label">總次數</span><span class="stat-val">${record.totalCount}</span></div>`;
            }

            // 準確率：null 時顯示 0%
            const accuracyDisplay = record.accuracy !== null ? `${record.accuracy}%` : '0%';
            statsHtml += `<div class="stat-item"><span class="stat-label">準確率</span><span class="stat-val">${accuracyDisplay}</span></div>`;

            // 運動時長：null 時顯示「未知」
            const durationDisplay = record.durationSec !== null ? `${record.durationSec} 秒` : "未知";
            statsHtml += `<div class="stat-item"><span class="stat-label">運動時長</span><span class="stat-val">${durationDisplay}</span></div>`;
            
            // 移動距離：僅在有資料時顯示（如跑步類運動）
            if (record.distanceM !== null) {
                statsHtml += `<div class="stat-item"><span class="stat-label">移動距離</span><span class="stat-val">${record.distanceM} 公尺</span></div>`;
            }

            // 🌟 額外擴充功能：如果 bodyWrong 有資料，將錯誤部位顯示出來
            if (record.bodyWrong && Object.keys(record.bodyWrong).length > 0) {
                let wrongTags = Object.entries(record.bodyWrong)
                    .map(([key, count]) => `<span style="font-size:0.8em; background:#ffeaa7; color:#d63031; padding:2px 6px; border-radius:4px; margin-right:4px;">${key}(${count})</span>`)
                    .join('');
                
                statsHtml += `<div class="stat-item" style="grid-column: 1 / -1;"><span class="stat-label">細部錯誤</span><div style="display:inline-block;">${wrongTags}</div></div>`;
            }

            // 取得時間部分 HH:mm:ss
            const timePart = record.time.split(' ')[1] || record.time;

            html += `
                    <div class="record-card">
                        <div class="record-header">
                            <span class="time-badge">🕒 ${timePart}</span>
                            <span class="ex-name">${exName}</span>
                        </div>
                        <div class="record-body">
                            ${statsHtml}
                        </div>
                    </div>
            `;
        });
        html += `</div></div>`;
    });

    // 4. 寫入 DOM
    container.innerHTML = html;
}