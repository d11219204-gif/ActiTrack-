// ActiTrack_BMI_Record.js
// 【功能】控制 BMI 歷史紀錄頁面，從後端取得資料後以卡片形式顯示

// 全域變數：暫存從 API 取得的原始資料，切換排序時不必重新請求
let globalBodyData = null;

// 頁面載入完成後執行初始化
document.addEventListener('DOMContentLoaded', () => {
    setupSortListener();         // 監聽排序下拉選單的變更
    fetchAndRenderBodyRecords(); // 從後端取得資料並渲染
});

// 監聽 <select id="sort-order"> 的 change 事件，有資料時直接重新渲染（不重新呼叫 API）
function setupSortListener() {
    const sortSelect = document.getElementById('sort-order');
    if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
            if (globalBodyData) renderBodyRecords(globalBodyData, e.target.value);
        });
    }
}

// 將後端回傳的台灣時間字串（如 "2026/2/24 上午5:15:00"）轉為毫秒數，供排序比較使用
function parseTaiwanTime(dateStr) {
    if (!dateStr) return 0;
    const parts = dateStr.split(' ');
    if (parts.length < 2) return new Date(dateStr).getTime() || 0;
    
    const dPart = parts[0]; // 日期部分
    const tPart = parts[1]; // 時間部分（含上午/下午）
    let h = 0, m = 0, s = 0;
    
    let isPM = tPart.includes('下午');
    let cleanTime = tPart.replace('上午', '').replace('下午', ''); // 去除中文，保留 "5:15:00"
    let tSplits = cleanTime.split(':');
    
    if (tSplits.length >= 2) {
        h = parseInt(tSplits[0]);
        m = parseInt(tSplits[1]);
        s = parseInt(tSplits[2] || 0);
    }
    
    // 12 小時制 → 24 小時制轉換
    if (isPM && h !== 12) h += 12;
    if (!isPM && h === 12) h = 0;
    
    return new Date(`${dPart} ${h}:${m}:${s}`).getTime();
}

// 呼叫 API 取得身體紀錄，存入 globalBodyData 後交給 renderBodyRecords 渲染
async function fetchAndRenderBodyRecords() {
    const container = document.getElementById('records-container');
    try {
        const response = await fetch('/api/get_body_records');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        
        globalBodyData = await response.json(); // 回應轉為 JSON 物件
        
        if (!globalBodyData || globalBodyData.length === 0) {
            container.innerHTML = '<div class="loading-text">目前尚無歷史BMI數值紀錄。</div>';
            return;
        }

        const sortSelect = document.getElementById('sort-order');
        const sortOrder = sortSelect ? sortSelect.value : 'desc'; // 預設新→舊
        renderBodyRecords(globalBodyData, sortOrder);

    } catch (error) {
        console.error("載入紀錄失敗:", error);
        container.innerHTML = '<div class="loading-text" style="color:#e74c3c;">資料載入失敗，請確認伺服器連線與 API 設定。</div>';
    }
}

// 將資料依日期分組、排序後，組成卡片 HTML 並一次寫入 DOM
function renderBodyRecords(data, sortOrder) {
    const container = document.getElementById('records-container');

    // Step 1：依日期分組 → { "2026/2/24": [record, ...], ... }
    const groupedRecords = {};
    data.forEach(record => {
        const dateStr = record.last_updated || "";
        const parts = dateStr.split(' ');
        const datePart = parts[0] || "未知日期";
        const timePart = parts.slice(1).join(' ') || "";

        record.displayTime = timePart;
        record.parsedTimeMs = parseTaiwanTime(dateStr); // 預先解析毫秒供排序用

        if (!groupedRecords[datePart]) groupedRecords[datePart] = [];
        groupedRecords[datePart].push(record);
    });

    // Step 2：依 sortOrder 排序日期（desc = 新→舊，asc = 舊→新）
    const sortedDates = Object.keys(groupedRecords).sort((a, b) => {
        const dateA = new Date(a).getTime() || 0;
        const dateB = new Date(b).getTime() || 0;
        return sortOrder === 'desc' ? dateB - dateA : dateA - dateB;
    });

    // Step 3：組合 HTML 字串
    let html = '';
    sortedDates.forEach(date => {
        html += `<div class="date-group">
                    <div class="date-title">📅 ${date}</div>
                    <div class="record-grid">`;
        
        let dailyRecords = groupedRecords[date];

        // 同日內也依時間排序
        dailyRecords.sort((a, b) =>
            sortOrder === 'desc' ? b.parsedTimeMs - a.parsedTimeMs : a.parsedTimeMs - b.parsedTimeMs
        );

        dailyRecords.forEach(record => {
            const basic = record.basic_info || {};
            const opt   = record.optional_info || {};
            const height = basic.height_cm || 0;
            const weight = basic.weight_kg || 0;
            
            // BMI = 體重(kg) ÷ 身高(m)²
            let bmiDisplay = "-";
            if (height > 0 && weight > 0) {
                const heightInMeter = height / 100;
                bmiDisplay = (weight / (heightInMeter * heightInMeter)).toFixed(1);
            }

            // 選填欄位若為 null 則顯示 "-"
            const bodyFat = opt.body_fat_percent   != null ? `${opt.body_fat_percent}%`     : "-";
            const muscle  = opt.skeletal_muscle_kg != null ? `${opt.skeletal_muscle_kg} kg` : "-";
            const age     = opt.age                != null ? `${opt.age} 歲`                : "-";

            html += `
                <div class="record-card">
                    <div class="record-header">
                        <span class="time-badge">🕒 ${record.displayTime}</span>
                        <span class="ex-name">身體數值紀錄</span>
                    </div>
                    <div class="record-body">
                        <div class="stat-item"><span class="stat-label">身高</span><span class="stat-val">${height} cm</span></div>
                        <div class="stat-item"><span class="stat-label">體重</span><span class="stat-val">${weight} kg</span></div>
                        <div class="stat-item"><span class="stat-label">BMI</span><span class="stat-val">${bmiDisplay}</span></div>
                        <div class="stat-item"><span class="stat-label">年齡</span><span class="stat-val">${age}</span></div>
                        <div class="stat-item"><span class="stat-label">體脂率</span><span class="stat-val">${bodyFat}</span></div>
                        <div class="stat-item"><span class="stat-label">骨骼肌</span><span class="stat-val">${muscle}</span></div>
                    </div>
                </div>
            `;
        });
        html += `</div></div>`;
    });

    // Step 4：一次性寫入 DOM（比逐筆操作 DOM 更有效率）
    container.innerHTML = html;
}
